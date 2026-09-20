"""Manheim New Zealand damaged-vehicle auction listings, scraped daily from 27 May 2023.

Mileage is deliberately not read: the publisher's clean_data.py fills missing mileage with the
(make, model, year) median, and the published file does not mark which values were filled.
"""
import pandas as pd

from .common import http_download

INFO = {"country": "NZ", "price_type": "asking", "license": "MIT",
        "url": "https://github.com/prasanthsasikumar/FindCars-NZ"}

URL = ("https://raw.githubusercontent.com/prasanthsasikumar/FindCars-NZ/main/"
       "data/processed/car_auction_public.parquet")

# Price_USD and Mileage_Miles are mislabels: clean_data.py parses the raw Manheim NZ fields
# without converting them, so the price is NZD and the mileage would be km.
FUEL = {"Petrol": "petrol", "Diesel": "diesel", "Hybrid": "hybrid", "Electric": "electric",
        "LPG": "lpg", "Dual Fuel": "other"}


def download(raw):
    http_download(URL, raw / "car_auction_public.parquet")


def load(raw):
    d = pd.read_parquet(raw / "car_auction_public.parquet")
    # the file is a daily scrape of live listings, so one car appears on many days
    d = d[d["Is_Latest"]].copy()
    gearbox = d["Transmission_Type"].astype("string").str.lower()
    impact = d["Impact_Severity"].astype("string")
    return pd.DataFrame({
        "listing_date": d["scrape_date"], "date_basis": "listing",
        "make": d["Manufacturer"], "model": d["Model"], "year": d["Year"],
        # values are truncated in places ("Automati") and carry a trailing comma ("5spd Manual,")
        "transmission": pd.Series(
            gearbox.str.contains("manual", na=False).map({True: "manual"})
            .fillna(gearbox.str.contains("automat|cvt", regex=True, na=False).map({True: "automatic"})),
            index=d.index),
        "fuel": d["Fuel Type"].map(FUEL),
        # every listing comes from Manheim's damaged-vehicles channel
        "is_damaged": True,
        "had_accident": impact.isin(["Heavy", "Medium", "Light"]).where(impact.ne("Unknown")),
        "days_on_market": d["Days_Listed"],
        "price": d["Price_USD"], "currency": "NZD",
    })
