"""DVM-CAR used-car adverts (UK), mostly 2018 plus 2017 and 2021. Non-commercial license."""
import pandas as pd

from .common import MILES_TO_KM, kaggle_download, leading_number

INFO = {"country": "GB", "price_type": "asking", "license": "CC BY-NC",
        "url": "https://deepvisualmarketing.github.io/"}


def download(raw):
    kaggle_download("mexwell/dvm-car", raw)


def load(raw):
    d = pd.read_csv(raw / "Ad_table.csv", dtype=str)
    return pd.DataFrame({
        "listing_id": d["Adv_ID"],
        "listing_date": pd.to_datetime(d["Adv_year"] + "-" + d["Adv_month"].str.zfill(2) + "-01",
                                       format="%Y-%m-%d", errors="coerce"),
        "date_basis": "listing_month",
        "make": d["Maker"], "model": d["Genmodel"], "year": d["Reg_year"],
        "mileage_km": pd.to_numeric(d["Runned_Miles"], errors="coerce") * MILES_TO_KM,
        "engine_cc": leading_number(d["Engin_size"]) * 1000,
        "fuel": d["Fuel_type"], "transmission": d["Gearbox"], "body_type": d["Bodytype"],
        "price": d["Price"], "currency": "GBP",
    })
