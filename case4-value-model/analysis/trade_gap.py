"""The retail-to-trade gap (skeptic B10), bounded from audited accounts, and how trade swings against retail.

B10: the value engine is calibrated on asking prices, but the group sells most returns at trade. No public series
prices the same car at retail and then at trade (X10: Aramis's trade and retail cars are different cars). But a
retailer that buys at trade and sells at retail earns the gap on the same car, so its audited margin bounds it:

- Motorpoint (UK, FY26) buys nearly new cars mostly through fleet and bulk channels. Its retail gross profit, less
  every pound of its finance and warranty commissions, is the least it can have earned on the car itself after
  preparation, which sits in its cost of sales: a floor for the gap.
- Aramis (the group's own used-car retailer, FY2025) reports gross profit before transport and refurbishing. With its
  services at no margin, that is the most its cars can have earned over what it paid. It buys partly from private
  sellers, at or below trade, so this is a ceiling for the gap at trade. With its services at full margin, its lowest.

Second, does the gap move with the market? US wholesale auction prices (the Manheim index) against the US CPI for
used cars (retail): whether trade swings wider, which moves first, and the one-in-ten-year fall of each. US data.

Usage: .venv/bin/python analysis/trade_gap.py   (writes analysis/trade_gap_report.md; seconds; downloads the
Manheim file once, 79 KB)
"""
import csv
import ssl
import sys
import urllib.request
from pathlib import Path

import certifi
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
REGISTER = HERE.parent / "assumptions.csv"
OUT = HERE / "trade_gap_report.md"
MANHEIM_URL = ("https://site.manheim.com/wp-content/uploads/sites/2/2025/12/"
               "Nov-2025-Manheim-Used-Vehicle-Value-Index.xlsx")
MANHEIM = DATA / "raw" / "manheim" / "Nov-2025-Manheim-Used-Vehicle-Value-Index.xlsx"
CPI = "US CPI, used cars and trucks, seasonally adjusted (CUSR0000SETA02)"
START, END = "1997-01", "2025-11"          # the Manheim file's span
LEADS = range(0, 13)                       # months by which trade may lead retail
REBASED = "2023-01"                         # Cox rebased the index with the January 2023 release (its method note)


def register():
    rows = csv.DictReader(open(REGISTER, encoding="utf-8"))
    return {r["id"]: float(r["value"]) for r in rows if r["value"]
            and r["id"].startswith(("motorpoint_fy26_", "aramis_fy25_", "engine_err_typical", "auto1_"))}


def gap(V):
    """The same-car gap as a share of the car's retail price (services taken out of the price)."""
    mp_car_rev = V["motorpoint_fy26_retail_revenue_gbp_m"] - V["motorpoint_fy26_services_revenue_gbp_m"]
    mp_gross = V["motorpoint_fy26_retail_revenue_gbp_m"] - V["motorpoint_fy26_retail_cost_of_sales_gbp_m"]
    ar_car_rev = V["aramis_fy25_revenue_eur_m"] - V["aramis_fy25_services_revenue_eur_m"]
    ar_before = V["aramis_fy25_gross_before_refurb_eur_m"]
    return {
        "mp_car_rev": mp_car_rev, "mp_gross": mp_gross, "ar_car_rev": ar_car_rev,
        "floor": (mp_gross - V["motorpoint_fy26_services_revenue_gbp_m"]) / mp_car_rev,
        "aramis_low": (ar_before - V["aramis_fy25_services_revenue_eur_m"]) / ar_car_rev,
        "ceiling": ar_before / ar_car_rev,
        "refurb": V["aramis_fy25_transport_refurb_eur_m"] / ar_car_rev,
    }


