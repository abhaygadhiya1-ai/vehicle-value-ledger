"""X7 part 5: does part 1's null survive without France, and on the two long histories we hold?

Part 1 (`level_forecast.py`) found that from 12 months on no simple model beats "no change" for the used-car level
detectably, on 26 markets' Eurostat indices. Part 3 raised two doubts about that result:
  - France's index barely moves, and it is part 1's longest history (with Lithuania, the only one before 2009). A flat
    index flatters no change. INSEE prices used cars from Argus guide values (cars aged 1, 3 and 5 years, 123 models)
    and, since January 2018, moves each car's index each month by the twelfth root of its year-on-year change, which
    INSEE says "induit un retard" (method note "Indice des prix a la consommation : les changements de l'annee 2018",
    12 February 2018).
  - the long horizons rest on few independent windows, so "not detectably better" is partly a limit of the data.
This script re-runs part 1's back-test unchanged, plus part 2a's real terms (the level grows 2% a year), on:
  26 markets              part 1's panel, reproduced exactly
  25 markets, no France   the same panel without France (the pooled AR is refitted without it)
  core without France     the group's largest markets less France, from the same run
  UK, ONS                 ONS CPI second-hand cars (D7E9), 1988 on. To January 2024: retail prices from a trade guide
                          for 35 models aged 1-3 (ONS, 28 June 2022); from February 2024: Auto Trader listings. The
                          published series is not revised, so the switch is a link, not a jump.
  US, from 1953 (US)      US CPI used cars and trucks, seasonally adjusted: J.D. Power valuation prices for cars aged
                          2-7 (BLS factsheet). Published since December 1952, and not adjusted for quality from 1952 to
                          1987 (Pashigian, BLS working paper 338, 2001).
  US, from 1987 (US)      the same series restarted in January 1987, when quality adjustment began. This split was fixed
                          from the method history before any result was seen.
With one market the pooled AR is not pooled, so single-series results leave it out.

Power: how often would the DM-HLN test detect a forecaster that truly beats no change at 36 and 48 months, at each
history length? The simulated log level is a random walk plus a mean-reverting part (half-life 24 months), sized so that
the oracle, which knows the mean-reverting part, has an RMSE ratio of 0.90 (or 0.95) against no change at 48 months.
The oracle has no estimation error, so this is an upper bound on what any real forecaster could show.

France: the lag-1 autocorrelation of France's monthly changes before and from January 2018, which the twelfth-root
rule should raise (a twelfth of a year-on-year change each month makes consecutive changes share eleven months), and
whether the Eurostat series and INSEE's own CPI series move together.

Checks: the 26-market and core tables equal part 1's report, cell for cell; in every set no change scores exactly 1
against itself, the tests' loss series has the ratios' mean, and every DM sign agrees with its ratio; real terms'
12-month forecast is exactly log(1.02); the power simulation's oracle ratio matches its analytic value on a long run.
The no-look-ahead check is part 1's, on the same `backtest` function, which this script does not change.

Usage: .venv/bin/python analysis/level_long.py   (writes analysis/level_long_report.md, ~1 minute)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
from level_forecast import (HORIZONS, MIN_TRAIN, MODELS, backtest, dm_test, fmt, histories,  # noqa: E402
                            score, verdict)
from level_indicators import TARGET, real_terms  # noqa: E402
from level_risk import EUROSTAT, load  # noqa: E402

OUT = HERE / "level_long_report.md"
PART1 = HERE / "level_forecast_report.md"
ONS = "ONS CPI 07.1.1B, second-hand cars (D7E9)"
US = "US CPI, used cars and trucks, seasonally adjusted (CUSR0000SETA02)"
INSEE = "INSEE CPI 07.1.1.2, used cars (idbank 001763645, discontinued series)"
US_QUALITY_FROM = "1987-01"     # BLS began adjusting used-car prices for quality (Pashigian 2001)
FR_METHOD_FROM = "2018-01"      # INSEE's twelfth-root rule (method note, 12 February 2018)
HALF_LIFE = 24                  # months, the power simulation's mean-reverting part
POWER_RATIOS = (0.90, 0.95)     # the oracle's RMSE ratio at 48 months
POWER_SEEDS = 200
SEED = 7


def with_real_terms(bt, panel):
    """Part 1's back-test rows plus part 2a's real terms on the same windows."""
    rt = real_terms(panel).assign(model="real terms", lags=np.nan, skipped=False)
    return pd.concat([bt, rt[bt.columns]], ignore_index=True)


def run(panel):
    return with_real_terms(backtest(panel), panel)


def part1_tables():
    """The two score tables of part 1's report, as lists of markdown lines."""
    sections = PART1.read_text().split("\n## ")
    grab = {"all": "All ", "core": "The group's largest markets"}
    return {k: [ln for ln in next(s for s in sections if s.startswith(head)).splitlines() if ln.startswith("|")]
            for k, head in grab.items()}


