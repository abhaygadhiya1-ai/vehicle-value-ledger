"""Build one unified table of car prices from all sources in loaders/.

Outputs
- data/unified/listings.parquet : one row per car observation, with the shared columns below
- data/unified/build_report.md  : rows kept and dropped per source, coverage, ranges, limits

Shared columns
  source, country       loader name, ISO country code
  price_type            asking (advert price), sale (recorded transaction price), auction (hammer / sold price)
  listing_id            listing id or URL where the source has one (used to remove duplicates)
  listing_date          when the car was listed or sold (see date_basis)
  date_basis            listing        per-row listing / publication / creation date
                        listing_month  per-row listing month
                        sale           per-row sale or auction date
                        scrape_month   one month for the whole dataset, from its description
                        upload_date    upload date of the dataset (approximate scrape date)
                        file_date      date in the file name
                        unclear        dataset dates contradict each other (see report)
  is_new                True = new car, False = used, <NA> = source does not say
  make, model, version  normalised lower-case names; version is free text where available
  is_stellantis         make is a Stellantis brand
  year                  first registration year (production / model year when registration is missing)
  age_years             age at listing_date; whole years when only the year is known
  mileage_km, power_kw, engine_cc
  fuel                  petrol, diesel, hybrid, plugin_hybrid, electric, lpg, cng, other
  transmission          manual, automatic
  body_type             suv, hatchback, sedan, estate, coupe, convertible, mpv, pickup, van, other
  seller_type           dealer, private
  n_owners              number of owners so far, where the source has it
  had_accident          True / False where the source has it
  is_damaged            True for damaged / salvage cars where the source says so
  days_on_market        where the source has it
  price, currency       price as recorded
  price_eur             price in EUR (ECB monthly rate of the listing month; World Bank annual rate
                        for currencies the ECB does not publish)
  new_price_eur         the car's new price (MSRP / list price) in EUR, where the source has it

Usage: .venv/bin/python build_unified.py
"""
from pathlib import Path

import pandas as pd

from loaders import SOURCES

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw"
OUT = HERE / "data" / "unified"

COLUMNS = [
    "source", "country", "price_type", "listing_id", "listing_date", "date_basis", "is_new",
    "make", "model", "version", "is_stellantis", "year", "age_years", "mileage_km",
    "power_kw", "engine_cc", "fuel", "transmission", "body_type", "seller_type",
    "n_owners", "had_accident", "is_damaged", "days_on_market",
    "price", "currency", "price_eur", "new_price_eur",
]
CATEGORY_COLUMNS = ["source", "country", "price_type", "date_basis", "make", "fuel", "transmission",
                    "body_type", "seller_type", "currency"]
HELPER_COLUMNS = ["reg_date", "new_price"]  # loaders may return these; they are used, then dropped

# Sources whose loader still exists but whose data failed an audit. They are not built, so no
# analysis can use them; the reason is written into the build report.
REJECTED = {
    "fr_2023": "Partly generated, not scraped (audit, 2026-09-17). In a quarter of its rows, price "
               "is a near-perfect rising straight line of mileage within one version (r > 0.98 in "
               "2,287 version groups, 35,844 rows), and 34,425 rows repeat another row's mileage and "
               "price under different registration dates. Real adverts show price falling with "
               "mileage; which rows are real cannot be told.",
}

STELLANTIS = {"abarth", "alfa romeo", "chrysler", "citroen", "dodge", "ds", "fiat", "jeep",
              "lancia", "maserati", "opel", "peugeot", "ram", "vauxhall"}
# some sources split makes across make and model ("alfa" + "romeo stelvio")
MAKE_ALIASES = {"alfa": "alfa romeo", "aston": "aston martin", "land": "land rover",
                "rolls": "rolls royce", "mercedes": "mercedes benz", "ds automobiles": "ds"}

