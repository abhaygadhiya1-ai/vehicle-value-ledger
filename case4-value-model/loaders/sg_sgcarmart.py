"""sgcarmart (Singapore) used-car adverts.

Singapore prices include the Certificate of Entitlement, a quota licence that can cost more than
the car, so price levels here are not comparable with any other country in the table.
"""
import pandas as pd

from .common import http_download

INFO = {"country": "SG", "price_type": "asking", "license": "Unknown (no license stated)",
        "url": "https://huggingface.co/datasets/Raymond0960/sgcarmart-data"}

URL = "https://huggingface.co/datasets/Raymond0960/sgcarmart-data/resolve/main/cars_sgcarmart.csv"

FUEL = {"Petrol": "petrol", "Diesel": "diesel", "Electric": "electric",
        "Petrol-Electric": "hybrid", "Diesel-Electric": "hybrid"}
# "Luxury" and "Sports" are price segments, not body shapes, so they are left unmapped
BODY = {"SUV": "suv", "Sedan": "sedan", "MPV": "mpv", "Hatchback": "hatchback", "Van": "van",
        "Stationwagon": "estate", "Truck": "pickup", "Bus": "van"}
PLACEHOLDER_PRICE = 128105  # repeated on 4,625 unrelated listings, so it is a default, not a price


def download(raw):
    http_download(URL, raw / "cars_sgcarmart.csv")


def load(raw):
    d = pd.read_csv(raw / "cars_sgcarmart.csv", low_memory=False)
    price = pd.to_numeric(d["price"], errors="coerce")
    return pd.DataFrame({
        "listing_id": d["listing_id"].astype("string"),
        # the listing_date column is empty on every row; the repository was published in 2025
        "listing_date": pd.Timestamp("2025-01-01"), "date_basis": "upload_date",
        # placeholder adverts have brand "Used" and model "Car"
        "make": d["brand"].astype("string").mask(d["brand"].astype("string").eq("Used")),
        "model": d["model"], "version": d["title"],
        "year": pd.to_numeric(d["year"], errors="coerce"),
        "mileage_km": pd.to_numeric(d["mileage"], errors="coerce"),
        "engine_cc": pd.to_numeric(d["engine_capacity"], errors="coerce"),
        "fuel": d["fuel_type"].map(FUEL),
        "transmission": d["transmission"].map({"Manual": "manual", "Auto": "automatic"}),
        "body_type": d["vehicle_type"].map(BODY),
        "price": price.mask(price.eq(PLACEHOLDER_PRICE)), "currency": "SGD",
    })
