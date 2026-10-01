"""X7 part 4a: does a Markov-switching model spot a falling market better than X6's signal?

X6 part 5 found that the level's position predicts the downside: contracts started when the level sat below its own
three-year average lost far more, so the re-mark raises the charge when the level falls below trend. The user asked
whether a Markov chain would do better. A regime model (Hamilton 1989) lets the market move between hidden states,
here "rising" and "falling", and gives at each month the probability that the market is in the falling one.

Point forecasts from such models rarely beat a random walk (Engel, NBER w4210), so this judges the model where X6
needs it: the downside. Same markets, windows, outcome, leave-one-market-out fit and placebo as X6 part 5
(`level_charge.py`, whose functions are reused unchanged). The only difference is the signal:
  gap       X6's: the log level less its average log over the previous 36 months
  falling   the filtered probability of the falling regime at the contract's start month

The model, per market: two regimes on monthly log changes, each with its own mean and variance (statsmodels
MarkovRegression). The fit runs five searches of 20 random starts each (seeds 7-11, passed to statsmodels' own `rng`,
which np.random does not control) and keeps the best likelihood; a search that fails numerically is skipped and
counted, since one bad start can break the EM step. A second variant lets only the mean switch (one variance): the
main model's regimes turned out to be calm against jumpy months, and one variance forces them to differ in
direction. "Falling" is the regime with the lower mean. The probabilities are filtered, so each month's uses no
later month given the parameters; the parameters are fitted on the market's full history. That favours the Markov signal: if it still
does not beat the gap, the result stands; if it does, it needs a real-time re-check before use. A market whose index
is unchanged in more than half its months (Greece) is not a monthly series and no regime model fits it, so it is left
out of both signals.

Checks: on a toy series with a known falling stretch the model finds it; the filtered probabilities up to a month do
not change when the later data are cut (given the parameters); the Markov windows are X6's windows exactly; every
market is held out once and every window predicted once; the fit is reproducible on the market with the most
unchanged months.

Usage: .venv/bin/python analysis/level_regimes.py   (writes analysis/level_regimes_report.md, ~2 minutes)
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
from level_charge import leave_one_out, placebo, shortfall, signal_windows  # noqa: E402
from level_risk import EUROPE, EUROSTAT, load  # noqa: E402

OUT = HERE / "level_regimes_report.md"
SEED = 7
STARTS = 20
SEEDS = range(7, 12)   # five searches; the best likelihood is kept
CONTRACTS = (36, 48)
MAX_FLAT = 0.5          # a market whose index is unchanged in more than half its months is not a monthly series


def fit(x, switching_variance=True):
    """Two regimes on a series of monthly log changes (in %), each with its own mean and variance. Returns the fit with
    the best likelihood over the searches, and how many searches failed numerically."""
    best, failed = None, 0
    for seed in SEEDS:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = MarkovRegression(x, k_regimes=2, trend="c", switching_variance=switching_variance).fit(
                    search_reps=STARTS, rng=seed, disp=False)   # statsmodels draws its starts from `rng`, not np.random
        except (np.linalg.LinAlgError, RuntimeError, ValueError):
            failed += 1
            continue
        if not np.isfinite(res.llf):
            failed += 1
        elif best is None or res.llf > best.llf:
            best = res
    if best is None:
        raise RuntimeError("no search converged")
    return best, failed


def falling(series, switching_variance=True):
    """Per month: the filtered probability of the lower-mean regime, and the fitted model's summary."""
    x = np.diff(np.log(series.to_numpy(dtype=float))) * 100
    res, failed = fit(x, switching_variance)
    par = dict(zip(res.model.param_names, res.params))
    fall = int(np.argmin([par["const[0]"], par["const[1]"]]))
    rise = 1 - fall
    p = np.asarray(res.filtered_marginal_probabilities)[:, fall]
    stay = {0: par["p[0->0]"], 1: 1 - par["p[1->0]"]}
    sd = {r: np.sqrt(par.get(f"sigma2[{r}]", par.get("sigma2", np.nan))) for r in (0, 1)}
    info = {"falling mean (% a year)": 12 * par[f"const[{fall}]"], "rising mean (% a year)": 12 * par[f"const[{rise}]"],
            "monthly SD, falling (%)": sd[fall], "monthly SD, rising (%)": sd[rise], "log-likelihood": res.llf,
            "months in falling (share)": float((p > 0.5).mean()),
            "expected stay in falling (months)": 1 / (1 - stay[fall]) if stay[fall] < 1 else np.inf,
            "searches failed": failed}
    return pd.Series(np.r_[np.nan, p], index=series.index), info, res, x


