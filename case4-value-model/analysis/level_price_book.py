"""X19 part 2: what the market level costs each book, by where the level sits when the contract starts.

X18 found the group's buy-back book counts both ways: its contracts bring the cars back (a repurchase obligation, or a
customer's put expected to be exercised), with gains and losses at disposal (`stellantis_buyback_forms`). X6's charge
is one-sided, the right price where a customer holds an option struck at the residual (bank leases). X6 part 5 also
found that 36- and 48-month contracts started with the level below its three-year average lost several times more
(`x6_charge_cold_*`). Before an internal price for the buy-back book is written, this script asks whether that
premium survives at the buy-back book's horizon (12 months) and with both sides counted.

1. **The state at the start:** the level's log gap above its average over the previous 36 months (X6's
   `signal_windows`), in terciles pooled across the panel: cold (bottom third), middle, hot.
2. **The cost of a 12-month contract,** per euro of residual, residual set at the panel's median 12-month move (X6's
   strike): one-sided, `E[max(0, assumed - realised)] / (1 + assumed)` (X6's put); two-sided, the same without the
   floor, so gains in a rising level count against losses. Two-sided at no change is shown beside it.
3. **Panels:** every Eurostat market with its full series (X6 part 5's panel; France from 1996); the core markets
   only; the UK's ONS series from 1988 (the longest, several cycles); the group's own book (markets weighted as it
   sells, `merger_diversification.py`'s base variant), short: its gap needs three years of history first.

Checks: X6's 36-month cold and middle charges reproduce (`x6_charge_cold_36m`, `x6_charge_middle_36m`) through this
script's own code path; toy cases for the state and the two-sided identity; every tercile has windows.

Usage: .venv/bin/python analysis/level_price_book.py   (writes analysis/level_price_book_report.md; seconds)
"""
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import merger_diversification as md  # noqa: E402
from build_unified import md_table  # noqa: E402
from level_charge import shortfall, signal_windows  # noqa: E402
from level_risk import CORE, EUROPE, EUROSTAT, load  # noqa: E402

OUT = HERE / "level_price_book_report.md"
REGISTER = HERE.parent / "assumptions.csv"
K = 12
STATES = ("cold", "middle", "hot")


def register():
    rows = {r["id"]: r for r in csv.DictReader(open(REGISTER, encoding="utf-8"))}
    return {k: float(rows[k]["value"]) for k in ("x6_charge_cold_36m", "x6_charge_middle_36m")}


def by_state(frame, cuts=None):
    """Terciles of the gap (cut on this frame unless cuts are given) and the cost per euro of residual in each."""
    assumed = float(np.median(frame["move"]))
    f = frame.assign(one=shortfall(frame["move"], assumed),
                     two=(assumed - frame["move"]) / (1 + assumed),
                     two_nc=-frame["move"])
    if cuts is None:
        cuts = np.quantile(f["gap"], [1 / 3, 2 / 3])
    edges = {"cold": (-np.inf, cuts[0]), "middle": (cuts[0], cuts[1]), "hot": (cuts[1], np.inf)}
    out = {}
    for name, (lo, hi) in edges.items():
        part = f[(f["gap"] > lo) & (f["gap"] <= hi)]
        out[name] = {"windows": len(part), "one": part["one"].mean(), "two": part["two"].mean(),
                     "two_nc": part["two_nc"].mean(), "loss_share": (part["move"] < assumed).mean(),
                     "gap": (lo, hi)}
    out["all"] = {"windows": len(f), "one": f["one"].mean(), "two": f["two"].mean(), "two_nc": f["two_nc"].mean(),
                  "loss_share": (f["move"] < assumed).mean(), "gap": (-np.inf, np.inf)}
    return out, assumed


def gap_label(lo, hi):
    if np.isinf(lo) and np.isinf(hi):
        return "all"
    if np.isinf(lo):
        return f"up to {100 * np.expm1(hi):+.1f}"
    if np.isinf(hi):
        return f"above {100 * np.expm1(lo):+.1f}"
    return f"{100 * np.expm1(lo):+.1f} to {100 * np.expm1(hi):+.1f}"


