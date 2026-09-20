"""OLX and Mobil123 (Indonesia) used-car adverts, 20-month collection ending 2025."""
import pandas as pd

from .common import http_download

INFO = {"country": "ID", "price_type": "asking", "license": "CC BY 4.0",
        "url": "https://zenodo.org/records/21792616"}

URL = "https://zenodo.org/api/records/21792616/files/dataset_raw_29747.csv/content"

FUEL = {"Bensin": "petrol", "Petrol": "petrol", "Diesel": "diesel", "Solar": "diesel",
        "Hybrid": "hybrid", "Listrik": "electric"}
BODY = {"SUV": "suv", "MPV": "mpv", "Hatchback": "hatchback", "Sedan": "sedan",
        "Compact & City Car": "hatchback", "Coupe": "coupe", "Van": "van", "Minibus": "van"}


def download(raw):
    http_download(URL, raw / "dataset_raw_29747.csv")


def load(raw):
    d = pd.read_csv(raw / "dataset_raw_29747.csv", low_memory=False)
    # "50.000-55.000 km": a band, so the midpoint of the two ends is used
    bands = (d["kilometer_raw"].astype("string").str.replace(".", "", regex=False)
             .str.extract(r"^(\d+)\s*-\s*(\d+)"))
    return pd.DataFrame({
        "listing_id": d["url"].astype("string"),
        "listing_date": pd.to_datetime(d["tanggal_raw"], format="%d-%m-%Y", errors="coerce"),
        "date_basis": "listing",
        "make": d["merek_raw"], "model": d["model_raw"], "version": d["varian_raw"],
        "year": pd.to_numeric(d["tahun"], errors="coerce"),
        "mileage_km": (pd.to_numeric(bands[0], errors="coerce")
                       + pd.to_numeric(bands[1], errors="coerce")) / 2,
        "engine_cc": pd.to_numeric(d["cc_raw"], errors="coerce"),
        "fuel": d["bb_raw"].map(FUEL),
        "transmission": d["transmisi_raw"].map({"Manual": "manual", "Automatic": "automatic"}),
        "body_type": d["bodi_raw"].map(BODY),
        # "499.000.000" rupiah
        "price": pd.to_numeric(d["harga_raw"].astype("string").str.replace(".", "", regex=False),
                               errors="coerce"),
        "currency": "IDR",
    })
