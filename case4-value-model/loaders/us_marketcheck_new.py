"""Marketcheck US new-car dealer inventory sample: asking price next to list price (MSRP)."""
import pandas as pd

from .common import http_download
from .us_marketcheck_used import frame

INFO = {"country": "US", "price_type": "asking", "license": "Unknown (no license stated on the dataset)",
        "url": "https://huggingface.co/datasets/Marketcheck/us_new_car_inventory_data"}

URL = ("https://huggingface.co/datasets/Marketcheck/us_new_car_inventory_data/"
       "resolve/main/us_new_car_inventory_data.csv")


def download(raw):
    http_download(URL, raw / "us_new_car_inventory_data.csv")


def load(raw):
    return frame(pd.read_csv(raw / "us_new_car_inventory_data.csv", low_memory=False))
