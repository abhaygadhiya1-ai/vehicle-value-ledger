"""X7 part 1: can a simple model forecast the used-car price level better than "no change"?

X6 priced the level as if nobody forecasts it better than the past. Skeptic B5 says residual guides do. This script
asks the question on public data first: does any simple time-series model beat "no change" for the level 3, 12, 36
and 48 months ahead?

Data: the Eurostat HICP second-hand car index (CP07112) for the 26 markets of `level_risk.py`'s panel, each on its full
monthly history (France and Lithuania from 1996, most markets from 2014-16). The index holds a car's age constant
(HICP manual, section 12.3.6.3), so its move is the level, not depreciation.

Rolling origin, expanding window. At every month with at least four years of history, each model is fitted on that
history only and forecasts the log level at each horizon:
  no change      the level stays where it is: the benchmark
  drift          the average monthly change so far, carried forward (X6's median strike is its cousin)
  AR             an autoregression on monthly log changes, lag order 0-12 by AIC on each window among the stationary
                 fits (an explosive fit iterated 36 months ahead forecasts nonsense), iterated forward
  AR, no drift   the same without an intercept: momentum only, with no drift to estimate. Added after the simulation
                 showed that estimating the drift, not the dynamics, is what costs AR at long horizons
  damped trend   Holt's linear trend with damping on the log level (statsmodels), damping held between 0.8 and 0.98
                 as Hyndman & Athanasopoulos advise (FPP3, section 8.2)
  pooled AR      one autoregression shared by all markets, on changes less each market's own mean, lag order by AIC,
                 fitted on every market's history up to the same month
All nest no change except the damped trend, which nests it approximately.

Scores, each market weighted equally:
  RMSE ratio      root mean squared error of the log level against no change's, on the same windows; below 1 beats it
  downside ratio  X6's expected shortfall per euro of residual when the residual assumes the forecast, against no
                  change's. A forecast biased low wins here and loses on RMSE, so read it with the bias.
  tests           the loss differential as one series by origin month, each market weighted by one over its number of
                  windows so the series' mean is exactly the ratios' market-weighted gap, then Diebold-Mariano with a
                  Newey-West variance over h-1 lags and the Harvey-Leybourne-Newbold correction (two-sided), and
                  Clark-West, which allows for the nesting (one-sided). DM asks whether the model as estimated forecasts
                  better, the pricing question, and decides the verdicts. Clark-West asks whether the extra parameters
                  are non-zero in the population, which they can be even when estimating them costs more than it gains.
Overlapping windows share months, and markets share shocks. The independent windows at a horizon are about the origin
months divided by the horizon, and fewer still after the correlation between markets.

Checks: no change scores exactly 1 against itself; forecasts up to a cut-off month do not change when every later
value is replaced by noise (no look-ahead); on long simulated histories AR recovers a planted AR(1) skill close to the
oracle's, and on our own lengths it finds none in a random walk. The same worlds at our own lengths show what this
panel can detect.

Usage: .venv/bin/python analysis/level_forecast.py   (writes analysis/level_forecast_report.md, ~5 minutes)
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.stats import t as student_t
import statsmodels.api as sm
from statsmodels.tsa.holtwinters import ExponentialSmoothing

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
from level_charge import common_panel, shortfall  # noqa: E402
from level_risk import EUROSTAT, load  # noqa: E402

OUT = HERE / "level_forecast_report.md"
HORIZONS = (3, 12, 36, 48)
MIN_TRAIN = 48          # months of history before a market's first forecast
MAX_LAG = 12
DAMPING = (0.8, 0.98)   # FPP3 section 8.2
MODELS = ("no change", "drift", "AR", "AR, no drift", "damped trend", "pooled AR")
CUT = "2019-12"         # the no-look-ahead check garbles every month after this one
SIM_PHI = 0.5           # the skill the simulation plants: AR(1) in monthly log changes
SIM_LONG = 600          # months per simulated market in the machinery check
SEED = 7


def histories():
    """The markets of level_risk.py's common panel, each on its full contiguous history, as log levels."""
    common, core, _ = common_panel()
    full = {g: s for (series, g), s in load().items() if series == EUROSTAT and g in common}
    return {g: np.log(full[g]) for g in sorted(full)}, core


