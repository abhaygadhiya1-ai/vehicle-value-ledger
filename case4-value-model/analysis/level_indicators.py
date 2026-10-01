"""X7 part 2: does information from outside the index beat "no change" for the used-car price level?

Part 1 (`level_forecast.py`) found that from 12 months on no model of the index's own past beats no change detectably,
and that estimating a drift is what costs at long horizons. Part 2 adds outside information, one indicator at a time.

Every indicator enters the same way, fixed before any result was seen:
  - as its deviation from its own average up to that month (real time: each month's average uses no later month);
  - with one slope per horizon shared by all markets, fitted by least squares on the windows that had ended by the
    origin month, *within* markets: each market's own averages are taken out (market fixed effects), so neither the
    price's drift nor differences between markets can enter the slope. The first versions fitted it pooled, and an
    indicator equal to the realised change got a negative slope at 48 months: within every market the relation was
    strongly positive, but markets with high readings had steep average falls (Simpson's paradox). The forecast
    uses the slope alone, so a normal reading forecasts no change, and no drift is forecast;
  - forecasting the h-month log change directly.
Origins, horizons, markets and scores are part 1's (`level_forecast.score`): RMSE and downside against no change on
the same windows, each market weighted equally, DM-HLN and Clark-West.

2a, no download:
  real terms   no change after inflation: the level grows at the ECB's 2% target ("aiming for 2% inflation over the
               medium term", ECB monetary policy strategy). Fixed in advance; nothing is estimated.
  used-to-new  the log ratio of the used-car index (CP07112) to the new-car index (CP07111), both held. Does a used
               level that ran ahead of new prices fall back?

2b, the supply pipeline:
  pipeline     the change over the forecast window in the cars coming back: new registrations 49-60 months before
               the target month against the same 12 months before the origin (ECB short-term statistics; DE, FR, IT,
               ES, PT, PL; no NL). Known at the origin at every horizon up to 48 months.

2c, the user's macro series, each as its change over the past 12 months (fixed before any result):
  loan rate    the rate on new consumer loans (ECB MIR), two months back so it is surely published
  inflation    the all-items HICP (CP00, Eurostat)
  fuel         the HICP for fuels and lubricants (CP0722, Eurostat)
  stocks       the Euro Stoxx 50 (ECB, from DataStream), the same series for every market

Placebo: each estimated indicator is re-run with its series shifted in time within each market (circularly), so its
values no longer line up with the months they describe. A real signal should beat most shifts.

Checks: the real-terms forecast is exactly the target compounded; the within-market slope returns the exact answer on
a toy panel where the pooled slope has the wrong sign; each forecast's realised change and indicator value match a
recomputation from the panel exactly; an indicator equal to the realised change beats no change at 3 and 12 months (at
long horizons it need not, because the drift it leaves out is large; an earlier bar of 0.5 at 3 months failed on
Slovenia's steep drift and was replaced by the exact bookkeeping check); a noise indicator finds no skill; forecasts
made up to a cut-off month do not change when every later price and indicator value is replaced by noise.

Usage: .venv/bin/python analysis/level_indicators.py [--pull]   (writes analysis/level_indicators_report.md;
       --pull fetches the downloaded inputs again)
"""
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_reference import _eurostat_rows  # noqa: E402
from build_unified import md_table  # noqa: E402
from level_forecast import HORIZONS, MIN_TRAIN, fmt, histories, score, verdict  # noqa: E402

OUT = HERE / "level_indicators_report.md"
REFERENCE = HERE.parent / "data" / "reference"
NEW_CARS = REFERENCE / "new_car_price_indices.parquet"
TARGET = 0.02            # the ECB's inflation target
MIN_X = 24               # months of an indicator before its own average counts
MIN_PAIRS = 36           # ended windows before a slope is fitted
PLACEBO_SHIFTS = (18, 30, 42, 54, 66, 78, 90, 102)
CUT = "2019-12"
SEED = 7

