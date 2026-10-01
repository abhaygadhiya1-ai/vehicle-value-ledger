"""X17 parts 3-4: the levers that recover value from a returned car, beyond time in stock.

Skeptic F3: leak 3 answers "maximize value recovery" with risk pricing. Part 2 (`time_in_stock.py`) priced a day in
stock; this script sizes the other levers that public evidence reaches, each on the group's own disclosed book or its
own subsidiary, and each as a rate the workbook can apply.

1. **The channel.** Selling a returned car through the group's own retail arm rather than to the trade. Aramis Group,
   60.54% owned, publishes its margin per retail car before and after transport and refurbishing, and its adjusted
   EBITDA. Per car: the margin after all costs (EBITDA per car, the low end) and before operating costs (gross profit
   per car, the high end), as shares of its average retail price. Retail takes longer than a trade sale, so the lever
   is stated with its break-even: how many extra days in stock would eat the margin, at part 2's daily cost.
2. **Condition reports, as speed.** Tadelis & Zettelmeyer's randomised US auction experiment: publishing a condition
   report raised the share sold at a weekly auction, with little effect on prices. With a constant weekly chance of
   sale and a re-run each week until sold, expected days to sale are 7 / p; the difference with and without a report
   is the days saved, priced at part 2's daily cost. Both periods of the experiment are shown, because the effect was
   large in one and nil in the other.

3. **Timing within the year.** Used-car price indices have a seasonal pattern. Each monthly series (Eurostat's
   second-hand car index for every EU market with a complete window, and the UK's ONS index, not seasonally adjusted)
   is compared with its own centred 2x12 moving average; the average deviation by calendar month is its seasonal
   profile. Two windows: before the shortage (2015-12 to 2019-12, where most EU series in our file begin) and the
   common window (2016-12 to 2025-12); the UK's long series (1988-2019) is shown beside as a check. The group sets the
   term of its buy-back contracts (12 months or less), so it can schedule returns away from weak months at no holding
   cost; holding a car to wait for a better month costs part 2's daily cost, which the profile is set against.
4. **Round-number mileage.** Lacetera, Pope & Sydnor found US wholesale prices drop at each 10,000-mile odometer
   mark. The same test on our European adverts in km: cars within 2,000 km of a 10,000-km mark, prices compared on
   either side with a local line on each side, inside cells of source x make x model x age x mark. Adverts heap at
   round mileages (30-64% at exact thousands in the continental sources), so only exact readings (not a multiple of
   1,000 km) are used; a placebo mark halfway between (x2,500 km) should show no jump. Sources: continental adverts in
   km (UK adverts are in miles; vans and `lv_ss`, whose rows are observations rather than cars, are left out).

Limits, stated rather than solved: Aramis's mix is its own (bought mostly from private sellers), not a returned
buy-back car; its EBITDA includes its B2B and services lines; the condition-report result is US data, from one auction
house, and European remarketing platforms already publish inspection reports, so the gain is a means of cutting days,
not a lever to add on top of part 2's.

Seasonality is of index prices (adverts in the UK since 2024, guide values in France, whose index is smoothed:
X10), and of an average car, not a returned one. The mileage test uses asking prices, so a jump shows what sellers
expect buyers to pay.

Checks: gross profit per car recomputed from the reconciliation equals the published GPU within a euro; the
experiment's two gaps reproduce the slides' 6.3 and 0.5 points; every input is read from the register or from
`time_in_stock_rates.csv`, never typed.

Usage: .venv/bin/python analysis/recovery_levers.py   (writes analysis/recovery_levers_report.md)
"""
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_unified import md_table  # noqa: E402

OUT = HERE / "recovery_levers_report.md"
REGISTER = HERE.parent / "assumptions.csv"
RATES = HERE / "time_in_stock_rates.csv"
WEEK = 7.0                     # the experiment's auction ran once a week
INDICES = HERE.parent / "data" / "reference" / "price_indices.parquet"
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
EUROSTAT = "Eurostat HICP, second-hand motor cars (CP07112)"
ONS = "ONS CPI 07.1.1B, second-hand cars (D7E9)"
EU = ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU",
      "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"]
