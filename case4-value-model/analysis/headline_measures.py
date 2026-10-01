"""X18: leak 3's level and curve lines in two measures, expected a year and one year in ten.

Skeptic F5: the headline added expected yearly losses (leaks 1 and 2, leak 3's resale execution) to a one-in-ten-year
downside (leak 3's level p10 plus the curve's centre-to-p10). A CFO reads one figure as a yearly cost. Basel's
convention (`bcbs_el_provisions`) is to show an expected loss, which is budgeted, beside a tail, which a price or
capital must hold, and never to add them. This script measures both for leak 3's level and curve, on the same data
the workbook already uses.

**What the book is.** The 20-F books every buy-back contract as an operating lease: either a repurchase obligation
(the group "is required to repurchase"), or a customer put that is expected to be exercised. Gains and losses are
booked at disposal against the carrying value (`stellantis_buyback_forms`). So the book is **two-sided**: the cars
come back, and a rising market pays for a falling one around the estimated residual. X6's put (one-sided, the group
bears only the downside) is right where a customer holds an option struck at the residual; here it is the upper end.

1. **The loss.** Per euro of the book due within a year (the workbook's base), a year's loss is
   `-(L + (1-t) C_known + t C_thin)`: the book's 12-month level move `L`, its markets weighted as it sells
   (`merger_diversification.py`'s base variant, which gives `level_1y_p10_book`), plus the curve error on the part of
   the book with its own history and on the thin slice, weighted by `thin_share_of_book` (`t`). The residual assumes
   no change in the level, X7's best forecast beyond a quarter.
2. **The curve's errors,** as `level_risk.py` builds them: the 52 monthly Latvian refits (with its own data) and the
   Student's t prediction interval across datasets (no history), each centred on its median and taken over one year
   on the pooled retained value. A 200-point quantile grid stands in for the t.
3. **Expected a year:** the mean loss. Two-sided on the book's own record; the same on the UK's 1988-2026 record,
   the longest we hold, as a check; one-sided per contract (each car in its own market, each slice with its own
   curve error, only losses count) as the upper end.
4. **One year in ten:** the p10 of the combined move, level and curve independent, against today's sum of their
   separate p10s (which assumes they go wrong together). The same for the stress (the core markets' pooled 12-month
   moves, which give `level_1y_p10_core`). The joint as a share of the sum is what the workbook applies.
5. **Do they go wrong together?** In Latvia, the year's change in the refitted curve against the year's level move.

Checks: the book's, the core markets' and the UK's p10 reproduce the register; the curve spreads reproduce
`curve_1y_p80_*`; toy cases (a sum of p10s equals the joint p10 for perfectly dependent risks and exceeds it for
independent ones); the two-sided identity; the joint below the sum and the one-sided mean above the two-sided on the
real data.

Usage: .venv/bin/python analysis/headline_measures.py   (writes analysis/headline_measures_report.md; under a minute)
"""
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import level_charge  # noqa: E402
import level_risk  # noqa: E402
import merger_diversification as md  # noqa: E402
from build_unified import md_table  # noqa: E402

OUT = HERE / "headline_measures_report.md"
REGISTER = HERE.parent / "assumptions.csv"
GRID = 200                        # quantile points standing in for the thin slice's Student's t
LV_HORIZONS = (3, 6, 12)


def register():
    rows = {r["id"]: r for r in csv.DictReader(open(REGISTER, encoding="utf-8"))}
    f = lambda k, c="value": float(rows[k][c])  # noqa: E731
    return {k: f(k) for k in ("buyback_payables_current_eur_m", "thin_share_of_book", "retained_1y_pooled",
                              "curve_1y_p80_known", "curve_1y_p80_unknown", "level_1y_p10_book",
                              "level_1y_p10_core", "level_1y_p10_uk_long")} | {
        "thin_low": f("thin_share_of_book", "low"), "thin_high": f("thin_share_of_book", "high")}


def curve_errors(retained):
    """The curve error over one year as a share of the residual: the Latvian refits and the t interval, centred."""
    rates = pd.read_csv(level_risk.LATVIA_MONTHLY)["depreciation_pct_per_year"].dropna().to_numpy() / 100
    known = (rates - np.median(rates)) / retained
    mid = np.mean(np.log1p(level_risk.SHAPE_ACROSS))
    scale = np.diff(np.log1p(level_risk.SHAPE_ACROSS))[0] / 2 / level_risk.T975_DF15
    q = (np.arange(GRID) + 0.5) / GRID
    thin = (np.expm1(mid + scale * student_t.ppf(q, level_risk._DF)) - np.expm1(mid)) / retained
    spread80 = lambda lo, hi: (np.expm1(mid + scale * hi) - np.expm1(mid + scale * lo)) * 100  # noqa: E731
    t90 = student_t.ppf(0.9, level_risk._DF)
    return known, thin, (np.percentile(rates, 90) - np.percentile(rates, 10)) * 100, spread80(-t90, t90)


