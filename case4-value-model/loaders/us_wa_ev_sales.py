"""Washington State DOL electric vehicle title/registration activity: recorded sale prices."""
import pandas as pd

from .common import MILES_TO_KM, http_download

INFO = {"country": "US", "price_type": "sale", "license": "Open Data Commons Attribution License",
        "url": "https://data.wa.gov/d/rpr4-cgyd"}

FIELDS = ["dol_vehicle_id", "model_year", "make", "model", "electric_vehicle_type",
          "vehicle_primary_use", "odometer_reading", "odometer_code", "new_or_used_vehicle",
          "sale_price", "date_of_vehicle_sale", "transaction_type", "transaction_date"]
FUEL = {"Battery Electric Vehicle (BEV)": "electric", "Plug-in Hybrid Electric Vehicle (PHEV)": "plugin_hybrid"}


def download(raw):
    http_download("https://data.wa.gov/resource/rpr4-cgyd.csv", raw / "sales.csv", params={
        "$select": ",".join(FIELDS), "$where": "sale_price > 0", "$limit": 500_000,
    })


def load(raw):
    d = pd.read_csv(raw / "sales.csv", low_memory=False)
    # odometer_reading is only recorded as "Actual Mileage"; other codes (no reading, exempt, etc.) are not a real mileage
    mileage_mi = pd.to_numeric(d["odometer_reading"], errors="coerce").where(d["odometer_code"] == "Actual Mileage")
    # dol_vehicle_id is per-vehicle (a car can be sold more than once); pair it with the sale date and a
    # per-day counter to get a unique id per transaction
    txn_key = d["dol_vehicle_id"].astype("string") + "_" + d["date_of_vehicle_sale"].astype("string")
    return pd.DataFrame({
        "listing_id": txn_key + "_" + txn_key.groupby(txn_key).cumcount().astype("string"),
        "listing_date": pd.to_datetime(d["date_of_vehicle_sale"], errors="coerce"),
        "date_basis": "sale",
        "is_new": d["new_or_used_vehicle"].map({"New": True, "Used": False}),
        "make": d["make"], "model": d["model"],
        "year": d["model_year"],
        "mileage_km": mileage_mi * MILES_TO_KM,
        "fuel": d["electric_vehicle_type"].map(FUEL),
        "price": d["sale_price"], "currency": "USD",
    })
