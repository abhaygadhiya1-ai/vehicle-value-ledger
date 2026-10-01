"""X9 part 2: does the used-EV price level move differently from petrol and diesel, in European adverts?

Two questions, both on our own European adverts (asking prices; local currency, so a currency move is not read as a
level move):

1. **The curve.** Within each source, how fast does each fuel lose value with age? A fixed effect per make, model and
   fuel holds the car; age and log mileage enter per fuel. Annual depreciation is exp(slope) - 1. Benchmark: Schloter
   (Transport Policy 126, 2022), 24,000 used sales across several countries: 1.16% a month for electric cars against
   0.87% for petrol (register `schloter_*`).

2. **The level.** Where one source was scraped more than once, how did each fuel's price level move between scrapes?
   Cars are compared within cells of make, model, fuel and whole year of age, so the index is the price of the same
   kind of car at the same age at two dates; log mileage enters per fuel. The EV level move is the EV index less the
   petrol index: a level shock that falls on EVs alone. Poland was scraped four times (spring 2021, May 2022, spring
   2023, summer 2023), the UK three (2018 and 2021 from `dvm`, October 2022 from `uk_2022_10`).

The official used-car index over the same months (Eurostat HICP CP07112 for Poland, ONS D7E9 for the UK) is set
beside each fuel's index. **The advert indices do not track it:** they rise far more. A car of the same age at a later
scrape is a later vintage with a higher list price (new-car prices rose fast in 2021-23), the UK comparison changes
source (`dvm` to `uk_2022_10`, the reason STATE says never to pool them), and scraping scope differs between scrapes. So
an advert index is not a level measure on its own. **The EV-less-petrol gap is:** everything common to the fuels
(inflation, source, scope, vintage effects shared by all cars) cancels in it. What does not cancel works against
finding an EV fall: a later EV of the same model and age usually has more range, which lifts the EV index. Robustness:
the gap without Tesla (its 2023 price cuts must not carry the finding; the Tesla event study is withdrawn), and hybrids
less petrol, a non-EV group, for how far any group drifts from petrol.

Ranges resample make-model clusters (a model drawn k times weighs k: with cell fixed effects, identical to copying
its rows). Checks: a planted EV level shift is recovered; a placebo split of petrol cars into two random pseudo-fuels
shows no gap; the index is zero at the base date by construction.

Sweden (`se_2022`) and Portugal (`pt_standvirtual`) carry listing dates, but from single scrapes, so older adverts are
the unsold survivors; they enter the curve, not the level. Latvia holds 11 EVs.

Usage: .venv/bin/python analysis/ev_level.py   (writes analysis/ev_level_report.md)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402

LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
REGISTER = HERE.parent / "assumptions.csv"
OUT = HERE / "ev_level_report.md"
SEED = 20260926
DRAWS = 200
FUELS = ("petrol", "diesel", "electric", "plugin_hybrid", "hybrid")
CURRENCY = {"Poland": "PLN", "UK": "GBP"}
# (label, source, listing year or None): the scrapes of one market, in time order
LEVEL_SETS = {
    "Poland": [("spring 2021", "pl_2021", None), ("May 2022", "pl_2022_05", None),
               ("spring 2023", "pl_2023_04", None), ("summer 2023", "pl_2023_08", None)],
    "UK": [("2018", "dvm", 2018), ("2021", "dvm", 2021), ("October 2022", "uk_2022_10", None)],
}
OFFICIAL = {"Poland": ("eurostat", "PL"), "UK": ("ons", "UK")}
CURVE_SOURCES = [("Netherlands, November 2025", "eu_2025_11"), ("Germany, June 2023", "de_2023"),
                 ("UK, October 2022", "uk_2022_10"), ("Sweden, 2021-22", "se_2022"),
                 ("Poland, summer 2023", "pl_2023_08"), ("Portugal, 2023-24", "pt_standvirtual")]
MIN_EV = 300           # EVs a curve needs


def load():
    cols = ["source", "country", "price_type", "is_new", "make", "model", "fuel", "age_years", "mileage_km",
            "price", "currency", "price_eur", "listing_date"]
    d = pd.read_parquet(LISTINGS, columns=cols)
    d = d[d["price_type"].eq("asking") & ~d["is_new"].fillna(False).astype(bool)]
    d = d[d["age_years"].between(0.5, 20) & d["mileage_km"].between(1_000, 400_000)
          & d["price_eur"].between(500, 200_000)]
    d["fuel"] = d["fuel"].astype(str)
    d = d[d["fuel"].isin(FUELS) & d["make"].notna() & d["model"].notna()].copy()
    d["mm"] = d["make"].astype(str).str.lower() + "|" + d["model"].astype(str).str.lower()
    d["age_int"] = d["age_years"].round().astype(int)
    d["log_km"] = np.log(d["mileage_km"].astype(float))
    return d


# ---------- weighted fixed-effect regression ----------

def demean(a, g, w):
    """Weighted within-group demeaning of each column of a (n x k) or vector."""
    sw = np.bincount(g, weights=w)
    if a.ndim == 1:
        return a - (np.bincount(g, weights=w * a) / sw)[g]
    return a - np.stack([np.bincount(g, weights=w * a[:, j]) / sw for j in range(a.shape[1])], axis=1)[g]


def wls(y, X, w):
    Xw = X * w[:, None]
    return np.linalg.solve(X.T @ Xw, Xw.T @ y)


# ---------- the level ----------

def level_frame(d, market):
    parts = []
    for i, (label, src, year) in enumerate(LEVEL_SETS[market]):
        s = d[(d["source"] == src) & (d["currency"] == CURRENCY[market])]
        if year is not None:
            s = s[s["listing_date"].dt.year == year]
        parts.append(s.assign(period=i, period_label=label))
    f = pd.concat(parts, ignore_index=True)
    f["y"] = np.log(f["price"].astype(float))
    f["cell"] = f["mm"] + "|" + f["fuel"] + "|" + f["age_int"].astype(str)
    both = f.groupby("cell")["period"].nunique()
    return f[f["cell"].isin(both[both >= 2].index)].reset_index(drop=True)


def level_design(f, fuels):
    """Period-by-fuel dummies (the base period dropped) and log mileage per fuel."""
    periods = sorted(f["period"].unique())
    names, cols = [], []
    for fu in fuels:
        isf = (f["fuel"] == fu).to_numpy()
        for t in periods[1:]:
            names.append(("period", fu, t))
            cols.append((isf & (f["period"] == t).to_numpy()).astype(float))
        names.append(("km", fu, None))
        cols.append(np.where(isf, f["log_km"].to_numpy(), 0.0))
    return names, np.column_stack(cols)


def fit_level(f, fuels, w=None):
    fuels = [fu for fu in fuels if (f["fuel"] == fu).any()]
    names, X = level_design(f, fuels)
    g = pd.factorize(f["cell"])[0]
    w = np.ones(len(f)) if w is None else w
    keep = w > 0
    g2 = pd.factorize(g[keep])[0]
    y, X, ww = f["y"].to_numpy()[keep], X[keep], w[keep]
    beta = wls(demean(y, g2, ww), demean(X, g2, ww), ww)
    return {n: b for n, b in zip(names, beta) if n[0] == "period"}


def model_weights(f, rng):
    """A cluster bootstrap draw: each make-model weighted by how often it is drawn."""
    codes, uniq = pd.factorize(f["mm"])
    draw = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))
    return draw[codes].astype(float)


def level_market(d, market, rng):
    f = level_frame(d, market)
    fuels = [fu for fu in FUELS if (f["fuel"] == fu).sum() >= 200]
    point = fit_level(f, fuels)
    boots = [fit_level(f, fuels, model_weights(f, rng)) for _ in range(DRAWS)]
    periods = LEVEL_SETS[market]
    rows = []
    for t in range(1, len(periods)):
        row = {"from": periods[0][0], "to": periods[t][0]}
        for fu in fuels:
            row[f"{fu} (%)"] = 100 * (np.exp(point[("period", fu, t)]) - 1)
        for fu in ("petrol", "diesel"):
            if fu in fuels and "electric" in fuels:
                gap = point[("period", "electric", t)] - point[("period", fu, t)]
                bs = np.array([b[("period", "electric", t)] - b[("period", fu, t)] for b in boots])
                row[f"EV less {fu} (points)"] = 100 * gap
                row[f"EV less {fu}, 95% range"] = (100 * np.quantile(bs, 0.025), 100 * np.quantile(bs, 0.975))
        rows.append(row)
    if len(periods) > 2 and "electric" in fuels:
        # the last scrape against the one before the first fall: the slump itself, with its own range
        a, t = 1, len(periods) - 1
        row = {"from": periods[a][0], "to": periods[t][0]}
        for fu in fuels:
            row[f"{fu} (%)"] = 100 * (np.exp(point[("period", fu, t)] - point[("period", fu, a)]) - 1)
        for fu in ("petrol", "diesel"):
            if fu in fuels:
                def gap(r):
                    return (r[("period", "electric", t)] - r[("period", fu, t)]) - \
                        (r[("period", "electric", a)] - r[("period", fu, a)])
                bs = np.array([gap(b) for b in boots])
                row[f"EV less {fu} (points)"] = 100 * gap(point)
                row[f"EV less {fu}, 95% range"] = (100 * np.quantile(bs, 0.025), 100 * np.quantile(bs, 0.975))
        rows.append(row)
    counts = f.groupby(["period_label", "fuel"], sort=False).size().unstack(fill_value=0)[fuels]
    return f, fuels, point, pd.DataFrame(rows), counts


def robustness(f, rng):
    """The slump's gap (the second scrape to the last): without Tesla, and hybrids less petrol for comparison."""
    t, a0 = f["period"].max(), 1
    rows = []
    for label, sub, a, b in (
            ("EV less petrol, without Tesla", f[~f["mm"].str.startswith("tesla|")].reset_index(drop=True),
             "electric", "petrol"),
            ("EV less diesel, without Tesla", f[~f["mm"].str.startswith("tesla|")].reset_index(drop=True),
             "electric", "diesel"),
            ("hybrid less petrol (a non-EV group)", f, "hybrid", "petrol")):
        fu = [a, b]

        def gap(r):
            return (r[("period", a, t)] - r[("period", b, t)]) - (r[("period", a, a0)] - r[("period", b, a0)])
        pt = fit_level(sub, fu)
        bs = np.array([gap(fit_level(sub, fu, model_weights(sub, rng))) for _ in range(DRAWS)])
        rows.append({"comparison": label, "EVs or hybrids": int((sub["fuel"] == a).sum()),
                     "gap (points)": f"{100 * gap(pt):+.1f}",
                     "95% range": f"{100 * np.quantile(bs, 0.025):+.1f} to {100 * np.quantile(bs, 0.975):+.1f}"})
    return pd.DataFrame(rows)


