"""Audit the unified table: a sanity profile of every source, and the two tests that found defects.

Run after `build_unified.py` and before trusting any analysis. It prints; it changes nothing.

  1. **Profile** - rows, price type, currency and rate per euro, price range, age, mileage and
     mileage a year, power, engine size, repeated rows. Anything outside a plausible range is flagged.
  2. **Repeated adverts** - rows identical in every field except a free-text label such as the
     variant. `uk_2022_10` repeated 360,988 of its raw rows this way.
  3. **Generated rows** - within one make, model, version and year, real advert prices fall as
     mileage rises. A source where price rises with mileage in most groups is not scraped data.
     `fr_2023` failed this (median correlation +0.99) and is rejected in `build_unified.py`.

Usage: .venv/bin/python audit_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
LISTINGS = HERE / "data" / "unified" / "listings.parquet"
EUROPE = {"AT", "BE", "BG", "CH", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "GB", "HR", "HU",
          "IE", "IT", "LT", "LU", "LV", "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK"}
# Expected units of currency per euro over the collection's years, to catch an inverted or wrong rate.
FX_RANGE = {"GBP": (0.80, 0.92), "USD": (1.00, 1.25), "PLN": (4.2, 4.7), "SEK": (9.5, 12.0),
            "CZK": (23, 27), "HUF": (300, 420), "NZD": (1.5, 1.9), "SGD": (1.4, 1.65)}


def median(x, digits=0):
    x = x.dropna()
    return None if x.empty else round(float(x.median()), digits or None)


def profile(d):
    rows, flags = [], []
    for source, g in d.groupby(d["source"].astype(str)):
        used = g[~g["is_new"].fillna(False).astype(bool)]
        per_year = g["mileage_km"] / g["age_years"].where(g["age_years"] >= 1)
        rate = (g["price"] / g["price_eur"]).replace([np.inf, -np.inf], np.nan)
        repeat = g.duplicated(["make", "model", "year", "mileage_km", "price", "fuel", "transmission",
                               "body_type"]).mean()
        r = {"source": source, "rows": len(g), "type": g["price_type"].astype(str).mode().iloc[0],
             "currency": g["currency"].astype(str).mode().iloc[0], "rate per EUR": median(rate, 3),
             "median price EUR": median(g["price_eur"]), "median age": median(used["age_years"], 1),
             "median km a year": median(per_year), "median kW": median(g["power_kw"]),
             "median cc": median(g["engine_cc"]), "repeated rows": f"{repeat:.0%}"}
        rows.append(r)
        if r["median km a year"] and not 5_000 <= r["median km a year"] <= 30_000:
            flags.append(f"{source}: {r['median km a year']:,} km a year")
        if r["median kW"] and not 50 <= r["median kW"] <= 250:
            flags.append(f"{source}: median power {r['median kW']} kW")
        if r["median cc"] and not 800 <= r["median cc"] <= 4_000:
            flags.append(f"{source}: median engine {r['median cc']} cc")
        if r["median price EUR"] and not 2_000 <= r["median price EUR"] <= 80_000:
            flags.append(f"{source}: median price EUR {r['median price EUR']:,}")
        if repeat > 0.05:
            flags.append(f"{source}: {repeat:.0%} of rows repeat another row's make, model, year, "
                         "mileage, price, fuel, gearbox and body")
    return pd.DataFrame(rows), flags


def repeated_adverts(d):
    """Rows identical to another in every field but the free-text variant label."""
    out = []
    fields = [c for c in d.columns if c not in ("version", "listing_id", "listing_date")]
    for source, g in d.groupby(d["source"].astype(str)):
        n = int(g.duplicated(fields).sum())
        if n:
            out.append({"source": source, "rows identical but for label/id/date": n,
                        "share": f"{n / len(g):.1%}"})
    return pd.DataFrame(out)


def generated_rows(d):
    """Within one make, model, version and year, does price fall as mileage rises?"""
    x = d[~d["is_new"].fillna(False).astype(bool) & d["mileage_km"].gt(1_000) & d["price"].gt(500)
          & d["version"].notna()].copy()
    x["group"] = (x["source"].astype(str) + "|" + x["make"].astype(str) + "|" + x["model"].astype(str)
                  + "|" + x["version"].astype(str) + "|" + x["year"].astype(str))
    x["lp"], x["lk"] = np.log(x["price"].astype(float)), np.log(x["mileage_km"].astype(float))
    x = x[x.groupby("group")["lp"].transform("size") >= 10]
    dx = x["lk"] - x.groupby("group")["lk"].transform("mean")
    dy = x["lp"] - x.groupby("group")["lp"].transform("mean")
    t = pd.DataFrame({"source": x["source"].astype(str), "group": x["group"], "xy": dx * dy,
                      "xx": dx * dx, "yy": dy * dy}).groupby(["source", "group"]).sum()
    t = t[(t["xx"] > 0) & (t["yy"] > 0)]
    t["corr"] = t["xy"] / np.sqrt(t["xx"] * t["yy"])
    return (t.groupby("source")["corr"]
            .agg(groups="size", rising=lambda c: f"{(c > 0).mean():.0%}", median="median")
            .round(2).reset_index())


def main():
    d = pd.read_parquet(LISTINGS)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    asking = d[d["price_type"].eq("asking")]
    print(f"{len(d):,} rows, {d['source'].nunique()} sources, {d['country'].nunique()} countries; "
          f"{len(asking):,} advert prices, {asking['country'].isin(EUROPE).mean():.0%} European\n")

    table, flags = profile(d)
    print(table.to_string(index=False))
    print("\nFLAGS - each needs an explanation or a fix")
    print("\n".join(f"  {f}" for f in flags) or "  none")

    print("\nRATES PER EUR")
    for currency, g in d.groupby(d["currency"].astype(str)):
        rate = float((g["price"] / g["price_eur"]).median())
        span = FX_RANGE.get(currency)
        verdict = "" if span is None else ("ok" if span[0] <= rate <= span[1] else "OUTSIDE RANGE")
        print(f"  {currency}: {rate:.3f} {verdict}")

    print("\nREPEATED ADVERTS (identical but for variant label, advert id or date)")
    print(repeated_adverts(d).to_string(index=False))

    print("\nGENERATED ROWS: share of make-model-version-year groups where price RISES with mileage")
    print("(real adverts: a minority, median correlation clearly negative)")
    print(generated_rows(d).to_string(index=False))


if __name__ == "__main__":
    main()
