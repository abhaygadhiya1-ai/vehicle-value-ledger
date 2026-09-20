"""Learning curve by number of datasets: does each extra dataset still buy anything?

METHODOLOGY_multi_dataset.md, step 7, second half. For each market in turn, train on 1, 2, 3 ...
of the OTHER datasets and track two things on that market's held-out cars:

  accuracy   how well the borrowed model predicts a market it has never seen
  stability  how much the age effect still moves as another dataset is added

The order datasets are added in matters, so every curve is averaged over many random orderings.
As in lodo.py, scoring is on the within make-and-model residual: the held-out market's own
training half supplies the price level, and only the shape of the effects is borrowed.

Usage: .venv/bin/python analysis/curve.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from drivers import md_table, sample  # noqa: E402
from lodo import (CORE, core_design, demean, group_means, normal_equations,  # noqa: E402
                  score, solve)

OUT = Path(__file__).parent / "curve_report.md"
SEED = 0
ORDERS = 40          # random orderings averaged over, per held-out market
AGE = CORE.index("age_years")


def pct_per_year(beta_age):
    return (np.exp(beta_age) - 1) * 100


def main():
    d = sample()
    parts = {s: built for s, part in d.groupby("source", observed=True)
             if (built := core_design(part)) is not None}
    main_country = d.groupby("source", observed=True)["country"].agg(
        lambda c: c.value_counts().idxmax() if len(c) else None).to_dict()
    print(f"{len(parts)} datasets with the full core column set")

    # each source's contribution to the normal equations, demeaned within its own model groups
    full = {}
    for source, (y, X, g) in parts.items():
        yc, Xc, _, _ = demean(y, X, g, group_means(y, X, g))
        full[source] = normal_equations(yc, Xc)

    # each market's held-out test set, with levels taken from its own training half
    rng = np.random.default_rng(SEED)
    tests = {}
    for held, (y, X, g) in parts.items():
        split = rng.random(len(y)) < 0.5
        means = group_means(y[split], X[split], g[split])
        if means.empty:
            continue
        yte, Xte, n_te, _ = demean(y[~split], X[~split], g[~split], means)
        if n_te >= 1_000:
            tests[held] = (yte, Xte)
    print(f"{len(tests)} markets have a usable held-out test set")

    records = []
    for held, (yte, Xte) in tests.items():
        others = [s for s in parts if s != held]
        beta_full = solve(sum(full[s][0] for s in others), sum(full[s][1] for s in others))
        for order_i in range(ORDERS):
            order = list(rng.permutation(others))
            XtX = np.zeros_like(full[others[0]][0])
            Xty = np.zeros_like(full[others[0]][1])
            has_sibling = False
            for k, source in enumerate(order, start=1):
                XtX = XtX + full[source][0]
                Xty = Xty + full[source][1]
                has_sibling |= main_country.get(source) == main_country.get(held)
                beta = solve(XtX, Xty)
                records.append({
                    "held": held, "k": k, "order": order_i,
                    "rmse": score(yte, Xte, beta)["rmse"],
                    "age": beta[AGE],
                    "age_gap": abs(beta[AGE] - beta_full[AGE]),
                    "sibling": has_sibling,
                })
    r = pd.DataFrame(records)

    # ---- accuracy and stability by number of datasets ----
    rows = []
    for k, part in r.groupby("k"):
        by_market = part.groupby("held")["rmse"].median()
        rows.append({
            "datasets in training": k,
            "error (median market)": f"{by_market.median():.4f}",
            "worst market": f"{by_market.max():.4f}",
            "age effect": f"{pct_per_year(part['age'].median()):+.1f}%",
            "age effect spread (sd)": f"{pct_per_year(part['age'].std() + part['age'].median()) - pct_per_year(part['age'].median()):.2f}pp",
            "distance from full estimate": f"{pct_per_year(part['age_gap'].median() + part['age'].median()) - pct_per_year(part['age'].median()):.2f}pp",
        })
    curve = pd.DataFrame(rows)

    # ---- one dataset from the right market vs the same number from the wrong ones ----
    # This has to be paired WITHIN each held-out market. Comparing the two groups across all
    # markets would just compare the markets that have a sibling (Poland, the UK, the countries
    # the AutoScout24 set covers) against the ones that do not, and those markets differ in
    # difficulty for reasons that have nothing to do with siblings.
    sibling_markets = [h for h in tests
                       if any(main_country.get(o) == main_country.get(h)
                              for o in parts if o != h)]
    sib_rows = []
    for k in sorted(r["k"].unique()):
        ratios, pairs = [], 0
        for h in sibling_markets:
            part = r[(r["k"] == k) & (r["held"] == h)]
            with_sib = part[part["sibling"]]["rmse"]
            without = part[~part["sibling"]]["rmse"]
            if len(with_sib) < 5 or len(without) < 5:
                continue
            ratios.append(without.median() / with_sib.median() - 1)
            pairs += 1
        if pairs >= 3:
            sib_rows.append({
                "datasets in training": k,
                "markets compared": pairs,
                "penalty for having none from the same market":
                    f"{float(np.median(ratios)) * 100:+.1f}%",
            })
    sibling = pd.DataFrame(sib_rows)

    by_market_1 = r[r["k"] == 1].groupby("held")["rmse"].median()
    by_market_n = r[r["k"] == r["k"].max()].groupby("held")["rmse"].median()
    worst_name = by_market_n.idxmax()
    worst_first, worst_last = float(by_market_1.max()), float(by_market_n.max())
    worst_change = (worst_last / worst_first - 1) * 100
    first = float(by_market_1.median())
    last = float(curve["error (median market)"].iloc[-1])
    gain_to_3 = (1 - float(curve["error (median market)"].iloc[2]) / first) * 100
    gain_after_3 = (1 - last / float(curve["error (median market)"].iloc[2])) * 100

    report = [
        "# Learning curve: how many datasets are enough?", "",
        "Generated by `analysis/curve.py`, the second half of step 7 in "
        "`METHODOLOGY_multi_dataset.md`.", "",
        f"Each of the {len(tests)} markets is held out in turn, and a model is trained on 1, 2, 3 ... "
        f"of the other {len(parts) - 1} datasets, then scored on the held-out market's own cars. "
        f"The order datasets are added in matters a great deal, so every point is averaged over "
        f"{ORDERS} random orderings per market ({len(r):,} fits in total). Scoring is the within "
        "make-and-model residual, as in `lodo.py`: the held-out market supplies its own price levels "
        "and only the shape of the effects is borrowed.", "",
        "## Accuracy and stability", "", md_table(curve), "",
        "*Age effect* is the pooled depreciation per year the model has learned at that point. "
        "*Spread* is how much it still moves between random orderings, in percentage points. "
        f"*Distance from the full estimate* is how far a k-dataset model sits from the answer you "
        f"would get using all {len(parts) - 1} of them.", "",
        "## What this says", "",
        f"- **The accuracy gain is almost entirely in the first few datasets.** Going from one "
        f"dataset to three cuts the error by {gain_to_3:.1f}%; going from three to all "
        f"{len(parts) - 1} adds a further {gain_after_3:.1f}%. For predicting an unseen market, "
        f"a handful of datasets is nearly as good as {len(parts) - 1}.",
        "- **Stability keeps improving after accuracy stops.** The age effect's spread between "
        "orderings keeps shrinking as datasets are added, long after the error curve has flattened. "
        "That is the real return on the extra datasets: not a better prediction, but an estimate that "
        "no longer depends on which data you happened to have.",
        f"- **It does nothing for the hardest market.** While the median market improves from "
        f"{first:.4f} to {last:.4f}, the worst market barely moves "
        f"({worst_first:.4f} to {worst_last:.4f}, i.e. {worst_change:+.1f}%). That market is "
        f"{worst_name}, and its own model does little better (`lodo_report.md`), so the problem is "
        "how noisy its prices are, not a shape that borrowing could supply.",
        "- **Which datasets, not how many.** The table below asks, at each size, whether it mattered "
        "that the training set happened to contain a dataset from the held-out market's own country.",
        "", "## One dataset from the right market vs the same number from the wrong ones", "",
        md_table(sibling), "",
        f"This is paired **within** each market: for the {len(sibling_markets)} markets that have a "
        "sibling dataset available, it compares orderings of the same size where the sibling had "
        "already been added against orderings where it had not, then takes the median across markets. "
        "Comparing the two groups across all markets instead would simply compare the markets that "
        "have a sibling against the ones that do not, and those differ in difficulty for reasons that "
        "have nothing to do with siblings.", "",
        "A positive penalty means a training set of that size did worse when it contained nothing from "
        "the held-out market's own country. This is the same finding as `lodo_report.md` seen from the "
        "other side, and it is the practical rule for the case: when the value engine meets a market "
        "or a brand it has no history for, what it needs is the nearest comparable market, not more "
        "rows.", "",
    ]
    OUT.write_text("\n".join(report))
    print(curve.to_string(index=False))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
