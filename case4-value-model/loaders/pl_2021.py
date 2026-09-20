"""Otomoto (Poland) car ads, published 26 Mar – 5 May 2021."""
import pandas as pd

from .common import HP_TO_KW, kaggle_download

INFO = {"country": "PL", "price_type": "asking", "license": "CC0",
        "url": "https://www.kaggle.com/datasets/bartoszpieniak/poland-cars-for-sale-dataset"}


def download(raw):
    kaggle_download("bartoszpieniak/poland-cars-for-sale-dataset", raw)


def load(raw):
    d = pd.read_csv(raw / "Car_sale_ads.csv", low_memory=False)
    return pd.DataFrame({
        "listing_id": d["Index"].astype("string"),
        "listing_date": pd.to_datetime(d["Offer_publication_date"], format="%d/%m/%Y", errors="coerce"),
        "date_basis": "listing",
        "is_new": d["Condition"].map({"New": True, "Used": False}),
        "make": d["Vehicle_brand"], "model": d["Vehicle_model"], "version": d["Vehicle_version"],
        "year": d["Production_year"],
        "reg_date": pd.to_datetime(d["First_registration_date"], format="%d/%m/%Y", errors="coerce"),
        "mileage_km": d["Mileage_km"], "power_kw": d["Power_HP"] * HP_TO_KW,
        "engine_cc": d["Displacement_cm3"],
        "fuel": d["Fuel_type"], "transmission": d["Transmission"], "body_type": d["Type"],
        "price": d["Price"], "currency": d["Currency"],
    })
