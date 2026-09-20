"""Given only the fields the company actually holds, which datasets should train the model?

The company does not have the same columns as any one of our sources, and the columns it has change
as the car moves through its life. At order it knows the build record but not a mileage; halfway
through a contract it knows a mileage from service visits; at return it knows everything.

The instinct is that this forces us to pick the single dataset whose schema matches. It does not.
A dataset is usable if it **contains** the fields we are querying on - it may hold more. So the real
question is a trade-off nobody states: **every field you add to the query shrinks the pool of
datasets that can train it.** Four fields qualify 11 datasets; all eight qualify only 2.

This measures that trade-off. For each set of fields, and each European dataset held out in turn,
five strategies are compared:

  own              the dataset's own training half, nothing borrowed
  best other       the single largest other qualifying dataset - the "just pick one" approach
  all qualifying   every other dataset containing these fields, refit on exactly these fields
  hierarchical     own and all-qualifying blended by how precisely the dataset measures each effect
  one model        one set of coefficients for every moment, trained on the same data - the
                   alternative to keeping a model per moment

Every dataset is refitted on **exactly the query fields**, never on its own richer set. That matters:
an age coefficient estimated with engine power controlled is not the same quantity as one estimated
without it, so pooling the two would average different estimands. Refitting makes them comparable.

Scoring follows `lodo.py`: the within make-and-model residual, with the held-out dataset's own
training half always supplying the price level, so only the shape is borrowed. Every strategy is
scored on exactly the same cars.

Usage: .venv/bin/python analysis/field_sets.py
"""
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from drivers import LISTINGS, MIN_GROUP, md_table  # noqa: E402

OUT = Path(__file__).parent / "field_sets_report.md"
SEED = 0
MIN_ROWS = 5_000
COVERAGE = 0.5          # a source "has" a field if it is present on this share of its rows

EUROPE = ["GB", "DE", "FR", "ES", "IT", "NL", "PL", "PT", "SE", "LV", "BE", "AT",
          "LU", "FI", "LT", "EE", "HU", "BG", "HR", "CZ"]

# Each feature names the raw columns a source must carry to supply it.
NEEDS = {"age": ["age_years"], "mileage": ["mileage_km"], "mileage_est": [],
         "fuel": ["fuel"], "gearbox": ["transmission"], "body": ["body_type"],
         "power": ["power_kw"], "engine": ["engine_cc"], "owners": ["n_owners"]}

# The four moments, and what the company plausibly holds at each.
MOMENTS = [
    ("At order or sale - the build record, no mileage yet",
     ["age", "fuel", "gearbox", "body", "power", "engine"]),
    ("Mid-contract, no service data - mileage estimated from age",
     ["age", "mileage_est", "fuel", "gearbox"]),
    ("Mid-contract, with service visits - a real odometer reading",
     ["age", "mileage", "fuel", "gearbox", "body", "power"]),
    ("At return - everything on the car",
     ["age", "mileage", "fuel", "gearbox", "body", "power", "engine", "owners"]),
]


def load():
    """Same filters as `drivers.sample()`, plus the two columns it does not carry."""
    cols = ["source", "country", "price_type", "is_new", "make", "model", "age_years",
            "mileage_km", "power_kw", "engine_cc", "n_owners", "fuel", "transmission",
            "body_type", "price_eur", "listing_date"]
    d = pd.read_parquet(LISTINGS, columns=cols)
    d = d[d["price_type"].eq("asking") & ~d["is_new"].fillna(False).astype(bool)]
    d = d[d["age_years"].between(0.5, 30) & d["mileage_km"].between(1_000, 400_000)
          & d["price_eur"].between(500, 200_000)]
    return d


def positive(series):
    """Non-positive readings are missing values, not measurements; NaN so the row is dropped."""
    v = series.to_numpy(float)
    return np.where(v > 0, v, np.nan)