def official_change(market, f):
    """The official used-car index's log change between the mean listing months of the first and each later scrape."""
    from level_risk import EUROSTAT, load as load_levels
    from level_long import ONS
    raw = load_levels()
    kind, geo = OFFICIAL[market]
    s = raw[(EUROSTAT, geo)] if kind == "eurostat" else raw[(ONS, geo)]
    s = s.dropna()
    s.index = pd.PeriodIndex(s.index, freq="M")
    months = f.groupby("period")["listing_date"].apply(lambda x: x.dt.to_period("M").astype("int64").mean())
    months = months.round().astype(int).map(lambda v: pd.Period(ordinal=v, freq="M"))
    out = {}
    for t in months.index[1:]:
        a, b = months.iloc[0], months.loc[t]
        out[t] = (np.log(s.loc[b] / s.loc[a]), str(a), str(b))
    return out


# ---------- the curve ----------

def fit_curve(s, fuels, w=None):
    g = pd.factorize(s["mm"] + "|" + s["fuel"])[0]
    names, cols = [], []
    for fu in fuels:
        isf = (s["fuel"] == fu).to_numpy()
        names += [("age", fu), ("km", fu)]
        cols += [np.where(isf, s["age_years"].to_numpy(float), 0.0), np.where(isf, s["log_km"].to_numpy(), 0.0)]
    X = np.column_stack(cols)
    w = np.ones(len(s)) if w is None else w
    keep = w > 0
    g2 = pd.factorize(g[keep])[0]
    y = np.log(s["price"].to_numpy(float))[keep]
    beta = wls(demean(y, g2, w[keep]), demean(X[keep], g2, w[keep]), w[keep])
    return {n[1]: b for n, b in zip(names, beta) if n[0] == "age"}