# Category maps. Keys are lower-case with single spaces ("_" becomes a space).
# Loaders may also return the canonical values directly; they map to themselves.
FUEL = {
    "gasoline": "petrol", "petrol": "petrol", "benzyna": "petrol", "essence": "petrol",
    "diesel": "diesel",
    "hybrid": "hybrid", "hybryda": "hybrid", "petrol hybrid": "hybrid", "diesel hybrid": "hybrid",
    "hybrid petrol/electric": "hybrid", "hybrid diesel/electric": "hybrid",
    "electric/gasoline": "hybrid", "electric/diesel": "hybrid",
    "hybride essence électrique": "hybrid", "hybride diesel électrique": "hybrid",
    "plugin hybrid": "plugin_hybrid", "plug-in hybrid": "plugin_hybrid", "petrol plug-in hybrid": "plugin_hybrid",
    "diesel plug-in hybrid": "plugin_hybrid", "hybrid petrol/electric plug-in": "plugin_hybrid",
    "hybrid diesel/electric plug-in": "plugin_hybrid",
    "electric": "electric", "elektryczny": "electric", "electrique": "electric",
    "lpg": "lpg", "gasoline + lpg": "lpg", "benzyna+lpg": "lpg", "bicarburation essence gpl": "lpg",
    "cng": "cng", "gasoline + cng": "cng", "benzyna+cng": "cng", "bicarburation essence gnv": "cng",
    "hydrogen": "other", "wodór": "other", "ethanol": "other", "etanol": "other", "other": "other",
    "others": "other", "bi fuel": "other", "petrol ethanol": "other",
    "bicarburation essence bioéthanol": "other",
}
TRANSMISSION = {
    "manual": "manual", "manualna": "manual",
    "automatic": "automatic", "automatyczna": "automatic", "semi-automatic": "automatic",
}
BODY = {
    "suv": "suv", "off-road/pick-up": "suv",
    "hatchback": "hatchback", "compact": "hatchback", "kompakt": "hatchback",
    "city cars": "hatchback", "auta miejskie": "hatchback", "small cars": "hatchback",
    "auta małe": "hatchback", "small": "hatchback",
    "sedan": "sedan", "saloon": "sedan", "limousine": "sedan",
    "station wagon": "estate", "estate": "estate", "kombi": "estate", "estate car": "estate",
    "coupe": "coupe", "coupé": "coupe",
    "convertible": "convertible", "cabriolet": "convertible", "kabriolet": "convertible",
    "cab": "convertible",
    "minivan": "mpv", "mpv": "mpv",
    "pickup": "pickup",
    "van": "van", "combi van": "van", "car derived van": "van", "panel van": "van",
    "window van": "van", "minibus": "van", "microbuses": "van", "camper": "van",
    "commercial": "van", "transporter": "van", "station wagon/van": "van",
    "van-high roof": "van", "box": "van", "flatbed van": "van",
    "other": "other",
}


# ---------- helpers ----------

def norm_name(s):
    """Lower-case, strip accents, '-' and '_' to spaces: 'Citroën' -> 'citroen'."""
    s = s.astype("string").str.normalize("NFKD").str.encode("ascii", "ignore").str.decode("ascii")
    return (s.astype("string").str.lower().str.replace(r"[-_]", " ", regex=True)
            .str.replace(r"\s+", " ", regex=True).str.strip())


def strip_make(model, make, make_raw):
    """Drop a make name repeated in the model: 'alfa romeo gtv' -> 'gtv', and the rest of a
    split make: make 'alfa', model 'romeo stelvio' -> 'stelvio'."""
    if not (isinstance(model, str) and isinstance(make, str)):
        return model
    prefixes = [make + " "]
    if isinstance(make_raw, str) and make.startswith(make_raw + " "):
        prefixes.append(make[len(make_raw) + 1:] + " ")
    for prefix in prefixes:
        if model.startswith(prefix):
            return model[len(prefix):]
    return model


def cat_key(s):
    """Key for the category maps: lower-case, '_' to space, single spaces."""
    return (s.astype("string").str.lower().str.replace("_", " ")
            .str.replace(r"\s+", " ", regex=True).str.strip())


def md_table(df):
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |")
    return "\n".join(lines)


def load_fx():
    """Monthly ECB rates and annual World Bank rates, both as units of currency per 1 EUR."""
    ecb = pd.read_csv(RAW / "fx/ecb_monthly.csv", usecols=["CURRENCY", "TIME_PERIOD", "OBS_VALUE"])
    ecb = ecb.rename(columns={"CURRENCY": "currency", "TIME_PERIOD": "month", "OBS_VALUE": "rate"})
    usd = ecb[ecb["currency"].eq("USD")]
    usd_per_eur = usd.groupby(usd["month"].str[:4].astype(int))["rate"].mean()
    wb = pd.read_csv(RAW / "fx/worldbank_annual.csv")  # currency, fx_year, lcu_per_usd
    wb["rate_year"] = wb["lcu_per_usd"] * wb["fx_year"].map(usd_per_eur)
    return ecb, wb[["currency", "fx_year", "rate_year"]].dropna()


# ---------- shared cleaning ----------

