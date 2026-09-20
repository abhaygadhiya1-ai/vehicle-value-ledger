"""Check one source end to end: download if needed, load, apply the shared cleaning, print a summary.

Usage: .venv/bin/python check_loader.py <source>
"""
import sys

import pandas as pd

import download_data
from build_unified import RAW, finish, load_fx
from loaders import SOURCES


def main(name):
    download_data.main([name])
    module = SOURCES[name]
    df, stats = finish(module.load(RAW / name), name, module.INFO, load_fx())
    print(f"\n== {name}: kept {stats['rows_kept']:,} of {stats['rows_raw']:,}")
    print("dropped:", stats["drops"])
    print("fx fallbacks: annual", stats["fx_annual"], "| latest year", stats["fx_latest_year"])
    print("unmapped:", stats["unmapped"])
    print("coverage:", {c: f"{df[c].notna().mean():.0%}" for c in df.columns})
    print("dates:", df["listing_date"].min(), "->", df["listing_date"].max(), "| basis:", df["date_basis"].unique().tolist())
    for col in ["country", "price_type", "is_new", "fuel", "transmission", "body_type", "seller_type", "currency"]:
        print(f"{col}:", df[col].value_counts(dropna=False).head(10).to_dict())
    print(df[["price_eur", "new_price_eur", "age_years", "mileage_km", "power_kw", "engine_cc"]]
          .describe(percentiles=[0.01, 0.5, 0.99]).round(0).to_string())
    print("top makes:", df["make"].value_counts().head(15).to_dict())
    print("sample:\n", df.sample(min(5, len(df)), random_state=0).to_string())


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    main(sys.argv[1])
