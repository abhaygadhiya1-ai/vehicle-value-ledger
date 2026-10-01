"""X17 part 2: what a day in stock costs a returned car, and the buy-back book.

Skeptic F3: the case asks how to "maximize value recovery across the ownership cycle", and our answer so far prices
the market level (X6) without sizing any recovery lever. Time is the first: every day a returned car waits unsold it
ages, the market moves under it, and its value is tied up. Dealers know this cost; the DAT Barometer puts a German
dealer's standing day at EUR 30 in October 2024, covering fees, marketing, standing damage and financing but not the
car's own loss of value (X17 part 1). This script measures that loss and prices a day on the group's disclosed book.

1. **The car ages.** A waiting car keeps its mileage, so its loss is the age curve at fixed mileage. For cars sampled
   from each market's recent listings, the value engine prices the same car at its age and one year older at the same
   mileage (no horizon, so no driving is projected); the log difference is the local yearly age cost at that age,
   including the curve's bend (the engine takes its level from cars within a year of the age asked).
2. **The market moves.** The average monthly move of the official used-car price index in the core markets
   (`level_risk.py`'s common window), and the same before the 2021-22 shortage. The average drift offsets part of the
   ageing; its variability is risk (X6, X7), not an expected cost.
3. **The money is tied up.** Financing at the ECB deposit rate (a floor) and at European banks' cost of equity (a
   ceiling), both register rows.

The book: payables for buy-back agreements due within a year (`buyback_payables_current_eur_m`, 20-F Note 24), whose
contracts run 12 months or less (`buyback_term_policy`), so returned cars are young: the 0-2 year band sets the
book's rate and 2-4 years is shown beside it. How many days the group could cut is not measured here: the group
discloses no days to sell. Part 5 registers it as an assumption anchored to DAT, INDICATA and Auto Trader.

Limits, stated rather than solved: advert prices; the engine's curve, not a transaction curve; the average drift is
nominal and includes the 2021-22 boom (hence the pre-shortage window beside it); a car's value at return is taken as
its repurchase price, since the book is a payable.

Checks: the mean yearly age cost at fixed mileage lies inside the register's pooled range (`dep_pooled`, low to
high); the engine really held the mileage (its valuation mileage equals the input); every core market has a full index
window; the book and the rates are read from the register, never typed.

Usage: .venv/bin/python analysis/time_in_stock.py   (writes analysis/time_in_stock_report.md; a few minutes)
"""
import csv
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import level_risk  # noqa: E402
import value_engine as ve  # noqa: E402
from build_unified import md_table  # noqa: E402
from engine_check import AGE_BANDS  # noqa: E402

OUT = HERE / "time_in_stock_report.md"
REGISTER = HERE.parent / "assumptions.csv"
MARKETS = ("GB", "PL", "SE", "DE", "PT", "NL", "FR", "AT")     # as conformal_bands.py
PER_BAND = 120              # cars sampled per market and age band
MAX_AGE = 15.0
PRE_SHORTAGE_END = "2019-12"
BOOK_BAND = "(0 to 2]"      # buy-back contracts run 12 months or less
CHECK_BAND = "(2 to 4]"
DAYS = 365.0


def register():
    rows = {r["id"]: r for r in csv.DictReader(open(REGISTER, encoding="utf-8"))}
    f = lambda k, c="value": float(rows[k][c])  # noqa: E731
    return {"dep": f("dep_pooled"), "dep_lo": f("dep_pooled", "low"), "dep_hi": f("dep_pooled", "high"),
            "book": f("buyback_payables_current_eur_m"), "ecb": f("ecb_deposit_rate"), "coe": f("eba_bank_coe"),
            "dat_day": f("dat_standing_day_cost_eur")}


