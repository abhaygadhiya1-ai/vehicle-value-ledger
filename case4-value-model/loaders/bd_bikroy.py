"""Used-car adverts on Bikroy.com (Bangladesh). One snapshot, no listing date."""
import pandas as pd

from .common import http_download, mendeley_files
from .bd_aiub import fuel_from_list

INFO = {"country": "BD", "price_type": "asking", "license": "CC BY 4.0",
        "url": "https://data.mendeley.com/datasets/fmb4xmp4k5"}

DATASET = "fmb4xmp4k5"

BODY = {"Saloon": "sedan", "SUV / 4x4": "suv", "MPV": "mpv", "Hatchback": "hatchback",
        "Estate": "estate", "Convertible": "convertible", "Coupé/Sports": "coupe"}


def download(raw):
    for name, url in mendeley_files(DATASET):
        http_download(url, raw / name)


def load(raw):
    d = pd.read_csv(raw / "car_dataset.csv", low_memory=False)
    return pd.DataFrame({
        # no advert date; the Mendeley record was published on 2 Jan 2024
        "listing_date": pd.Timestamp("2024-01-02"), "date_basis": "upload_date",
        "make": d["brand"], "model": d["car_model"],
        # the year inside car_name disagrees with model_year on 73 of 1,209 rows, so the
        # explicit model_year column is used
        "year": d["model_year"],
        "mileage_km": d["kilometers_run"], "engine_cc": d["engine_capacity"],
        "fuel": fuel_from_list(d["fuel_type"]),
        "transmission": d["transmission"].map({"Manual": "manual", "Automatic": "automatic"}),
        "body_type": d["body_type"].map(BODY),
        "price": d["price"], "currency": "BDT",
    })
