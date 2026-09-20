"""What drives a car's value? Fit the same model in every dataset, then pool the results.

This follows METHODOLOGY_multi_dataset.md:
  stage 1  the same regression in each dataset separately, so no dataset's price level or
           currency contaminates another's
  stage 2  a random-effects meta-analysis across datasets, which gives one combined effect,
           a confidence range, and a measure of how much the effect really differs by market

The model is log price on age, mileage, fuel, gearbox, body and power, with make-and-model fixed
effects absorbed by demeaning inside each make-model group. Effects therefore compare cars of the
SAME model against each other, not a Fiat 500 against a Porsche.

Usage: .venv/bin/python analysis/drivers.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import md_table  # noqa: E402  (the project root is added above)

HERE = Path(__file__).parent
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
OUT = HERE / "drivers_report.md"
EFFECTS = HERE / "drivers_effects.csv"   # read by level_risk.py, one_car.py and value_engine.py

MIN_ROWS = 5_000        # a dataset needs this many usable rows to be its own "study"
MIN_GROUP = 20          # a make-model group needs this many rows to identify a within effect
MIN_SHARE = 0.02        # a dummy needs this share of rows in a dataset to be estimated there
LEASE_AGE = 3           # the age at which the with-mileage yearly loss is quoted
EUROPE = {"AT", "BE", "BG", "CH", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "GB", "HR", "HU",
          "IE", "IT", "LT", "LU", "LV", "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK"}

DRIVERS = {
    "age_years": "one more year of age",
    "log_mileage": "10% more mileage",
    "log_power": "10% more power (kW)",
    "fuel_diesel": "diesel instead of petrol",
    "fuel_electric": "electric instead of petrol",
    "fuel_hybrid": "hybrid instead of petrol",
    "fuel_plugin_hybrid": "plug-in hybrid instead of petrol",
    "transmission_automatic": "automatic instead of manual",
    "body_suv": "SUV instead of hatchback",
    "body_estate": "estate instead of hatchback",
    "body_sedan": "sedan instead of hatchback",
}


def sample():
    """Used cars with an advertised price and a believable age, mileage and price."""
    cols = ["source", "country", "price_type", "is_new", "make", "model", "age_years",
            "mileage_km", "power_kw", "fuel", "transmission", "body_type", "price_eur",
            "listing_date"]
    d = pd.read_parquet(LISTINGS, columns=cols)
    before = len(d)
    # is_new is unknown on most sources, and "unknown" must not mean "drop"
    d = d[d["price_type"].eq("asking") & ~d["is_new"].fillna(False).astype(bool)]
    d = d[d["age_years"].between(0.5, 30) & d["mileage_km"].between(1_000, 400_000)
          & d["price_eur"].between(500, 200_000)]
    print(f"sample: {len(d):,} of {before:,} rows "
          f"(asking prices, used, plausible age / mileage / price)")
    return d


def design(d, core=False):
    """Build y and X for one dataset.

    core=True keeps only the drivers that nearly every dataset records. The pooled model needs
    that: a row is dropped if any column in the matrix is missing, so including power or body
    type there would throw away every car from the sources that do not record them.
    """
    x = pd.DataFrame(index=d.index)
    x["age_years"] = d["age_years"].to_numpy(dtype=float)
    x["log_mileage"] = np.log(d["mileage_km"].to_numpy(dtype=float))
    if not core and d["power_kw"].notna().mean() > 0.5:
        power = d["power_kw"].to_numpy(dtype=float)
        x["log_power"] = np.log(np.where(power > 0, power, np.nan))
    columns = [("fuel", "petrol"), ("transmission", "manual")]
    if not core:
        columns.append(("body_type", "hatchback"))
    for col, base in columns:
        s = d[col].astype("string")
        if s.notna().mean() < 0.5 or (s == base).mean() < MIN_SHARE:
            continue
        prefix = "body" if col == "body_type" else col
        for value in s.dropna().unique():
            if value == base:
                continue
            name = f"{prefix}_{value}"
            if name in DRIVERS and (s == value).mean() >= MIN_SHARE:
                x[name] = (s == value).astype(float)
        x[f"_{col}_known"] = s.notna().astype(float)   # keeps unknown-category rows identified
    y = np.log(d["price_eur"].to_numpy(dtype=float))
    keep = x.notna().all(axis=1).to_numpy()
    return y[keep], x[keep], d[keep]


def absorb(y, X, groups):
    """Subtract each make-model group's mean, which absorbs a fixed effect per model."""
    g = pd.factorize(groups)[0]
    counts = np.bincount(g)
    big = counts[g] >= MIN_GROUP
    y, X, g = y[big], X[big], pd.factorize(g[big])[0]
    n_groups = g.max() + 1 if len(g) else 0
    mean_y = np.bincount(g, weights=y) / np.bincount(g)
    out = X - np.stack([np.bincount(g, weights=X[:, j]) / np.bincount(g) for j in range(X.shape[1])],
                       axis=1)[g]
    return y - mean_y[g], out, n_groups