def aramis_price():
    """The latest quarter's realised price per refurbished car, read from aramis_prices_report.md (X10)."""
    lines = (HERE / "aramis_prices_report.md").read_text().splitlines()
    head = next(i for i, x in enumerate(lines) if x.startswith("| fiscal quarter |"))
    cols = [c.strip() for c in lines[head].strip("|").split("|")]
    body = []
    for x in lines[head + 2:]:
        if not x.startswith("|"):
            break
        body.append([c.strip() for c in x.strip("|").split("|")])
    last = dict(zip(cols, body[-1]))
    return float(last["realised price per refurbished car (EUR)"].replace(",", "")), last["fiscal quarter"]


def band_of(age):
    return pd.cut(pd.Series(age), AGE_BANDS).astype(str).str.replace(", ", " to ").to_numpy()


def ageing(market):
    """Yearly log change in value from one more year of age at the same mileage, per sampled car."""
    engine = ve.ValueEngine(market, verbose=False)
    d = engine.local.dropna(subset=["make", "model", "age_years", "mileage_km", "fuel", "transmission",
                                    "body_type", "price_eur"])
    d = d[(d["age_years"] > 0.1) & (d["age_years"] <= MAX_AGE) & (d["mileage_km"] > 0)]
    d = d.assign(band=band_of(d["age_years"].to_numpy(float)))
    seed = zlib.crc32(("stock-" + market).encode()) % 2 ** 31
    sample = pd.concat([g.sample(min(PER_BAND, len(g)), random_state=seed) for _, g in d.groupby("band")])
    rows = []
    for _, c in sample.iterrows():
        kw = dict(mileage=float(c["mileage_km"]), fuel=c["fuel"], gearbox=c["transmission"], body=c["body_type"])
        try:
            now = engine.predict(c["make"], c["model"], float(c["age_years"]), **kw)
            older = engine.predict(c["make"], c["model"], float(c["age_years"]) + 1.0, **kw)
        except ValueError:
            continue
        held = (now["mileage_at_valuation_km"] == kw["mileage"]) and (older["mileage_at_valuation_km"] == kw["mileage"])
        rows.append({"market": market, "band": c["band"], "age": float(c["age_years"]), "price": float(c["price_eur"]),
                     "value": now["value_eur"], "yearly_log": np.log(older["value_eur"] / now["value_eur"]),
                     "mileage_held": held})
    return pd.DataFrame(rows)


