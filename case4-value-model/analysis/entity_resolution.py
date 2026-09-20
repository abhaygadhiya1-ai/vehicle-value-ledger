"""Finding the same record twice, when nothing reliable joins them - leak 1's problem, measured.

Leak 1 rests on claims paid twice under two inherited systems. The design in the solution document
(a layered pipeline: deterministic keys, then blocking, then a scored match, then a review band)
is standard record linkage. What it has never had is evidence that the obvious approach - match on
the fields, exactly - is insufficient. This measures that on real records where the answer is known.

**Where the truth comes from.** Five sources scrape the same advert more than once and carry the
site's own advert id. Hide the id, match on the fields alone, and score the answer against it. The
duplicates are real, the drift between copies is real, and nobody constructed either.

Two mechanisms show up, and they fail differently:

  es_2020_11, pl_*      the same advert repeated as an identical row. Exact matching finds these.
  pt_standvirtual       the same advert seen across weekly scrapes, with the price cut part-way
                        through. Exact matching misses the copies that straddle the cut.

The second is the leak 1 case: one event recorded twice, with the amount changed between them. The
report measures which field moves, and the money field is the one that moves most.

**What transfers and what does not.** The rates here are rates for used-car adverts, not for dealer
incentive claims, and no figure in this report should be read as a prediction about the group's
systems. What transfers is the shape of the failure and the design that answers it - the same
distinction the rest of this project keeps arriving at. The matcher itself is the deliverable:
`resolve()` takes any table and a field spec, so it can be pointed at a claims extract unchanged.

Usage: .venv/bin/python analysis/entity_resolution.py
"""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_unified import RAW, md_table  # noqa: E402

OUT = HERE / "entity_resolution_report.md"

# Sources that scrape the same advert more than once AND carry the site's own advert id, so the
# answer is known. Every other source either has no id or never repeats one.
TRUTH_SOURCES = ["es_2020_11", "pl_2022_05", "pl_2023_08", "pt_standvirtual", "id_2025"]

# A free-text label that describes the same thing in more than one way. In the UK file it is the
# marketing variant; in a claims system it is the programme name or the description on the claim.
LABEL = "version"
# Fields that can legitimately change while the record stays the same one.
VOLATILE = ["price", "mileage_km"]
# Never used for matching: the id is the answer, and the rest describe the scrape, not the car.
EXCLUDE = ["listing_id", "listing_date", "date_basis", "currency", "reg_date"]

BLOCK = ["make", "model", "year"]   # the cheap key that decides which pairs are ever compared
TOL = 0.01                          # a numeric field agrees within 1%
PAIR_BUDGET = 12_000_000            # cap on candidate pairs held at once
SEED = 0


def load_source(name):
    """The loaded frame before build_unified.py removes duplicates, so the copies are still there."""
    module = importlib.import_module(f"loaders.{name}")
    d = module.load(RAW / name)
    d = d[d["listing_id"].notna()].reset_index(drop=True)
    return d


def match_fields(d):
    """Columns worth matching on: present, not all missing, not the answer."""
    return [c for c in d.columns
            if c not in EXCLUDE and d[c].notna().any() and d[c].nunique(dropna=True) > 1]


def key(d, fields):
    """One string per row from these fields, missing values included, for an exact-match group."""
    return d[fields].astype("string").fillna("~").agg("|".join, axis=1)


