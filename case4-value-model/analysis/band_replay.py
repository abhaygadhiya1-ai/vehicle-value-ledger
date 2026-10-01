"""X13 part 3: override bands replayed on real people's adjustments to a model's number.

Skeptic A11: pricers may adjust the value engine's price by ±5% (`price_band_pct`). The repair is a band tied to the
engine's own uncertainty: wide where the model is weak, tight where it is sure. No published experiment compares the
two (X13 part 1). Two public human datasets let us test the pieces on real people instead of recruiting any.

1. Dietvorst, Simmons & Massey (2018), "Overcoming algorithm aversion", Management Science 64(3), data on OSF 5nz9c.
   People forecast students' test percentiles with a model; one row per participant. What it can show: uptake under
   each band, how much of the band people use, and whether the band binds on their largest changes. It cannot replay a
   band forecast by forecast, because the file holds averages only.
2. Poursabzi-Sangdeh, Goldstein, Hofman, Wortman Vaughan & Wallach (2021), "Manipulating and measuring model
   interpretability", CHI; data on GitHub (Foroughp/Manipulating-and-Measuring-Model-Interpretability). US online
   participants priced New York apartments after seeing a model's price; one row per person and apartment, with the
   sale price. Ten apartments are typical; one (q10) has an unusual layout and the model overprices it badly. That is
   the setting of A11 in miniature, so each band rule is replayed on these real adjustments: every person's deviation
   from the model is capped at the band, and the capped price is scored against the sale price.

The tied band needs each apartment's uncertainty before its price is known. It is fixed here, before any replay:
the study's model is refitted (ordinary least squares on bathrooms and square feet, which reproduces its rounded
prices), out-of-fold log residuals come from 10-fold cross-validation on the 393 listed apartments, and an apartment's
80% half-width is the 80th percentile of the absolute residuals of its 25 nearest listed apartments in the eight
standardised features, excluding the apartment's own listings. 50 neighbours is shown beside as a check.

Band rules: model only (no change), free adjustment, fixed caps of ±5%, ±10% and ±20%, and tied caps scaled so their
average over the eleven apartments equals each fixed cap (the same latitude, redistributed by uncertainty), plus the
full local 80% band.

Limits, stated rather than solved: post-hoc capping is not behaviour under a cap (Dietvorst's people adjusted less
under a cap, using about half of it); eleven apartments and one unusual one; lay US participants with no private
information beyond the listing, while real pricers see the car; prices were entered in steps of $0.1m.

Checks: the published figures are reproduced from both files before anything new is computed (Dietvorst's uptake
and deviations; Poursabzi-Sangdeh's deviations and simulation errors in Figure 3); the refitted model reproduces the
study's rounded prices; the clipping rule passes a toy case; tied caps average exactly the fixed cap they match.

Usage: .venv/bin/python analysis/band_replay.py   (writes analysis/band_replay_report.md, under a minute)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_unified import md_table  # noqa: E402

RAW = HERE.parent / "data/raw"
DV = RAW / "x13_dietvorst/data.xlsx"
PS = RAW / "x13_poursabzi"
OUT = HERE / "band_replay_report.md"
SEED = 7
K_NEAR = 25                   # neighbours for an apartment's local uncertainty; 50 shown as a check
FOLDS = 10
LEVEL = 0.8                   # an 80% band, the value engine's own
CAPS = (0.05, 0.10, 0.20)
MODEL_CONDS = {"C0": "BB-2", "C1": "CLEAR-2", "C2": "BB-8", "C3": "CLEAR-8"}   # conditions shown the model
FEATURES = ["bedrooms", "baths", "sqft", "total_rooms", "maintenance_fee", "days_on_the_market", "subway_distance",
            "school_distance"]
MODEL_FEATURES = ["baths", "sqft"]    # the study's two-feature model
UNUSUAL = 10                          # q_id of the unusual apartment with a sale price; q11 has none (-1)


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


# ---------------------------------------------------------------- Dietvorst et al. 2018, one row per participant

def dietvorst():
    x = pd.ExcelFile(DV)
    out = {}
    for study in (1, 2):
        d = x.parse(f"Study {study} Data")
        d = d[pd.to_numeric(d["Condition"], errors="coerce").notna()].copy()
        for c in d.columns:
            if c not in ("ResponseID", "StartDate"):
                d[c] = pd.to_numeric(d[c], errors="coerce")
        out[study] = d
    return out


def dietvorst_tables(dv):
    s1, s2 = dv[1], dv[2]
    names1 = {1: "can't change", 2: "adjust by up to 10", 3: "change 10 forecasts", 4: "use freely"}
    names2 = {1: "can't change", 2: "adjust by up to 10", 3: "adjust by up to 5", 4: "adjust by up to 2"}
    rows = []
    for study, d, names in ((1, s1, names1), (2, s2, names2)):
        for c, g in d.groupby("Condition"):
            users = g[g["ModelBonus"].eq(1)]
            rows.append({"study": study, "condition": names[int(c)], "n": len(g),
                         "chose the model": pct(g["ModelBonus"].mean()) if g["ModelBonus"].notna().any() else "n/a",
                         "deviation of model users": f"{users['AvDiffFromModel'].mean():.2f}" if len(users) else ""})
    uptake = pd.DataFrame(rows)

    # how much of the band model users used, and whether it bound on their largest changes (Study 1 only)
    lat = []
    for c, cap in ((2, 10), (3, 5), (4, 2)):
        u = s2[s2["Condition"].eq(c) & s2["ModelBonus"].eq(1)]
        share = u["AvDiffFromModel"] / cap
        lat.append({"band (percentiles)": f"±{cap}", "model users": len(u), "mean share of band used": pct(share.mean()),
                    "median": pct(share.median()), "quarter using over": pct(share.quantile(0.75))})
    latitude = pd.DataFrame(lat)

    a10 = s1[s1["Condition"].eq(2) & s1["ModelBonus"].eq(1)]
    free = s1[s1["Condition"].eq(4)]
    bind = pd.DataFrame([
        {"group": "adjust by up to 10, model users", "n": len(a10),
         "mean of their 10 largest changes": f"{a10['AvgLargest10Changes'].mean():.2f}",
         "share whose 10 largest average 9.5 or more": pct(a10["AvgLargest10Changes"].ge(9.5).mean())},
        {"group": "use freely (no cap)", "n": len(free),
         "mean of their 10 largest changes": f"{free['AvgLargest10Changes'].mean():.2f}",
         "share whose 10 largest average 9.5 or more": pct(free["AvgLargest10Changes"].ge(9.5).mean())},
    ])
    return uptake, latitude, bind


def dietvorst_checks(dv):
    """The paper's own figures (pp. 1159 and 1161), from its file."""
    s1, s2 = dv[1], dv[2]
    up1 = s1.groupby("Condition")["ModelBonus"].mean()
    up2 = s2.groupby("Condition")["ModelBonus"].mean()
    dev2 = s2[s2["ModelBonus"].eq(1)].groupby("Condition")["AvDiffFromModel"].mean()
    expect = [("Study 1 uptake, can't change", up1[1], 0.32), ("Study 1 uptake, adjust by 10", up1[2], 0.76),
              ("Study 1 uptake, change 10", up1[3], 0.73), ("Study 2 uptake, can't change", up2[1], 0.47),
              ("Study 2 uptake, adjust by 10", up2[2], 0.71), ("Study 2 uptake, adjust by 5", up2[3], 0.71),
              ("Study 2 uptake, adjust by 2", up2[4], 0.68)]
    rows = [(n, round(v, 2), e, abs(v - e) <= 0.005) for n, v, e in expect]
    for c, e in ((2, 5.00), (3, 2.61), (4, 1.33)):
        rows.append((f"Study 2 deviation of model users, condition {c}", round(dev2[c], 2), e, abs(dev2[c] - e) < 0.006))
    free = s1[s1["Condition"].eq(4)]["AvDiffFromModel"].mean()
    cant = s1[s1["Condition"].eq(1)]["HumModelAvDiff"].mean()
    rows += [("Study 1 deviation, use freely", round(free, 2), 8.18, abs(free - 8.18) < 0.006),
             ("Study 1 deviation, can't change", round(cant, 2), 18.66, abs(cant - 18.66) < 0.006)]
    return pd.DataFrame(rows, columns=["figure", "from the file", "published", "match"])


