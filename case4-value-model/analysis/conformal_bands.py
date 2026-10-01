"""X15 part 1: conformal bands for the value engine. Does the 80% band hold in every market and age, and can a
calibration guarantee it?

The value engine's 80% band (`value_engine.py`) is built from three measured sources of uncertainty and is right on
average in the UK (`engine_check_report.md`), but a band that is right on average can be wrong in a market or at an
age. Split conformal prediction (Vovk et al. 2005; Romano, Patterson & Candes 2019, conformalized quantile regression)
fixes that with a finite-sample guarantee: score each calibration car by how far its price falls outside the band,
    s = max(log(low / price), log(price / high))     (negative inside the band)
take the ceil((n + 1)(1 - a))-th smallest score q, and widen (q > 0) or narrow (q < 0) every band by q on the log
scale. If calibration and new cars are exchangeable, a new car's price falls inside with probability at least 1 - a.
Done separately per market, or per market and age band (Mondrian conformal), the guarantee holds in each slice.

Design, per market: the engine is fitted on half its recent listings, as `engine_check.py` does; from the other half,
cars whose make and model have at least 30 training cars and all fields present are drawn, split at random into a
calibration set and a test set, and priced. Coverage and width are scored on the test set only: the band as built, and
calibrated per market, per market and age band, and with one calibration (the UK's) for every market.

The limit, stated rather than solved: the guarantee needs exchangeability. Three years out the market level moves, and
no calibration on today's cars covers that (the Latvian test in `engine_check_report.md`, and X7).

Checks: the quantile follows the finite-sample rule on a toy; on simulated exchangeable scores the average coverage
lands between 1 - a and 1 - a + 1/(n + 1); calibration and test cars are disjoint and never in the training half; the
UK's as-built coverage agrees with `engine_check_report.md`'s within sampling error.

Usage: .venv/bin/python analysis/conformal_bands.py   (writes analysis/conformal_bands_report.md, ~10 minutes)
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
from engine_check import AGE_BANDS, held_out, split_half  # noqa: E402

OUT = HERE / "conformal_bands_report.md"
ALPHA = 0.2                 # an 80% band, the engine's own
MARKETS = ("GB", "PL", "SE", "DE", "PT", "NL", "FR", "AT")
MIN_MODEL_CARS = 30         # as engine_check's main test
PER_MARKET = 2_000          # cars priced per market, half to calibrate and half to test
MIN_SLICE = 30              # a market-and-age slice with fewer calibration cars takes the market's q
SEED = 7


def conformal_q(scores, alpha=ALPHA):
    """The ceil((n + 1)(1 - alpha))-th smallest score; infinite when n is too small for the level."""
    s = np.sort(np.asarray(scores, dtype=float))
    k = int(np.ceil((len(s) + 1) * (1 - alpha)))
    return float(s[k - 1]) if k <= len(s) else np.inf


def score(t):
    """How far each price falls outside its band, on the log scale; negative inside."""
    return np.maximum(np.log(t["low"] / t["price"]), np.log(t["price"] / t["high"]))


def covered(t, q):
    return (t["price"] >= t["low"] * np.exp(-q)) & (t["price"] <= t["high"] * np.exp(q))


def width(t, q):
    """The band's width, high over low less 1, after widening by q on each side."""
    return (t["high"] / t["low"]) * np.exp(2 * q) - 1


def price_market(market):
    """Calibration and test cars of one market, priced by an engine fitted on the other half."""
    engine = ve.ValueEngine(market, verbose=False)
    full, train, test = split_half(engine, "conformal-" + market)
    pool = test[test["_n"] >= MIN_MODEL_CARS]
    pool = pool.sample(min(PER_MARKET, len(pool)), random_state=zlib.crc32(market.encode()) % 2 ** 31)
    t = held_out(engine, pool, ve.AGE_NEIGHBOURS)
    t.index = pool.index
    half = np.random.default_rng(zlib.crc32(("split-" + market).encode())).permutation(len(t)) < len(t) // 2
    t["set"] = np.where(half, "calibration", "test")
    t["market"] = market
    t["in_training"] = t.index.isin(train.index)
    return t, len(full)