CORE = ["FR", "IT", "DE", "ES", "PL", "NL", "PT"]          # level_risk.py's core markets
WINDOWS = {"2015-12 to 2019-12 (before the shortage)": ("2015-12", "2019-12"),
           "2016-12 to 2025-12 (common window)": ("2016-12", "2025-12")}
UK_LONG = ("1988-01", "2019-12")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
KM_SOURCES = ["de_2023", "pl_2021", "pl_2022_05", "pl_2023_04", "pl_2023_08", "es_2020_11", "se_2022", "eu_2025_11"]
MARK, WINDOW_KM = 10_000, 2_000


def register():
    rows = {r["id"]: r for r in csv.DictReader(open(REGISTER, encoding="utf-8"))}
    return {k: float(r["value"]) for k, r in rows.items() if r["value"] not in ("", None)
            and k.startswith(("aramis_fy25_", "tz_", "dat_"))}


def eur(x, d=0):
    return f"EUR {x:,.{d}f}"


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def channel(reg, rates):
    units = reg["aramis_fy25_b2c_units"]
    price = reg["aramis_fy25_b2c_revenue_eur_m"] * 1e6 / units
    before = reg["aramis_fy25_gross_before_refurb_eur_m"] * 1e6 / units
    refurb = reg["aramis_fy25_transport_refurb_eur_m"] * 1e6 / units
    gpu = before - refurb
    ebitda = reg["aramis_fy25_adj_ebitda_eur_m"] * 1e6 / units
    per_car = pd.DataFrame([
        ("average retail price", eur(price), ""),
        ("margin before transport and refurbishing", eur(before), pct(before / price)),
        ("transport and refurbishing", eur(refurb), pct(refurb / price)),
        ("gross profit (GPU), before operating costs", eur(gpu), pct(gpu / price)),
        ("adjusted EBITDA, after all costs", eur(ebitda), pct(ebitda / price)),
    ], columns=["per retail car, FY2025", "euros", "share of the retail price"])
    rows = []
    for key, label in (("rate_low", "low"), ("rate_mid", "central"), ("rate_high", "high")):
        day = rates[key] * price
        rows.append({"daily cost of stock (part 2)": label, "a day for this car": eur(day, 2),
                     "extra days that eat the margin after all costs": f"{ebitda / day:.0f}",
                     "extra days that eat the gross profit": f"{gpu / day:.0f}"})
    breakeven = pd.DataFrame(rows)
    book = rates["book_eur_m"]
    per_share = pd.DataFrame([
        {"of a year's buy-back returns routed to own retail": "each 1%",
         "gain after all costs": f"EUR {book * 0.01 * ebitda / price:.1f}m",
         "gain before operating costs": f"EUR {book * 0.01 * gpu / price:.1f}m"}])
    out = {"price": price, "gpu": gpu, "ebitda": ebitda, "refurb": refurb,
           "rate_low_gain": ebitda / price, "rate_high_gain": gpu / price,
           "breakeven_mid": ebitda / (rates["rate_mid"] * price)}
    return per_car, breakeven, per_share, out


def condition(reg, rates, price):
    rows, days = [], {}
    for period, a, b in (("weeks 31-39", "tz_sold_no_report_late_pct", "tz_sold_report_late_pct"),
                         ("weeks 21-30", "tz_sold_no_report_early_pct", "tz_sold_report_early_pct")):
        p0, p1 = reg[a] / 100, reg[b] / 100
        d0, d1 = WEEK / p0, WEEK / p1
        days[period] = d0 - d1
        rows.append({"period of the experiment": period, "sold a week, no report": pct(p0),
                     "sold a week, with a report": pct(p1), "gap (points)": f"{100 * (p1 - p0):.1f}",
                     "expected days to sale, no report": f"{d0:.1f}", "expected days, with a report": f"{d1:.1f}",
                     "days saved": f"{d0 - d1:.1f}",
                     "per car at the retail price, central daily cost": eur((d0 - d1) * rates["rate_mid"] * price, 2),
                     "a year's buy-back returns, central": f"EUR {(d0 - d1) * rates['rate_mid'] * rates['book_eur_m']:.1f}m"})
    return pd.DataFrame(rows), days