def frames_for(full, k, signal=None):
    """X6 part 5's windows per market; with `signal`, its gap replaced by the signal at the start month."""
    out = {}
    for g, s in full.items():
        f = signal_windows(s, k)
        if len(f) < 24:
            continue
        if signal is not None:
            f = f.assign(gap=signal[g].reindex(f["start"]).to_numpy())
        out[g] = f
    return out


def evaluate(frames, k):
    """X6 part 5's scores for one signal: error saved against the flat charge on left-out markets, and the placebo."""
    lomo = leave_one_out(frames, k)
    placebos, actual = placebo(frames, k)
    sq = lomo.assign(moving=(lomo["realised"] - lomo["moving"]) ** 2, flat=(lomo["realised"] - lomo["flat"]) ** 2)
    per = sq.groupby("market")[["moving", "flat"]].sum()
    peak = sq[sq["start"].astype(str).str[:4].isin(["2021", "2022"])]
    return lomo, {"pooled slope": actual, "placebo p": float((np.abs(placebos) >= abs(actual)).mean()),
                  "saved": 1 - sq["moving"].sum() / sq["flat"].sum(),
                  "saved_peak": 1 - peak["moving"].sum() / peak["flat"].sum() if len(peak) else np.nan,
                  "markets": f"{int((per['moving'] < per['flat']).sum())} of {len(per)}", "sse": sq["moving"].sum()}


def checks(full, fits, frames_gap, frames_mk, lomo48):
    rows = []

    def check(name, passes, got):
        rows.append({"check": name, "got": got, "passes": bool(passes)})

    rng = np.random.default_rng(SEED)
    steps = np.r_[rng.normal(1.0, 0.5, 60), rng.normal(-1.0, 0.5, 36), rng.normal(1.0, 0.5, 60)]
    toy = pd.Series(np.exp(np.r_[0.0, np.cumsum(steps / 100)]),
                    index=pd.period_range("2000-01", periods=len(steps) + 1, freq="M").astype(str))
    p, info, _, _ = falling(toy)
    inside = float(p.iloc[1:][66:96].mean())       # the falling stretch, after a few months to notice it
    outside = float(pd.concat([p.iloc[1:][6:60], p.iloc[1:][102:]]).mean())
    check("toy: a series rising 1% a month, then falling 1% a month for three years, then rising again: the falling "
          "probability averages above 0.8 inside the fall and below 0.2 outside it",
          inside > 0.8 and outside < 0.2, f"inside {inside:.2f}, outside {outside:.2f}")

    g = max(full, key=lambda m: len(full[m]))
    _, _, res, x = fits[g]
    cut = len(x) // 2
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        short = MarkovRegression(x[:cut], k_regimes=2, trend="c", switching_variance=True).filter(res.params)
    gap = float(np.abs(np.asarray(short.filtered_marginal_probabilities)
                       - np.asarray(res.filtered_marginal_probabilities)[:cut]).max())
    check(f"filtered, not smoothed: {g}'s probabilities for the first {cut} months, with its parameters, are the "
          "same when every later month is cut", gap < 1e-10, f"largest change {gap:.1e}")

    hard = min(full, key=lambda m: -float((np.diff(full[m].to_numpy(dtype=float)) == 0).mean()))
    xh = np.diff(np.log(full[hard].to_numpy(dtype=float))) * 100
    a, b = fit(xh)[0].llf, fit(xh)[0].llf
    check(f"reproducible: {hard}, the market with the most unchanged months, fitted twice gives the same likelihood",
          a == b, f"{a:.6f} and {b:.6f}")

    same = all(frames_gap[k][m]["start"].equals(frames_mk[k][m]["start"]) and
               np.array_equal(frames_gap[k][m]["move"].to_numpy(), frames_mk[k][m]["move"].to_numpy())
               for k in CONTRACTS for m in frames_gap[k])
    check("the Markov signal is scored on X6 part 5's windows exactly (same markets, start months and moves)", same,
          f"{sum(len(f) for f in frames_mk[48].values()):,} windows at 48 months")
    check("leave-one-out: every market held out once and every window predicted once (48 months)",
          lomo48["market"].nunique() == len(frames_mk[48])
          and len(lomo48) == sum(len(f) for f in frames_mk[48].values()), f"{len(lomo48):,} windows")
    missing = sum(int(f["gap"].isna().sum()) for k in CONTRACTS for f in frames_mk[k].values())
    check("every window has a Markov signal at its start month", missing == 0, f"{missing} missing")
    return pd.DataFrame(rows)


