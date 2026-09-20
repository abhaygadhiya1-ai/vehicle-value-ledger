"""Build the reference tables in data/reference/: new-car prices and used-car price indices.

These are not listings. They are the yardsticks the value model measures against:

- rdw_new_prices.parquet   Dutch official new-car catalogue price (catalogusprijs) by make,
                           model and first-registration year. Aggregated on RDW's own server,
                           because the source table holds 8.9m priced passenger cars.
- fipe_history.parquet     Brazil's FIPE table: the official monthly valuation of each model
                           and model year, including the 0 km (new) price.
- dvm_new_prices.parquet   UK new-car prices by model and year from DVM-CAR, both the entry
                           price and the spread across that year's trims.
- price_indices.parquet    Official second-hand car price indices, used to put prices from
                           different years on the same footing.
- new_car_price_indices.parquet  The same HICP family for NEW cars (CP07111). Kept in its own
                           file, not added to price_indices.parquet: `latvia_time.py` selects
                           its series with `str.contains("Eurostat")` and a second Eurostat
                           series in that file would silently break it.

Usage: .venv/bin/python build_reference.py [rdw|fipe|dvm|indices]
"""
import io
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

from build_unified import MAKE_ALIASES, norm_name, strip_make
from loaders.common import http_download

HERE = Path(__file__).parent


def align_names(make, model):
    """Normalise make and model exactly as build_unified.py does, so these tables join to the
    listings. Without this the reference says "mercedes-benz" and the listings say
    "mercedes benz", and nothing matches."""
    make_raw = norm_name(make)
    make = make_raw.replace(MAKE_ALIASES)
    model = norm_name(model)
    model = pd.Series([strip_make(m, k, r) for m, k, r in zip(model, make, make_raw)],
                      index=model.index, dtype="string")
    return make, model
RAW = HERE / "data" / "raw"
OUT = HERE / "data" / "reference"

# ---------- RDW: Dutch catalogue prices ----------

RDW_URL = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"
RDW_PAGE = 50_000


def build_rdw():
    """Group 8.9m priced Dutch passenger cars into make / model / registration-year averages."""
    year = "date_trunc_y(datum_eerste_toelating_dt)"
    params = {
        "$select": f"merk,handelsbenaming,{year} AS jaar,count(1) AS n,"
                   "median(catalogusprijs) AS price_median,avg(catalogusprijs) AS price_avg,"
                   "min(catalogusprijs) AS price_min,max(catalogusprijs) AS price_max",
        "$where": "voertuigsoort='Personenauto' AND catalogusprijs IS NOT NULL",
        "$group": f"merk,handelsbenaming,{year}",
        "$order": f"merk,handelsbenaming,{year}",
        "$limit": RDW_PAGE,
    }
    pages, offset = [], 0
    while True:
        r = requests.get(RDW_URL, params={**params, "$offset": offset}, timeout=600)
        r.raise_for_status()
        page = pd.DataFrame(r.json())
        pages.append(page)
        print(f"  rdw: {offset + len(page):,} groups", flush=True)
        if len(page) < RDW_PAGE:
            break
        offset += RDW_PAGE
    d = pd.concat(pages, ignore_index=True)
    make, model = align_names(d["merk"], d["handelsbenaming"])
    out = pd.DataFrame({
        "make": make,
        "model": model,
        "year": pd.to_datetime(d["jaar"]).dt.year,
        "n": pd.to_numeric(d["n"]),
        # the median is the one to use: a few model-years carry obvious entry errors
        # (a 1 euro car, a 200,000 euro Peugeot 208) that pull the average around
        "new_price_eur": pd.to_numeric(d["price_median"]),
        "new_price_avg_eur": pd.to_numeric(d["price_avg"]).round(2),
        "new_price_min_eur": pd.to_numeric(d["price_min"]),
        "new_price_max_eur": pd.to_numeric(d["price_max"]),
    })
    return out.sort_values(["make", "model", "year"], ignore_index=True)


# ---------- FIPE: Brazilian official valuations ----------

FIPE_URL = ("https://huggingface.co/datasets/alanwgt/fipex-veiculos-brasil/"
            "resolve/main/fipex-prices-latest-merged.parquet")