# ---------------------------------------------------------------- Poursabzi-Sangdeh et al. 2021, one row per answer

def responses():
    frames = []
    for e in (1, 2, 3):
        d = pd.read_csv(PS / f"data_exp{e}_data.csv")
        d["exp"] = e
        frames.append(d)
    return frames


def paper_check(exp1):
    """Figure 3 of the paper: mean deviation from the model and mean simulation error, $k, typical apartments."""
    lab = {**MODEL_CONDS, "C4": "NO-MODEL"}
    n = exp1[exp1["q_id"] < 10].assign(cond=lambda t: t["condition"].map(lab))
    n = n.assign(dev=(n["final_pred"] - n["model_pred"]).abs(), sim=(n["user_model_pred"] - n["model_pred"]).abs())
    per = n.groupby(["cond", "worker_id"])[["dev", "sim"]].mean().groupby("cond").mean() * 1e3
    published = {"CLEAR-2": (155, 132), "CLEAR-8": (164, 261), "BB-2": (144, 206), "BB-8": (151, 239)}
    rows = []
    for c, (dev, sim) in published.items():
        rows.append((f"{c} deviation, $k", round(per.loc[c, "dev"]), dev, round(per.loc[c, "dev"]) == dev))
        rows.append((f"{c} simulation error, $k", round(per.loc[c, "sim"]), sim, round(per.loc[c, "sim"]) == sim))
    return pd.DataFrame(rows, columns=["figure", "from the file", "published", "match"])


