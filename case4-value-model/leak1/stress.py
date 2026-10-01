"""X1 part 6b: the stress test. Does layer 2 still link correctly when the world is as messy as real data?

Part 6 ran on a world whose only noise was in the keys. Dates, prices and dealer codes always agreed with the car,
and no typo went beyond two edits. That flatters both Splink and the plain rule. This script rebuilds what a
detector reads with realistic noise at three levels, and re-runs layer 1, Splink and the rule on each:
  0 = the clean world, which must reproduce part 6 exactly;
  1 = moderate, at the rates in `spec.py`;
  2 = every rate doubled.

  fleet batches   fleet cars of one make, model, trim and registration day go through one dealer, so identical
                  cars share dealer, day and price (level 1 and up)
  invoice price   for a share of cars, programme amounts are computed on the invoice price (catalogue x 0.95-1.10)
  date offset     a share of claims carry a sale-event date 1-7 days off
  date swap       a few claims have day and month swapped
  dealer code     a share of claims are filed under another dealer's code in the same system
  heavy typo      a share of the mistyped keys get one or two more characters wrong, beyond the rule's reach

The noise touches only what a detector reads. No label changes: a noisy claim is still clean, or still a leak, and
leak euros follow the noisy amount. Nothing is written to disk; every level runs in memory. The rates are ASSUMPTION
settings in `spec.py`. Results are synthetic and scored with the same strict scorer.
Usage: .venv/bin/python leak1/stress.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from generate import SYN, setting  # noqa: E402
from layer1_keys import layer1, load  # noqa: E402
from layer2_splink import (BAND, accepted, anchor_m, best_candidates, link_accuracy, records,  # noqa: E402
                           resolve, rule_candidates, train)
from population import ALPHABET  # noqa: E402
from score import score  # noqa: E402
from spec import LEAKS, PROGRAMMES  # noqa: E402

LEVELS = [0, 1, 2]
SEED = 66  # part 6b


def more_edits(s, rng, alphabet, start=0):
    """One or two more characters replaced, from position `start` on."""
    v = list(s)
    for _ in range(int(rng.integers(1, 3))):
        i = int(rng.integers(start, len(v)))
        options = alphabet.replace(v[i], "")
        v[i] = options[int(rng.integers(0, len(options)))]
    return "".join(v)


def stressed(level, claims, master, truth, dealers):
    """The detector-side world at a stress level, and the truth with leak euros following the noisy amounts."""
    if level == 0:
        return claims, master, truth, {}, pd.DataFrame({"claim_id": claims["claim_id"]})
    rng = np.random.default_rng(SEED + level)

    def rate(name):
        return min(1.0, level * setting(name))

    cols = list(claims.columns)
    c = claims.merge(truth[["claim_id", "car_id", "label", "detail"]], on="claim_id", validate="one_to_one")
    m, t, n = master.copy(), truth.copy(), len(c)
    D = dealers.set_index("dealer_id")
    realised = {}

    # fleet batches: identical fleet cars registered on one day go through one dealer
    f = m[m["buyer"].eq("fleet")].sort_values("car_id")
    lead = f.groupby([f["make"], f["model"], f["trim"].fillna(""), f["registration_date"]])["dealer_id"] \
            .transform("first")
    m.loc[lead.index, "dealer_id"] = lead
    old = c["car_id"].map(master.set_index("car_id")["dealer_id"])
    new = c["car_id"].map(m.set_index("car_id")["dealer_id"])
    new_code = pd.Series(np.where(c["system"].eq("A"), new.map(D["code_a"]), new.map(D["code_b"])), index=c.index)
    moved = new.ne(old).fillna(False) & new_code.notna()
    c.loc[moved, "dealer"] = new_code[moved]
    realised["fleet_batch_claims_moved"] = int(moved.sum())

    # invoice price: one factor per car, applied to every percentage-of-price claim of that car
    cars = m["car_id"].to_numpy()
    factor = pd.Series(np.where(rng.random(len(cars)) < rate("stress_invoice_price"),
                                rng.uniform(0.95, 1.10, len(cars)), 1.0), index=cars)
    f_claim = c["car_id"].map(factor).astype(float)
    phantom = c["car_id"].isna()
    f_claim[phantom] = np.where(rng.random(phantom.sum()) < rate("stress_invoice_price"),
                                rng.uniform(0.95, 1.10, phantom.sum()), 1.0)
    basis = PROGRAMMES.set_index(["system", "code"])["basis"]
    pct = pd.Series([basis[k] == "pct_list" for k in zip(c["system"], c["programme"])], index=c.index)
    priced = pct & f_claim.ne(1.0)
    c.loc[priced, "amount_net"] = (c.loc[priced, "amount_net"] * f_claim[priced]).round(2)
    realised["invoice_priced_claims"] = int(priced.sum())

    # sale-event dates keyed a few days off, and day-month swaps
    off = rng.random(n) < rate("stress_date_offset")
    shift = rng.integers(1, 8, n) * np.where(rng.random(n) < 0.5, -1, 1)
    c.loc[off, "event_date"] = c.loc[off, "event_date"] + pd.to_timedelta(shift[off], unit="D")
    e = c["event_date"]
    swap = (rng.random(n) < rate("stress_date_swap")) & e.dt.day.le(12) & e.dt.day.ne(e.dt.month)
    c.loc[swap, "event_date"] = pd.to_datetime(pd.DataFrame(
        {"year": e[swap].dt.year, "month": e[swap].dt.day, "day": e[swap].dt.month}))
    realised["date_offset_claims"], realised["date_swap_claims"] = int(off.sum()), int(swap.sum())

    # dealer codes: another dealer's code in the same system
    err = rng.random(n) < rate("stress_dealer_code")
    for system, col in (("A", "code_a"), ("B", "code_b")):
        pool = D[col].dropna().to_numpy()
        idx = c.index[err & c["system"].eq(system)]
        for i in idx:
            options = pool[pool != c.at[i, "dealer"]]
            c.at[i, "dealer"] = options[int(rng.integers(0, len(options)))]
    realised["dealer_code_claims"] = int(err.sum())

    # heavy typos: mistyped keys get one or two more characters wrong
    vin_typo = c["label"].eq("vin_typo") | (c["label"].eq("legit_key_typo") & c["detail"].str.startswith("vin"))
    order_typo = c["label"].eq("legit_key_typo") & c["detail"].eq("order")
    heavy = rng.random(n) < rate("stress_heavy_typo")
    for i in c.index[heavy & vin_typo & c["vin"].notna()]:
        c.at[i, "vin"] = more_edits(c.at[i, "vin"], rng, ALPHABET)
    for i in c.index[heavy & order_typo]:
        c.at[i, "order_no"] = more_edits(c.at[i, "order_no"], rng, "0123456789", start=2)
    realised["heavy_typo_claims"] = int((heavy & (vin_typo | order_typo)).sum())

    leak = t["label"].isin(LEAKS)
    amount = t["claim_id"].map(c.set_index("claim_id")["amount_net"])
    t["leak_eur"] = np.where(leak, amount, 0.0)
    noise = pd.DataFrame({"claim_id": c["claim_id"], "fleet batch": moved, "invoice price": priced,
                          "date keyed off": off | swap, "wrong dealer code": err,
                          "heavy typo": heavy & (vin_typo | order_typo)})
    return c[cols], m, t, realised, noise


def run_level(level, claims, master, truth, dealers):
    c, m, t, realised, noise = stressed(level, claims, master, truth, dealers)
    l1, _ = layer1(c, m)
    band_ids = l1.loc[l1["reason"].isin(BAND), "claim_id"].to_numpy()
    left, right = records(c[c["claim_id"].isin(band_ids)], m, dealers)
    mm, _ = anchor_m(c, m, dealers, l1)
    best = best_candidates(train(left, right, mm))
    runs = {"layer 1 only": None, "splink": accepted(best), "rule": rule_candidates(left, right)}
    rows = []
    for name, suggested in runs.items():
        flags = l1 if suggested is None else resolve(c, m, l1, suggested)
        h, _, _ = score(flags, t)
        acc = link_accuracy(band_ids, suggested, t) if suggested is not None else {}
        rows.append({"level": level, "method": name, **acc,
                     **{k: h[k] for k in ["precision", "recall", "euro_recall", "false_alarms_per_1000_legit",
                                          "review_load_per_1000"]}})
        if level == 0 and name == "splink":
            saved = pd.read_parquet(SYN / "x1_flags_layer2.parquet")  # compare content; parquet changes dtypes
            assert (flags["claim_id"].equals(saved["claim_id"])
                    and flags["reason"].fillna("").astype(str).equals(saved["reason"].fillna("").astype(str))
                    and flags["car_id"].astype("Float64").fillna(-1).equals(saved["car_id"].astype("Float64").fillna(-1))), \
                "level 0 must reproduce part 6"
    trained = {"dealer m": mm["dealer_id"][0], "exact date m (A)": mm["reg_date"][0],
               "price within EUR 1 m": mm["price"][0]}
    # where each method fails: of the real band claims hit by each kind of noise, the share left without a car
    causes = []
    if level > 0:
        real = t.set_index("claim_id").loc[band_ids, "car_id"].notna()
        real_ids = real.index[real]
        nz = noise.set_index("claim_id").loc[real_ids]
        for cause in nz.columns:
            hit = nz.index[nz[cause]]
            if len(hit):
                causes.append({"level": level, "noise": cause, "real band claims hit": len(hit),
                               **{f"unlinked, {k}": round(1 - pd.Index(hit).isin(runs[k].index).mean(), 3)
                                  for k in ("splink", "rule")}})
        clean = nz.index[~nz.any(axis=1)]
        causes.append({"level": level, "noise": "none of these", "real band claims hit": len(clean),
                       **{f"unlinked, {k}": round(1 - pd.Index(clean).isin(runs[k].index).mean(), 3)
                          for k in ("splink", "rule")}})
    return rows, realised, trained, causes


def main():
    claims, master = load()
    truth = pd.read_parquet(SYN / "x1_truth.parquet")
    dealers = pd.read_parquet(SYN / "x1_dealers.parquet")
    rows, causes = [], []
    for level in LEVELS:
        r, realised, trained, cz = run_level(level, claims, master, truth, dealers)
        rows += r
        causes += cz
        print(f"level {level}: noise {realised or 'none'}")
        print(f"         anchor-measured m: " + ", ".join(f"{k} {v:.3f}" for k, v in trained.items()))
    print("\nlevel 0 reproduces part 6 exactly\n")
    out = pd.DataFrame(rows)
    for col in ["precision", "recall", "euro_recall"]:
        out[col] = (100 * out[col]).round(1)
    for col in ["false_alarms_per_1000_legit", "review_load_per_1000"]:
        out[col] = out[col].round(2)
    out = out.rename(columns={"false_alarms_per_1000_legit": "false_alarms_1k", "review_load_per_1000": "review_1k",
                              "phantom_linked": "phantom_in", "phantom_unlinked": "phantom_out"})
    print(out.fillna("").to_string(index=False))
    print("\nwhere each method fails: share of real band claims left without a car, by the noise that hit them")
    print("(a claim can be hit by several kinds of noise)")
    print(pd.DataFrame(causes).to_string(index=False))


if __name__ == "__main__":
    main()