FIPE_FILE = RAW / "br_fipe" / "fipex-prices-latest-merged.parquet"


def build_fipe():
    """Reduce FIPE's full monthly history to passenger cars and the columns we use."""
    if not FIPE_FILE.exists():
        print("  fipe: downloading ~128 MB")
        http_download(FIPE_URL, FIPE_FILE)
    d = pd.read_parquet(FIPE_FILE)
    print(f"  fipe: {len(d):,} rows, vehicle types {d['tipo_veiculo'].value_counts().to_dict()}")
    cars = d[d["tipo_veiculo"].astype("string").str.lower().isin(["carro", "car", "1"])]
    if cars.empty:                       # the column may already hold only cars
        cars = d
    make, model = align_names(cars["nome_marca"], cars["nome_modelo"])
    out = pd.DataFrame({
        "make": make, "model": model,
        "fuel_raw": cars["nome_combustivel"],
        "model_year": pd.to_numeric(cars["ano_modelo"], errors="coerce"),
        "is_new": cars["zero_km"],
        "ref_year": pd.to_numeric(cars["ano_referencia"], errors="coerce"),
        "ref_month": pd.to_numeric(cars["mes_referencia"], errors="coerce"),
        "price_brl": pd.to_numeric(cars["valor_centavos"], errors="coerce") / 100,
    })
    # FIPE writes model year 32000 for a 0 km car
    out["model_year"] = out["model_year"].where(out["model_year"] < 3000)
    return out


# ---------- DVM-CAR: UK new-car prices ----------

def build_dvm():
    """UK entry price per model-year, plus the spread across that year's trims."""
    raw = RAW / "dvm"
    entry = pd.read_csv(raw / "Price_table.csv")
    trims = pd.read_csv(raw / "Trim_table.csv", low_memory=False)
    spread = (trims.groupby(["Genmodel_ID", "Year"])["Price"]
              .agg(trim_min="min", trim_median="median", trim_max="max", trims="size")
              .reset_index())
    d = entry.merge(spread, on=["Genmodel_ID", "Year"], how="left")
    make, model = align_names(d["Maker"], d["Genmodel"])
    return pd.DataFrame({
        "make": make, "model": model,
        "year": d["Year"],
        # the entry price is the cheapest trim on 6,139 of 6,333 model-years; the median trim
        # price is steadier when a model's trim line-up changes
        "entry_price_gbp": d["Entry_price"],
        "trim_min_gbp": d["trim_min"], "trim_median_gbp": d["trim_median"],
        "trim_max_gbp": d["trim_max"], "n_trims": d["trims"],
    }).sort_values(["make", "model", "year"], ignore_index=True)


# ---------- Official second-hand car price indices ----------

EUROSTAT = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx"
            "?format=JSON&coicop=CP07112&unit=I15")   # CP07112 = second-hand motor cars, 2015=100
ONS = "https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7e9/mm23/data"
INSEE = "https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/001763645"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CUSR0000SETA02"


def _eurostat_rows(url):
    """Unpack one Eurostat HICP series into geo / month / index_value."""
    d = requests.get(url, timeout=300).json()
    geos = {i: g for g, i in d["dimension"]["geo"]["category"]["index"].items()}
    times = {i: t for t, i in d["dimension"]["time"]["category"]["index"].items()}
    n_time = len(times)
    rows = []
    for flat, value in d["value"].items():
        geo, time = divmod(int(flat), n_time)
        rows.append((geos[geo], times[time], value))
    return pd.DataFrame(rows, columns=["geo", "month", "index_value"])


def _eurostat():
    out = _eurostat_rows(EUROSTAT)
    out["series"] = "Eurostat HICP, second-hand motor cars (CP07112)"
    out["base"] = "2015=100"
    out["source_url"] = "https://ec.europa.eu/eurostat/databrowser/product/page/prc_hicp_midx"
    return out


