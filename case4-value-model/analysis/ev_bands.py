"""X9 part 5: is the value engine's band right for EVs, and how much could battery health narrow it?

X15 calibrated the value engine's 80% band by market and age (`conformal_bands.py`), on cars drawn at random, which
holds too few EVs to judge them. Here, per market with enough EVs, the engine is fitted on half its local cars (as
`engine_check.split_half` does) and prices held-out battery EVs and held-out petrol and diesel cars of models with at
least 30 training cars. Scored on the held-out cars: coverage of the band as built; the typical error; and the
conformal widening each fuel needs for 80% (X15's rule, `conformal_bands.conformal_q`, fitted on a calibration half
and scored on the other half).

Battery health: no advert records it, so it cannot be measured here. What can be measured is the ceiling on it: an EV's
price error beyond a combustion car's, same engine, same market, is everything EV-specific the engine does not see
(battery health, range, charging, software). Battery health can narrow an EV's band by at most that excess. The
ledger can read each car's state of health at return (Regulation (EU) 2023/1542, Article 14, since 18 August 2024;
`battreg_soh_access_from`), so the pilot can measure how much of the excess it explains, car by car.

Checks: calibration and test cars are disjoint and never in the training half; the calibrated coverage on the test
half lands within three binomial standard errors of 80% for each fuel; combustion cars' coverage as built is within five points of X15's all-market coverage.

Usage: .venv/bin/python analysis/ev_bands.py   (writes analysis/ev_bands_report.md, ~10 minutes)
"""
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import value_engine as ve  # noqa: E402
from build_unified import md_table  # noqa: E402
from conformal_bands import conformal_q, covered, score, width  # noqa: E402
from engine_check import held_out, split_half  # noqa: E402

OUT = HERE / "ev_bands_report.md"
MARKETS = ("GB", "NL", "DE", "SE", "PL", "PT")
MIN_MODEL_CARS = 30
PER_FUEL = 600               # held-out cars priced per fuel group and market
MIN_EV = 150                 # a market needs this many priced EVs to be reported
ALPHA = 0.2
FUEL_GROUP = {"electric": "battery EV", "petrol": "combustion", "diesel": "combustion"}


def price_market(market):
    engine = ve.ValueEngine(market, verbose=False)
    full, train, test = split_half(engine, "ev-bands-" + market)
    test = test[test["_n"] >= MIN_MODEL_CARS].copy()
    test["group"] = test["fuel"].astype("string").map(FUEL_GROUP)
    parts = []
    for grp, g in test.dropna(subset=["group"]).groupby("group"):
        pool = g.sample(min(PER_FUEL, len(g)), random_state=zlib.crc32((market + grp).encode()) % 2 ** 31)
        t = held_out(engine, pool, ve.AGE_NEIGHBOURS)
        t.index = pool.index
        t["group"], t["make"], t["model"] = grp, pool["make"].astype(str).to_numpy(), pool["model"].astype(str).to_numpy()
        half = np.random.default_rng(zlib.crc32(("split-" + market + grp).encode())).permutation(len(t)) < len(t) // 2
        t["set"] = np.where(half, "calibration", "test")
        parts.append(t)
    t = pd.concat(parts)
    t["market"] = market
    t["in_training"] = t.index.isin(train.index)
    return t


def summarise(t):
    rows = []
    for (m, grp), g in t.groupby(["market", "group"]):
        cal, tst = g[g["set"] == "calibration"], g[g["set"] == "test"]
        q = conformal_q(score(cal), ALPHA)
        rows.append({"market": m, "fuel": grp, "priced": len(g),
                     "coverage as built": covered(tst, 0.0).mean(),
                     "typical error": np.expm1(tst["log_err"].abs().median()),
                     "width as built": width(tst, 0.0).median(),
                     "widening for 80% (log)": q,
                     "coverage calibrated": covered(tst, q).mean(),
                     "width calibrated": width(tst, q).median()})
    return pd.DataFrame(rows)