def slice_q(cal, keys):
    """q per slice; a slice with too few calibration cars falls back to its market's q."""
    market_q = cal.groupby("market").apply(lambda g: conformal_q(score(g)))
    out = {}
    for key, g in cal.groupby(keys):
        m = key[0] if isinstance(key, tuple) else key
        out[key] = conformal_q(score(g)) if len(g) >= MIN_SLICE else market_q[m]
    return out, market_q


def checks(priced, eng_cov_gb):
    rows = []

    def check(name, passes, got):
        rows.append({"check": name, "got": got, "passes": bool(passes)})

    toy = np.arange(1, 11, dtype=float)            # n = 10: k = ceil(11 x 0.8) = 9, the 9th smallest
    check("the conformal quantile follows the finite-sample rule: scores 1..10 at 80% give the 9th smallest",
          conformal_q(toy) == 9.0, f"{conformal_q(toy):.0f}")
    rng = np.random.default_rng(SEED)
    n, trials = 100, 20_000
    cover = np.mean([rng.standard_normal() <= conformal_q(rng.standard_normal(n)) for _ in range(trials)])
    lo, hi = 1 - ALPHA, 1 - ALPHA + 1 / (n + 1)
    se = np.sqrt(lo * (1 - lo) / trials)
    check(f"on exchangeable scores (n = {n}, {trials:,} trials) coverage lands in [{lo:.3f}, {hi:.3f}] within "
          "three standard errors", lo - 3 * se <= cover <= hi + 3 * se, f"{cover:.4f}")
    check("no calibration or test car is in the training half, and the two sets never share a car",
          (~priced["in_training"]).all()
          and not priced.assign(_i=priced.index).duplicated(["market", "_i"]).any(),
          f"{len(priced):,} cars in {priced['market'].nunique()} markets")
    gb = priced[(priced["market"] == "GB")]
    got = covered(gb, 0.0).mean()
    se = np.sqrt(0.8 * 0.2 / len(gb))
    check(f"the UK's as-built coverage agrees with engine_check_report.md's {eng_cov_gb:.0%} within three standard "
          "errors", abs(got - eng_cov_gb) <= 3 * se, f"{got:.1%} on {len(gb):,} cars")
    return pd.DataFrame(rows)