def profiles(window, only_uk=False):
    """Seasonal profile per series: mean log deviation from a centred 2x12 moving average, by calendar month."""
    d = pd.read_parquet(INDICES)
    start, end = window
    out = {}
    for (series, geo), g in d.groupby(["series", "geo"], observed=True):
        if not ((series == EUROSTAT and geo in EU and not only_uk) or (series == ONS)):
            continue
        s = g.sort_values("month").drop_duplicates("month").set_index("month")["index_value"].astype(float)
        s = s[(s.index >= start) & (s.index <= end)]
        if len(s) != len(pd.period_range(start, end, freq="M")) or s.isna().any() or (s <= 0).any():
            continue
        x = np.log(s.to_numpy())
        trend = pd.Series(x).rolling(12, center=True).mean().rolling(2, center=True).mean().shift(-1).to_numpy()
        dev = pd.Series(x - trend, index=pd.PeriodIndex(s.index, freq="M")).dropna()
        prof = dev.groupby(dev.index.month).mean()
        out["UK" if series == ONS else geo] = prof - prof.mean()
    return pd.DataFrame(out)


def seasonality(rates):
    tables, summary = {}, {}
    for label, window in WINDOWS.items():
        p = profiles(window)
        pooled = p.median(axis=1)
        worst, best = int(pooled.idxmin()), int(pooled.idxmax())
        own_worst = p.idxmin()
        near = ((own_worst - worst).abs().isin([0, 1, 11])).mean()
        corr = p.corr().to_numpy()
        mean_corr = float(corr[np.triu_indices_from(corr, 1)].mean())
        nxt = (worst % 12) + 1
        prv = ((worst - 2) % 12) + 1
        gain_adjacent = float(max(pooled[nxt], pooled[prv]) - pooled[worst])
        show = [g for g in CORE + ["UK"] if g in p.columns]
        rows = [{"market": g, **{m: f"{100 * p.loc[i + 1, g]:+.1f}" for i, m in enumerate(MONTHS)},
                 "best to worst (points)": f"{100 * (p[g].max() - p[g].min()):.1f}"} for g in show]
        rows.append({"market": f"median of all {p.shape[1]} markets",
                     **{m: f"{100 * pooled[i + 1]:+.1f}" for i, m in enumerate(MONTHS)},
                     "best to worst (points)": f"{100 * (pooled.max() - pooled.min()):.1f}"})
        if label.endswith("(before the shortage)"):
            uk = profiles(UK_LONG, only_uk=True)["UK"]
            rows.append({"market": "UK, 1988-2019 (check)", **{m: f"{100 * uk[i + 1]:+.1f}" for i, m in enumerate(MONTHS)},
                         "best to worst (points)": f"{100 * (uk.max() - uk.min()):.1f}"})
        tables[label] = pd.DataFrame(rows)
        summary[label] = {"markets": p.shape[1], "worst": MONTHS[worst - 1], "best": MONTHS[best - 1],
                          "spread": float(pooled.max() - pooled.min()), "near": float(near), "corr": mean_corr,
                          "gain_adjacent": gain_adjacent, "month_hold": 30 * rates["rate_mid"],
                          "book_gain": rates["book_eur_m"] / 12 * gain_adjacent}
    return tables, summary