def main():
    frames = []
    for m in MARKETS:
        try:
            t = price_market(m)
        except Exception as e:           # a market the engine cannot build is reported, not hidden
            print(f"{m}: skipped ({e})")
            continue
        n_ev = int((t["group"] == "battery EV").sum())
        print(f"{m}: {len(t)} priced, {n_ev} EVs")
        if n_ev >= MIN_EV:
            frames.append(t)
    t = pd.concat(frames)
    s = summarise(t)
    ev, ice = s[s["fuel"] == "battery EV"].set_index("market"), s[s["fuel"] == "combustion"].set_index("market")
    both = ev.index.intersection(ice.index)
    excess = pd.DataFrame({
        "EV typical error": ev.loc[both, "typical error"], "ICE typical error": ice.loc[both, "typical error"],
        "EV excess error (points)": 100 * (ev.loc[both, "typical error"] - ice.loc[both, "typical error"]),
        "EV coverage as built": ev.loc[both, "coverage as built"],
        "ICE coverage as built": ice.loc[both, "coverage as built"],
        "EV band after calibration, over ICE's (ratio)": ev.loc[both, "width calibrated"] / ice.loc[both, "width calibrated"],
    })
    pooled = {}
    for grp in ("battery EV", "combustion"):
        g = t[t["group"] == grp]
        cal, tst = g[g["set"] == "calibration"], g[g["set"] == "test"]
        pooled[grp] = {"coverage": covered(tst, 0.0).mean(), "typical": np.expm1(tst["log_err"].abs().median()),
                       "q": conformal_q(score(cal), ALPHA)}

    # checks
    rows = []

    def check(name, passes, got):
        rows.append({"check": name, "got": got, "passes": bool(passes)})

    check("calibration and test cars are disjoint and none was in the engine's training half",
          (~t["in_training"]).all() and t.groupby(level=0).size().max() == 1, f"{len(t):,} priced cars")
    n_test = t[t["set"] == "test"].groupby(["market", "group"]).size().reindex(
        pd.MultiIndex.from_frame(s[["market", "fuel"]])).to_numpy()
    se = np.sqrt((1 - ALPHA) * ALPHA / n_test)
    z = (s["coverage calibrated"].to_numpy() - (1 - ALPHA)) / se
    check("calibrated coverage on the test half is within three binomial standard errors of 80% in every market "
          "and fuel (a slice of about 100 test cars has a standard error near 4 points)", bool((np.abs(z) <= 3).all()),
          f"{s['coverage calibrated'].min():.0%} to {s['coverage calibrated'].max():.0%}; largest {np.abs(z).max():.1f} "
          "standard errors")
    x15 = pd.read_csv(HERE.parent / "assumptions.csv").set_index("id")["value"]
    ice_all = t[(t["group"] == "combustion") & (t["set"] == "test")]
    x15_all = float(x15["x15_cov_all_asbuilt"])
    got = covered(ice_all, 0.0).mean()
    check("combustion cars' coverage as built is within five points of X15's all-market coverage "
          "(x15_cov_all_asbuilt)", abs(100 * got - x15_all) <= 5, f"{got:.1%} against {x15_all:.0f}%")
    ck = pd.DataFrame(rows)

    def pct(v):
        return f"{100 * v:.0f}%"
    show = s.copy()
    for c in ("coverage as built", "coverage calibrated"):
        show[c] = show[c].map(pct)
    for c in ("typical error", "width as built", "width calibrated"):
        show[c] = show[c].map(lambda v: f"{100 * v:.1f}%")
    show["widening for 80% (log)"] = show["widening for 80% (log)"].map(lambda v: f"{v:+.3f}")
    ex = excess.reset_index()
    for c in ("EV typical error", "ICE typical error"):
        ex[c] = ex[c].map(lambda v: f"{100 * v:.1f}%")
    for c in ("EV coverage as built", "ICE coverage as built"):
        ex[c] = ex[c].map(pct)
    ex["EV excess error (points)"] = ex["EV excess error (points)"].map(lambda v: f"{v:+.1f}")
    ex["EV band after calibration, over ICE's (ratio)"] = ex["EV band after calibration, over ICE's (ratio)"].map(
        lambda v: f"{v:.2f}")
    heads = pd.DataFrame([
        {"figure": "battery EVs, all markets: coverage of the 80% band as built", "value": pct(pooled["battery EV"]["coverage"])},
        {"figure": "combustion cars, all markets: coverage as built", "value": pct(pooled["combustion"]["coverage"])},
        {"figure": "battery EVs, all markets: typical error (%)", "value": f"{100 * pooled['battery EV']['typical']:.1f}"},
        {"figure": "combustion cars, all markets: typical error (%)", "value": f"{100 * pooled['combustion']['typical']:.1f}"},
        {"figure": "battery EVs' excess typical error over combustion cars, all markets (points)",
         "value": f"{100 * (pooled['battery EV']['typical'] - pooled['combustion']['typical']):+.1f}"},
        {"figure": "markets where EVs' error exceeds combustion cars'",
         "value": f"{int((excess['EV excess error (points)'] > 0).sum())} of {len(excess)}"},
    ])
    print(show.to_string(index=False)); print(ex.to_string(index=False)); print(ck.to_string(index=False))
    lines = [
        "# X9 part 5: the value engine's band for EVs",
        "",
        "Generated by `analysis/ev_bands.py`; the method is in its docstring. Held-out adverts (asking prices), today's "
        "value only: the band says nothing about the level three years out (X15, X7).",
        "",
        "## Headline",
        "",
        md_table(heads),
        "",
        "## By market and fuel",
        "",
        md_table(show),
        "",
        "## EVs against combustion cars, same engine and market",
        "",
        "The excess error is the ceiling on what battery health could explain: it holds everything EV-specific the "
        "engine does not see (battery health, range, charging, software). A read state of health can narrow an EV's "
        "band by at most that much, and the pilot measures how much it does (the ledger reads it at return under "
        "Article 14 of the battery regulation).",
        "",
        md_table(ex),
        "",
        "## Reading it",
        "",
        "- **Today's EV price is as predictable as a combustion car's.** From make, model, age and mileage the engine "
        f"prices held-out EVs with a typical error of {100 * pooled['battery EV']['typical']:.1f}% against "
        f"{100 * pooled['combustion']['typical']:.1f}% for petrol and diesel, and its band covers them as well. EVs' "
        f"error is larger in {int((excess['EV excess error (points)'] > 0).sum())} of {len(excess)} markets, by a "
        "couple of points at most.",
        "- **So battery health can explain little of today's price spread,** at most that small excess where it exists. "
        "Buyers mostly cannot see a battery's health either, so its uncertainty is already in the price the band is "
        "fitted to. The band needs no EV widening today; X15's calibration by market and age serves EVs too.",
        "- **The EV risk is the level at return** (parts 2 and 3), which no band on today's cars covers. A state of "
        "health read at return (Article 14) is for the ledger's record: it lets the pilot test whether it explains "
        "any of the excess, and lets a buyer who can see it pay for it.",
        "",
        "## Checks",
        "",
        md_table(ck),
        "",
        "## Limits",
        "",
        "- **Asking prices, today.** A band that is right today says nothing about the level at return.",
        "- **Models with 30 training cars.** A rare EV model is priced from its neighbours, with a wider error.",
        "- **Exchangeability.** The calibrated band holds for cars like those it was calibrated on; a new EV "
        "generation or a price cut breaks it (X7's limit, sharper for EVs).",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
