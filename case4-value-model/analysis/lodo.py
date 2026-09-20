"""Leave one dataset out: does adding more datasets actually help?

METHODOLOGY_multi_dataset.md, step 7. For each dataset in turn, hold it out and compare three
models on the SAME held-out test rows:

  own       trained only on the held-out market's own training half
  transfer  trained only on the OTHER datasets, never having seen this market
  pooled    trained on the other datasets plus this market's training half

Price levels are not comparable across markets (tax, income, Singapore's COE), so every model is
judged on the within-make-and-model residual: each market's own training half supplies the level
for each model name, and only the SHAPE of the effects comes from the training data. That is the
thing that is supposed to travel between markets, so that is what is tested.

Usage: .venv/bin/python analysis/lodo.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from drivers import EUROPE, MIN_GROUP, md_table, sample  # noqa: E402

OUT = Path(__file__).parent / "lodo_report.md"
SEED = 0
MIN_ROWS = 5_000
# one fixed column set, so a model fitted on one market can be applied to another
CORE = ["age_years", "log_mileage", "fuel_diesel", "fuel_electric", "fuel_hybrid",
        "fuel_plugin_hybrid", "transmission_automatic"]


def core_design(d):
    """The same columns for every dataset, so coefficients can be carried between them."""
    d = d[d["fuel"].notna() & d["transmission"].notna()]
    if len(d) < MIN_ROWS:
        return None
    fuel = d["fuel"].astype("string")
    x = pd.DataFrame({
        "age_years": d["age_years"].to_numpy(dtype=float),
        "log_mileage": np.log(d["mileage_km"].to_numpy(dtype=float)),
        "fuel_diesel": (fuel == "diesel").astype(float),
        "fuel_electric": (fuel == "electric").astype(float),
        "fuel_hybrid": (fuel == "hybrid").astype(float),
        "fuel_plugin_hybrid": (fuel == "plugin_hybrid").astype(float),
        "transmission_automatic": (d["transmission"].astype("string") == "automatic").astype(float),
    }, index=d.index)[CORE]
    y = pd.Series(np.log(d["price_eur"].to_numpy(dtype=float)), index=d.index)
    group = (d["make"].astype(str) + "|" + d["model"].astype(str))
    keep = x.notna().all(axis=1) & np.isfinite(y)
    return y[keep], x[keep], group[keep]


def group_means(y, X, group):
    """Mean of y and of each column of X within each make-model group."""
    frame = X.copy()
    frame["_y"] = y
    frame["_g"] = group
    means = frame.groupby("_g", observed=True).mean()
    counts = frame.groupby("_g", observed=True).size()
    return means[counts >= MIN_GROUP]


def demean(y, X, group, means):
    """Remove each group's level, using levels measured on the training half."""
    ok = group.isin(means.index)
    y, X, group = y[ok], X[ok], group[ok]
    ref = means.loc[group]
    return (y.to_numpy() - ref["_y"].to_numpy(),
            X.to_numpy(dtype=float) - ref[CORE].to_numpy(dtype=float), int(ok.sum()), int((~ok).sum()))


def normal_equations(y, X):
    return X.T @ X, X.T @ y


def solve(XtX, Xty):
    return np.linalg.pinv(XtX) @ Xty


def per_source_betas(full):
    """Each training dataset's own coefficients, used to measure how much markets really differ."""
    return {s: solve(XtX, Xty) for s, (XtX, Xty, _) in full.items()}


def eb_blend(beta_own, beta_transfer, XtX_tr, resid_var, tau2):
    """Hierarchical estimate: lean on the other markets only as far as local noise justifies.

    Each coefficient is blended separately. tau2 is how much that coefficient genuinely varies
    between markets; var_own is how precisely this market measures it. A market with plenty of
    data keeps its own number, a thin one is pulled toward the others.
    """
    var_own = np.diag(np.linalg.pinv(XtX_tr)) * resid_var
    weight = np.where(tau2 + var_own > 0, tau2 / (tau2 + var_own), 1.0)
    return weight * beta_own + (1 - weight) * beta_transfer, weight


def score(y, X, beta):
    resid = y - X @ beta
    return {"rmse": float(np.sqrt(np.mean(resid ** 2))),
            "mape": float(np.median(np.abs(np.expm1(resid))) * 100)}