def columns(d, feats, km_per_year):
    """Build the design for one feature set. Returns a DataFrame of named columns."""
    fuel = d["fuel"].astype("string")
    body = d["body_type"].astype("string")
    out = {}
    for f in feats:
        if f == "age":
            out["age_years"] = d["age_years"].to_numpy(float)
        elif f == "mileage":
            out["log_mileage"] = np.log(d["mileage_km"].to_numpy(float))
        elif f == "mileage_est":
            est = np.maximum(km_per_year * d["age_years"].to_numpy(float), 1_000)
            out["log_mileage_est"] = np.log(est)
        elif f == "fuel":
            for name in ("diesel", "electric", "hybrid"):
                out[f"fuel_{name}"] = (fuel == name).fillna(False).to_numpy(float)
        elif f == "gearbox":
            out["automatic"] = (d["transmission"].astype("string") == "automatic") \
                .fillna(False).to_numpy(float)
        elif f == "body":
            for name in ("suv", "estate", "sedan"):
                out[f"body_{name}"] = (body == name).fillna(False).to_numpy(float)
        elif f == "power":
            out["log_power"] = np.log(positive(d["power_kw"]))
        elif f == "engine":
            # Some sources record 0 cc for electric cars; that is missing, not a real engine.
            out["log_engine"] = np.log(positive(d["engine_cc"]))
        elif f == "owners":
            out["n_owners"] = d["n_owners"].to_numpy(float)
    return pd.DataFrame(out, index=d.index)


