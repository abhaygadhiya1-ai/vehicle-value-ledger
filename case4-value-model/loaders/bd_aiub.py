"""Used-car adverts in Bangladesh, collected by AIUB. One snapshot, no listing date."""
import pandas as pd

from .common import http_download, mendeley_files

INFO = {"country": "BD", "price_type": "asking", "license": "CC BY 4.0",
        "url": "https://data.mendeley.com/datasets/8d38h82fyt"}

DATASET = "8d38h82fyt"


def fuel_from_list(series):
    """Bangladeshi adverts list every fuel the car can run on ("Petrol, Hybrid, Octane").

    The powertrain is read first, then a gas conversion, then the base fuel. Octane is the
    local name for high-octane petrol.
    """
    s = series.astype("string")
    out = pd.Series(pd.NA, index=s.index, dtype="string")
    for word, value in [("Petrol|Octane", "petrol"), ("Diesel", "diesel"), ("LPG", "lpg"),
                        ("CNG", "cng"), ("Hybrid", "hybrid")]:
        out = out.mask(s.str.contains(word, case=False, regex=True, na=False), value)
    return out


def load(raw):
    d = pd.read_csv(raw / "UsedCarInfo.csv", low_memory=False)
    number = lambda s: pd.to_numeric(s.astype("string").str.replace(r"[^\d]", "", regex=True),
                                     errors="coerce")
    return pd.DataFrame({
        # no advert date; the Mendeley record was published on 30 Jun 2026, which matches
        # car_age (a 1996 car is listed as 30 years old)
        "listing_date": pd.Timestamp("2026-06-30"), "date_basis": "upload_date",
        "make": d["brand"], "model": d["model"], "year": d["year_of_manufacture"],
        "age_years": d["car_age"],
        "mileage_km": number(d["kilometers_run"]),  # "89,000 km"
        "engine_cc": number(d["energy_capacity"]),  # "1,500 cc"
        "fuel": fuel_from_list(d["fuel_type"]),
        "transmission": d["transmission"].map({"Manual": "manual", "Automatic": "automatic"}),
        "price": number(d["price"]), "currency": "BDT",  # "Tk 530,000"
    })


def download(raw):
    for name, url in mendeley_files(DATASET):
        http_download(url, raw / name)