def main():
    frames, sizes = [], {}
    for m in MARKETS:
        t, n = price_market(m)
        frames.append(t)
        sizes[m] = n
        print(f"priced {m}: {len(t):,} cars")
    priced = pd.concat(frames)
    priced["band"] = priced["band"].astype(str)
    cal, test = priced[priced["set"] == "calibration"], priced[priced["set"] == "test"]

    q_age, q_market = slice_q(cal, ["market", "band"])
    q_uk = q_market["GB"]
    test = test.assign(q_market=test["market"].map(q_market),
                       q_age=[q_age.get((m, b), q_market[m]) for m, b in zip(test["market"], test["band"])])

    rows = []
    for m, g in test.groupby("market", sort=False):
        se = np.sqrt(0.8 * 0.2 / len(g))
        rows.append({"market": m, "recent listings": f"{sizes[m]:,}", "test cars": len(g),
                     "as built": f"{covered(g, 0.0).mean():.1%}",
                     "calibrated on the UK": f"{covered(g, q_uk).mean():.1%}",
                     "calibrated per market": f"{covered(g, g['q_market']).mean():.1%}",
                     "calibrated per market and age": f"{covered(g, g['q_age']).mean():.1%}",
                     "one standard error (points)": f"{100 * se:.1f}",
                     "q per market (log points)": f"{100 * q_market[m]:+.1f}",
                     "band width as built": f"{width(g, 0.0).median():.0%}",
                     "band width per market": f"{width(g, g['q_market']).median():.0%}"})
    by_market = pd.DataFrame(rows)

    rows = []
    for (m, b), g in test.groupby(["market", "band"], sort=True):
        if len(g) < 20:
            continue
        rows.append({"market and age": f"{m}, {b.replace(', ', ' to ')} years", "test cars": len(g),
                     "as built": f"{covered(g, 0.0).mean():.0%}",
                     "calibrated per market": f"{covered(g, g['q_market']).mean():.0%}",
                     "calibrated per market and age": f"{covered(g, g['q_age']).mean():.0%}"})
    by_age = pd.DataFrame(rows)

    from scipy.stats import binomtest
    slices = [(k, g) for k, g in test.groupby(["market", "band"]) if len(g) >= 20]
    old = test[test["band"].str.startswith("(12")]

    def row(label, q):
        cov = [(covered(g, g[q] if isinstance(q, str) else q), len(g)) for _, g in slices]
        rates = np.array([c.mean() for c, _ in cov])
        n = np.array([m for _, m in cov])
        below = sum(binomtest(int(c.sum()), m, 1 - ALPHA, alternative="less").pvalue < 0.05 for c, m in cov)
        allq = test[q] if isinstance(q, str) else q
        oldq = old[q] if isinstance(q, str) else q
        return {"band": label, "all test cars": f"{covered(test, allq).mean():.1%}",
                "lowest slice": f"{rates.min():.0%}", "highest slice": f"{rates.max():.0%}",
                "mean distance from 80%, weighted by cars (points)": f"{100 * np.average(np.abs(rates - 0.8), weights=n):.1f}",
                f"slices below 80% at 5% (one-sided), of {len(slices)}": int(below),
                "cars 12 years and older": f"{covered(old, oldq).mean():.1%}"}

    summary = pd.DataFrame([row("as built", 0.0), row("calibrated on the UK only", q_uk),
                            row("calibrated per market", "q_market"), row("calibrated per market and age", "q_age")])

    import re
    line = next(x for x in (HERE / "engine_check_report.md").read_text().splitlines()
                if x.startswith("- **Overall coverage:"))
    eng_cov_gb = float(re.search(r"(\d+)% as built", line).group(1)) / 100
    ck = checks(priced, eng_cov_gb)
    fallback = sum(1 for (m, b), g in cal.groupby(["market", "band"]) if len(g) < MIN_SLICE)

    lines = [
        "# X15 part 1: conformal bands for the value engine",
        "",
        "Generated by `analysis/conformal_bands.py`; the method is in its docstring. Per market, the engine is fitted "
        f"on half its recent listings; up to {PER_MARKET:,} held-out cars whose make and model have at least "
        f"{MIN_MODEL_CARS} training cars are priced, half to calibrate and half to test. Coverage is the share of test "
        "cars whose advertised price falls inside the 80% band; the target is 80%.",
        "",
        "## Summary: coverage across market-and-age slices (test cars)",
        "",
        md_table(summary),
        "",
        "## By market",
        "",
        "q is the calibration's widening on the log scale: positive widens the band, negative narrows it. Width is "
        "high over low less 1, the median across test cars.",
        "",
        md_table(by_market),
        "",
        "## By market and age band (slices with 20 or more test cars)",
        "",
        f"A slice with fewer than {MIN_SLICE} calibration cars takes its market's q ({fallback} slices).",
        "",
        md_table(by_age),
        "",
        "## Checks",
        "",
        md_table(ck),
        "",
        "## Limits",
        "",
        "- **Exchangeability.** The guarantee covers a new car drawn like the calibration cars: today's market. "
        "Three years out the level moves, and in the Latvian test the band missed most adverts "
        "(`engine_check_report.md`, section 4). Calibration fixes the band's shape, not the level (X7).",
        "- **Advertised prices,** like every headline here, not transaction prices.",
        "- **Marginal, not per car.** The guarantee is for the share of cars in a slice, not for any one car; slices "
        "with few calibration cars have a coarse q.",
        "- **Models with at least 30 training cars.** Thin models are left to the engine's borrowing "
        "(`engine_check_report.md`, section 3).",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(summary.to_string(index=False))
    print(by_market.to_string(index=False))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