def lagmat(z, p, start):
    """Rows t = start .. n-1; columns z[t-1] .. z[t-p]."""
    n = len(z)
    return np.column_stack([z[start - j: n - j] for j in range(1, p + 1)]) if p else np.empty((n - start, 0))


def stationary(coefs):
    """True when an autoregression's roots lie inside the unit circle, so the changes it forecasts do not explode."""
    p = len(coefs)
    if not p:
        return True
    companion = np.zeros((p, p))
    companion[0] = coefs
    companion[1:, :-1] = np.eye(p - 1)
    return bool(np.abs(np.linalg.eigvals(companion)).max() < 1)


def by_aic(X_of_p, y, const):
    """OLS for each lag order on one common sample; keep the stationary order with the lowest AIC.

    An autoregression on changes assumes the changes are stable. An explosive fit (some windows around 2022) iterated
    36 months ahead forecasts nonsense, so it is skipped; order 0 always qualifies. Also returns whether the lowest-AIC
    order of all was skipped."""
    fits = []
    for p in range(MAX_LAG + 1):
        X = X_of_p(p)
        if const:
            X = np.column_stack([np.ones(len(y)), X])
        beta = np.linalg.lstsq(X, y, rcond=None)[0] if X.shape[1] else np.empty(0)
        rss = float(((y - X @ beta) ** 2).sum())
        c, coefs = (beta[0], beta[1:]) if const else (0.0, beta)
        fits.append((len(y) * np.log(rss / len(y)) + 2 * X.shape[1], p, c, coefs))
    best = min((f for f in fits if stationary(f[3])), key=lambda f: f[0])
    return best[1], best[2], best[3], best[0] > min(f[0] for f in fits)


def ar_fit(x, const=True):
    """An autoregression on one market's monthly log changes; without an intercept it forecasts no drift."""
    return by_aic(lambda p: lagmat(x, p, MAX_LAG), x[MAX_LAG:], const)


def pooled_fit(xs):
    """One autoregression shared by all markets, on each market's changes less its own mean."""
    zs = [x - x.mean() for x in xs]
    y = np.concatenate([z[MAX_LAG:] for z in zs])
    return by_aic(lambda p: np.vstack([lagmat(z, p, MAX_LAG) for z in zs]), y, const=False)


def iterate(x, const, coefs, h):
    """Cumulative forecast change 1..h months ahead from an autoregression on x."""
    hist = list(x[-len(coefs):]) if len(coefs) else []
    steps = []
    for _ in range(h):
        nxt = const + sum(c * hist[-j] for j, c in enumerate(coefs, 1))
        hist.append(nxt)
        steps.append(nxt)
    return np.cumsum(steps)


