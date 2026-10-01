"""The upgrade window with the first year measured (skeptic B11: "month 12" broke our own rule).

The Leak 2 sheet finds the month a car's equity first covers the next deposit, on the UK 2018 value curve. UK adverts
carry whole-year ages, so that curve starts at one year: before it, the sheet drew a line from 100% of list, which put
equity equal to the deposit at month 0 by construction, and it searched from month 12. So its "month 12" was where the
search began, not a finding, and it hid how far a market fall delays the window.

This measures the window where the first year can be seen: Dutch adverts (the continental 2025 scrape) carry the date
of first registration, and the RDW's catalogue price gives each model year's list price (the same join as
`value_retained.py`, not the UK's entry-trim price). Value retained by age is estimated within model (a fixed effect
per make and model), so the curve compares like with like rather than whichever models happen to be young; its level is
the sample's average model. The balance, the deposit and the level shocks are the Leak 2 sheet's own. A bootstrap over
models gives the window's range.

Usage: .venv/bin/python analysis/upgrade_window.py   (writes analysis/upgrade_window_report.md; seconds)
"""
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
REGISTER = HERE.parent / "assumptions.csv"
WORKBOOK = HERE.parent.parent / "Case4_Value_at_Risk.xlsx"
OUT = HERE / "upgrade_window_report.md"
EDGES = [0, 3, 6, 9, 12, 18, 24, 36, 48, 60]          # age bins, months: quarters in the first year, then wider
BOOT, SEED = 300, 20260927


def register():
    return {r["id"]: float(r["value"]) for r in csv.DictReader(open(REGISTER, encoding="utf-8")) if r["value"]}


def sample():
    """Dutch used-car adverts joined to the RDW catalogue price of their make, model and year (value_retained.py's
    join and filters), aged up to five years."""
    d = pd.read_parquet(DATA / "unified" / "listings.parquet",
                        columns=["source", "country", "price_type", "is_new", "make", "model", "year", "age_years",
                                 "price_eur"])
    d = d[d["price_type"].eq("asking") & ~d["is_new"].fillna(False).astype(bool) & d["country"].eq("NL")]
    rdw = pd.read_parquet(DATA / "reference" / "rdw_new_prices.parquet")
    d = d.merge(rdw[["make", "model", "year", "new_price_eur", "n"]].rename(columns={"new_price_eur": "rdw"}),
                on=["make", "model", "year"], how="inner")
    d = d[d["n"].ge(3)].copy()
    d["retained"] = d["price_eur"] / d["rdw"]
    d["months"] = d["age_years"].astype(float) * 12
    d = d[d["retained"].between(0.02, 1.5) & d["months"].gt(0) & d["months"].le(EDGES[-1])].copy()
    d["bin"] = np.digitize(d["months"], EDGES[1:-1])
    d["mm"] = d["make"] + " | " + d["model"]
    return d.reset_index(drop=True)


def fe_curve(d):
    """Retained share by age bin, within model: log retained on bin and make-model effects; the level is the
    sample's average model. Returns the curve (share of list) at each bin."""
    y = np.log(d["retained"].to_numpy())
    mm = pd.factorize(d["mm"])[0]
    nb = len(EDGES) - 1
    bins = d["bin"].to_numpy()
    # Two-way fixed effects by alternating means (exact at convergence for this unbalanced design).
    a, b = np.zeros(mm.max() + 1), np.zeros(nb)
    for _ in range(500):
        b_new = np.bincount(bins, y - a[mm], minlength=nb) / np.maximum(np.bincount(bins, minlength=nb), 1)
        a_new = np.bincount(mm, y - b_new[bins]) / np.bincount(mm)
        done = np.max(np.abs(b_new - b)) < 1e-12 and np.max(np.abs(a_new - a)) < 1e-12
        a, b = a_new, b_new
        if done:
            break
    level = np.average(a, weights=np.bincount(mm))
    return np.exp(level + b)


def value_path(curve, months):
    """Share of list at each month: 100 at 0 (new), then straight lines between bin midpoints, flat beyond the last."""
    mids = [(lo + hi) / 2 for lo, hi in zip(EDGES[:-1], EDGES[1:])]
    return np.interp(months, [0] + mids, [100] + list(100 * curve))