def series_stats(name, s):
    x = np.diff(np.log(s.to_numpy(dtype=float)))
    return {"series": name, "from": s.index[0], "to": s.index[-1], "months": len(s),
            "total move": f"{s.iloc[-1] / s.iloc[0] - 1:+.0%}",
            "SD of monthly change (pp)": f"{x.std() * 100:.2f}",
            "lag-1 autocorrelation of monthly change": f"{pd.Series(x).autocorr(1):.2f}"}


def france(eurostat_fr, insee_fr):
    """Before and from INSEE's twelfth-root rule; and whether the two French series move together."""
    rows = []
    for name, s in (("Eurostat HICP (CP07112)", eurostat_fr), ("INSEE CPI (07.1.1.2)", insee_fr)):
        x = np.log(s).diff().dropna()
        for label, part in (("before", x[x.index < FR_METHOD_FROM]), ("from", x[x.index >= FR_METHOD_FROM])):
            rows.append({"series": name, "months": f"{label} {FR_METHOD_FROM}",
                         "changes": len(part), "SD of monthly change (pp)": f"{part.std() * 100:.2f}",
                         "lag-1 autocorrelation": f"{part.autocorr(1):.2f}",
                         "move": f"{np.expm1(part.sum()):+.1%}"})
    both = pd.concat({"e": np.log(eurostat_fr).diff(), "i": np.log(insee_fr).diff()}, axis=1).dropna()
    return pd.DataFrame(rows), float(both["e"].corr(both["i"])), len(both)


def summary(sets):
    """Per set and horizon: the lowest error, what beats no change at 5%, and real terms."""
    rows = []
    for label, sc in sets.items():
        for h in HORIZONS:
            sub = sc[(sc["h"] == h) & (sc["model"] != "no change")].sort_values("ratio")
            best = sub.iloc[0]
            wins = sub[(sub["ratio"] < 1) & (sub["dm_p"] < 0.05) & (sub["dm_stat"] > 0)]
            rt = sc[(sc["h"] == h) & (sc["model"] == "real terms")].iloc[0]
            rows.append({"set and horizon": f"{label}, {h} months", "lowest error": best["model"],
                         "its RMSE ratio": f"{best['ratio']:.3f}", "its DM-HLN p": f"{best['dm_p']:.3f}",
                         "beats no change at 5% (DM-HLN)": ", ".join(wins["model"]) or "none",
                         "real terms RMSE ratio": f"{rt['ratio']:.3f}", "real terms DM-HLN p": f"{rt['dm_p']:.3f}",
                         "real terms downside ratio": f"{rt['down']:.3f}", "windows": f"{rt['origins'] / h:.1f}"})
    return pd.DataFrame(rows)


def reverting_variance(ratio, h, phi):
    """The mean-reverting part's variance (random-walk steps of variance 1) giving the oracle `ratio` at h months.

    No change's MSE is h + 2V(1 - phi^h); the oracle's is h + V(1 - phi^2h)."""
    a, b = 1 - phi ** (2 * h), 2 * (1 - phi ** h)
    return h * (1 - ratio ** 2) / (ratio ** 2 * b - a)


def simulate_level(n, v, phi, rng):
    """A random walk plus a stationary AR(1) level of variance v; returns the log level and the AR(1) part."""
    w = np.cumsum(rng.normal(0.0, 1.0, n))
    u = np.empty(n)
    u[0] = rng.normal(0.0, np.sqrt(v))
    e = rng.normal(0.0, np.sqrt(v * (1 - phi ** 2)), n)
    for t in range(1, n):
        u[t] = phi * u[t - 1] + e[t]
    return w + u, u


def oracle_losses(y, u, phi, h):
    """Squared errors of no change and of the oracle, every origin with MIN_TRAIN months of history, as in part 1."""
    i = np.arange(MIN_TRAIN - 1, len(y) - h)
    e0 = y[i + h] - y[i]
    return e0 ** 2, (e0 - (phi ** h - 1) * u[i]) ** 2