CACHE = REFERENCE / "level_indicators.parquet"     # downloaded series; `--pull` fetches them again
ECB = "https://data-api.ecb.europa.eu/service/data/{key}?format=csvdata&detail=dataonly"
# New passenger-car registrations, working-day and seasonally adjusted (ECB short-term statistics). No NL series
# exists, and they end in December 2022.
REGISTRATIONS = {g: f"STS/M.{g}.Y.CREG.PC0000.3.ABS" for g in ("DE", "FR", "IT", "ES", "PT", "PL")}
# The cars coming back at a month are those registered 49-60 months earlier: X3's 60-month wave and the months
# after the 48-month one. At every horizon up to 48 months, that window ends before the origin, so it is published.
RETURN_AGE = (49, 60)
assert max(HORIZONS) <= RETURN_AGE[0] - 1
# Bank interest rates on new loans to households for consumption (ECB MIR). These are the markets with a series: CZ,
# DK, EL, HU, PL, RO and SE have none, and NL's ends in 2002. Taken two months back, so it is surely published.
LOAN_RATES = {g: f"MIR/M.{g}.B.A2B.A.R.A.2250.EUR.N" for g in (
    "AT", "BG", "CY", "DE", "EE", "ES", "FI", "FR", "HR", "IE", "IT", "LT", "LU", "LV", "MT", "PT", "SI", "SK")}
RATE_LAG = 2
STOXX = "FM/M.U2.EUR.DS.EI.DJES50I.HSTA"         # Euro Stoxx 50, monthly average (ECB, from DataStream)
HICP = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx"
        "?format=JSON&coicop={coicop}&unit=I15")
HICP_SERIES = {"all items": "CP00", "fuel": "CP0722"}   # CP0722 = fuels and lubricants for personal transport


def mnum(months):
    """'YYYY-MM' strings to month numbers."""
    m = pd.Index(months).astype(str)
    return m.str[:4].astype(int).to_numpy() * 12 + m.str[5:7].astype(int).to_numpy() - 1


def new_car_levels():
    """The new-car index (CP07111) per market, as log levels by month."""
    d = pd.read_parquet(NEW_CARS)
    return {g: np.log(x.set_index("month")["index_value"].astype(float)).dropna()
            for g, x in d.groupby("geo", observed=True)}


def used_to_new(panel, new):
    """Used over new, in logs, per market: the same for every horizon."""
    x = {g: (s - new[g]).dropna() for g, s in panel.items() if g in new}
    return {h: x for h in HORIZONS}


def raw_series(pull=False):
    """Every downloaded input as {(series, geo): values by month}, cached in data/reference (private)."""
    wanted = ({("registrations", g): key for g, key in REGISTRATIONS.items()}
              | {("loan rate", g): key for g, key in LOAN_RATES.items()} | {("stocks", "EA"): STOXX})
    have = (pd.read_parquet(CACHE) if CACHE.exists() and not pull
            else pd.DataFrame(columns=["series", "geo", "month", "value", "source"]))
    got = set(zip(have["series"], have["geo"]))
    fetched = []
    for (series, geo), key in wanted.items():
        if (series, geo) in got:
            continue
        url = ECB.format(key=key)
        d = pd.read_csv(io.StringIO(requests.get(url, timeout=120).text))
        fetched.append(pd.DataFrame({"series": series, "geo": geo, "month": d["TIME_PERIOD"].astype(str),
                                     "value": d["OBS_VALUE"].astype(float), "source": url}))
    for series, coicop in HICP_SERIES.items():
        if series in set(have["series"]):
            continue
        url = HICP.format(coicop=coicop)
        d = _eurostat_rows(url)
        fetched.append(pd.DataFrame({"series": series, "geo": d["geo"], "month": d["month"].astype(str),
                                     "value": d["index_value"].astype(float), "source": url}))
    if fetched:
        have = pd.concat([have, *fetched], ignore_index=True)
        have.to_parquet(CACHE)
    return {(s, g): x.set_index("month")["value"].astype(float).sort_index()
            for (s, g), x in have.groupby(["series", "geo"])}


def pipeline(panel, regs):
    """Per horizon: the change in the cars coming back over the forecast window, in logs. The 12 months of
    registrations RETURN_AGE before the target month against the same 12 months before the origin."""
    lo, hi = RETURN_AGE
    out = {h: {} for h in HORIZONS}
    for g, r in regs.items():
        if g not in panel:
            continue
        r = pd.Series(r.to_numpy(), index=pd.PeriodIndex(r.index, freq="M"))
        assert len(r) == len(pd.period_range(r.index.min(), r.index.max(), freq="M")), f"{g}: gaps"
        supply = np.log(r.rolling(hi - lo + 1).sum().dropna())
        supply.index = supply.index + lo            # at month T: registrations from T - 60 to T - 49
        for h in HORIZONS:
            ahead = supply.copy()
            ahead.index = ahead.index - h           # at origin t: the supply at t + h
            x = (ahead - supply).dropna()
            out[h][g] = pd.Series(x.to_numpy(), index=x.index.astype(str))
    return out