def split_for(src, n):
    """A deterministic train/test split per source. Same source and same row count, same split."""
    order = np.random.default_rng(zlib.crc32(src.encode()) + SEED).permutation(n)
    return order[:n // 2], order[n // 2:]


def qualifies(d, feats):
    """A source can train this field set only if it carries every raw column it needs."""
    for f in feats:
        for raw in NEEDS[f]:
            if d[raw].notna().mean() < COVERAGE:
                return False
    return True


def prepare(d, feats):
    """y, X and the make-model key for one source, dropped to complete rows."""
    km_per_year = float(np.nanmedian(d["mileage_km"].to_numpy(float)
                                     / d["age_years"].to_numpy(float)))
    X = columns(d, feats, km_per_year)
    y = pd.Series(np.log(d["price_eur"].to_numpy(float)), index=d.index)
    group = d["make"].astype(str) + "|" + d["model"].astype(str)
    keep = X.notna().all(axis=1) & np.isfinite(y) & np.isfinite(X).all(axis=1)
    if keep.sum() < MIN_ROWS:
        return None
    return y[keep], X[keep], group[keep]


def levels(y, X, group):
    """Each make-model's mean price and mean features, measured on the training half only."""
    frame = X.copy()
    frame["_y"] = y
    frame["_g"] = group
    means = frame.groupby("_g", observed=True).mean()
    counts = frame.groupby("_g", observed=True).size()
    return means[counts >= MIN_GROUP]


def demean(y, X, group, means):
    """Subtract the training-half level, so only the shape of the effects is being tested."""
    ok = group.isin(means.index)
    y, X, group = y[ok], X[ok], group[ok]
    ref = means.loc[group]
    return (y.to_numpy() - ref["_y"].to_numpy(),
            X.to_numpy(float) - ref[list(X.columns)].to_numpy(float))


def solve(XtX, Xty):
    return np.linalg.pinv(XtX) @ Xty


def rmse(y, X, beta):
    return float(np.sqrt(np.mean((y - X @ beta) ** 2)))


def blend(beta_own, beta_other, XtX_own, resid_var, tau2):
    """Lean on the other datasets only as far as local noise justifies, as in lodo.py."""
    var_own = np.diag(np.linalg.pinv(XtX_own)) * resid_var
    w = np.where(tau2 + var_own > 0, tau2 / (tau2 + var_own), 1.0)
    return w * beta_own + (1 - w) * beta_other


def one_model(fitted, target):
    """One coefficient vector for every moment, the single-model alternative to one per moment.

    Trained on exactly the blocks the per-moment models use - every qualifying source's training
    half, once for each moment it qualifies for, with the fields that moment lacks set to zero -
    and scored on exactly the same test rows. So the only thing left different is one model
    against four. Missing-indicator columns would add nothing: within a make and model an absent
    field is absent for every car, so its indicator is removed along with the level.
    """
    names = list(dict.fromkeys(c for ready in fitted.values()
                               for v in ready.values() for c in v["cols"]))
    at = {c: i for i, c in enumerate(names)}
    XtX, Xty = np.zeros((len(names), len(names))), np.zeros(len(names))
    for ready in fitted.values():
        for src, v in ready.items():
            if src == target:
                continue
            ix = [at[c] for c in v["cols"]]
            XtX[np.ix_(ix, ix)] += v["XtX"]
            Xty[ix] += v["Xty"]
    beta = solve(XtX, Xty)
    return {c: beta[at[c]] for c in names}


def run_moment(by_source, feats, siblings):
    """Fit every qualifying source, then hold each out in turn."""
    ready = {}
    for src, d in by_source.items():
        if not qualifies(d, feats):
            continue
        got = prepare(d, feats)
        if got is None:
            continue
        y, X, g = got
        tr, te = split_for(src, len(y))
        means = levels(y.iloc[tr], X.iloc[tr], g.iloc[tr])
        if means.empty:
            continue
        y_tr, X_tr = demean(y.iloc[tr], X.iloc[tr], g.iloc[tr], means)
        y_te, X_te = demean(y.iloc[te], X.iloc[te], g.iloc[te], means)
        if len(y_tr) < MIN_ROWS or len(y_te) < 500:
            continue
        ready[src] = {"n": len(y), "y_tr": y_tr, "X_tr": X_tr, "y_te": y_te, "X_te": X_te,
                      "XtX": X_tr.T @ X_tr, "Xty": X_tr.T @ y_tr, "cols": list(X.columns)}

    if len(ready) < 3:
        return ready, []

    betas = {s: solve(v["XtX"], v["Xty"]) for s, v in ready.items()}
    stacked = np.vstack(list(betas.values()))
    tau2 = np.maximum(stacked.var(axis=0, ddof=1), 1e-12)

    rows = []
    for target, v in sorted(ready.items(), key=lambda kv: -kv[1]["n"]):
        others = [s for s in ready if s != target]
        XtX_o = sum(ready[s]["XtX"] for s in others)
        Xty_o = sum(ready[s]["Xty"] for s in others)
        beta_all = solve(XtX_o, Xty_o)

        biggest = max(others, key=lambda s: ready[s]["n"])
        beta_best = betas[biggest]

        # The same comparison with the held-out dataset's own market removed from both sides.
        apart = [s for s in others if s not in siblings[target]]
        gain_apart = np.nan
        if apart:
            e_all_apart = rmse(v["y_te"], v["X_te"], solve(sum(ready[s]["XtX"] for s in apart),
                                                           sum(ready[s]["Xty"] for s in apart)))
            e_best_apart = rmse(v["y_te"], v["X_te"],
                                betas[max(apart, key=lambda s: ready[s]["n"])])
            gain_apart = pct(e_all_apart, e_best_apart)

        beta_own = betas[target]
        resid_var = float(np.mean((v["y_tr"] - v["X_tr"] @ beta_own) ** 2))
        beta_hier = blend(beta_own, beta_all, v["XtX"], resid_var, tau2)

        e_own = rmse(v["y_te"], v["X_te"], beta_own)
        e_best = rmse(v["y_te"], v["X_te"], beta_best)
        e_all = rmse(v["y_te"], v["X_te"], beta_all)
        e_hier = rmse(v["y_te"], v["X_te"], beta_hier)
        rows.append({"held-out dataset": target, "test cars": f"{len(v['y_te']):,}",
                     "own": f"{e_own:.4f}", "best single other": f"{e_best:.4f}",
                     "all qualifying": f"{e_all:.4f}", "hierarchical": f"{e_hier:.4f}",
                     "pooling vs picking one": f"{(e_all - e_best) / e_best * 100:+.1f}%",
                     "_all": e_all, "_apart": gain_apart})
    return ready, rows




def same_market(by_source, share=0.2):
    """For each dataset, the others that share a market with it: a country at least a fifth of each."""
    big = {s: {c for c, v in g["country"].value_counts(normalize=True).items() if v >= share}
           for s, g in by_source.items()}
    return {s: {o for o in big if o != s and big[s] & big[o]} for s in big}


def pct(a, b):
    return (a - b) / b * 100


def effect(beta, cols, name, scale=1.0):
    """A log-price coefficient as a percentage effect; `scale` is the change in the column."""
    return float(np.expm1(beta[cols.index(name)] * scale) * 100)


def main():
    d = load()
    d = d[d["country"].isin(EUROPE) & d["price_eur"].notna()]
    by_source = {s: g for s, g in d.groupby("source", observed=True) if len(g) >= MIN_ROWS}
    siblings = same_market(by_source)
    print(f"{len(by_source)} European sources, {len(d):,} rows\n")

    fitted, tables = {}, {}
    for title, feats in MOMENTS:
        ready, rows = run_moment(by_source, feats, siblings)
        for v in ready.values():   # from here on only the test halves and the XtX sums are needed
            del v["y_tr"], v["X_tr"]
        fitted[title], tables[title] = ready, rows
        print(f"{title}\n  {len(ready)} datasets qualify, "
              f"{sum(v['n'] for v in ready.values()):,} rows")

    one = {}
    for title, rows in tables.items():
        for r in rows:
            t = r["held-out dataset"]
            if t not in one:
                one[t] = one_model(fitted, t)
            v = fitted[title][t]
            e = rmse(v["y_te"], v["X_te"], np.array([one[t][c] for c in v["cols"]]))
            r["one model, every moment"] = f"{e:.4f}"
            r["_one"] = pct(e, r["_all"])
            r["one model vs per-moment"] = f"{r['_one']:+.1f}%"

    report = [
        "# Which datasets can train the fields we actually have?", "",
        "Generated by `analysis/field_sets.py`. No new data source.", "",
        "The company does not hold the same columns as any one of our sources, and what it holds "
        "changes through the car's life. The instinct is that this forces us to pick the single "
        "dataset whose schema matches ours. It does not: **a dataset is usable if it contains the "
        "fields we are querying on**, and it may hold more besides.", "",
        "That turns the problem into a trade-off which is worth stating plainly: **every field "
        "added to the query shrinks the pool of datasets that can train it.** This measures which "
        "side of that trade wins, at each moment in a car's life.", "",
        "Every dataset is refitted on **exactly the query fields**, never on its own richer set. "
        "An age effect estimated with engine power held constant is not the same quantity as one "
        "estimated without it, so pooling the two unrefitted would average two different things.",
        "", "Scoring follows `lodo_report.md`: the within make-and-model residual, root mean "
        "squared error of log price, with the held-out dataset's own training half always "
        "supplying the price level. Lower is better; 0.30 is a typical error of roughly 30%.", "",
        "*One model, every moment* is the single-model alternative: one set of coefficients "
        "trained on exactly the same data as the per-moment models - every qualifying dataset, "
        "once for each moment it qualifies for, with the fields that moment lacks set to zero - "
        "and scored on exactly the same cars. The only thing it changes is one model against "
        "four.", "",
    ]

    summary = []
    for title, feats in MOMENTS:
        ready, rows = fitted[title], tables[title]
        n_rows = sum(v["n"] for v in ready.values())
        report += [f"## {title}", "",
                   f"**Fields:** {', '.join(feats)}  ",
                   f"**{len(ready)} datasets qualify**, {n_rows:,} cars between them.", ""]
        if not rows:
            report += ["Too few datasets carry this combination to run the comparison.", ""]
            continue
        report += [md_table(pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")}
                                          for r in rows])), ""]
        gains = [float(r["pooling vs picking one"].rstrip("%")) for r in rows]
        ones = [r["_one"] for r in rows]
        summary.append({"moment": title, "fields": len(feats),
                        "datasets qualifying": len(ready), "cars available": f"{n_rows:,}",
                        "pooling vs picking one": f"{np.mean(gains):+.1f}%",
                        "datasets where pooling won": f"{sum(g < 0 for g in gains)} of {len(rows)}",
                        "one model vs per-moment": f"{np.mean(ones):+.1f}%",
                        "datasets where one model was worse": f"{sum(o > 0 for o in ones)} of "
                                                             f"{len(rows)}"})
        print(f"  pooling vs picking one {np.mean(gains):+.1f}% | one model vs per-moment "
              f"{np.mean(ones):+.1f}%, worse in {sum(o > 0 for o in ones)} of {len(rows)}\n")

    rows = [r for t in tables.values() for r in t]
    wins = sum(float(r["pooling vs picking one"].rstrip("%")) < 0 for r in rows)
    apart = [r["_apart"] for r in rows if np.isfinite(r["_apart"])]
    gain = np.mean([float(r["pooling vs picking one"].rstrip("%")) for r in rows])
    by_ds = pd.DataFrame([{"ds": r["held-out dataset"], "gain": -float(
        r["pooling vs picking one"].rstrip("%")), "n": fitted[t][r["held-out dataset"]]["n"]}
        for t, tr in tables.items() for r in tr]).groupby("ds").agg(gain=("gain", "mean"),
                                                                     n=("n", "max"))
    small, large = by_ds["n"].idxmin(), by_ds["n"].idxmax()
    same = sum(r["own"] == r["hierarchical"] for r in rows)
    one_worse = {t: (np.mean([r["_one"] for r in tr]), sum(r["_one"] > 0 for r in tr), len(tr))
                 for t, tr in tables.items() if tr}
    order, estimated, odometer, at_return = (t for t, _ in MOMENTS)

    # Why one model loses once an odometer is known: the same cars, with and without the reading.
    odo = fitted[odometer]
    cols = next(iter(odo.values()))["cols"]
    XtX = sum(v["XtX"] for v in odo.values())
    Xty = sum(v["Xty"] for v in odo.values())
    with_odo = solve(XtX, Xty)
    keep = [i for i, c in enumerate(cols) if c != "log_mileage"]
    without = solve(XtX[np.ix_(keep, keep)], Xty[keep])
    shared = one_model(fitted, None)
    shared_beta = np.array([shared[c] for c in cols])
    diesel_with = effect(with_odo, cols, "fuel_diesel")
    diesel_without = effect(without, [cols[i] for i in keep], "fuel_diesel")
    diesel_one = effect(shared_beta, cols, "fuel_diesel")
    km_with = effect(with_odo, cols, "log_mileage", np.log(1.1))
    km_one = effect(shared_beta, cols, "log_mileage", np.log(1.1))

    report += ["## The trade-off, in one table", "",
               md_table(pd.DataFrame(summary)), "",
               "*Negative is better: it means the strategy cut the error.*", "",
               "## What this says", "",
               f"1. **If you are going to borrow, borrow from every dataset that carries your "
               f"fields, not from the one that looks closest.** Pooling beat picking the single "
               f"largest qualifying dataset in **{wins} of {len(rows)}** tests, by {-gain:.1f}% on "
               f"average. With every dataset from the held-out dataset's own country removed from "
               f"both - Poland has four scrapes and the UK two - it still won in "
               f"**{sum(a < 0 for a in apart)} of {len(apart)}**, so it is not just borrowing the "
               "same market back.",
               f"2. **The gain lands where the dataset is small.** The smallest, `{small}`, gained "
               f"{by_ds.loc[small, 'gain']:.1f}% on average; the largest, `{large}`, "
               f"{by_ds.loc[large, 'gain']:.1f}%. That is the same lesson as `lodo_report.md` from "
               "another direction: borrowing pays on thin slices.",
               f"3. **A dataset with plenty of its own data should still use it.** The "
               f"*hierarchical* column blends the local fit with the pooled one by how precisely "
               f"each effect is measured locally, and it matches *own* to four decimals in "
               f"{same} of {len(rows)} tests, because it falls back to local when local is precise. "
               "That is the correct behaviour, not a failure.",
               f"4. **The richest query has the thinnest support.** At return the company knows the "
               f"most about the car - mileage, specification, owners - and only **"
               f"{len(fitted[at_return])} of our {len(by_source)} European sources** carry all of "
               "it, too few to run the comparison. Nobody sells the dataset that would fill that "
               "gap, because it is made of the group's own returned cars. Every buy-back the ledger "
               "records builds the one source that can train the richest field set.",
               f"5. **One model for every moment does not beat a model per moment, and it loses once "
               f"an odometer is known.** Against the per-moment models it scored "
               f"{one_worse[order][0]:+.1f}% at order (worse in {one_worse[order][1]} of "
               f"{one_worse[order][2]}), {one_worse[estimated][0]:+.1f}% with mileage estimated from "
               f"age ({one_worse[estimated][1]} of {one_worse[estimated][2]}) and "
               f"**{one_worse[odometer][0]:+.1f}% with a real odometer reading (worse in "
               f"{one_worse[odometer][1]} of {one_worse[odometer][2]})**. The first two are close "
               "to a tie; the third is not.",
               f"6. **The reason is measured, and it is about stand-ins.** On the same cars, a diesel "
               f"is priced {diesel_without:+.1f}% against petrol when the model cannot see the "
               f"mileage, and {diesel_with:+.1f}% when it can: without an odometer, fuel type "
               f"stands in for the distance driven. A single model has to split the difference "
               f"({diesel_one:+.1f}%), so once the odometer is known it still marks diesels down "
               f"for mileage it can now see directly. Its mileage effect is diluted the same way: "
               f"10% more mileage costs {-km_with:.1f}% in the per-moment model and {-km_one:.1f}% "
               "in the single one. So keep a model per moment - not because one model is badly "
               "wrong at order, but because it gains nothing there and costs accuracy on the cars "
               "the group knows most about.", "",
               "## Limits", "",
               "- **Advertised prices throughout**, so this measures asking-price accuracy.",
               "- **A source counts as having a field if it is present on more than half its "
               "rows**, and rows missing it are then dropped. A source that records a field "
               "patchily is therefore excluded rather than part-used.",
               "- **The held-out dataset always supplies its own price level.** This tests whether "
               "the *shape* borrows well, which is the question. It says nothing about markets "
               "where no local cars exist at all to set a level.",
               "- **Half of each dataset is used for training.** Real thin slices are much smaller, "
               "and `lodo_report.md` shows borrowing pays far more there.",
               "- **The single model is linear.** A flexible model, gradient boosting for example, "
               "can let an effect depend on which fields are present, which is exactly what a "
               "linear model cannot do. `one_model_gbm_report.md` tests that: a boosted single "
               "model narrows the gap on the richest moment but does not close it, and boosting "
               "per moment beats the linear models outright.",
               "- **An earlier version of this comparison was not like-for-like.** It scored the "
               "single model on different cars from the per-moment models and trained it on data in "
               "which mileage was never missing, which overstated the gap at order. Do not quote "
               "figures from it.",
               "- `lv_ss` is a monthly panel with no advert id, so a car that stays listed appears "
               "once per month and its rows are observations rather than cars.", ""]
    OUT.write_text("\n".join(report))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
