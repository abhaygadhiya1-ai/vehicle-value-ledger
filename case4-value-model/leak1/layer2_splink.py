"""X1 part 6, layer 2: Fellegi-Sunter matching (Splink) on the claims layer 1 could not link.

Layer 1 leaves a band of claims it cannot link: an unknown VIN, an unknown order number, or a key conflict. Most are
legitimate claims with a mistyped key. Some are leaks: a duplicate filed under a mistyped VIN, or a phantom order.
Keys cannot tell them apart. Layer 2 asks which car each claim in the band most likely belongs to, then re-runs
layer 1's duplicate logic with those suggested cars:
  - the suggested car already has a live claim of the same family -> duplicate (flag)
  - the suggested car has no such claim -> the key was mistyped; pass, with the key corrected
  - no car reaches the threshold -> unmatched (flag): the phantom-order case

**The model.** Fellegi-Sunter, in Splink 4 on DuckDB, links the band's claims to the vehicle record.
  - VIN and order number: 1 edit, 2 edits (Damerau-Levenshtein), else. There is no exact level: a claim with an
    exact key was linked by layer 1 and never reaches the band.
  - Dealer: exact.
  - The claim's sale event against the car's registration date (A) or order date (B): same day, within 7 days,
    within 30 days, else.
  - The list price implied by the amount: within EUR 1, within EUR 250, else. Flat programmes imply no price.
  - Brand system: exact.
Training is unsupervised and never reads the truth table:
  - the prior (the chance two random records match) is 1 / number of cars, since a claim belongs to at most one car;
  - u comes from random sampling;
  - m for the non-key comparisons (dealer, dates, price, system) is *measured*, not fitted: on the claims layer 1
    linked by an exact key, how often each field agrees with the claim's own car (Laplace-smoothed). Those links
    come from the data, not the truth table. These m values are then fixed.
  - m for the keys (VIN, order number) comes from expectation maximisation within dealer blocks.
  Two plain-EM designs were tried first and rejected:
    - blocking on part of the VIN groups cars of one model, year and plant, so EM learned "same model at the same
      time" rather than "same car" (it put the dealer match at 4.5% among true matches);
    - blocking on dealer and then on exact dates still mis-learned the B side, where the band holds very few true
      matches among the phantoms (dealer match 64%, exact order date 18%).
**The decision rule:** accept the best candidate when its match probability is at least 0.5 (more likely than not)
*and* it holds at least half the evidence among all the claim's candidate cars (its share of their summed Bayes
factors). The threshold was fixed before any result. The share condition was added before the stress test (part
6b), for a reason the clean world exposed. Fellegi-Sunter scores each pair on its own and does not know a claim
belongs to at most one car. EM, seeing identical fleet cars at one dealer on one day, learned that about 8% of true
matches carry an unrelated VIN, so such a batch-mate can pass 0.5 too. A near-miss VIN still wins its batch
outright; a genuinely ambiguous claim stays unlinked. (A first version, "no second car reaches 0.5", left 76 good
claims unlinked in the clean world and was replaced.) Other thresholds are shown for sensitivity; none is chosen
from them.

**The rule it must beat (skeptic A9).** A plain deterministic rule on the same band: the same dealer, and the VIN
(or, for a claim with no VIN, the order number) within two edits of a car's. The closest car wins; a tie stays
unlinked. Splink earns its place only if it beats this rule on the same scorer.

Caveat: dealer codes are never mistyped in this world, so blocking and matching on dealer are perfect here. In real
data they are not. All results are synthetic; they measure the tool, not the group.

Outputs (data/synthetic/): x1_flags_layer2.parquet (Splink), x1_flags_rule2.parquet (the rule),
x1_splink_model.json (the trained model).
Usage: .venv/bin/python leak1/layer2_splink.py
"""
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import splink.comparison_level_library as cll
import splink.comparison_library as cl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from generate import SYN  # noqa: E402
from layer1_keys import duplicates, load, with_family  # noqa: E402
from score import score, show  # noqa: E402
from spec import PROGRAMMES  # noqa: E402

THRESHOLD = 0.5  # fixed in advance: more likely than not
SENSITIVITY = [0.5, 0.8, 0.9, 0.99]
BAND = {"unknown_vin", "unknown_order", "key_conflict"}
MODEL = SYN / "x1_splink_model.json"


