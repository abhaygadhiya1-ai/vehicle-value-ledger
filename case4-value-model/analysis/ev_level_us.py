"""X9 part 3: how often, and how far, does the used-EV level move on its own? A long realised series (US data).

Europe's EV adverts give a few scrapes (part 2). The only long, realised, monthly used-EV price record we hold is
Washington State's title transfers (`us_wa_ev_sales`): a sale price and a sale date for every used EV and plug-in
hybrid retitled, 2017 to 2026. **US data**, and the prices are self-reported on the title (the loader's filters and
the pass-through study's price band apply). It answers what Europe's scrapes cannot: the distribution of EV level
moves, on X6's measures, beside the whole used market's over the same months (US CPI used cars and trucks, seasonally
adjusted, CUSR0000SETA02, the series X7 used).

The index: used sales only, a fixed effect per make, model and whole year of age (the same kind of car at the same
age, the concept of the official indices), log mileage, and a dummy per month; January 2017 = 1. Built for battery
EVs with and without Tesla (whose 2023 price cuts must not carry the finding; the Tesla event study stays withdrawn)
and for plug-in hybrids. A monthly hedonic index carries sampling noise, which would widen its tail against the smooth
CPI, so the tail measures use its three-month average (checked not to drive the result), and every measure is recomputed on
a make-model cluster bootstrap for its range.

Measures, both series over the same months: the one-year move's p10 and worst; the largest fall from a peak; and X6's
expected shortfall per unit of residual at 36 and 48 months, at X6's two strikes (`level_charge.charge`). The ratio of
EV to market is what part 4 may carry, labelled US, to leak 3's EV slice.

Checks: a planted fall in the EV index is recovered exactly; January 2017 is 1 by construction; the market series is
X7's; smoothing moves no one-year p10 by more than a point.

Usage: .venv/bin/python analysis/ev_level_us.py   (writes analysis/ev_level_us_report.md)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
from ev_level import demean, model_weights, wls  # noqa: E402
from level_charge import charge  # noqa: E402

LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
OUT = HERE / "ev_level_us_report.md"
SEED = 20260926
DRAWS = 100
PRICE_BAND = (2000, 150000)      # us_wa_ev_sales writes sale dates into some price fields (discount_passthrough.py)
START = "2017-01"
HORIZONS = (36, 48)


def load():
    d = pd.read_parquet(LISTINGS, filters=[("source", "==", "us_wa_ev_sales")],
                        columns=["make", "model", "fuel", "age_years", "mileage_km", "price", "listing_date", "is_new"])
    d = d[~d["is_new"].fillna(True).astype(bool) & d["price"].between(*PRICE_BAND)
          & d["mileage_km"].between(1_000, 300_000) & d["age_years"].between(0.5, 12)].copy()
    d["month"] = d["listing_date"].dt.to_period("M")
    d = d[d["month"] >= pd.Period(START, "M")]
    d["mm"] = d["make"].astype(str).str.lower() + "|" + d["model"].astype(str).str.lower()
    d["cell"] = d["mm"] + "|" + d["age_years"].round().astype(int).astype(str)
    d["y"] = np.log(d["price"].astype(float))
    d["log_km"] = np.log(d["mileage_km"].astype(float))
    return d.reset_index(drop=True)


def fit_index(f, w=None):
    """Monthly index (log), the first month 0: cell fixed effects, log mileage, a dummy per later month."""
    months = sorted(f["month"].unique())
    idx = pd.Series(pd.Categorical(f["month"], categories=months).codes)
    X = np.zeros((len(f), len(months)))
    X[np.arange(len(f)), idx.to_numpy()] = 1.0
    X = np.column_stack([X[:, 1:], f["log_km"].to_numpy()])
    w = np.ones(len(f)) if w is None else w
    keep = w > 0
    g = pd.factorize(f["cell"].to_numpy()[keep])[0]
    beta = wls(demean(f["y"].to_numpy()[keep], g, w[keep]), demean(X[keep], g, w[keep]), w[keep])
    return pd.Series(np.r_[0.0, beta[:-1]], index=pd.PeriodIndex(months, freq="M"))


def index_with_draws(f, rng):
    """The index and its model-cluster bootstrap draws (which models are in it moves the EV level a lot)."""
    point = fit_index(f)
    boots = [fit_index(f, model_weights(f, rng)).reindex(point.index) for _ in range(DRAWS)]
    return point, boots


def smooth(log_index):
    return log_index.rolling(3, center=True, min_periods=2).mean()


def measures(level):
    """X6's measures on a level series (not logged)."""
    one = (level.shift(-12) / level - 1).dropna()
    out = {"one-year move, p10 (%)": 100 * np.percentile(one, 10), "one-year move, worst (%)": 100 * one.min(),
           "largest fall from a peak (%)": 100 * (level / level.cummax() - 1).min()}
    for k in HORIZONS:
        mv = (level.shift(-k) / level - 1).dropna()
        for strike in ("no change", "median"):
            c = charge(mv, strike)
            out[f"{k}-month expected shortfall, {strike} strike (% of residual)"] = 100 * c["expected"]
            out[f"{k}-month worst tenth, {strike} strike (% of residual)"] = 100 * c["worst_tenth"]
    out["windows, one-year"] = len(one)
    return out


