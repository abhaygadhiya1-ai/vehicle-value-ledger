"""The uplift engine: who an offer would *change*, not who would respond anyway.

The readiness engine says which cars are about to come to market. That is not the same as which
customers an approach would change, and the difference is where a retention budget is wasted: a
customer who was going to upgrade anyway costs money to contact and produces nothing.

Nobody publishes a randomised trial in automotive finance - the case's group would have to run its
own - so the coefficients here are not transferable and are not offered as such. **What is
transferable is the machine and the test.** This builds the estimator and validates it on a
dataset where the treatment really was randomised, so what is handed over is a working method with
a measured answer to the only question that matters: does targeting by uplift beat targeting by
likelihood of response?

Data: the MineThatData E-Mail Analytics and Data Mining Challenge (Kevin Hillstrom, 2008), 64,000
customers randomised one third to no e-mail, one third to a men's campaign, one third to a
women's. Randomised by the publisher, which is what makes it usable.
`http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv`

Three models, and the third is the one companies actually run:

  * **Two-model (T-learner)** - fit response among the treated and among the untreated, and
    subtract. Simple, and noisy because two errors add.
  * **Class transformation** - relabel the outcome so a single model estimates the uplift
    directly. One model, one error. Weighted so the two arms count equally: unweighted, the
    relabelling is only valid on a 50/50 split, and Hillstrom's is two to one.
  * **Response model** - ignore the treatment and target whoever is most likely to respond. This
    is the baseline to beat. **On this data the uplift models do not beat it**, which is the
    finding, and the reason the deliverable is a measurement rather than a recommendation.

Scored with the Qini coefficient and with uplift at the top decile, on a held-out half.

Usage: .venv/bin/python analysis/uplift_engine.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import md_table  # noqa: E402
from loaders.common import http_download  # noqa: E402

HERE = Path(__file__).parent
RAW = HERE.parent / "data" / "raw" / "hillstrom" / "hillstrom.csv"
URL = ("http://www.minethatdata.com/"
       "Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv")
OUT = HERE / "uplift_engine_report.md"
CURVE = HERE / "uplift_engine_qini.csv"

OUTCOME = "visit"
SEED = 20260921
DECILE = 0.10
REFITS = 10
MODELS = ("Class transformation", "Two-model (T-learner)", "Response model (the usual way)")


def load():
    if not RAW.exists():
        print("  downloading Hillstrom (~4 MB)")
        http_download(URL, RAW)
    d = pd.read_csv(RAW)
    d["treated"] = (d["segment"] != "No E-Mail").astype(int)
    feats = ["recency", "history", "mens", "womens", "newbie"]
    for col in ("zip_code", "channel", "history_segment"):
        for v in sorted(d[col].unique())[1:]:
            name = f"{col}={v}"
            d[name] = (d[col] == v).astype(float)
            feats.append(name)
    return d, feats


def fit_predict(X_tr, y_tr, X_te, weight=None):
    m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.06, max_depth=4,
                                       random_state=SEED)
    m.fit(X_tr, y_tr, sample_weight=weight)
    return m.predict_proba(X_te)[:, 1]


def qini(score, treated, outcome):
    """The Qini curve, and the area between it and targeting at random.

    Walk the population from the highest score down. At each point, the incremental response is
    the treated responders so far minus the untreated responders so far, rescaled to the same
    number of people. A model that finds persuadable customers lifts the curve above the diagonal;
    a model that finds people who would have responded anyway does not.
    """
    order = np.argsort(-score)
    t, y = treated[order], outcome[order]
    nt = np.cumsum(t)
    nc = np.cumsum(1 - t)
    yt = np.cumsum(y * t)
    yc = np.cumsum(y * (1 - t))
    with np.errstate(invalid="ignore", divide="ignore"):
        curve = yt - yc * np.where(nc > 0, nt / np.maximum(nc, 1), 0.0)
    curve = np.nan_to_num(curve)
    n = len(score)
    overall = curve[-1]
    frac = np.arange(1, n + 1) / n
    random = overall * frac
    area = float(np.trapezoid(curve - random, frac))
    return curve, random, frac, area, float(overall)


def uplift_at(score, treated, outcome, frac=DECILE):
    """The measured uplift among the top slice the model picks."""
    k = max(int(len(score) * frac), 1)
    top = np.argsort(-score)[:k]
    t, y = treated[top], outcome[top]
    if t.sum() == 0 or (1 - t).sum() == 0:
        return np.nan
    return float(y[t == 1].mean() - y[t == 0].mean())


def bootstrap(scores, treated, outcome, draws=400):
    """Resample the held-out half to see whether the models really differ.

    Two rankings of the same 32,000 people, scored on the same outcome, will differ by chance.
    Without this the table invites a story about a winner that the data does not support.
    """
    rng = np.random.default_rng(SEED + 1)
    n = len(outcome)
    keys = list(scores)
    out = {k: [] for k in keys}
    for _ in range(draws):
        i = rng.integers(0, n, n)
        t, y = treated[i], outcome[i]
        for k in keys:
            out[k].append(uplift_at(scores[k][i], t, y))
    return {k: np.array(v) for k, v in out.items()}


def score_models(Xtr, ttr, ytr, Xte):
    """The three models, fitted on one training set and scored on the held-out customers."""
    # 1. two models, subtracted
    s_two = fit_predict(Xtr[ttr == 1], ytr[ttr == 1], Xte) - fit_predict(Xtr[ttr == 0], ytr[ttr == 0], Xte)

    # 2. class transformation: z = 1 when treated-and-responded or untreated-and-not. Weighting
    #    each arm by 0.5 over its share of the trial makes the split 50/50, and then a single model
    #    on z estimates the uplift directly: 2 P(z=1|x) - 1. Hillstrom's split is two to one (two
    #    e-mail arms, one control), so unweighted the score would be part uplift, part response.
    p = ttr.mean()
    z = (ytr == ttr).astype(int)
    s_ct = 2 * fit_predict(Xtr, z, Xte, weight=np.where(ttr == 1, 0.5 / p, 0.5 / (1 - p))) - 1

    # 3. what a company does without uplift: target the most likely responder
    s_resp = fit_predict(Xtr, ytr, Xte)
    return s_ct, s_two, s_resp


def refits(Xtr, ttr, ytr, Xte, tte, yte, k=REFITS, share=0.8):
    """Refit every model on random subsamples of the training half, scored on the same held-out half.

    The bootstrap resamples the held-out customers only, so it says nothing about how much a
    model's answer depends on the customers it was trained on. Uplift is a small difference
    between two noisy rates, and a model fitted to it can depend on its training draw far more
    than a response model does.
    """
    rng = np.random.default_rng(SEED + 2)
    out = []
    for _ in range(k):
        i = rng.choice(len(ytr), int(share * len(ytr)), replace=False)
        for name, s in zip(MODELS, score_models(Xtr[i], ttr[i], ytr[i], Xte)):
            out.append({"Model": name, "top": uplift_at(s, tte, yte), "Qini": qini(s, tte, yte)[3]})
    return pd.DataFrame(out).groupby("Model", sort=False).agg(
        top_mean=("top", "mean"), top_min=("top", "min"), top_max=("top", "max"),
        qini_mean=("Qini", "mean"), qini_min=("Qini", "min"), qini_max=("Qini", "max"))


def main():
    d, feats = load()
    rng = np.random.default_rng(SEED)
    test = rng.random(len(d)) < 0.5
    tr, te = d[~test], d[test]
    Xtr, Xte = tr[feats].to_numpy(float), te[feats].to_numpy(float)
    ttr, tte = tr["treated"].to_numpy(), te["treated"].to_numpy()
    ytr, yte = tr[OUTCOME].to_numpy(), te[OUTCOME].to_numpy()
    print(f"{len(d):,} customers, {d['treated'].mean():.0%} treated, "
          f"{OUTCOME} rate {d[OUTCOME].mean():.1%}; {len(te):,} held out")

    base_lift = yte[tte == 1].mean() - yte[tte == 0].mean()

    s_ct, s_two, s_resp = score_models(Xtr, ttr, ytr, Xte)

    # 4. the floor: no model at all
    s_rand = rng.random(len(te))

    rows, curves = [], {}
    for name, s in (("Class transformation", s_ct), ("Two-model (T-learner)", s_two),
                    ("Response model (the usual way)", s_resp), ("Random", s_rand)):
        curve, random, frac, area, overall = qini(s, tte, yte)
        rows.append({"Model": name, "Qini": area,
                     "uplift_top": uplift_at(s, tte, yte),
                     "vs_average": uplift_at(s, tte, yte) / base_lift if base_lift else np.nan})
        curves[name] = curve
    res = pd.DataFrame(rows)

    scores = {"Class transformation": s_ct, "Two-model (T-learner)": s_two,
              "Response model (the usual way)": s_resp, "Random": s_rand}
    boot = bootstrap(scores, tte, yte)
    res["lo"] = [np.nanquantile(boot[m], 0.025) for m in res["Model"]]
    res["hi"] = [np.nanquantile(boot[m], 0.975) for m in res["Model"]]
    uplift_models = ["Class transformation", "Two-model (T-learner)"]
    gaps = {m: boot[m] - boot["Response model (the usual way)"] for m in uplift_models}
    gap_best = max(gaps, key=lambda m: np.nanmean(gaps[m]))
    g = gaps[gap_best]
    g_mean, g_lo, g_hi = np.nanmean(g), np.nanquantile(g, 0.025), np.nanquantile(g, 0.975)
    rf = refits(Xtr, ttr, ytr, Xte, tte, yte)
    rand_top = res[res["Model"] == "Random"]["uplift_top"].iloc[0]

    lines = [
        "# The uplift engine, built and validated on a randomised trial",
        "",
        f"{len(d):,} customers, randomly assigned by the publisher: a third got no e-mail, two "
        f"thirds got one. {len(te):,} held out. The outcome is a visit. **Across everyone the "
        f"campaign lifts visits by {base_lift:+.1%}** - that is what an untargeted send buys.",
        "",
        "The question is not who visits. It is who visits *because they were contacted*. Those "
        "are different people, and the table says how different.",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Model": res["Model"],
        "Qini": res["Qini"].map("{:+.1f}".format),
        f"Uplift in the top {DECILE:.0%}": res["uplift_top"].map("{:+.2%}".format),
        "95% range": [f"{lo:+.2%} to {hi:+.2%}" for lo, hi in zip(res["lo"], res["hi"])],
        "Against an untargeted send": res["vs_average"].map("{:.2f}x".format),
    })))
    lines += [
        "",
        "## Headline",
        "",
        "*In a table so `check_assumptions.py` can pin each figure to its own cell.*",
        "",
        md_table(pd.DataFrame([
            {"What": "Best uplift model against the response model, top decile",
             "Figure": f"{g_mean * 100:+.2f}"},
            {"What": "...low end of its range", "Figure": f"{g_lo * 100:+.2f}"},
            {"What": "...high end of its range", "Figure": f"{g_hi * 100:+.2f}"},
            {"What": "Customers in the trial", "Figure": f"{len(d):,}"},
            *({"What": f"{m}, top-decile uplift, mean of {REFITS} refits",
               "Figure": f"{rf.loc[m, 'top_mean'] * 100:+.2f}"} for m in MODELS),
        ])),
        "",
        "## The result, which is not the one the technique is usually sold with",
        "",
        f"**No uplift model beats the ordinary response model.** The best uplift approach here is "
        f"{gap_best.lower()}; against the response model "
        f"its top-decile uplift differs by **{g_mean:+.2%} ({g_lo:+.2%} to {g_hi:+.2%})**, a range "
        "that comfortably contains zero.",
        "",
        f"What *is* clear is that a response model is worth having: its top decile shows "
        f"{res[res['Model'] == MODELS[2]]['uplift_top'].iloc[0]:+.2%} against {rand_top:+.2%} for a "
        f"random tenth, and {base_lift:+.1%} for sending to everybody.",
        "",
        "**So the honest recommendation is not \"build an uplift model\".** It is: build the "
        "measurement first, and let it decide. On this dataset the extra machinery earns nothing "
        "over a plain response model, and a team that had assumed otherwise would have spent a "
        "quarter finding out. The group's own pilot may well answer differently - automotive "
        "replacement is a considered, once-every-few-years decision, where who-would-have-anyway "
        "and who-can-be-moved plausibly diverge far more than they do for a clothing e-mail. "
        "**That is a reason to measure it, not a reason to assume it.**",
        "",
        "## Does the answer depend on the training draw?",
        "",
        f"The bootstrap above resamples the held-out customers; the models stay fixed. Here each model "
        f"is refitted on {REFITS} random 80% subsamples of the training half and scored on the same "
        "held-out half.",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Model": list(MODELS),
        "Top-decile uplift, mean": [f"{rf.loc[m, 'top_mean']:+.2%}" for m in MODELS],
        "lowest": [f"{rf.loc[m, 'top_min']:+.2%}" for m in MODELS],
        "highest": [f"{rf.loc[m, 'top_max']:+.2%}" for m in MODELS],
        "Qini, mean": [f"{rf.loc[m, 'qini_mean']:+.1f}" for m in MODELS],
        "Qini, lowest": [f"{rf.loc[m, 'qini_min']:+.1f}" for m in MODELS],
        "Qini, highest": [f"{rf.loc[m, 'qini_max']:+.1f}" for m in MODELS],
    })))
    lines += [
        "",
        f"**The response model barely moves; the uplift models fall and scatter.** Averaged over the "
        f"refits, the uplift models reach {rf.loc[MODELS[0], 'top_mean']:+.2%} and "
        f"{rf.loc[MODELS[1], 'top_mean']:+.2%} in the top decile, against the response model's "
        f"{rf.loc[MODELS[2], 'top_mean']:+.2%}; a random tenth gives {rand_top:+.2%}. The single fit in "
        "the first table is one draw. Uplift is a small difference between two noisy rates, and a "
        "model fitted to it learns noise as readily as signal. So the negative result stands, and "
        "firmer: on this trial the response model is the steadier one, and no refit average favours "
        "an uplift model.",
        "",
        "## What transfers and what does not",
        "",
        "- **No coefficient transfers.** This is a 2008 clothing retailer's e-mail campaign. "
        "Nothing in it is about cars, finance, or a five-figure decision.",
        "- **The machine and the test transfer.** `qini()`, `uplift_at()`, `bootstrap()` and the "
        "three estimators take any table with a randomised flag and an outcome. Pointed at the "
        "group's own pilot they answer the same question about the group's own customers - "
        "including the question of whether uplift modelling is worth doing at all.",
        "- **It needs a randomised holdout, and that is the ask.** Uplift cannot be measured on "
        "past campaign data, because whoever was contacted was chosen. A pilot has to hold back a "
        "random control group. That is a business decision before it is a technical one, and it "
        "is the single thing the group must supply that no public data can.",
        "- **The outcome is a visit, not a purchase.** Conversion in this data is under one per "
        "cent, too thin to rank on.",
        "- **One trial here.** A negative on Hillstrom is not a negative everywhere; it is the "
        "reason to run the test rather than the answer to it. `uplift_second.py` repeats the test "
        "on two more public trials, each tested for randomisation first.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    pd.DataFrame({"frac": np.arange(1, len(te) + 1) / len(te),
                  **{k: v for k, v in curves.items()}}).iloc[::200].to_csv(CURVE, index=False)
    print(f"wrote {OUT.name}")
    for _, r in res.iterrows():
        print(f"  {r['Model']:32s} Qini {r['Qini']:+7.1f}  top-decile uplift "
              f"{r['uplift_top']:+.2%}  ({r['vs_average']:.2f}x)")


if __name__ == "__main__":
    main()
