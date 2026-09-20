"""Otomoto (Poland) listings added 31 Jul – 31 Aug 2023 (Polish column names)."""
import pandas as pd

from .common import HP_TO_KW, kaggle_download

INFO = {"country": "PL", "price_type": "asking", "license": "Unknown",
        "url": "https://www.kaggle.com/datasets/krzysztofdogowski/used-cars-in-poland-many-parameters"}


def download(raw):
    kaggle_download("krzysztofdogowski/used-cars-in-poland-many-parameters", raw)


def load(raw):
    d = pd.read_csv(raw / "cleaned_combined_raw_results_full.csv", low_memory=False)
    return pd.DataFrame({
        "listing_id": d["Link"],
        "listing_date": pd.to_datetime(d["Czas dodania"], errors="coerce"), "date_basis": "listing",
        "is_new": d["Stan"].map({"Nowe": True, "Używane": False}),
        "make": d["Marka pojazdu"], "model": d["Model pojazdu"], "year": d["Rok produkcji"],
        "mileage_km": d["Przebieg"], "power_kw": d["Moc"] * HP_TO_KW,
        "engine_cc": d["Pojemność skokowa"],
        "fuel": d["Rodzaj paliwa"], "transmission": d["Skrzynia biegów"], "body_type": d["Typ nadwozia"],
        # "Firmy" = offered by a company; counted as dealer
        "seller_type": d["Oferta od"].map({"Osoby prywatnej": "private", "Firmy": "dealer"}),
        # these flags are only ever "Tak" (yes) or empty, so empty means "not stated"
        "had_accident": d["Bezwypadkowy"].map({"Tak": False}),  # accident-free: yes
        "is_damaged": d["Uszkodzony"].map({"Tak": True}),  # damaged: yes
        "n_owners": d[" Pierwszy właściciel (od nowości)"].map({"Tak": 1}),  # first owner since new: yes
        "price": d["Cena"], "currency": d["Waluta"],
    })
