"""Which fields actually move a car's value, and what does it cost not to have one?

Two questions the value engine has to answer before it can be built into a live system.

**1. What does not knowing the odometer cost?** The upgrade-timing model has to run over every
customer before anyone is contacted, so it cannot ask them for a mileage. It has to work from what
the company already holds. This measures the penalty directly, on the Corsa, by taking the true
odometer away and replacing it with a guess from age alone.

**2. If the market level dominates, what still distinguishes one car from another?** These are
different questions and it is easy to confuse them. The level moves every car together, so it says
nothing about which car is worth more. This decomposes the variation in price to show what does.

Both use data already in the repo. No new source.

Usage: .venv/bin/python analysis/what_matters.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import md_table  # noqa: E402

HERE = Path(__file__).parent
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
OUT = HERE / "what_matters_report.md"

MAKE, MODEL, COUNTRY = "vauxhall", "corsa", "GB"
TRAIN_SOURCE, TEST_SOURCE = "dvm", "uk_2022_10"
PANEL = "lv_ss"          # the only source with a real monthly time series
ANCHOR_N = 25            # cars used to re-anchor the level, as in one_car.py
SEED = 0

# Measured elsewhere, quoted so the comparison is traceable.
LEVEL_SUMMARY = Path(__file__).parent / "level_risk_summary.csv"   # written by level_risk.py


def clean(d, price_col="price"):
    d = d[d["price_type"].eq("asking") & ~d["is_new"].fillna(False).astype(bool)]
    return d[d["age_years"].between(0.5, 30) & d["mileage_km"].between(1_000, 400_000)
             & d[price_col].between(500, 200_000)]


def design(d, mileage):
    return np.column_stack([
        d["age_years"].to_numpy(float),
        np.log(mileage),
        (d["transmission"].astype("string") == "automatic").fillna(False).to_numpy(float),
        (d["fuel"].astype("string") == "diesel").fillna(False).to_numpy(float),
        np.ones(len(d)),
    ])


def fit(y, X):
    return np.linalg.pinv(X.T @ X) @ (X.T @ y)


def demean(values, groups):
    """Remove each group's mean - the variation that group identity explains."""
    g = pd.factorize(groups)[0]
    counts = np.bincount(g)
    means = np.bincount(g, weights=values) / counts
    return values - means[g]


def mileage_cost():
    """Take the odometer away and measure what it costs."""
    cols = ["source", "country", "make", "model", "price_type", "is_new", "age_years",
            "mileage_km", "price", "currency", "fuel", "transmission", "listing_date"]
    d = pd.read_parquet(LISTINGS, columns=cols)
    d = d[(d["make"] == MAKE) & (d["model"] == MODEL) & (d["country"] == COUNTRY)
          & d["currency"].eq("GBP")]
    d = clean(d)
    # The DVM set holds a few adverts from other years, including 2021; the model is the 2018 one.
    tr = d[(d["source"] == TRAIN_SOURCE) & d["listing_date"].dt.year.eq(2018)]
    te = d[d["source"] == TEST_SOURCE]

    y_tr, y_te = np.log(tr["price"].to_numpy(float)), np.log(te["price"].to_numpy(float))
    true_km = te["mileage_km"].to_numpy(float)
    beta = fit(y_tr, design(tr, tr["mileage_km"].to_numpy(float)))

    # What a company with no odometer would use: median km per year of age, from the training data.
    km_per_year = float(np.median(tr["mileage_km"].to_numpy(float)
                                  / tr["age_years"].to_numpy(float)))
    guessed = np.maximum(km_per_year * te["age_years"].to_numpy(float), 1_000)

    rng = np.random.default_rng(SEED)
    anchor = rng.choice(len(y_te), ANCHOR_N, replace=False)
    held = np.setdiff1d(np.arange(len(y_te)), anchor)
    actual = np.exp(y_te[held])

    def score(km):
        """Re-anchor the level the same way every time, so only the mileage treatment differs."""
        X = design(te, km)
        shift = float(np.mean(y_te[anchor] - X[anchor] @ beta))
        pred = np.exp(X[held] @ beta + shift)
        return float(np.median(np.abs((pred - actual) / actual * 100)))

    base = score(true_km)
    rows = [{"what the model knows about the odometer": "**The true reading**",
             "median error": f"{base:.1f}%", "cost of not knowing": "-"}]
    for label, km in [
            (f"**Nothing at all** - guessed from age ({km_per_year:,.0f} km a year)", guessed),
            ("Known, but wrong by +/-10% on each car", true_km * np.exp(rng.normal(0, 0.10, len(te)))),
            ("Known, but wrong by +/-20% on each car", true_km * np.exp(rng.normal(0, 0.20, len(te)))),
            ("Known, but wrong by +/-50% on each car", true_km * np.exp(rng.normal(0, 0.50, len(te)))),
            ("Every reading doubled (a systematic error)", true_km * 2)]:
        e = score(km)
        rows.append({"what the model knows about the odometer": label,
                     "median error": f"{e:.1f}%", "cost of not knowing": f"+{e - base:.1f} points"})

    elasticity = beta[1]
    spread = (np.exp(elasticity * np.log(80_000 / 20_000)) - 1) * 100
    return rows, base, elasticity, spread, km_per_year, len(tr), len(te)


