"""Avtoelon.uz (Uzbekistan) used-car adverts, scraped Mar 2026.

The dataset card states the data is "for research and educational purposes only", which is not
an open licence; check before using it outside the analysis.
"""
import pandas as pd

from .common import http_download, leading_number

INFO = {"country": "UZ", "price_type": "asking",
        "license": "For research and educational purposes only (not an open licence)",
        "url": "https://huggingface.co/datasets/Mehriddin1997/uzbekistan-car-prices"}

URL = ("https://huggingface.co/datasets/Mehriddin1997/uzbekistan-car-prices/"
       "resolve/main/avtoelon-car-prices-raw.csv")

FUEL = {"benzin": "petrol", "gaz-benzin": "lpg", "dizel": "diesel", "elektro": "electric",
        "gibrid": "hybrid", "metan": "cng", "propan": "lpg"}
TRANSMISSION = {"Mexanika": "manual", "Avtomat": "automatic", "Variator": "automatic",
                "Robot": "automatic"}
BODY = {"Sedan": "sedan", "Hatchback": "hatchback", "Krossover": "suv", "Yo‘ltanlamas": "suv",
        "Pikup": "pickup", "Miniven": "mpv", "Universal": "estate"}


def download(raw):
    http_download(URL, raw / "avtoelon-car-prices-raw.csv")


def load(raw):
    d = pd.read_csv(raw / "avtoelon-car-prices-raw.csv", low_memory=False)
    engine = d["engine"].astype("string")  # "1.6 (Gaz-benzin)"
    return pd.DataFrame({
        "listing_id": d["advert_id"].astype("string"),
        "listing_date": pd.to_datetime(d["scraped_at"], errors="coerce"), "date_basis": "scrape_month",
        "make": d["brand"], "model": d["model"],
        "year": pd.to_numeric(d["year"], errors="coerce"),
        "mileage_km": pd.to_numeric(d["param_yurgani"].astype("string")
                                    .str.replace(r"[^\d]", "", regex=True), errors="coerce"),
        "engine_cc": leading_number(engine) * 1000,
        "fuel": engine.str.extract(r"\(([^)]+)\)")[0].str.lower().map(FUEL),
        "transmission": d["transmission"].map(TRANSMISSION),
        "body_type": d["body"].map(BODY),
        "price": pd.to_numeric(d["price_value"], errors="coerce"),
        "currency": d["price_currency"],
    })
