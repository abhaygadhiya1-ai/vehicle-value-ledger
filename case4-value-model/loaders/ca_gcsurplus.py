"""GCSurplus: Government of Canada surplus asset sales, 2015-2025. Realised sale prices.

Most lots are not vehicles (furniture, tools, boats, aircraft, snowmobiles) and there is no
structured make or model: the loader reads "2017 Chevrolet Express 2500 ..." out of the free-text
lot description and keeps only single-item lots whose make is a passenger-vehicle brand.
The source carries no odometer reading anywhere, so mileage stays empty.
"""
import pandas as pd
import requests

from .common import http_download

INFO = {"country": "CA", "price_type": "auction", "license": "Open Government Licence - Canada",
        "url": "https://open.canada.ca/data/en/dataset/1a09c5c1-3554-4b70-9e53-6322a72ec7d4"}

PACKAGE = "1a09c5c1-3554-4b70-9e53-6322a72ec7d4"

# passenger cars, vans and pickups only: the auctions also sell ATVs (Polaris, Arctic Cat),
# aircraft (Cessna) and farm machinery (John Deere), which are not comparable vehicles
CAR_MAKES = {
    "acura", "audi", "bmw", "buick", "cadillac", "chevrolet", "chrysler", "dodge", "fiat", "ford",
    "gmc", "honda", "hyundai", "infiniti", "isuzu", "jaguar", "jeep", "kia", "land", "lexus",
    "lincoln", "mazda", "mercedes", "mercedes-benz", "mercury", "mini", "mitsubishi", "nissan",
    "oldsmobile", "plymouth", "pontiac", "porsche", "ram", "saab", "saturn", "smart", "subaru",
    "suzuki", "tesla", "toyota", "volkswagen", "volvo",
}


def download(raw):
    package = requests.get("https://open.canada.ca/data/api/3/action/package_show",
                           params={"id": PACKAGE}, timeout=120).json()["result"]
    for r in package["resources"]:
        if r["url"].endswith("-eng.zip"):
            http_download(r["url"], raw / r["url"].rsplit("/", 1)[-1])


def load(raw):
    d = pd.concat([pd.read_csv(p, low_memory=False) for p in sorted(raw.glob("*-eng.zip"))],
                  ignore_index=True)
    desc = d["LOT_DESC"].astype("string")
    # "2017 Chevrolet Express 2500 Cargo Extended - Involved in an Accident, Sold for Parts"
    parts = desc.str.extract(r"^\s*((?:19|20)\d{2})\s+([A-Za-z][A-Za-z\-]*)\s+(.*)$")
    quantity = d["LOT_ITEMS"].astype("string").str.extract(r"Quantity:\s*(\d+)")[0].astype("Float64")
    is_car = parts[1].str.lower().isin(CAR_MAKES) & quantity.eq(1)
    d, desc, parts = d[is_car], desc[is_car], parts[is_car]
    low = desc.str.lower()
    return pd.DataFrame({
        "listing_date": pd.to_datetime(d["CLOSING_DT"], errors="coerce"), "date_basis": "sale",
        "make": parts[1], "model": parts[2].str.split(r"\s+-\s+", regex=True).str[0],
        "version": parts[2],
        "year": pd.to_numeric(parts[0], errors="coerce"),
        "is_damaged": low.str.contains("sold for parts|salvage|not roadworthy", regex=True, na=False)
                      .where(desc.notna()),
        "had_accident": low.str.contains("involved in an accident", na=False).where(desc.notna()),
        "price": pd.to_numeric(d["SOLD_AMT"], errors="coerce"), "currency": "CAD",
    })
