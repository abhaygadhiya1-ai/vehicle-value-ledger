"""JUCars-2024: used-car adverts in Jordan. One snapshot, no listing date."""
import pandas as pd

from .common import http_download, mendeley_files

INFO = {"country": "JO", "price_type": "asking", "license": "CC BY 4.0",
        "url": "https://data.mendeley.com/datasets/ddcz486x5t"}

DATASET = "ddcz486x5t"

FUEL = {"Gasoline": "petrol", "Diesel": "diesel", "Electric": "electric", "Hybrid": "hybrid",
        "Mild Hybrid": "hybrid", "Plug-in - Hybrid": "plugin_hybrid"}
BODY = {"Sedan": "sedan", "SUV": "suv", "HatchBack": "hatchback", "PickUp": "pickup",
        "Coupe": "coupe", "Bus - Van": "van", "Convertible": "convertible"}
# only the two unambiguous ends of the body-condition scale are read as a damage flag
DAMAGED = {"Poor (severe body damages)": True, "Excellent with no defects": False}


def download(raw):
    for name, url in mendeley_files(DATASET):
        http_download(url, raw / name)


def load(raw):
    d = pd.read_csv(raw / "cars_jordan.csv", low_memory=False)
    return pd.DataFrame({
        # no advert date in the data; the Mendeley record was published on 5 Mar 2026
        "listing_date": pd.Timestamp("2026-03-05"), "date_basis": "upload_date",
        "is_new": d["condition"].map({"New": True, "Used": False}),
        "make": d["make"], "model": d["model"], "year": d["year"],
        "mileage_km": d["mileage_km"],
        "fuel": d["fuel_type"].map(FUEL),
        "transmission": d["transmission"].map({"Manual": "manual", "Automatic": "automatic"}),
        "body_type": d["body_type"].map(BODY),
        # feat_paintcondition is not used: a repaint is not evidence of an accident
        "is_damaged": d["feat_body_condition"].map(DAMAGED),
        "price": d["price_value_JOD"], "currency": "JOD",
    })