def ols(y, X, n_groups):
    """OLS with heteroskedasticity-robust (HC1) standard errors."""
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta
    n, k = X.shape
    meat = (X * resid[:, None]).T @ (X * resid[:, None])
    dof = max(n - k - n_groups, 1)
    cov = XtX_inv @ meat @ XtX_inv * (n / dof)
    return beta, np.sqrt(np.diag(cov))


def fit_one(d):
    y, x, d = design(d)
    if len(y) < MIN_ROWS:
        return None
    names = [c for c in x.columns]
    y, X, n_groups = absorb(y, x.to_numpy(dtype=float),
                            (d["make"].astype(str) + "|" + d["model"].astype(str)))
    if len(y) < MIN_ROWS or n_groups < 10:
        return None
    # a column that is constant within every make-model group is all zeros after demeaning,
    # which would make the covariance matrix singular
    informative = X.std(axis=0) > 1e-8
    X, names = X[:, informative], [n for n, k in zip(names, informative) if k]
    beta, se = ols(y, X, n_groups)
    coef = {n: (b, e) for n, b, e in zip(names, beta, se)
            if not n.startswith("_") and np.isfinite(b) and np.isfinite(e) and e > 0}
    return {"n": len(y), "n_models": n_groups, "coef": coef} if coef else None


def meta(estimates):
    """DerSimonian-Laird random-effects pooling of one driver across datasets."""
    y = np.array([e[0] for e in estimates])
    v = np.array([e[1] ** 2 for e in estimates])
    k = len(y)
    if k == 1:
        return y[0], np.sqrt(v[0]), 0.0, np.nan
    w = 1 / v
    fixed = (w * y).sum() / w.sum()
    q = (w * (y - fixed) ** 2).sum()
    denom = w.sum() - (w ** 2).sum() / w.sum()
    tau2 = max(0.0, (q - (k - 1)) / denom) if denom > 0 else 0.0
    wr = 1 / (v + tau2)
    pooled = (wr * y).sum() / wr.sum()
    se = np.sqrt(1 / wr.sum())
    i2 = max(0.0, (q - (k - 1)) / q) * 100 if q > 0 else 0.0
    return pooled, se, i2, tau2


# Two-sided 97.5% points of Student's t, indexed by degrees of freedom. A prediction interval
# uses t rather than 1.96 because tau-squared is itself estimated from only a handful of datasets.
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
        9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 25: 2.060, 30: 2.042}


def prediction_interval(pooled, se, tau2, k):
    """Where the effect in a NEW market is expected to fall, not where the average sits.

    With datasets this large the confidence interval on the mean is almost meaningless: it
    shrinks toward a point while real differences between markets stay put. Riley, Higgins &
    Deeks (BMJ 2011;342:d549) recommend the prediction interval instead, which adds the
    between-market variance back in. This is the number the value engine actually needs, because
    it is asked about markets it has not seen.
    """
    df = k - 2
    if df < 1 or not np.isfinite(tau2):
        return np.nan, np.nan
    half = t975(df) * np.sqrt(tau2 + se ** 2)
    return pooled - half, pooled + half


def t975(df):
    return T975.get(df) or (2.042 if df > 30 else 2.131)


def effect(driver="age_years", scope="pooled"):
    """One effect from drivers.py's last run, on the log scale: estimate, pi_lo, pi_hi, t975,
    datasets. `scope` is "pooled" or a source name (per-source rows exist for the age effect)."""
    e = pd.read_csv(EFFECTS)
    return e[(e["driver"] == driver) & (e["scope"] == scope)].iloc[0].to_dict()