def what_distinguishes():
    """Decompose the variation in price: what explains which car is worth more?"""
    cols = ["source", "price_type", "is_new", "make", "model", "listing_date", "age_years",
            "mileage_km", "price_eur", "fuel", "transmission", "body_type"]
    d = pd.read_parquet(LISTINGS, columns=cols)
    d = clean(d[d["source"] == PANEL], "price_eur")
    d = d[d["listing_date"].notna() & d["age_years"].notna() & d["mileage_km"].notna()]

    y = np.log(d["price_eur"].to_numpy(float))
    total = float(np.var(y))
    month = pd.to_datetime(d["listing_date"]).dt.to_period("M").astype(str).to_numpy()
    name = (d["make"].astype(str) + "|" + d["model"].astype(str)).to_numpy()

    steps, resid = [], y - y.mean()
    swap = "with the odometer entered before age"

    def record(label, new_resid, note):
        nonlocal resid
        before = float(np.var(resid))
        after = float(np.var(new_resid))
        steps.append({"what you know, added in this order": label,
                      "variation still unexplained": f"{after / total * 100:.0f}%",
                      "this step explains": f"{(before - after) / total * 100:.1f} points",
                      swap: "", "what it tells you": note})
        resid = new_resid

    record("**The month** - what the whole market is doing",
           demean(resid, month), "moves every car together, so it separates none of them")
    # Month and model are removed together, alternating until neither mean is left, so the model
    # step is not overstated by whatever the month step could not separate from it.
    both = y - y.mean()
    for _ in range(20):
        both = demean(demean(both, month), name)
    record("**Which model of car it is**", both, "by far the largest single thing")

    # Each car-level step refits every field entered so far, so correlated fields are not
    # double-counted, and the order only decides which of them gets the shared credit.
    within = resid
    fields = {"age": d[["age_years"]].to_numpy(float),
              "odometer": np.log(d[["mileage_km"]].to_numpy(float)),
              "spec": np.column_stack([
                  (d["transmission"].astype("string") == "automatic").fillna(False).to_numpy(float),
                  (d["fuel"].astype("string") == "diesel").fillna(False).to_numpy(float),
                  (d["body_type"].astype("string") == "suv").fillna(False).to_numpy(float)])}

    def left_after(*names):
        Xc = np.column_stack([fields[n] for n in names] + [np.ones(len(within))])
        return within - Xc @ fit(within, Xc)

    record("**How old it is**", left_after("age"), "")
    record("**The odometer**", left_after("age", "odometer"), "")
    record("**Gearbox, fuel and body**", left_after("age", "odometer", "spec"), "specification")

    shared = float(np.var(within))
    odometer_first = (shared - float(np.var(left_after("odometer")))) / total * 100
    age_second = (float(np.var(left_after("odometer"))) - float(np.var(left_after("age", "odometer")))) \
        / total * 100
    steps[2][swap], steps[3][swap] = f"{age_second:.1f} points", f"{odometer_first:.1f} points"
    steps[2]["what it tells you"] = "age and mileage share most of what they explain"
    steps[3]["what it tells you"] = "small here only because age went in first"
    missing = (int(d["fuel"].isna().sum()), int(d["body_type"].isna().sum()))
    return steps, len(d), d["listing_date"].min(), d["listing_date"].max(), missing


