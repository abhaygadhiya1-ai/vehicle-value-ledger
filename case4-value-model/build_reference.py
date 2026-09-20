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
- nl_transfer_hazard.parquet  How often a Dutch car of each age changes keeper, from RDW's
                           own register: the base hazard of the readiness engine.
- new_car_price_indices.parquet  The same HICP family for NEW cars (CP07111). Kept in its own
                           file, not added to price_indices.parquet: `latvia_time.py` selects
                           its series with `str.contains("Eurostat")` and a second Eurostat
                           series in that file would silently break it.

Usage: .venv/bin/python build_reference.py [rdw|fipe|dvm|indices|newindices|nlhazard|nlmake]
"""
import io
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

from build_unified import MAKE_ALIASES, STELLANTIS, norm_name, strip_make
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


# ---------- RDW: how often a Dutch car changes hands, by age ----------

STELLANTIS_NL = None  # filled by build_nl_hazard from RDW's own spelling of each make


def rdw_group(select, where, group, limit=5_000):
    """One server-side aggregation against the RDW register. Nothing is downloaded row by row:
    the table holds 10.8m passenger cars and the machine has no room for them."""
    r = requests.get(RDW_URL, params={"$select": select, "$where": where, "$group": group,
                                      "$limit": limit}, timeout=900)
    r.raise_for_status()
    return pd.DataFrame(r.json())


def build_nl_hazard():
    """The base hazard of layer 1: the share of Dutch cars of each age that changed keeper in the
    last twelve months.

    RDW's open register carries, for every car, the date it was first admitted and the date the
    *current* keeper took it on. So the numerator and the denominator come out of the same
    official file, at single years of age, and neither is modelled.

    Two cuts of the population, because both matter and they differ:

      * `all`      - every car on the road, imports included. An imported used car necessarily
                     registers a keeper change when it arrives, and imports are over a third of
                     the parc at ages four to six, so this cut runs hot at exactly the ages the
                     engine cares about.
      * `domestic` - cars first put on Dutch plates when new. This is the population that behaves
                     like a lease book, and it is the one the engine uses.

    A first registration is not a keeper change, so it is excluded; without that, age 0 reads
    100% by construction.
    """
    global STELLANTIS_NL
    live = ("voertuigsoort='Personenauto' AND export_indicator='Nee' "
            "AND tenaamstellen_mogelijk='Ja' AND datum_eerste_toelating_dt IS NOT NULL")
    born_here = ("date_extract_y(datum_eerste_tenaamstelling_in_nederland_dt) "
                 "= date_extract_y(datum_eerste_toelating_dt)")

    latest = rdw_group("max(datum_tenaamstelling_dt) AS m", live, "")["m"].iloc[0]
    end = pd.Timestamp(latest).normalize().replace(day=1)

    # Two windows, not one. The register only ever shows the *current* keeper, so the twelve
    # months before last are seen only through cars that have not moved since - censored, and
    # `readiness_base.py` undoes that. It is worth the trouble: one window cannot tell an age
    # effect from a cohort effect, and two can.
    windows = {"latest": (end - pd.DateOffset(months=12), end),
               "previous": (end - pd.DateOffset(months=24), end - pd.DateOffset(months=12))}

    def moved_in(start, stop):
        return (f"datum_tenaamstelling_dt >= '{start:%Y-%m-%d}T00:00:00.000' "
                f"AND datum_tenaamstelling_dt < '{stop:%Y-%m-%d}T00:00:00.000' "
                "AND datum_tenaamstelling_dt > datum_eerste_tenaamstelling_in_nederland_dt")

    print(f"  nlhazard: windows {windows['previous'][0]:%Y-%m} / "
          f"{windows['latest'][0]:%Y-%m} / {end:%Y-%m}", flush=True)

    makes = rdw_group("merk,count(1) AS n", live, "merk", limit=50_000)
    norm = norm_name(makes["merk"]).replace(MAKE_ALIASES)
    STELLANTIS_NL = sorted(makes.loc[norm.isin(STELLANTIS), "merk"].dropna().unique())
    quoted = ",".join("'" + m.replace("'", "''") + "'" for m in STELLANTIS_NL)
    print(f"  nlhazard: {len(STELLANTIS_NL)} Stellantis spellings in RDW", flush=True)

    year = "date_extract_y(datum_eerste_toelating_dt)"
    # `all_ever` drops the "still on the road" filter. Its parc is not a fleet, so it is no use
    # as a hazard, but its numerator is the right one to hold against a published count of sales:
    # a car sold in November and exported in March was still a sale.
    ever = "voertuigsoort='Personenauto' AND datum_eerste_toelating_dt IS NOT NULL"

    rows = []
    for population, pop_where in (("all", live), ("domestic", f"{live} AND {born_here}"),
                                  ("all_ever", ever)):
        for brands, brand_where in (("all", pop_where),
                                    ("stellantis", f"{pop_where} AND merk IN ({quoted})")):
            parc = rdw_group(f"{year} AS y,count(1) AS n", brand_where, "y", limit=200)
            for window, (start, stop) in windows.items():
                movers = rdw_group(f"{year} AS y,count(1) AS n",
                                   f"{brand_where} AND {moved_in(start, stop)}", "y", limit=200)
                m = dict(zip(movers["y"].astype(int), movers["n"].astype(int)))
                for y, n in zip(parc["y"].astype(int), parc["n"].astype(int)):
                    rows.append({"population": population, "brands": brands, "window": window,
                                 "window_start": start, "window_end": stop, "reg_year": y,
                                 "age_years": end.year - y, "parc": n, "movers": m.get(y, 0)})
            print(f"  nlhazard: {population}/{brands} {parc['n'].astype(int).sum():,} cars",
                  flush=True)

    # the official new price of the cars of each vintage that are actually still on the road.
    # `readiness_value.py` needs it, and taking it here keeps that analysis offline.
    priced = rdw_group(f"{year} AS y,median(catalogusprijs) AS med,count(1) AS n",
                       f"{live} AND {born_here} AND catalogusprijs IS NOT NULL "
                       "AND catalogusprijs > 2000", "y", limit=200)
    newp = dict(zip(priced["y"].astype(int), priced["med"].astype(float)))

    d = pd.DataFrame(rows)
    d["rate"] = d["movers"] / d["parc"]
    d["new_price_eur"] = d["reg_year"].map(newp)
    return d.sort_values(["population", "brands", "window", "age_years"], ignore_index=True)


def build_nl_by_make():
    """The same keeper-change rate, but split by make within each registration year.

    Layer 1 says a five-year-old car is the likeliest to move. That is an average, and an average
    over makes is not a prediction about a car: this table is what the spread inside one age looks
    like, which is the whole reason a model is needed on top of the curve.
    """
    live = ("voertuigsoort='Personenauto' AND export_indicator='Nee' "
            "AND tenaamstellen_mogelijk='Ja' AND datum_eerste_toelating_dt IS NOT NULL")
    born_here = ("date_extract_y(datum_eerste_tenaamstelling_in_nederland_dt) "
                 "= date_extract_y(datum_eerste_toelating_dt)")
    latest = rdw_group("max(datum_tenaamstelling_dt) AS m", live, "")["m"].iloc[0]
    end = pd.Timestamp(latest).normalize().replace(day=1)
    start = end - pd.DateOffset(months=12)
    moved = (f"datum_tenaamstelling_dt >= '{start:%Y-%m-%d}T00:00:00.000' "
             f"AND datum_tenaamstelling_dt < '{end:%Y-%m-%d}T00:00:00.000' "
             "AND datum_tenaamstelling_dt > datum_eerste_tenaamstelling_in_nederland_dt")
    year = "date_extract_y(datum_eerste_toelating_dt)"
    where = f"{live} AND {born_here} AND {year} >= {end.year - 20}"

    parc = rdw_group(f"merk,{year} AS y,count(1) AS n", where, f"merk,{year}", limit=5000)
    mov = rdw_group(f"merk,{year} AS y,count(1) AS n", f"{where} AND {moved}",
                    f"merk,{year}", limit=5000)
    key = lambda d: list(zip(d["merk"], d["y"].astype(int)))
    m = dict(zip(key(mov), mov["n"].astype(int)))
    d = pd.DataFrame({
        "merk": parc["merk"],
        "reg_year": parc["y"].astype(int),
        "parc": parc["n"].astype(int),
    })
    d["age_years"] = end.year - d["reg_year"]
    d["movers"] = [m.get(k, 0) for k in key(parc)]
    d["rate"] = d["movers"] / d["parc"]
    d["make"] = norm_name(d["merk"]).replace(MAKE_ALIASES)
    d["is_group"] = d["make"].isin(STELLANTIS)
    d["window_start"], d["window_end"] = start, end
    print(f"  nlmake: {len(d):,} make-year cells, {d['parc'].sum():,} cars")
    return d.sort_values(["age_years", "rate"], ascending=[True, False], ignore_index=True)


BUILDERS = {"rdw": ("rdw_new_prices", build_rdw), "fipe": ("fipe_history", build_fipe),
            "dvm": ("dvm_new_prices", build_dvm), "indices": ("price_indices", build_indices),
            "newindices": ("new_car_price_indices", build_new_indices),
            "nlhazard": ("nl_transfer_hazard", build_nl_hazard),
            "nlmake": ("nl_transfer_by_make", build_nl_by_make)}


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
