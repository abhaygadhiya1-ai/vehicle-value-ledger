"""Hatla2ee (Egypt) used-car adverts. Published as train/validation/test splits, no listing date."""
import pandas as pd

from .common import http_download

INFO = {"country": "EG", "price_type": "asking", "license": "Unknown (the dataset card states 'unknown')",
        "url": "https://huggingface.co/datasets/mo-hug-me/used-car-listings-dataset-from-hatla2ee2026"}

BASE = ("https://huggingface.co/datasets/mo-hug-me/"
        "used-car-listings-dataset-from-hatla2ee2026/resolve/main")
# test_hidden is left out: its price column is empty on every row
SPLITS = ["train", "validation", "test"]

FUEL = {"Gas": "petrol", "Diesel": "diesel", "Natural Gas": "cng", "Electric": "electric",
        "Hybrid": "hybrid"}


def download(raw):
    for split in SPLITS + ["test_hidden"]:
        http_download(f"{BASE}/{split}.csv", raw / f"{split}.csv")


def load(raw):
    d = pd.concat([pd.read_csv(raw / f"{split}.csv", low_memory=False) for split in SPLITS],
                  ignore_index=True)
    number = lambda c: pd.to_numeric(d[c].astype("string").str.replace(r"[^\d]", "", regex=True),
                                     errors="coerce")
    return pd.DataFrame({
        # the adverts carry no date; the dataset is named for 2026 and was published that year
        "listing_date": pd.Timestamp("2026-01-01"), "date_basis": "upload_date",
        "make": d["brand"], "model": d["model"], "year": pd.to_numeric(d["year"], errors="coerce"),
        "mileage_km": number("km"),      # "122,000 KM"
        "fuel": d["fuel"].map(FUEL),     # "Gas" is the local name for petrol
        "transmission": d["transmission"].map({"Manual": "manual", "Automatic": "automatic"}),
        "price": number("price"), "currency": "EGP",  # "530,000 EGP"
    })