def half80(x):
    return (np.percentile(x, 90) - np.percentile(x, 10)) / 2


def combined(level, known, thin, t):
    """Every combination of a level move and the two slices' curve errors, as the book's move (equally weighted)."""
    return (np.asarray(level)[:, None, None] + (1 - t) * known[None, :, None] + t * thin[None, None, :]).ravel()


def one_in_ten(level, known, thin, t):
    """Loss one year in ten: the sum of the separate p10s (today's workbook) and the joint p10, both as losses."""
    summed = -np.percentile(level, 10) + (1 - t) * half80(known) + t * half80(thin)
    joint = -np.percentile(combined(level, known, thin, t), 10)
    return summed, joint


def one_sided(moves, weights, known, thin, t, strike=0.0):
    """Mean and p90 of the book's loss when only losses count, per contract: each car in its own market's move,
    each slice with its own (common) curve error."""
    m = moves.to_numpy() - strike
    w = weights.to_numpy()
    k = np.einsum("wmk,m->wk", np.maximum(0, -(m[:, :, None] + known[None, None, :])), w)
    u = np.einsum("wmu,m->wu", np.maximum(0, -(m[:, :, None] + thin[None, None, :])), w)
    loss = ((1 - t) * k[:, :, None] + t * u[:, None, :]).ravel()
    return float(loss.mean()), float(np.percentile(loss, 90))


def latvia_comovement():
    """The year's change in the refitted curve against the year's level move, Latvia's monthly refits."""
    lv = pd.read_csv(level_risk.LATVIA_MONTHLY)
    rate = lv["depreciation_pct_per_year"] / 100
    rows = []
    for idx, name in (("eurostat_index", "Eurostat index"), ("our_index", "our advert index")):
        for k in LV_HORIZONS:
            z = pd.concat([rate.shift(-k) - rate, lv[idx].shift(-k) / lv[idx] - 1], axis=1).dropna()
            rows.append({"window": f"{k} months, {name}, overlapping", "windows": len(z),
                         "correlation": round(float(z.corr().iloc[0, 1]), 2)})
            if k == 12:
                zz = z.iloc[::12]
                rows.append({"window": f"12 months, {name}, non-overlapping", "windows": len(zz),
                             "correlation": round(float(zz.corr().iloc[0, 1]), 2)})
    return pd.DataFrame(rows), lv["month"].iloc[0], lv["month"].iloc[-1]


def pct(x, d=2):
    return round(100 * float(x), d)