def fit_ols(X, y):
    X1 = np.c_[np.ones(len(X)), X]
    b, *_ = np.linalg.lstsq(X1, y, rcond=None)
    return b


def predict(b, X):
    return np.c_[np.ones(len(X)), X] @ b


def local_uncertainty(pool, test, k):
    """Each test apartment's 80% half-width on the log scale, from its neighbours' out-of-fold residuals."""
    rng = np.random.default_rng(SEED)
    folds = rng.integers(0, FOLDS, len(pool))
    resid = np.empty(len(pool))
    for f in range(FOLDS):
        tr, te = folds != f, folds == f
        b = fit_ols(pool.loc[tr, MODEL_FEATURES].values, pool.loc[tr, "price"].values)
        resid[te] = np.log(pool.loc[te, "price"].values / predict(b, pool.loc[te, MODEL_FEATURES].values))
    mu, sd = pool[FEATURES].mean(), pool[FEATURES].std()
    zp = ((pool[FEATURES] - mu) / sd).values
    zt = ((test[FEATURES] - mu) / sd).values
    own = ["bedrooms", "baths", "sqft", "total_rooms", "maintenance_fee"]
    out = []
    for i in range(len(test)):
        same = (pool[own].values == test[own].values[i]).all(axis=1)      # the apartment's own listings
        dist = np.sqrt(((zp - zt[i]) ** 2).sum(axis=1))
        dist[same] = np.inf
        near = np.argsort(dist)[:k]
        out.append(np.quantile(np.abs(resid[near]), LEVEL))
    return np.array(out)


def clip_ratio(final, model, cap):
    """The price a pricer could set: the model's price moved by the person's own move, capped at ±cap."""
    move = final / model - 1
    return model * (1 + np.clip(move, -cap, cap))


def replay(ans, caps_by_q, label):
    cap = ans["q_id"].map(caps_by_q).values
    p = clip_ratio(ans["final_pred"].values, ans["model_pred"].values, cap)
    ape = np.abs(p - ans["actual_price"].values) / ans["actual_price"].values
    t = ans.assign(ape=ape, typical=ans["q_id"] < 10)
    return {"rule": label,
            "typical apartments": pct(t.loc[t["typical"], "ape"].mean(), 1),
            "unusual apartment": pct(t.loc[~t["typical"], "ape"].mean(), 1),
            "all eleven": pct(t["ape"].mean(), 1)}


