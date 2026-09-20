"""MUCars-2024: used-car adverts in Morocco. One snapshot, no listing date."""
import pandas as pd

from .common import http_download, mendeley_files

INFO = {"country": "MA", "price_type": "asking", "license": "CC BY 4.0",
        "url": "https://data.mendeley.com/datasets/vjrbcb2rrt"}

DATASET = "vjrbcb2rrt"

FUEL = {"Diesel": "diesel", "Petrol": "petrol", "Hybrid": "hybrid", "Electrique": "electric",
        "LPG": "lpg"}
CONDITION_NEW = {"New": True, "Excellent": False, "Very Good": False, "Good": False,
                 "Fair": False, "Damaged": False, "For Parts": False}


def download(raw):
    for name, url in mendeley_files(DATASET):
        http_download(url, raw / name)


def load(raw):
    d = pd.read_csv(raw / "cars_dataframe.csv", low_memory=False)
    # mileage is a band, "200 000 - 249 999": the midpoint of the two ends is used
    bands = d["Mileage"].astype("string").str.replace(r"\s", "", regex=True).str.extract(r"^(\d+)-(\d+)$")
    condition = d["Condition"].astype("string")
    return pd.DataFrame({
        # the adverts carry no date; the Mendeley record was published on 17 Dec 2024
        "listing_date": pd.Timestamp("2024-12-17"), "date_basis": "upload_date",
        "is_new": condition.map(CONDITION_NEW),
        "make": d["Brand"], "model": d["Model"], "year": d["Year"],
        "mileage_km": (pd.to_numeric(bands[0], errors="coerce")
                       + pd.to_numeric(bands[1], errors="coerce")) / 2,
        # "Fiscal Power" is Moroccan tax horsepower (CV), a tax band and not engine output,
        # so it is deliberately not read into power_kw
        "fuel": d["Fuel"].map(FUEL),
        "transmission": d["Gearbox"].map({"Manual": "manual", "Automatic": "automatic"}),
        "is_damaged": condition.isin(["Damaged", "For Parts"]).where(condition.notna()),
        "n_owners": d["First Owner"].map({"Yes": 1}),  # "No" only means more than one owner
        "price": d["Price"], "currency": "MAD",
    })
