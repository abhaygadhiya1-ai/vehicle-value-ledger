"""eBay Motors completed auctions, 2006 (replication data for Lewis 2011).

The published file is the paper's analysis matrix: 562 columns, most of them text-mining dummies.
Only the listing fields are read. Two limits worth knowing:
- the price is the highest bid on a completed auction. The reserve column is 1 on every row, so
  the file gives no usable way to tell which auctions actually met their reserve and sold.
- the file also carries an Edmunds used-car appraisal (bookvalue) on 62% of rows. That is a
  valuation of the used car, not a new-car list price, so it is deliberately not read into
  new_price; it is available in the raw file for a separate appraisal-versus-price analysis.
"""
import re

import pandas as pd
import requests

from .common import HEADERS, MILES_TO_KM, http_download

INFO = {"country": "US", "price_type": "auction", "license": "CC0 1.0",
        "url": "https://doi.org/10.7910/DVN/V5XSMF"}

DOI = "doi:10.7910/DVN/V5XSMF"
FILE = "ebaydatafinal.tab"
COLUMNS = ["maker", "name", "year", "miles", "enddate", "numbids", "biddy1"]


def download(raw):
    # the file id is not stable enough to hard-code, so look it up in the record
    meta = requests.get("https://dataverse.harvard.edu/api/datasets/:persistentId/",
                        params={"persistentId": DOI}, headers=HEADERS, timeout=120).json()
    file_id = next(f["dataFile"]["id"] for f in meta["data"]["latestVersion"]["files"]
                   if f["dataFile"]["filename"] == FILE)
    http_download(f"https://dataverse.harvard.edu/api/access/datafile/{file_id}", raw / FILE)


def load(raw):
    d = pd.read_csv(raw / "ebaydatafinal.tab", sep="\t", usecols=COLUMNS, low_memory=False)
    # only auctions that actually drew a bid
    d = d[d["biddy1"].notna() & d["numbids"].gt(0)].copy()
    maker = d["maker"].astype("string").str.strip().mask(lambda s: s.eq("."))  # 1,387 rows have no make
    name = d["name"].astype("string")
    # "1996 Green Chevrolet Camaro 2 Door Couple With T-Tops" -> the word after the make
    makes = "|".join(re.escape(m) for m in sorted(maker.dropna().unique()))
    model = name.str.extract(rf"(?i)\b(?:{makes})\s+([A-Za-z0-9\-]+)")[0]
    miles = pd.to_numeric(d["miles"], errors="coerce")
    return pd.DataFrame({
        # "Jul-16-06 20:30:00 PDT"
        "listing_date": pd.to_datetime(d["enddate"].astype("string").str[:9], format="%b-%d-%y",
                                       errors="coerce"),
        "date_basis": "sale",
        "make": maker, "model": model, "version": name,
        "year": pd.to_numeric(d["year"], errors="coerce"),
        # a few rows carry a negative odometer, which is left empty rather than dropping the sale
        "mileage_km": miles.where(miles.ge(0)) * MILES_TO_KM,
        "price": d["biddy1"], "currency": "USD",
    })