def records(claims, master, dealers):
    """The band's claims and the vehicle record, in the same columns, for linking."""
    code = {k: v for col in ["code_a", "code_b"] for k, v in zip(dealers[col], dealers["dealer_id"]) if pd.notna(k)}
    prog = PROGRAMMES.set_index(["system", "code"])
    rate = np.array([prog.at[k, "amount"] if prog.at[k, "basis"] == "pct_list" else np.nan
                     for k in zip(claims["system"], claims["programme"])])
    left = pd.DataFrame({
        "unique_id": claims["claim_id"].to_numpy(), "vin": claims["vin"].to_numpy(),
        "order_no": claims["order_no"].to_numpy(), "dealer_id": claims["dealer"].map(code).to_numpy(),
        "reg_date": claims["event_date"].where(claims["system"].eq("A")).to_numpy(),
        "order_date": claims["event_date"].where(claims["system"].eq("B")).to_numpy(),
        "price": np.where(claims["amount_net"].to_numpy() > 0, claims["amount_net"].to_numpy() / rate, np.nan),
        "system": claims["system"].to_numpy(),
    })
    right = pd.DataFrame({
        "unique_id": master["car_id"].astype(str).to_numpy(), "vin": master["vin"].to_numpy(),
        "order_no": master["order_no"].to_numpy(), "dealer_id": master["dealer_id"].to_numpy(),
        "reg_date": master["registration_date"].to_numpy(), "order_date": master["order_date"].to_numpy(),
        "price": master["list_price_eur"].astype(float).to_numpy(), "system": master["system"].to_numpy(),
    })
    return left, right


def key_comparison(col):
    return cl.CustomComparison([
        cll.NullLevel(col), cll.DamerauLevenshteinLevel(col, 1), cll.DamerauLevenshteinLevel(col, 2),
        cll.ElseLevel()], output_column_name=col)


def anchor_m(claims, master, dealers, l1):
    """m for the non-key comparisons, measured on the claims layer 1 linked by an exact key: the share of those
    claims whose dealer, sale-event date, implied price and system fall in each level against their own car.
    Laplace-smoothed, so no level is ever impossible. Uses the data only, never the truth table."""
    a = claims.merge(l1[["claim_id", "car_id"]], on="claim_id")
    a = a[a["car_id"].notna() & (a["amount_net"] > 0)]
    rec, _ = records(a, master, dealers)
    car = master.set_index("car_id").loc[a["car_id"].astype("int64").to_numpy()]
    day = lambda x, y: (pd.Series(x) - pd.Series(y)).abs().dt.days.to_numpy()  # noqa: E731
    fields = {
        "dealer_id": np.where(rec["dealer_id"].to_numpy() == car["dealer_id"].to_numpy(), 0, 1),
        "reg_date": np.digitize(day(rec["reg_date"], car["registration_date"].to_numpy()), [1, 8, 31]),
        "order_date": np.digitize(day(rec["order_date"], car["order_date"].to_numpy()), [1, 8, 31]),
        "price": np.digitize(np.abs(rec["price"].to_numpy() - car["list_price_eur"].to_numpy()), [1.0000001, 250.0000001]),
        "system": np.where(rec["system"].to_numpy() == car["system"].to_numpy(), 0, 1),
    }
    nulls = {"reg_date": rec["reg_date"].isna(), "order_date": rec["order_date"].isna(), "price": rec["price"].isna()}
    m = {}
    for name, level in fields.items():
        level = level[~nulls[name].to_numpy()] if name in nulls else level
        k = 2 if name in ("dealer_id", "system") else (4 if "date" in name else 3)
        counts = np.bincount(level, minlength=k)[:k]
        m[name] = (counts + 1) / (counts.sum() + k)
    return m, len(a)


def fixed(level, m):
    return level.configure(m_probability=float(m), fix_m_probability=True)


