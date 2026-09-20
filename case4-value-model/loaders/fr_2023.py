"""LaCentrale (France) listings. Scrape date unclear (see build report); age is exact."""
import pandas as pd

from .common import HP_TO_KW, kaggle_download

INFO = {"country": "FR", "price_type": "asking", "license": "Unknown",
        "url": "https://www.kaggle.com/datasets/bozzabb/data-of-second-hand-vehicles"}


def download(raw):
    kaggle_download("bozzabb/data-of-second-hand-vehicles", raw)


def load(raw):
    d = pd.read_csv(raw / "df3.csv", low_memory=False)
    return pd.DataFrame({
        # Kaggle upload date is 2023-06-16, but circulation date + circulation days gives
        # 2023-11-19 for every row, so the scrape date is unclear. Age uses circulation days.
        "listing_date": pd.Timestamp("2023-06-16"), "date_basis": "unclear",
        "make": d["model1"], "model": d["model2"], "version": d["version"],
        "year": pd.to_datetime(d["circuilation_date"], errors="coerce").dt.year,
        "age_years": d["circuilation_days"] / 365.25,
        "mileage_km": d["km"], "power_kw": d["HorseP"] * HP_TO_KW,
        "fuel": d["fuel"], "transmission": d["Gearbox_auto"].map({1: "automatic", 0: "manual"}),
        "n_owners": d["first_hand"].map({1: 1}),  # first hand = one owner; otherwise unknown
        "price": d["price"], "currency": "EUR",
    })