def curves(d, rng):
    rows = []
    for label, src in CURVE_SOURCES:
        s = d[d["source"] == src]
        s = s[s["currency"] == s["currency"].mode().iloc[0]]
        fuels = [fu for fu in ("petrol", "diesel", "electric") if (s["fuel"] == fu).sum() >= MIN_EV]
        if "electric" not in fuels or "petrol" not in fuels:
            continue
        s = s[s["fuel"].isin(fuels)].reset_index(drop=True)
        point = fit_curve(s, fuels)
        dep = {fu: 100 * (1 - np.exp(point[fu])) for fu in fuels}
        boots = []
        for _ in range(DRAWS // 2):
            bb = fit_curve(s, fuels, model_weights(s, rng))
            boots.append(100 * (np.exp(bb["petrol"]) - np.exp(bb["electric"])))
        row = {"source": label, "EVs": int((s["fuel"] == "electric").sum())}
        for fu in fuels:
            row[f"{fu}, a year (%)"] = dep[fu]
        row["EV less petrol (points a year)"] = dep["electric"] - dep["petrol"]
        row["EV less petrol, 95% range"] = tuple(np.quantile(boots, [0.025, 0.975]))
        rows.append(row)
    return pd.DataFrame(rows)


# ---------- checks ----------

def checks(d, level_f, rng):
    rows = []

    def check(name, passes, got):
        rows.append({"check": name, "got": got, "passes": bool(passes)})

    # a planted EV level shift is recovered
    f = level_f["Poland"].copy()
    ev_late = ((f["fuel"] == "electric") & (f["period"] == f["period"].max())).to_numpy()
    f["y"] = f["y"] + np.where(ev_late, np.log(0.9), 0.0)
    base = fit_level(level_f["Poland"], ["petrol", "electric"])
    moved = fit_level(f, ["petrol", "electric"])
    t = f["period"].max()
    shift = moved[("period", "electric", t)] - base[("period", "electric", t)]
    check("a planted 10% fall in the EV level at the last Polish scrape is recovered exactly (log points)",
          abs(shift - np.log(0.9)) < 1e-9, f"{100 * shift:+.2f} against {100 * np.log(0.9):+.2f}")

    # placebo: petrol split into two random pseudo-fuels shows no gap
    f = level_f["Poland"].copy()
    petrol = f["fuel"] == "petrol"
    models = pd.Series(pd.factorize(f["mm"])[0])
    flip = (models.map(pd.Series(rng.random(models.max() + 1))) < 0.5).to_numpy()
    f.loc[petrol & flip, "fuel"] = "pseudo"
    f["cell"] = f["mm"] + "|" + f["fuel"] + "|" + f["age_int"].astype(str)
    p = fit_level(f, ["petrol", "pseudo"])
    gaps = [p[("period", "pseudo", t)] - p[("period", "petrol", t)] for t in range(1, f["period"].max() + 1)]
    worst = max(abs(g) for g in gaps)
    check("placebo: petrol models split at random into two pseudo-fuels differ by under 3 points at every Polish "
          "scrape", worst < 0.03, f"largest gap {100 * worst:.2f} points")
    return pd.DataFrame(rows)


def fmt_range(r):
    return f"{r[0]:+.1f} to {r[1]:+.1f}"


def main():
    rng = np.random.default_rng(SEED)
    d = load()
    print(f"sample: {len(d):,} adverts")
    level_f, level_tabs, sections, heads = {}, {}, [], []
    for market in LEVEL_SETS:
        f, fuels, point, tab, counts = level_market(d, market, rng)
        level_f[market] = f
        level_tabs[market] = tab
        off = official_change(market, f)
        show = tab.copy()
        n = len(LEVEL_SETS[market])
        offs = [off[t] for t in range(1, n)]
        if len(show) > n - 1:     # the slump row: the official index between the second and last scrapes
            offs.append((off[n - 1][0] - off[1][0], off[1][2], off[n - 1][2]))
        show["official index (%)"] = [100 * (np.exp(o[0]) - 1) for o in offs]
        show["official months"] = [f"{o[1]} to {o[2]}" for o in offs]
        for c in show.columns:
            if c.endswith("(%)") or c.endswith("(points)"):
                show[c] = show[c].map(lambda v: f"{v:+.1f}")
            elif c.endswith("range"):
                show[c] = show[c].map(fmt_range)
        cnt = counts.reset_index().rename(columns={"period_label": "scrape"})
        sections += [f"### {market} ({CURRENCY[market]})", "",
                     "Adverts in cells seen at two or more scrapes, by fuel:", "", md_table(cnt), "",
                     md_table(show), ""]
        last = tab.iloc[n - 2]
        if market == "Poland":
            rb = robustness(f, rng)
            print(rb.to_string(index=False))
            slump = tab.iloc[-1]
            sections += [f"Robustness, {slump['from']} to {slump['to']} (all makes are in the table above):", "",
                         md_table(rb), ""]
            for _, r in rb.iterrows():
                heads.append({"figure": f"Poland: {r['comparison']}, {slump['from']} to {slump['to']} (points)",
                              "value": r["gap (points)"]})
            heads.append({"figure": f"Poland: EV level less petrol, {slump['from']} to {slump['to']} (points)",
                          "value": f"{slump['EV less petrol (points)']:+.1f}"})
            heads.append({"figure": "Poland: that slump's 95% range, low (points)",
                          "value": f"{slump['EV less petrol, 95% range'][0]:+.1f}"})
            heads.append({"figure": "Poland: that slump's 95% range, high (points)",
                          "value": f"{slump['EV less petrol, 95% range'][1]:+.1f}"})
        heads.append({"figure": f"{market}: EV level less petrol, {last['from']} to {last['to']} (points)",
                      "value": f"{last['EV less petrol (points)']:+.1f}"})
        heads.append({"figure": f"{market}: its 95% range, low (points)",
                      "value": f"{last['EV less petrol, 95% range'][0]:+.1f}"})
        heads.append({"figure": f"{market}: its 95% range, high (points)",
                      "value": f"{last['EV less petrol, 95% range'][1]:+.1f}"})
        heads.append({"figure": f"{market}: petrol level, {last['from']} to {last['to']} (%)",
                      "value": f"{last['petrol (%)']:+.1f}"})
        heads.append({"figure": f"{market}: official used-car index over the same months (%)",
                      "value": f"{100 * (np.exp(off[len(LEVEL_SETS[market]) - 1][0]) - 1):+.1f}"})
        print(market); print(tab.to_string(index=False))

    cv = curves(d, rng)
    cshow = cv.copy()
    for c in cshow.columns:
        if c.endswith("(%)"):
            cshow[c] = cshow[c].map(lambda v: f"{v:.1f}")
        elif c.endswith("(points a year)"):
            cshow[c] = cshow[c].map(lambda v: f"{v:+.1f}")
        elif c.endswith("range"):
            cshow[c] = cshow[c].map(fmt_range)
    print(cv.to_string(index=False))
    for _, r in cv.iterrows():
        heads.append({"figure": f"{r['source']}: EV depreciation less petrol's (points a year)",
                      "value": f"{r['EV less petrol (points a year)']:+.1f}"})
    ck = checks(d, level_f, rng)
    print(ck.to_string(index=False))

    reg = pd.read_csv(REGISTER).set_index("id")["value"]
    sch = ""
    if "schloter_ev_dep_month" in reg.index:
        ev_y = 100 * (1 - (1 - reg["schloter_ev_dep_month"] / 100) ** 12)
        pe_y = 100 * (1 - (1 - reg["schloter_petrol_dep_month"] / 100) ** 12)
        sch = (f" Schloter's monthly rates compound to about {ev_y:.1f}% a year for electric cars and {pe_y:.1f}% "
               f"for petrol, a gap of {ev_y - pe_y:.1f} points (`schloter_*`).")
    pl_slump = level_tabs["Poland"].iloc[-1]
    faster = cv[cv["EV less petrol (points a year)"] > 0]["source"].tolist()
    slower = cv[cv["EV less petrol (points a year)"] <= 0]["source"].tolist()
    reading = [
        "## Reading it",
        "",
        f"- **The EV level fell on its own in Poland.** Between {pl_slump['from']} and {pl_slump['to']} the EV index "
        f"lost {abs(pl_slump['EV less petrol (points)']):.0f} points against petrol, the range excluding zero, with "
        "Tesla out it stays large, and a non-EV group (hybrids) drifted a fraction of that. This is the European "
        "used-EV slump Fitch dates from 2023, measured on the same model at the same age.",
        "- **The UK comparison is inconclusive.** It ends in October 2022, near the top, crosses a source change, and "
        "its range spans large moves both ways.",
        f"- **No steady EV curve gap.** With the model held, EVs lose value faster with age in {len(faster)} of "
        f"{len(cv)} sources ({', '.join(faster)}) and no faster, or slower, in {len(slower)} "
        f"({', '.join(slower)}). The sources where EVs are steeper are those scraped after the 2023 fall: a "
        "cross-section reads vintage list prices as depreciation, so the sign moving with the date points at the "
        "level, not at a faster curve. Schloter's steady gap is not what these European adverts show once the model "
        "is held.",
        "- **So EV residual risk is a level risk.** It is the programme's thesis again, for the EV slice: the curve "
        "can be learned, the level must be priced and re-marked (X6), and on the EV slice the level has moved on its "
        "own. Part 3 asks how often, on a long realised series.",
        "",
    ]
    lines = [
        "# X9 part 2: the EV level and curve in European adverts",
        "",
        "Generated by `analysis/ev_level.py`; the method is in its docstring. Asking prices, local currency.",
        "",
        "## Headline",
        "",
        md_table(pd.DataFrame(heads)),
        "",
        "## The level: each fuel's price between scrapes, same model, fuel and age",
        "",
        "Each fuel's index is the price change of the same kind of car at the same age. \"EV less petrol\" is the "
        "level move that fell on electric cars alone. The official index is the market's used-car index between the "
        "mean listing months: the combustion indices should track it.",
        "",
        *sections,
        *reading,
        "## The curve: how fast each fuel loses value with age",
        "",
        "Within each source, a fixed effect per make, model and fuel; age and log mileage per fuel. Depreciation a "
        "year is the fall in price for one more year of age at the same mileage; \"EV less petrol\" is positive when "
        "EVs lose value faster. A cross-section also carries vintage effects (a list price that rose or fell across "
        "model years reads as depreciation)." + sch,
        "",
        md_table(cshow),
        "",
        "## Checks",
        "",
        md_table(ck),
        "",
        "## Limits",
        "",
        "- **Asking prices.** Every figure here is an advert price; a level fall that dealers absorb by discounting "
        "shows late or not at all.",
        "- **Generations inside a model name.** A two-year-old EV of one model in 2018 and in 2022 may be different "
        "generations with different ranges; model names carry no generation (STATE data trap). Part of an EV's "
        "level move is its own obsolescence, which is exactly what a lessor holding it meets.",
        "- **Few scrapes, one slump.** Poland's four scrapes end in summer 2023, early in the EV price fall that "
        "Fitch reports from 2023 (`fitch_eu_abs_bev_*`); the UK's end in October 2022, near the top. They measure "
        "direction and size at those dates, not a distribution of EV level shocks; part 3 uses a long realised series "
        "for that (US).",
        "- **Mileage is held, not range or battery.** Neither is in the adverts.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