def drift():
    """Average monthly log move of each core market's official index, full common window and before the shortage."""
    series = level_risk.load()
    rows = []
    for geo in level_risk.CORE:
        s = series.get((level_risk.EUROSTAT, geo))
        if s is None:
            continue
        s = s[(s.index >= level_risk.COMMON_START) & (s.index <= level_risk.COMMON_END)]
        full = len(s) == len(pd.period_range(level_risk.COMMON_START, level_risk.COMMON_END, freq="M"))
        m = np.log(s).diff().dropna()
        pre = m[m.index <= PRE_SHORTAGE_END]
        rows.append({"geo": geo, "full_window": full, "monthly_full": float(m.mean()), "monthly_pre": float(pre.mean()),
                     "months": len(m)})
    return pd.DataFrame(rows)


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def main():
    reg = register()
    cars = pd.concat([ageing(m) for m in MARKETS], ignore_index=True)
    dr = drift()

    # 1. yearly age cost at fixed mileage, by age band: median per market, then the median across markets
    order = [str(b).replace(", ", " to ") for b in pd.cut([1], AGE_BANDS).categories]
    per = cars.groupby(["band", "market"])["yearly_log"].median().unstack()
    per = per.reindex([b for b in order if b in per.index])
    pooled = per.median(axis=1)
    age_rows = []
    for b in per.index:
        row = {"car age, years": b.replace("(", "").replace("]", ""),
               "cars": int(cars[cars["band"] == b].shape[0]),
               "all markets (median of markets)": pct(np.expm1(pooled[b]))}
        row.update({m: pct(np.expm1(per.loc[b, m])) for m in per.columns})
        age_rows.append(row)
    age_table = pd.DataFrame(age_rows)
    mean_yearly = float(np.expm1(cars["yearly_log"].mean()))

    # 2. the market's drift
    ok_drift = bool(dr["full_window"].all()) and len(dr) >= 5
    drift_full = float(dr["monthly_full"].median())
    drift_pre = float(dr["monthly_pre"].median())
    drift_table = pd.DataFrame({"market": dr["geo"], "average move a month, 2016-12 to 2025-12": [pct(np.expm1(x), 2) for x in dr["monthly_full"]],
                                f"the same, to {PRE_SHORTAGE_END}": [pct(np.expm1(x), 2) for x in dr["monthly_pre"]]})

    # 3. a day in stock, per EUR 10,000 of car, for the book's age band and the check band
    def day_rates(band):
        age_day = -pooled[band] / DAYS                              # value lost to ageing a day (positive)
        return {"ageing": age_day,
                "ageing net of average drift (full window)": age_day - drift_full * 12 / DAYS,
                "ageing net of average drift (before the shortage)": age_day - drift_pre * 12 / DAYS,
                "financing at the ECB deposit rate": np.log1p(reg["ecb"] / 100) / DAYS,
                "financing at banks' cost of equity": np.log1p(reg["coe"] / 100) / DAYS}
    book_rates, check_rates = day_rates(BOOK_BAND), day_rates(CHECK_BAND)
    low = book_rates["ageing net of average drift (full window)"] + book_rates["financing at the ECB deposit rate"]
    mid = book_rates["ageing"] + book_rates["financing at the ECB deposit rate"]
    high = book_rates["ageing net of average drift (before the shortage)"] + book_rates["financing at banks' cost of equity"]
    day_table = pd.DataFrame([{"a day in stock": k, "cars 0-2 years, per EUR 10,000": f"EUR {1e4 * v:.2f}",
                               "cars 2-4 years, per EUR 10,000": f"EUR {1e4 * check_rates[k]:.2f}"}
                              for k, v in book_rates.items()])
    total_table = pd.DataFrame([
        {"reading": "low: ageing net of the full-window drift, financing at the ECB deposit rate",
         "per EUR 10,000 a day": f"EUR {1e4 * low:.2f}", "a year's buy-back returns, per day of stock": f"EUR {reg['book'] * low:.2f}m"},
        {"reading": "central: ageing, financing at the ECB deposit rate",
         "per EUR 10,000 a day": f"EUR {1e4 * mid:.2f}", "a year's buy-back returns, per day of stock": f"EUR {reg['book'] * mid:.2f}m"},
        {"reading": "high: ageing net of the pre-shortage drift, financing at banks' cost of equity",
         "per EUR 10,000 a day": f"EUR {1e4 * high:.2f}", "a year's buy-back returns, per day of stock": f"EUR {reg['book'] * high:.2f}m"},
    ])

    # 4. one car at Aramis's latest realised price, beside a German dealer's standing day (DAT, no value loss)
    car_value, car_quarter = aramis_price()
    car_age_day = car_value * book_rates["ageing"]
    car_low, car_mid, car_high = car_value * low, car_value * mid, car_value * high

    # checks
    lo, hi = sorted([reg["dep_lo"] / 100, reg["dep_hi"] / 100])
    ck = pd.DataFrame([
        {"check": "the mean yearly age cost at fixed mileage lies inside the register's pooled range (dep_pooled)",
         "got": f"{pct(mean_yearly)} against {pct(lo)} to {pct(hi)}", "passes": lo <= mean_yearly <= hi},
        {"check": "the engine held every car's mileage", "got": f"{cars['mileage_held'].mean():.0%} of {len(cars):,} cars",
         "passes": bool(cars["mileage_held"].all())},
        {"check": "every core market has a full index window", "got": f"{int(dr['full_window'].sum())} of {len(dr)}",
         "passes": ok_drift},
        {"check": "the book and the rates come from the register", "got": f"book EUR {reg['book']:,.0f}m, ECB {reg['ecb']}%, "
         f"cost of equity {reg['coe']}%", "passes": True},
    ])
    all_ok = bool(ck["passes"].all())

    findings = [
        f"- **A returned young car loses {pct(np.expm1(pooled[BOOK_BAND]))} of its value a year to age alone at fixed "
        f"mileage** (cars 0-2 years, median across eight markets; {pct(np.expm1(pooled[CHECK_BAND]))} at 2-4 years). "
        f"Over all ages the engine's mean, {pct(mean_yearly)}, sits inside the register's pooled range.",
        f"- **The market's average drift offsets part of it:** the core markets' indices rose by a median "
        f"{pct(np.expm1(drift_full), 2)} a month over 2016-2025 and {pct(np.expm1(drift_pre), 2)} before the shortage. "
        "That is an average, not a forecast (X7).",
        f"- **A day in stock costs about EUR {1e4 * low:.2f} to EUR {1e4 * high:.2f} per EUR 10,000 of young car** "
        f"(central EUR {1e4 * mid:.2f}), counting ageing, the average drift and financing.",
        f"- **On a year's buy-back returns (EUR {reg['book']:,.0f}m), each day of average time to sale costs about "
        f"EUR {reg['book'] * low:.1f}m to EUR {reg['book'] * high:.1f}m** (central EUR {reg['book'] * mid:.1f}m). "
        "Ten days cut is ten times that. How many days the group can cut is not measured: it discloses no days to sell.",
        f"- **One car at Aramis's latest realised price** (EUR {car_value:,.0f}, {car_quarter}) loses about "
        f"EUR {car_age_day:.2f} a day to age, and costs EUR {car_low:.2f} to EUR {car_high:.2f} a day in all "
        f"(central EUR {car_mid:.2f}). A German dealer's standing day is EUR {reg['dat_day']:.0f} before any loss of "
        "value (DAT): a dealer's day is mostly the cost of running the stock, the group's mostly the car ageing and "
        "its financing, so a dealer's day plus the ageing is the upper reference for a retail sale.",
    ]

    lines = [
        "# X17 part 2: what a day in stock costs",
        "",
        "Generated by `analysis/time_in_stock.py`; the method is in its docstring. **Advert prices**, the value engine's "
        "curve at fixed mileage, the core markets' official indices, and the group's disclosed buy-back book.",
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
        "## 1. The car ages: yearly loss of value at fixed mileage, by age",
        "",
        "Median across sampled cars in each market; the first value column is the median of the market medians.",
        "",
        md_table(age_table),
        "",
        "## 2. The market moves: average monthly change of the official used-car index",
        "",
        md_table(drift_table),
        "",
        "## 3. A day in stock, per EUR 10,000 of car",
        "",
        md_table(day_table),
        "",
        "## 4. Adding it up",
        "",
        md_table(total_table),
        "",
        "## Limits",
        "",
        "- **Advert prices** and the engine's curve; the loss a remarketer meets at auction may differ.",
        "- **The curve bends in some markets only.** Where the engine's local level doesn't change with age (AT, FR, NL "
        "and PT in the table), the yearly cost is the straight-line slope at every age. It is measured at fixed "
        "mileage, so it is flatter for young cars than a curve that also counts their driving.",
        "- **The drift is an average over a window with a boom in it** (hence the pre-shortage reading); a given month's "
        "move is risk, priced by X6, not an expected cost.",
        "- **The book is a payable:** a car's value at return is taken as its repurchase price.",
        "- **Days saved are not measured here.** The group discloses none; part 5 anchors an assumption to DAT, INDICATA "
        "and Auto Trader.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    pd.DataFrame([("rate_low", low, "a day in stock per euro of young car: ageing net of the full-window drift, ECB rate"),
                  ("rate_mid", mid, "the same: ageing, ECB rate"),
                  ("rate_high", high, "the same: ageing net of the pre-shortage drift, banks' cost of equity"),
                  ("ageing_day", book_rates["ageing"], "value lost to ageing a day per euro of young car"),
                  ("book_eur_m", reg["book"], "buy-back payables due within a year, from the register")],
                 columns=["key", "value", "description"]).to_csv(HERE / "time_in_stock_rates.csv", index=False)
    print(ck.to_string(index=False))
    print(f"wrote {OUT.name}; checks pass: {all_ok}")


if __name__ == "__main__":
    main()