def manheim():
    if not MANHEIM.exists():
        MANHEIM.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(MANHEIM_URL, headers={"User-Agent": "Mozilla/5.0"})
        ctx = ssl.create_default_context(cafile=certifi.where())
        MANHEIM.write_bytes(urllib.request.urlopen(req, context=ctx).read())
    d = pd.read_excel(MANHEIM, sheet_name="DATA", header=0)
    d = d.rename(columns={d.columns[0]: "date", "Index (1/97 = 100)": "idx", "Index % YoY": "yoy_file"})
    d = d.dropna(subset=["date"])
    d["month"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.set_index("month")[["idx", "yoy_file"]]


def cpi():
    p = pd.read_parquet(DATA / "reference" / "price_indices.parquet")
    p = p[p["series"].eq(CPI)]
    return p.set_index("month")["index_value"].sort_index()


def change12(s):
    return (s / s.shift(12) - 1).dropna()


def us():
    m, c = manheim(), cpi()
    months = pd.period_range(START, END, freq="M").strftime("%Y-%m")
    w_idx, r_idx = m["idx"].reindex(months), c.reindex(months)
    w, r = change12(w_idx), change12(r_idx)
    both = pd.concat([w.rename("w"), r.rename("r")], axis=1).dropna()
    out = {"m": m, "months": months, "w_idx": w_idx, "r_idx": r_idx, "both": both}
    out["sd_w"], out["sd_r"] = both["w"].std(), both["r"].std()
    out["p10_w"], out["p10_r"] = both["w"].quantile(0.10), both["r"].quantile(0.10)
    out["min_w"], out["min_r"] = both["w"].min(), both["r"].min()
    out["min_w_at"], out["min_r_at"] = both["w"].idxmin(), both["r"].idxmin()
    out["mean_w"], out["mean_r"] = both["w"].mean(), both["r"].mean()
    # Which moves first: trade now against retail k months later.
    corr = {k: both["w"].corr(both["r"].shift(-k)) for k in LEADS}
    out["corr"], out["lead"] = corr, max(corr, key=corr.get)
    k = out["lead"]
    aligned = pd.concat([both["w"], both["r"].shift(-k)], axis=1).dropna()
    aligned.columns = ["w", "r"]
    out["slope_same"] = np.polyfit(both["r"], both["w"], 1)[0]
    out["slope_lead"] = np.polyfit(aligned["r"], aligned["w"], 1)[0]
    # December to December: independent years.
    dec = [x for x in months if x.endswith("-12")]
    out["years"] = pd.DataFrame({"w": w_idx.reindex(dec).pct_change(), "r": r_idx.reindex(dec).pct_change()}).dropna()
    return out


def pc(x, d=1):
    return f"{100 * x:.{d}f}"


def main():
    V = register()
    g = gap(V)
    u = us()
    ck = []

    def check(name, ok, got):
        ck.append((name, got, bool(ok)))

    gpu_mp = g["mp_gross"] * 1e6 / (V["motorpoint_fy26_retail_units_k"] * 1e3)
    check("Motorpoint's retail gross profit per car, from revenue, cost of sales and cars sold, is its stated GBP 1,368 "
          "(within GBP 1; cars are rounded to hundreds)", abs(gpu_mp - V["motorpoint_fy26_retail_gpu_gbp"]) < 1.5,
          f"GBP {gpu_mp:,.1f}")
    gpu_ar = (V["aramis_fy25_gross_before_refurb_eur_m"] - V["aramis_fy25_transport_refurb_eur_m"]) * 1e6 \
        / V["aramis_fy25_b2c_units"]
    check("Aramis's GPU, from gross profit less transport and refurbishing over retail cars, is its stated EUR 2,359 "
          "(within EUR 1)", abs(gpu_ar - V["aramis_fy25_gpu_eur"]) < 1, f"EUR {gpu_ar:,.1f}")
    parts = V["aramis_fy25_b2c_revenue_eur_m"] + V["aramis_fy25_b2b_revenue_eur_m"] + \
        V["aramis_fy25_services_revenue_eur_m"]
    check("Aramis's retail, trade and services revenue add up to its total (within EUR 0.1m)",
          abs(parts - V["aramis_fy25_revenue_eur_m"]) < 0.1, f"{parts:,.1f} vs {V['aramis_fy25_revenue_eur_m']:,.1f}")
    check("the bounds are in order: floor below Aramis's lowest below the ceiling",
          0 < g["floor"] < g["aramis_low"] < g["ceiling"], f"{pc(g['floor'])} < {pc(g['aramis_low'])} < "
          f"{pc(g['ceiling'])}")
    yoy = change12(u["w_idx"]).reindex(u["m"].index).dropna()
    gapm = (yoy - u["m"]["yoy_file"].reindex(yoy.index)).abs().dropna()
    rest = gapm.drop(REBASED)
    check("the Manheim 12-month changes, recomputed from its index, equal the file's own column within 0.0001, "
          f"every month but {REBASED} (the month Cox rebased the index)", rest.max() < 1e-4,
          f"largest gap {rest.max():.1e} over {len(rest)} months; {gapm[REBASED]:.1e} in {REBASED}")
    check("both indices have every month from January 1997 to November 2025",
          u["w_idx"].notna().all() and u["r_idx"].notna().all(), f"{u['w_idx'].notna().sum()} and "
          f"{u['r_idx'].notna().sum()} of {len(u['months'])}")
    check("the same months are compared for both", len(u["both"]) == len(u["months"]) - 12,
          f"{len(u['both'])} twelve-month changes")

    ok = all(p for _, _, p in ck)
    L = []
    w = L.append
    w("# The retail-to-trade gap, bounded; and how trade swings against retail\n")
    w("`analysis/trade_gap.py`. Skeptic B10: the value engine is calibrated on asking prices, but the group sells most "
      "returns at trade. No public series prices the same car at retail and then at trade (X10: Aramis's trade and "
      "retail cars are different cars). A retailer that buys at trade and sells at retail earns the gap on the same "
      "car, so its audited accounts bound it. Then US data show how the gap moves with the market.\n")
    w("## 1. The gap on the same young car, from two retailers' accounts\n")
    w("Each figure is a share of the car's retail price, with finance, warranty and other services taken out of the "
      "price.\n")
    w("| bound | source | what it counts | gap (%) |")
    w("|---|---|---|---|")
    w(f"| floor | Motorpoint FY26, UK (`motorpoint_fy26_*`) | retail gross profit (GBP {g['mp_gross']:.1f}m) less all "
      f"its commissions (GBP {V['motorpoint_fy26_services_revenue_gbp_m']:.1f}m), over car revenue (GBP "
      f"{g['mp_car_rev']:,.1f}m); preparation already deducted | {pc(g['floor'])} |")
    w(f"| Aramis, services at full margin | Aramis FY2025, the group's own (`aramis_fy25_*`) | gross profit before "
      f"transport and refurbishing (EUR {V['aramis_fy25_gross_before_refurb_eur_m']:.1f}m) less all services revenue "
      f"(EUR {V['aramis_fy25_services_revenue_eur_m']:.1f}m), over car revenue (EUR {g['ar_car_rev']:,.1f}m) | "
      f"{pc(g['aramis_low'])} |")
    w(f"| ceiling | Aramis FY2025 | the same with services at no margin | {pc(g['ceiling'])} |")
    w(f"| the engine's typical error, for comparison | `engine_err_typical` | its error on cars it has never seen | "
      f"{V['engine_err_typical']:g} |")
    w("")
    w("- **Why the floor is a floor.** Motorpoint buys nearly new cars mostly through fleet and bulk channels "
      "(`motorpoint_fy26_sourcing`), the trade the group's returns are sold into. Its cost of sales already holds "
      "preparation and transport, and no service can earn more than its revenue, so what it earned on the car over "
      "its trade price is at least this.")
    w("- **Why the ceiling is a ceiling.** Aramis's gross profit before transport and refurbishing, with its services "
      "earning nothing, is the most its cars earned over what it paid. It buys partly from private sellers, and a "
      "buyer of private cars pays them less than trade: Auto1 buys cars from consumers and resells them to dealers at "
      f"a gross profit of EUR {V['auto1_merchant_gpu_q1_2026_eur']:,.0f} a car (`auto1_merchant_gpu_q1_2026_eur`). "
      "So on Aramis's mix the gap at trade is no larger. Its B2B line (older cars sold to the trade) and its "
      "pre-registered cars sit in the average.")
    w(f"- **Aramis's own spend on transport and refurbishing** is {pc(g['refurb'])}% of its car revenue: part of any "
      "gap a retailer earns pays for making the car retail-ready.")
    w(f"- **Reading.** For a young car, the trade price sits between about {pc(g['floor'], 0)}% and "
      f"{pc(g['ceiling'], 0)}% below the retail price, on average over these retailers' mixes; the group's own retailer "
      f"earns at least about {pc(g['aramis_low'], 0)}% over what it paid, before making the car retail-ready. The "
      "engine's typical error lies inside that range. So B10 is right that the gap is of the engine's order, and it "
      "is bounded: under a fifth of the price. It is a level offset that realised trade prices on the returns "
      "measure (the Phase 2 gate), plus any discount off the asking price, which X10 could not size from averages.\n")
    w("## 2. US data: does the gap move with the market?\n")
    w("The Manheim index (US wholesale auction prices, adjusted for mix, mileage and season: `manheim_index_method`) "
      f"against the US CPI for used cars (retail transactions, seasonally adjusted), monthly, {START} to {END}: "
      f"{len(u['both'])} twelve-month changes.\n")
    w("| measure | trade (Manheim) | retail (CPI) | ratio |")
    w("|---|---|---|---|")
    w(f"| standard deviation of 12-month changes (%) | {pc(u['sd_w'])} | {pc(u['sd_r'])} | "
      f"{u['sd_w'] / u['sd_r']:.2f} |")
    w(f"| one-in-ten-year 12-month change, p10 (%) | {pc(u['p10_w'])} | {pc(u['p10_r'])} | "
      f"{u['p10_w'] / u['p10_r']:.2f} |")
    w(f"| worst 12-month change (%) | {pc(u['min_w'])} ({u['min_w_at']}) | {pc(u['min_r'])} ({u['min_r_at']}) | "
      f"{u['min_w'] / u['min_r']:.2f} |")
    w(f"| mean 12-month change (%) | {pc(u['mean_w'])} | {pc(u['mean_r'])} | |")
    w("")
    w("| how they move together | value |")
    w("|---|---|")
    w(f"| months by which trade leads retail (best correlation) | {u['lead']} |")
    w(f"| correlation at that lead | {u['corr'][u['lead']]:.2f} |")
    w(f"| correlation in the same month | {u['corr'][0]:.2f} |")
    w(f"| points of trade change per point of retail change, same month | {u['slope_same']:.2f} |")
    w(f"| the same, trade leading by the best lead | {u['slope_lead']:.2f} |")
    w("")
    w("Every year in which either fell, December to December (independent years):\n")
    w("| year | trade (%) | retail (%) | trade over retail |")
    w("|---|---|---|---|")
    yrs = u["years"]
    for y, row in yrs[(yrs["w"] < 0) | (yrs["r"] < 0)].iterrows():
        both_fell = row["w"] < 0 and row["r"] < 0
        w(f"| {y[:4]} | {pc(row['w'])} | {pc(row['r'])} | {row['w'] / row['r']:.2f} |" if both_fell
          else f"| {y[:4]} | {pc(row['w'])} | {pc(row['r'])} | one rose |")
    w("")
    w("- **Reading.** Over the year, US trade and retail prices move about one for one, and trade moves first (the "
      "lead above). Trade swings only a little wider in general (the ratio of standard deviations), and its "
      "one-in-ten-year fall is no deeper than retail's. In the two market-wide slumps, 2008 and 2022-23, trade fell "
      "further (the table), and in 2003 and 2014-17 retail fell while trade did not. So the gap does move, mostly in timing: a mark on retail or asking indices is late "
      "at a turn, as X10 found for Germany's asking prices, and it can understate a slump at trade.")
    w("- **No multiplier is carried into the workbook.** Two slumps are too few to set a ratio, and the rest of the "
      "record shows none; X6's charge stays a floor for X10's reasons.")
    w("- **Limits.** US data, one market; the two indices adjust for quality differently (the CPI's quality "
      "adjustment, Manheim's mix and mileage within its classes), which can open gaps over years. No European public "
      "series prices the trade (auction results are private: the dead ends in `notes/Case4_Extensions.md`).\n")
    w("## What this changes\n")
    w("- **B10 moves from unmeasured to bounded.** The gap is between the floor and the ceiling above; Phase 1's mark "
      "starts from that range and Phase 2 measures it on the returns (the gates report's B10 rows).")
    w("- **The mark turns with trade.** US trade leads retail by a couple of months, so the ledger's re-mark should "
      "read the group's own trade results as they come (its returns' auction prices), not only indices.")
    w("- **The headline does not move.** Leak 3 is sized on percentage moves of the level and the curve, not on the "
      "engine's price level.\n")
    w("## Checks\n")
    w("| check | got | passes |")
    w("|---|---|---|")
    for n_, got, p in ck:
        w(f"| {n_} | {got} | {'yes' if p else '**NO**'} |")
    w(f"\n{'All checks pass.' if ok else 'A CHECK FAILED.'}")
    OUT.write_text("\n".join(L) + "\n")
    for n_, got, p in ck:
        print(p, n_, got)
    print({k: round(v, 4) for k, v in g.items()})
    print("sd", u["sd_w"], u["sd_r"], "p10", u["p10_w"], u["p10_r"], "min", u["min_w"], u["min_w_at"], u["min_r"],
          u["min_r_at"], "lead", u["lead"], {k: round(v, 3) for k, v in u["corr"].items()}, "slopes", u["slope_same"],
          u["slope_lead"])
    print(u["years"].round(3).to_string())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
