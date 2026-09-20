"""Marketcheck US used-car dealer inventory sample: asking price next to the car's original MSRP."""
import pandas as pd

from .common import MILES_TO_KM, http_download

INFO = {"country": "US", "price_type": "asking", "license": "Unknown (no license stated on the dataset)",
        "url": "https://huggingface.co/datasets/Marketcheck/us_used_car_inventory_data"}

URL = ("https://huggingface.co/datasets/Marketcheck/us_used_car_inventory_data/"
       "resolve/main/us_used_car_inventory_data.csv")

# neo_powertrain_type is checked first; rows it does not cover fall through to neo_fuel_type
POWERTRAIN = {"BEV": "electric", "PHEV": "plugin_hybrid", "EREV": "plugin_hybrid", "HEV": "hybrid",
              "FCEV": "other"}
FUEL = {
    "Unleaded": "petrol", "Premium Unleaded": "petrol", "Premium Unleaded / Unleaded": "petrol",
    "Unleaded / Premium Unleaded": "petrol",
    "Diesel": "diesel", "Biodiesel": "diesel",
    "E85 / Unleaded": "other", "E85 / Premium Unleaded": "other", "E85": "other", "Unleaded / E85": "other",
    "Hydrogen": "other",
    "Electric": "electric",
    # petrol/electric without a powertrain label: cannot tell a full hybrid from a plug-in
    "Electric / Unleaded": "hybrid", "Electric / Premium Unleaded": "hybrid",
}
BODY = {"SUV": "suv", "Sedan": "sedan", "Pickup": "pickup", "Hatchback": "hatchback", "Coupe": "coupe",
        "Convertible": "convertible", "Minivan": "mpv", "Mini Mpv": "mpv", "Wagon": "estate",
        "Cargo Van": "van", "Passenger Van": "van", "Van": "van", "Car Van": "van", "Combi": "van",
        "Chassis Cab": "other", "Cutaway": "other"}
TRANSMISSION = {"Automatic": "automatic", "CVT": "automatic", "Manual": "manual"}


def download(raw):
    http_download(URL, raw / "us_used_car_inventory_data.csv")


def frame(d):
    """Shared shape for the used and new inventory files (same 117 columns)."""
    # miles_indicator is per row: a few listings are recorded in kilometres already
    miles = pd.to_numeric(d["miles"], errors="coerce")
    return pd.DataFrame({
        "listing_id": d["id"].astype("string"),
        # scraped_at is when this price was recorded; first_scraped_at is when the advert first appeared
        "listing_date": pd.to_datetime(d["scraped_at"], format="ISO8601", utc=True).dt.tz_localize(None),
        "date_basis": "listing",
        "is_new": d["inventory_type"].map({"new": True, "used": False}),
        "make": d["neo_make"], "model": d["neo_model"], "version": d["neo_version"],
        "year": d["neo_year"],
        "mileage_km": miles.where(d["miles_indicator"].eq("KILOMETERS"), miles * MILES_TO_KM),
        "engine_cc": pd.to_numeric(d["neo_engine_displacement"], errors="coerce") * 1000,
        "fuel": d["neo_powertrain_type"].map(POWERTRAIN).fillna(d["neo_fuel_type"].map(FUEL)),
        "transmission": d["neo_transmission"].map(TRANSMISSION),
        "body_type": d["neo_body_type"].map(BODY),
        "seller_type": d["seller_type"],  # 'dealer' on every row: Marketcheck is dealer inventory
        # carfax_1_owner marks one-owner cars; 0 does not mean two owners, so it stays empty
        "n_owners": d["carfax_1_owner"].map({1: 1}),
        # carfax_clean_title is left out: 0 on 85% of rows, so it reads as "not checked", not "damaged"
        "days_on_market": d["dom"],
        "price": d["price"], "currency": d["currency_indicator"],
        "new_price": d["mc_msrp"],  # the car's original list price, not today's asking price
    })


def load(raw):
    return frame(pd.read_csv(raw / "us_used_car_inventory_data.csv", low_memory=False))