def pct(beta, driver):
    """Turn a log-price coefficient into a readable percentage."""
    if driver in ("log_mileage", "log_power"):
        return (1.10 ** beta - 1) * 100      # a 10% change in the driver
    return (np.exp(beta) - 1) * 100


def pooled_model(d, sources):
    """Stage 2b: one model across every dataset, borrowing strength between them.

    Fixed effects are source x make x model, so each dataset keeps its own price level and
    currency and only the shape of the effects is shared. This is the model the value engine
    would use, and it lets thin datasets lean on thick ones instead of being noisy alone.
    """
    d = d[d["source"].isin(sources)]
    y, x, d = design(d, core=True)
    names = list(x.columns)
    group = (d["source"].astype(str) + "|" + d["make"].astype(str) + "|" + d["model"].astype(str))
    y, X, n_groups = absorb(y, x.to_numpy(dtype=float), group)
    informative = X.std(axis=0) > 1e-8
    X, names = X[:, informative], [n for n, k in zip(names, informative) if k]
    beta, se = ols(y, X, n_groups)
    return {"n": len(y), "n_groups": n_groups,
            "coef": {n: (b, e) for n, b, e in zip(names, beta, se) if not n.startswith("_")}}


def shrunk(estimates, pooled, tau2):
    """Empirical-Bayes estimate per dataset: pulled toward the pooled mean by its own noise."""
    out = []
    for source, (b, e) in estimates:
        weight = tau2 / (tau2 + e ** 2) if (tau2 + e ** 2) > 0 else 0.0
        out.append((source, b, weight * b + (1 - weight) * pooled, weight))
    return out


