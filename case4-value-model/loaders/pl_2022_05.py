"""Otomoto (Poland) listings collected in May 2022. Only 23 makes, few columns."""
import pandas as pd

from .common import kaggle_download

INFO = {"country": "PL", "price_type": "asking", "license": "CC0",
        "url": "https://www.kaggle.com/datasets/krzysztofdogowski/used-cars-poland-with-links-may-2022"}


def download(raw):
    kaggle_download("krzysztofdogowski/used-cars-poland-with-links-may-2022", raw)


def load(raw):
    d = pd.read_csv(raw / "Car_Prices_Poland_BS4_1_0.csv")
    return pd.DataFrame({
        "listing_id": d["link"],
        "listing_date": pd.Timestamp("2022-05-01"), "date_basis": "scrape_month",
        "make": d["mark"], "model": d["model"], "year": d["year"],
        "mileage_km": d["mileage"], "engine_cc": d["vol_engine"], "fuel": d["fuel"],
        "price": d["price"], "currency": "PLN",
    })
