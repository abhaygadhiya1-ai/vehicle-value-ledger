"""Otomoto (Poland) offers created 14 Mar – 23 Apr 2023."""
import pandas as pd

from .common import HP_TO_KW, kaggle_download, leading_number

INFO = {"country": "PL", "price_type": "asking", "license": "CC BY-SA 4.0",
        "url": "https://www.kaggle.com/datasets/szymoncyperski/car-sales-offers-from-otomotopl-2023"}


def download(raw):
    kaggle_download("szymoncyperski/car-sales-offers-from-otomotopl-2023", raw)


def load(raw):
    d = pd.read_csv(raw / "otomoto_offers_eng_23-04-2023.csv", sep=";", low_memory=False)
    return pd.DataFrame({
        "listing_id": d["id"].astype("string"),
        "listing_date": pd.to_datetime(d["offer_creation_date"], errors="coerce"),
        "date_basis": "listing",
        "is_new": d["state"].map({"New": True, "Used": False}),
        "make": d["vehicle_brand"], "model": d["vehicle_model"], "version": d["version"],
        "year": d["production_year"], "mileage_km": leading_number(d["mileage"]),
        "power_kw": leading_number(d["power"]) * HP_TO_KW,
        "engine_cc": leading_number(d["engine_displacement"]),
        "fuel": d["fuel_type"], "transmission": d["transmission"], "body_type": d["body_type"],
        "seller_type": d["seller_type"].map(
            {"Private person": "private", "Dealer": "dealer", "Authorized Dealer": "dealer"}),
        "price": leading_number(d["price"]), "currency": d["currency"],
    })
