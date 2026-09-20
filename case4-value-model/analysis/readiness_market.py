"""Layer 4: does the market level change which cars come to market?

Layers 1 and 2 answer "how likely" and "which car". Layer 4 asks whether the answer moves when the
used-car market moves. The only place the project can ask it is Latvia: 52 monthly snapshots of
ss.com, 2019 to 2023, spanning the shortage, with a quality-adjusted price index already built by
`latvia_time.py` and Eurostat's official Latvian index beside it.

**Volume is not the measure, and that is the first thing to get right.** `lv_ss` has no advert id,
so a car that stays listed is counted again every month, and the number of rows in a month is as
much a fact about the scrape as about the market. Anything built on monthly counts would be
measuring the scraper.

**Composition is the measure.** What share of the cars on sale are old ones, and what is the median
age and mileage on offer? Those are ratios inside a month, so the size of the scrape divides out.
If a rising market pulls cars onto the market that would otherwise have stayed on the road, the
mix gets older and harder-driven. That is a testable statement about the hazard, and it is the one
this data can carry.

The comparison is against `our_index` (quality-adjusted, ours) with Eurostat's official Latvian
second-hand index as the independent check.

Usage: .venv/bin/python analysis/readiness_market.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import md_table  # noqa: E402

HERE = Path(__file__).parent
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
MONTHLY = HERE / "latvia_monthly.csv"
OUT = HERE / "readiness_market_report.md"
TABLE = HERE / "readiness_market_monthly.csv"

OLD_YEARS = 15          # "an old car" in a fleet whose median is well above ten
HIGH_KM = 250_000


def monthly():
    cols = ["source", "listing_date", "age_years", "mileage_km", "price_eur", "is_new",
            "price_type"]
    d = pd.read_parquet(LISTINGS, columns=cols)
    d = d[(d["source"] == "lv_ss") & d["price_type"].eq("asking")]
    d = d[d["age_years"].between(0.5, 40) & d["price_eur"].between(500, 200_000)]
    d = d.dropna(subset=["listing_date", "age_years"])
    d["month"] = pd.to_datetime(d["listing_date"]).dt.to_period("M").astype(str)
    g = d.groupby("month")
    out = pd.DataFrame({
        "rows": g.size(),
        "median_age": g["age_years"].median(),
        "share_old": g["age_years"].apply(lambda s: float((s >= OLD_YEARS).mean())),
        "median_km": g["mileage_km"].median(),
        "share_high_km": g["mileage_km"].apply(lambda s: float((s >= HIGH_KM).mean())),
    }).reset_index()
    idx = pd.read_csv(MONTHLY)
    return out.merge(idx, on="month", how="inner")


def fit(y, x, t, months):
    """y on x, with a linear trend and calendar-month effects.

    The trend matters: both a price index and a fleet's age drift over five years, and without it
    any two rising series look related. The calendar effects matter because a used-car market has
    a season.
    """
    parts = [np.ones(len(y)), x - x.mean(), (t - t.mean()) / t.std()]
    for m in range(2, 13):
        parts.append((months == m).astype(float))
    X = np.column_stack(parts)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = max(len(y) - X.shape[1], 1)
    cov = float(resid @ resid / dof) * np.linalg.pinv(X.T @ X)
    return float(beta[1]), float(np.sqrt(cov[1, 1]))


def main():
    d = monthly().sort_values("month", ignore_index=True)
    d["t"] = np.arange(len(d), dtype=float)
    d["moy"] = pd.to_datetime(d["month"] + "-01").dt.month
    print(f"{len(d)} months, {int(d['rows'].sum()):,} listing rows")

    rows = []
    for index_name, label in (("our_index", "our quality-adjusted index"),
                              ("eurostat_index", "Eurostat's official index")):
        x = np.log(d[index_name].to_numpy(float))
        for col, what, unit in (("median_age", "Median age on sale", "years per 10% of price"),
                                ("share_old", f"Share aged {OLD_YEARS}+", "points per 10%"),
                                ("median_km", "Median mileage on sale", "km per 10% of price"),
                                ("share_high_km", f"Share over {HIGH_KM:,} km", "points per 10%")):
            y = d[col].to_numpy(float)
            b, se = fit(y, x, d["t"].to_numpy(float), d["moy"].to_numpy())
            step = np.log(1.10)                      # a ten per cent stronger market
            rows.append({"index": label, "what": what, "unit": unit,
                         "effect": b * step, "se": se * step,
                         "t": b / se if se else np.nan})
    res = pd.DataFrame(rows)

    fmtnum = lambda v: f"{v:+,.3f}" if abs(v) < 10 else f"{v:+,.0f}"
    strong = res.loc[res["t"].abs().idxmax()]
    price_move = d["our_index"].max() / d["our_index"].min() - 1
    vol_r = float(np.corrcoef(np.log(d["rows"]), np.log(d["our_index"]))[0, 1])

    lines = [
        "# Layer 4: does the market level change which cars come to market?",
        "",
        f"Latvia, {d['month'].iloc[0]} to {d['month'].iloc[-1]}, {len(d)} monthly snapshots of "
        f"ss.com, {int(d['rows'].sum()):,} listing rows. Over that window our quality-adjusted "
        f"Latvian price index rises **{price_move:.0%}**, so there is a real market move to test "
        "against - this is the window that contains the shortage.",
        "",
        "**Volume is not used, on purpose.** `lv_ss` carries no advert id, so a car that stays "
        "listed is counted again in every snapshot and a month's row count is as much a fact "
        f"about the scrape as about the market. For the record, log rows against log price "
        f"correlate at {vol_r:+.2f}, and **that number should not be quoted**: it cannot be told "
        "apart from the scraper changing size.",
        "",
        "What *can* be measured is composition - the mix of what is on sale, which is a ratio "
        "inside a month, so the size of the scrape divides out. Each row below is the effect of a "
        "**10% stronger market**, with a linear time trend and calendar-month effects taken out.",
        "",
    ]
    # one unique label per row, so check_assumptions.py can pin a figure to its own cell
    res["label"] = res["what"] + ", against " + res["index"]
    lines.append(md_table(pd.DataFrame({
        "Measure": res["label"],
        "Effect of a 10% stronger market": [fmtnum(v) for v in res["effect"]],
        "t": res["t"].map("{:+.1f}".format),
        "Unit": res["unit"],
    })))
    agree = (np.sign(res[res["index"].str.startswith("our")]["effect"].to_numpy())
             == np.sign(res[res["index"].str.startswith("Eurostat")]["effect"].to_numpy()))
    lines += [
        "",
        f"The strongest reading is **{strong['what']}** against {strong['index']}: "
        f"{fmtnum(strong['effect'])} {strong['unit']}, t {strong['t']:+.1f}. The two indices agree "
        f"on the sign of {int(agree.sum())} of {len(agree)} measures.",
        "",
        "## What to take from it",
        "",
        "- **There are two readings and this data cannot separate them.** Either a stronger "
        "market pulls older, harder-driven cars onto the market that would otherwise have stayed "
        "on the road - which is a hazard effect and the one the engine would want - or those cars "
        "simply sell more slowly and pile up in what is on display. Without an advert id `lv_ss` "
        "shows the cars that *are* on sale, not the cars that *came* on sale, so both produce "
        "exactly this table. **Do not present it as proof of the first reading.** What argues "
        "mildly against the second is that the window is the shortage, when cheap old cars sold "
        "unusually fast, but that is an argument, not a measurement.",
        "- **One market, and an unusual one.** Latvia over 2019-2023 contains the shortage. The "
        "project has measured that the level moved and the depreciation *rate* did not "
        "(`latvia_time_report.md`: 52 months all between -13.2% and -11.7% a year).",
        "- **It does not give the engine a coefficient.** Layer 4 in the engine remains the value "
        "side - `level_risk.py` and `value_engine.py` already price what the market level does to "
        "the money. What this adds is whether the level moves the *hazard*, and on this data the "
        "honest answer is a composition effect of the size in the table, measured on a stock.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    d.to_csv(TABLE, index=False)
    res.to_csv(TABLE.with_name("readiness_market_effects.csv"), index=False)
    print(f"wrote {OUT.name}")
    for _, r in res.iterrows():
        print(f"  {r['index'][:22]:24s} {r['what']:28s} {fmtnum(r['effect'])} (t {r['t']:+.1f})")


if __name__ == "__main__":
    main()
