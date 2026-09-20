"""Download raw data for every source in loaders/, plus exchange rates, into data/raw/.

- Kaggle sources need the Kaggle CLI signed in (token at ~/.kaggle/access_token).
- Exchange rates: ECB monthly reference rates, and World Bank annual official rates for
  currencies the ECB does not publish. Both are open.

Folders that already have files are skipped, so the script is safe to re-run.
Usage: .venv/bin/python download_data.py            (all sources)
       .venv/bin/python download_data.py lv_2023     (one or more sources)
"""
import csv
import sys
from pathlib import Path

import requests

from loaders import SOURCES
from loaders.common import http_download

RAW = Path(__file__).parent / "data" / "raw"

ECB_CURRENCIES = ["USD", "GBP", "PLN", "SEK", "NOK", "DKK", "CZK", "HUF", "RON", "BGN", "CHF",
                  "NZD", "CAD", "AUD", "BRL", "SGD", "IDR", "ZAR", "TRY", "JPY"]
ECB_URL = ("https://data-api.ecb.europa.eu/service/data/EXR/M." + "+".join(ECB_CURRENCIES)
           + ".EUR.SP00.A?startPeriod=2005-01&format=csvdata")
# World Bank official exchange rate, LCU per USD, annual average (indicator PA.NUS.FCRF)
WORLD_BANK_CURRENCIES = {"MAR": "MAD", "JOR": "JOD", "EGY": "EGP", "BGD": "BDT", "UZB": "UZS", "NGA": "NGN"}
WORLD_BANK_URL = ("https://api.worldbank.org/v2/country/" + ";".join(WORLD_BANK_CURRENCIES)
                  + "/indicator/PA.NUS.FCRF?format=json&date=2005:2026&per_page=1000")


def download_fx():
    fx = RAW / "fx"
    if not (fx / "ecb_monthly.csv").exists():
        print("download ECB exchange rates")
        http_download(ECB_URL, fx / "ecb_monthly.csv")
    if not (fx / "worldbank_annual.csv").exists():
        print("download World Bank exchange rates")
        rows = requests.get(WORLD_BANK_URL, timeout=120).json()[1]
        with open(fx / "worldbank_annual.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["currency", "fx_year", "lcu_per_usd"])
            for r in rows:
                if r["value"] is not None:
                    w.writerow([WORLD_BANK_CURRENCIES[r["countryiso3code"]], r["date"], r["value"]])


def main(names):
    download_fx()
    for name in names or SOURCES:
        raw = RAW / name
        if raw.exists() and any(raw.iterdir()):
            print(f"skip {name} (already downloaded)")
            continue
        print(f"download {name}")
        raw.mkdir(parents=True, exist_ok=True)
        SOURCES[name].download(raw)


if __name__ == "__main__":
    main(sys.argv[1:])