def main():
    dv = dietvorst()
    d_checks = dietvorst_checks(dv)
    uptake, latitude, bind = dietvorst_tables(dv)

    frames = responses()
    p_checks = paper_check(frames[0])

    pool = pd.read_csv(PS / "data_apartments_all_apartments.csv")
    test = pd.read_csv(PS / "data_apartments_test_samples.csv")
    b = fit_ols(pool[MODEL_FEATURES].values, pool["price"].values / 1e6)
    refit = np.round(predict(b, test[MODEL_FEATURES].values), 1)
    shown = pd.concat(frames).query("condition in @MODEL_CONDS and condition in ['C0', 'C1']")
    shown = shown.groupby("q_id")["model_pred"].first()
    q = np.arange(12)
    refit_match = int((np.round(refit[:12], 1) == shown.reindex(q).values).sum())

    u25 = local_uncertainty(pool, test, K_NEAR)[:11]
    u50 = local_uncertainty(pool, test, 2 * K_NEAR)[:11]
    half25 = np.exp(u25) - 1
    half50 = np.exp(u50) - 1

    # the model's own error on each apartment, for the table only (never used to set a band)
    apts = pd.DataFrame({"apartment": [f"q{i}" + (" (unusual)" if i == UNUSUAL else "") for i in range(11)],
                         "model's price, $m": shown.reindex(range(11)).values,
                         "sale price, $m": (test["actual_price"].values[:11] / 1e6).round(2),
                         "model's error": [pct(abs(m / a - 1)) for m, a in
                                           zip(shown.reindex(range(11)).values, test["actual_price"].values[:11] / 1e6)],
                         "local 80% half-width (25 nearest)": [pct(h) for h in half25],
                         "rank": pd.Series(-half25).rank().astype(int).values,
                         "(50 nearest)": [pct(h) for h in half50]})

    ans = pd.concat(frames)
    ans = ans[ans["condition"].isin(MODEL_CONDS) & ans["q_id"].le(UNUSUAL) & ans["actual_price"].gt(0)
              & ans["final_pred"].gt(0)].copy()
    ans["model_pred"] = ans["model_pred"].astype(float)

    rules = [replay(ans, {i: 0.0 for i in range(11)}, "model only"),
             replay(ans, {i: np.inf for i in range(11)}, "free adjustment (as people answered)")]
    tied_mean_check = []
    for cap in CAPS:
        rules.append(replay(ans, {i: cap for i in range(11)}, f"fixed ±{pct(cap)}"))
        scaled = half25 * cap / half25.mean()
        tied_mean_check.append(abs(scaled.mean() - cap) < 1e-12)
        rules.append(replay(ans, dict(enumerate(scaled)), f"tied, same average (±{pct(cap)})"))
    rules.append(replay(ans, dict(enumerate(half25)), f"tied, the full local 80% band (average ±{pct(half25.mean())})"))
    table = pd.DataFrame(rules)

    # check with 50 neighbours: the same comparison at the ±10% average
    alt = []
    for cap in CAPS:
        scaled = half50 * cap / half50.mean()
        alt.append(replay(ans, dict(enumerate(scaled)), f"tied (50 nearest), same average (±{pct(cap)})"))
    alt = pd.DataFrame(alt)

    # weight of advice on real price estimates (experiment 3: own estimate first, then the model's)
    e3 = frames[2]
    e3 = e3[e3["condition"].isin(MODEL_CONDS) & e3["q_id"].le(UNUSUAL)
            & (e3["model_pred"] - e3["user_init_pred"]).abs().gt(1e-9)].copy()
    e3["woa"] = ((e3["final_pred"] - e3["user_init_pred"]) / (e3["model_pred"] - e3["user_init_pred"])).clip(0, 1)
    e3["own_closer"] = ((e3["user_init_pred"] - e3["actual_price"]).abs()
                        < (e3["model_pred"] - e3["actual_price"]).abs())
    typ, unu = e3[e3["q_id"] < 10], e3[e3["q_id"].eq(UNUSUAL)]
    model_err_unusual = abs(shown[UNUSUAL] / (test["actual_price"].values[UNUSUAL] / 1e6) - 1)
    woa_rows = pd.DataFrame([
        {"apartments": "typical (q0-q9)", "answers": len(typ), "median weight on the model": f"{typ['woa'].median():.2f}",
         "mean": f"{typ['woa'].mean():.2f}", "own first price closer to the sale price than the model's": pct(
             typ["own_closer"].mean())},
        {"apartments": f"unusual (q10), where the model is {pct(model_err_unusual)} too high", "answers": len(unu),
         "median weight on the model": f"{unu['woa'].median():.2f}", "mean": f"{unu['woa'].mean():.2f}",
         "own first price closer to the sale price than the model's": pct(unu["own_closer"].mean())},
    ])

    # how much of the model's error people's own first prices carried (their private signal), and its spread
    def signal(t):
        s = np.log(t["user_init_pred"] / t["model_pred"])
        e = np.log(t["actual_price"] / t["model_pred"])
        return float(np.corrcoef(s, e)[0, 1] ** 2), float(s.std() / e.std())
    e3s = e3[e3["user_init_pred"].gt(0)]
    r2_all, spread_all = signal(e3s)
    r2_typ, spread_typ = signal(e3s[e3s["q_id"] < 10])
    sig_rows = pd.DataFrame([
        {"apartments": "all eleven", "share of the model's error their own first price carried (R²)": f"{r2_all:.3f}",
         "spread of own view against spread of the model's error": f"{spread_all:.2f}"},
        {"apartments": "typical (q0-q9)", "share of the model's error their own first price carried (R²)": f"{r2_typ:.3f}",
         "spread of own view against spread of the model's error": f"{spread_typ:.2f}"},
    ])
    params = pd.DataFrame([
        ("weight_on_model_median", float(e3["woa"].median()), "median weight on the model's price, experiment 3, all eleven"),
        ("signal_r2_all", r2_all, "R² of the model's log error on people's own first log move, all eleven apartments"),
        ("signal_r2_typical", r2_typ, "the same on the ten typical apartments"),
        ("signal_spread_all", spread_all, "sd of people's own first log move over sd of the model's log error"),
    ], columns=["key", "value", "description"])
    params.to_csv(HERE / "band_replay_params.csv", index=False)

    toy = np.allclose(clip_ratio(np.array([1.3, 0.8, 1.02]), np.array([1.0, 1.0, 1.0]), 0.05), [1.05, 0.95, 1.02])
    checks = pd.concat([d_checks, p_checks], ignore_index=True)
    all_ok = bool(checks["match"].all()) and toy and all(tied_mean_check) and refit_match >= 11

    # what the tables show, read from them rather than typed
    s2 = dv[2]
    up_fixed = s2[s2["Condition"].eq(1)]["ModelBonus"].mean()
    up_band = s2[s2["Condition"].isin([2, 3, 4])].groupby("Condition")["ModelBonus"].mean()
    share_used = [float(r.strip("%")) for r in latitude["mean share of band used"]]
    unusual_rank = int(apts["rank"].iloc[UNUSUAL])
    allr = table.set_index("rule")["all eleven"].str.rstrip("%").astype(float)
    gaps = [abs(allr[f"fixed ±{pct(c)}"] - allr[f"tied, same average (±{pct(c)})"]) for c in CAPS]
    typr = table.set_index("rule")["typical apartments"].str.rstrip("%").astype(float)
    unur = table.set_index("rule")["unusual apartment"].str.rstrip("%").astype(float)
    findings = [
        f"- **Any band gets the model used; its width barely matters.** Uptake rose from {pct(up_fixed)} with no "
        f"adjustment to {pct(up_band.min())}-{pct(up_band.max())} with a band of 2, 5 or 10 percentiles.",
        f"- **People use part of the band, not all of it:** {share_used[0]:.0f}%, {share_used[1]:.0f}% and "
        f"{share_used[2]:.0f}% of a ±10, ±5 and ±2 band on average. Only {bind.iloc[0, 3]} of capped model users "
        f"pressed against the cap on their largest changes, against {bind.iloc[1, 3]} of free adjusters who went "
        "beyond it: a cap scales moves down, it doesn't just trim the big ones.",
        f"- **People weight the model the same where it is badly wrong.** On the unusual apartment the median weight "
        f"on the model was {woa_rows.iloc[1, 2]}, as on typical ones ({woa_rows.iloc[0, 2]}), although "
        f"{woa_rows.iloc[1, 4]} of their own first prices were closer to the sale price there, against "
        f"{woa_rows.iloc[0, 4]} on typical apartments. This is naive advice weighting on real price estimates.",
        f"- **With no private information, the model alone was best on typical apartments** ({typr['model only']}%) "
        f"and free adjustment worst ({typr['free adjustment (as people answered)']}%). Free adjustment was best only "
        f"on the unusual apartment ({unur['free adjustment (as people answered)']}% against "
        f"{unur['model only']}% for the model).",
        f"- **The tied band did no better than a fixed one of the same average width** (within {max(gaps):.1f} "
        f"points on all eleven), because the uncertainty measure ranked the unusual apartment {unusual_rank} of 11: "
        "it did not flag where the model was wrong. A band tied to uncertainty is only as good as the uncertainty's "
        "ability to flag the model's large errors. Part 4 tests that on the value engine's own band.",
    ]

    lines = [
        "# X13 part 3: override bands replayed on real people's adjustments",
        "",
        "Generated by `analysis/band_replay.py`. Two public human datasets, no recruitment. Dietvorst, Simmons & Massey "
        "(2018; Wharton lab and online samples; OSF 5nz9c) and Poursabzi-Sangdeh et al. (2021; US online participants "
        "pricing New York apartments, so **US data**; GitHub). Every figure here is from their files.",
        "",
        "## Checks",
        "",
        f"- Published figures reproduced from the files: {int(checks['match'].sum())} of {len(checks)}.",
        f"- The refitted two-feature model reproduces the study's rounded model price on {refit_match} of 12 apartments.",
        f"- Clipping rule on a toy case: {'passes' if toy else 'FAILS'}. Tied caps average the fixed cap they match: "
        f"{'yes' if all(tied_mean_check) else 'NO'}.",
        f"- All checks pass: {'yes' if all_ok else 'NO'}.",
        "",
        md_table(checks.assign(match=checks["match"].map({True: "yes", False: "NO"}))),
        "",
        "## What it shows",
        "",
        *findings,
        "",
        "## 1. Dietvorst et al.: uptake and how much of a band people use (no private information)",
        "",
        md_table(uptake),
        "",
        "Deviation is the mean absolute distance from the model's forecast, in percentiles, for participants who chose "
        "the model. How much of the band they used (Study 2):",
        "",
        md_table(latitude),
        "",
        "Did the cap bind on people's largest changes? (Study 1: the mean of each person's 10 largest distances from the "
        "model.)",
        "",
        md_table(bind),
        "",
        "## 2. Poursabzi-Sangdeh et al.: each apartment's uncertainty, fixed before the replay",
        "",
        "The local 80% half-width comes from the listed apartments nearest in all eight features, never from the sale "
        "price of the apartment itself. The model's error is shown beside it, to see whether the uncertainty flags the "
        "apartment the model gets wrong.",
        "",
        md_table(apts),
        "",
        "## 3. The replay: mean absolute error against the sale price, by band rule",
        "",
        f"{len(ans):,} answers from {ans['worker_id'].nunique():,} people in the four conditions shown the model "
        "(experiments 1-3). Each person's own move from the model's price is capped at the band; the capped price is "
        "scored against the sale price. Ten typical apartments and one unusual one, as in the experiment.",
        "",
        md_table(table),
        "",
        "With 50 neighbours for the uncertainty (a check on the one choice made):",
        "",
        md_table(alt),
        "",
        "## 4. Weight on the model, on real price estimates (experiment 3)",
        "",
        "People gave their own price first, then saw the model's. Weight on the model = (final - own) / (model - own), "
        "clipped to 0-1, for answers where the two differed.",
        "",
        md_table(woa_rows),
        "",
        "How much of the model's error did people's own first prices carry? The share of the variance of the model's "
        "log error explained by each person's own first log move away from the model (lay people who saw only the "
        "listing; part 4 uses it as one reference point for a pricer's information, written to "
        "`band_replay_params.csv`):",
        "",
        md_table(sig_rows),
        "",
        "## Limits",
        "",
        "- Capping afterwards is not behaviour under a cap. Under a cap, Dietvorst's people moved less than the cap "
        "allowed, so a real cap shrinks moves further than this replay does.",
        "- Eleven apartments, one of them unusual; the pooled column weights them as the experiment did. How often a "
        "car is 'unusual' for the engine is set by our own data in part 4, not here.",
        "- Lay US participants who saw only the listing; real pricers see the car. Prices were entered in steps of "
        "$0.1m, which is coarse for the cheapest apartments.",
        "- Dietvorst's task gave people nothing the model lacked, so any adjustment could only cost accuracy there.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.name}; checks pass: {all_ok}")


if __name__ == "__main__":
    main()