def train(left, right, m):
    def dates(col):
        return cl.CustomComparison([
            cll.NullLevel(col), fixed(cll.ExactMatchLevel(col), m[col][0]),
            fixed(cll.AbsoluteDateDifferenceLevel(col, input_is_string=False, threshold=7, metric="day"), m[col][1]),
            fixed(cll.AbsoluteDateDifferenceLevel(col, input_is_string=False, threshold=30, metric="day"), m[col][2]),
            fixed(cll.ElseLevel(), m[col][3])], output_column_name=col)

    def exact(col):
        return cl.CustomComparison([cll.NullLevel(col), fixed(cll.ExactMatchLevel(col), m[col][0]),
                                    fixed(cll.ElseLevel(), m[col][1])], output_column_name=col)

    settings = SettingsCreator(
        link_type="link_only",
        probability_two_random_records_match=1 / len(right),
        comparisons=[
            key_comparison("vin"),
            key_comparison("order_no"),
            exact("dealer_id"),
            dates("reg_date"),
            dates("order_date"),
            cl.CustomComparison([cll.NullLevel("price"), fixed(cll.AbsoluteDifferenceLevel("price", 1), m["price"][0]),
                                 fixed(cll.AbsoluteDifferenceLevel("price", 250), m["price"][1]),
                                 fixed(cll.ElseLevel(), m["price"][2])], output_column_name="price"),
            exact("system"),
        ],
        blocking_rules_to_generate_predictions=[
            block_on("dealer_id"),
            "substr(l.vin, 1, 11) = substr(r.vin, 1, 11)",
            "substr(l.vin, 10, 8) = substr(r.vin, 10, 8)",
            "substr(l.order_no, 3, 4) = substr(r.order_no, 3, 4)",
            "substr(l.order_no, 7, 4) = substr(r.order_no, 7, 4)",
        ],
    )
    linker = Linker([left, right], settings, db_api=DuckDBAPI(), input_table_aliases=["claims", "cars"],
                    set_up_basic_logging=False)
    linker.training.estimate_u_using_random_sampling(max_pairs=2e7, seed=6)
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("dealer_id"))
    return linker


def best_candidates(linker):
    """Each band claim's most likely car, its match probability, and its share of the evidence among the claim's
    candidates (claims with no pair above 1% are absent)."""
    p = linker.inference.predict(threshold_match_probability=0.01).as_pandas_dataframe()
    left_is_claim = p["source_dataset_l"].eq("claims")
    p["claim_id"] = p["unique_id_l"].where(left_is_claim, p["unique_id_r"])
    p["car_id"] = p["unique_id_r"].where(left_is_claim, p["unique_id_l"]).astype("int64")
    p = p.sort_values(["claim_id", "match_probability", "car_id"], ascending=[True, False, True])
    rel = np.exp2(p["match_weight"] - p.groupby("claim_id")["match_weight"].transform("max"))
    p["share"] = rel / rel.groupby(p["claim_id"]).transform("sum")
    return p.drop_duplicates("claim_id").set_index("claim_id")[["car_id", "match_probability", "share"]]


def accepted(best, threshold=THRESHOLD):
    """The decision rule: the best car reaches the threshold and holds at least half the evidence."""
    ok = best["match_probability"].ge(threshold) & best["share"].ge(0.5)
    return best.loc[ok, "car_id"]


def rule_candidates(left, right):
    """The deterministic rule: same dealer, key within two edits; the closest car wins, a tie stays unlinked."""
    con = duckdb.connect()
    con.register("claims", left)
    con.register("cars", right)
    d = con.sql("""
        select l.unique_id as claim_id, cast(r.unique_id as bigint) as car_id,
               case when l.vin is not null then damerau_levenshtein(l.vin, r.vin)
                    else damerau_levenshtein(l.order_no, r.order_no) end as dist
        from claims l join cars r on l.dealer_id = r.dealer_id
        where (l.vin is not null and damerau_levenshtein(l.vin, r.vin) <= 2)
           or (l.vin is null and damerau_levenshtein(l.order_no, r.order_no) <= 2)
    """).df()
    d = d[d["dist"].eq(d.groupby("claim_id")["dist"].transform("min"))]
    d = d[d.groupby("claim_id")["car_id"].transform("size").eq(1)]
    return d.set_index("claim_id")["car_id"]


def resolve(claims, master, l1, suggested):
    """Layer 1's flags, with the band's claims re-linked to their suggested cars and the duplicate logic re-run."""
    c = with_family(claims).merge(l1[["claim_id", "reason", "car_id"]], on="claim_id", validate="one_to_one")
    band = c["reason"].isin(BAND)
    c.loc[band, "car_id"] = c.loc[band, "claim_id"].map(suggested).astype("Int64")
    reason = pd.Series(pd.NA, index=c.index, dtype="object")
    still = band & c["car_id"].isna()
    reason[still & c["vin"].notna()] = "unmatched_vin"
    reason[still & c["vin"].isna()] = "unmatched_order"
    dup, _ = duplicates(c, master)
    reason[dup] = "duplicate"
    return pd.DataFrame({"claim_id": c["claim_id"], "reason": reason, "car_id": c["car_id"]})


