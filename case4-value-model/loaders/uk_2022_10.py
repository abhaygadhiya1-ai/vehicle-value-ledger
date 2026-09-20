"""UK used-car adverts, October 2022 (one snapshot)."""
import numpy as np
import pandas as pd

from .common import BHP_TO_KW, HP_TO_KW, MILES_TO_KM, kaggle_download

INFO = {"country": "GB", "price_type": "asking", "license": "CC0",
        "url": "https://www.kaggle.com/datasets/guanhaopeng/uk-used-car-market"}


def download(raw):
    kaggle_download("guanhaopeng/uk-used-car-market", raw)


def load(raw):
    cols = ["make", "model", "variant", "car_price", "car_seller", "year", "body_type", "miles",
            "engine_vol", "engine_size", "engine_size_unit", "transmission", "feul_type", "brand_new",
            "num_owner"]
    d = pd.read_csv(raw / "all_car_adverts.csv", usecols=cols, low_memory=False)
    seller = np.where(d["car_seller"].eq("Private seller"), "private",
                      np.where(d["car_seller"].notna(), "dealer", None))
    out = pd.DataFrame({
        "listing_date": pd.Timestamp("2022-10-01"), "date_basis": "scrape_month",
        "is_new": pd.to_numeric(d["brand_new"], errors="coerce").map({1: True, 0: False}),
        "make": d["make"], "model": d["model"], "version": d["variant"],
        "year": pd.to_numeric(d["year"], errors="coerce"),  # text here means shifted columns -> dropped
        "mileage_km": pd.to_numeric(d["miles"], errors="coerce") * MILES_TO_KM,
        "power_kw": pd.to_numeric(d["engine_size"], errors="coerce")
                    * d["engine_size_unit"].map({"ps": HP_TO_KW, "bhp": BHP_TO_KW}),
        "engine_cc": pd.to_numeric(d["engine_vol"], errors="coerce") * 1000,
        "fuel": d["feul_type"], "transmission": d["transmission"], "body_type": d["body_type"],
        "seller_type": seller,
        "n_owners": pd.to_numeric(d["num_owner"], errors="coerce"),
        "price": d["car_price"], "currency": "GBP",
    })
    # The raw file lists many adverts two or three times under different variant labels, identical
    # in every other field down to the mileage (audit, 2026-09-17: 360,988 of 818,456 raw rows).
    # There is no advert id, so keep one row per advert: the first variant label seen.
    return out.drop_duplicates(subset=[c for c in out.columns if c != "version"])