def change12(series, lag=0):
    """The change over 12 months of a monthly series, taken `lag` months before each month."""
    s = pd.Series(series.to_numpy(dtype=float), index=pd.PeriodIndex(series.index, freq="M"))
    s = s[~s.index.duplicated()].sort_index()
    s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))   # a missing month stays missing
    x = (s - s.shift(12)).shift(lag).dropna()
    return pd.Series(x.to_numpy(), index=x.index.astype(str))


def macro(panel, raw, name):
    """2c: the 12-month change in one outside series, per market (the same for every horizon)."""
    if name == "loan rate":
        x = {g: change12(raw[("loan rate", g)], RATE_LAG) for g in LOAN_RATES if g in panel}
    elif name == "stocks":
        stocks = change12(np.log(raw[("stocks", "EA")]))
        x = {g: stocks for g in panel}
    else:
        x = {g: change12(np.log(raw[(name, g)])) for g in panel if (name, g) in raw}
    return {h: x for h in HORIZONS}


def realtime(x):
    """Each month's value less its own average up to that month."""
    return x - x.expanding(min_periods=MIN_X).mean()


def cumulative(pairs):
    """Per market: the windows' end months in order, with running sums of x, y, xy and xx."""
    per = []
    for _, d in pairs.groupby("market", sort=False):
        d = d.sort_values("end", kind="stable")
        x, y = d["x"].to_numpy(dtype=float), d["y"].to_numpy(dtype=float)
        per.append((d["end"].to_numpy(), np.cumsum(x), np.cumsum(y), np.cumsum(x * y), np.cumsum(x * x)))
    return per


def within_slope(per, t):
    """The slope on every window ended by month t, within markets. Each market's own averages are taken out, so
    neither the price's drift nor differences between markets can enter it."""
    num = den = 0.0
    n = 0
    for ends, sx, sy, sxy, sxx in per:
        k = int(np.searchsorted(ends, t, side="right"))
        if k < 2:
            continue
        i = k - 1
        num += sxy[i] - sx[i] * sy[i] / k
        den += sxx[i] - sx[i] ** 2 / k
        n += k
    return num / den if n >= MIN_PAIRS and den > 0 else np.nan


def windows(panel, xh, h):
    """Every market's h-month windows: origin, end month, the indicator's real-time deviation, the realised change."""
    pairs = []
    for g, s in panel.items():
        if g not in xh[h]:
            continue
        v = s.to_numpy(dtype=float)
        y = np.full(len(v), np.nan)
        y[:-h] = v[h:] - v[:-h]
        m = mnum(s.index)
        pairs.append(pd.DataFrame({"market": g, "origin": s.index, "m": m, "end": m + h, "pos": np.arange(len(v)),
                                   "x": realtime(xh[h][g]).reindex(s.index).to_numpy(), "y": y}))
    return pd.concat(pairs, ignore_index=True)


def hindsight(panel, xh):
    """Per horizon, the within-market slope on every window up to the last month: in sample, not a forecast."""
    out = {}
    for h in HORIZONS:
        p = windows(panel, xh, h).dropna(subset=["x", "y"])
        out[h] = within_slope(cumulative(p), p["end"].max())
    return out


def direct(panel, xh):
    """One indicator's forecasts. Per horizon, a slope shared by all markets, fitted within markets at each origin on
    every window that had ended by then. Returns market, origin, h, pred, actual, the slope used and the deviation."""
    out = []
    for h in HORIZONS:
        p = windows(panel, xh, h)
        per = cumulative(p.dropna(subset=["x", "y"]))
        test = p[(p["pos"] >= MIN_TRAIN - 1) & p["x"].notna() & p["y"].notna()].copy()
        slopes = {t: within_slope(per, t) for t in np.unique(test["m"])}   # windows ending on or before the origin
        test["slope"] = test["m"].map(slopes)
        test = test.dropna(subset=["slope"])
        test["pred"] = test["slope"] * test["x"]     # the slope alone: no drift is forecast
        test["h"] = h
        out.append(test.rename(columns={"y": "actual"})[["market", "origin", "h", "pred", "actual", "slope", "x"]])
    return pd.concat(out, ignore_index=True)