def main():
    reg = register()
    t, book, ret = reg["thin_share_of_book"] / 100, reg["buyback_payables_current_eur_m"], reg["retained_1y_pooled"] / 100
    known, thin, known80, thin80 = curve_errors(ret)

    d = md.clean(md.registrations())
    series, n, m = md.run_variant(d, md.VARIANTS[md.BASE_VARIANT])
    markets = m["markets"]
    weights = m["weights"].loc[markets, "merged"]
    moves = md.market_moves({g: series[g] for g in markets}, 12)[markets]
    L = (moves @ weights).to_numpy()
    common, core, _ = level_charge.common_panel()
    pool = level_risk.pooled(common, core, 12) / 100
    uk_raw = level_risk.load()[(md.ONS_SERIES, "UK")].dropna()
    uk = (uk_raw.shift(-12) / uk_raw - 1).dropna().to_numpy()

    # ---- checks ----
    ck = []

    def check(name, want, got, tol):
        ck.append({"check": name, "expected": want, "got": round(float(got), 4), "passes": abs(want - got) <= tol})

    check("the book's p10 reproduces `level_1y_p10_book` (3 decimals)", reg["level_1y_p10_book"], pct(np.percentile(L, 10), 3), 5e-4)
    check("the core markets' pooled p10 reproduces `level_1y_p10_core` (1 decimal)", reg["level_1y_p10_core"],
          round(100 * np.percentile(pool, 10), 1), 1e-9)
    check("the UK's 1988-2026 p10 reproduces `level_1y_p10_uk_long` (2 decimals)", reg["level_1y_p10_uk_long"],
          pct(np.percentile(uk, 10)), 5e-3)
    check("the refits' one-year spread reproduces `curve_1y_p80_known` (1 decimal)", reg["curve_1y_p80_known"],
          round(known80, 1), 1e-9)
    check("the t interval's one-year spread reproduces `curve_1y_p80_unknown` (1 decimal)",
          reg["curve_1y_p80_unknown"], round(thin80, 1), 1e-9)
    a = np.linspace(-0.1, 0.1, 1001)
    check("toy: perfectly dependent risks, the joint p10 equals the sum of p10s", 0.0,
          np.percentile(a + 2 * a, 10) - (np.percentile(a, 10) + np.percentile(2 * a, 10)), 1e-12)
    ind = (a[:, None] + a[None, :]).ravel()
    check("toy: independent risks, the joint p10 loss is below the sum (1 = yes)", 1.0,
          float(-np.percentile(ind, 10) < -2 * np.percentile(a, 10)), 0)
    x = combined(L, known, thin, t)
    check("two-sided identity on the book: E[loss] - E[gain] = -E[move]", 0.0,
          np.maximum(0, -x).mean() - np.maximum(0, x).mean() + x.mean(), 1e-12)
    summed, joint = one_in_ten(L, known, thin, t)
    exp_one, p90_one = one_sided(moves, weights, known, thin, t)
    check("on the book, the joint p10 loss is below the sum of p10s (1 = yes)", 1.0, float(joint < summed), 0)
    check("on the book, the one-sided mean is above the two-sided mean (1 = yes)", 1.0, float(exp_one > -x.mean()), 0)
    ck = pd.DataFrame(ck)
    all_ok = bool(ck["passes"].all())

    # ---- the measures ----
    xu = combined(uk, known, thin, t)
    med = float(np.median(moves.to_numpy().ravel()))
    exp_one_med, _ = one_sided(moves, weights, known, thin, t, strike=med)
    s_summed, s_joint = one_in_ten(pool, known, thin, t)
    level = pd.DataFrame([
        ("the book's 12-month move, p10", pct(np.percentile(L, 10), 3)),
        ("the book's 12-month move, median", pct(np.median(L), 3)),
        ("the book's 12-month move, mean", pct(L.mean(), 3)),
        ("the book's 12-month move, worst", pct(L.min(), 3)),
        ("the book's 12-month move, best", pct(L.max(), 3)),
        ("its markets' moves pooled, median (X6's median strike)", pct(med, 3)),
        ("the core markets' moves pooled, p10 (the stress)", pct(np.percentile(pool, 10), 3)),
        ("the UK's 12-month move 1988-2026, p10", pct(np.percentile(uk, 10), 3)),
        ("the UK's 12-month move 1988-2026, mean", pct(uk.mean(), 3)),
    ], columns=["measure", "move (%)"])
    expected = pd.DataFrame([
        ("two-sided, the book's record", -x.mean(),
         "the 20-F's contracts: the cars come back, so gains count too; a residual at no change gained over the decade"),
        ("two-sided, the UK's 1988-2026 record", -xu.mean(), "the same, on the longest record we hold (UK data)"),
        ("one-sided per contract, residual at no change", exp_one,
         "upper end: as if every contract were a customer's put struck at the residual (X6's case)"),
        ("one-sided per contract, residual at the median move", exp_one_med, "the same at X6's median strike"),
    ], columns=["measure", "share", "reading"])
    expected["% of the book"] = [pct(v, 3) for v in expected["share"]]
    expected["EUR m on the book due within a year"] = [round(v * book, 1) for v in expected["share"]]
    expected = expected[["measure", "% of the book", "EUR m on the book due within a year", "reading"]]
    tails = pd.DataFrame([
        ("base: the book's own record", summed, joint),
        ("stress: a core market's bad year", s_summed, s_joint),
    ], columns=["case", "sum", "joint"])
    tails["sum of the two p10s (%)"] = [pct(v, 3) for v in tails["sum"]]
    tails["joint p10 (%)"] = [pct(v, 3) for v in tails["joint"]]
    tails["joint as % of the sum"] = [round(100 * j / s, 1) for s, j in zip(tails["sum"], tails["joint"])]
    tails["EUR m, sum"] = [round(v * book, 1) for v in tails["sum"]]
    tails["EUR m, joint"] = [round(v * book, 1) for v in tails["joint"]]
    tails = tails.drop(columns=["sum", "joint"])
    thin_rows = []
    for label, tt in (("low", reg["thin_low"]), ("central", reg["thin_share_of_book"]), ("high", reg["thin_high"])):
        s1, j1 = one_in_ten(L, known, thin, tt / 100)
        s2, j2 = one_in_ten(pool, known, thin, tt / 100)
        thin_rows.append({"thin share": f"{label} ({tt:g}%)", "base: joint as % of the sum": round(100 * j1 / s1, 1),
                          "stress: joint as % of the sum": round(100 * j2 / s2, 1)})
    thin_table = pd.DataFrame(thin_rows)
    one_side_tail = pd.DataFrame([("one-sided per contract, the book's record, p90 loss", pct(p90_one, 3)),
                                  ("two-sided, the book's record, p90 loss (the joint p10)", pct(joint, 3))],
                                 columns=["measure", "% of the book"])
    co, lv_start, lv_end = latvia_comovement()
    c12 = co.loc[co["window"] == "12 months, Eurostat index, overlapping"].iloc[0]
    c12n = co.loc[co["window"] == "12 months, Eurostat index, non-overlapping"].iloc[0]

    findings = [
        f"- **Expected a year, two-sided (the 20-F's contracts):** on the book's own record a residual set at no change "
        f"*gained* {pct(x.mean())}% of the book a year, because the level rose on average over the decade (mean "
        f"{pct(L.mean())}%, median {pct(np.median(L))}%: one boom lifts the mean). On the UK's 1988-2026 record the same "
        f"residual lost {pct(-xu.mean())}% a year. So the level and curve cost about nothing on average: the workbook "
        "counts the book's record, floored at zero (a gain is not a leak), and shows the UK figure beside it.",
        f"- **Upper end, one-sided:** if every contract were a customer's put struck at the residual, the expected loss "
        f"would be {pct(exp_one)}% of the book, EUR {exp_one * book:.1f}m a year. That is X6's case; the 20-F's contracts "
        "are not it, but where a put caps the group's upside the truth lies between.",
        f"- **One year in ten, base:** the level and the curve at their separate p10s add to {pct(summed)}% of the book "
        f"(EUR {summed * book:.1f}m); their joint p10 is {pct(joint)}% (EUR {joint * book:.1f}m), "
        f"{100 * joint / summed:.1f}% of the sum. The sum is a year in which both go wrong at once, rarer than one in ten.",
        f"- **Stress:** {pct(s_summed)}% against a joint {pct(s_joint)}% ({100 * s_joint / s_summed:.1f}% of the sum): "
        "the level dominates a core market's bad year, so less is gained by not adding.",
        f"- **They don't go wrong together in Latvia:** the year's change in the refitted curve moved against the "
        f"year's level move (correlation {c12['correlation']} over {c12['windows']} overlapping windows, "
        f"{c12n['correlation']} over {c12n['windows']} independent years, {lv_start} to {lv_end}). Treating them as "
        "independent is, on this evidence, cautious.",
    ]
    lines = [
        "# X18: the headline in two measures, expected a year and one year in ten",
        "",
        "_Generated by `analysis/headline_measures.py`. The book's 12-month level moves (Eurostat HICP CP07112 and ONS, "
        "its markets weighted by the group's 2019 registrations, France on the euro-area index: the base of "
        "`level_1y_p10_book`), the core markets' pooled moves (the stress), the UK's ONS series 1988-2026, the 52 "
        "Latvian monthly refits and the curve's cross-dataset interval. Per euro of buy-back payables due within a "
        "year. Real data, nothing synthetic._",
        "",
        "## Checks",
        "",
        md_table(ck.assign(passes=ck["passes"].map({True: "yes", False: "NO"}))),
        "",
        f"All checks pass: {'yes' if all_ok else 'NO'}.",
        "",
        "## What it shows",
        "",
        *findings,
        "",
        "## 1. The level alone: the book's one-year moves",
        "",
        md_table(level),
        "",
        "## 2. Expected a year, level and curve",
        "",
        md_table(expected),
        "",
        "## 3. One year in ten, level and curve",
        "",
        md_table(tails),
        "",
        "### Across the thin share's range",
        "",
        md_table(thin_table),
        "",
        "### One-sided, for comparison",
        "",
        md_table(one_side_tail),
        "",
        "## 4. Do the curve and the level go wrong together? Latvia",
        "",
        "The change in the refitted depreciation rate over the window against the level's move over the same window. "
        "A positive correlation would mean a steeper curve when the level falls, both losses at once.",
        "",
        md_table(co),
        "",
        "## Limits",
        "",
        "- **The contract mix is not published.** Repurchase obligations are two-sided; a customer's put caps the "
        "group's upside at the repurchase price, whose cost is not disclosed. The one-sided row is the upper end.",
        "- **The book's record is nine years with one boom and no Europe-wide crash.** Its mean is that decade's drift, "
        "not an expectation, hence the UK check and the floor at zero; its p10 is why the stress exists.",
        "- **Independence is assumed** between the level and the curve. Latvia's refits lean the other way, but that is "
        "one country and a handful of independent years; the sum of p10s stays in the workbook as the upper end.",
        "- **The curve's shape** comes from one country's refits and a Student's t across datasets; the one-in-ten "
        "figure depends on their tails, which are thin samples.",
        "- **Index prices** understate the level a lessor meets (X7), so both measures are floors.",
        "- **One in ten is a 90% level;** capital standards sit far higher (`bcbs_irb_confidence_pct`).",
        "- **Leaks 1 and 2 and resale execution** have no measured distributions, so the one-in-ten column holds them "
        "at their expected values.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(expected.drop(columns=["reading"]).to_string(index=False))
    print(tails.to_string(index=False))
    print(f"wrote {OUT.name}; checks pass: {all_ok}")


if __name__ == "__main__":
    main()
