"""Does the value engine's answer hold up against cars it has not seen?

Four checks, all on data already in the repo:

  1. **Held-out UK cars.** Half of the recent UK listings set the engine's levels and shape; the
     other half are priced and compared with their advertised price. How often does the 80% band
     contain the real price, and does the value lean one way at some ages? Run twice: the engine
     as built, which takes each model's level and scatter from cars within a year of the car's
     age, and the same engine taking them from every age.
  2. **Other markets.** For the three most-listed models in five more markets, the engine's value
     for a three-year-old car against the median of matching local cars.
  3. **Thin slices.** Held-out UK cars of rarely listed models, and a market with few cars of its
     own (Austria, from the multi-country AutoScout24 set), where the shape leans on other markets.
  4. **Three years out, in Latvia.** The one market with five years of monthly data. The engine is
     run as of mid-2020 and end-2020, prices cars three years ahead, and is compared with what
     matching Latvian adverts actually asked three years later.

Usage: .venv/bin/python analysis/engine_check.py
"""
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import value_engine as ve  # noqa: E402
from build_unified import md_table  # noqa: E402

OUT = Path(__file__).parent / "engine_check_report.md"
MARKET = "GB"
SAMPLE = 3_000
OTHER_MARKETS = ["DE", "FR", "PL", "PT", "SE"]
THIN_MARKET = "AT"
THIN_BANDS = [(10, 100), (100, 250), (250, None)]   # training-half cars of that make and model
BACKTEST = [("2020-06-01", "2023-06-01"), ("2020-12-01", "2023-12-01")]
LATVIA_MONTHLY = Path(__file__).parent / "latvia_monthly.csv"
AGE_BANDS = [0, 2, 4, 7, 12, 30]
EVERY_AGE = 100.0      # a neighbour window wide enough to take in every age


def held_out(engine, test, neighbours):
    ve.AGE_NEIGHBOURS = neighbours
    rows = []
    for _, c in test.iterrows():
        r = engine.predict(c["make"], c["model"], float(c["age_years"]),
                           mileage=float(c["mileage_km"]), fuel=c["fuel"],
                           gearbox=c["transmission"], body=c["body_type"])
        rows.append({"age": c["age_years"], "price": c["price_eur"], "value": r["value_eur"],
                     "low": r["low_eur"], "high": r["high_eur"],
                     "local": r["shape_weight_on_local"]})
    t = pd.DataFrame(rows)
    t["covered"] = t["price"].between(t["low"], t["high"])
    t["log_err"] = np.log(t["price"] / t["value"])
    t["band"] = pd.cut(t["age"], AGE_BANDS).astype(str).str.replace(", ", " to ")
    return t


