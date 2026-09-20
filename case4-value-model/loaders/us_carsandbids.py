"""Cars & Bids completed online auctions (US, enthusiast cars), Aug 2021 onwards. Sold prices."""
import pandas as pd

from .common import MILES_TO_KM, http_download

INFO = {"country": "US", "price_type": "auction", "license": "None stated (no license file in the repo)",
        "url": "https://github.com/MattSnively/CarsAndBidsData"}

URL = "https://raw.githubusercontent.com/MattSnively/CarsAndBidsData/main/data/carsandbids_master.csv"

BODY = {"Coupe": "coupe", "Sedan": "sedan", "SUV/Crossover": "suv", "Convertible": "convertible",
        "Truck": "pickup", "Wagon": "estate", "Hatchback": "hatchback", "Van/Minivan": "van"}
# a US title brand meaning the car was written off at some point
DAMAGED_WORDS = "salvage|salvaged|rebuilt|flood|totaled|reconstructed"


def download(raw):
    http_download(URL, raw / "carsandbids_master.csv")


def load(raw):
    d = pd.read_csv(raw / "carsandbids_master.csv", low_memory=False)
    # only completed sales: no_sale and canceled auctions have no sale_price at all
    d = d[d["sale_price"].notna()].copy()
    title = d["title_status"].astype("string").str.strip().str.lower()
    gearbox = d["transmission"].astype("string").str.lower()
    seller = d["seller_type"].astype("string")
    return pd.DataFrame({
        "listing_id": d["url"],
        "listing_date": pd.to_datetime(d["end_date"], errors="coerce"), "date_basis": "sale",
        "make": d["make"], "model": d["model"], "year": d["year"],
        "mileage_km": pd.to_numeric(d["mileage"], errors="coerce") * MILES_TO_KM,
        # transmission is written as "Manual (6-Speed)" / "Automatic (CVT)"
        "transmission": pd.Series(
            gearbox.str.startswith("manual").map({True: "manual"})
            .fillna(gearbox.str.startswith("automatic").map({True: "automatic"})), index=d.index),
        "body_type": d["body_style"].map(BODY),
        # free text like "Dealer\n($80 Temporary Tag)" or "Certified Seller (Private Party)"
        "seller_type": pd.Series(
            seller.str.contains("Private Party", na=False).map({True: "private"})
            .fillna(seller.str.contains("Dealer", na=False).map({True: "dealer"})), index=d.index),
        # a clean title means no write-off brand; anything outside these two groups stays empty
        "is_damaged": pd.Series(
            title.str.startswith(("clean", "clear")).map({True: False})
            .fillna(title.str.contains(DAMAGED_WORDS, regex=True, na=False).map({True: True})), index=d.index),
        "price": d["sale_price"], "currency": "USD",
    })
