"""StandVirtual (Portugal) adverts, weekly snapshots Jun 2023 - Apr 2024."""
import urllib.parse

import pandas as pd
import requests

from .common import HP_TO_KW, http_download, leading_number

INFO = {"country": "PT", "price_type": "asking", "license": "None stated (no license file in the repo)",
        "url": "https://github.com/r-rodri/ImportedCars"}

REPO = "r-rodri/ImportedCars"

MONTHS = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
          "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
FUEL = {"Diesel": "diesel", "Gasolina": "petrol", "Eléctrico": "electric", "GPL": "lpg", "GNC": "cng",
        "Híbrido (Gasolina)": "hybrid", "Híbrido (Diesel)": "hybrid", "Híbrido Plug-In": "plugin_hybrid"}
# Portuguese market segments rather than strict body shapes
BODY = {"SUV / TT": "suv", "Carrinha": "estate", "Utilitário": "hatchback", "Citadino": "hatchback",
        "Pequeno citadino": "hatchback", "Sedan": "sedan", "Coupé": "coupe", "Monovolume": "mpv",
        "Cabrio": "convertible"}


def download(raw):
    tree = requests.get(f"https://api.github.com/repos/{REPO}/git/trees/main?recursive=1",
                        timeout=120).json()["tree"]
    for t in tree:
        if "StandVirtual/" in t["path"] and t["path"].endswith(".csv"):
            http_download(f"https://raw.githubusercontent.com/{REPO}/main/"
                          + urllib.parse.quote(t["path"]), raw / t["path"].rsplit("/", 1)[-1])


def _date(year, month, day):
    """Build a date from parts that may be missing, without tripping over the gaps."""
    parts = [x.astype("Float64").astype("Int64").astype("string") for x in (year, month, day)]
    return pd.to_datetime(parts[0] + "-" + parts[1] + "-" + parts[2], format="%Y-%m-%d",
                          errors="coerce")


def load(raw):
    parts = []
    for path in sorted(raw.glob("*.csv")):
        try:
            d = pd.read_csv(path, low_memory=False)
        except Exception:
            continue  # 4 of the 56 snapshots are empty or malformed in the repo
        if "Preco" in d.columns:
            # StandVirtualGeral_2023-06-26_222639.csv -> the day this snapshot was taken
            d["_snapshot"] = pd.to_datetime(path.stem.split("_")[1], errors="coerce")
            parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    text = lambda c: d[c].astype("string").str.strip()
    number = lambda c: pd.to_numeric(text(c).str.replace(r"[^\d]", "", regex=True), errors="coerce")
    reg_month = text("Mês de Registo").str.lower().map(MONTHS)
    advert = text("Data Anuncio").str.extract(r"^(\d{1,2})\s+(\S+)\s+(\d{4})$")
    advert_date = _date(pd.to_numeric(advert[2], errors="coerce"),
                        advert[1].str.lower().map(MONTHS),
                        pd.to_numeric(advert[0], errors="coerce"))
    return pd.DataFrame({
        "listing_id": text("ID Anuncio"),
        # "26 Junho 2023"
        # a quarter of the adverts have no readable date, so those fall back to the day the
        # snapshot was taken, and date_basis records which of the two each row uses
        "listing_date": advert_date.fillna(d["_snapshot"]),
        "date_basis": advert_date.notna().map({True: "listing", False: "file_date"}),
        "is_new": text("Condição").map({"Novos": True, "Usados": False}),
        "make": text("Marca"), "model": text("Modelo"), "version": text("Versão"),
        "year": pd.to_numeric(d["Ano"], errors="coerce"),
        "reg_date": _date(pd.to_numeric(d["Ano"], errors="coerce"), reg_month,
                          pd.Series(1, index=d.index)),
        "mileage_km": number("Quilómetros"),   # "193 584 km"
        # "1 499 cm3": take the leading number only, or the 3 of cm3 is read as a digit
        "engine_cc": pd.to_numeric(text("Cilindrada").str.extract(r"^([\d\s]+)")[0]
                                   .str.replace(r"\s", "", regex=True), errors="coerce"),
        "power_kw": leading_number(text("Potência")) * HP_TO_KW,  # "130 cv"
        "fuel": text("Combustível").map(FUEL),
        "transmission": text("Tipo de Caixa").map({"Manual": "manual", "Automática": "automatic"}),
        "body_type": text("Segmento").map(BODY),
        "seller_type": text("Anunciante").map({"Profissional": "dealer", "Particular": "private"}),
        "n_owners": pd.to_numeric(d["Registo(s)"], errors="coerce"),  # number of registrations
        "price": number("Preco"), "currency": "EUR",  # "12 990        EUR"
    })
