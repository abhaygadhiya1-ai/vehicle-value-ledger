"""Swedish dealer listings, published 17 Mar 2021 – 15 Sep 2022."""
import pandas as pd

from .common import HP_TO_KW, kaggle_download

INFO = {"country": "SE", "price_type": "asking", "license": "Unknown",
        "url": "https://www.kaggle.com/datasets/jodancker/swedens-used-car-market"}


def download(raw):
    kaggle_download("jodancker/swedens-used-car-market", raw)


def load(raw):
    d = pd.read_csv(raw / "used_car_dataset.csv", low_memory=False)
    plug_in = d["fuel"].eq("hybrid") & (pd.to_numeric(d["electric_range_km"], errors="coerce") > 0)
    return pd.DataFrame({
        "listing_id": d["url"],
        "listing_date": pd.to_datetime(d["publication_datetime"], errors="coerce"), "date_basis": "listing",
        "make": d["manufacturer"], "model": d["model"], "version": d["note"], "year": d["entry_year"],
        "mileage_km": d["mileage_km"], "power_kw": pd.to_numeric(d["horse_power"], errors="coerce") * HP_TO_KW,
        "engine_cc": d["engine_size_ccm"],
        "fuel": d["fuel"].mask(plug_in, "plug-in hybrid"),
        "transmission": d["transmission"], "body_type": d["car_type"],
        "seller_type": "dealer",  # dataset description: cars advertised by car dealers
        "price": d["price_sek"], "currency": "SEK",
    })
