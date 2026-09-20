"""ss.com (Latvia) used-car adverts, monthly snapshots 2019-2023 (2021 is Q1 only).

Five Mendeley records by the same author. The file format and the vocabulary both change over
the series: 2019-2020 are one .xlsx per year with a Month column, 2021-2023 are one .txt per
month; 2019 writes the categories as single letters and later years write them as Latvian words.
One combined map covers both, so every year is read the same way.
"""
import warnings

import pandas as pd

from .common import http_download, leading_number, mendeley_files

INFO = {"country": "LV", "price_type": "asking", "license": "CC BY 4.0",
        "url": "https://data.mendeley.com/datasets/6bhm5zbs7f"}

RECORDS = {"2019": "kyf948x63n", "2020": "hg38nn6c45", "2021": "rh9zh9ncnk",
           "2022": "mgdthphhy4", "2023": "6bhm5zbs7f"}
# 2021-2022 keep the English header, 2023 switched to Latvian
COLUMNS = {"Cena": "Price", "Marka": "Model", "Izlaiduma_gads": "First_registration_date",
           "Motors": "Motor", "Atr_karba": "Gearbox", "Nobraukums": "Mileage", "Krasa": "Color",
           "Virsbuves_tips": "Body_types", "Price_Eiro": "Price", "Issue_year": "First_registration_date",
           "Milage": "Mileage"}
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dec": 12}

# Motor is "1.9 dizelis" or "1.8 b": engine size, then the fuel as a word or a single letter.
FUEL = {"d": "diesel", "dizelis": "diesel",
        "b": "petrol", "benzins": "petrol",
        "g": "lpg", "gaze": "lpg", "b/g": "lpg", "benzins/gaze": "lpg",
        "h": "hybrid", "hibrids": "hybrid",
        "e": "electric", "elektro": "electric", "elektriskais": "electric"}
# the dataset's own dictionary lists "c" as both cabriolet and coupe. The 2023 files, which spell
# the words out, have 510 Kupeja to 122 Kabriolets; the coded files have 9,091 "c" to 2,420 "ca",
# the same 4:1 split, so "c" is coupe and "ca" is cabriolet.
BODY = {"u": "estate", "universals": "estate",
        "s": "sedan", "sedans": "sedan",
        "h": "hatchback", "hecbeks": "hatchback",
        "o": "suv", "apvidus": "suv",
        "mv": "mpv", "minivens": "mpv",
        "mb": "van", "mikroautobuss": "van",
        "p": "pickup", "pikaps": "pickup",
        "c": "coupe", "kupeja": "coupe",
        "ca": "convertible", "kabriolets": "convertible"}


def download(raw):
    for year, dataset in RECORDS.items():
        for name, url in mendeley_files(dataset):
            http_download(url, raw / year / name)


def _read(path):
    if path.suffix == ".xlsx":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = pd.read_excel(path)
        month = pd.to_numeric(d["Month"], errors="coerce")
    else:
        # the monthly files are Windows-encoded; the euro sign survives as a stray byte
        d = pd.read_csv(path, sep=";", encoding="latin-1", low_memory=False)
        month = MONTHS[path.stem[:3].lower()]
    d = d.rename(columns=COLUMNS)
    d["_month"] = month
    d["_year"] = int(path.parent.name)
    return d


def load(raw):
    d = pd.concat([_read(p) for p in sorted(raw.glob("*/*"))
                   if p.suffix in (".xlsx", ".txt") and "discription" not in p.name],
                  ignore_index=True)
    # "1.9 dizelis" / "1.8 b" -> engine litres and fuel; "Manuala 6 atrumi" / "m 5 s" -> first letter
    motor = d["Motor"].astype("string").str.strip()
    text = lambda s: s.astype("string").str.strip().str.lower()
    return pd.DataFrame({
        "listing_date": pd.to_datetime(dict(year=d["_year"], month=d["_month"], day=1), errors="coerce"),
        "date_basis": "listing_month",
        "make": d["Model"].astype("string").str.split(r"\s+", regex=True).str[0],
        "model": d["Model"].astype("string").str.split(r"\s+", regex=True).str[1:].str.join(" "),
        # "2006 februaris" -> the registration year
        "year": pd.to_numeric(d["First_registration_date"].astype("string")
                              .str.extract(r"(1[89]\d\d|20\d\d)")[0], errors="coerce"),
        "mileage_km": pd.to_numeric(d["Mileage"].astype("string")
                                    .str.replace(r"[^\d.]", "", regex=True), errors="coerce"),
        "engine_cc": leading_number(motor) * 1000,
        "fuel": text(motor.str.replace(r"^[\d.]+\s*", "", regex=True)).map(FUEL),
        "transmission": text(d["Gearbox"]).str[0].map({"m": "manual", "a": "automatic"}),
        "body_type": text(d["Body_types"]).map(BODY),
        "price": pd.to_numeric(d["Price"].astype("string").str.replace(r"[^\d.]", "", regex=True),
                               errors="coerce"),
        "currency": "EUR",
    })