def main():
    rng = np.random.default_rng(SEED)
    from level_risk import load as load_levels
    from level_long import US
    cpi = load_levels()[(US, "US")].dropna()
    cpi.index = pd.PeriodIndex(cpi.index, freq="M")

    d = load()
    print(f"used EV and PHEV sales: {len(d):,}")
    sets = {"battery EVs": d[d["fuel"] == "electric"],
            "battery EVs without Tesla": d[(d["fuel"] == "electric") & ~d["mm"].str.startswith("tesla|")],
            "plug-in hybrids": d[d["fuel"] == "plugin_hybrid"]}
    indices, draws, counts = {}, {}, {}
    for name, f in sets.items():
        f = f.reset_index(drop=True)
        indices[name], draws[name] = index_with_draws(f, rng)
        counts[name] = len(f)
        print(name, len(f))
    common = indices["battery EVs"].index.intersection(cpi.index)
    common = common[common >= pd.Period(START, "M")]
    series = {"US used market (CPI)": cpi.reindex(common) / cpi.loc[common[0]]}
    for name, li in indices.items():
        series[name] = np.exp(smooth(li).reindex(common))
    tab = pd.DataFrame({name: measures(s) for name, s in series.items()}).T
    KEY = ("one-year move, p10 (%)", "largest fall from a peak (%)",
           "36-month expected shortfall, no change strike (% of residual)",
           "48-month expected shortfall, no change strike (% of residual)",
           "36-month expected shortfall, median strike (% of residual)",
           "48-month expected shortfall, median strike (% of residual)")   # X6 prices at the median strike
    ratio = {m: tab.loc["battery EVs", m] / tab.loc["US used market (CPI)", m] for m in KEY}
    # uncertainty: every measure, and its ratio to the market, recomputed on each bootstrap draw
    unc_rows = []
    for name in indices:
        ms = pd.DataFrame([measures(np.exp(smooth(b).reindex(common))) for b in draws[name]])
        row = {"series": name}
        for m in KEY:
            lo, hi = np.nanpercentile(ms[m], [5, 95])
            row[f"{m.split(' (')[0]}, 90% range"] = f"{lo:+.1f} to {hi:+.1f}"
            if name == "battery EVs":
                r = ms[m] / tab.loc["US used market (CPI)", m]
                ratio[m + " range"] = tuple(np.nanpercentile(r, [5, 95]))
        unc_rows.append(row)
    unc = pd.DataFrame(unc_rows)
    raw_p10 = {n: measures(np.exp(li.reindex(common)))["one-year move, p10 (%)"] for n, li in indices.items()}
    print(tab.round(2).to_string()); print(unc.to_string(index=False))

    # the path: yearly snapshots of each index
    path = pd.DataFrame({name: s for name, s in series.items()})
    snaps = path[path.index.month == 6]
    snaps.index = snaps.index.astype(str)

    # checks
    rows = []

    def check(name, passes, got):
        rows.append({"check": name, "got": got, "passes": bool(passes)})

    f = sets["battery EVs"].reset_index(drop=True).copy()
    late = (f["month"] >= pd.Period("2024-01", "M")).to_numpy()
    base = fit_index(f)
    f2 = f.assign(y=f["y"] + np.where(late, np.log(0.8), 0.0))
    moved = fit_index(f2)
    shift = (moved - base).loc[pd.Period("2025-06", "M")]
    check("a planted 20% fall in battery-EV prices from January 2024 is recovered exactly (log points, June 2025)",
          abs(shift - np.log(0.8)) < 1e-9, f"{100 * shift:+.2f} against {100 * np.log(0.8):+.2f}")
    check("the index is 1 in January 2017 by construction", abs(indices["battery EVs"].iloc[0]) < 1e-12, "1")
    check("the market series is X7's US CPI used cars (CUSR0000SETA02), same months", len(common) > 100,
          f"{len(common)} months, {common[0]} to {common[-1]}")
    moved = max(abs(raw_p10[n] - tab.loc[n, "one-year move, p10 (%)"]) for n in indices)
    check("smoothing does not drive the result: the three-month average moves no series' one-year p10 by more than "
          "one point", moved <= 1.0, "unsmoothed " + ", ".join(f"{n} {raw_p10[n]:+.1f}" for n in indices))
    ck = pd.DataFrame(rows)

    fmt = tab.copy()
    for c in fmt.columns:
        fmt[c] = fmt[c].map(lambda v: f"{v:,.0f}" if c.startswith("windows") else f"{v:+.1f}")
    fmt = fmt.reset_index().rename(columns={"index": "series"})
    unc.insert(1, "used sales", [f"{counts[n]:,}" for n in indices])
    heads = pd.DataFrame(
        [{"figure": f"{n}: one-year move, p10 (%)", "value": f"{tab.loc[n, 'one-year move, p10 (%)']:+.1f}"}
         for n in series]
        + [{"figure": f"{n}: largest fall from a peak (%)", "value": f"{tab.loc[n, 'largest fall from a peak (%)']:+.1f}"}
           for n in series]
        + [{"figure": f"{n}: 48-month expected shortfall, {k} strike (% of residual)",
            "value": f"{tab.loc[n, f'48-month expected shortfall, {k} strike (% of residual)']:.1f}"}
           for k in ("no change", "median") for n in series]
        + [{"figure": f"battery EVs against the market: {m.split(' (')[0]} (ratio)", "value": f"{ratio[m]:.2f}"}
           for m in KEY]
        + [{"figure": f"battery EVs against the market: {m.split(' (')[0]} (ratio), 90% range, {end}",
            "value": f"{ratio[m + ' range'][i]:.2f}"} for m in KEY for i, end in ((0, "low"), (1, "high"))])
    snap = snaps.map(lambda v: f"{v:.2f}").reset_index().rename(columns={"index": "June of"})
    lines = [
        "# X9 part 3: the used-EV level on a long realised series (US data)",
        "",
        "Generated by `analysis/ev_level_us.py`; the method is in its docstring. **US data**: Washington State title "
        "transfers, self-reported sale prices; the market is US CPI used cars and trucks. January 2017 = 1.",
        "",
        "## Headline",
        "",
        md_table(heads),
        "",
        "## The level, June of each year",
        "",
        md_table(snap),
        "",
        "## X6's measures, same months",
        "",
        md_table(fmt),
        "",
        "## Uncertainty: which models are in the index",
        "",
        "Model-cluster bootstrap (100 draws): each measure recomputed on each draw, 5th to 95th percentile. The EV "
        "level depends heavily on which models it holds (Tesla against the rest), so the ranges are wide; the market "
        "series is the official CPI and is held fixed.",
        "",
        md_table(unc),
        "",
        "## Checks",
        "",
        md_table(ck),
        "",
        "## Limits",
        "",
        "- **US, one state.** Washington's EV market, US incentives (the federal credit's rules changed in 2023 and it "
        "expired on 30 September 2025, as the group's 20-F notes) and Tesla's weight differ from Europe's. The ratio "
        "is a scale, not a European figure; part 2's Polish slump is the European evidence.",
        "- **Self-reported prices.** A title's price can understate a sale; the band drops dates written as prices.",
        "- **One EV cycle.** 2017-2026 holds one boom and one bust in used-EV prices; the tail measures rest on about "
        "nine independent years and overlapping windows, like X6's.",
        "- **Same model and age, not same battery.** Range and battery health are not in the record. A later EV of the "
        "same model and age usually has more range, so the index drifts up with quality (visible in 2017-20, when "
        "the market was flat): the EV falls measured here are, if anything, understated.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(heads.to_string(index=False))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