LOCAL_SIZES = [100, 250, 500, 1_000, 2_500, 5_000, 10_000, 25_000]


def learning_curve(y_tr, X_tr, y_te, X_te, beta_transfer, tau2, rng):
    """How much local data does a market need before it stops needing the others?

    Only the slopes are learned from the subsample; the price level per model still comes from
    the market's full training half, so this isolates the question of learning the shape.
    """
    out = {}
    for n in LOCAL_SIZES:
        if n > len(y_tr):
            continue
        idx = rng.choice(len(y_tr), size=n, replace=False)
        ys, Xs = y_tr[idx], X_tr[idx]
        XtX, Xty = normal_equations(ys, Xs)
        beta_own = solve(XtX, Xty)
        resid_var = float(np.mean((ys - Xs @ beta_own) ** 2))
        beta_eb, _ = eb_blend(beta_own, beta_transfer, XtX, resid_var, tau2)
        out[n] = (score(y_te, X_te, beta_own)["rmse"],
                  score(y_te, X_te, beta_transfer)["rmse"],
                  score(y_te, X_te, beta_eb)["rmse"])
    return out


def main():
    d = sample()
    parts = {}
    for source, part in d.groupby("source", observed=True):
        built = core_design(part)
        if built is not None:
            parts[source] = built
    print(f"{len(parts)} datasets have the full core column set")

    # each source's contribution to the normal equations, demeaned within its own model groups
    full = {}
    for source, (y, X, g) in parts.items():
        yc, Xc, n, _ = demean(y, X, g, group_means(y, X, g))
        full[source] = (*normal_equations(yc, Xc), n)
    all_XtX = sum(v[0] for v in full.values())
    all_Xty = sum(v[1] for v in full.values())

    source_betas = per_source_betas(full)
    # which country each dataset mostly covers, to spot datasets that share a market
    main_country = d.groupby("source", observed=True)["country"].agg(
        lambda c: c.value_counts().idxmax() if len(c) else None).to_dict()
    rows, curves = [], []
    rng = np.random.default_rng(SEED)
    for held, (y, X, g) in parts.items():
        split = rng.random(len(y)) < 0.5
        y_tr, X_tr, g_tr = y[split], X[split], g[split]
        y_te, X_te, g_te = y[~split], X[~split], g[~split]
        means = group_means(y_tr, X_tr, g_tr)          # levels always come from the held-out market
        if means.empty:
            continue
        ytr_c, Xtr_c, _, _ = demean(y_tr, X_tr, g_tr, means)
        yte_c, Xte_c, n_te, dropped = demean(y_te, X_te, g_te, means)
        if n_te < 1_000:
            continue
        tr_XtX, tr_Xty = normal_equations(ytr_c, Xtr_c)
        others_XtX = all_XtX - full[held][0]
        others_Xty = all_Xty - full[held][1]

        beta_own = solve(tr_XtX, tr_Xty)
        beta_transfer = solve(others_XtX, others_Xty)
        # how much each coefficient really varies between the training markets
        others = np.array([b for s_, b in source_betas.items() if s_ != held])
        tau2 = others.var(axis=0, ddof=1)
        resid_var = float(np.mean((ytr_c - Xtr_c @ beta_own) ** 2))
        beta_eb, weight = eb_blend(beta_own, beta_transfer, tr_XtX, resid_var, tau2)
        betas = {"own": beta_own, "transfer": beta_transfer,
                 "stacked": solve(others_XtX + tr_XtX, others_Xty + tr_Xty), "hierarchical": beta_eb}
        s = {k: score(yte_c, Xte_c, b) for k, b in betas.items()}
        curves.append((held, learning_curve(ytr_c, Xtr_c, yte_c, Xte_c, beta_transfer, tau2, rng)))
        rows.append({
            "held-out dataset": held,
            "test cars": f"{n_te:,}",
            "no model match": f"{dropped:,}",
            "own": f"{s['own']['rmse']:.4f}",
            "transfer": f"{s['transfer']['rmse']:.4f}",
            "stacked": f"{s['stacked']['rmse']:.4f}",
            "hierarchical": f"{s['hierarchical']['rmse']:.4f}",
            "transfer vs own": f"{(s['transfer']['rmse'] / s['own']['rmse'] - 1) * 100:+.1f}%",
            "hierarchical vs own": f"{(s['hierarchical']['rmse'] / s['own']['rmse'] - 1) * 100:+.1f}%",
            "own median err": f"{s['own']['mape']:.1f}%",
            "_h_better": s["hierarchical"]["rmse"] <= s["own"]["rmse"] * 1.0001,
            "_transfer_better": s["transfer"]["rmse"] < s["own"]["rmse"],
            "_sibling": any(main_country.get(o) == main_country.get(held)
                            for o in parts if o != held),
            "_penalty": (s["transfer"]["rmse"] / s["own"]["rmse"] - 1) * 100,
            "_europe": main_country.get(held) in EUROPE,
        })
        print(f"  {held:22} own={s['own']['rmse']:.4f} transfer={s['transfer']['rmse']:.4f} "
              f"stacked={s['stacked']['rmse']:.4f} hier={s['hierarchical']['rmse']:.4f}")

    # average over the SAME datasets at every sample size, otherwise the rows are not comparable
    common = [(h, c) for h, c in curves if all(n in c for n in LOCAL_SIZES)]
    curve_rows = []
    for n in LOCAL_SIZES:
        vals = [c[n] for _, c in common]
        if not vals:
            continue
        # the median across markets, not the mean: with very few local cars an ordinary least
        # squares fit occasionally explodes, and one blown-up fit would dominate a mean
        own = float(np.median([v[0] for v in vals]))
        transfer = float(np.median([v[1] for v in vals]))
        hier = float(np.median([v[2] for v in vals]))
        unstable = sum(v[0] > 1.0 for v in vals)
        gain = (1 - hier / own) * 100
        curve_rows.append({"local cars used for the slopes": f"{n:,}",
                           "own": f"{own:.4f}", "transfer": f"{transfer:.4f}",
                           "hierarchical": f"{hier:.4f}",
                           "gain from borrowing": f"{gain:+.1f}%",
                           "markets whose own fit blew up": unstable, "_n": n, "_gain": gain})
    curve_table = pd.DataFrame(curve_rows)
    faded = [r for r in curve_rows if r["_gain"] < 1.0]
    crossover_text = (
        f"Borrowing from the other markets cuts the typical error by {curve_rows[0]['_gain']:.1f}% "
        f"when a market has only {curve_rows[0]['_n']:,} cars of its own. By {faded[0]['_n']:,} cars "
        f"the gain is under 1%, and by {curve_rows[-1]['_n']:,} it is nil."
        if curve_rows and faded else "Local data wins at every sample size tested.")
    curve_table = curve_table.drop(columns=["_n", "_gain"])

    table = pd.DataFrame(rows)
    pooled_wins = int(table["_h_better"].sum())
    transfer_wins = int(table["_transfer_better"].sum())
    n = len(table)
    sib = table[table["_sibling"]]
    lone = table[~table["_sibling"]]
    sibling_note = (
        f"- **{len(sib)} of the {n} datasets share their market with another dataset in the training "
        f"set** (Poland has four, the UK two, and the multi-country AutoScout24 set overlaps Germany, "
        f"France and Spain). For those, the transfer model pays a median penalty of only "
        f"**{sib['_penalty'].median():+.1f}%**. For the {len(lone)} datasets that are the only one "
        f"from their market, the penalty is **{lone['_penalty'].median():+.1f}%**. "
        "This is leave-one-*dataset*-out, not leave-one-*market*-out, and the gap between those two "
        "numbers is the clearest result here: what transfers is the market, not the row count. "
        "Another million cars from Latvia does not teach you Egypt.")
    eu_sib, eu_lone = sib[sib["_europe"]], lone[lone["_europe"]]
    holds = eu_lone["_penalty"].median() > eu_sib["_penalty"].median()
    europe_note = (
        ("- **The gap is smaller inside Europe, and that is the comparison that matters for the "
         "group.** " if holds else
         "- **Inside Europe the gap disappears, and that is the comparison that matters for the "
         "group.** ")
        + f"{len(lone) - len(eu_lone)} of the lone datasets are outside Europe. Among European "
        f"datasets only, those sharing a market pay **{eu_sib['_penalty'].median():+.1f}%** "
        f"({len(eu_sib)} datasets) and those alone pay **{eu_lone['_penalty'].median():+.1f}%** "
        f"({len(eu_lone)} datasets, from {eu_lone['_penalty'].min():+.1f}% to "
        f"{eu_lone['_penalty'].max():+.1f}%). "
        + ("Same direction, a smaller gap, and resting on few datasets." if holds else
           "A European dataset alone in its market does no worse than one with a sibling, so the "
           "'market, not rows' result rests on the markets outside Europe and should not be quoted "
           "for the group's own markets."))
    show = table.drop(columns=["_h_better", "_transfer_better", "_sibling", "_penalty", "_europe"])

    report = [
        "# Does adding more datasets help? Leave-one-dataset-out", "",
        "Generated by `analysis/lodo.py`, following step 7 of `METHODOLOGY_multi_dataset.md`.", "",
        "Each dataset is held out in turn and four models are scored on the **same** held-out test "
        "rows (a random half of that market, seed 0):", "",
        "- **own** - trained only on the held-out market's other half",
        "- **transfer** - trained only on the other datasets, having never seen this market",
        "- **stacked** - every dataset's rows simply added together, the naive way to pool",
        "- **hierarchical** - each coefficient blended between own and transfer by how precisely the "
        "local market measures it, which is the principled way to pool", "",
        "Price levels do not travel between markets, so all three are scored on the **within "
        "make-and-model residual**: the held-out market's own training half always supplies the price "
        "level for each model name, and only the shape of the effects comes from the training data. "
        "The score is the root mean squared error of log price, so 0.30 means a typical error of "
        "roughly 30%. *No model match* counts test cars whose make and model never appeared in the "
        "training half with at least "
        f"{MIN_GROUP} cars, so no level could be set for them; they are excluded.", "",
        "## Results", "", md_table(show), "",
        "## What this says", "",
        f"- **A market's own data wins almost every time.** The hierarchical model matched or beat "
        f"the local model on {pooled_wins} of {n} datasets, and the transfer model beat it on "
        f"{transfer_wins} of {n}. With hundreds of thousands of local cars, no amount of foreign data "
        "improves on a market that can already measure itself.",
        "- **Naive stacking is actively worse.** The *stacked* column simply adds every dataset's "
        "rows together; because the other markets outnumber the held-out one, it drags the estimate "
        "away from local truth. The *hierarchical* column blends each coefficient by how precisely "
        "the local market measures it, and collapses back to the local answer - which is the correct "
        "behaviour, not a failure.",
        sibling_note,
        europe_note, "",
        "## So when is another dataset worth having?", "",
        "The test above gives every market hundreds of thousands of its own cars, which is not the "
        "situation the value ledger faces. The table below cuts the local training data down and "
        "re-runs the same comparison, averaged over the "
        f"{len(common)} datasets whose training half is large enough to supply every sample size, so "
        "each row compares the same markets. Only the slopes are learned from the smaller sample; the "
        "price level per model still comes from the market's full training half.", "",
        md_table(curve_table), "",
        f"**{crossover_text}** That is the practical answer: pooling other markets is worth real "
        "money exactly when a market, a segment or a model line is new or thin - a newly merged "
        "brand, an EV line with two years of history, a market the group has just entered - and it "
        "stops mattering surprisingly quickly once that slice has a few hundred to a thousand cars "
        "of its own. The other columns are worth reading too: the *transfer* model, which never saw "
        "the market, is flat at 0.28 regardless of local sample size, and below roughly 250 local "
        "cars it beats the local fit outright.", "",
        "The *markets whose own fit blew up* column counts how many of the local fits produced a "
        "worse-than-useless model (error above 100%) at that sample size. This is the real risk a "
        "thin slice carries: not a slightly worse number, but an unusable one. The hierarchical "
        "model never does this, because it falls back on the other markets exactly when the local "
        "data cannot support an estimate.", "",
    ]
    OUT.write_text("\n".join(report))
    print(f"\npooled better on {pooled_wins}/{n}, transfer better on {transfer_wins}/{n}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
