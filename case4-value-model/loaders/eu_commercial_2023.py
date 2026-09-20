"""Used commercial vehicles (vans and trucks) advertised in 15 European countries, 2023.

One .xlsx per country, each with its own columns, currency and language, so the loader keeps the
fields every country shares: name, price, year and mileage. Currencies and the German net price
are taken from the per-country description.txt files shipped with the dataset.
"""
import warnings

import pandas as pd

from .common import http_download, mendeley_files

INFO = {"country": None, "price_type": "asking", "license": "CC BY 4.0",
        "url": "https://data.mendeley.com/datasets/kz6hh7832p"}

DATASET = "kz6hh7832p"

# currency per the country's own description.txt. DE quotes "Price Net" (ex-VAT); every other
# country quotes the advertised price.
# HU is the one exception to the description: it says EUR, but the values are Hungarian forint
# (an Opel Combo Cargo at 9,264,904 is about EUR 24,000, not EUR 9.2m), so HUF is used.
CURRENCY = {"AT": "EUR", "BG": "BGN", "CZ": "CZK", "DE": "EUR", "EE": "EUR", "ES": "EUR",
            "FI": "EUR", "FR": "EUR", "HU": "HUF", "IT": "EUR", "LV": "EUR", "NO": "NOK",
            "PL": "PLN", "RO": "EUR", "SE": "SEK"}
# LT is left out: its file has no header row, so its columns cannot be named with confidence.
PRICE_COL = {"CZ": "Price, Kč"}
# Estonia and Latvia keep the make in Name and the model in its own column
MODEL_COL = {"EE": "Model", "LV": "Model"}
MILEAGE_COL = {"BG": "Mileage\t", "ES": "Milage", "FR": "Milage"}
FUEL_COL = {"AT": "Fuel, Gearbox\t", "BG": "Fuel", "DE": "Fuel", "ES": "Fuel", "FI": "Fuel",
            "FR": "Fuel", "HU": "Fuel", "PL": "Fuel", "SE": "Fuel"}

FUEL = {
    "diesel": "diesel", "dízel": "diesel", "дизел": "diesel", "d": "diesel",
    "gasolina": "petrol", "bensiini": "petrol", "bensin": "petrol", "benzin": "petrol",
    "benzyna": "petrol", "essence": "petrol", "бензин": "petrol", "b": "petrol",
    "eléctrico": "electric", "sähkö": "electric", "el": "electric", "electrique": "electric",
    "elektromos": "electric", "elektryczny": "electric", "електрически": "electric", "e": "electric",
    "híbrido": "hybrid", "hybridi": "hybrid", "hybryda": "hybrid", "хибриден": "hybrid", "h": "hybrid",
    "lpg": "lpg", "benzin/gáz": "lpg", "benzyna+lpg": "lpg",
    "cng": "cng", "benzyna+cng": "cng",
    "otros": "other", "autres": "other", "bifuel": "other", "flexifuel": "other",
    # Swedish "Miljöbränsle/Hybrid" bundles biofuel with hybrid, so it is not a clean hybrid
    "miljöbränsle/hybrid": "other",
}
# Austria keeps fuel and gearbox in one free-text field ("Diesel, Schaltgetriebe, Gewährleistung")
AT_FUEL = {"Diesel": "diesel", "Benzin": "petrol", "Elektro": "electric", "Hybrid": "hybrid"}
AT_GEARBOX = {"Schaltgetriebe": "manual", "Automatik": "automatic"}


def download(raw):
    for name, url in mendeley_files(DATASET):
        http_download(url, raw / name)


def _country(raw, code):
    path = raw / f"{code}.xlsx"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the files carry stray styling openpyxl warns about
        d = pd.read_excel(path)
    name = d["Name"].astype("string").str.strip()
    if code in MODEL_COL:
        make, model = name, d[MODEL_COL[code]].astype("string").str.strip()
    else:
        # "Volkswagen Crafter 2.5 TDI Kasten": first word is the make, second the model
        make, model = name.str.split(r"\s+", regex=True).str[0], name.str.split(r"\s+", regex=True).str[1]
    # some files are mis-encoded, so Citroen's accented characters survive as stray letters
    make = (make.str.replace(r"(?i)^citro.{0,3}n$", "Citroen", regex=True)
            .str.replace(r"(?i)^vw$", "Volkswagen", regex=True))
    out = pd.DataFrame({
        "country": code,
        "make": make, "model": model, "version": name,
        # Bulgaria writes the year in Bulgarian ("април 2006 г.") and Estonia mixes in full dates
        "year": pd.to_numeric(d["Year"].astype("string").str.extract(r"(1[89]\d\d|20\d\d)")[0],
                              errors="coerce"),
        # Latvia's prices carry a stray byte where the euro sign should be ("24900\x88")
        "price": pd.to_numeric(d[PRICE_COL.get(code, "Price")].astype("string")
                               .str.replace(r"[^\d.]", "", regex=True), errors="coerce"),
        "currency": CURRENCY[code],
    })
    mileage = MILEAGE_COL.get(code, "Mileage")
    if mileage in d:
        out["mileage_km"] = pd.to_numeric(d[mileage], errors="coerce")
    if code == "AT":
        text = d[FUEL_COL[code]].astype("string")
        for word, value in AT_FUEL.items():
            out.loc[text.str.contains(word, na=False), "fuel"] = value
        for word, value in AT_GEARBOX.items():
            out.loc[text.str.contains(word, na=False), "transmission"] = value
    elif code in FUEL_COL:
        out["fuel"] = d[FUEL_COL[code]].astype("string").str.strip().str.lower().map(FUEL)
    return out


def load(raw):
    d = pd.concat([_country(raw, code) for code in CURRENCY], ignore_index=True)
    # the dataset description gives no per-row date, only that it was collected through 2023
    d["listing_date"] = pd.Timestamp("2023-07-01")
    d["date_basis"] = "unclear"
    return d
