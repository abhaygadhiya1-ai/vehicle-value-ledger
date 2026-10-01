"""X15 part 3: does the uplift engine's negative result hold on a second randomised trial?

The uplift engine (`uplift_engine.py`) was validated on one randomised trial, the Hillstrom e-mail campaign, and on it
no uplift model beat the ordinary response model at targeting (register `up_gap_vs_response`). One trial is one trial.
This runs a corrected version of the same machine on the Hillstrom trial again and on the two large public uplift
datasets, after first testing whether each is really randomised.

  Hillstrom e-mail  the uplift engine's own trial: 64,000 customers, two thirds e-mailed at random; outcome a visit.
  Lenta SMS         Lenta's SMS campaign (Russian grocery retailer; the BigTarget hackathon, 2020, distributed by the
                    scikit-uplift project): 687,029 customers, about three quarters sent an SMS; outcome a store visit.
                    Its documentation gives a treatment ratio but does not say assignment was random.
                    https://sklift.s3.eu-west-2.amazonaws.com/lenta_dataset.csv.gz
  Criteo ads        Criteo AI Lab's uplift dataset v2.1: 13.9 million users from advertisers' incrementality tests that
                    withheld ads from a random subset, pooled after subsampling every test to one treatment ratio
                    (Diemert et al. 2021, arXiv 2111.10106, which validates it with a classifier two-sample test). A
                    fixed 20% random sample. `exposure` happens after assignment and is never a feature.
                    https://huggingface.co/datasets/criteo/criteo-uplift
Lenta and Criteo are downloaded once into data/raw/ (private).

Two randomisation tests, before any model. (1) Every feature's standardised mean difference between the arms must lie
within a Bonferroni bound, z(1 - 0.05 / 2k) x sqrt(1 / n1 + 1 / n0) for k features. (2) Criteo's own check, a classifier
two-sample test: a model predicting treatment from the features, cross-fitted in two halves, against a constant; its
AUC and the z of its log-loss gain. In a clean trial neither finds anything.

The models are the uplift engine's (the same gradient boosting settings; a held-out half), corrected for unequal arms:
the class transformation is fitted with inverse-propensity weights, 0.5 / e(x) for treated and 0.5 / (1 - e(x)) for
control, e(x) the cross-fitted propensity. Unweighted on an unequal split (Hillstrom's is two to one), the
class-transformed score mixes the response rate into the uplift; the uplift engine now weights by the design's split.
Uplift in the
top decile is scored the same way: treated and control means weighted by 1 / e(x) and 1 / (1 - e(x)). In a clean
trial e(x) is flat and this changes nothing; where treatment is mildly predictable it removes the observable part of
the imbalance, assuming no hidden selection. Confidence ranges resample the held-out half (400 draws).

Checks: on a simulated trial with 75% treated, a planted uplift on one feature and a planted baseline on another, the
weighted class transformation recovers the uplift and ignores the baseline, while the unweighted one mixes the baseline
in; with a constant propensity the weighted top-decile uplift equals the plain one exactly; each dataset's Qini curve
ends at its overall incremental response and its uplift over everyone is the difference in means.

Usage: .venv/bin/python analysis/uplift_second.py   (writes analysis/uplift_second_report.md, ~20 minutes)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
import uplift_engine  # noqa: E402
from uplift_engine import DECILE, SEED, qini, uplift_at  # noqa: E402

RAW = HERE.parent / "data" / "raw"
OUT = HERE / "uplift_second_report.md"
REGISTER = HERE.parent / "assumptions.csv"
CRITEO_SHARE = 0.2
DRAWS = 400
CLIP = 0.01
MODELS = ("Class transformation (weighted)", "Two-model (T-learner)", "Response model (the usual way)", "Random")


def load_hillstrom():
    d, feats = uplift_engine.load()
    return d[feats].astype(np.float32).reset_index(drop=True), d["treated"].to_numpy(), \
        d[uplift_engine.OUTCOME].to_numpy()


def load_lenta():
    d = pd.read_csv(RAW / "lenta" / "lenta_dataset.csv.gz")
    t = (d["group"] == "test").to_numpy().astype(np.int8)
    y = d["response_att"].to_numpy().astype(np.int8)
    extra = pd.DataFrame({"gender=M": d["gender"].isin(["М", "M"]).astype(np.float32),     # Cyrillic and Latin
                          "gender=missing": (d["gender"].isna() | (d["gender"] == "Не определен")).astype(np.float32)})
    X = pd.concat([d.drop(columns=["group", "gender", "response_att"]).astype(np.float32), extra], axis=1)
    return X, t, y


def load_criteo():
    cols = [f"f{i}" for i in range(12)]
    d = pd.read_csv(RAW / "criteo" / "criteo-research-uplift-v2.1.csv.gz",
                    dtype={**{c: np.float32 for c in cols}, "treatment": np.int8, "visit": np.int8,
                           "conversion": np.int8, "exposure": np.int8})
    keep = np.random.default_rng(SEED).random(len(d)) < CRITEO_SHARE
    d = d[keep]
    return d[cols].reset_index(drop=True), d["treatment"].to_numpy(), d["visit"].to_numpy()


DATASETS = {"Hillstrom e-mail": load_hillstrom, "Lenta SMS": load_lenta,
            f"Criteo ads, {CRITEO_SHARE:.0%} sample": load_criteo}


def model():
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.06, max_depth=4, random_state=SEED)


def fit_predict(X_tr, y_tr, X_te, weight=None):
    """The uplift engine's model and settings, with optional sample weights."""
    return model().fit(X_tr, y_tr, sample_weight=weight).predict_proba(X_te)[:, 1]


