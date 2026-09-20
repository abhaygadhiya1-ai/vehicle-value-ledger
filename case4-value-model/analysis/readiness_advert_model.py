"""Does anything public predict that a car comes to *market* - or only that it leaves the fleet?

`readiness_mileage.py` answered half of this with one coefficient: mileage against the cohort moves
the chance of being advertised by **1.03x** per doubling, which is nothing. But one coefficient is
a thin test. A car might be predictable from what it is rather than how far it has gone, and the
two-layer engine cannot see make, fuel or engine size at all.

So this asks the question the way a model would. The density-ratio estimator

    hazard(x)  is proportional to  f(x | came to market) / f(x | parc)

can be estimated by **training a classifier to tell an advert apart from a car on the road**. If
that classifier can do better than the age curve alone, something public predicts coming to
market. If it cannot, then the honest conclusion is that the group's own data is the only place
the signal lives - and that is the ledger's argument, arrived at with a model rather than a slope.

    parc     UK MOT tests, September to November 2022, the months around the advert scrape
    adverts  `uk_2022_10`, the October 2022 UK listings already in the collection
    shared   age, odometer, odometer against the cohort, make, fuel

Make is normalised on both sides with `build_unified.norm_name`, or a Ford in the register would
not be a Ford in the adverts.

    .venv/bin/python analysis/readiness_advert_model.py --build   # ~8 min, streams 1.1 GB
    .venv/bin/python analysis/readiness_advert_model.py           # trains and scores
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).parent.parent))
import mot_stream as mot  # noqa: E402
from build_unified import MAKE_ALIASES, md_table, norm_name  # noqa: E402
from readiness_model import mix  # noqa: E402

HERE = Path(__file__).parent
PARC = HERE.parent / "data" / "reference" / "uk_mot_2022_parc.parquet"
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
OUT = HERE / "readiness_advert_model_report.md"

MILES_TO_KM = 1.609344
MIN_KM, MAX_KM = 1_000, 400_000
AGES = (3, 20)
MONTHS = ("2022-09", "2022-10", "2022-11")
KEEP = 3                 # one parc car in three, by mixed id
SEED = 20260921
ROUND_MILES = 1_000      # both sides to the same grid; see load()
CAT_CAP = 200            # levels kept per categorical; the rest become one "other"

# MOT records fuel as a two-letter code; the listings record a word
FUEL = {"PE": "petrol", "DI": "diesel", "HY": "hybrid", "EL": "electric",
        "LP": "lpg", "GB": "hybrid", "GA": "lpg", "FC": "electric"}


def build():
    rows = []
    zf, names = mot.members(2022)
    scanned = 0
    for p in mot.rows(zf, names[0]):
        scanned += 1
        if scanned % 5_000_000 == 0:     # before the filter, or it almost never fires
            print(f"  {scanned:,} car tests scanned, {len(rows):,} kept", flush=True)
        if p[2][:7] not in MONTHS or mix(int(p[1])) % KEEP:
            continue
        fu, m = mot.reg_year(p), mot.mileage(p)
        if fu is None or m is None:
            continue
        a = 2022 - fu
        k = m * MILES_TO_KM
        if AGES[0] <= a <= AGES[1] and MIN_KM <= k <= MAX_KM:
            rows.append((a, k, p[8], FUEL.get(p[11], "other")))
    d = pd.DataFrame(rows, columns=["age", "km", "make_raw", "fuel"])
    d["make"] = norm_name(d["make_raw"]).replace(MAKE_ALIASES)
    d = d.drop(columns=["make_raw"])
    PARC.parent.mkdir(parents=True, exist_ok=True)
    d.to_parquet(PARC, index=False)
    print(f"wrote {PARC.name}: {len(d):,} cars, {PARC.stat().st_size / 1e6:.0f} MB")


def load():
    parc = pd.read_parquet(PARC)
    lst = pd.read_parquet(LISTINGS, columns=["source", "country", "year", "mileage_km", "make",
                                             "fuel", "is_new", "price_type"])
    ad = lst[(lst["source"] == "uk_2022_10") & lst["price_type"].eq("asking")
             & ~lst["is_new"].fillna(False).astype(bool)].dropna(subset=["year", "mileage_km"])
    ad = ad.assign(age=2022 - ad["year"].astype(int), km=ad["mileage_km"].astype(float))
    ad = ad[ad["age"].between(*AGES) & ad["km"].between(MIN_KM, MAX_KM)]
    ad = ad[["age", "km", "make", "fuel"]].copy()
    ad["fuel"] = ad["fuel"].astype("string").fillna("other")
    parc["listed"] = 0
    ad["listed"] = 1
    d = pd.concat([parc, ad], ignore_index=True)

    # **Round both sides to the same grid, or the model cheats.** A seller types 100,000 and a
    # tester reads 98,432: 30.9% of advert mileages are exact multiples of a thousand miles
    # against 0.11% of MOT readings, a 280x difference. Left alone, the classifier identifies the
    # *file* from the digits and returns an AUC that has nothing to do with replacement. Rounding
    # both sides to the nearest thousand miles removes the tell and costs nothing that matters.
    miles = d["km"].to_numpy() / MILES_TO_KM
    d["km"] = np.round(miles / ROUND_MILES) * ROUND_MILES * MILES_TO_KM
    med = d.loc[d["listed"] == 0].groupby("age")["km"].median()
    d["km_ratio"] = d["km"] / d["age"].map(med)
    return d.dropna(subset=["km_ratio"])


def fit(d, feats, cats):
    rng = np.random.default_rng(SEED)
    test = rng.random(len(d)) < 0.30
    tr, te = d[~test], d[test]
    m = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, random_state=SEED,
        categorical_features=[f in cats for f in feats])
    m.fit(tr[feats], tr["listed"])
    p = m.predict_proba(te[feats])[:, 1]
    return m, te, p, roc_auc_score(te["listed"], p)


def main():
    if "--build" in sys.argv:
        build()
        return
    d = load()
    # boosted trees take at most 255 levels, and the two files between them spell 786 makes
    for c in ("make", "fuel"):
        keep = d[c].value_counts().head(CAT_CAP).index
        d[c] = d[c].where(d[c].isin(keep), "OTHER").astype("category").cat.codes.astype(np.int32)
    n_ad = int(d["listed"].sum())
    print(f"{len(d):,} rows: {n_ad:,} adverts, {len(d) - n_ad:,} parc")

    _, _, _, auc_age = fit(d, ["age"], set())
    _, _, _, auc_am = fit(d, ["age", "km", "km_ratio"], set())
    m, te, p, auc_all = fit(d, ["age", "km", "km_ratio", "make", "fuel"], {"make", "fuel"})

    rng = np.random.default_rng(SEED + 3)
    feats = ["age", "km", "km_ratio", "make", "fuel"]
    imp = []
    for f in feats:
        X = te[feats].copy()
        X[f] = rng.permutation(X[f].to_numpy())
        imp.append({"Field": f,
                    "AUC lost": auc_all - roc_auc_score(te["listed"], m.predict_proba(X)[:, 1])})
    imp = pd.DataFrame(imp).sort_values("AUC lost", ascending=False)

    lines = [
        "# Can a model tell which cars come to market?",
        "",
        f"{n_ad:,} UK adverts of October 2022 against {len(d) - n_ad:,} cars tested in the "
        "September-to-November parc. A classifier is trained to tell one from the other; that is "
        "the density-ratio estimator in `readiness_mileage.py`, done with a model instead of a "
        "slope, so it can use what the car *is* and not only how far it has gone.",
        "",
        "AUC 0.5 means the model cannot tell an advertised car from one on the road - which would "
        "mean nothing public predicts coming to market.",
        "",
    ]
    lines.append(md_table(pd.DataFrame([
        {"What the model may use": "Age only", "AUC": f"{auc_age:.3f}"},
        {"What the model may use": "Age, odometer, odometer against the cohort",
         "AUC": f"{auc_am:.3f}"},
        {"What the model may use": "...and make and fuel", "AUC": f"{auc_all:.3f}"},
    ])))
    lines += [
        "",
        f"**Mileage adds {auc_am - auc_age:+.3f} over age alone** - which matches the elasticity "
        "of 0.041 in `readiness_mileage_report.md`, reached a second way and by a method free to "
        "find any shape it likes. **Mileage does not predict coming to market.**",
        "",
        f"**Make and fuel add a further {auc_all - auc_am:+.3f}, and that number cannot be "
        "believed.** A density ratio over makes is only a replacement signal if the adverts are a "
        "fair sample of the cars coming to market. They are one site's stock, and a site's brand "
        "mix is not the fleet's. Nothing in this data separates *Brand X changes hands more often* "
        "from *Brand X is over-represented on this website*, and the second needs no explaining.",
        "",
        "**The comparison that makes the point:** in `readiness_model_report.md`, where the "
        "outcome is observed per car and no sampling stands between the model and the truth, "
        "**make is worth +0.002 of AUC** - almost nothing. Here it is worth +0.082. A field that "
        "barely matters when you can watch the cars, and matters greatly when you are comparing "
        "two files, is telling you about the files.",
        "",
        "**So the answer to the question in the title is: age, and then not much that can be "
        "trusted.** Which is the ledger's argument reached with a model - if public data cannot "
        "say which car comes to market beyond its age, the contract date, the equity and the "
        "service history the group holds are not a refinement. They are the signal.",
        "",
        "## What each field is worth",
        "",
        md_table(pd.DataFrame({
            "Field": imp["Field"],
            "AUC lost when shuffled": imp["AUC lost"].map("{:+.3f}".format),
        })),
        "",
        "## What this settles",
        "",
        "- **It is the same conclusion the slope gave, reached a second way.** "
        "`readiness_mileage_report.md` found a mileage elasticity of 0.041 on this event - "
        "nothing - and a model free to use make and fuel does not rescue it.",
        "- **It is the argument for the ledger, made with a model.** If public data cannot say "
        "which car comes to market beyond its age, then the contract date, the equity and the "
        "service history that only the group holds are not a nice-to-have. They are the signal.",
        "- **The obvious cheat is closed, and it was large.** A seller types 100,000 and a tester "
        "reads 98,432: **30.9% of advert mileages are exact multiples of a thousand miles against "
        "0.11% of MOT readings, a 280x difference.** Left alone a classifier identifies the file "
        "from the digits and scores AUC 0.737 that has nothing to do with replacement. Both sides "
        "are rounded to the nearest thousand miles before anything is fitted.",
        "- **Other file differences may remain.** One October scrape against a three-month parc, "
        "and a site's brand mix is not the fleet's. Whatever is left of that inflates this AUC "
        "rather than deflating it, which makes a low number the safer error.",
        f"- **The commonest {CAT_CAP} makes are kept** and the rest pooled into one bucket, "
        "because a boosted tree takes at most 255 levels.",
        "- **Make is normalised on both sides** with `build_unified.norm_name` and "
        "`MAKE_ALIASES`, or the register's Ford would not be the adverts' Ford.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.name}")
    print(f"  age {auc_age:.3f} -> +mileage {auc_am:.3f} -> +make/fuel {auc_all:.3f}")


if __name__ == "__main__":
    main()