def finish(df, source, info, fx):
    """Normalise one source to the shared columns, drop bad rows, and return (df, stats)."""
    df = df.copy()
    df["source"] = source
    if "country" not in df:
        df["country"] = info["country"]
    if "price_type" not in df:
        df["price_type"] = info["price_type"]
    for col in COLUMNS + HELPER_COLUMNS:
        if col not in df:
            df[col] = pd.NA
    stats = {"rows_raw": len(df)}

    # names
    make_raw = norm_name(df["make"])
    df["make"] = make_raw.replace(MAKE_ALIASES)
    model = norm_name(df["model"])
    df["model"] = pd.Series([strip_make(m, k, r) for m, k, r in zip(model, df["make"], make_raw)],
                            index=df.index, dtype="string")
    df["version"] = df["version"].astype("string").str.strip()
    df["is_stellantis"] = df["make"].isin(STELLANTIS)

    # categories (values not in the maps become <NA>; the most common ones are reported)
    stats["unmapped"] = {}
    for col, mapping in [("fuel", FUEL), ("transmission", TRANSMISSION), ("body_type", BODY)]:
        key = cat_key(df[col])
        unmapped = key[key.notna() & ~key.isin(list(mapping))]
        stats["unmapped"][col] = unmapped.value_counts().head(5).to_dict()
        df[col] = key.map(mapping)

    # numbers and age
    for col in ["year", "age_years", "mileage_km", "power_kw", "engine_cc", "price", "new_price",
                "n_owners", "days_on_market"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # impossible spec values are left empty rather than dropping the listing
    df["power_kw"] = df["power_kw"].where(df["power_kw"].between(10, 1000))
    df["engine_cc"] = df["engine_cc"].where(df["engine_cc"] <= 10_000)
    df["listing_date"] = pd.to_datetime(df["listing_date"])
    reg = pd.to_datetime(df["reg_date"], errors="coerce")
    df["year"] = reg.dt.year.astype("Float64").fillna(df["year"])
    age_from_reg = (df["listing_date"] - reg).dt.days / 365.25
    age_from_year = df["listing_date"].dt.year - df["year"]
    df["age_years"] = df["age_years"].fillna(age_from_reg).fillna(age_from_year)
    for col in ["is_new", "had_accident", "is_damaged"]:
        df[col] = df[col].astype("boolean")

    # prices in EUR: ECB monthly rate of the listing month, else World Bank annual rate,
    # else the latest World Bank year for that currency
    ecb, wb = fx
    df["currency"] = df["currency"].astype("string").str.upper()
    df["month"] = df["listing_date"].dt.strftime("%Y-%m")
    df["fx_year"] = df["listing_date"].dt.year
    df = df.merge(ecb, on=["currency", "month"], how="left")
    df = df.merge(wb, on=["currency", "fx_year"], how="left")
    latest = wb.sort_values("fx_year").groupby("currency")["rate_year"].last()
    df.loc[df["currency"].eq("EUR"), "rate"] = 1.0
    stats["fx_annual"] = int((df["rate"].isna() & df["rate_year"].notna()).sum())
    df["rate"] = df["rate"].fillna(df["rate_year"])
    stats["fx_latest_year"] = int((df["rate"].isna() & df["currency"].isin(latest.index)).sum())
    df["rate"] = df["rate"].fillna(df["currency"].map(latest))
    df["price_eur"] = df["price"] / df["rate"]
    df["new_price_eur"] = df["new_price"] / df["rate"]

    # drop bad rows; each row is counted under the first rule it breaks
    rules = {
        "missing price, make, model or year": df[["price_eur", "make", "model", "year"]].isna().any(axis=1),
        "price below 500 or above 1,000,000 EUR": ~df["price_eur"].between(500, 1_000_000),
        "mileage above 1,000,000 km or negative": df["mileage_km"].notna() & ~df["mileage_km"].between(0, 1_000_000),
        "year before 1980 or after listing year + 1": ~df["year"].between(1980, df["listing_date"].dt.year + 1),
        "age below -1 year": df["age_years"] < -1,
    }
    keep = pd.Series(True, index=df.index)
    stats["drops"] = {}
    for name, bad in rules.items():
        bad = bad.fillna(False).astype(bool) & keep
        stats["drops"][name] = int(bad.sum())
        keep &= ~bad
    df = df[keep].copy()
    df["age_years"] = df["age_years"].clip(lower=0)

    has_id = df["listing_id"].notna()
    dup = ((has_id & df.duplicated("listing_id"))
           | (~has_id & df.duplicated([c for c in COLUMNS if c != "listing_id"])))
    stats["drops"]["duplicate listing"] = int(dup.sum())
    df = df[~dup]

    stats["rows_kept"] = len(df)
    return df[COLUMNS], stats


# ---------- report ----------

def report(df, stats, infos):
    fmt = lambda x: f"{x:,.0f}"
    pct = lambda x: f"{100 * x:.0f}%"
    g = df.groupby("source", observed=True)

    overview = pd.DataFrame({
        "country": g["country"].agg(lambda s: ", ".join(s.value_counts()[lambda v: v > 0].index.astype(str)[:8])),
        "price type": g["price_type"].first(),
        "date basis": g["date_basis"].first(),
        "dates": g["listing_date"].agg(lambda s: f"{s.min():%Y-%m-%d} – {s.max():%Y-%m-%d}"),
        "rows raw": [fmt(stats[s]["rows_raw"]) for s in g.groups],
        "rows kept": g.size().map(fmt),
        "used / new / unknown": g["is_new"].agg(
            lambda s: f"{pct(s.eq(False).sum() / len(s))} / {pct(s.eq(True).sum() / len(s))} / {pct(s.isna().mean())}"),
        "median price €": g["price_eur"].median().map(fmt),
        "EVs": g["fuel"].agg(lambda s: fmt((s == "electric").sum())),
        "Stellantis rows": g["is_stellantis"].sum().map(fmt),
        "license": [infos[s]["license"] for s in g.groups],
    }).reset_index()

    drops = pd.DataFrame({s: stats[s]["drops"] for s in stats}).T
    drops["fx: annual rate"] = [stats[s]["fx_annual"] for s in drops.index]
    drops["fx: latest-year rate"] = [stats[s]["fx_latest_year"] for s in drops.index]
    drops = drops.map(fmt).reset_index(names="source")

    shared = ["listing_id", "is_new", "version", "mileage_km", "power_kw", "engine_cc", "fuel",
              "transmission", "body_type", "seller_type", "n_owners", "had_accident", "is_damaged",
              "days_on_market", "new_price_eur"]
    coverage = g[shared].agg(lambda s: pct(s.notna().mean())).reset_index()

    fuel = pd.crosstab(df["source"], df["fuel"]).map(fmt).reset_index()
    body = pd.crosstab(df["source"], df["body_type"]).map(fmt).reset_index()
    by_country = (df.groupby("country", observed=True)
                  .agg(rows=("price_eur", "size"), sources=("source", lambda s: ", ".join(sorted(s.unique()))))
                  .sort_values("rows", ascending=False))
    by_country["rows"] = by_country["rows"].map(fmt)
    by_type = df.groupby("price_type", observed=True).size().map(fmt).reset_index(name="rows")
    sources = pd.DataFrame([{"source": s, "url": infos[s]["url"]} for s in sorted(infos)])

    unmapped = [f"- **{s}** {col}: {vals}" for s in stats for col, vals in stats[s]["unmapped"].items() if vals]

    return "\n\n".join([
        "# Unified car prices: build report",
        f"Generated by `build_unified.py` on {pd.Timestamp.today():%Y-%m-%d}. "
        f"**{len(df):,} rows** from {df['source'].nunique()} sources in {df['country'].nunique()} countries.",
        "## Rows by price type", md_table(by_type),
        "## Sources", md_table(overview),
        "## Rows dropped, by rule (and rows converted with fallback exchange rates)", md_table(drops),
        "## Column coverage (share of rows with a value)", md_table(coverage),
        "## Fuel mix", md_table(fuel),
        "## Body types", md_table(body),
        "## Rows by country", md_table(by_country.reset_index()),
        "## Values not mapped (left empty)", "\n".join(unmapped) or "None.",
        "## Sources rejected, not built", "\n".join(f"- **{s}**: {why}" for s, why in REJECTED.items())
        or "None.",
        "## Source links", md_table(sources),
        "## Notes and limits",
        "\n".join([
            "- **Price types differ.** `asking` prices are advert prices, `sale` prices are recorded "
            "transaction prices, and `auction` prices are sold / hammer prices. Analyse them separately, "
            "or model the gap explicitly.",
            "- **Dates.** Check `date_basis`. Several sources have one approximate date for the whole dataset. "
            "`fr_2023` is unclear: the upload date is 2023-06-16, but circulation date + circulation days "
            "gives 2023-11-19 for every row. Its age comes from circulation days, so age is not affected.",
            "- **Age.** Taken from the registration date where the source has one. Otherwise it is listing year "
            "minus year, in whole years.",
            "- **Exchange rates.** ECB monthly averages where the ECB publishes the currency. Otherwise World Bank "
            "annual official rates (converted via the annual USD/EUR average), which miss sharp moves within a year.",
            "- **Hybrids.** Some sources do not separate plug-in hybrids, so their `hybrid` can include plug-ins.",
            "- **Body types.** 'Compact', 'city car' and 'small car' are grouped as hatchback. AutoScout24 'Van' "
            "(which can include MPVs) is grouped as van.",
            "- **UK rows without a year.** In `uk_2022_10`, rows with text in the year column have shifted columns. "
            "Almost all are brand-new cars, so dropping them does not affect used-car analysis.",
            "- **Names.** Makes are aligned across sources, but model names are not fully aligned (e.g. Polish "
            "'klasa e' vs 'e class'). Compare models within a source or country.",
            "- **Specs.** Power outside 10–1,000 kW and engine size above 10,000 cc are left empty, not dropped.",
            "- **Excluded.** `de_cz_2015_2017`, because its fuel labels are wrong and it has no country column "
            "(see DATASETS.md).",
            "- **Repeated observations.** `lv_ss` is a monthly panel and `pt_standvirtual` a weekly one: "
            "an advert that stays up appears once per snapshot. Rows are observations, not unique cars, "
            "so cluster by car or take one snapshot before modelling.",
            "- **Not passenger cars.** `eu_commercial_2023` is vans and trucks. Its German prices are net "
            "of VAT (the source says so); every other country quotes the advertised price. Hungary's "
            "description claims EUR but the values are forint, so HUF is used.",
            "- **Damaged-vehicle auctions.** `nz_findcars` is Manheim New Zealand's damaged-vehicle "
            "channel, so every row is marked damaged and the price level is far below a normal used car. "
            "The EUR 500 floor removes about two thirds of its lots, which biases what is left upwards. "
            "Its mileage is not read at all, because the publisher fills missing values with a group "
            "median and does not mark which ones were filled.",
            "- **Auction prices.** `us_carsandbids` keeps only completed sales, but the cars are "
            "enthusiast and collector vehicles, not a normal market. `us_ebay_2006` gives the highest bid "
            "on a completed 2006 auction: the file has no usable flag for whether the reserve was met.",
            "- **Parsed from free text.** `ca_gcsurplus` reads year, make and model out of a lot "
            "description and keeps only single-item lots with a passenger-car make; it carries no "
            "odometer reading at all.",
            "- **Singapore.** `sg_sgcarmart` prices include the Certificate of Entitlement, a quota "
            "licence that can cost more than the car, so its price level is not comparable with any "
            "other country. Listings repeating a placeholder price of 128,105 are dropped.",
            "- **Missing columns by design.** `es_2020_11` has no usable fuel column (the source's own "
            "attribute columns are shifted), and `us_ebay_2006` has no fuel, gearbox or body type.",
            "- **New-car prices.** Only `us_marketcheck_used` and `us_marketcheck_new` carry a list price "
            "on every row, and they are 1,000-row samples. `data/reference/` holds the larger new-price "
            "and index tables.",
            "- **Licence to check.** `uz_avtoelon` is published 'for research and educational purposes "
            "only', which is not an open licence.",
        ]),
    ]) + "\n"


def main():
    fx = load_fx()
    parts, stats, infos = [], {}, {}
    for source, module in SOURCES.items():
        if source in REJECTED:
            print(f"{source}: rejected - {REJECTED[source]}")
            continue
        raw = RAW / source
        if not raw.exists() or not any(raw.iterdir()):
            print(f"{source}: no raw data - run download_data.py first")
            continue
        print(f"{source}: loading")
        part, stats[source] = finish(module.load(raw), source, module.INFO, fx)
        infos[source] = module.INFO
        print(f"{source}: kept {stats[source]['rows_kept']:,} of {stats[source]['rows_raw']:,}")
        parts.append(part)

    df = pd.concat(parts, ignore_index=True)
    for col in CATEGORY_COLUMNS:
        df[col] = df[col].astype("category")
    for col in ["listing_id", "model", "version"]:
        df[col] = df[col].astype("string")

    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "listings.parquet", index=False)
    (OUT / "build_report.md").write_text(report(df, stats, infos))
    print(f"wrote {len(df):,} rows to {OUT / 'listings.parquet'}")


if __name__ == "__main__":
    main()
