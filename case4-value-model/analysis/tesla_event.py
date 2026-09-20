"""Did Tesla's January 2023 price cuts move used Tesla prices? A difference-in-differences.

Washington State records the sale price and sale date of every electric vehicle title transfer,
which gives realised transaction prices rather than advertised ones. Tesla cut US new-car prices
on 13 January 2023 (6-20% depending on trim). The question is whether used Tesla values fell
beyond what the rest of the used-EV market was doing anyway.

  treated  used Tesla sales
  control  used non-Tesla electric vehicle sales, same state, same months
  outcome  log sale price, with a fixed effect per model and model year, so a 2019 Model 3 is
           compared with a 2019 Model 3, plus age and mileage controls

Reported as an event study: one coefficient per month relative to December 2022. The months
BEFORE the cut are the point of the exercise. If they are not flat, the parallel-trends
assumption fails and no difference-in-differences number from this data is causal.

Usage: .venv/bin/python analysis/tesla_event.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import md_table  # noqa: E402

HERE = Path(__file__).parent
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
OUT = HERE / "tesla_event_report.md"

CUT = pd.Timestamp("2023-01-13")     # Tesla's US price cut
REFERENCE = "2022-12"                # the last full month before the cut
START, END = "2022-01-01", "2023-12-31"
PRICE_MIN, PRICE_MAX = 2_000, 150_000


def load():
    d = pd.read_parquet(LISTINGS, columns=["source", "make", "model", "year", "age_years",
                                           "mileage_km", "fuel", "listing_date", "price", "is_new"])
    d = d[(d["source"] == "us_wa_ev_sales") & (d["is_new"] == False)]
    d = d[d["listing_date"].between(START, END)]
    d = d[d["price"].between(PRICE_MIN, PRICE_MAX)]
    d = d[d["mileage_km"].between(100, 400_000) & d["age_years"].between(0, 15)]
    d = d.copy()
    d["month"] = d["listing_date"].dt.to_period("M").astype(str)
    d["tesla"] = d["make"].eq("tesla")
    d["cell"] = d["make"].astype(str) + "|" + d["model"].astype(str) + "|" + d["year"].astype(str)
    return d


def absorb(y, X, groups, min_group=5):
    g = pd.factorize(groups)[0]
    counts = np.bincount(g)
    big = counts[g] >= min_group
    y, X, g = y[big], X[big], pd.factorize(g[big])[0]
    n = np.bincount(g)
    ybar = np.bincount(g, weights=y) / n
    Xbar = np.stack([np.bincount(g, weights=X[:, j]) / n for j in range(X.shape[1])], axis=1)
    return y - ybar[g], X - Xbar[g], int(g.max() + 1), big


def cluster_ols(y, X, clusters, n_absorbed):
    """OLS with cluster-robust standard errors.

    Clustering by month would be wrong here: the specification has a dummy for every month and
    every month-by-Tesla combination, so residuals sum to about zero inside each month and the
    sandwich collapses, giving errors seven times too small. Clustering is done by make-model-year
    cell instead, which is where correlated shocks actually live.
    """
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    u = y - X @ beta
    meat = np.zeros((X.shape[1], X.shape[1]))
    codes = pd.factorize(clusters)[0]
    for c in np.unique(codes):
        Xg, ug = X[codes == c], u[codes == c]
        s = Xg.T @ ug
        meat += np.outer(s, s)
    g = len(np.unique(codes))
    n, k = X.shape
    scale = (g / (g - 1)) * ((n - 1) / (n - k - n_absorbed))
    cov = XtX_inv @ meat @ XtX_inv * scale
    return beta, np.sqrt(np.clip(np.diag(cov), 0, None))


def event_study(d, label):
    months = sorted(d["month"].unique())
    others = [m for m in months if m != REFERENCE]
    cols, names = [], []
    for m in others:                                   # common month effects
        cols.append((d["month"] == m).to_numpy(float)); names.append(f"month_{m}")
    for m in others:                                   # Tesla-specific month effects
        cols.append(((d["month"] == m) & d["tesla"]).to_numpy(float)); names.append(f"tesla_{m}")
    cols.append(d["age_years"].to_numpy(float)); names.append("age_years")
    cols.append(np.log(d["mileage_km"].to_numpy(float))); names.append("log_mileage")
    X = np.stack(cols, axis=1)
    y = np.log(d["price"].to_numpy(float))
    yc, Xc, n_cells, kept = absorb(y, X, d["cell"])
    beta, se = cluster_ols(yc, Xc, d["cell"].to_numpy()[kept], n_cells)
    out = {n: (b, s) for n, b, s in zip(names, beta, se)}
    return out, int(kept.sum()), n_cells, months


def pct(b):
    return (np.exp(b) - 1) * 100


def main():
    d = load()
    print(f"sample: {len(d):,} used EV sales in WA, {START[:7]} to {END[:7]}")
    print(f"  tesla {int(d['tesla'].sum()):,} | other EV {int((~d['tesla']).sum()):,}")

    coef, n_used, n_cells, months = event_study(d, "all")
    print(f"  fitted on {n_used:,} rows, {n_cells:,} model-year cells")

    rows = []
    for m in months:
        if m == REFERENCE:
            rows.append({"month": m + " (reference)", "Tesla vs other EVs": "0.0%",
                         "95% range": "-", "period": "before the cut"})
            continue
        b, s = coef[f"tesla_{m}"]
        rows.append({
            "month": m,
            "Tesla vs other EVs": f"{pct(b):+.1f}%",
            "95% range": f"{pct(b - 1.96 * s):+.1f}% to {pct(b + 1.96 * s):+.1f}%",
            "period": "before the cut" if m < "2023-01" else "after the cut",
        })
    table = pd.DataFrame(rows)

    # The pre-period is not a smooth trend: it is flat through August 2022 and then breaks
    # downward from September, four months before the cut. A straight line through the whole
    # pre-period would average those two regimes together and mislead, so the periods are
    # compared as plateaus instead.
    mean_of = lambda ms: float(np.mean([coef[f"tesla_{m}"][0] for m in ms if m != REFERENCE]))
    plateau_2022 = [m for m in months if m <= "2022-08"]
    slide = [m for m in months if "2022-09" <= m <= "2022-12"]
    first3 = [m for m in months if "2023-01" <= m <= "2023-03"]
    plateau_2023 = [m for m in months if m >= "2023-04"]

    pre_level = mean_of(plateau_2022)
    post_level = mean_of(plateau_2023)
    naive = mean_of(first3)
    before_cut_fall = pct(0) - pct(pre_level)          # plateau -> December 2022 reference
    after_cut_fall = pct(post_level) - pct(0)          # reference -> 2023 plateau
    total_fall = pct(post_level) - pct(pre_level)
    share_before = abs(before_cut_fall) / (abs(before_cut_fall) + abs(after_cut_fall)) * 100
    med = d.groupby(["month", "tesla"])["price"].median().unstack()
    tesla_sep, tesla_dec = med.loc["2022-09", True], med.loc["2022-12", True]
    other_sep, other_dec = med.loc["2022-09", False], med.loc["2022-12", False]

    report = [
        "# Did Tesla's January 2023 price cut move used Tesla values?", "",
        "Generated by `analysis/tesla_event.py`.", "",
        "**Short answer: the data cannot separate the cut from a fall that was already happening.** "
        "Used Tesla prices in Washington State were dropping fast for months before 13 January 2023, "
        "while the rest of the used-EV market was flat. Any before-and-after number from this event "
        "therefore mostly measures the pre-existing slide, not the cut.", "",
        "## Setup", "",
        f"- **Data:** Washington State title-transfer records, which carry a realised sale price and "
        f"sale date. {len(d):,} used electric-vehicle sales between {START[:7]} and {END[:7]} "
        f"({int(d['tesla'].sum()):,} Tesla, {int((~d['tesla']).sum()):,} other EV).",
        "- **Treated:** used Tesla sales. **Control:** used non-Tesla EV sales in the same state and "
        "months.",
        f"- **Event:** Tesla cut US new-car prices on 13 January 2023, by roughly 6-20% depending on "
        "trim ([CNBC](https://www.cnbc.com/2023/01/13/tesla-cuts-prices-in-us-and-europe-to-stoke-sales.html), "
        "[CNN](https://www.cnn.com/2023/01/13/business/tesla-price-cuts/index.html)).",
        f"- **Model:** log sale price, with a fixed effect per make, model and model year "
        f"({n_cells:,} cells), plus age and mileage. One coefficient per month for Tesla relative to "
        f"December 2022. Standard errors clustered by make-model-year cell. Fitted on "
        f"{n_used:,} sales.", "",
        "## Month-by-month, Tesla against other used EVs", "", md_table(table), "",
        "## The repricing started four months before the cut", "",
        "Read the table as three regimes rather than a trend:", "",
        f"| Period | Tesla vs other used EVs | What it means |",
        "|---|---|---|",
        f"| Jan-Aug 2022 | about **{pct(pre_level):+.1f}%** | A stable premium. Used Teslas held their "
        "value well above the rest of the used-EV market. |",
        f"| Sep-Dec 2022 | falls to 0% | **The slide starts here, four months before the cut.** By the "
        "December reference month the premium has gone. |",
        f"| Jan-Mar 2023 | **{pct(naive):+.1f}%** | The three months after the cut. |",
        f"| Apr-Dec 2023 | about **{pct(post_level):+.1f}%**, flat | It stops falling and settles. |", "",
        f"- **The premium fell {abs(before_cut_fall):.1f} points before the cut and a further "
        f"{abs(after_cut_fall):.1f} points after it.** About **{share_before:.0f}%** of the total "
        "repricing had already happened by the time of the January US list-price cut.",
        "- **But not before every Tesla price move.** Tesla cut Model 3 and Model Y prices in China "
        "by up to 9% on 24 October 2022 "
        "([CNN](https://www.cnn.com/2022/10/24/investing/tesla-china-price-cuts/index.html)), and "
        "offered US buyers $3,750 off December deliveries from 1 December "
        "([TechCrunch](https://techcrunch.com/2022/12/01/tesla-offers-3750-discount-for-model-3-model-y-deliveries-in-december/embed/)), "
        "raised to $7,500 on 22 December "
        "([Bloomberg](https://www.bloomberg.com/news/articles/2022-12-22/tesla-discount-7-500-to-take-delivery-of-model-3-or-model-y)). "
        "Most of the pre-cut fall is in November and December, alongside those. Only the start of "
        "the slide, in September, comes before any Tesla price action we could find.",
        f"- **Naive estimate:** the first three months after the cut sit {pct(naive):+.1f}% below "
        "December 2022. That is the number a careless analysis would report as the effect of the cut, "
        "and it is measuring the tail of a slide that began in September 2022.",
        "- **This is a parallel-trends failure, not a small one.** Through the autumn of 2022 the "
        f"median non-Tesla used EV in this data barely moved (${other_sep:,.0f} in September, "
        f"${other_dec:,.0f} in December) while the median used Tesla fell from ${tesla_sep:,.0f} to "
        f"${tesla_dec:,.0f}. The two groups were "
        "already diverging before the treatment, so the assumption that makes "
        "difference-in-differences causal does not hold, and no number in this table should be "
        "presented as the causal effect of the price cut.", "",
        "## What can honestly be said", "",
        "1. **Used Tesla values fell hard, and mostly before the US list-price cut.** Between "
        f"September and December 2022 the median used Tesla in this data went from ${tesla_sep:,.0f} "
        f"to ${tesla_dec:,.0f} while the median non-Tesla used EV barely moved.",
        "2. **The January cut is not separable from that slide.** Two things make a clean estimate "
        "impossible: the steep pre-trend, and the fact that January was the *first of a series* - "
        "Tesla cut again in April 2023 and repeatedly after that, so the post period is not a single "
        "treatment.",
        "3. **The control group is not clean either.** The whole used-EV market softened through "
        "2023, so non-Tesla EVs are a treated control, which biases the measured gap toward zero.",
        "4. **For the case, the useful finding is the timing, not the size.** Residual value moved "
        "months ahead of the headline list-price cut - partly on the manufacturer's own discounts "
        "and its cuts in another market, which a list-price feed does not show. A residual-risk "
        "model that watches only official list prices is already too late; it has to see "
        "discounts, other markets' prices and the used market itself.", "",
        "## Limits", "",
        "- Washington State only, electric vehicles only, so this is not a general used-car result.",
        "- Title-transfer prices include private sales and are self-reported; the source contains "
        "some clearly wrong values (sale dates written into the price field), so prices outside "
        f"${PRICE_MIN:,}-${PRICE_MAX:,} are excluded.",
        "- Sales are dated by title transfer, which can lag the handshake by days or weeks. That "
        "blurs a sharp event boundary but does not create a months-long pre-trend.", "",
    ]
    OUT.write_text("\n".join(report))
    print(f"\n2022 plateau {pct(pre_level):+.1f}% | Jan-Mar 2023 {pct(naive):+.1f}% | "
          f"2023 plateau {pct(post_level):+.1f}% | {share_before:.0f}% of the fall came first")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
