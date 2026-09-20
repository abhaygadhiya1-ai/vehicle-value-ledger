"""AutoScout24 Germany offers, uploaded 24 Jun 2023 (no listing date in the data)."""
import pandas as pd

from .common import kaggle_download

INFO = {"country": "DE", "price_type": "asking", "license": "CC0",
        "url": "https://www.kaggle.com/datasets/wspirat/germany-used-cars-dataset-2023"}


def download(raw):
    kaggle_download("wspirat/germany-used-cars-dataset-2023", raw)


def load(raw):
    d = pd.read_csv(raw / "data.csv", low_memory=False)
    return pd.DataFrame({
        "listing_date": pd.Timestamp("2023-06-24"), "date_basis": "upload_date",
        "make": d["brand"], "model": d["model"], "version": d["offer_description"],
        "year": d["year"],
        "reg_date": pd.to_datetime(d["registration_date"], format="%m/%Y", errors="coerce"),
        "mileage_km": d["mileage_in_km"], "power_kw": d["power_kw"],
        "fuel": d["fuel_type"], "transmission": d["transmission_type"],
        "price": d["price_in_euro"], "currency": "EUR",
    })