def smd(x, t):
    """Standardised mean difference between the arms, ignoring missing values."""
    a, b = x[t == 1], x[t == 0]
    s = np.sqrt((np.nanvar(a) + np.nanvar(b)) / 2)
    return 0.0 if s == 0 else float((np.nanmean(a) - np.nanmean(b)) / s)


def propensity(X, t):
    """The chance of treatment given the features, cross-fitted in two halves; and the two-sample test on it."""
    fold = np.random.default_rng(SEED + 7).random(len(t)) < 0.5
    e = np.empty(len(t))
    for a in (True, False):
        e[fold == a] = model().fit(X[fold != a], t[fold != a]).predict_proba(X[fold == a])[:, 1]
    e = np.clip(e, CLIP, 1 - CLIP)
    const = t.mean()
    gain = -(t * np.log(const) + (1 - t) * np.log(1 - const)) + (t * np.log(e) + (1 - t) * np.log(1 - e))
    z = gain.mean() / (gain.std(ddof=1) / np.sqrt(len(gain)))
    return e, float(roc_auc_score(t, e)), float(z)


def randomisation(X, t):
    s = pd.Series({c: smd(X[c].to_numpy(), t) for c in X.columns}).abs()
    bound = norm.ppf(1 - 0.05 / (2 * len(s))) * np.sqrt(1 / t.sum() + 1 / (1 - t).sum())
    return {"largest": float(s.max()), "worst": s.idxmax(), "bound": float(bound), "above": int((s >= bound).sum()),
            "features": len(s)}


def ipw(t, e):
    return np.where(t == 1, 1 / e, 1 / (1 - e))


def uplift_w(score, t, y, w, frac=DECILE):
    """Top-slice uplift with treated and control means weighted by inverse propensity."""
    k = max(int(len(score) * frac), 1)
    top = np.argsort(-score)[:k]
    tt, yy, ww = t[top], y[top], w[top]
    if tt.sum() == 0 or (1 - tt).sum() == 0:
        return np.nan
    return float((ww * yy * tt).sum() / (ww * tt).sum() - (ww * yy * (1 - tt)).sum() / (ww * (1 - tt)).sum())


def bootstrap_w(scores, t, y, w, draws=DRAWS):
    rng = np.random.default_rng(SEED + 1)
    out = {k: [] for k in scores}
    for _ in range(draws):
        i = rng.integers(0, len(y), len(y))
        for k, s in scores.items():
            out[k].append(uplift_w(s[i], t[i], y[i], w[i]))
    return {k: np.array(v) for k, v in out.items()}