def damped(y, h):
    """Holt's damped trend on the log level: cumulative forecast change 1..h months ahead."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(y, trend="add", damped_trend=True,
                                   bounds={"damping_trend": DAMPING}).fit()
    return np.asarray(fit.forecast(h)) - y[-1]


def backtest(panel, extra=None, until=None, with_damped=True):
    """Every market and every origin with MIN_TRAIN months of history: forecasts from that history only.

    panel: {market: Series of log levels by month}. extra: {name: f(history) -> path}, for the checks.
    One row per market, origin, horizon and model: the forecast and the realised log change."""
    hmax = max(HORIZONS)
    steps = np.arange(1, hmax + 1)
    values = {g: s.to_numpy(dtype=float) for g, s in panel.items()}
    position = {g: {m: i for i, m in enumerate(s.index)} for g, s in panel.items()}
    rows = []
    for origin in sorted(set().union(*(s.index for s in panel.values()))):
        if until is not None and origin > until:
            break
        live = {g: values[g][: position[g][origin] + 1] for g in panel
                if origin in position[g] and position[g][origin] + 1 >= MIN_TRAIN}
        if not live:
            continue
        p_pool, _, c_pool, skip_pool = pooled_fit([np.diff(y) for y in live.values()])
        for g, y in live.items():
            i = len(y) - 1
            if i + HORIZONS[0] >= len(values[g]):
                continue
            x = np.diff(y)
            p, const, coefs, skip = ar_fit(x)
            p0, _, coefs0, skip0 = ar_fit(x, const=False)
            path = {"no change": np.zeros(hmax), "drift": x.mean() * steps, "AR": iterate(x, const, coefs, hmax),
                    "AR, no drift": iterate(x, 0.0, coefs0, hmax),
                    "pooled AR": iterate(x - x.mean(), 0.0, c_pool, hmax) + x.mean() * steps}
            fitted = {"AR": (p, skip), "AR, no drift": (p0, skip0)}
            if with_damped:
                path["damped trend"] = damped(y, hmax)
            for name, f in (extra or {}).items():
                path[name] = f(y)
            for h in HORIZONS:
                if i + h < len(values[g]):
                    actual = values[g][i + h] - y[-1]
                    for m, f in path.items():
                        rows.append((g, origin, h, m, f[h - 1], actual, *fitted.get(m, (p_pool, skip_pool))))
    return pd.DataFrame(rows, columns=["market", "origin", "h", "model", "pred", "actual", "lags", "skipped"])


def hac_var(u, h):
    """Newey-West long-run variance of a mean-zero series: Bartlett weights over h-1 lags."""
    n = len(u)
    v = u @ u / n
    for k in range(1, h):
        v += 2 * (1 - k / h) * (u[k:] @ u[:-k]) / n
    return v


def dm_test(d, h):
    """Diebold-Mariano on a loss differential (positive: the model beats no change), with the Harvey-Leybourne-Newbold
    correction; two-sided p from Student's t with n-1 degrees of freedom."""
    n, dbar = len(d), d.mean()
    v = hac_var(d - dbar, h)
    if v <= 0:
        return np.nan, np.nan
    stat = dbar / np.sqrt(v / n) * np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    return stat, 2 * student_t.sf(abs(stat), n - 1)


def cw_test(f, h):
    """Clark-West on the adjusted differential for nested models; one-sided normal p (the model is better)."""
    n, fbar = len(f), f.mean()
    v = hac_var(f - fbar, h)
    if v <= 0:
        return np.nan, np.nan
    stat = fbar / np.sqrt(v / n)
    return stat, norm.sf(stat)


def panel_series(values, index):
    """A loss series by origin month whose mean is the average over markets of each market's own mean.

    Averaging markets within each month instead would let France and Lithuania, alone before 2009, carry a decade
    of origins; this weighting makes every market count the same in the tests as in the ratios."""
    s = pd.Series(np.asarray(values, dtype=float), index=index)
    by_origin = (s / s.groupby(level="market").transform("size")).groupby(level="origin").sum()
    return by_origin * len(by_origin) / index.get_level_values("market").nunique()


def score(bt, geos):
    """Per horizon and model, against no change on the same windows, each market weighted equally."""
    bt = bt[bt["market"].isin(geos)].copy()
    bt["err"] = bt["actual"] - bt["pred"]
    bt["short"] = shortfall(np.expm1(bt["actual"]), np.expm1(bt["pred"]))
    key = ["market", "origin", "h"]
    base = bt[bt["model"] == "no change"].set_index(key)
    rows, per_market = [], {}
    for h in HORIZONS:
        for m in [m for m in bt["model"].unique()]:
            cur = bt[(bt["model"] == m) & (bt["h"] == h)].set_index(key)
            b = base.loc[cur.index]
            per = pd.DataFrame({"se": cur["err"] ** 2, "se0": b["err"] ** 2, "sh": cur["short"], "sh0": b["short"],
                                "err": cur["err"]}).groupby(level="market").mean()
            d = panel_series(b["err"].to_numpy() ** 2 - cur["err"].to_numpy() ** 2, cur.index).to_numpy()
            f = panel_series(b["err"].to_numpy() ** 2 - cur["err"].to_numpy() ** 2
                             + (cur["pred"].to_numpy() - b["pred"].to_numpy()) ** 2, cur.index)
            dm = dm_test(d, h)
            cw = cw_test(f.to_numpy(), h)
            origins = cur.index.get_level_values("origin")
            rows.append({"h": h, "model": m, "ratio": float(np.sqrt(per["se"].mean() / per["se0"].mean())),
                         "gap": float(per["se0"].mean() - per["se"].mean()), "d_mean": float(d.mean()),
                         "beaten": int((per["se"] < per["se0"]).sum()), "markets": len(per),
                         "bias": float(per["err"].mean()), "down": float(per["sh"].mean() / per["sh0"].mean()),
                         "dm_p": dm[1], "dm_stat": dm[0], "cw_p": cw[1], "origins": len(f),
                         "from": origins.min(), "to": origins.max()})
            per_market[(h, m)] = np.sqrt(per["se"] / per["se0"])
    return pd.DataFrame(rows), per_market


