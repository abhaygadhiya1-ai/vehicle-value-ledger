"""X13 part 4: the pricer's override band on our own cars. Fixed ±5%, or tied to the engine's calibrated band?

Skeptic A11: pricers may move the value engine's price by ±5% (`price_band_pct`), less than the engine's own typical
error, so the band stops people correcting exactly where the model is weakest. The repair ties the band to the
engine's uncertainty. X13 part 3 showed on real people's price estimates that a tied band is only as good as its
uncertainty's power to flag the model's large errors: a local uncertainty that missed the one badly priced apartment
bought nothing. So this script asks two questions of the engine itself.

1. Measured, no behaviour assumed. On held-out cars in eight markets (priced exactly as `conformal_bands.py` does:
   engine fitted on half the recent listings, calibrated per market and age on half the rest, scored on the other
   half): how wide is the calibrated 80% band against ±5%; how many advert prices lie outside ±5% of the engine's
   price; does the band's width flag the engine's large errors (rank correlation, error by width quintile); and how
   much of the engine's error could a pricer who knew the true price remove under each band (an upper bound)?
2. A pricer with the behaviours X13 measured or sourced. The pricer's own view of the engine's log error e is
   s = rho e + sqrt(1 - rho^2) k sigma z (z standard normal). rho^2 is the share of the engine's error the pricer can
   see, which no source measures for cars, so it is swept from 0 to 1. Following naive advice weighting (Balakrishnan,
   Ferreira & Tong; part 3's median weight on the model), the pricer moves by w s with one weight w on every car,
   w = 1 - the median weight on the model from `band_replay_params.csv`. The move is capped by the band. Two readings
   of the pricer's noise: the same on every car (sigma = the spread of e over all cars), or scaled to the car's
   market-and-age slice (sigma = that slice's spread). k is the noise's spread against the engine's error: 1, and the
   lay value part 3 measured. The score is the mean absolute log error against the advert price.

Band rules: the engine's price only; free adjustment; fixed ±5%; a band tied to the calibrated band and scaled to the
same average width as ±5% (the same latitude, redistributed); and the full calibrated 80% band (A11's repair as
written).

Limits, stated rather than solved: advert prices, not transactions; the pricer model is a model, its one unknown
swept; post-hoc capping, while Dietvorst's people moved less than a cap allowed; the calibration's guarantee is for
today's market (exchangeability), not a moved level.

Checks: the calibrated coverage of all test cars reproduces `conformal_bands_report.md`; the tied caps average ±5%
exactly; the clip rule on a toy case; with no information (rho = 0) free adjustment is worse than the engine alone.

Usage: .venv/bin/python analysis/override_band.py   (writes analysis/override_band_report.md; about 10 minutes the
first time, then reads its cache in data/; --reprice prices again)
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
import conformal_bands as cb  # noqa: E402

OUT = HERE / "override_band_report.md"
CACHE = HERE.parent / "data/x13_override_priced.parquet"
PARAMS = HERE / "band_replay_params.csv"
FIXED = np.log(1.05)                          # ±5%, the register's price_band_pct
RHO2 = (0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
REPS = 20
SEED = 7


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def priced_cars(reprice):
    if CACHE.exists() and not reprice:
        return pd.read_parquet(CACHE)
    frames = []
    for m in cb.MARKETS:
        t, _ = cb.price_market(m)
        frames.append(t)
        print(f"priced {m}: {len(t):,} cars")
    p = pd.concat(frames)
    p["band"] = p["band"].astype(str)
    p = p.reset_index(drop=True)
    p.to_parquet(CACHE)
    return p


def calibrate(priced):
    """Test cars with the band calibrated per market and age (conformal_bands.py's rule), on the log scale."""
    cal, test = priced[priced["set"] == "calibration"], priced[priced["set"] == "test"].copy()
    q_age, q_market = cb.slice_q(cal, ["market", "band"])
    test["q"] = [q_age.get((m, b), q_market[m]) for m, b in zip(test["market"], test["band"])]
    test["lo"] = np.log(test["low"] / test["value"]) - test["q"]      # allowed log move down, full band
    test["hi"] = np.log(test["high"] / test["value"]) + test["q"]     # allowed log move up
    test["u"] = (test["hi"] - test["lo"]) / 2                          # the band's half-width, log scale
    test["e"] = np.log(test["price"] / test["value"])                  # the engine's error
    cal_e = np.log(cal["price"] / cal["value"])
    slice_sd = cal_e.groupby([cal["market"], cal["band"]]).std()
    market_sd = cal_e.groupby(cal["market"]).std()
    test["sd_slice"] = [slice_sd.get((m, b), market_sd[m]) if (cal["market"].eq(m) & cal["band"].eq(b)).sum() >= 30
                        else market_sd[m] for m, b in zip(test["market"], test["band"])]
    return test


def capped(move, lo, hi):
    return np.clip(move, lo, hi)


def rules(t):
    """Each rule's allowed log move, down and up, per car."""
    scale = FIXED / t["u"].mean()
    n = len(t)
    return {
        "engine only": (np.zeros(n), np.zeros(n)),
        "free adjustment": (np.full(n, -np.inf), np.full(n, np.inf)),
        "fixed ±5%": (np.full(n, -FIXED), np.full(n, FIXED)),
        "tied, same average as ±5%": (-(t["u"] * scale).values, (t["u"] * scale).values),
        "the full calibrated 80% band": (t["lo"].values, t["hi"].values),
    }


def oracle(t, rl):
    """A pricer who knows the true price moves as far as the band allows."""
    rows = []
    base = np.abs(t["e"]).mean()
    for name, (lo, hi) in rl.items():
        left = np.abs(t["e"].values - capped(t["e"].values, lo, hi)).mean()
        rows.append({"band": name, "mean error left, all cars": pct(left, 1),
                     "share of the engine's error removable": pct(1 - left / base),
                     "cars 12+ years: error left": pct(np.abs((t["e"] - capped(t["e"].values, lo, hi))[t["old"]]).mean(), 1)})
    return pd.DataFrame(rows)


def simulate(t, rl, rho2, w, k, noise):
    rng = np.random.default_rng(SEED)
    e = t["e"].values
    sigma = np.full(len(t), e.std()) if noise == "same" else t["sd_slice"].values
    rho = np.sqrt(rho2)
    out = {name: 0.0 for name in rl}
    old = {name: 0.0 for name in rl}
    for _ in range(REPS):
        s = rho * e + np.sqrt(1 - rho2) * k * sigma * rng.standard_normal(len(e))
        for name, (lo, hi) in rl.items():
            err = np.abs(e - capped(w * s, lo, hi))
            out[name] += err.mean() / REPS
            old[name] += err[t["old"].values].mean() / REPS
    return out, old


def breakeven(curve, a, b):
    """The smallest rho^2 on the grid from which rule a beats rule b at every larger value."""
    wins = [curve[r][a] < curve[r][b] for r in RHO2]
    for i, r in enumerate(RHO2):
        if all(wins[i:]):
            return f"{r:.2f}"
    return "never on the grid"


def main():
    priced = priced_cars("--reprice" in sys.argv)
    t = calibrate(priced)
    t["old"] = t["band"].str.startswith("(12")
    params = pd.read_csv(PARAMS).set_index("key")["value"]
    w = 1 - params["weight_on_model_median"]
    k_lay = params["signal_spread_all"]

    # ---- 1. measured
    t["outside5"] = np.abs(t["e"]) > FIXED
    t["outside_band"] = (t["e"] < t["lo"]) | (t["e"] > t["hi"])
    scale = FIXED / t["u"].mean()
    order = [b for b in (str(c).replace(", ", " to ") for c in pd.cut([1], cb.AGE_BANDS).categories) if b in set(t["band"])]
    by_age = t.groupby("band").agg(cars=("e", "size"), half=("u", "median"),
                                   out5=("outside5", "mean"), outb=("outside_band", "mean"),
                                   err=("e", lambda x: np.abs(x).mean())).reindex(order)
    by_age.loc["all ages"] = [len(t), t["u"].median(), t["outside5"].mean(), t["outside_band"].mean(),
                              np.abs(t["e"]).mean()]
    age_table = pd.DataFrame({"car age, years": [b.replace("(", "").replace("]", "") for b in by_age.index],
                              "test cars": by_age["cars"].astype(int).values,
                              "calibrated 80% band, median half-width": [pct(np.exp(x) - 1) for x in by_age["half"]],
                              "tied cap, same average as ±5% (median)": [pct(np.exp(x * scale) - 1, 1)
                                                                          for x in by_age["half"]],
                              "engine's mean error": [pct(x, 1) for x in by_age["err"]],
                              "adverts outside ±5% of the engine's price": [pct(x) for x in by_age["out5"]],
                              "adverts outside the calibrated band": [pct(x) for x in by_age["outb"]]})
    by_mkt = t.groupby("market", sort=False).agg(cars=("e", "size"), half=("u", "median"), out5=("outside5", "mean"))
    mkt_table = pd.DataFrame({"market": by_mkt.index, "test cars": by_mkt["cars"].values,
                              "calibrated 80% band, median half-width": [pct(np.exp(x) - 1) for x in by_mkt["half"]],
                              "adverts outside ±5%": [pct(x) for x in by_mkt["out5"]]})

    rho_all = spearmanr(t["u"], np.abs(t["e"])).statistic
    within = [spearmanr(g["u"], np.abs(g["e"])).statistic for _, g in t.groupby("market")]
    t["quint"] = pd.qcut(t["u"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
    qt = t.groupby("quint", observed=True).agg(cars=("e", "size"), half=("u", "median"),
                                               err=("e", lambda x: np.abs(x).mean()),
                                               out5=("outside5", "mean"), old=("old", "mean"))
    share_top = np.abs(t.loc[t["quint"] == 5, "e"]).sum() / np.abs(t["e"]).sum()
    quint_table = pd.DataFrame({"band-width fifth": ["narrowest", "2", "3", "4", "widest"],
                                "cars": qt["cars"].values,
                                "median half-width": [pct(np.exp(x) - 1) for x in qt["half"]],
                                "engine's mean error": [pct(x, 1) for x in qt["err"]],
                                "adverts outside ±5%": [pct(x) for x in qt["out5"]],
                                "cars 12+ years": [pct(x) for x in qt["old"]]})
    ratio = qt["err"].iloc[-1] / qt["err"].iloc[0]
    flag_table = pd.DataFrame([
        ("rank correlation of half-width with absolute error, all test cars", f"{rho_all:.2f}"),
        ("the same, lowest within a market", f"{min(within):.2f}"),
        ("the same, highest within a market", f"{max(within):.2f}"),
        ("widest fifth's mean error over the narrowest fifth's", f"{ratio:.1f}"),
        ("share of all the engine's error in the widest fifth", pct(share_top)),
    ], columns=["measure", "value"])

    rl = rules(t)
    orc = oracle(t, rl)

    # ---- 2. the pricer, swept over what they can see
    settings = [("same", 1.0, "noise the same on every car, spread as the engine's error"),
                ("slice", 1.0, "noise scaled to the car's market-and-age slice"),
                ("same", k_lay, "noise the same on every car, lay spread from part 3"),
                ("slice", k_lay, "noise scaled to the slice, lay spread from part 3")]
    curves, old_curves = {}, {}
    for noise, k, label in settings:
        curves[label], old_curves[label] = {}, {}
        for r in RHO2:
            curves[label][r], old_curves[label][r] = simulate(t, rl, r, w, k, noise)
    base = settings[0][2]
    sweep = pd.DataFrame([{"share of the engine's error the pricer can see (rho²)": f"{r:.2f}",
                           **{name: pct(v, 1) for name, v in curves[base][r].items()}} for r in RHO2])
    sweep_old = pd.DataFrame([{"rho²": f"{r:.2f}", **{name: pct(v, 1) for name, v in old_curves[base][r].items()}}
                              for r in RHO2])
    be = pd.DataFrame([{"pricer's noise": label,
                        "tied (same average) beats fixed ±5% from rho²": breakeven(curves[label], "tied, same average as ±5%", "fixed ±5%"),
                        "full calibrated band beats fixed ±5% from": breakeven(curves[label], "the full calibrated 80% band", "fixed ±5%"),
                        "fixed ±5% beats the engine alone from": breakeven(curves[label], "fixed ±5%", "engine only"),
                        "full band beats the engine alone from": breakeven(curves[label], "the full calibrated 80% band", "engine only")}
                       for _, _, label in settings])

    # ---- checks
    rep = next(x for x in (HERE / "conformal_bands_report.md").read_text().splitlines()
               if x.startswith("| calibrated per market and age |"))
    published = float(re.findall(r"(\d+\.\d)%", rep)[0])
    cov = 100 * (~t["outside_band"]).mean()
    scale_ok = abs((t["u"] * FIXED / t["u"].mean()).mean() - FIXED) < 1e-12
    toy = np.allclose(capped(np.array([0.2, -0.3, 0.01]), -0.05, 0.05), [0.05, -0.05, 0.01])
    noinfo = curves[base][0.0]["free adjustment"] > curves[base][0.0]["engine only"]
    ck = pd.DataFrame([
        {"check": "calibrated coverage of all test cars reproduces conformal_bands_report.md",
         "got": f"{cov:.1f}% against {published:.1f}%", "passes": abs(cov - published) < 0.05},
        {"check": "the tied caps average ±5% exactly", "got": "yes" if scale_ok else "no", "passes": scale_ok},
        {"check": "clip rule on a toy case", "got": "yes" if toy else "no", "passes": toy},
        {"check": "with no information, free adjustment is worse than the engine alone",
         "got": f"{pct(curves[base][0.0]['free adjustment'], 1)} against {pct(curves[base][0.0]['engine only'], 1)}",
         "passes": noinfo},
    ])
    all_ok = bool(ck["passes"].all())

    lay_r2 = params["signal_r2_all"]
    orc_i = orc.set_index("band")
    rem = "share of the engine's error removable"
    old_left = "cars 12+ years: error left"
    be_i = be.set_index("pricer's noise")
    full_vs_fixed = sorted(set(be_i.iloc[:, 1]))
    full_vs_engine = sorted(set(be_i.iloc[:, 3]))
    fixed_vs_engine = sorted(set(be_i.iloc[:, 2]))
    old_worse = [f"{r:.2f}" for r in RHO2 if old_curves[base][r]["tied, same average as ±5%"]
                 > old_curves[base][r]["fixed ±5%"]]
    at = age_table.set_index("car age, years")
    half_col, tied_col = "calibrated 80% band, median half-width", "tied cap, same average as ±5% (median)"
    out_col = "adverts outside ±5% of the engine's price"
    findings = [
        f"- **The engine's calibrated band is far wider than ±5% at every age:** median half-width "
        f"{at.loc['all ages', half_col]} over all test cars. {at.loc['all ages', out_col]} of adverts lie outside ±5% of the engine's "
        f"price, so a ±5% band leaves a pricer who knew the true price unable to reach it on most cars.",
        f"- **The engine's band does flag its large errors** (unlike part 3's apartment measure): rank correlation "
        f"{rho_all:.2f} between width and error over all test cars, {min(within):.2f} to {max(within):.2f} within "
        f"markets. The widest fifth has {ratio:.1f} times the narrowest fifth's mean error and holds "
        f"{pct(share_top)} of all the engine's error.",
        f"- **Upper bound (a pricer who knows the price):** ±5% lets them remove {orc_i.loc['fixed ±5%', rem]} of the "
        f"engine's error; the same average latitude tied to the band removes {orc_i.loc['tied, same average as ±5%', rem]}"
        f", but on cars 12 years and older leaves {orc_i.loc['tied, same average as ±5%', old_left]} against "
        f"{orc_i.loc['fixed ±5%', old_left]}; the full band removes {orc_i.loc['the full calibrated 80% band', rem]}.",
        f"- **A band tied to the calibrated band at the same average width as ±5% is never worse than ±5%** on the "
        f"grid, at any level of pricer information, under all four readings of the pricer's noise (break-even "
        f"{', '.join(sorted(set(be_i.iloc[:, 0])))}). It moves latitude from young cars (median cap "
        f"{at.loc['2 to 4', tied_col]} at 2-4 years) to old ones ({at.loc['12 to 30', tied_col]} at 12+), where the engine errs most. "
        f"On cars 12 years and older it is worse than ±5% only at rho² {', '.join(old_worse) or 'none'}. Uptake "
        "should not suffer: in Dietvorst's data the band's width barely moved it.",
        f"- **The full calibrated band (A11's repair as written) needs an informed pricer.** It beats ±5% only once the "
        f"pricer sees a share of the engine's error of {' to '.join(full_vs_fixed)}, and beats the engine alone from "
        f"{' to '.join(full_vs_engine)}. Even ±5% beats the engine alone only from {' to '.join(fixed_vs_engine)}. Lay "
        f"people pricing apartments carried almost none of the model's error (rho² {lay_r2:.3f}, part 3); what a "
        "pricer who inspects the car carries is unmeasured, and the pilot can measure it.",
    ]

    lines = [
        "# X13 part 4: the override band on our own cars",
        "",
        "Generated by `analysis/override_band.py`; the method is in its docstring. Held-out cars in eight markets, "
        "priced and calibrated as in `conformal_bands.py`; every price is an **advert price**. The pricer's weight on "
        f"their own view is {w:.2f} (one minus part 3's median weight on the model) on every car.",
        "",
        "## Checks",
        "",
        md_table(ck.assign(passes=ck["passes"].map({True: "yes", False: "NO"}))),
        "",
        f"All checks pass: {'yes' if all_ok else 'NO'}.",
        "",
        "## What it shows",
        "",
        *findings,
        "",
        "## 1. Measured: the band against ±5%, by age",
        "",
        md_table(age_table),
        "",
        "By market:",
        "",
        md_table(mkt_table),
        "",
        "## 2. Measured: does the band's width flag the engine's large errors?",
        "",
        md_table(flag_table),
        "",
        md_table(quint_table),
        "",
        "## 3. Upper bound: a pricer who knows the true price moves as far as the band allows",
        "",
        md_table(orc),
        "",
        "## 4. A pricer with the measured behaviours, swept over what they can see",
        "",
        "Mean absolute error against the advert price, all test cars; the pricer's noise the same on every car, spread "
        "as the engine's error:",
        "",
        md_table(sweep),
        "",
        "Cars 12 years and older, the same setting:",
        "",
        md_table(sweep_old),
        "",
        "From which share of the engine's error the pricer must see (rho², on the grid) each band pays, under four "
        "readings of the pricer's noise:",
        "",
        md_table(be),
        "",
        "## Limits",
        "",
        "- **The pricer's information is the unknown.** No source measures how much of the engine's error a used-car "
        "pricer can see; it is swept. Lay people pricing apartments from a listing saw almost none of the model's error "
        "(part 3); a pricer who inspects the car sees condition, damage and options the engine can't.",
        "- **Naive advice weighting is imposed** (one weight on every car). A pricer who weights by their information "
        "would do better under every band, most under the widest.",
        "- **Post-hoc capping.** Under a real cap people move less than it allows (Dietvorst), which shrinks both the "
        "noise and the signal.",
        "- **Advert prices** and today's market: the calibration guarantee does not cover a moved level (X7).",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(f"wrote {OUT.name}; checks pass: {all_ok}")


if __name__ == "__main__":
    main()