def toy_check():
    rng = np.random.default_rng(SEED)
    n = 60_000
    x = rng.normal(size=(n, 3)).astype(np.float32)
    t = (rng.random(n) < 0.75).astype(int)
    uplift = 0.10 * (x[:, 0] > 0)                          # planted: 10 points of uplift on feature 0
    base = 0.10 + 0.30 * (x[:, 1] > 0)                     # planted: 30 points of baseline on feature 1
    y = (rng.random(n) < base + uplift * t).astype(int)
    half = rng.random(n) < 0.5
    z = (y == t).astype(int)
    e = np.full(n, t.mean())
    out = {}
    for label, w in (("weighted", 0.5 * ipw(t, e)[~half]), ("unweighted", None)):
        s = 2 * fit_predict(x[~half], z[~half], x[half], w) - 1
        xh = x[half]
        out[label] = (float(s[xh[:, 0] > 0].mean() - s[xh[:, 0] <= 0].mean()),
                      float(s[xh[:, 1] > 0].mean() - s[xh[:, 1] <= 0].mean()))
    passes = (abs(out["weighted"][0] - 0.10) <= 0.03 and abs(out["weighted"][1]) <= 0.03
              and abs(out["unweighted"][1]) > 0.10)
    rows = [{"check": "simulated trial, 75% treated, 10 points of uplift on one feature and 30 of baseline on another: "
                      "the weighted class transformation recovers the uplift (within 3 points) and ignores the "
                      "baseline (within 3), while the unweighted one mixes the baseline in (more than 10)",
             "got": f"weighted: uplift {out['weighted'][0]:+.3f}, baseline {out['weighted'][1]:+.3f}; "
                    f"unweighted: baseline {out['unweighted'][1]:+.3f}", "passes": passes}]
    s = rng.random(n)
    a, b = uplift_w(s, t, y, ipw(t, e)), uplift_at(s, t, y)
    rows.append({"check": "with a constant propensity the weighted top-decile uplift equals the plain one",
                 "got": f"{a:+.6f} and {b:+.6f}", "passes": abs(a - b) < 1e-12})
    return rows


def analyse(name, X, t, y):
    rnd = randomisation(X, t)
    e, auc, z_c2st = propensity(X, t)
    rng = np.random.default_rng(SEED)
    test = rng.random(len(y)) < 0.5
    Xtr, Xte = X[~test], X[test]
    ttr, tte, ytr, yte, etr, ete = t[~test], t[test], y[~test], y[test], e[~test], e[test]
    wte = ipw(tte, ete)
    base_plain = yte[tte == 1].mean() - yte[tte == 0].mean()
    base_adj = uplift_w(np.zeros(len(yte)), tte, yte, wte, frac=1.0)
    p1 = fit_predict(Xtr[ttr == 1], ytr[ttr == 1], Xte)
    p0 = fit_predict(Xtr[ttr == 0], ytr[ttr == 0], Xte)
    z = (ytr == ttr).astype(int)
    scores = dict(zip(MODELS, (2 * fit_predict(Xtr, z, Xte, 0.5 * ipw(ttr, etr)) - 1, p1 - p0,
                               fit_predict(Xtr, ytr, Xte), rng.random(len(yte)))))
    boot = bootstrap_w(scores, tte, yte, wte)
    rows = []
    for m, s in scores.items():
        rows.append({"model": m, "Qini (unadjusted)": f"{qini(s, tte, yte)[3]:+.1f}",
                     f"uplift in the top {DECILE:.0%}, unadjusted (points)": f"{100 * uplift_at(s, tte, yte):+.2f}",
                     f"uplift in the top {DECILE:.0%}, adjusted (points)": f"{100 * uplift_w(s, tte, yte, wte):+.2f}",
                     "95% range, adjusted (points)": f"{100 * np.nanquantile(boot[m], 0.025):+.2f} to "
                                                     f"{100 * np.nanquantile(boot[m], 0.975):+.2f}"})
    gaps = {m: boot[m] - boot["Response model (the usual way)"] for m in MODELS[:2]}
    best = max(gaps, key=lambda m: np.nanmean(gaps[m]))
    g = gaps[best]

    s = scores["Response model (the usual way)"]
    overall = qini(s, tte, yte)[4]
    expected = yte[tte == 1].sum() - yte[tte == 0].sum() * tte.sum() / (1 - tte).sum()
    book = {"check": f"{name}: the Qini curve ends at the overall incremental response, and the uplift over everyone "
                     "is the difference in means",
            "got": f"{overall:,.1f} incremental responses",
            "passes": abs(overall - expected) < 1e-6 and abs(uplift_at(s, tte, yte, frac=1.0) - base_plain) < 1e-12}
    tests = {"dataset": name, "customers": f"{len(y):,}", "treated": f"{t.mean():.0%}",
             "largest standardised difference": f"{rnd['largest']:.4f} ({rnd['worst']})",
             "bound chance allows": f"{rnd['bound']:.4f}",
             "features beyond it": f"{rnd['above']} of {rnd['features']}",
             "classifier AUC predicting treatment": f"{auc:.3f}",
             "log-loss gain z": f"{z_c2st:.1f}"}
    head = [
        {"what": f"{name}: overall uplift, held-out half, adjusted (points)", "figure": f"{100 * base_adj:+.2f}"},
        {"what": f"{name}: best uplift model ({best}) against the response model, top decile, adjusted (points)",
         "figure": f"{100 * np.nanmean(g):+.2f}"},
        {"what": f"{name}: its 95% range, low (points)", "figure": f"{100 * np.nanquantile(g, 0.025):+.2f}"},
        {"what": f"{name}: its 95% range, high (points)", "figure": f"{100 * np.nanquantile(g, 0.975):+.2f}"}]
    return tests, head, pd.DataFrame(rows), book