def link_accuracy(band_ids, suggested, truth):
    """Scorer-side only: did each band claim get its true car?"""
    t = truth.set_index("claim_id").loc[band_ids]
    got = pd.Series(band_ids, index=band_ids).map(suggested)
    real = t["car_id"].notna()
    return {"band": len(t), "right_car": int((real & got.eq(t["car_id"]).fillna(False)).sum()),
            "wrong_car": int((real & got.notna() & got.ne(t["car_id"]).fillna(False)).sum()),
            "no_car": int((real & got.isna()).sum()),
            "phantom_linked": int((~real & got.notna()).sum()), "phantom_unlinked": int((~real & got.isna()).sum())}


def print_model(path):
    """Match weights per comparison level, from the saved model: what the unsupervised training learned."""
    for comp in json.loads(path.read_text())["comparisons"]:
        levels = []
        for lv in comp["comparison_levels"]:
            if lv.get("is_null_level"):
                continue
            m, u = lv.get("m_probability"), lv.get("u_probability")
            w = np.log2(m / u) if m and u else float("nan")
            levels.append(f"{lv.get('label_for_charts', '?')}: {w:+.1f} (m {m:.3f})")
        print(f"  {comp['output_column_name']}: " + "; ".join(levels))


def main():
    claims, master = load()
    dealers = pd.read_parquet(SYN / "x1_dealers.parquet")
    l1 = pd.read_parquet(SYN / "x1_flags_layer1.parquet")
    truth = pd.read_parquet(SYN / "x1_truth.parquet")
    band_ids = l1.loc[l1["reason"].isin(BAND), "claim_id"].to_numpy()
    left, right = records(claims[claims["claim_id"].isin(band_ids)], master, dealers)
    print(f"band: {len(left):,} claims layer 1 could not link; vehicle record: {len(right):,} cars\n")
    if len(left) == 0:  # nothing to link (found by the red team, whose world has no broken keys)
        flags = resolve(claims, master, l1, pd.Series(dtype="int64"))
        show(flags, "layers 1+2 (empty band: layer 1 passed through)")
        for name in ["x1_flags_layer2", "x1_flags_rule2"]:
            flags.to_parquet(SYN / f"{name}.parquet", index=False)
        return

    m, n_anchor = anchor_m(claims, master, dealers, l1)
    print(f"non-key m measured on {n_anchor:,} exact-key links: " + "; ".join(
        f"{k} {np.round(v, 4).tolist()}" for k, v in m.items()) + "\n")
    linker = train(left, right, m)
    linker.misc.save_model_to_json(str(MODEL), overwrite=True)
    print("trained match weights (log2 Bayes factor; + is evidence for a match):")
    print_model(MODEL)
    best = best_candidates(linker)
    again = best_candidates(train(left, right, m))
    assert best["car_id"].equals(again["car_id"]), "training is not reproducible"

    rule = rule_candidates(left, right)
    print("\nwho got the right car (scorer side):")
    runs = {"splink": accepted(best), "rule": rule}
    for name, s in runs.items():
        print(f"  {name}: {link_accuracy(band_ids, s, truth)}")

    print(f"\nthreshold sensitivity (the headline uses {THRESHOLD}, fixed in advance):")
    rows = []
    for t in SENSITIVITY:
        h, _, _ = score(resolve(claims, master, l1, accepted(best, t)), truth)
        rows.append({"threshold": t, **{k: round(v, 4) for k, v in h.items() if k not in ("claims",)}})
    print(pd.DataFrame(rows).to_string(index=False))

    h1, _, _ = score(l1, truth)
    print(f"\nlayer 1 alone: precision {h1['precision']:.1%} | recall {h1['recall']:.1%} | euro recall "
          f"{h1['euro_recall']:.1%} | false alarms {h1['false_alarms_per_1000_legit']:.2f} per 1,000\n")
    flags2 = resolve(claims, master, l1, runs["splink"])
    show(flags2, "layers 1+2, Splink")
    print()
    flags_rule = resolve(claims, master, l1, rule)
    show(flags_rule, "layers 1+2, the deterministic rule")
    flags2.to_parquet(SYN / "x1_flags_layer2.parquet", index=False)
    flags_rule.to_parquet(SYN / "x1_flags_rule2.parquet", index=False)


if __name__ == "__main__":
    main()
