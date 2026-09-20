"""AutoScout24 listings in 8 European countries, snapshot 8 Nov 2025."""
import pandas as pd

from .common import kaggle_download

INFO = {"country": None, "price_type": "asking", "license": "MIT",
        "url": "https://www.kaggle.com/datasets/clkmuhammed/autoscout24-car-listings-dataset"}


def download(raw):
    kaggle_download("clkmuhammed/autoscout24-car-listings-dataset", raw)


def load(raw):
    cols = ["id", "price_currency", "price", "make", "model", "model_version", "mileage_km_raw",
            "registration_date", "production_year", "body_type", "power_kw", "transmission",
            "cylinders_volume_cc", "fuel_category", "electric_range_km", "is_new",
            "country_code", "seller_is_dealer", "nr_prev_owners"]
    d = pd.read_csv(raw / "autoscout24_dataset_20251108.csv", usecols=cols, low_memory=False)
    plug_in = (d["fuel_category"].isin(["Electric/Gasoline", "Electric/Diesel"])
               & (pd.to_numeric(d["electric_range_km"], errors="coerce") > 0))
    as_bool = {True: True, False: False, "True": True, "False": False}
    return pd.DataFrame({
        "country": d["country_code"], "listing_id": d["id"].astype("string"),
        "listing_date": pd.Timestamp("2025-11-08"), "date_basis": "file_date",
        "is_new": d["is_new"].map(as_bool),
        "make": d["make"], "model": d["model"], "version": d["model_version"],
        "year": d["production_year"],
        "reg_date": pd.to_datetime(d["registration_date"], errors="coerce"),
        "mileage_km": d["mileage_km_raw"],  # mileage_km is text ("10,500 km")
        "power_kw": d["power_kw"], "engine_cc": d["cylinders_volume_cc"],
        # hybrids with an electric range are treated as plug-in hybrids
        "fuel": d["fuel_category"].mask(plug_in, "plug-in hybrid"),
        "transmission": d["transmission"], "body_type": d["body_type"],
        "seller_type": d["seller_is_dealer"].map({True: "dealer", False: "private",
                                                   "True": "dealer", "False": "private"}),
        "n_owners": pd.to_numeric(d["nr_prev_owners"], errors="coerce"),
        # had_accident is not used: it is False on 118,379 rows and True on 3, so it is a default, not history
        "price": d["price"], "currency": d["price_currency"],
    })