def real_terms(panel):
    """No change after inflation: the log level grows by the target, compounded, over the horizon."""
    rows = []
    for g, s in panel.items():
        v = s.to_numpy(dtype=float)
        for h in HORIZONS:
            for i in range(MIN_TRAIN - 1, len(v) - h):
                rows.append((g, s.index[i], h, h / 12 * np.log1p(TARGET), v[i + h] - v[i]))
    return pd.DataFrame(rows, columns=["market", "origin", "h", "pred", "actual"])


def with_no_change(frames):
    """Stack the models and add a no-change row for every window any of them forecasts."""
    bt = pd.concat([f.assign(model=name) for name, f in frames.items()], ignore_index=True)
    base = bt.drop_duplicates(["market", "origin", "h"])[["market", "origin", "h", "actual"]].assign(
        model="no change", pred=0.0)
    return pd.concat([bt, base], ignore_index=True)


def circular(xh, k):
    """Every market's indicator shifted k months in time, wrapping round, so values no longer match their months."""
    return {h: {g: pd.Series(np.roll(x.to_numpy(), k), index=x.index) for g, x in xg.items()} for h, xg in xh.items()}


def placebo(panel, xh, name):
    """The indicator's RMSE ratio at each horizon, and the same after each time shift."""
    rows = []
    real = score(with_no_change({name: direct(panel, xh)}), list(panel))[0].set_index(["h", "model"])
    for h in HORIZONS:
        shifted = []
        for k in PLACEBO_SHIFTS:
            sc = score(with_no_change({name: direct(panel, circular(xh, k))}), list(panel))[0]
            shifted.append(float(sc[(sc["h"] == h) & (sc["model"] == name)]["ratio"].iloc[0]))
        r = float(real.loc[(h, name), "ratio"])
        rows.append({"indicator": name, "months ahead": h, "RMSE ratio": f"{r:.3f}",
                     "placebo median": f"{np.median(shifted):.3f}", "placebo best": f"{min(shifted):.3f}",
                     "shifts doing as well": f"{sum(v <= r for v in shifted)} of {len(shifted)}"})
    return rows