def balance(V, m):
    """The Leak 2 sheet's balance: an annuity on the amount financed, zero after the term."""
    n, i = V["loan_term_months"], V["loan_apr"] / 1200
    return np.where(m >= n, 0.0, (100 - V["loan_deposit_pct"]) * ((1 + i) ** n - (1 + i) ** m) / ((1 + i) ** n - 1))


def window(V, curve, shock_pct):
    """First month from 1 at which equity, with the level moved by `shock_pct`, covers the next deposit."""
    m = np.arange(1, int(V["loan_term_months"]) + 13)
    eq = value_path(curve, m) * (1 + shock_pct / 100) - balance(V, m)
    hit = np.nonzero(eq >= V["loan_deposit_pct"])[0]
    return int(m[hit[0]]) if len(hit) else None


def main():
    V = register()
    d = sample()
    curve = fe_curve(d)
    shocks = {"level as measured": 0.0, f"level {V['level_3y_p10_core']:g}% (p10)": V["level_3y_p10_core"],
              f"level {V['level_3y_worst']:g}% (worst)": V["level_3y_worst"]}
    win = {k: window(V, curve, s) for k, s in shocks.items()}

    rng = np.random.default_rng(SEED)
    models = d["mm"].unique()
    groups = {k: g.index.to_numpy() for k, g in d.groupby("mm")}
    boot = {k: [] for k in shocks}
    boot_curve = []
    for _ in range(BOOT):
        pick = rng.choice(models, size=len(models), replace=True)
        idx = np.concatenate([groups[p] for p in pick])
        bd = d.loc[idx].copy()
        bd["mm"] = np.repeat(np.arange(len(pick)), [len(groups[p]) for p in pick]).astype(str)
        if bd["bin"].nunique() < len(EDGES) - 1:
            continue
        c = fe_curve(bd)
        boot_curve.append(c)
        for k, s in shocks.items():
            boot[k].append(window(V, c, s))
    boot_curve = np.array(boot_curve)

    def rng80(xs):
        xs = np.array([x if x is not None else np.nan for x in xs], dtype=float)
        return np.nanpercentile(xs, 10), np.nanpercentile(xs, 90), np.isnan(xs).mean()

    ck = []

    def check(name, ok, got):
        ck.append((name, got, bool(ok)))

    ws = load_workbook(WORKBOOK, data_only=True)["Leak 2 - Upgrade timing"]
    head = next(r[0].row for r in ws.iter_rows() if r[0].value == "month")
    wb_bal = {m: ws.cell(row=head + 1 + m, column=2).value for m in (12, 24, 47)}
    gap = max(abs(wb_bal[m] - float(balance(V, np.array(m)))) for m in wb_bal)
    check("the balance equals the Leak 2 sheet's", gap < 1e-9, f"largest gap {gap:.1e}")
    raw = d.groupby("bin")["retained"].median().to_numpy()
    # The estimator, on a simulated market with known age effects, model effects and young cars skewed to dear models.
    sim_rng = np.random.default_rng(SEED)
    true_b = np.log(np.linspace(0.9, 0.55, len(EDGES) - 1))
    sim = d[["mm", "bin"]].copy()
    fx = pd.Series(sim_rng.normal(0, 0.3, sim["mm"].nunique()), index=sim["mm"].unique())
    fx = fx + 0.2 * (d.groupby("mm")["bin"].mean().rsub(len(EDGES) - 1) / (len(EDGES) - 1))  # young mix is dearer
    fx = fx - np.average(fx[d["mm"]].to_numpy())
    sim["retained"] = np.exp(true_b[sim["bin"]] + fx[sim["mm"]].to_numpy() + sim_rng.normal(0, 0.05, len(sim)))
    err = np.max(np.abs(fe_curve(sim) - np.exp(true_b)))
    check("the within-model estimator recovers a known curve despite a skewed model mix", err < 0.01, f"{err:.4f}")
    at36 = float(value_path(curve, np.array([36.0]))[0])
    check("at three years the curve agrees with the register's Dutch figure (retained_3y_nl), within 3 points",
          abs(at36 - V["retained_3y_nl"]) < 3, f"{at36:.1f} vs {V['retained_3y_nl']:g}")
    check("the curve falls from the first bin to the last", curve[-1] < curve[0], f"{curve[0]:.3f} > {curve[-1]:.3f}")
    check("a deeper fall never opens the window sooner",
          all((win[a] or 999) <= (win[b] or 999) for a, b in zip(list(shocks), list(shocks)[1:])),
          " <= ".join(str(win[k]) for k in shocks))
    check("every bootstrap draw had every age bin", len(boot_curve) == BOOT, f"{len(boot_curve)} of {BOOT}")

    ok = all(p for _, _, p in ck)
    L = []
    w = L.append
    w("# The upgrade window, with the first year measured\n")
    w("`analysis/upgrade_window.py`. Skeptic B11: the Leak 2 sheet's \"month 12\" was where its search began, because "
      "the UK curve has whole-year ages and so no first year. Here the first year is measured on Dutch adverts with "
      "exact ages (the continental 2025 scrape) against the RDW catalogue price of each make, model and year, within "
      "model. The contract (deposit, term, rate) and the level shocks are the Leak 2 sheet's own.\n")
    w(f"{len(d):,} adverts, {d['mm'].nunique():,} makes and models, up to five years old. Bootstrap: {BOOT} draws of "
      "whole models, so the range carries the uncertainty of which models are in the sample.\n")
    w("## Value retained by age, share of list\n")
    w("| age (months) | adverts | within model | raw median | 80% range (bootstrap) |")
    w("|---|---|---|---|---|")
    n_bin = d.groupby("bin").size()
    for j, (lo, hi) in enumerate(zip(EDGES[:-1], EDGES[1:])):
        p10, p90 = np.percentile(boot_curve[:, j], [10, 90])
        w(f"| {lo}-{hi} | {n_bin.get(j, 0):,} | {100 * curve[j]:.1f} | {100 * raw[j]:.1f} | {100 * p10:.1f}-"
          f"{100 * p90:.1f} |")
    w("")
    w("A car loses most of its first year's value in its first months, and the within-model curve holds the model mix "
      "fixed: the raw medians of the youngest bins swing with whichever models are young (a few premium models "
      "dominate the first quarter).\n")
    w("## The window: when equity first covers the next deposit\n")
    w(f"The sample contract: a {V['loan_deposit_pct']:g}% deposit, {V['loan_term_months']:.0f} months at "
      f"{V['loan_apr']:g}% (`loan_*`). Searched from month 1; a level shock moves every month's value.\n")
    w("| market level | month | 80% range (bootstrap) | draws where it never opens in the term |")
    w("|---|---|---|---|")
    for k in shocks:
        lo, hi, never = rng80(boot[k])
        w(f"| {k} | {win[k] if win[k] is not None else 'not within the term'} | {lo:.0f}-{hi:.0f} | "
          f"{100 * never:.0f}% |")
    w("")
    w("## What this does and doesn't change\n")
    w("- **The Leak 2 sheet keeps the UK curve** (the sample car is British, and X19's trade-off and the Per car sheet "
      "read it), but its window row is a bound: with no sub-year ages it can only say the window is open by month 12.")
    w("- **The months quoted are these.** They are measured, and the first year is no longer a line drawn from list.")
    w("- **Leak 2's euros do not move:** they are contracts times an assumed uplift times an assumed margin, not the "
      "window.")
    w("- **Limits:** Dutch asking prices in one scrape (2025), not transactions; the RDW catalogue price is a model "
      "year's list price, so options and trims above it lift the youngest cars (some sit above 100%); the curve's "
      "level is the sample's average model.\n")
    w("## Checks\n")
    w("| check | got | passes |")
    w("|---|---|---|")
    for n_, g, p in ck:
        w(f"| {n_} | {g} | {'yes' if p else '**NO**'} |")
    w(f"\n{'All checks pass.' if ok else 'A CHECK FAILED.'}")
    OUT.write_text("\n".join(L) + "\n")
    for n_, g, p in ck:
        print(p, n_, g)
    print("curve", np.round(100 * curve, 1), "raw", np.round(100 * raw, 1))
    print("windows", win, {k: rng80(v) for k, v in boot.items()})
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