def simulate(template, phi, sigma, seed):
    """Markets with the real ones' months; monthly log changes follow AR(1) with coefficient phi and the given SD."""
    rng = np.random.default_rng(seed)
    out = {}
    for g, s in template.items():
        burn = 200
        e = rng.normal(0.0, sigma * np.sqrt(1 - phi ** 2), len(s) + burn)
        x = np.zeros(len(s) + burn)
        for t in range(1, len(x)):
            x[t] = phi * x[t - 1] + e[t]
        out[g] = pd.Series(np.concatenate([[0.0], np.cumsum(x[burn + 1:])]), index=s.index)
    return out


def oracle(phi):
    """The true AR(1) forecast, zero mean: the last change decays by phi each month."""
    k = np.arange(1, max(HORIZONS) + 1)
    return lambda y: (y[-1] - y[-2]) * phi * (1 - phi ** k) / (1 - phi)


def checks(panel, bt, scores):
    rows = []

    def check(name, passes, got):
        rows.append({"check": name, "got": got, "passes": bool(passes)})

    s = scores.set_index(["h", "model"])
    nc = s.xs("no change", level="model")
    check("no change against itself: RMSE ratio exactly 1 at every horizon", (nc["ratio"] == 1.0).all(),
          ", ".join(f"{v:.6f}" for v in nc["ratio"]))
    check("no change against itself: downside ratio exactly 1 at every horizon", (nc["down"] == 1.0).all(),
          ", ".join(f"{v:.6f}" for v in nc["down"]))

    others = scores[scores["model"] != "no change"]
    check("the tests' loss series has the same mean as the ratios' market-weighted gap, every horizon and model",
          np.allclose(others["d_mean"], others["gap"], rtol=0, atol=1e-12),
          f"largest difference {(others['d_mean'] - others['gap']).abs().max():.1e}")
    check("every DM statistic's sign agrees with its RMSE ratio (positive when below 1)",
          ((others["dm_stat"] > 0) == (others["ratio"] < 1)).all(),
          f"{int(((others['dm_stat'] > 0) == (others['ratio'] < 1)).sum())} of {len(others)}")

    key = ["market", "origin", "h"]
    e = bt.assign(err=bt["actual"] - bt["pred"])
    base = e[e["model"] == "no change"].set_index(key)
    for m, h in (("damped trend", 48), ("AR", 3)):
        cur = e[(e["model"] == m) & (e["h"] == h)].set_index(key)
        d = panel_series(base.loc[cur.index, "err"].to_numpy() ** 2 - cur["err"].to_numpy() ** 2,
                         cur.index).to_numpy()
        n = len(d)
        ols = sm.OLS(d, np.ones(n)).fit(cov_type="HAC", cov_kwds={"maxlags": h - 1, "use_correction": False})
        independent = float(ols.tvalues[0]) * np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
        mine = dm_test(d, h)[0]
        check(f"DM statistic, {m} at {h} months, equals statsmodels' HAC t-statistic times the HLN factor "
              f"({independent:.6f})", abs(mine - independent) < 1e-9, f"{mine:.6f}")

    rng = np.random.default_rng(SEED)
    garbled ={g: pd.Series(np.where(s.index > CUT, rng.normal(0, 5, len(s)), s.to_numpy()), index=s.index)
               for g, s in panel.items()}
    early = backtest(garbled, until=CUT).set_index(["market", "origin", "h", "model"])["pred"]
    same = bt.set_index(["market", "origin", "h", "model"])["pred"].loc[early.index]
    gap = float((early - same).abs().max())
    check(f"no look-ahead: every month after {CUT} replaced by noise; forecasts made up to {CUT} unchanged "
          f"({len(early):,} forecasts)", gap == 0.0 and len(early) > 0, f"largest change {gap:.1e}")

    # Simulated markets, the changes' spread matched to the real ones. The machinery check uses long histories, where
    # estimation error is small; the same worlds at our own lengths show what this panel can detect.
    sigma = float(np.concatenate([np.diff(s.to_numpy()) for s in panel.values()]).std())
    long_months = pd.period_range("1900-01", periods=SIM_LONG, freq="M").astype(str)
    long_panel = {g: pd.Series(np.zeros(SIM_LONG), index=long_months) for g in panel}
    sims = []
    for world, template, phi in ((f"AR(1), phi {SIM_PHI}, {SIM_LONG}-month histories", long_panel, SIM_PHI),
                                 (f"AR(1), phi {SIM_PHI}, our histories", panel, SIM_PHI),
                                 ("random walk, our histories", panel, 0.0)):
        markets = simulate(template, phi, sigma, SEED)
        sim = backtest(markets, extra={"oracle": oracle(phi)} if phi else None, with_damped=False)
        sc = score(sim, list(markets))[0].set_index(["h", "model"])
        for h in HORIZONS:
            sims.append({"world": world, "months ahead": h, "AR": f"{sc.loc[(h, 'AR'), 'ratio']:.3f}",
                         "AR, no drift": f"{sc.loc[(h, 'AR, no drift'), 'ratio']:.3f}",
                         "pooled AR": f"{sc.loc[(h, 'pooled AR'), 'ratio']:.3f}",
                         "drift": f"{sc.loc[(h, 'drift'), 'ratio']:.3f}",
                         "oracle": f"{sc.loc[(h, 'oracle'), 'ratio']:.3f}" if phi else "1 (no change)",
                         "AR's DM-HLN p": f"{sc.loc[(h, 'AR'), 'dm_p']:.3f}"})
        ar, h = sc.loc[(3, "AR")], 3
        if template is long_panel:
            orc = sc.loc[(h, "oracle"), "ratio"]
            check(f"{world}, {h} months: AR recovers the planted skill, RMSE ratio within 0.02 of the oracle's "
                  f"({orc:.3f})", abs(ar["ratio"] - orc) <= 0.02, f"{ar['ratio']:.3f}")
            check(f"{world}, {h} months: the panel test detects it (DM-HLN p < 0.05)",
                  ar["dm_p"] < 0.05 and ar["dm_stat"] > 0, f"p {ar['dm_p']:.4f}")
        elif not phi:
            for h in (3, 12):
                ar = sc.loc[(h, "AR")]
                check(f"{world}, {h} months: AR finds no skill (RMSE ratio at least 0.98, DM-HLN not significant in "
                      "its favour)", ar["ratio"] >= 0.98 and not (ar["dm_p"] < 0.05 and ar["dm_stat"] > 0),
                      f"{ar['ratio']:.3f}, p {ar['dm_p']:.3f}")
    return pd.DataFrame(rows), pd.DataFrame(sims)