def checks(panel, indicators, bt):
    rows = []

    def check(name, passes, got):
        rows.append({"check": name, "got": got, "passes": bool(passes)})

    rt = bt[(bt["model"] == "real terms") & (bt["h"] == 12)]["pred"]
    check("real terms: the 12-month forecast is exactly log(1.02)", np.allclose(rt, np.log1p(TARGET), rtol=0, atol=0),
          f"{rt.iloc[0]:.12f}")

    oracle = {}
    for h in HORIZONS:
        oracle[h] = {}
        for g, s in panel.items():
            v = s.to_numpy(dtype=float)
            y = np.full(len(v), np.nan)
            y[:-h] = v[h:] - v[:-h]
            oracle[h][g] = pd.Series(y, index=s.index).dropna()
    o = direct(panel, oracle)
    sc = score(with_no_change({"oracle": o}), list(panel))[0].set_index(["h", "model"])
    last = o.sort_values("origin", kind="stable").groupby("h")["slope"].last()
    check("an indicator equal to the realised change (look-ahead on purpose) beats no change at 3 and 12 months, "
          "where the drift it leaves out is small (at 36-48 months it need not). Its slopes at the last origin: "
          + ", ".join(f"{h}m {v:.2f}" for h, v in last.items()),
          sc.loc[(3, "oracle"), "ratio"] < 1 and sc.loc[(12, "oracle"), "ratio"] < 1,
          ", ".join(f"{h}m {sc.loc[(h, 'oracle'), 'ratio']:.3f}" for h in HORIZONS))

    for name, build in indicators.items():
        xh = build(panel)
        d = direct(panel, xh)
        at = {g: {m: i for i, m in enumerate(s.index)} for g, s in panel.items()}
        rt = {(h, g): realtime(x) for h, xg in xh.items() for g, x in xg.items()}
        want_y = np.array([panel[g].iloc[at[g][o] + h] - panel[g].iloc[at[g][o]]
                           for g, o, h in zip(d["market"], d["origin"], d["h"])])
        want_x = np.array([rt[(h, g)][o] for g, o, h in zip(d["market"], d["origin"], d["h"])])
        gap = max(float(np.abs(d["actual"].to_numpy() - want_y).max()), float(np.abs(d["x"].to_numpy() - want_x).max()))
        check(f"bookkeeping, {name}: every forecast's realised change and indicator value, recomputed from the panel "
              f"and the indicator at its origin month, match exactly ({len(d):,})", gap == 0.0,
              f"largest gap {gap:.1e}")

    n = 20   # two toy markets, y = 0.5 x + a market constant, placed so the pooled slope is negative
    toy = pd.DataFrame({"market": ["A"] * n + ["B"] * n, "end": np.tile(np.arange(n), 2),
                        "x": np.r_[np.arange(n), 30 + np.arange(n)].astype(float)})
    toy["y"] = 0.5 * toy["x"] + np.where(toy["market"] == "A", 50.0, -50.0)
    pooled_slope = float(np.polyfit(toy["x"], toy["y"], 1)[0])
    got = within_slope(cumulative(toy), n)
    check(f"the slope is fitted within markets: a toy panel with slope 0.5 in each market and a pooled slope of "
          f"{pooled_slope:+.2f} returns 0.5", abs(got - 0.5) < 1e-12 and pooled_slope < 0, f"{got:.12f}")

    rng = np.random.default_rng(SEED)
    noise = {g: pd.Series(rng.normal(size=len(s)), index=s.index) for g, s in panel.items()}
    sc = score(with_no_change({"noise": direct(panel, {h: noise for h in HORIZONS})}), list(panel))[0]
    sc = sc[sc["model"] == "noise"]
    check("a noise indicator finds no skill: no RMSE ratio below 0.98 with DM-HLN p < 0.05",
          not ((sc["ratio"] < 0.98) & (sc["dm_p"] < 0.05)).any(),
          ", ".join(f"{r.h}m {r.ratio:.3f}" for r in sc.itertuples()))

    garbled_panel = {g: pd.Series(np.where(s.index > CUT, rng.normal(0, 5, len(s)), s.to_numpy()), index=s.index)
                     for g, s in panel.items()}
    for name, build in indicators.items():
        real = direct(panel, build(panel)).set_index(["market", "origin", "h"])["pred"]
        early = direct(garbled_panel, build(garbled_panel, garble=True)).set_index(["market", "origin", "h"])["pred"]
        early = early[early.index.get_level_values("origin") <= CUT]
        gap = float((early - real.loc[early.index]).abs().max())
        check(f"no look-ahead, {name}: every price and input after {CUT} replaced by noise; forecasts made up to {CUT} "
              f"unchanged ({len(early):,})", gap == 0.0 and len(early) > 0, f"largest change {gap:.1e}")
    return pd.DataFrame(rows)