def _ons():
    d = requests.get(ONS, timeout=300, headers={"User-Agent": "case4-value-model"}).json()
    out = pd.DataFrame([{"geo": "UK",
                         "month": f"{m['year']}-{pd.Timestamp(m['month'][:3] + ' 2000').month:02d}",
                         "index_value": float(m["value"])}
                        for m in d["months"] if m["value"]])
    out["series"] = "ONS CPI 07.1.1B, second-hand cars (D7E9)"
    out["base"] = "2015=100"
    out["source_url"] = "https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7e9/mm23"
    return out


def _insee():
    text = requests.get(INSEE, timeout=300).content
    root = ET.fromstring(text)
    rows = [(o.get("TIME_PERIOD"), o.get("OBS_VALUE")) for o in root.iter()
            if o.get("TIME_PERIOD") and o.get("OBS_VALUE")]
    if not rows:
        return None
    out = pd.DataFrame(rows, columns=["month", "index_value"])
    out["index_value"] = pd.to_numeric(out["index_value"], errors="coerce")
    out["geo"] = "FR"
    out["series"] = "INSEE CPI 07.1.1.2, used cars (idbank 001763645, discontinued series)"
    out["base"] = "2015=100"
    out["source_url"] = "https://www.insee.fr/fr/statistiques/serie/001763645"
    return out.dropna(subset=["index_value"])


def _fred():
    d = pd.read_csv(io.StringIO(requests.get(FRED, timeout=300).text))
    d.columns = ["date", "index_value"]
    out = pd.DataFrame({"geo": "US",
                        "month": pd.to_datetime(d["date"]).dt.strftime("%Y-%m"),
                        "index_value": pd.to_numeric(d["index_value"], errors="coerce")})
    out["series"] = "US CPI, used cars and trucks, seasonally adjusted (CUSR0000SETA02)"
    out["base"] = "1982-84=100"
    out["source_url"] = "https://fred.stlouisfed.org/series/CUSR0000SETA02"
    return out.dropna(subset=["index_value"])


NEW_CARS = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx"
            "?format=JSON&coicop=CP07111&unit=I15")   # CP07111 = new motor cars, 2015=100


def _eurostat_new():
    out = _eurostat_rows(NEW_CARS)
    out["series"] = "Eurostat HICP, new motor cars (CP07111)"
    out["base"] = "2015=100"
    out["source_url"] = "https://ec.europa.eu/eurostat/databrowser/product/page/prc_hicp_midx"
    return out


def build_new_indices():
    d = _eurostat_new()
    print(f"  new indices: eurostat {len(d):,} rows, {d['geo'].nunique()} geo, "
          f"{d['month'].min()} -> {d['month'].max()}")
    d["date"] = pd.to_datetime(d["month"] + "-01", errors="coerce")
    return d.dropna(subset=["date"]).sort_values(["geo", "date"], ignore_index=True)


def build_indices():
    parts = []
    for name, fn in [("eurostat", _eurostat), ("ons", _ons), ("insee", _insee), ("fred", _fred)]:
        try:
            part = fn()
        except Exception as e:
            print(f"  indices: {name} failed ({type(e).__name__}: {e})")
            continue
        if part is None or part.empty:
            print(f"  indices: {name} returned nothing")
            continue
        print(f"  indices: {name} {len(part):,} rows, {part['geo'].nunique()} geo, "
              f"{part['month'].min()} -> {part['month'].max()}")
        parts.append(part)
    d = pd.concat(parts, ignore_index=True)
    d["date"] = pd.to_datetime(d["month"] + "-01", errors="coerce")
    return d.dropna(subset=["date"]).sort_values(["geo", "series", "date"], ignore_index=True)


BUILDERS = {"rdw": ("rdw_new_prices", build_rdw), "fipe": ("fipe_history", build_fipe),
            "dvm": ("dvm_new_prices", build_dvm), "indices": ("price_indices", build_indices),
            "newindices": ("new_car_price_indices", build_new_indices)}


def main(names):
    OUT.mkdir(parents=True, exist_ok=True)
    for name in names or BUILDERS:
        stem, fn = BUILDERS[name]
        print(f"{name}: building")
        d = fn()
        path = OUT / f"{stem}.parquet"
        d.to_parquet(path, index=False)
        print(f"{name}: wrote {len(d):,} rows to {path.name} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main(sys.argv[1:])