def fmt(scores):
    out = scores.copy()
    out["windows"] = (out["origins"] / out["h"]).map(lambda v: f"{v:.1f}")
    out["markets beaten"] = out["beaten"].astype(str) + " of " + out["markets"].astype(str)
    out["RMSE ratio"] = out["ratio"].map(lambda v: f"{v:.3f}")
    out["bias (pp)"] = (out["bias"] * 100).map(lambda v: f"{v:+.1f}")
    out["downside ratio"] = out["down"].map(lambda v: f"{v:.3f}")
    out["DM-HLN p"] = out["dm_p"].map(lambda v: "" if pd.isna(v) else f"{v:.3f}")
    out["Clark-West p"] = out["cw_p"].map(lambda v: "" if pd.isna(v) else f"{v:.3f}")
    out["origins"] = out["origins"].astype(str) + " (" + out["from"] + " to " + out["to"] + ")"
    out = out.rename(columns={"h": "months ahead"})
    return out[["months ahead", "model", "RMSE ratio", "markets beaten", "bias (pp)", "downside ratio", "DM-HLN p",
                "Clark-West p", "origins", "windows"]]


def verdict(scores):
    """One line per horizon: the best model by RMSE, and which models the DM-HLN test says beat no change."""
    lines = []
    for h in HORIZONS:
        sub = scores[(scores["h"] == h) & (scores["model"] != "no change")].sort_values("ratio")
        best = sub.iloc[0]
        wins = sub[(sub["ratio"] < 1) & (sub["dm_p"] < 0.05) & (sub["dm_stat"] > 0)]
        said = ", ".join(f"{r.model} (RMSE ratio {r.ratio:.3f}, p {r.dm_p:.3f})" for r in wins.itertuples()) or "none"
        lines.append(f"- **{h} months:** the lowest error is {best['model']}'s, RMSE ratio {best['ratio']:.3f} "
                     f"({best['beaten']} of {best['markets']} markets beaten). Beats no change at 5% (DM-HLN): "
                     f"{said}.")
    return "\n".join(lines)