def load_km():
    cols = ["source", "country", "make", "model", "age_years", "mileage_km", "price_eur"]
    t = pq.read_table(LISTINGS, columns=cols, filters=[("source", "in", KM_SOURCES)])
    d = t.to_pandas()
    d = d[d["country"].isin(["DE", "PL", "ES", "SE", "IT"])]
    d = d.dropna(subset=["make", "model", "age_years", "mileage_km", "price_eur"])
    d = d[(d["price_eur"] > 500) & (d["age_years"] >= 1) & (d["age_years"] <= 12)
          & (d["mileage_km"] > 5_000) & (d["mileage_km"] < 155_000)]
    return d.assign(exact=(d["mileage_km"] % 1000) != 0, age=d["age_years"].astype(int),
                    y=np.log(d["price_eur"].astype(float)))


def jump(d, offset):
    """Price jump at marks every 10,000 km (shifted by `offset`), local lines on each side, within cells."""
    m = d["mileage_km"].to_numpy(float)
    mark = np.round((m - offset) / MARK) * MARK + offset
    r = m - mark
    keep = (np.abs(r) < WINDOW_KM) & (r != 0) & (mark >= MARK)
    e = d[keep].assign(mark=mark[keep], r=r[keep] / 1000)
    e = e.assign(above=(e["r"] > 0).astype(float))
    e = e.assign(ra=e["r"] * e["above"])
    cell = e.groupby(["source", "make", "model", "age", "mark"], observed=True).ngroup()
    e = e.assign(cell=cell.to_numpy())
    both = e.groupby("cell")["above"].transform(lambda a: 0 < a.mean() < 1)
    e = e[both]
    cols = ["y", "above", "r", "ra"]
    dm = e[cols] - e.groupby("cell")[cols].transform("mean")
    X, y = dm[["above", "r", "ra"]].to_numpy(), dm["y"].to_numpy()
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    u = y - X @ beta
    bread = np.linalg.pinv(X.T @ X)
    g = pd.DataFrame(X * u[:, None]).groupby(e["cell"].to_numpy()).sum().to_numpy()
    V = bread @ (g.T @ g) @ bread
    below = ((r > -500) & (r < 0)).sum()
    above_n = ((r > 0) & (r < 500)).sum()
    return {"jump": float(beta[0]), "se": float(np.sqrt(V[0, 0])), "cars": len(e), "cells": int(e["cell"].nunique()),
            "density_ratio": float(below / above_n) if above_n else float("nan"),
            "median_price": float(np.exp(e["y"]).median())}


def left_digit():
    d = load_km()
    exact = d[d["exact"]]
    real, placebo = jump(exact, 0), jump(exact, MARK / 4)
    return real, placebo, float(d["exact"].mean()), len(d)


