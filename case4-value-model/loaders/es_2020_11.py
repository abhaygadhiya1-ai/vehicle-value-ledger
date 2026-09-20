"""Milanuncios (Spain) used-car adverts, scraped 3-5 Nov 2020."""
import pandas as pd

from .common import HP_TO_KW, http_download

INFO = {"country": "ES", "price_type": "asking", "license": "CC BY 4.0",
        "url": "https://zenodo.org/records/4252636"}

URL = "https://zenodo.org/records/4252636/files/dataset.csv?download=1"

TRANSMISSION = {"Manual": "manual", "Automático": "automatic"}


def download(raw):
    http_download(URL, raw / "dataset.csv")


def load(raw):
    d = pd.read_csv(raw / "dataset.csv", low_memory=False)
    # the file is several scrape chunks concatenated, so the header line repeats inside it
    d = d[d["ad_id"].astype("string").ne("ad_id")].copy()
    # car_engine_type and car_door_num are identical and hold whichever attribute the advert
    # listed first (gearbox, doors or power), so only the gearbox values are usable
    attr = d["car_engine_type"].astype("string")
    power = d["car_power"].astype("string")
    km = d["car_km"].astype("string")
    return pd.DataFrame({
        "listing_id": d["ad_id"].astype("string"),
        # ts is the scrape timestamp; the advert's own publication date is only given as
        # relative text ("3 dias"), so the scrape is the date we can stand behind
        "listing_date": pd.to_datetime(d["ts"], errors="coerce"), "date_basis": "scrape_month",
        # ad_title is "MAKE - MODEL" on 97% of rows
        "make": d["ad_title"].astype("string").str.split(" - ").str[0],
        "model": d["ad_title"].astype("string").str.split(" - ").str[1],
        "year": d["car_year"],
        # "185.000 kms": Spanish thousands separator
        "mileage_km": pd.to_numeric(km.where(km.str.match(r"^[\d.]+\s*kms$", na=False))
                                    .str.replace(".", "", regex=False).str.extract(r"(\d+)")[0],
                                    errors="coerce"),
        "power_kw": pd.to_numeric(power.where(power.str.match(r"^\d+\s*CV$", na=False))
                                  .str.extract(r"(\d+)")[0], errors="coerce") * HP_TO_KW,
        # fuel is not recoverable: the free-text description mentions it on only 22% of rows
        "transmission": attr.map(TRANSMISSION),
        "seller_type": d["advertizer_type"].map({"Profesional": "dealer", "Particular": "private"}),
        "price": pd.to_numeric(d["car_price"], errors="coerce"), "currency": "EUR",
    })