def main():
    panel, core = histories()
    bt = backtest(panel)
    all_scores, per_market = score(bt, list(panel))
    core_scores, _ = score(bt, core)
    ck, sims = checks(panel, bt, all_scores)

    ar_fits = bt[(bt["model"] == "AR") & (bt["h"] == HORIZONS[0])]
    ar_lags = ar_fits["lags"]
    pool_fits = bt[(bt["model"] == "pooled AR") & (bt["h"] == HORIZONS[0])].groupby("origin")[["lags", "skipped"]]
    pool_lags = pool_fits.first()["lags"]
    lag1 = [pd.Series(np.diff(s.to_numpy())).autocorr(1) for s in panel.values()]
    lv = pd.read_csv(HERE / "latvia_monthly.csv").dropna(subset=["our_index", "eurostat_index"])  # latvia_time.py
    lv_move = {c: lv[c].iloc[-1] / lv[c].iloc[0] - 1 for c in ("our_index", "eurostat_index")}
    starts = pd.DataFrame({"market": list(panel), "from": [s.index[0] for s in panel.values()],
                           "months": [len(s) for s in panel.values()]})
    wide = pd.DataFrame({f"{m} {h}m": per_market[(h, m)] for h in (12, 36) for m in MODELS if m != "no change"})
    cols = list(wide.columns)
    wide = wide.map(lambda v: f"{v:.2f}").reset_index().merge(starts, on="market")[["market", "from", "months"] + cols]

    lines = [
        "# X7 part 1: can a simple model forecast the used-car price level?",
        "",
        "Generated by `analysis/level_forecast.py`; the method is in its docstring. Eurostat HICP second-hand car "
        f"index (CP07112) for the {len(panel)} markets of `level_risk.py`'s panel, each on its full monthly history. "
        f"Rolling origin with an expanding window: every month with at least {MIN_TRAIN} months of history, each model "
        "is fitted on that history only.",
        "",
        "How to read the tables:",
        "- **RMSE ratio:** the model's root mean squared error of the log level against no change's, on the same "
        "windows, each market weighted equally. Below 1 beats no change.",
        "- **Bias:** realised minus forecast, in percentage points of the level. Positive means the level ended above "
        "the forecast.",
        "- **Downside ratio:** X6's expected shortfall per euro of residual when the residual assumes the forecast, "
        "against no change's. A forecast biased low wins here, so read it with the bias and the RMSE.",
        "- **DM-HLN p:** Diebold-Mariano, two-sided, on the loss differential as one series by origin month, each "
        "market weighted by one over its number of windows, so the series' mean is the ratio's market-weighted gap "
        "and every market counts the same in the test as in the ratio; Newey-West variance over h-1 lags and the "
        "Harvey-Leybourne-Newbold correction. This asks the pricing "
        "question: does the model, as estimated from the data a lessor had, forecast better than no change?",
        "- **Clark-West p:** one-sided, allowing for the models nesting no change. It asks a different question: are "
        "the model's extra parameters (a drift, a lag) non-zero in the population? They can be even when estimating "
        "them costs more than they gain, so a small p here beside an RMSE ratio above 1 means *there is a signal, but "
        "not enough data to forecast with it*. The verdicts below use DM-HLN.",
        "- **Windows:** origin months divided by the horizon, roughly the independent windows before the correlation "
        "between markets shrinks them further.",
        "",
        f"## All {len(panel)} markets",
        "",
        md_table(fmt(all_scores)),
        "",
        verdict(all_scores),
        "",
        f"## The group's largest markets ({', '.join(core)})",
        "",
        md_table(fmt(core_scores)),
        "",
        verdict(core_scores),
        "",
        "## Each market: RMSE ratio against no change at 12 and 36 months",
        "",
        md_table(wide),
        "",
        "## What the models chose",
        "",
        f"- AR's lag order across all market-origin fits: median {ar_lags.median():.0f}, none (drift only) in "
        f"{(ar_lags == 0).mean():.0%} of fits, the maximum of {MAX_LAG} in {(ar_lags == MAX_LAG).mean():.0%}. The "
        f"lowest-AIC order was explosive and skipped in {ar_fits['skipped'].mean():.1%} of fits "
        f"({int(ar_fits['skipped'].sum())} of {len(ar_fits):,}).",
        f"- The pooled AR's lag order across origin months: median {pool_lags.median():.0f}, range "
        f"{pool_lags.min():.0f} to {pool_lags.max():.0f}; its lowest-AIC order was skipped in "
        f"{int(pool_fits.first()['skipped'].sum())} of {len(pool_lags)} months.",
        f"- The data's own persistence: the lag-1 autocorrelation of monthly log changes has a median of "
        f"{np.median(lag1):.2f} across markets (range {min(lag1):.2f} to {max(lag1):.2f}).",
        "",
        "## Checks",
        "",
        md_table(ck),
        "",
        "The first design of the planted-skill check ran on our own history lengths and failed at 12 months: the "
        "oracle knows the mean change is zero, while AR must estimate a drift from as little as four years of data, "
        "and that error outweighed the planted skill. The check of the machinery therefore runs on long histories, and "
        "our own lengths are shown below as what this panel can detect.",
        "",
        "## Simulation: what this panel can detect",
        "",
        f"Simulated markets with the real changes' spread. In the AR(1) worlds, monthly changes follow an AR(1) with "
        f"coefficient {SIM_PHI}, {'stronger' if SIM_PHI > np.median(lag1) else 'weaker'} than the data's median "
        "above; the oracle forecasts with the true "
        "coefficient and a zero mean. RMSE ratios against no change.",
        "",
        md_table(sims),
        "",
        "## Limits",
        "",
        "- **Few independent windows at the long horizons.** Overlapping windows share months, and markets share "
        "shocks. At 36 and 48 months the tests rest on a handful of independent windows, so a failure to beat no "
        "change there means *not detectably better*, not *impossible*. The simulated AR(1) world shows what the same "
        "panel can detect at the short horizons.",
        "- **The long-horizon windows span one regime.** Most markets' histories start in 2014-16, so their 36- and "
        "48-month windows run into the 2021-23 supply shock, which the ECB traces to supply chains and energy for new "
        "cars (Economic Bulletin 7/2022). The early windows come from France and Lithuania alone.",
        "- **The index is not seasonally adjusted.** At 3 months an autoregression with 12 lags can profit from "
        "seasonality, which is real skill but not pricing skill; 12, 36 and 48 months are whole years.",
        "- **Expanding windows,** so Giacomini-White's rolling-window result does not apply; Clark-West covers the "
        "nesting. Four models, four horizons and two sets of markets make many tests; read a lone p near 0.05 as "
        "noise.",
        "- **Retail, constant-age prices.** The index tracks dealer retail and advertised prices, not the auction "
        "prices a lessor gets (basis risk, X6 part 1).",
        f"- **Adverts can move more than the official index.** Latvia is the one market with our own constant-quality "
        f"advert index (`latvia_time.py`). From {lv['month'].iloc[0]} to {lv['month'].iloc[-1]} it moved "
        f"{lv_move['our_index']:+.0%}, against {lv_move['eurostat_index']:+.0%} for Eurostat's Latvian index. Latvia's "
        "neighbours' official indices rose nearly as much as our advert index (`latvia_time_report.md`), so the gap "
        "may be Latvia's own. Still, this forecasts the official index, and the prices a lessor meets can move more.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(all_scores[["h", "model", "ratio", "beaten", "down", "dm_p", "cw_p", "origins"]].round(3).to_string(index=False))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