def main():
    every = {g: s for (series, g), s in load().items() if series == EUROSTAT and g in EUROPE}
    flat = {g: float((np.diff(s.to_numpy(dtype=float)) == 0).mean()) for g, s in every.items()}
    full = {g: s for g, s in every.items() if flat[g] <= MAX_FLAT}
    dropped = ", ".join(f"{g} (unchanged in {flat[g]:.0%} of months)" for g in sorted(every) if g not in full)
    fits = {g: falling(s) for g, s in full.items()}
    prob = {g: f[0] for g, f in fits.items()}
    fits_mean = {g: falling(s, switching_variance=False) for g, s in full.items()}
    prob_mean = {g: f[0] for g, f in fits_mean.items()}
    def regime_table(fitted):
        return pd.DataFrame([{"market": g, **{k: (f"{v:+.1f}" if "mean" in k or "likelihood" in k
                                                  else f"{v:.2f}" if "SD" in k
                                                  else f"{v:.0%}" if "share" in k else f"{v:.0f}" if "months" in k
                                                  else f"{v} of {len(SEEDS)}") for k, v in fitted[g][1].items()}}
                             for g in sorted(fitted)])
    regimes, regimes_mean = regime_table(fits), regime_table(fits_mean)

    frames_gap = {k: frames_for(full, k) for k in CONTRACTS}
    frames_mk = {k: frames_for(full, k, prob) for k in CONTRACTS}
    frames_mm = {k: frames_for(full, k, prob_mean) for k in CONTRACTS}
    rows, split, saved = [], [], {}
    lomo48 = None
    for k in CONTRACTS:
        lg, eg = evaluate(frames_gap[k], k)
        lm, em = evaluate(frames_mk[k], k)
        _, emm = evaluate(frames_mm[k], k)
        saved[k] = (eg["saved"], em["saved"], emm["saved"])
        if k == 48:
            lomo48 = lm
        for name, e in (("gap (X6)", eg), ("falling probability (Markov, mean and variance switch)", em),
                        ("falling probability (Markov, only the mean switches)", emm)):
            rows.append({"contract": f"{k} months", "signal": name, "pooled slope of shortfall on signal":
                         f"{e['pooled slope']:+.3f}", "placebo p, two-sided": f"{e['placebo p']:.3f}",
                         "markets where the moving charge errs less": e["markets"],
                         "error saved against the flat charge, left-out markets": f"{e['saved']:+.1%}",
                         "the same, contracts started 2021-22": "" if np.isnan(e["saved_peak"])
                         else f"{e['saved_peak']:+.1%}"})
        rows.append({"contract": f"{k} months", "signal": "Markov against gap",
                     "error saved against the flat charge, left-out markets":
                         f"Markov's squared error is {em['sse'] / eg['sse']:.2f} times the gap's (mean and variance), "
                         f"{emm['sse'] / eg['sse']:.2f} times (only the mean)"})
        for spec, frames in (("mean and variance switch", frames_mk[k]), ("only the mean switches", frames_mm[k])):
            pooled = pd.concat(frames.values())
            assumed = float(np.median(pooled["move"]))
            pooled = pooled.assign(shortfall=shortfall(pooled["move"], assumed))
            for name, part in (("falling probability above 0.5", pooled[pooled["gap"] > 0.5]),
                               ("falling probability 0.5 or below", pooled[pooled["gap"] <= 0.5])):
                split.append({"contract": f"{k} months", "model": spec, "at the start": name, "windows": len(part),
                              "expected shortfall (% of residual)": f"{100 * part['shortfall'].mean():.2f}"})
    ck = checks(full, fits, frames_gap, frames_mk, lomo48)

    table = pd.DataFrame(rows).fillna("")
    lines = [
        "# X7 part 4a: does a Markov-switching model spot a falling market better than X6's signal?",
        "",
        "Generated by `analysis/level_regimes.py`; the method is in its docstring. The comparison is X6 part 5's own "
        "test (`level_charge_report.md`, part 5): a charge `a + b × signal` fitted on all markets but one and scored "
        "on the one left out, against the flat charge from the same markets; the placebo shifts each market's signal "
        "in time 1,000 times. Only the signal differs.",
        "",
        f"Markets: X6 part 5's, less those whose index is unchanged in more than half its months, which no regime "
        f"model can fit: {dropped or 'none'}. Both signals use the same markets, so the gap's figures differ slightly "
        "from X6's published part 5.",
        "",
        "## The two signals, head to head",
        "",
        md_table(table),
        "",
        "\n".join(
            f"- **{k} months:** the gap saves {g:+.1%} of the flat charge's error on markets it never saw; the Markov "
            f"signal saves {m:+.1%} (mean and variance switch) and {mm:+.1%} (only the mean switches)."
            for k, (g, m, mm) in saved.items()),
        "",
        ("**The gap stays X6's re-mark signal.** Neither Markov variant comes close, even with parameters fitted in "
         "hindsight, which favour it." if all(g > max(m, mm) for g, m, mm in saved.values()) else
         "**A Markov variant beats the gap somewhere.** Its parameters are fitted in hindsight, so re-check it in "
         "real time before any use."),
        "",
        "## Expected shortfall by the Markov signal at the start (all markets pooled)",
        "",
        md_table(pd.DataFrame(split)),
        "",
        "## The fitted regimes, per market",
        "",
        "Each market's two regimes on monthly changes; means annualised. \"Falling\" is the lower-mean regime; in a "
        "market that rarely fell it is the slower-rising one. When the variance may switch, the regimes the data "
        "support mostly separate calm months from jumpy ones, not rising from falling: compare the two SD columns. "
        "In markets whose index often does not change (a fifth or more of months in SI, SK, CY, DK), one regime can "
        "collapse onto the unchanged months with a variance near zero, where the likelihood has no maximum; an SD "
        "near 0.00 with a very high log-likelihood marks it.",
        "",
        "**Mean and variance switch** (the main model):",
        "",
        md_table(regimes),
        "",
        "**Only the mean switches** (one variance), which forces the regimes to differ in direction. Added after the "
        "main model's regimes turned out to be about volatility; both are reported.",
        "",
        md_table(regimes_mean),
        "",
        "## Checks",
        "",
        md_table(ck),
        "",
        "## Limits",
        "",
        "- **The Markov parameters see each market's whole history.** Its probabilities are filtered, but the regimes' "
        "means, variances and persistence are fitted in hindsight, which favours it against the gap.",
        "- **The index is not seasonally adjusted,** so some monthly swings the regimes see are seasonal.",
        "- **X6 part 5's caveats apply:** few independent episodes, overlapping windows, and the 2021-22 shortage "
        "carrying much of the signal. France's index barely moves (`level_professional_report.md`).",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(table.to_string(index=False))
    print(pd.DataFrame(split).to_string(index=False))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