def power(lengths):
    phi = 0.5 ** (1 / HALF_LIFE)
    rng = np.random.default_rng(SEED)
    rows = []
    for target in POWER_RATIOS:
        v = reverting_variance(target, max(HORIZONS), phi)
        for label, n in lengths.items():
            hits = {h: 0 for h in (36, 48)}
            for _ in range(POWER_SEEDS):
                y, u = simulate_level(n, v, phi, rng)
                for h in hits:
                    l0, l1 = oracle_losses(y, u, phi, h)
                    stat, p = dm_test(l0 - l1, h)
                    hits[h] += bool(p < 0.05 and stat > 0)
            rows.append({"history, oracle's true RMSE ratio at 48 months": f"{label}, {target:.2f}", "months": n, **{f"detected at {h} months": f"{k / POWER_SEEDS:.0%}" for h, k in hits.items()}})
    return pd.DataFrame(rows), phi


def main():
    panel, core = histories()
    raw = load()
    ons = raw[(ONS, "UK")]
    us = raw[(US, "US")]
    singles = {"UK, ONS, 1988 on": np.log(ons), "US, 1953 on (US data)": np.log(us),
               "US, 1987 on (US data)": np.log(us[us.index >= US_QUALITY_FROM])}

    bt_all = run(panel)
    no_fr = {g: s for g, s in panel.items() if g != "FR"}
    bt_nofr = run(no_fr)
    core_nofr = [g for g in core if g != "FR"]
    sets = {f"{len(panel)} markets": score(bt_all, list(panel))[0],
            f"core ({', '.join(core)})": score(bt_all, core)[0],
            f"{len(no_fr)} markets, no France": score(bt_nofr, list(no_fr))[0],
            f"core without France ({', '.join(core_nofr)})": score(bt_nofr, core_nofr)[0]}
    single_bt = {}
    for label, s in singles.items():
        single_bt[label] = run({label: s})
        sets[label] = score(single_bt[label][single_bt[label]["model"] != "pooled AR"], [label])[0]
        print(f"done {label}")

    # checks
    rows = []

    def check(name, passes, got):
        rows.append({"check": name, "got": got, "passes": bool(passes)})

    p1 = part1_tables()
    for key, sc in (("all", sets[f"{len(panel)} markets"]), ("core", sets[f"core ({', '.join(core)})"])):
        mine = md_table(fmt(sc[sc["model"].isin(MODELS)])).splitlines()
        same = sum(a == b for a, b in zip(mine, p1[key]))
        check(f"part 1 reproduced: the {key} table equals `level_forecast_report.md` cell for cell",
              mine == p1[key], f"{same} of {len(p1[key])} lines equal")
    for label, sc in sets.items():
        nc = sc[sc["model"] == "no change"]
        others = sc[sc["model"] != "no change"]
        ok = ((nc["ratio"] == 1.0).all() and (nc["down"] == 1.0).all()
              and np.allclose(others["d_mean"], others["gap"], rtol=0, atol=1e-12)
              and ((others["dm_stat"] > 0) == (others["ratio"] < 1)).all())
        check(f"{label}: no change exactly 1 against itself; the tests' mean equals the ratios' gap; every DM sign "
              "agrees with its ratio", ok, f"{len(others)} model-horizon rows")
    rt12 = pd.concat([bt_all, *single_bt.values()])
    rt12 = rt12[(rt12["model"] == "real terms") & (rt12["h"] == 12)]["pred"]
    check("real terms: every 12-month forecast is exactly log(1.02)",
          np.allclose(rt12, np.log1p(TARGET), rtol=0, atol=0), f"{len(rt12):,} forecasts")
    phi = 0.5 ** (1 / HALF_LIFE)
    y, u = simulate_level(100_000, reverting_variance(POWER_RATIOS[0], 48, phi), phi, np.random.default_rng(SEED))
    l0, l1 = oracle_losses(y, u, phi, 48)
    got = float(np.sqrt(l1.mean() / l0.mean()))
    check(f"power simulation: on a 100,000-month run the oracle's 48-month RMSE ratio is within 0.01 of "
          f"{POWER_RATIOS[0]:.2f}", abs(got - POWER_RATIOS[0]) <= 0.01, f"{got:.3f}")
    ck = pd.DataFrame(rows)

    lengths = {"a typical panel market (median length)": int(np.median([len(s) for s in panel.values()]))}
    lengths.update({label: len(s) for label, s in singles.items()})
    pw, phi = power(lengths)

    fr_table, fr_corr, fr_n = france(raw[(EUROSTAT, "FR")], raw[(INSEE, "FR")])
    stats = pd.DataFrame([series_stats("France, Eurostat HICP", np.exp(panel["FR"])),
                          *[series_stats(k, np.exp(s)) for k, s in singles.items()],
                          *[series_stats(f"{g}, Eurostat HICP", np.exp(panel[g])) for g in core if g != "FR"]])

    lines = [
        "# X7 part 5: does the null survive without France, and on the two long histories?",
        "",
        "Generated by `analysis/level_long.py`; the method is in its docstring. Part 1's back-test (`level_forecast.py`)"
        " is re-run unchanged, plus part 2a's real terms (the level grows at the ECB's "
        f"{TARGET:.0%} target), on part 1's panel with and without France and on two long series part 1 never used: "
        "the UK's ONS index and US CPI used cars (US data). The tables read as in `level_forecast_report.md`.",
        "",
        "## The series",
        "",
        md_table(stats),
        "",
        "What each series prices, from its producer's method notes:",
        "- **France (INSEE, which compiles France's HICP):** Argus guide values for cars aged 1, 3 and 5 years, 123 "
        f"models. From {FR_METHOD_FROM}, each car's index moves each month by the twelfth root of its year-on-year "
        "change, which INSEE says introduces a lag (method note, 12 February 2018: "
        "https://www.insee.fr/en/statistiques/documentation/IPC_op%C3%A9rations%20changement%20ann%C3%A9e%202018.pdf).",
        "- **UK (ONS D7E9):** to January 2024, retail prices from a trade guide for 35 models aged 1-3 years; from "
        "February 2024, Auto Trader listings; the published series is not revised "
        "(https://www.ons.gov.uk/economy/inflationandpriceindices/articles/"
        "usingautotradercarlistingsdatatotransformconsumerpricestatisticsuk/2022-06-28 and the December 2023 impact "
        "analysis).",
        "- **US (BLS CUSR0000SETA02, US data):** J.D. Power valuation prices for cars aged 2-7 years, seasonally "
        "adjusted (https://www.bls.gov/cpi/factsheets/used-cars-and-trucks.htm). Published since December 1952; not "
        f"adjusted for quality from 1952 to 1987, so the series is also run from {US_QUALITY_FROM} "
        "(Pashigian, BLS working paper 338, 2001: https://www.bls.gov/osmr/research-papers/2001/ec010060.htm).",
        "",
        "All three are guide or valuation prices for most of their history, not auction or transaction prices.",
        "",
        "## France: the method in the data",
        "",
        md_table(fr_table),
        "",
        f"The Eurostat and INSEE French series' monthly log changes correlate at {fr_corr:.3f} over {fr_n} months.",
        "",
        "## Summary: every set",
        "",
        "Lowest error: the model with the lowest RMSE ratio against no change, and its DM-HLN p (two-sided, so a "
        "small p beside a ratio above 1 means significantly worse). Real terms' downside ratio below 1 is a smaller "
        "expected shortfall. Windows: origin months over the horizon, per market for the single series.",
        "",
        md_table(summary(sets)),
        "",
    ]
    for label, sc in sets.items():
        lines += [f"## {label}", "", md_table(fmt(sc)), "", verdict(sc), ""]
    lines += [
        "## Power: what each history length can detect",
        "",
        f"Simulated log level: a random walk plus a mean-reverting part with a half-life of {HALF_LIFE} months "
        f"(monthly coefficient {phi:.4f}), sized so the oracle, which knows that part, has the stated RMSE ratio "
        f"against no change at 48 months. {POWER_SEEDS} worlds per row; detected means DM-HLN p < 0.05 in the "
        "oracle's favour. The oracle has no estimation error, so these are upper bounds for any real forecaster. A "
        "panel of markets detects more than one market of the same length, less than the count suggests because "
        "markets move together.",
        "",
        md_table(pw),
        "",
        "## Checks",
        "",
        md_table(ck),
        "",
        "## Limits",
        "",
        "- **Guide prices.** France, the UK to January 2024 and the US are guide or valuation prices, not the auction "
        "prices a lessor gets (X6 part 1's basis risk; part 3 found the lessor's margin moved about twice the index). "
        "This part tests France and history length, not that gap.",
        "- **One US method break is handled, others are not.** BLS rotated the sample (last in 2018) and changed the "
        "mileage adjustment in January 2024. The UK changed source in February 2024.",
        "- **Real terms uses 2% throughout,** fixed in advance as in part 2a, though neither the UK nor the US had a "
        "2% target for most of its history.",
        "- **Seasonality.** The US series is seasonally adjusted; the UK and Eurostat series are not. It matters only "
        "at 3 months.",
        "- **The power simulation has one shape of skill,** slow mean reversion. A forecaster whose skill takes "
        "another shape has different power.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(summary(sets).to_string(index=False))
    print(pw.to_string(index=False))
    print(fr_table.to_string(index=False), fr_corr)
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