def main():
    tests, heads, sections, ck = [], [], [], toy_check()
    reg = pd.read_csv(REGISTER).set_index("id")["value"]
    for name, loader in DATASETS.items():
        X, t, y = loader()
        tt, head, table, book = analyse(name, X, t, y)
        del X
        tests.append(tt)
        heads += head
        ck.append(book)
        sections += [f"## {name}", "", f"{tt['customers']} customers, {tt['treated']} treated.", "", md_table(table), ""]
        print(f"done {name}")
    heads.append({"what": "Hillstrom as published by the uplift engine, unadjusted "
                          "(register up_gap_vs_response, points)", "figure": f"{reg['up_gap_vs_response']:+.2f}"})
    ck = pd.DataFrame(ck)
    lines = [
        "# X15 part 3: the uplift engine on a second randomised trial",
        "",
        "Generated by `analysis/uplift_second.py`; the method is in its docstring. The question, as in the uplift "
        "engine: does targeting by uplift beat targeting by likelihood of response? Adjusted figures weight treated "
        "and control by the inverse of the cross-fitted propensity; in a clean trial they equal the unadjusted ones.",
        "",
        "## Randomisation tests (before any model)",
        "",
        md_table(pd.DataFrame(tests)),
        "",
        "A clean trial shows no feature beyond the bound and an AUC near 0.5 with a small z. **Lenta** fails both "
        "plainly: treatment is predictable from its customers' history (its documentation never says assignment was "
        "random), so its uplift results are not evidence even adjusted, since hidden selection cannot be ruled out. "
        "**Criteo** is nearly balanced, as its publisher's own check found, but not perfectly at this sample size; its "
        "adjusted results remove the observable imbalance. **Hillstrom** is the reference.",
        "",
        "## Headline",
        "",
        md_table(pd.DataFrame(heads)),
        "",
        *sections,
        "## Checks",
        "",
        md_table(ck),
        "",
        "## Limits",
        "",
        "- **Not cars.** An e-mail, a grocery SMS and display advertising test the machine on real trials; the "
        "coefficients do not transfer, and the group would run its own trial (part 2 sizes it).",
        "- **Not European, and Criteo's features are anonymised.** The question answered is methodological.",
        "- **Adjustment assumes no hidden selection.** It removes the part of an imbalance the features explain.",
        "- **One contact, one outcome window each.** Uplift from a longer or costlier contact may differ.",
        "- **The ranges are test-sample noise only.** Refitted on other training draws, the uplift models scatter "
        "far more than the response model (`uplift_engine_report.md`, on Hillstrom), so these ranges understate "
        "the uncertainty of an uplift model's win; they cannot create one.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(pd.DataFrame(tests).to_string(index=False))
    print(pd.DataFrame(heads).to_string(index=False))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
