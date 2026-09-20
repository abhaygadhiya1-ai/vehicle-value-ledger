"""Cars45 (Nigeria) used-car adverts.

The published file has a second "Car Name.1" column that shows a different vehicle from the one
the row's price belongs to (the two agree on 1.2% of rows), so only "Car Name" is read.
"""
import pandas as pd

from .common import http_download

INFO = {"country": "NG", "price_type": "asking", "license": "Unknown (no license stated)",
        "url": "https://huggingface.co/datasets/Binaryy/cars-for-sale"}

URL = ("https://huggingface.co/datasets/Binaryy/cars-for-sale/resolve/main/"
       "data/train-00000-of-00001-b41d1d2b26fde43c.parquet")
FILE = "train-00000-of-00001-b41d1d2b26fde43c.parquet"


def download(raw):
    http_download(URL, raw / FILE)


def load(raw):
    d = pd.read_parquet(raw / FILE, columns=["Car Name", "Region", "Price", "Status", "Mileage"])
    # "Toyota Sequoia 2005 Gray" -> make, model, year, colour
    parts = d["Car Name"].astype("string").str.extract(r"^(\S+)\s+(.*?)\s+(\d{4})\b")
    number = lambda s: pd.to_numeric(s.astype("string").str.replace(r"[^\d]", "", regex=True),
                                     errors="coerce")
    return pd.DataFrame({
        # no advert date in the data; the dataset was published in 2023
        "listing_date": pd.Timestamp("2023-01-01"), "date_basis": "upload_date",
        "make": parts[0], "model": parts[1],
        "year": pd.to_numeric(parts[2], errors="coerce"),
        "mileage_km": number(d["Mileage"]),  # "322770 km"
        # Status is about import origin ("Nigerian Used" / "Foreign Used"), not condition,
        # so only "Brand New" is read as a new car
        "is_new": d["Status"].map({"Brand New": True, "Nigerian Used": False, "Foreign Used": False}),
        "price": number(d["Price"]), "currency": "NGN",  # "N 1,687,500"
    })
