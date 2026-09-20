"""One real car, end to end: a Vauxhall Corsa in the United Kingdom.

Vauxhall is one of the merged group's own brands and the Corsa is its highest-volume UK model, so
this is the case's own product rather than an illustration. Two snapshots of it exist in the
collection and they are four years apart:

  * **2018** - the DVM-CAR adverts listed in 2018; the set also carries a new list price per model year
  * **October 2022** - the UK scrape, after the 2021-22 used-car price surge

That gap is a natural test of the claim the rest of this project keeps arriving at. A value model
fitted on the 2018 Corsas is asked to price the 2022 ones. If the **shape** of depreciation travels
and only the **level** moves, then the 2018 model should get the ordering and the slopes right and
the level wrong - and re-anchoring the level on a handful of current cars should fix most of it.

The level shift the Corsa data implies is then checked against the ONS second-hand car index, which
is an independent measurement of the same thing.

Usage: .venv/bin/python analysis/one_car.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import md_table  # noqa: E402

HERE = Path(__file__).parent
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
RETAINED = HERE.parent / "data" / "unified" / "value_retained.parquet"
INDICES = HERE.parent / "data" / "reference" / "price_indices.parquet"
OUT = HERE / "one_car_report.md"

MAKE, MODEL, COUNTRY = "vauxhall", "corsa", "GB"
TRAIN_SOURCE, TEST_SOURCE = "dvm", "uk_2022_10"
ANCHOR_SIZES = (25, 50, 100, 250, 1000)
SEED = 0
TRAIN_YEAR = 2018   # DVM also holds a few adverts from other years, including 2021, mid-shortage
DRAWS = 500         # random splits of the 2022 cars; every figure is the median across them

# Measured elsewhere in this project, quoted so the baselines are traceable.
sys.path.insert(0, str(Path(__file__).parent))
from drivers import effect  # noqa: E402  (drivers.py must run first)
RATE_POOLED = float(np.expm1(effect("age_years")["estimate"]))             # pooled across datasets
RATE_UK = float(np.expm1(effect("age_years", "uk_2022_10")["estimate"]))   # uk_2022_10's own

FEATURES = ["age_years", "log_mileage", "automatic", "diesel", "hatchback"]


def load():
    cols = ["source", "country", "make", "model", "price_type", "is_new", "year", "age_years",
            "mileage_km", "price", "currency", "fuel", "transmission", "body_type", "listing_date"]
    d = pd.read_parquet(LISTINGS, columns=cols)
    d = d[(d["make"] == MAKE) & (d["model"] == MODEL) & (d["country"] == COUNTRY)]
    d = d[d["price_type"].eq("asking") & ~d["is_new"].fillna(False).astype(bool)]
    d = d[d["age_years"].between(0.5, 30) & d["mileage_km"].between(1_000, 400_000)
          & d["price"].between(500, 200_000) & d["currency"].eq("GBP")]
    return d


def design(d):
    x = pd.DataFrame({
        "age_years": d["age_years"].to_numpy(float),
        "log_mileage": np.log(d["mileage_km"].to_numpy(float)),
        "automatic": (d["transmission"].astype("string") == "automatic").to_numpy(float),
        "diesel": (d["fuel"].astype("string") == "diesel").to_numpy(float),
        "hatchback": (d["body_type"].astype("string") == "hatchback").to_numpy(float),
    }, index=d.index)
    x["const"] = 1.0
    y = np.log(d["price"].to_numpy(float))
    keep = x.notna().all(axis=1).to_numpy() & np.isfinite(y)
    return y[keep], x[keep], d[keep]


def fit(y, X):
    return np.linalg.pinv(X.T @ X) @ (X.T @ y)


def errors(actual, predicted):
    """Median absolute and median signed percentage error."""
    e = (predicted - actual) / actual * 100
    return float(np.median(np.abs(e))), float(np.median(e))


def main():
    rng = np.random.default_rng(SEED)
    d = load()
    train_raw = d[(d["source"] == TRAIN_SOURCE) & d["listing_date"].dt.year.eq(TRAIN_YEAR)]
    test_raw = d[d["source"] == TEST_SOURCE]

    y_tr, x_tr, d_tr = design(train_raw)
    y_te, x_te, d_te = design(test_raw)
    # A feature that never varies is collinear with the constant: every Corsa is a hatchback.
    used = [c for c in FEATURES if x_tr[c].nunique() > 1 and x_te[c].nunique() > 1]
    dropped = [c for c in FEATURES if c not in used]
    cols = used + ["const"]
    beta = fit(y_tr, x_tr[cols].to_numpy(float))
    beta_te = fit(y_te, x_te[cols].to_numpy(float))

    Xte = x_te[cols].to_numpy(float)
    actual = np.exp(y_te)

    # One random draw of 25 cars is luck as much as evidence, so repeat it. In each draw half of the
    # 2022 cars supply the refit and the anchor cars, and the other half are priced by every model.
    half = len(y_te) // 2
    runs = {"as_is": [], "refit": [], **{n: [] for n in ANCHOR_SIZES}}
    shifts, shares = {n: [] for n in ANCHOR_SIZES}, []
    for _ in range(DRAWS):
        perm = rng.permutation(len(y_te))
        fit_i, score_i = perm[:half], perm[half:]
        runs["as_is"].append(errors(actual[score_i], np.exp(Xte[score_i] @ beta)))
        runs["refit"].append(errors(actual[score_i],
                                    np.exp(Xte[score_i] @ fit(y_te[fit_i], Xte[fit_i]))))
        for n in ANCHOR_SIZES:
            shift = float(np.mean(y_te[fit_i[:n]] - Xte[fit_i[:n]] @ beta))
            shifts[n].append(shift)
            runs[n].append(errors(actual[score_i], np.exp(Xte[score_i] @ beta + shift)))
        smallest = runs[min(ANCHOR_SIZES)][-1][0]
        shares.append((runs["as_is"][-1][0] - smallest)
                      / (runs["as_is"][-1][0] - runs["refit"][-1][0]) * 100)

    def med(key, i):
        return float(np.median([r[i] for r in runs[key]]))

    rows = [{"how the 2022 Corsas are priced": "**2018 model, used as it stands**",
             "cars used from 2022": "0",
             "median error": f"{med('as_is', 0):.1f}%",
             "bias (median signed)": f"{med('as_is', 1):+.1f}%"}]
    for n in ANCHOR_SIZES:
        rows.append({"how the 2022 Corsas are priced":
                     f"2018 model, **level re-anchored** on {n} current cars",
                     "cars used from 2022": f"{n}",
                     "median error": f"{med(n, 0):.1f}%", "bias (median signed)": f"{med(n, 1):+.1f}%"})
    # A model refitted entirely on 2022 - the ceiling for this feature set.
    rows.append({"how the 2022 Corsas are priced": "**refitted from scratch** on 2022 data",
                 "cars used from 2022": f"{half:,}",
                 "median error": f"{med('refit', 0):.1f}%",
                 "bias (median signed)": f"{med('refit', 1):+.1f}%"})

    # The fixed-depreciation rule every residual-value desk starts from.
    ret = pd.read_parquet(RETAINED)
    ret = ret[(ret["make"] == MAKE) & (ret["model"] == MODEL) & (ret["source"] == TEST_SOURCE)]
    ret = ret[ret["age_years"].between(0.5, 30) & ret["price"].between(500, 200_000)]
    for label, rate in ((f"pooled {RATE_POOLED * 100:.1f}% a year", RATE_POOLED),
                        (f"UK's own {RATE_UK * 100:.1f}% a year", RATE_UK)):
        pred = ret["new_price"].to_numpy(float) * (1 + rate) ** ret["age_years"].to_numpy(float)
        mae, bias = errors(ret["price"].to_numpy(float), pred)
        rows.append({"how the 2022 Corsas are priced":
                     f"fixed depreciation rule off the new price, {label}",
                     "cars used from 2022": "0",
                     "median error": f"{mae:.1f}%", "bias (median signed)": f"{bias:+.1f}%"})

    # Did the shape travel? Compare each 2018 slope with the same slope refitted on 2022.
    shape = pd.DataFrame([
        {"driver": name,
         "2018 estimate": f"{beta[i]:+.4f}", "2022 estimate": f"{beta_te[i]:+.4f}",
         "change": f"{beta_te[i] - beta[i]:+.4f}"}
        for i, name in enumerate(used)
    ] + [{"driver": "**constant (the price level)**", "2018 estimate": f"{beta[-1]:+.4f}",
          "2022 estimate": f"{beta_te[-1]:+.4f}", "change": f"{beta_te[-1] - beta[-1]:+.4f}"}])

    # How much of the recoverable error was level, and how much was the slopes?
    err_asis, err_refit, err_anchor = med("as_is", 0), med("refit", 0), med(min(ANCHOR_SIZES), 0)
    share_level = float(np.median(shares))
    share_lo, share_hi = np.percentile(shares, [10, 90])
    anchored = ANCHOR_SIZES

    # The level shift the Corsa implies, against the ONS index over the same months.
    implied = float(np.exp(np.median(shifts[max(ANCHOR_SIZES)])) - 1) * 100
    idx = pd.read_parquet(INDICES)
    ons = idx[idx["series"].str.startswith("ONS")].set_index("month")["index_value"].astype(float)
    ons_move = float(ons["2022-10"] / ons["2018-01"] - 1) * 100

    # A four-year-old Corsa in each snapshot, each measured against its own cohort's list price.
    all_ret = pd.read_parquet(RETAINED)
    all_ret = all_ret[(all_ret["make"] == MAKE) & (all_ret["model"] == MODEL)
                      & all_ret["age_years"].between(3.5, 4.5)
                      & all_ret["price"].between(500, 200_000)]
    walk_rows, retained_by_snapshot = [], {}
    for src, when in ((TRAIN_SOURCE, "2018"), (TEST_SOURCE, "October 2022")):
        g = all_ret[all_ret["source"] == src]
        share = float(g["retained"].median()) * 100
        retained_by_snapshot[when] = share
        walk_rows.append({
            "a four-year-old Corsa, in": f"**{when}**",
            "list price when new (£)": f"{g['new_price'].median():,.0f}",
            "market price (£)": f"{g['price'].median():,.0f}",
            "share of its own list price": f"{share:.0f}%",
            "adverts": f"{len(g):,}"})
    walk = pd.DataFrame(walk_rows)

    # The same list price in euros, for the lifetime profit-and-loss. The rate is this cohort's own
    # median pounds per euro, not a typed constant.
    latest = all_ret[all_ret["source"] == TEST_SOURCE]
    gbp_per_eur = float((latest["price"] / latest["price_eur"]).median())
    list_gbp = float(latest["new_price"].median())
    money = pd.DataFrame([{
        "the worked example car": "Vauxhall Corsa, entry trim, four years old in October 2022",
        "list price when new (GBP)": f"{list_gbp:,.0f}",
        "pounds per euro": f"{gbp_per_eur:.4f}",
        "list price when new (EUR)": f"{list_gbp / gbp_per_eur:,.0f}"}])

    report = [
        "# One real car, end to end: a Vauxhall Corsa in the UK", "",
        "Generated by `analysis/one_car.py`. Vauxhall is one of the merged group's own brands and "
        "the Corsa is its highest-volume UK model, so this is the group's own product, not an "
        "illustration. Prices are in **pounds**, the car's own currency, so no exchange rate enters "
        "the comparison.", "",
        f"Two snapshots of the same car sit four years apart in the collection: **{len(d_tr):,} "
        f"adverts from 2018** (DVM-CAR, which also carries a new list price per model year) and "
        f"**{len(d_te):,} from October 2022** (the UK scrape), either side of the 2021-22 used-car "
        "price surge. That gap is a natural test of the claim the rest of this project keeps "
        "arriving at.", "",
        "## The test: can a 2018 model price a 2022 car?", "",
        "A model of log price on age, mileage, gearbox, fuel and body is fitted on the 2018 Corsas "
        "and asked to price the 2022 ones. *Median error* is the typical gap between the predicted "
        "and the advertised price; *bias* is the median signed gap, so a negative number means the "
        f"prediction is too low. Every figure is the median over {DRAWS} random splits of the 2022 "
        "cars: half supply the refit and the anchor cars, the other half are priced by every model, "
        "so no model is scored on cars it was fitted to.", "",
        md_table(pd.DataFrame(rows)), "",
        f"**The 2018 model is not wrong about the car. It is wrong about the market.** Used as it "
        f"stands it is off by {err_asis:.0f}%, and almost all of that is bias: it prices every 2022 "
        f"Corsa about {abs(med('as_is', 1)):.0f}% too low, because it still believes in "
        f"2018 prices. Re-anchoring the level on **{min(anchored)} current cars** - nothing else "
        f"changed, every slope still from 2018 - cuts the median error to {err_anchor:.1f}%.", "",
        f"**Put the three numbers side by side and the split is measured, not asserted.** Going "
        f"from the 2018 model ({err_asis:.1f}%) to a model refitted from scratch on {half:,} "
        f"current cars ({err_refit:.1f}%) recovers {err_asis - err_refit:.1f} points of error. "
        f"Re-anchoring the level alone, on {min(anchored)} cars, recovers "
        f"{err_asis - err_anchor:.1f} of those {err_asis - err_refit:.1f} points - "
        f"**{share_level:.0f}% of everything there was to recover.** Refitting every slope on "
        f"{half:,} cars buys the remaining {err_anchor - err_refit:.1f} points.", "",
        f"Which {min(anchored)} cars you happen to draw matters a little: across the {DRAWS} draws "
        f"the share recovered runs from {share_lo:.0f}% to {share_hi:.0f}% (p10 to p90).", "",
        "This is the same result as `lodo_report.md` arrived at across markets, and "
        "`latvia_time_report.md` across time, now on a single car in a single market: **the shape "
        "is worth keeping and the level has to be bought fresh.**", "",
        "## The slopes, 2018 against 2022", "",
        md_table(shape), "",
        (f"*{', '.join(dropped)} dropped: no variation in this model, so collinear with the "
         f"constant.*\n\n" if dropped else "")
        + "The slopes did move - mileage most of all - so this is not a claim that the shape is "
        "frozen. The point is the one the decomposition above makes: correcting the slopes is worth "
        "a fraction of a point once the level is right.", "",
        "**Read the constant row with care.** It is not the size of the level shift on its own: the "
        "mileage slope also moved, and mileage enters in logs around 11, so part of the constant's "
        f"jump offsets that. The level gap measured properly - by holding every 2018 slope and "
        f"refitting only the constant - is the {implied:+.1f}% in the next section.", "",
        "## Checking the level shift against an official index", "",
        f"- The level gap between the 2018 fit and the October 2022 cars is **{implied:+.1f}%**.",
        f"- The ONS second-hand car index (CPI 07.1.1B, series D7E9) rose **{ons_move:+.1f}%** over "
        "the same months.",
        "- **These two numbers are not measuring quite the same thing, and the gap should not be "
        "read as a market move.** The 2018 and 2022 snapshots come from two different scrapes, so "
        "the shift mixes a real price rise with whatever differs between the sources - stock mix, "
        "trim, seller type - and the two never overlap in time, so this design cannot separate "
        "them. The ONS figure is the part that is definitely market.",
        "- **That confound does not weaken the finding; it is the finding.** A value engine does "
        "not need to know *why* its level is wrong. Re-anchoring corrects a level gap whatever its "
        "cause - a market move, a new data source, a different mix - and "
        f"{min(anchored)} current cars were enough to do it here.", "",
        "## The fixed-depreciation rule, for comparison", "",
        "The last two rows of the table are the rule a residual-value desk starts from: take the "
        "list price and apply a fixed percentage a year. On these cars it is **wrong in a "
        "particular direction** - it prices them far too low, because the rule cannot know that the "
        "whole used market had risen since the car was new. It is the same failure as the 2018 "
        "model, from a simpler starting point.", "",
        "## The car itself", "",
        "Each snapshot is measured against **its own cohort's list price**, so the two rows are "
        "like for like: a car that was four years old in 2018 is a different model year, with a "
        "different list price, from one that was four years old in 2022.", "",
        md_table(walk), "",
        f"A four-year-old Corsa held {retained_by_snapshot['2018']:.0f}% of its list price in 2018 "
        f"and {retained_by_snapshot['October 2022']:.0f}% of it in October 2022. **The same car, "
        f"the same age, a different market** - a gap of "
        f"{retained_by_snapshot['October 2022'] - retained_by_snapshot['2018']:.0f} points of the "
        "original price. A lease written on the 2018 view would have been wrong by roughly that "
        "much, and no amount of information about the car would have closed it.", "",
        "## Limits", "",
        "- **Advertised prices, not sale prices**, on both sides. `price_types_report.md` explains "
        "why no asking-to-sale adjustment can be quoted from this collection.",
        "- **The new price is DVM's entry trim**, the cheapest version of that model year, so the "
        "share-of-list figures are flattered and the fixed-rule baseline is handicapped. The "
        "comparison between the model rows is unaffected: they never use the new price.",
        "- **Two sources, not one.** The 2018 and 2022 snapshots are different scrapes with "
        "different mixes, so some of the level shift is composition the features do not capture.",
        "- **One model, one country.** The Corsa is a small, high-volume hatchback; a premium or "
        "electric model need not behave this way.",
        f"- The 2018 side is dominated by a single scrape month, so it measures one moment rather "
        f"than the whole of 2018.", "",
        "## The same car in euros", "",
        "Everything above is in pounds. The lifetime profit-and-loss in the deliverables is in euros, "
        "so the conversion is done once, here, at this cohort's own median rate rather than a typed "
        "constant:", "", md_table(money), "",
        "The euro figure is the one the per-car profit-and-loss is built on. Every line of that "
        "profit-and-loss is a share of it, so it must not be re-derived anywhere else.", "",
    ]
    OUT.write_text("\n".join(report))

    print(f"train {len(y_tr):,} (2018) | test {len(y_te):,} (Oct 2022)")
    print(f"as-is median err {err_asis:.1f}% (bias {med('as_is', 1):+.1f}%)")
    for n in ANCHOR_SIZES:
        print(f"  re-anchored on {n:>4}: {med(n, 0):.1f}% (bias {med(n, 1):+.1f}%)")
    print(f"refit from scratch: {err_refit:.1f}% | level share {share_level:.0f}% "
          f"(p10-p90 {share_lo:.0f}-{share_hi:.0f})")
    print(f"implied level shift {implied:+.1f}% vs ONS {ons_move:+.1f}%")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