def main():
    reg = register()
    rates = pd.read_csv(RATES).set_index("key")["value"]
    per_car, breakeven, per_share, ch = channel(reg, rates)
    cond, days = condition(reg, rates, ch["price"])
    seas_tables, seas = seasonality(rates)
    ld_real, ld_placebo, exact_share, km_cars = left_digit()

    gaps = [100 * (reg["tz_sold_report_late_pct"] - reg["tz_sold_no_report_late_pct"]) / 100,
            100 * (reg["tz_sold_report_early_pct"] - reg["tz_sold_no_report_early_pct"]) / 100]
    ck = pd.DataFrame([
        {"check": "gross profit per car recomputed from the reconciliation equals the published GPU within a euro",
         "got": f"{eur(ch['gpu'])} against {eur(reg['aramis_fy25_gpu_eur'])}",
         "passes": abs(ch["gpu"] - reg["aramis_fy25_gpu_eur"]) <= 1.0},
        {"check": "the experiment's gaps reproduce the slides' 6.3 and 0.5 points",
         "got": f"{gaps[0]:.1f} and {gaps[1]:.1f}", "passes": round(gaps[0], 1) == 6.3 and round(gaps[1], 1) == 0.5},
        {"check": "part 2's daily rates are read from time_in_stock_rates.csv", "got": f"{len(rates)} rates",
         "passes": {"rate_low", "rate_mid", "rate_high", "book_eur_m"} <= set(rates.index)},
        {"check": "seasonal profiles cover most EU markets in both windows",
         "got": ", ".join(f"{v['markets']} series" for v in seas.values()),
         "passes": all(v["markets"] >= 15 for v in seas.values())},
        {"check": "the placebo mark (halfway between 10,000s) shows no jump beyond two standard errors",
         "got": f"{100 * ld_placebo['jump']:+.2f}% (s.e. {100 * ld_placebo['se']:.2f})",
         "passes": abs(ld_placebo["jump"]) <= 2 * ld_placebo["se"]},
    ])
    all_ok = bool(ck["passes"].all())

    findings = [
        f"- **Retailing a returned car in-house earns between {pct(ch['rate_low_gain'])} and "
        f"{pct(ch['rate_high_gain'])} of its price** over selling it to the trade: Aramis's EBITDA per retail car "
        f"({eur(ch['ebitda'])}) after all costs, its gross profit per car ({eur(ch['gpu'])}) before operating costs. The "
        "truth for extra cars routed through existing sites lies between: some operating costs are fixed.",
        f"- **It pays unless retail adds more than about {ch['breakeven_mid']:.0f} days in stock** (central daily cost, "
        "after all costs). Refurbishing is part of it: transport and refurbishing cost Aramis "
        f"{eur(ch['refurb'])} a car, already inside both margins.",
        f"- **Each 1% of a year's buy-back returns routed to own retail is worth about {per_share.iloc[0, 1]} to "
        f"{per_share.iloc[0, 2]} a year.** How much can be routed is capacity and mix, not measured here; part 5 "
        "registers it as an assumption.",
        f"- **Condition reports buy speed, not price:** in the weeks the effect showed, a published report cut the "
        f"expected time to sale by about {days['weeks 31-39']:.1f} days; in the other period by "
        f"{days['weeks 21-30']:.1f}. On a year's buy-back returns that is up to {cond.iloc[0, -1]} at the central daily "
        "cost (US data). European remarketing platforms already publish inspection reports, so this is one way to cut "
        "days, not a lever to add to part 2's.",
    ]
    pre = seas["2015-12 to 2019-12 (before the shortage)"]
    com = seas["2016-12 to 2025-12 (common window)"]
    sig = abs(ld_real["jump"]) > 2 * ld_real["se"]
    uk_long = profiles(UK_LONG, only_uk=True)["UK"]
    uk_spread = 100 * float(uk_long.max() - uk_long.min())
    findings += [
        f"- **Continental used-car prices are barely seasonal, and not in step:** across {pre['markets']} markets "
        f"before the shortage the median profile runs {100 * pre['spread']:.1f} points from its weakest month "
        f"({pre['worst']}) to its best ({pre['best']}), {100 * com['spread']:.1f} points in the common window. "
        f"Markets' profiles correlate {pre['corr']:.2f} on average, and only {pct(pre['near'], 0)} have their own "
        f"weakest month within a month of the median's. The UK's index is the seasonal one ({uk_spread:.1f} points "
        "over 1988-2019), and even its shape changed between windows.",
        f"- **Timing is a scheduling lever, not a holding one.** Moving a return from the weakest month to the better "
        f"neighbouring month gains about {100 * pre['gain_adjacent']:.1f} points (before the shortage), while holding a "
        f"car a month costs about {100 * pre['month_hold']:.1f} points (part 2, central). Setting buy-back terms so "
        f"returns avoid the weakest month costs nothing to hold: on a twelfth of a year's returns that is about "
        f"EUR {pre['book_gain']:.1f}m ({com['book_gain']:.1f}m in the common window).",
        f"- **Round-number mileage {'does' if sig else 'does not'} show in European asking prices:** at 10,000-km marks, "
        f"prices {'drop' if ld_real['jump'] < 0 else 'change'} by {100 * ld_real['jump']:+.2f}% (s.e. "
        f"{100 * ld_real['se']:.2f}; {ld_real['cars']:,} exact readings in {ld_real['cells']:,} cells), against "
        f"{100 * ld_placebo['jump']:+.2f}% at the placebo mark; {pct(exact_share, 0)} of adverts give an exact reading. "
        f"Sellers bunch just below the mark ({ld_real['density_ratio']:.2f} times as many exact readings in the 500 km "
        "below as above, against about 1 at the placebo), which is what a seller expecting the penalty would do, and "
        "which also means the jump is not a clean causal estimate. The size is close to the US finding. The lever is "
        "small: only cars that would cross a mark while waiting for sale are exposed, so the ledger should flag them "
        "rather than the workbook count them.",
        "- **Cross-border has no public net figure.** The European Commission's 2014 study shows the flows (42% of "
        "imported used cars come from Germany) but no margin net of VAT, registration tax and transport, and "
        "vendor claims were rejected (part 1). Named, unsized.",
    ]

    lines = [
        "# X17 parts 3-4: the channel, condition reports, timing and round-number mileage",
        "",
        "Generated by `analysis/recovery_levers.py`; the method is in its docstring. Aramis Group is the group's own "
        "used-car retailer (60.54% owned); the auction experiment is **US data**.",
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
        "## 1. The channel: Aramis per retail car",
        "",
        md_table(per_car),
        "",
        "How many extra days in stock would eat the margin, at part 2's daily cost for a car at this price:",
        "",
        md_table(breakeven),
        "",
        "Scaled to the group's book:",
        "",
        md_table(per_share),
        "",
        "## 2. Condition reports, as days saved",
        "",
        "Expected days to sale = 7 / (the share sold each weekly auction), re-running each week until sold.",
        "",
        md_table(cond),
        "",
        "## 3. Timing within the year: seasonal profiles (points above or below the market's own trend)",
        "",
        *[x for label, t in seas_tables.items() for x in (f"**{label}**", "", md_table(t), "")],
        "## 4. Round-number mileage in European asking prices",
        "",
        md_table(pd.DataFrame([
            {"mark": "every 10,000 km", "price jump": f"{100 * ld_real['jump']:+.2f}%",
             "standard error (by cell)": f"{100 * ld_real['se']:.2f}", "exact readings": f"{ld_real['cars']:,}",
             "cells": f"{ld_real['cells']:,}", "readings just below over just above (500 km)": f"{ld_real['density_ratio']:.2f}"},
            {"mark": "placebo, halfway between", "price jump": f"{100 * ld_placebo['jump']:+.2f}%",
             "standard error (by cell)": f"{100 * ld_placebo['se']:.2f}", "exact readings": f"{ld_placebo['cars']:,}",
             "cells": f"{ld_placebo['cells']:,}", "readings just below over just above (500 km)": f"{ld_placebo['density_ratio']:.2f}"},
        ])),
        "",
        f"Continental adverts in km ({', '.join(KM_SOURCES)}), cars 1-12 years, {km_cars:,} adverts of which "
        f"{pct(exact_share, 0)} give an exact reading. A ratio well above 1 would mean sellers bunch below the mark.",
        "",
        "## Limits",
        "",
        "- **Aramis's mix is its own:** cars bought mostly from private sellers, not returned buy-back cars; its "
        "EBITDA includes its B2B and services lines.",
        "- **The margin is an average, not the margin on the next car routed:** some operating costs are fixed, so the "
        "marginal gain lies between the two ends.",
        "- **The auction experiment is US data,** one auction house, one period with an effect and one without; the "
        "weekly re-run model assumes a constant chance of sale.",
        "- **Seasonality is of index prices** (the UK's index is adverts since 2024; France's is smoothed guide "
        "values), of an average car, and moving many returns into one month would move its price.",
        "- **The mileage test is on asking prices** and exact readings only; it says what sellers expect, not what "
        "buyers paid.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(f"wrote {OUT.name}; checks pass: {all_ok}")


if __name__ == "__main__":
    main()