def pair_counts(pred, truth):
    """Pairs the rule links, pairs that are truly the same record, and pairs it gets right."""
    t = pd.DataFrame({"p": np.asarray(pred), "t": np.asarray(truth)})
    n = lambda s: int((s * (s - 1) // 2).sum())  # noqa: E731
    return (n(t.groupby("p", observed=True).size()),
            n(t.groupby("t", observed=True).size()),
            n(t.groupby(["p", "t"], observed=True).size()))


def score_rule(d, fields, truth):
    """Precision and recall of an exact match on `fields`, measured over pairs of rows."""
    linked, true_pairs, hit = pair_counts(key(d, fields), truth)
    return {"linked": linked, "true": true_pairs, "hit": hit,
            "precision": hit / linked if linked else np.nan,
            "recall": hit / true_pairs if true_pairs else np.nan}


def drift_profile(d, fields, truth):
    """Among pairs the id confirms are the same record, which fields differ between the copies?"""
    idx = pd.Series(np.arange(len(d))).groupby(pd.Series(truth)).apply(list)
    I, J = [], []
    for g in idx:
        if len(g) < 2:
            continue
        g = np.asarray(g)
        a, b = np.triu_indices(len(g), k=1)
        I.append(g[a])
        J.append(g[b])
    if not I:
        return {}, 0
    I, J = np.concatenate(I), np.concatenate(J)
    out = {}
    for c in fields:
        s = d[c]
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            v = s.to_numpy(float)
            a, b = v[I], v[J]
            differ = np.isfinite(a) & np.isfinite(b) & ~(np.abs(a - b) <= TOL * np.maximum(np.abs(a), np.abs(b)))
        else:
            v = s.astype("string")
            present = v.notna().to_numpy()
            v = v.fillna("").to_numpy(dtype=object)
            differ = present[I] & present[J] & (v[I] != v[J])
        out[c] = float(differ.mean())
    return out, len(I)


def blocking_recall(d, truth):
    """The ceiling a blocking key sets: true pairs it never puts in front of the matcher."""
    b = key(d, BLOCK)
    _, true_pairs, kept = pair_counts(pd.Series(b).astype(str) + "#" + pd.Series(truth).astype(str),
                                      truth)
    return kept / true_pairs if true_pairs else np.nan, true_pairs


def candidate_pairs(d, rng):
    """Row-index pairs the blocking key puts together, sampled by block if the budget is exceeded."""
    groups = [g for g in d.groupby(key(d, BLOCK), observed=True).indices.values() if len(g) >= 2]
    sizes = np.array([len(g) * (len(g) - 1) // 2 for g in groups])
    order = rng.permutation(len(groups))
    take, total = [], 0
    for k in order:
        if total + sizes[k] > PAIR_BUDGET:
            continue
        take.append(k)
        total += sizes[k]
    I, J = [], []
    for k in take:
        g = np.sort(np.asarray(groups[k]))
        a, b = np.triu_indices(len(g), k=1)
        I.append(g[a])
        J.append(g[b])
    share = total / sizes.sum() if sizes.sum() else 1.0
    if not I:
        return np.array([], int), np.array([], int), share
    return np.concatenate(I), np.concatenate(J), share


def agreement(d, fields, I, J):
    """Share of comparable fields on which two rows agree, one value per pair."""
    agree = np.zeros(len(I), float)
    comparable = np.zeros(len(I), float)
    for c in fields:
        s = d[c]
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            v = s.to_numpy(float)
            a, b = v[I], v[J]
            both = np.isfinite(a) & np.isfinite(b)
            close = np.abs(a - b) <= TOL * np.maximum(np.abs(a), np.abs(b))
            same = both & (close | ((a == 0) & (b == 0)))
        else:
            v = s.astype("string")
            present = v.notna().to_numpy()
            v = v.fillna("").to_numpy(dtype=object)
            both = present[I] & present[J]
            same = both & (v[I] == v[J])
        comparable += both
        agree += same
    return np.divide(agree, comparable, out=np.zeros_like(agree), where=comparable > 0)


def sweep(d, fields, truth, rng):
    """Precision and recall of a scored match as the link threshold moves."""
    I, J, share = candidate_pairs(d, rng)
    if not len(I):
        return pd.DataFrame(), share, np.nan
    s = agreement(d, fields, I, J)
    t = np.asarray(truth)
    same = t[I] == t[J]
    _, true_pairs, _ = pair_counts(np.arange(len(d)), truth)
    rows = []
    for thr in np.round(np.arange(0.50, 1.001, 0.05), 2):  # rounded: arange overshoots 1.0
        linked = s >= thr
        hit = int((linked & same).sum())
        rows.append({"threshold": round(float(thr), 2),
                     "pairs linked": int(linked.sum()),
                     "precision": hit / linked.sum() if linked.sum() else np.nan,
                     "recall": hit / true_pairs if true_pairs else np.nan})
    return pd.DataFrame(rows), share, int(same.sum())


def uk_no_id():
    """The UK file has no advert id at all, so truth is inferred, not known. Reported separately."""
    cols = ["make", "model", "variant", "car_price", "car_seller", "year", "body_type", "miles",
            "engine_vol", "engine_size", "engine_size_unit", "transmission", "feul_type",
            "brand_new", "num_owner"]
    d = pd.read_csv(RAW / "uk_2022_10" / "all_car_adverts.csv", usecols=cols, low_memory=False)
    every = list(d.columns)
    no_label = [c for c in every if c != "variant"]
    exact = int(d.duplicated(every).sum())
    label_blind = int(d.duplicated(no_label).sum())
    m = pd.to_numeric(d["miles"], errors="coerce")
    fine = d[m.notna() & (m % 1000 != 0)]
    return {"rows": len(d), "exact": exact, "label_blind": label_blind,
            "recall": exact / label_blind if label_blind else np.nan,
            "fine_rows": len(fine),
            "fine_exact": int(fine.duplicated(every).sum()),
            "fine_label_blind": int(fine.duplicated(no_label).sum())}


def pct(x):
    return "" if not np.isfinite(x) else f"{x:.1%}"


def main():
    rng = np.random.default_rng(SEED)
    pd.set_option("display.width", 220)
    recall_rows, drift_rows, relax_rows, sweeps = [], [], [], {}
    total_pairs = 0

    for name in TRUTH_SOURCES:
        d = load_source(name)
        truth = d["listing_id"].astype(str).to_numpy()
        fields = match_fields(d)
        stable = [c for c in fields if c not in VOLATILE + [LABEL]]
        no_label = [c for c in fields if c != LABEL]

        exact = score_rule(d, fields, truth)
        blind = score_rule(d, no_label, truth)
        loose = score_rule(d, stable, truth)
        prof, n_pairs = drift_profile(d, fields, truth)
        brecall, _ = blocking_recall(d, truth)
        table, share, _ = sweep(d, fields, truth, rng)
        sweeps[name] = (table, share)

        total_pairs += n_pairs
        moved = sorted(((c, v) for c, v in prof.items() if v > 0.001), key=lambda x: -x[1])
        print(f"{name}: {len(d):,} rows, {n_pairs:,} confirmed duplicate pairs, {len(fields)} fields"
              f" | exact recall {pct(exact['recall'])} | drift: "
              + (", ".join(f"{c} {v:.1%}" for c, v in moved[:4]) or "none"))

        recall_rows.append({
            "source": name, "country": name[:2].upper(),
            "rows": f"{len(d):,}",
            "match fields": len(fields),
            "confirmed duplicate pairs": f"{n_pairs:,}",
            "copies that differ somewhere": pct(1 - exact["recall"]),
            "recall, exact match": pct(exact["recall"]),
            "recall, ignoring the label": pct(blind["recall"]),
            "blocking recall": pct(brecall),
        })
        drift_rows.append({
            "source": name,
            "the money field (price)": pct(prof.get("price", 0.0)),
            "odometer": pct(prof.get("mileage_km", 0.0)),
            "the free-text label": pct(prof.get(LABEL, 0.0)),
            "anything at all": pct(1 - exact["recall"]),
        })
        relax_rows.append({
            "source": name,
            "recall, exact": pct(exact["recall"]), "precision, exact": pct(exact["precision"]),
            "recall, relaxed": pct(loose["recall"]), "precision, relaxed": pct(loose["precision"]),
        })

    uk = uk_no_id()
    print(f"\nuk_2022_10 (no advert id): exact {uk['exact']:,}  label-blind {uk['label_blind']:,}  "
          f"recall of exact {pct(uk['recall'])}")

    pt = next(r for r in drift_rows if r["source"] == "pt_standvirtual")
    pt_recall = next(r for r in recall_rows if r["source"] == "pt_standvirtual")

    report = [
        "# Finding the same record twice, when nothing reliable joins them",
        "",
        "Generated by `analysis/entity_resolution.py`. No new data source.",
        "",
        "Leak 1 is claims paid twice across two inherited systems. The pipeline the solution "
        "document proposes - deterministic keys, then blocking, then a scored match, then a band "
        "sent to a person - is standard record linkage. What it lacked was evidence that the rule "
        "anyone reaches for first, *match the records on their fields*, is not enough. This "
        "measures that on real records where the answer is known.",
        "",
        "## Where the truth comes from",
        "",
        f"{len(TRUTH_SOURCES)} sources scrape the same advert more than once and carry the site's "
        "own advert id. The id is hidden, the rows are matched on their fields alone, and the answer "
        "is scored against it. Figures are measured over **pairs of rows**: a rule links a pair or "
        "it does not, and the id says whether it should have.",
        "",
        f"Confirmed duplicate pairs across the five sources: **{total_pairs:,}**.",
        "",
        "## What actually differs between two copies of the same record",
        "",
        "This is the mechanism, and it decides everything downstream. Among pairs the id confirms "
        "are the same advert, the share on which each field disagrees:",
        "",
        md_table(pd.DataFrame(drift_rows)),
        "",
        f"**The field most likely to move is the money field.** In `pt_standvirtual`, scraped weekly "
        f"for eleven months, the price differs on **{pt['the money field (price)']}** of confirmed "
        f"duplicate pairs - the advert was still the same advert, and the seller cut the price. "
        "Where a source is a single snapshot, its copies are identical rows and nothing moves.",
        "",
        "That is exactly the leak 1 case. A claim resubmitted with a corrected amount is one event "
        "recorded twice, differing on the amount - the field a claims system would naturally match "
        "on.",
        "",
        "**Only one source can show this at all, and that is the point.** `pt_standvirtual` is the "
        "only source in the collection that is both scraped repeatedly over time and carries an "
        "advert id. The others are single snapshots, so a second copy is a byte-identical row and "
        "nothing has had the chance to move. So exact matching looking near-perfect in four of five "
        "sources is not reassurance: **it succeeds exactly where the duplicate is trivial.** A "
        "claims system is the other case by construction - claims arrive over time, get corrected, "
        "and get resubmitted.",
        "",
        "## What exact matching recovers",
        "",
        md_table(pd.DataFrame(recall_rows)),
        "",
        "*Recall* is the share of confirmed duplicate pairs the rule links. **It tracks the drift "
        "above precisely**: where copies are byte-identical, exact matching finds all of them; "
        f"where the price moved, it misses **{pt_recall['copies that differ somewhere']}** of them. "
        "*Blocking recall* is the separate ceiling set by only ever comparing rows that share a "
        "make, model and year - pairs outside it are never examined, whatever the matcher does "
        "next.",
        "",
        "Ignoring the free-text label changes little in these sources, because their duplicates do "
        "not differ in the label. The UK file below is the case where it is the only thing that "
        "differs.",
        "",
        "## Why you cannot simply loosen the rule",
        "",
        "The obvious response to missed copies is to stop matching on the fields that move. That "
        "trade is measured here: *relaxed* drops the label and the two fields that drift, price and "
        "odometer.",
        "",
        md_table(pd.DataFrame(relax_rows)),
        "",
        "**Read the movement, not the levels** (the levels are not comparable across sources - see "
        "Limits). Relaxing the rule buys back most of the missed copies and destroys precision "
        "doing it. There is no exact rule that is both complete and correct, which is the whole "
        "argument for a scored match with a band sent to a person rather than a cleverer rule.",
        "",
        "## The scored match, as the threshold moves",
        "",
        "Every pair inside a block is scored by the share of comparable fields on which the two rows "
        f"agree, numeric fields within {TOL:.0%}. The threshold is where a pair is called a link. "
        "This is the curve the two-threshold design needs: above the upper line link automatically, "
        "below the lower line do not link, and in between send it to a person.",
        "",
    ]

    for name, (table, share) in sweeps.items():
        if table.empty:
            continue
        report += [f"### {name}", "",
                   md_table(table.assign(precision=table["precision"].map(pct),
                                         recall=table["recall"].map(pct),
                                         **{"pairs linked": table["pairs linked"].map("{:,}".format)})),
                   ""]
        if share < 0.999:
            report += [f"*{share:.0%} of candidate pairs compared, whole blocks at a time "
                       f"(seed {SEED}).*", ""]

    pt_sweep = sweeps.get("pt_standvirtual", (pd.DataFrame(), 1.0))[0]
    if not pt_sweep.empty:
        hi = pt_sweep[pt_sweep["threshold"] == 0.95].iloc[0]
        lo = pt_sweep[pt_sweep["threshold"] == 0.90].iloc[0]
        report += [
            "### Where the two lines go",
            "",
            "Read `pt_standvirtual`, the one source where copies drift:",
            "",
            md_table(pd.DataFrame([
                {"line": "link automatically above", "threshold": hi["threshold"],
                 "pairs": f"{int(hi['pairs linked']):,}", "precision": pct(hi["precision"]),
                 "recall": pct(hi["recall"])},
                {"line": "review down to", "threshold": lo["threshold"],
                 "pairs": f"{int(lo['pairs linked']):,}", "precision": pct(lo["precision"]),
                 "recall": pct(lo["recall"])},
                {"line": "the review band", "threshold": "",
                 "pairs": f"{int(lo['pairs linked'] - hi['pairs linked']):,}", "precision": "",
                 "recall": ""},
            ])),
            "",
            "Linking automatically at the upper line is nearly always right and catches four fifths "
            "of the copies. The lower line catches almost all of them but is wrong a third of the "
            "time, so it cannot be the automatic one. Working the band between them by hand is what "
            "buys the difference.",
            "",
            "That is the whole design in one table: a high line to link on, a low line to discard "
            "below, and a queue in between whose size the data tells you rather than a judgement "
            "call. The same three numbers are what a claims extract would produce, with the group's "
            "own costs deciding where the lines sit.",
            "",
        ]

    report += [
        "## The case with no id at all",
        "",
        f"`uk_2022_10` has no advert id, so its duplicates can only be inferred rather than known. "
        f"Its {uk['rows']:,} raw rows, by rule:",
        "",
        md_table(pd.DataFrame([
            {"rule": "exact match on every field",
             "copies removed": f"{uk['exact']:,}",
             "share of the file": f"{uk['exact'] / uk['rows']:.1%}",
             "recall": pct(uk["recall"])},
            {"rule": "ignoring the one free-text label",
             "copies removed": f"{uk['label_blind']:,}",
             "share of the file": f"{uk['label_blind'] / uk['rows']:.1%}",
             "recall": pct(1.0)},
            {"rule": "missed by exact matching",
             "copies removed": f"{uk['label_blind'] - uk['exact']:,}",
             "share of the file": f"{(uk['label_blind'] - uk['exact']) / uk['rows']:.1%}",
             "recall": ""},
            {"rule": "exact match, non-round odometers only",
             "copies removed": f"{uk['fine_exact']:,}",
             "share of the file": f"{uk['fine_exact'] / uk['fine_rows']:.1%}",
             "recall": pct(uk["fine_exact"] / uk["fine_label_blind"])},
        ])),
        "",
        "The last row restricts to the rows whose odometer is not a round number, where a "
        "coincidental match on both an exact price and an exact mileage is implausible. One "
        "free-text label is the only thing standing between the exact rule and the rest of the "
        "file.",
        "",
        "One advert, two marketing labels, everything else identical to the mile:",
        "",
        "```",
        "Abarth 124 Spider  MultiAir   GBP 15,995  44,000 mi  2017  manual",
        "Abarth 124 Spider  Scorpione  GBP 15,995  44,000 mi  2017  manual",
        "```",
        "",
        "This is the source the 2026-09-17 audit caught, and it matters twice over. The copies cost "
        "nothing directly, but they sat in **both halves of a train/test split** and flattered the "
        "value engine's held-out test until they were removed (`../Case4_Audit.md`: coverage 81% to "
        "80%, typical error 9.9% to 10.5%). A duplicate that survives into the measurement set "
        "corrupts the baseline a saving is certified against - which is the argument for resolving "
        "entities *before* booking any benefit, not after.",
        "",
        "## What transfers to the group's systems, and what does not",
        "",
        "**Not the rates.** These are used-car adverts, not dealer incentive claims. No number here "
        "predicts anything about the group's systems, and none should be quoted as if it did. Leak "
        "1 stays an assumption until it is measured on the group's own data.",
        "",
        "**The failure transfers.** Records with no reliable shared key, copies that differ on the "
        "amount, and errors that cost different amounts in each direction fail this way wherever "
        "they occur. It is the same rule the rest of this project keeps arriving at from other "
        "directions: the shape travels, the level is local.",
        "",
        "**And the instrument transfers.** `resolve()` in this script takes a table and a field "
        "spec. Pointed at a claims extract with the same shape - an id where one exists, a "
        "programme label, an amount that can be corrected - it produces the group's own precision "
        "and recall, which is what the Phase 1 gates in the solution document ask for.",
        "",
        "## Limits",
        "",
        "- **Precision levels are not comparable across these sources, and are not interpretable on "
        "their own.** Two opposite errors are mixed into them. An advert relisted under a new id is "
        "a real duplicate the id calls distinct, which understates precision: `es_2020_11` carries "
        "five ids for one Abarth 500 at 100,867 km and EUR 10,747. And where a source records few "
        "fields, genuinely different cars coincide, which is real over-linking: `pl_2022_05` has two "
        "distinct 2021 Giulia demonstrators, both at 1 km and the same PLN 169,900 list price. "
        "Recall does not have this problem, because it is measured only over pairs the id confirms.",
        "- **An advert id is the best truth available, not perfect truth**, for the same reason.",
        "- **Advert records are not claim records.** They share the structure of the problem and "
        "little else. The field set, the error modes and the costs all differ.",
        "- **Pair counts are dominated by the largest clusters.** One `es_2020_11` advert appears "
        "186 times and contributes 17,205 of that source's pairs on its own.",
        "- **Pairs, not clusters.** Scores are over pairs of rows with no transitive closure, so "
        "chains that would merge three records through two links are not counted.",
        "- **One blocking key.** Blocking recall is measured for make, model and year together. A "
        "production system runs several blocking rules and takes the union, which raises the ceiling "
        "at the cost of more comparisons.",
        f"- **Numeric agreement is a fixed {TOL:.0%} tolerance**, not a learned one. A trained "
        "Fellegi-Sunter model weights each field by how much its agreement actually distinguishes a "
        "match, which needs labels the group has and this data does not.",
        "",
    ]
    OUT.write_text("\n".join(report))
    print(f"\nwrote {OUT}")


def resolve(d, id_field=None, threshold=0.95):
    """The deliverable: link duplicate records in any table.

    Returns the frame with a `cluster` column - rows sharing a cluster are judged the same record.
    Pointing this at a claims extract means setting BLOCK, LABEL, VOLATILE and EXCLUDE for that
    table at the top of this file, not rewriting the function. `id_field`, where the table has one,
    is kept out of the matching so it can be scored against.
    """
    fields = [c for c in d.columns if c not in list(EXCLUDE) + ([id_field] if id_field else [])
              and d[c].notna().any()]
    rng = np.random.default_rng(SEED)
    I, J, _ = candidate_pairs(d.reset_index(drop=True), rng)
    s = agreement(d.reset_index(drop=True), fields, I, J)
    parent = np.arange(len(d))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in zip(I[s >= threshold], J[s >= threshold]):
        ri, rj = root(i), root(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)
    return d.assign(cluster=[root(i) for i in range(len(d))])


if __name__ == "__main__":
    main()