def split_half(engine, label):
    """Half of the engine's local cars set levels and shape; the other half are priced."""
    full = engine.local
    order = np.random.default_rng(zlib.crc32(label.encode())).permutation(len(full))
    train, test = full.iloc[order[: len(full) // 2]], full.iloc[order[len(full) // 2:]]
    engine.local = train
    counts = train.groupby(["make", "model"], observed=True).size()
    test = test.dropna(subset=["fuel", "transmission", "body_type"])
    n = pd.MultiIndex.from_frame(test[["make", "model"]]).map(counts).fillna(0)
    return full, train, test.assign(_n=np.asarray(n, float))


def summarise(t, label):
    return {"slice": label, "held-out cars": len(t),
            "coverage": f"{t['covered'].mean():.0%}",
            "median lean": f"{np.expm1(t['log_err'].median()) * 100:+.1f}%",
            "typical error": f"{np.expm1(t['log_err'].abs().median()) * 100:.1f}%",
            "shape from local cars": f"{t['local'].mean():.0%}"}


def backtest(origin, target, monthly):
    """Price one month's cars three years ahead as of `origin`; compare with adverts at `target`."""
    engine = ve.ValueEngine("LV", verbose=False, as_of=origin)
    loc = engine.local
    counts = loc.groupby(["make", "model"], observed=True).size()
    cars = loc[loc["listing_date"].eq(pd.Timestamp(origin))].dropna(
        subset=["fuel", "transmission", "body_type"])
    cars = cars[pd.MultiIndex.from_frame(cars[["make", "model"]]).isin(counts[counts >= 30].index)]
    cars = cars[cars["age_years"].between(1, 12)].sample(min(SAMPLE // 3, len(cars)), random_state=0)
    later = ve.load()
    later = later[later["source"].eq("lv_ss") & later["listing_date"].eq(pd.Timestamp(target))]
    groups = {k: g for k, g in later.groupby(["make", "model", "fuel", "transmission",
                                               "body_type", "age_years"], observed=True)}
    rows = []
    for _, c in cars.iterrows():
        r = engine.predict(c["make"], c["model"], float(c["age_years"]), horizon_years=3,
                           mileage=float(c["mileage_km"]), fuel=c["fuel"],
                           gearbox=c["transmission"], body=c["body_type"])
        g = groups.get((c["make"], c["model"], c["fuel"], c["transmission"], c["body_type"],
                        c["age_years"] + 3))
        if g is None:
            continue
        km = r["mileage_at_valuation_km"]
        g = g[g["mileage_km"].between(km * 0.75, km * 1.25)]
        if len(g) < 5:
            continue
        prices = g["price_eur"].to_numpy(float)
        rows.append({"inside": float(np.mean((prices >= r["low_eur"]) & (prices <= r["high_eur"]))),
                     "above": float(np.mean(prices > r["high_eur"])),
                     "ratio": float(np.median(prices) / r["value_eur"])})
    t = pd.DataFrame(rows)
    ours = monthly.set_index("month")["our_index"]
    official = monthly.set_index("month")["eurostat_index"]
    o, g = origin[:7], target[:7]
    return {"priced as of": o, "compared at": g, "cars priced": len(cars),
            "with 5+ matching adverts later": len(t),
            "adverts inside the 80% band": f"{t['inside'].mean():.0%}",
            "adverts above it": f"{t['above'].mean():.0%}",
            "actual / forecast (median)": f"{(t['ratio'].median() - 1) * 100:+.0f}%",
            "our Latvian index over the same months": f"{(ours[g] / ours[o] - 1) * 100:+.0f}%",
            "Eurostat Latvian index": f"{(official[g] / official[o] - 1) * 100:+.0f}%",
            "_ratio": t["ratio"].median(), "_ours": ours[g] / ours[o],
            "_official": official[g] / official[o], "_inside": t["inside"].mean(),
            "_above": t["above"].mean()}


def main():
    engine = ve.ValueEngine(MARKET, verbose=False)
    full = engine.local
    order = np.random.default_rng(zlib.crc32(b"engine-check")).permutation(len(full))
    train, test = full.iloc[order[: len(full) // 2]], full.iloc[order[len(full) // 2:]]
    engine.local = train
    counts = train.groupby(["make", "model"], observed=True).size()
    enough = pd.MultiIndex.from_frame(test[["make", "model"]]).isin(counts[counts >= 30].index)
    test_all = test.dropna(subset=["fuel", "transmission", "body_type"])
    test_all = test_all.assign(_n=np.asarray(
        pd.MultiIndex.from_frame(test_all[["make", "model"]]).map(counts).fillna(0), float))
    test = test[enough].dropna(subset=["fuel", "transmission", "body_type"])
    test = test.sample(SAMPLE, random_state=0)

    built = held_out(engine, test, ve.AGE_NEIGHBOURS if ve.AGE_NEIGHBOURS < EVERY_AGE else 1.0)
    every = held_out(engine, test, EVERY_AGE)
    ve.AGE_NEIGHBOURS = 1.0

    by_age = pd.DataFrame({
        "car age, years": built.groupby("band", sort=False).size().index,
        "held-out cars": built.groupby("band", sort=False).size().to_numpy(),
        "coverage, every age": every.groupby("band", sort=False)["covered"].mean().to_numpy(),
        "coverage, as built": built.groupby("band", sort=False)["covered"].mean().to_numpy(),
        "median lean, every age": every.groupby("band", sort=False)["log_err"].median().to_numpy(),
        "median lean, as built": built.groupby("band", sort=False)["log_err"].median().to_numpy(),
    })
    order_bands = [str(b).replace(", ", " to ") for b in pd.cut([1], AGE_BANDS).categories]
    by_age = by_age.set_index("car age, years").loc[order_bands].reset_index()
    for c in ("coverage, every age", "coverage, as built"):
        by_age[c] = (by_age[c] * 100).map("{:.0f}%".format)
    for c in ("median lean, every age", "median lean, as built"):
        by_age[c] = (np.expm1(by_age[c]) * 100).map("{:+.1f}%".format)

    cov_every = every.groupby("band")["covered"].mean()
    cov_built = built.groupby("band")["covered"].mean()
    lean_every = np.expm1(every.groupby("band")["log_err"].median())
    lean_built = np.expm1(built.groupby("band")["log_err"].median())
    abs_every = float(np.expm1(every["log_err"].abs().median()) * 100)
    abs_built = float(np.expm1(built["log_err"].abs().median()) * 100)

    spots = []
    for market in OTHER_MARKETS:
        e = ve.ValueEngine(market, verbose=False)
        loc = e.local.dropna(subset=["fuel", "transmission"])
        top = loc.groupby(["make", "model"], observed=True).size().sort_values(ascending=False)
        for (make, model), _ in top.head(3).items():
            m = loc[(loc["make"] == make) & (loc["model"] == model)
                    & loc["age_years"].between(2.5, 3.5)]
            if len(m) < 30:
                continue
            fuel, gear = m["fuel"].mode()[0], m["transmission"].mode()[0]
            m = m[(m["fuel"] == fuel) & (m["transmission"] == gear)]
            km = float(m["mileage_km"].median())
            like = m[m["mileage_km"].between(km * 0.75, km * 1.25)]
            r = e.predict(make, model, float(m["age_years"].median()), mileage=km, fuel=fuel,
                          gearbox=gear)
            actual = float(like["price_eur"].median())
            spots.append({"market": market, "car": f"{make} {model}, {fuel}, {gear}",
                          "km": f"{km:,.0f}", "matching cars": len(like),
                          "engine": f"{r['value_eur']:,.0f}",
                          "80% band": f"{r['low_eur']:,.0f} - {r['high_eur']:,.0f}",
                          "actual median": f"{actual:,.0f}",
                          "engine / actual": f"{r['value_eur'] / actual:.2f}",
                          "_inside": r["low_eur"] <= actual <= r["high_eur"],
                          "_ratio": r["value_eur"] / actual})
    spot = pd.DataFrame(spots)
    inside = int(spot["_inside"].sum())
    ratios = spot["_ratio"]

    thin_rows = []
    for lo, hi in THIN_BANDS:
        pool = test_all[(test_all["_n"] >= lo) & ((test_all["_n"] < hi) if hi else True)]
        t = held_out(engine, pool.sample(min(SAMPLE // 3, len(pool)), random_state=0), 1.0)
        thin_rows.append(summarise(t, f"{MARKET} models with {lo}-{hi - 1} cars" if hi
                                   else f"{MARKET} models with {lo}+ cars"))
    small = ve.ValueEngine(THIN_MARKET, verbose=False)
    small_full, _, small_test = split_half(small, "engine-check-thin")
    small_test = small_test[small_test["_n"] >= 10]
    t = held_out(small, small_test.sample(min(SAMPLE // 3, len(small_test)), random_state=0), 1.0)
    thin_rows.append(summarise(t, f"{THIN_MARKET}, a market with {len(small_full):,} recent cars"))
    ve.AGE_NEIGHBOURS = 1.0
    thin = pd.DataFrame(thin_rows)

    monthly = pd.read_csv(LATVIA_MONTHLY)
    back = pd.DataFrame([backtest(o, g, monthly) for o, g in BACKTEST])

    report = [
        "# Does the value engine hold up against cars it has not seen?", "",
        "Generated by `analysis/engine_check.py`. No new data source.", "",
        f"## 1. Held-out {MARKET} cars", "",
        f"Half of the {len(full):,} recent {MARKET} listings set the engine's levels and shape; "
        f"{len(test):,} cars drawn from the other half are priced with their own age, mileage, "
        "fuel, gearbox and body and compared with their advertised price. *Every age* takes each "
        "model's level and scatter from all its cars; *as built* takes them from cars within a "
        "year of the car's age. *Coverage* is the share of cars whose price falls inside the 80% "
        "band, so 80% is right. *Median lean* is how far real prices sit above (+) or below (-) the "
        "engine's value.", "",
        md_table(by_age), "",
        f"- **Overall coverage: {every['covered'].mean():.0%} taking every age, "
        f"{built['covered'].mean():.0%} as built.** Both are right on average.",
        f"- **By age:** coverage runs {cov_every.min():.0%} to {cov_every.max():.0%} taking every age - "
        f"too wide for young cars, too narrow for old ones, because old cars scatter much more - "
        f"and {cov_built.min():.0%} to {cov_built.max():.0%} as built.",
        f"- **The lean with age shrinks.** A straight-line age curve cannot follow the real one "
        f"everywhere. Taking one level over every age, real prices sit between "
        f"{lean_every.min():+.1%} and {lean_every.max():+.1%} of the engine's value across the age "
        f"bands; taking it from cars of about the same age, between {lean_built.min():+.1%} and "
        f"{lean_built.max():+.1%}.",
        f"- **Typical error, as built: {abs_built:.1f}%** (median absolute difference between the "
        "advertised price and the engine's value). This is the per-car figure the value-at-risk "
        "model contrasts with a market-level move, so it is kept on a line of its own.",
        f"- Taking every age instead of cars of about the same age, it is {abs_every:.1f}%.", "",
        "## 2. Other markets, a three-year-old car", "",
        "The three most-listed models in each market, at their most common fuel and gearbox and "
        "median mileage, against the median of local cars within 25% of that mileage.", "",
        md_table(spot.drop(columns=["_inside", "_ratio"])), "",
        f"- **The engine lands between {ratios.min():.2f} and {ratios.max():.2f} of the actual "
        f"median, and the median is inside the 80% band in {inside} of {len(spot)} cases.**",
        "- The worst misses are where one model name covers very different cars - a body style, "
        "a performance version or a new generation that the data does not separate.", "",
        "## 3. Thin slices", "",
        f"The same held-out test on rarely listed {MARKET} models, grouped by how many cars of that "
        f"model sit in the training half, and on {THIN_MARKET}, whose recent cars all come from "
        "one multi-country dataset. *Shape from local cars* is the average weight the engine put "
        "on the market's own slopes rather than other markets'.", "",
        md_table(thin), "",
        "## 4. Three years out, in Latvia", "",
        "The engine is run as it would have been on the pricing date - listings, other datasets and "
        "index history up to then - and prices that month's Latvian adverts three years ahead, at "
        "the market level of the pricing date. Three years later, each forecast is compared with "
        "the Latvian adverts for the same model, age, fuel, gearbox and body within 25% of the "
        "projected mileage.", "",
        md_table(back.drop(columns=[c for c in back.columns if c.startswith("_")])), "",
        f"- **The level broke the band.** Three years later, matching adverts asked "
        f"{(back['_ratio'].median() - 1) * 100:.0f}% more than the forecast (median of the two "
        f"windows), and only {back['_inside'].mean():.0%} of them sat inside the 80% band, with "
        f"{back['_above'].mean():.0%} above it. Our own Latvian index rose "
        f"{(back['_ours'].median() - 1) * 100:+.0f}% over the same months; dividing that move out "
        f"leaves a gap of {(back['_ratio'].median() / back['_ours'].median() - 1) * 100:+.0f}%, so "
        "most of the miss is the market level, not the car or the curve. That index is built from "
        "the same adverts, so this is a consistency check rather than independent proof.",
        "- **The official index does not explain it.** Eurostat's Latvian index rose only "
        + " and ".join(f"{(v - 1) * 100:+.0f}%" for v in back["_official"])
        + " over the two windows. That is the disagreement `latvia_time_report.md` already found, "
        "and the reason the value-at-risk model treats shocks measured from official indices as a "
        "floor.",
        "- **The engine meeting its limit, honestly.** It prices one car at the pricing date's level, "
        "and its level band drew on the core markets' history before mid-2020, which held nothing "
        "like the 2021-22 surge. A move on that scale cannot be forecast from car data. It is what "
        "the level shock on the whole book and a monthly re-anchor exist for.", "",
        "## Limits", "",
        "- **Advertised prices on both sides.** This checks the engine against asking prices, the "
        "same thing it was built from.",
        f"- **The {MARKET} snapshot records the registration year only**, so ages are whole years "
        "and the neighbour window takes three cohorts.",
        "- **Model names carry no generation.** A model changed inside the window moves the level. "
        "The sixth-generation Vauxhall Corsa launched in late 2019 "
        "([Wikipedia](https://en.wikipedia.org/wiki/Opel_Corsa), [Auto Express]"
        "(https://www.autoexpress.co.uk/vauxhall/corsa/108403/new-vauxhall-corsa-2019-review)), "
        "so in the October 2022 snapshot the two-year-olds are mostly the new car and the "
        "three-year-olds mostly the old one, and a three-year-old Corsa's level is pulled up by its "
        "younger neighbours.",
        "- **The Latvian backtest is one market over two overlapping windows**, and the matching "
        "adverts three years later are other cars of the same model, age, fuel, gearbox, body and "
        "similar mileage, not the same cars. Its shape could lean on only one other dataset "
        "before mid-2020, and its level band on index history up to the pricing date.", ""]
    OUT.write_text("\n".join(report))
    print(by_age.to_string(index=False))
    print(thin.to_string(index=False))
    print(back.drop(columns=[c for c in back.columns if c.startswith("_")]).to_string(index=False))
    print(f"typical error {abs_every:.1f}% -> {abs_built:.1f}%; other markets "
          f"{ratios.min():.2f}-{ratios.max():.2f}, {inside} of {len(spot)} inside the band")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