def main():
    d = sample()
    fits = {}
    for source, part in d.groupby("source", observed=True):
        if len(part) < MIN_ROWS:
            continue
        fit = fit_one(part)
        if fit:
            fits[source] = fit
            print(f"  {source:22} n={fit['n']:>9,}  models={fit['n_models']:>5,}  "
                  f"drivers={len(fit['coef'])}")
    print(f"\nfitted {len(fits)} datasets")

    print("\nfitting the pooled model across all datasets")
    joint = pooled_model(d, list(fits))
    print(f"  pooled: n={joint['n']:,} rows, {joint['n_groups']:,} source-make-model groups")

    rows, per_source, shrink_rows, effects, published = [], [], [], {}, []
    for driver, label in DRIVERS.items():
        est = [(s, f["coef"][driver]) for s, f in fits.items() if driver in f["coef"]]
        if len(est) < 2:
            continue
        pooled, se, i2, tau2 = meta([e[1] for e in est])
        if driver == "age_years":
            shrink_rows = shrunk(est, pooled, tau2)
        lo, hi = pooled - 1.96 * se, pooled + 1.96 * se
        plo, phi = prediction_interval(pooled, se, tau2, len(est))
        published.append({"driver": driver, "scope": "pooled", "datasets": len(est), "estimate": pooled,
                          "pi_lo": plo, "pi_hi": phi, "t975": t975(len(est) - 2)})
        if driver == "age_years":
            published += [{"driver": driver, "scope": s, "datasets": 1, "estimate": b}
                          for s, (b, _) in est]
        effects[driver] = {"pooled": pooled, "lo": lo, "hi": hi, "plo": plo, "phi": phi,
                           "k": len(est), "all_negative": all(b < 0 for _, (b, _) in est),
                           "joint": joint["coef"][driver][0] if driver in joint["coef"] else None}
        rows.append({
            "driver": label,
            "datasets": len(est),
            "cars": f"{sum(fits[s]['n'] for s, _ in est):,}",
            "effect on price": f"{pct(pooled, driver):+.1f}%",
            "95% range": f"{pct(lo, driver):+.1f}% to {pct(hi, driver):+.1f}%",
            "95% prediction interval": ("" if not np.isfinite(plo) else
                                        f"{pct(plo, driver):+.1f}% to {pct(phi, driver):+.1f}%"),
            "differs by market (I²)": f"{i2:.0f}%",
            "pooled model": (f"{pct(joint['coef'][driver][0], driver):+.1f}%"
                             if driver in joint["coef"] else ""),
        })
        spread = sorted(((pct(b, driver), s) for s, (b, _) in est))
        per_source.append((label, spread))

    age_lo, age_hi = min(r[1] for r in shrink_rows), max(r[1] for r in shrink_rows)
    home = d.groupby("source", observed=True)["country"].agg(lambda c: c.mode().iloc[0])
    european = [r[1] for r in shrink_rows if home.get(r[0]) in EUROPE]
    europe_lo, europe_hi = pct(min(european), "age_years"), pct(max(european), "age_years")
    age, km = effects["age_years"], effects["log_mileage"]
    auto, diesel, ev = (effects["transmission_automatic"], effects["fuel_diesel"],
                        effects["fuel_electric"])
    diesel_spread = dict(per_source)[DRIVERS["fuel_diesel"]]
    # A year of age plus the extra mileage that year usually brings, for a car driven at a steady
    # rate: log mileage rises by log((a + 1) / a).
    step = km["pooled"] * np.log((LEASE_AGE + 1) / LEASE_AGE)
    mileage_year = float(np.expm1(step) * 100)
    with_mileage = float(np.expm1(age["pooled"] + step) * 100)
    report = ["# What drives a car's value", "",
              "Generated by `analysis/drivers.py`. Each dataset is fitted separately (stage 1), then the "
              "results are pooled with a random-effects meta-analysis (stage 2), following "
              "`METHODOLOGY_multi_dataset.md`.", "",
              f"**{len(fits)} datasets, {sum(f['n'] for f in fits.values()):,} used cars.** "
              "Effects are within make and model: a car is compared with the same model, not with a "
              "different one. Advertised prices only; sale and auction prices are analysed separately.", "",
              "## What to take from this", "",
              f"1. **A used car loses about {-pct(age['pooled'], 'age_years'):.0f}% of its value for "
              f"every year of age, with its mileage held fixed.** Pooled across {len(fits)} datasets "
              f"and {sum(f['n'] for f in fits.values()):,} cars; the single pooled model says "
              f"{-pct(age['joint'], 'age_years'):.1f}%. Every market tested falls between "
              f"{pct(age_lo, 'age_years'):.1f}% and {pct(age_hi, 'age_years'):.1f}% a year "
              f"({europe_lo:.1f}% to {europe_hi:.1f}% in the European datasets), so the rate is real "
              "everywhere but its size is a local number, not a global constant.",
              f"2. **A car that is also being driven loses more than that.** Mileage grows with age, "
              f"so a year older usually means more on the clock too. At {LEASE_AGE} years old a "
              f"further year of typical driving adds about {mileage_year:+.1f}% on the pooled "
              f"mileage effect, about {with_mileage:+.0f}% for the year in all. Quote the "
              f"{-pct(age['pooled'], 'age_years'):.0f}% as the age effect, not as what a lease car "
              "loses in a year.",
              f"3. **Mileage costs about {-pct(km['pooled'], 'log_mileage'):.1f}% per 10% more on the "
              f"clock**, holding age and model fixed"
              + (f". Negative in all {km['k']} datasets." if km["all_negative"] else "."),
              f"4. **An automatic gearbox is worth about {pct(auto['pooled'], 'transmission_automatic'):.0f}% "
              f"more than a manual** on the same model ({pct(auto['joint'], 'transmission_automatic'):+.0f}% "
              "in the pooled model), the largest single specification effect we can measure.",
              f"5. **Fuel type is not a reliable driver on its own.** Diesel comes out "
              f"{pct(diesel['pooled'], 'fuel_diesel'):+.1f}% pooled but "
              f"{pct(diesel['joint'], 'fuel_diesel'):+.1f}% in the pooled model, and the per-market "
              f"range runs from {diesel_spread[0][0]:+.1f}% to {diesel_spread[-1][0]:+.1f}%. Any claim "
              "about diesel or electric resale has to be made per market, not globally.", "",
              "## Pooled effects", "", md_table(pd.DataFrame(rows)), "",
              "**How to read this.** The *effect on price* column is the random-effects pooled estimate "
              "across datasets; the *pooled model* column is a single regression over all "
              f"{joint['n']:,} cars at once, with a fixed effect per source, make and model "
              f"({joint['n_groups']:,} groups), so each market keeps its own price level and only the "
              "shape of the effect is shared. It covers the drivers every dataset records (age, "
              "mileage, fuel, gearbox); power and body type are left to the per-dataset stage, because "
              "a pooled row is dropped if any column is missing and most sources record neither.", "",
              "**Read the prediction interval, not the 95% range.** The *95% range* is a "
              "confidence interval on the pooled average, and with millions of cars it collapses "
              "toward a point while the real differences between markets stay exactly where they "
              "were. The *95% prediction interval* adds the between-market variance back in and "
              "answers the question the value engine is actually asked: where would this effect "
              "fall in a market we have never seen? Riley, Higgins & Deeks (BMJ 2011;342:d549) "
              "recommend it for exactly this situation. The gap between the two columns is the "
              "honest measure of how much markets differ: age is "
              f"{pct(age['lo'], 'age_years'):.1f}% to {pct(age['hi'], 'age_years'):.1f}% on average but "
              f"{pct(age['plo'], 'age_years'):.1f}% to {pct(age['phi'], 'age_years'):.1f}% in a market "
              "we have not seen.", "",
              f"**The electric row is the one to look at twice.** {ev['k']} datasets, and a prediction "
              f"interval running from {pct(ev['plo'], 'fuel_electric'):.1f}% to "
              f"{pct(ev['phi'], 'fuel_electric'):+.1f}%. We cannot say what an electric car is worth "
              "against a petrol one in a market we have not measured. That is the same thing "
              "Stellantis reports in its own Form 20-F, that residual values for electrified "
              "vehicles carry greater uncertainty because historical resale data is limited - "
              "measured here from the other side.", "",
              "**I² is ~100% on almost every driver, and that is expected, not alarming.** With hundreds "
              "of thousands of cars per dataset the sampling error is tiny, so even a small genuine "
              "difference between markets dominates it. The honest reading is the per-dataset spread "
              "below, not the single pooled number.", "",
              "**Body type is the weakest row here.** Because a fixed effect per make and model is "
              "absorbed first, body type only varies within a single model name, so those coefficients "
              "are identified off unusual within-model variation and should not be read as "
              "\"SUVs are worth less\". The base is also wider than its label: every body type "
              "other than SUV, estate and sedan counts as hatchback. Age, mileage, power, gearbox "
              "and fuel all vary properly within a model and are the trustworthy rows.", "",
              "## Per-dataset spread", ""]
    for label, spread in per_source:
        lo_s, hi_s = spread[0], spread[-1]
        report.append(f"- **{label}:** {lo_s[0]:+.1f}% ({lo_s[1]}) to {hi_s[0]:+.1f}% ({hi_s[1]})")
    report += ["", "## Borrowing strength: each market's age effect, before and after pooling", "",
               "Empirical-Bayes shrinkage pulls each dataset's own estimate toward the pooled mean by "
               "how noisy that dataset is. A weight near 1 means the dataset is precise enough to stand "
               "on its own; a lower weight means it is leaning on the others.", "",
               "**Every weight here is about 1.000, so nothing is actually borrowed.** That is worth "
               "stating rather than hiding: these datasets are so large that each one pins down its own "
               "age effect precisely, and the differences between them are real differences between "
               "markets, not noise. Borrowing strength only starts to matter on thin slices - electric "
               "cars in a small market, a rare model, one model-year - which is exactly where the "
               "pooled model earns its keep and a per-market model would be unusable.", "",
               md_table(pd.DataFrame([
                   {"source": s, "own estimate": f"{pct(b, 'age_years'):+.1f}%",
                    "after borrowing": f"{pct(sb, 'age_years'):+.1f}%",
                    "weight on its own data": f"{w:.3f}"}
                   for s, b, sb, w in sorted(shrink_rows, key=lambda r: r[1])])), "",
               "## Datasets fitted", "",
               "*Not every dataset is European or a car: `bd_aiub`, `eg_hatla2ee` and "
               "`ma_mucars_2024` are Bangladesh, Egypt and Morocco, and `eu_commercial_2023` is vans "
               "and trucks. No US dataset enters this table.*", "",
               md_table(pd.DataFrame([{"source": s, "cars": f"{f['n']:,}",
                                       "make-model groups": f"{f['n_models']:,}",
                                       "drivers estimated": len(f["coef"])}
                                      for s, f in sorted(fits.items())])), ""]
    OUT.write_text("\n".join(report))
    pd.DataFrame(published).to_csv(EFFECTS, index=False)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