def main():
    panel, core = histories()
    new = new_car_levels()
    raw = raw_series(pull="--pull" in sys.argv)
    regs = {g: raw[("registrations", g)] for g in REGISTRATIONS}
    rng = np.random.default_rng(SEED)

    def garbled(series):
        """Every value after CUT replaced by positive noise around the series' median."""
        return {g: pd.Series(np.where(s.index > CUT, s.median() * rng.uniform(0.2, 5, len(s)), s.to_numpy()),
                             index=s.index) for g, s in series.items()}

    # The estimated indicators, each built from the panel and its own inputs (garbled for the look-ahead check).
    indicators = {
        "used-to-new": lambda p, garble=False: used_to_new(p, garbled(new) if garble else new),
        "pipeline": lambda p, garble=False: pipeline(p, garbled(regs) if garble else regs),
    }
    for name in ("loan rate", "inflation", "fuel", "stocks"):
        series = {"inflation": "all items"}.get(name, name)
        indicators[name] = (lambda p, garble=False, series=series:
                            macro(p, garbled(raw) if garble else raw, series))
    frames = {"real terms": real_terms(panel)}
    frames.update({name: direct(panel, build(panel)) for name, build in indicators.items()})
    bt = with_no_change(frames)
    all_scores, _ = score(bt, list(panel))
    core_scores, _ = score(bt, core)
    last = (pd.concat(frames[n].assign(model=n) for n in indicators).sort_values("origin", kind="stable")
            .groupby(["model", "h"])["slope"].last())
    slopes = pd.DataFrame(
        [{"indicator": n, "slope": "at the last origin (used in forecasts)",
          **{f"{h} months": f"{last[(n, h)]:+.3f}" for h in HORIZONS}} for n in indicators]
        + [{"indicator": n, "slope": "hindsight: every window to the end (in sample, not a forecast)",
            **{f"{h} months": f"{v:+.3f}" for h, v in hindsight(panel, build(panel)).items()}}
           for n, build in indicators.items()]).sort_values("indicator", kind="stable")
    plc = pd.DataFrame([r for name, build in indicators.items() for r in placebo(panel, build(panel), name)])
    ck = checks(panel, indicators, bt)
    reg_span = {g: f"{s.index.min()} to {s.index.max()}" for g, s in regs.items()}

    lines = [
        "# X7 part 2: does outside information beat \"no change\" for the used-car price level?",
        "",
        "Generated by `analysis/level_indicators.py`; the method is in its docstring. Same panel, origins, horizons and "
        "scores as part 1 (`level_forecast_report.md`, which explains every column). Each estimated indicator enters "
        "as its deviation from its own average so far, with one slope per horizon fitted within markets on the windows "
        "that had ended by the origin month; the forecast is the slope times the deviation, so a normal reading "
        "forecasts no change. Each indicator is scored on the markets and months it covers, against no change on the "
        "same windows.",
        "",
        "## The indicators",
        "",
        "**2a, no download:**",
        f"- **real terms:** the level grows at the ECB's {TARGET:.0%} inflation target. Nothing is estimated.",
        "- **used-to-new:** the used-car index over the new-car index (CP07111). A negative slope means a used level "
        "that ran ahead of new prices falls back.",
        "",
        "**2b, the supply pipeline:**",
        f"- **pipeline:** the change over the forecast window in the cars coming back: new registrations "
        f"{RETURN_AGE[0]}-{RETURN_AGE[1]} months before the target month against the same 12 months before the origin "
        "(ECB short-term statistics, working-day and seasonally adjusted; "
        + "; ".join(f"{g} {v}" for g, v in reg_span.items()) + "; no NL series). A negative slope means more cars "
        "coming back lowers the level.",
        "",
        "**2c, the user's macro series,** each as its change over the past 12 months:",
        f"- **loan rate:** the rate on new consumer loans (ECB MIR), in percentage points, taken {RATE_LAG} months "
        f"back so it is surely published; {len([g for g in LOAN_RATES if g in panel])} markets (none for CZ, DK, EL, "
        "HU, PL, RO or SE; NL's ends in 2002). Expected sign: negative.",
        "- **inflation:** the all-items HICP (CP00), in logs. Expected sign: positive.",
        "- **fuel:** the HICP for fuels and lubricants (CP0722), in logs. Either sign is plausible.",
        "- **stocks:** the Euro Stoxx 50 (ECB, monthly average), in logs, the same series for every market. Expected "
        "sign: positive.",
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
        "## The fitted slopes",
        "",
        "The slope at the last origin is what the forecasts used. The hindsight slope uses every window to the end of "
        "the data, including windows no forecast could have seen; it shows whether a relation exists at all, not that "
        "it could have been forecast.",
        "",
        md_table(slopes),
        "",
        "## Placebo: each indicator shifted in time",
        "",
        md_table(plc),
        "",
        "## Checks",
        "",
        md_table(ck),
        "",
        "## Limits",
        "",
        "- Part 1's limits all apply: few independent windows at 36 and 48 months, one regime (2021-23) in most "
        "long-horizon windows, and an official retail index rather than auction prices.",
        "- **Real terms uses one target for every market.** Non-euro central banks set their own targets, so for them "
        "it is a round number, not their target.",
        "- **One functional form,** chosen before the results: a linear slope on the indicator's deviation from its own "
        "average. Other forms may do better; trying many would find one by chance. The used-to-new gap trends in "
        "several markets, so its own long-run average is a poor normal there.",
        "- **The pipeline covers six markets** and assumes cars come back 49-60 months after registration everywhere, "
        "taken from the Dutch register (X3). Registrations count all new cars, bought or leased.",
        "- **Six indicators, four horizons, two sets of markets** make many tests. A lone p near 0.05 is noise, and "
        "an indicator counts only if it also beats most of its time-shifted placebos.",
        "- **The macro series are published at different speeds.** The loan rate is taken two months back; the HICP "
        "series are treated as known in their own month, as the used-car index itself is in part 1.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(all_scores[["h", "model", "ratio", "beaten", "markets", "bias", "down", "dm_p", "cw_p"]].round(3)
          .to_string(index=False))
    print(plc.to_string(index=False))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
