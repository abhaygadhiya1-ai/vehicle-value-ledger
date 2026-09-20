"""How much does the used-car price *level* move, and how does that compare with curve error?

Every other analysis here measures the shape of depreciation: how fast a car loses value as it
ages. This one measures the other half of a residual value, the part no car-level model can see -
what the whole used market is worth on the day the car comes back.

The question it answers is the one a lease book actually faces. A three-year lease fixes a
contractual residual today and finds out in 36 months whether it was right. Two things can make it
wrong: the curve (how fast this car aged) and the level (what the market was worth when it
returned). This script sizes both in the same unit - points of the original list price - so they
can be compared.

Source: `data/reference/price_indices.parquet`, built by `build_reference.py`. No new data.

Method note. Coverage is very uneven: France and Lithuania run from 1996, most markets only from
2014-2016. Pooling every overlapping window across all markets would let those two supply a third
of the sample. So the headline panel uses a **common window with every market weighted equally**,
and the long histories are reported separately as a robustness check.

Usage: .venv/bin/python analysis/level_risk.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import md_table  # noqa: E402

HERE = Path(__file__).parent
INDICES = HERE.parent / "data" / "reference" / "price_indices.parquet"
OUT = HERE / "level_risk_report.md"
SERIES = HERE / "level_risk_markets.csv"

EUROSTAT = "Eurostat HICP, second-hand motor cars (CP07112)"

# EU/EEA national markets. Aggregates (EA, EU27_2020, ...) and candidate countries are excluded:
# an aggregate would double-count its members.
EUROPE = ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU",
          "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"]

# The merged group's largest European markets, among those with full common-window coverage.
CORE = ["FR", "IT", "DE", "ES", "PL", "NL", "PT"]

COMMON_START, COMMON_END = "2016-12", "2025-12"
HORIZONS = (12, 36)
# Shorter horizons answer a different question: how far can the level drift between two reviews?
# Stellantis re-estimates expected residual values quarterly (20-F FY2025), so 3 months is the
# window in which a move goes unseen.
REVIEW_HORIZONS = (1, 3, 6, 12)

# Measured inputs from the other reports, quoted here so the comparison is traceable.
# Measured inputs from the other analyses, read from what they wrote rather than copied, so a re-run
# there cannot leave these behind. drivers.py and latvia_time.py must run first.
from drivers import effect  # noqa: E402
from scipy.stats import t as student_t  # noqa: E402
_AGE = effect("age_years")
SHAPE_POOLED = float(np.expm1(_AGE["estimate"]))                                 # pooled rate
SHAPE_ACROSS = (float(np.expm1(_AGE["pi_lo"])), float(np.expm1(_AGE["pi_hi"])))  # 95% prediction interval
LEASE_YEARS = 3
LATVIA_MONTHLY = HERE / "latvia_monthly.csv"   # latvia_time.py: the monthly refits
SUMMARY = HERE / "level_risk_summary.csv"      # read by what_matters.py
_RATES = pd.read_csv(LATVIA_MONTHLY)["depreciation_pct_per_year"].dropna() / 100
SHAPE_STABLE = (float(_RATES.min()), float(_RATES.max()))                     # range of the refits
# Student's t at the prediction interval's degrees of freedom (datasets less 2), the one
# drivers.py builds its 95% interval on. Its 90% point narrows that to an 80% interval,
# matching a p10-p90 band.
_DF = int(_AGE["datasets"]) - 2
T975_DF15, T90_DF15 = float(_AGE["t975"]), float(student_t.ppf(0.90, _DF))


def load():
    """One contiguous monthly series per geo and series name; gappy series are dropped."""
    d = pd.read_parquet(INDICES)
    out = {}
    for (series, geo), g in d.groupby(["series", "geo"], observed=True):
        s = g.sort_values("month").set_index("month")["index_value"].astype(float)
        s = s[~s.index.duplicated()]
        want = pd.period_range(s.index.min(), s.index.max(), freq="M").astype(str)
        if len(want) != len(s) or s.isna().any():
            continue
        out[(series, geo)] = s
    return out


def moves(s, k):
    """Percentage change over k months, as a percentage."""
    return ((s / s.shift(k) - 1) * 100).dropna()


def drawdown(s):
    """Worst peak-to-trough fall, as a percentage."""
    return float((s / s.cummax() - 1).min() * 100)


def stats(s):
    row = {"months": len(s), "from": s.index[0], "to": s.index[-1]}
    for k in HORIZONS:
        m = moves(s, k)
        row[f"worst {k}m"] = f"{m.min():+.1f}%" if len(m) else ""
        row[f"median {k}m"] = f"{m.median():+.1f}%" if len(m) else ""
        row[f"best {k}m"] = f"{m.max():+.1f}%" if len(m) else ""
    row["worst drawdown"] = f"{drawdown(s):+.1f}%"
    return row


def pooled(series_by_geo, geos, k):
    """Every market contributes the same number of windows, so none dominates."""
    return np.concatenate([moves(series_by_geo[g], k).to_numpy() for g in geos])


def pct_line(a, label):
    p = {q: np.percentile(a, q) for q in (1, 5, 10, 50, 90, 95, 99)}
    return {"set": label, "markets": "", "windows": f"{len(a):,}",
            **{f"p{q}": f"{v:+.1f}%" for q, v in p.items()},
            "worst": f"{a.min():+.1f}%", "best": f"{a.max():+.1f}%"}


def retained(rate, years=LEASE_YEARS):
    return (1 + rate) ** years


def main():
    raw = load()
    euro = {g: s for (series, g), s in raw.items() if series == EUROSTAT and g in EUROPE}

    common = {}
    for g, s in euro.items():
        w = s[(s.index >= COMMON_START) & (s.index <= COMMON_END)]
        if len(w) == len(pd.period_range(COMMON_START, COMMON_END, freq="M")):
            common[g] = w
    core = [g for g in CORE if g in common]
    dropped = sorted(set(euro) - set(common))

    per_market = pd.DataFrame(
        [{"market": g, **stats(common[g])} for g in sorted(common)]
    ).drop(columns=["months", "from", "to"])
    per_market.to_csv(SERIES, index=False)

    pool_all = {k: pooled(common, sorted(common), k) for k in HORIZONS}
    pool_core = {k: pooled(common, core, k) for k in HORIZONS}

    pooled_tbl = []
    for k in HORIZONS:
        for label, geos, arr in ((f"all {len(common)} EU markets", common, pool_all[k]),
                                 (f"the group's {len(core)} largest", core, pool_core[k])):
            row = pct_line(arr, f"{k}-month moves, {label}")
            row["markets"] = str(len(geos))
            pooled_tbl.append(row)

    review_tbl = []
    for k in REVIEW_HORIZONS:
        a = pooled(common, sorted(common), k)
        review_tbl.append({"months between reviews": k, "windows": f"{len(a):,}",
                           "p5": f"{np.percentile(a, 5):+.1f}%",
                           "median fall (p50 of falls)":
                               f"{np.median(a[a < 0]):+.1f}%" if (a < 0).any() else "",
                           "worst": f"{a.min():+.1f}%",
                           "share of windows moving more than 2%":
                               f"{(np.abs(a) > 2).mean() * 100:.0f}%"})

    long_rows = []
    for (series, g), s in sorted(raw.items(), key=lambda kv: -len(kv[1])):
        if len(s) < 200:
            continue
        long_rows.append({"series": series.split(",")[0], "geo": g, **stats(s)})

    # Shape against level, both in points of the original list price at the lease's end.
    base = retained(SHAPE_POOLED)
    shape_known = abs(retained(SHAPE_STABLE[0]) - retained(SHAPE_STABLE[1])) * 100
    shape_unknown = abs(retained(SHAPE_ACROSS[0]) - retained(SHAPE_ACROSS[1])) * 100
    lo, hi = np.percentile(pool_all[36], 10) / 100, np.percentile(pool_all[36], 90) / 100
    level_band = base * (hi - lo) * 100
    worst = pool_all[36].min() / 100

    # The same two curve errors at p10-p90, so they sit like for like beside the level band.
    rates = pd.read_csv(LATVIA_MONTHLY)["depreciation_pct_per_year"].to_numpy() / 100
    stable80 = (np.percentile(rates, 10), np.percentile(rates, 90))
    known80 = abs(retained(stable80[0]) - retained(stable80[1])) * 100
    mid = np.mean(np.log1p(SHAPE_ACROSS))
    half80 = np.diff(np.log1p(SHAPE_ACROSS))[0] / 2 * T90_DF15 / T975_DF15
    across80 = (np.expm1(mid - half80), np.expm1(mid + half80))
    unknown80 = abs(retained(across80[0]) - retained(across80[1])) * 100

    # The same at one year, for the part of a buy-back book that comes back within twelve months.
    base1 = retained(SHAPE_POOLED, 1)
    known80_1y = abs(retained(stable80[0], 1) - retained(stable80[1], 1)) * 100
    unknown80_1y = abs(retained(across80[0], 1) - retained(across80[1], 1)) * 100
    lo12, hi12 = np.percentile(pool_all[12], 10) / 100, np.percentile(pool_all[12], 90) / 100
    level_band_1y = base1 * (hi12 - lo12) * 100
    one_year = pd.DataFrame([
        {"source of error": "**Curve**, in a market with its own data, p10 to p90",
         "points of list price at 1y": f"{known80_1y:.1f}"},
        {"source of error": "**Curve**, in a market with no history, 80% prediction interval",
         "points of list price at 1y": f"{unknown80_1y:.1f}"},
        {"source of error": "**Level**, p10 to p90 of 12-month moves",
         "points of list price at 1y": f"{level_band_1y:.1f}"},
    ])

    compare = pd.DataFrame([
        {"source of error": "**Curve**, in a market with its own data",
         "measured range": f"{SHAPE_STABLE[0]*100:.1f}% to {SHAPE_STABLE[1]*100:.1f}% a year",
         "where from": f"`latvia_time_report.md`, {len(_RATES)} monthly refits",
         f"points of list price at {LEASE_YEARS}y": f"{shape_known:.1f}"},
        {"source of error": "**Curve**, in a market with no history of its own",
         "measured range": f"{SHAPE_ACROSS[0]*100:.1f}% to {SHAPE_ACROSS[1]*100:.1f}% a year",
         "where from": "`drivers_report.md`, 95% prediction interval",
         f"points of list price at {LEASE_YEARS}y": f"{shape_unknown:.1f}"},
        {"source of error": "**Curve**, in a market with its own data, p10 to p90",
         "measured range": f"{stable80[0]*100:.1f}% to {stable80[1]*100:.1f}% a year",
         "where from": f"`latvia_time_report.md`, {len(_RATES)} monthly refits",
         f"points of list price at {LEASE_YEARS}y": f"{known80:.1f}"},
        {"source of error": "**Curve**, in a market with no history, 80% prediction interval",
         "measured range": f"{across80[0]*100:.1f}% to {across80[1]*100:.1f}% a year",
         "where from": "`drivers_report.md` interval, narrowed from 95% to 80%",
         f"points of list price at {LEASE_YEARS}y": f"{unknown80:.1f}"},
        {"source of error": "**Level**, p10 to p90",
         "measured range": f"{lo*100:+.1f}% to {hi*100:+.1f}% over {LEASE_YEARS} years",
         "where from": f"this report, {len(common)} EU markets",
         f"points of list price at {LEASE_YEARS}y": f"{level_band:.1f}"},
        {"source of error": "**Level**, worst window observed",
         "measured range": f"{worst*100:+.1f}% over {LEASE_YEARS} years",
         "where from": "this report",
         f"points of list price at {LEASE_YEARS}y": f"{base * abs(worst) * 100:.1f}"},
    ])

    pd.DataFrame([{"name": "level_points", "value": level_band},
                  {"name": "retained_3y_pooled", "value": base * 100}]).to_csv(SUMMARY, index=False)
    ratio_known = level_band / shape_known
    ratio_unknown = level_band / shape_unknown

    report = [
        "# Level risk: the half of a residual value that no car-level model can see", "",
        "Generated by `analysis/level_risk.py` from `data/reference/price_indices.parquet`. "
        "No new data source; this is the reference table `build_reference.py` already builds.", "",
        "A three-year lease fixes a residual value today and learns in 36 months whether it was "
        "right. Two things can make it wrong: **the curve** - how fast this particular car lost "
        "value - and **the level** - what the whole used market was worth on the day it came back. "
        "Every other analysis in this project measures the curve. This one measures the level, in "
        "the same unit, so the two can be put side by side.", "",
        "## Method", "",
        f"Coverage is very uneven. France and Lithuania run from 1996; most markets begin between "
        f"2014 and 2016. Pooling every overlapping window across all markets would let those two "
        f"supply a third of the sample, so the headline panel uses a **common window, "
        f"{COMMON_START} to {COMMON_END}**, in which every market contributes the same number of "
        f"windows. {len(common)} EU national markets clear that bar. "
        + (f"Dropped for short coverage: {', '.join(dropped)}. " if dropped else "")
        + "Aggregates (EA, EU27) are excluded because they would double-count their members. "
        "Long histories are reported separately below as a check.", "",
        "## Each market on its own", "",
        md_table(per_market), "",
        "*Worst drawdown* is the largest peak-to-trough fall in the index over the window.", "",
        "## Pooled, every market weighted equally", "",
        md_table(pd.DataFrame(pooled_tbl)), "",
        "## How far the level drifts between two reviews", "",
        "Stellantis states that expected residual values are **analyzed quarterly** and depreciation "
        "rates adjusted accordingly ([Form 20-F FY2025]"
        "(https://www.sec.gov/Archives/edgar/data/1605484/000160548426000021/stellantis-20251231.htm))."
        " Three months is therefore the window in which a move goes unseen. The same markets, same "
        "common window, at shorter horizons:", "",
        md_table(pd.DataFrame(review_tbl)), "",
        "## The long series, full history", "",
        md_table(pd.DataFrame(long_rows)), "",
        "The US row is **US data** and is here only for contrast: it contains the 2020-2022 "
        "used-car spike, the largest move in any series in the table.", "",
        "## Curve error against level error, in the same unit", "",
        f"A car that keeps {base*100:.1f}% of its list price after {LEASE_YEARS} years at the "
        f"pooled {abs(SHAPE_POOLED)*100:.1f}%-a-year rate is the reference point. Each row below "
        "asks how far that number moves when one source of error is applied.", "",
        md_table(compare), "",
        f"- **In a market the group already sells in, level risk is about "
        f"{ratio_known:.0f} times curve risk.** The curve is known to within about "
        f"{shape_known:.1f} points of list price; the market level moves by about "
        f"{level_band:.0f} points across an ordinary three-year window.",
        f"- **In a market or a brand with no history, the two are comparable** "
        f"({shape_unknown:.0f} points against {level_band:.0f}, a ratio of "
        f"{ratio_unknown:.1f}). That is the thin-slice case, and it is the one pooling fixes: "
        "`lodo_report.md` shows borrowing pays only while a slice has few cars of its own.",
        f"- **Like for like, the gap is wider still.** The level row is a p10-p90 band; the first "
        f"two curve rows are the full range of 52 refits and a 95% interval, both wider measures. "
        f"At p10-p90 on both sides, level risk is about {level_band / known80:.0f} times curve "
        f"risk in a known market ({known80:.1f} points) and {level_band / unknown80:.1f} times in "
        f"a market with no history ({unknown80:.1f} points). The headline comparison is therefore "
        "the conservative one. The value-at-risk model uses the p10-p90 rows, so its curve "
        "downside sits at the same one-in-ten as its level shock.",
        "- **The two errors therefore need two different remedies.** Curve error is a modelling "
        "problem and a shared value engine solves it. Level error is not a modelling problem at "
        "all: no amount of car data forecasts it, so it has to be priced into the decision and "
        "re-marked as it moves.", "",
        "### The same over one year", "",
        f"Most of the group's buy-back payables fall due within a year ([Form 20-F FY2025, Note 24]"
        "(https://www.sec.gov/Archives/edgar/data/1605484/000160548426000021/stellantis-20251231.htm)"
        f"), so the value-at-risk model also needs the one-year version. A car that keeps "
        f"{base1*100:.1f}% of its list price after one "
        f"year at the pooled {abs(SHAPE_POOLED)*100:.1f}%-a-year rate is the one-year reference "
        "point. Same measured ranges as above, over one year, and the level from 12-month moves "
        f"across all {len(common)} markets:", "",
        md_table(one_year), "",
        f"Over one year level risk is about {level_band_1y / known80_1y:.0f} times curve risk in a "
        f"known market and {level_band_1y / unknown80_1y:.1f} times in a market with no history.", "",
        "## What this means for the case", "",
        "1. **A residual value set today is a bet on the market, not on the car.** The car part is "
        "knowable to a few points. The market part is not knowable at all at a three-year horizon, "
        f"and has actually moved {worst*100:+.0f}% over three years in this sample.",
        "2. **So the ledger's job is not a better forecast.** It is to separate the two, price the "
        "part that cannot be forecast, and re-mark it monthly - the design rule "
        "`latvia_time_report.md` arrived at from the other direction.",
        "3. **And the decisions that stay open are worth more than the forecast.** A contractual "
        "residual is locked on day one; when to offer the upgrade, which channel to sell through "
        "and which country to sell in are not. Those are where a moving level can be answered.", "",
        "## Limits", "",
        "- **These are official consumer price indices, not the group's own realised prices.** "
        "Each statistical office quality-adjusts its own way, and the basket is consumer "
        "second-hand purchases, not a lease book's mix.",
        "- **The windows overlap**, so they are not independent draws. The percentiles describe "
        "the range of history, not a sampling distribution.",
        "- **Official indices may understate the moves.** `latvia_time_report.md` found our "
        "advert-based Latvian index rose +42% against Eurostat's +8.8% over the same months, with "
        "Latvia's neighbours (LT +38%, EE +38%) sitting with our figure. If that pattern holds "
        "elsewhere, the level risk here is a floor, not a ceiling.",
        f"- **The common window is {COMMON_START} to {COMMON_END}**, which contains the 2021-22 "
        "shortage and its unwinding. That is a real episode, not an outlier to be removed, but a "
        "different decade would give different percentiles.",
        "- The curve figures compared here come from advert prices; the level indices are built "
        "from transaction data. They are not the same kind of measurement.", "",
    ]
    OUT.write_text("\n".join(report))

    print(f"{len(common)} EU markets, common window {COMMON_START}..{COMMON_END}")
    print(f"36m moves, p10 {lo*100:+.1f}% | median {np.median(pool_all[36]):+.1f}% | p90 {hi*100:+.1f}%")
    print(f"curve error {shape_known:.1f}pp (market known) / {shape_unknown:.1f}pp (unknown); "
          f"p10-p90 {known80:.1f}pp / {unknown80:.1f}pp")
    print(f"level error {level_band:.1f}pp -> ratio {ratio_known:.1f}x known, {ratio_unknown:.1f}x unknown")
    print(f"wrote {OUT} and {SERIES}")


if __name__ == "__main__":
    main()