def main():
    rows, base, elasticity, spread, km_year, n_tr, n_te = mileage_cost()
    steps, n_panel, first, last, (no_fuel, no_body) = what_distinguishes()
    summary = pd.read_csv(LEVEL_SUMMARY).set_index("name")["value"]
    level_share = summary["level_points"] / summary["retained_3y_pooled"] * 100

    report = [
        "# Which fields matter, and what it costs not to have one", "",
        "Generated by `analysis/what_matters.py`. No new data source.", "",
        "## 1. Running the model without an odometer", "",
        "The upgrade-timing model has to score every customer **before** anyone is contacted, so it "
        "cannot ask them how many miles the car has done. It has to work from what the company "
        "already holds. The question is what that costs.", "",
        f"A model is fitted on {n_tr:,} Corsa adverts from 2018 and used to price {n_te:,} from "
        "October 2022, with the price level re-anchored on "
        f"{ANCHOR_N} current cars each time so that only the mileage treatment differs.", "",
        md_table(pd.DataFrame(rows)), "",
        f"**Knowing nothing about the odometer costs about "
        f"{float(rows[1]['cost of not knowing'].strip('+ points')):.1f} points of error.** For "
        f"scale, the market level moves about {level_share:.0f}% of a car's residual value across "
        "an ordinary three years (`level_risk_report.md`). Mileage is a second-order problem next "
        "to the one nobody can forecast.", "",
        "**The last row is the interesting one and it is easy to misread.** Doubling every reading "
        "costs nothing at all - but not because mileage is irrelevant. A *systematic* error, where "
        "every car is wrong by the same factor, is absorbed entirely by the monthly level "
        "re-anchor. Random per-car error is not. The practical rule: an odometer feed may be "
        "biased, but it must not be noisy.", "",
        "### Where the readings come from without asking anyone", "",
        "- **Every workshop visit** records the odometer on the job card, for service intervals and "
        "warranty. For a car still under contract that is roughly annual.",
        "- **Every warranty claim, recall fix and roadside callout** records it too.",
        "- **Connected cars** report it directly, subject to a lawful basis for using it.",
        "- **Roadworthiness tests** - UK MOT from year three, Dutch APK, Belgian Car-Pass, which is "
        "mandatory and centralised.",
        "- **The finance contract** states a mileage allowance. Not the actual reading, but a good "
        "prior - and the gap between allowance and actual is itself an upgrade signal.", "",
        "So the sequence is two steps with different accuracy needs: **screen everyone** on "
        "estimated mileage, because you are only ranking them; then **contact the top slice**, and "
        "the conversation returns the true reading, the condition and the intent, which is when a "
        "precise number is actually needed - to price the offer.", "",
        "## 2. If the market moves every car, what still tells cars apart?", "",
        "These are different questions, and conflating them is a trap. The level moves every car "
        "**together**, so it explains a great deal about what a car is worth and **nothing** about "
        "which car is worth more. The table below takes the Latvian panel - "
        f"{n_panel:,} adverts across {first:%Y-%m} to {last:%Y-%m}, the only source with a real "
        "monthly series - and removes one thing at a time.", "",
        md_table(pd.DataFrame(steps)), "",
        "*Sequential, so the order matters: each row is measured after everything above it has "
        "already been taken out, refitting all of it at each step. The age and odometer rows are "
        "also shown the other way round.*", "",
        "**Two numbers in that table need reading carefully.**", "",
        "- **The month explains very little here, and that is the point, not a contradiction.** "
        "This table measures what tells cars *apart* at a moment in time, and the market level is "
        "shared by all of them, so it separates none of them. The same level move that barely "
        "registers here is the thing that dominates when you ask what one car will be worth in "
        "three years. Two different questions, two different answers.",
        f"- **The odometer adds almost nothing *because age is already in the model*, and that "
        f"must not be read as 'mileage does not matter'.** Age and mileage move together - a car "
        f"three years old has usually done about three years of miles. Put the odometer in first "
        f"and it explains {steps[3]['with the odometer entered before age']}, with age adding "
        f"{steps[2]['with the odometer entered before age']} more. Together they explain the same "
        f"either way; which of them gets the credit is a choice of order, not a finding. What is a "
        f"finding is that age carries most of what the odometer would say, which is why guessing "
        f"mileage from age works.", "",
        "**Which model of car it is dominates everything else.** That is the answer to the worry "
        "that a small mileage effect leaves cars indistinguishable. It never did: model identity is "
        "the largest term in the model, and the value engine carries a separate level for every "
        "make and model. Within a model, age and mileage together are the strongest thing, and "
        "most of what they explain they explain jointly.", "",
        "### Why mileage explains a lot but missing it costs little", "",
        "Both are true at once, and the reconciliation is the point:", "",
        f"- The **range** of mileage across cars is wide. On the measured elasticity "
        f"({elasticity:+.3f} in logs, about {elasticity * np.log(1.1) * 100:+.2f}% for 10% more "
        f"miles), going from 20,000 km to 80,000 km is worth about **{spread:.0f}%** of the price. "
        "That is material.",
        f"- Our **uncertainty** about mileage is narrow beside that range. Guessing "
        f"{km_year:,.0f} km a year from the car's age lands close enough that the error costs about "
        "a point.", "",
        "A field can be a strong driver and a cheap thing to estimate at the same time. Mileage is "
        "both.", "",
        "## Limits", "",
        "- **One model, one country, for part 1.** The Corsa is a small high-volume hatchback and "
        "the UK is a strong used market. `drivers_report.md` shows the mileage effect varying "
        "several-fold between datasets, so a long-distance diesel market would be more sensitive "
        "than this.",
        "- **Advertised prices on both sides**, with mileage self-reported by sellers and often "
        "rounded.",
        "- **Part 2 is Latvia only**, a small import-driven market, and the decomposition is "
        "sequential rather than a simultaneous variance partition, so the order of the rows is a "
        "choice. It is ordered to answer the question asked: the market first, then the car. Do not "
        "put the odometer row on a slide without the column beside it.",
        "- `lv_ss` is a monthly panel with no listing id, so a car that stays listed is counted once "
        "per month it appears. Shares of variation are little affected; counts of cars are not.",
        f"- **An unrecorded field is read as 'no'.** Latvia has {no_fuel:,} adverts with no fuel "
        f"and {no_body:,} with no body type; those count as not-diesel and not-SUV, which "
        "understates those two rows slightly.",
        "- The guessed-mileage row uses a single median km per year. A real system would use a "
        "per-market, per-segment curve and do better than this.", "",
    ]
    OUT.write_text("\n".join(report))

    print(f"mileage: true {base:.1f}% | no odometer {rows[1]['median error']} "
          f"(+{float(rows[1]['cost of not knowing'].strip('+ points')):.1f} points)")
    print(f"elasticity {elasticity:+.3f} -> 20k to 80k km is {spread:.0f}% of price")
    for s in steps:
        print(f"  {s['what you know, added in this order'][:46]:<48} "
              f"explains {s['this step explains']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