def book_frame():
    """The group's book: each market's gap and 12-month move, weighted as the book sells (the base variant)."""
    d = md.clean(md.registrations())
    series, n, m = md.run_variant(d, md.VARIANTS[md.BASE_VARIANT])
    w = m["weights"].loc[m["markets"], "merged"]
    frames = {g: signal_windows(series[g], K).set_index("start") for g in m["markets"]}
    gap = sum(frames[g]["gap"] * w[g] for g in m["markets"])
    move = sum(frames[g]["move"] * w[g] for g in m["markets"])
    return pd.DataFrame({"gap": gap, "move": move}).dropna().reset_index()


def main():
    reg = register()
    raw = load()
    full = {g: s for (series, g), s in raw.items() if series == EUROSTAT and g in EUROPE}
    uk = raw[(md.ONS_SERIES, "UK")].dropna()

    def pooled(k, geos):
        frames = [signal_windows(full[g], k) for g in geos]
        return pd.concat([f for f in frames if len(f) >= 24])

    panels = {
        "every Eurostat market, full series": pooled(K, sorted(full)),
        "the core markets": pooled(K, [g for g in CORE if g in full]),
        "the UK, ONS 1988-2026": signal_windows(uk, K),
        "the group's book (short)": book_frame(),
    }
    results = {name: by_state(f) for name, f in panels.items()}

    # ---- checks ----
    ck = []

    def check(name, want, got, tol):
        ck.append({"check": name, "expected": want, "got": round(float(got), 4), "passes": abs(want - got) <= tol})

    x6, _ = by_state(pooled(36, sorted(full)))
    check("X6's 36-month cold charge reproduces (`x6_charge_cold_36m`)", reg["x6_charge_cold_36m"],
          round(100 * x6["cold"]["one"], 2), 5e-3)
    check("X6's 36-month middle charge reproduces (`x6_charge_middle_36m`)", reg["x6_charge_middle_36m"],
          round(100 * x6["middle"]["one"], 2), 5e-3)
    toy = pd.Series(np.exp([0.0, 0.0, 0.0, 0.3, 0.3]), index=pd.period_range("2020-01", periods=5, freq="M"))
    tw = signal_windows(toy, 1, lookback=3)
    check("toy: after three flat months the level jumps 0.3 in logs, so the gap is 0.3", 0.3,
          float(tw["gap"].iloc[0]), 1e-12)
    a = pd.Series([-0.1, 0.0, 0.05, 0.2])
    check("toy: two-sided minus one-sided equals minus the gain side, E[max(0, m-a)] - E[a-m] = E[max(0, a-m)]",
          float(np.maximum(0, a - 0.0).mean()), float(shortfall(a, 0.0).mean() - (0.0 - a).mean()), 1e-12)
    check("every tercile of every panel has windows (1 = yes)", 1.0,
          float(all(r[0][s]["windows"] > 0 for r in results.values() for s in STATES)), 0)
    ck = pd.DataFrame(ck)
    all_ok = bool(ck["passes"].all())

    # ---- tables ----
    rows = []
    for name, (res, assumed) in results.items():
        for s in (*STATES, "all"):
            r = res[s]
            rows.append({"panel and state": f"{name}, {s}", "gap above its 36-month average (%)": gap_label(*r["gap"]),
                         "windows": r["windows"],
                         "one-sided (% of residual)": round(100 * r["one"], 2),
                         "two-sided (% of residual)": round(100 * r["two"], 2),
                         "two-sided at no change (%)": round(100 * r["two_nc"], 2),
                         "share of windows with a loss (%)": round(100 * r["loss_share"], 1)})
    table = pd.DataFrame(rows)
    strike = pd.DataFrame([{"panel": name, "median 12-month move, the strike (%)": round(100 * assumed, 2),
                            "windows": res["all"]["windows"]} for name, (res, assumed) in results.items()])
    premium = pd.DataFrame([{"panel": name,
                             "cold minus all, two-sided (points of residual)": round(100 * (res["cold"]["two"] - res["all"]["two"]), 2),
                             "cold minus hot, two-sided (points)": round(100 * (res["cold"]["two"] - res["hot"]["two"]), 2),
                             "cold minus all, one-sided (points)": round(100 * (res["cold"]["one"] - res["all"]["one"]), 2)}
                            for name, (res, _) in results.items()])

    ev, uk_r, bk = results["every Eurostat market, full series"][0], results["the UK, ONS 1988-2026"][0], \
        results["the group's book (short)"][0]
    co = results["the core markets"][0]
    findings = [
        f"- **Unconditionally, both sides counted, a 12-month contract costs nothing on average:** "
        f"{100 * ev['all']['two']:.2f}% of the residual across every Eurostat market, {100 * co['all']['two']:.2f}% in "
        f"the core markets, {100 * uk_r['all']['two']:.2f}% on the UK's long record (negative is a gain), against a "
        f"one-sided {100 * ev['all']['one']:.2f}%, {100 * co['all']['one']:.2f}% and {100 * uk_r['all']['one']:.2f}%. "
        "X18's finding, now per contract.",
        f"- **The cold state costs more, both sides counted, in every long panel:** cold minus all is "
        f"{100 * (co['cold']['two'] - co['all']['two']):.2f} points of residual in the core markets, "
        f"{100 * (uk_r['cold']['two'] - uk_r['all']['two']):.2f} on the UK's long record and "
        f"{100 * (ev['cold']['two'] - ev['all']['two']):.2f} across every Eurostat market. But a cold contract is a "
        f"loss on average only in the broadest panel ({100 * ev['cold']['two']:.2f}%); in the core markets "
        f"({100 * co['cold']['two']:.2f}%) and the UK ({100 * uk_r['cold']['two']:.2f}%) it is about break-even. So X6's "
        "rule survives two-sided as a relative premium: price a buy-back contract higher when the level starts cold.",
        f"- **The group's own book is too short to say:** {bk['all']['windows']} overlapping windows after the three-year "
        f"look-back, cold {100 * bk['cold']['two']:.2f}%, middle {100 * bk['middle']['two']:.2f}%, hot "
        f"{100 * bk['hot']['two']:.2f}% two-sided. Read the longer panels.",
    ]
    lines = [
        "# X19 part 2: what the market level costs each book, by the level's state at the start",
        "",
        "_Generated by `analysis/level_price_book.py`. Eurostat HICP second-hand car indices (CP07112), each market's "
        "full series as in X6 part 5; the ONS UK series from 1988; the group's book as in `merger_diversification.py`'s "
        "base variant. 12-month contracts, the buy-back book's horizon. Per euro of residual. Real data, nothing "
        "synthetic._",
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
        "## The cost of a 12-month contract by the level's state at the start",
        "",
        "One-sided: only losses count (X6's put, a customer holding an option at the residual). Two-sided: gains count "
        "too (the buy-back book, X18). Residual set at the panel's median 12-month move.",
        "",
        md_table(table),
        "",
        "### The cold state's premium",
        "",
        md_table(premium),
        "",
        "### The strike in each panel",
        "",
        md_table(strike),
        "",
        "## Limits",
        "",
        "- **Overlapping windows:** 12-month windows start every month, so neighbouring windows share most of their "
        "move; the effective sample is far smaller than the count (X6 part 1's table).",
        "- **Terciles are cut within each panel,** so 'cold' is relative to that panel's own history.",
        "- **The book's panel starts in 2019-12** (three years of look-back first) and holds one boom.",
        "- **Index prices, retail,** understate what a lessor meets (X7), so these are floors.",
        "- **The state is known at the start,** so a state-dependent price is usable; whether a price that moves with "
        "the state errs less out of sample was tested by X6 part 5 at 36 and 48 months, not here.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(table.to_string(index=False))
    print(f"wrote {OUT.name}; checks pass: {all_ok}")


if __name__ == "__main__":
    main()
