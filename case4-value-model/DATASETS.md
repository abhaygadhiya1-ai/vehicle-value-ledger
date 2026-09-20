# DATASETS.md: data for the car-value engine

Last updated 2026-09-17. Analysis results live in `analysis/` (`drivers_report.md`, `lodo_report.md`, `curve_report.md`).

**How this was checked:**
1. Kaggle's public search API and each dataset's metadata (files, sizes, columns, license, description), plus the Hugging Face API and the DVM-CAR user manual.
2. The 7 shortlisted datasets were downloaded with the Kaggle CLI into `data/raw/` and counted with pandas. All numbers marked **(counted)** come from our own count of the downloaded files.

## Audit corrections (2026-09-17) - read before any count below

An audit profiled every source (prices, units, exchange rates, mileage per year, repeated rows) and
found three defects in the data as built. They are fixed, and the unified table is rebuilt.
**Counts further down this file are from before the audit unless they say otherwise.**

| Defect | What was wrong | Fix |
|---|---|---|
| **`uk_2022_10` repeats adverts** | The raw Kaggle file lists many adverts two or three times under different variant labels, identical in every other field down to the mileage: 360,988 of 818,456 raw rows. The build removed only rows identical in every column, so 314,057 copies reached the table. | The loader keeps one row per advert. 442,344 UK adverts remain. |
| **`fr_2023` is partly generated** | In 2,287 version groups (35,844 rows, a quarter of the file) price is a near-perfect *rising* straight line of mileage (r > 0.98); 34,425 rows repeat another row's mileage and price under different registration dates. Within one model, version and year, price rose with mileage in 74% of groups, median correlation +0.99, against -0.36 to -0.76 in every other European source. Which rows are real cannot be told. | **Rejected.** `build_unified.py` lists it in `REJECTED` and does not build it; the reason is in `build_report.md`. France still appears through `eu_2025_11`. |
| **`pt_standvirtual` engine size misread** | "1 499 cm3" was read as 14,993 because the 3 of cm3 was kept as a digit; values over 10,000 were then discarded, leaving 12% coverage, all wrong. | Leading number only: 93% coverage. |

**After the audit:** 3,879,498 rows from 29 sources in 31 countries; 3,359,330 advert prices (96%
European), 425,974 sale and 94,194 auction prices. `drivers.py` fits 16 datasets.

**Checked and left alone, with the reason:**
- `lv_ss` repeats cars month to month: a monthly panel with no advert id, known and documented.
- `eu_2025_11`: 839 groups of identical cars listed in more than one country (AutoScout24 cross-listing); which country is right cannot be told.
- **`eu_2025_11`'s Dutch subset is premium dealer stock, not a market** (found 2026-09-21). Its
  median asking price is **EUR 99,950 for a two-year-old car** on 483 adverts and the curve is not
  monotone in age. Pricing the Dutch used-car flow from it gives **EUR 30.9bn against EUR 13.0bn**
  from official catalogue prices - a 2.4x overstatement. Adverts per car on the road correlate with
  the register at rho **0.14**. **Do not use it for a national price level.** Its *retention ratio*
  does survive, because the same bias sits in the advert price and the catalogue price and divides
  out. This is the listings collection's general shape: good pooled across many sources, bad as a
  level in one country.
- `es_2020_11`, `se_2022`, `id_2025`, `nz_findcars`: repeated attribute sets with different advert ids or dates - reposts or identical dealer stock, not provably duplicates.
- `us_wa_ev_sales`: repeats are new EVs sold at list price with delivery miles; the analyses use used sales only.
- `nz_findcars` is labelled `asking` but is a damaged-vehicle auction that also lists trailers and motorcycles; it has no mileage and no analysis uses it.
- Exchange rates: every currency's median rate per EUR sits in its expected range (GBP 0.87, PLN 4.56, SEK 10.58, USD 1.12, ...).
- The Eurostat and ONS index values in `data/reference/` match the official APIs exactly (spot checks: LV, DE, FR, PL, UK).

## What we need

- Used-car listings with price, make, model, year/age, mileage, fuel (incl. EVs), transmission, engine, body type, country.
- **A listing or scrape date for each row** (for the time split and the price-cut study).
- Europe first, with brands from a merged group (Stellantis). Several years if possible.
- Bonus: the new-car price, to model value retained as a % of the new price.

## Downloaded datasets (counted)

| # | Dataset | Country | Rows (counted) | Date field and real range (counted) | EVs (counted) | Teslas (counted) | Stellantis-brand rows (counted) | License | Size (unzipped) |
|---|---|---|---|---|---|---|---|---|---|
| P1 | [Otomoto 2021](https://www.kaggle.com/datasets/bartoszpieniak/poland-cars-for-sale-dataset) | Poland | 208,304 (182,850 used) | `Offer_publication_date`: 26 Mar – 5 May 2021 (all but 8 in Apr–May) | 1,553 | 90 (Model 3: 27, no Model Y) | 42,881 | CC0 | 166 MB |
| P2 | [Otomoto May 2022](https://www.kaggle.com/datasets/krzysztofdogowski/used-cars-poland-with-links-may-2022) | Poland | 152,943 | none (collected May 2022). **Only 23 makes, no Tesla, Jeep, DS or Lancia.** | 763 | 0 | ≥26,411 | CC0 | 26 MB |
| P3 | [Otomoto April 2023](https://www.kaggle.com/datasets/szymoncyperski/car-sales-offers-from-otomotopl-2023) | Poland | 208,205 (187,515 used) | `offer_creation_date`: 14 Mar – 23 Apr 2023 (208,026 in April) | 3,373 | 284 (Model 3: 117, Model Y: 30) | 39,394 | CC BY-SA 4.0 | 140 MB |
| P4 | [Otomoto August 2023](https://www.kaggle.com/datasets/krzysztofdogowski/used-cars-in-poland-many-parameters) | Poland | 170,693 (153,060 used) | `Czas dodania` (time added): 31 Jul – 31 Aug 2023 | 3,779 | 311 (Model 3: 134, Model Y: 36) | 32,160 | Unknown | 82 MB |
| UK | [UK used car listings, Oct 2022](https://www.kaggle.com/datasets/guanhaopeng/uk-used-car-market) | UK | 818,456 (764,247 used) | none (October 2022 per description) | 13,896 electric, 14,086 plug-in hybrid | 947 (Model 3: 590, Model Y: 70) | 115,876 | CC0 | 279 MB |
| DVM | [DVM-CAR](https://deepvisualmarketing.github.io/) ([Kaggle copy](https://www.kaggle.com/datasets/mexwell/dvm-car)) | UK | 268,255 ads | `Adv_year`/`Adv_month`: mostly 2018 (239,973), plus 2017 (11,320) and 2021 (14,864) | 1,302 | 69 (Model S/X only) | 51,611 | CC BY-NC (non-commercial) | 53 MB |
| DE/CZ | [Classified ads, DE + CZ](https://www.kaggle.com/datasets/mirosval/personal-cars-classifieds) | Germany, Czechia | 3,552,912 | `date_created`: Nov 2015 – Mar 2017, but very uneven (4,297 rows in Apr 2016) | see below | 235 (mostly Model S) | 611,685 | CC0 | 420 MB |

**Data quality notes (counted):**
- **UK:** some rows have shifted columns (text in the `year` column), so cleaning is needed.
- **DE/CZ:** fuel type is missing for 1,847,606 rows. The 26,350 "electric" rows only appear from late 2016, and the top makes are Skoda, VW and Ford, so the label is clearly wrong. There is no country column. **Rejected.** It can be deleted to free 420 MB and re-downloaded if ever needed.
- **DVM price table:** 6,333 rows, 647 models, 1998–2021, with new-car entry prices (cheapest trim) by model and year. It contains 902 year-on-year price cuts, 335 of them over 5%. 211,713 of the 239,973 ads from 2018 match a new price.

## Added for the unified table (counted)

| # | Dataset | Country | Rows (counted) | Date | License | Size (unzipped) |
|---|---|---|---|---|---|---|
| DE23 | [Germany used cars 2023 (AutoScout24)](https://www.kaggle.com/datasets/wspirat/germany-used-cars-dataset-2023) | Germany | 251,079 | no listing date; Kaggle upload 24 Jun 2023 used as an approximate date | CC0 | 36 MB |
| EU25 | [AutoScout24 listings 2025](https://www.kaggle.com/datasets/clkmuhammed/autoscout24-car-listings-dataset) | DE, IT, NL, BE, ES, AT, FR, LU | 118,382 | snapshot 8 Nov 2025 (file name). Rich: accidents, previous owners, dealer flag | MIT | 549 MB |
| SE22 | [Sweden's used car market](https://www.kaggle.com/datasets/jodancker/swedens-used-car-market) | Sweden | 134,243 | `publication_datetime`: 17 Mar 2021 – 15 Sep 2022 (dealers only) | Unknown | 41 MB |
| FR23 (**rejected in the 2026-09-17 audit: partly generated**) | [LaCentrale France](https://www.kaggle.com/datasets/bozzabb/data-of-second-hand-vehicles) | France | 141,199 | Unclear: upload date 16 Jun 2023, but the data implies 19 Nov 2023. Age is still exact (days in circulation). | Unknown | 29 MB |

## Unified table

`build_unified.py` combines all 10 datasets above (P1–P4, UK, DVM, DE23, EU25, SE22, FR23; not DE/CZ) into `data/unified/listings.parquet`. The result is **2,373,524 listings from 11 countries**, with the same columns for every source and €-converted asking prices (ECB monthly rates). `data/unified/build_report.md` shows rows kept and dropped per rule, column coverage, fuel and body mix, and known limits. `download_data.py` re-downloads everything.

## Beyond Kaggle (searched 2026-09-16, loaded 2026-09-17)

Five search agents covered Hugging Face, research repositories (Zenodo, Mendeley, Figshare, Harvard
Dataverse, UCI, OpenML), GitHub, official open data and other data platforms. They found 55
candidates; the full list with checked metadata is in
`data/sources/sweep_beyond_kaggle_2026-09-16.json`.

**20 of them are now loaded**, adding **1,959,971 rows** and taking the unified table from
2,374,224 rows in 11 countries to **4,334,195 rows from 30 sources in 31 countries** (before the
audit; after it, **3,879,498 rows from 29 sources**). All counts below are our own, measured after
cleaning.

### Loaded (counted)

| Source | Country | Rows kept | Price type | Dates | Stellantis rows | What it adds | Licence |
|---|---|---|---|---|---|---|---|
| [lv_ss](https://data.mendeley.com/datasets/6bhm5zbs7f) | LV | 944,395 | asking | 2019-01 – 2023-12 | 120,073 | **A monthly panel, 52 months** (May-Dec 2021 missing). The only source with a real time series. | CC BY 4.0 |
| [us_wa_ev_sales](https://data.wa.gov/d/rpr4-cgyd) | US | 425,974 | **sale** | 2012-04 – 2026-08 | 19,360 | **Recorded sale prices**, 340,376 of them EVs | ODC-BY |
| [es_2020_11](https://zenodo.org/records/4252636) | ES | 188,779 | asking | 2020-11 | 45,796 | Spain at scale (was 7,933 rows) | CC BY 4.0 |
| [eu_commercial_2023](https://data.mendeley.com/datasets/kz6hh7832p) | 15 countries | 144,530 | asking | 2023 | 30,520 | **Vans and trucks**, the Stellantis Pro One side | CC BY 4.0 |
| [ma_mucars_2024](https://data.mendeley.com/datasets/vjrbcb2rrt) | MA | 61,163 | asking | 2024-12 | 14,991 | Morocco | CC BY 4.0 |
| [us_ebay_2006](https://doi.org/10.7910/DVN/V5XSMF) | US | 45,811 | auction | 2006 | 1,955 | Auction bids, plus an Edmunds appraisal in the raw file | CC0 |
| [us_carsandbids](https://github.com/MattSnively/CarsAndBidsData) | US | 26,975 | auction | 2021-08 – 2026-08 | 1,344 | **Sold auction prices**, with title brands | None stated |
| [ca_gcsurplus](https://open.canada.ca/data/en/dataset/1a09c5c1-3554-4b70-9e53-6322a72ec7d4) | CA | 21,408 | auction | 2015-08 – 2025-12 | 4,153 | **Realised fleet sale prices**, 10 years | OGL Canada |
| [nz_findcars](https://github.com/prasanthsasikumar/FindCars-NZ) | NZ | 20,167 | asking | 2023-05 – 2026-02 | 189 | **Damaged-vehicle auctions**: the only damage group | MIT |
| [eg_hatla2ee](https://huggingface.co/datasets/mo-hug-me/used-car-listings-dataset-from-hatla2ee2026) | EG | 19,303 | asking | 2026 | 2,553 | Egypt | Unknown |
| [pt_standvirtual](https://github.com/r-rodri/ImportedCars) | PT | 16,249 | asking | 2023-05 – 2024-04 | 3,869 | Portugal, weekly snapshots, owners and warranty | None stated |
| [id_2025](https://zenodo.org/records/21792616) | ID | 14,890 | asking | 2025-04 – 2026-08 | 0 | Indonesia, with real advert dates | CC BY 4.0 |
| [jo_jucars_2024](https://data.mendeley.com/datasets/ddcz486x5t) | JO | 9,380 | asking | 2026-03 | 535 | Jordan, 1,929 EVs | CC BY 4.0 |
| [sg_sgcarmart](https://huggingface.co/datasets/Raymond0960/sgcarmart-data) | SG | 7,931 | asking | 2025 | 283 | Singapore (COE-inflated prices) | Unknown |
| [bd_aiub](https://data.mendeley.com/datasets/8d38h82fyt) | BD | 5,872 | asking | 2026-06 | 0 | Bangladesh | CC BY 4.0 |
| [uz_avtoelon](https://huggingface.co/datasets/Mehriddin1997/uzbekistan-car-prices) | UZ | 2,618 | asking | 2026-03 | 0 | Uzbekistan | **Not open** (see below) |
| [ng_cars45](https://huggingface.co/datasets/Binaryy/cars-for-sale) | NG | 1,327 | asking | 2023 | 37 | Nigeria | Unknown |
| [bd_bikroy](https://data.mendeley.com/datasets/fmb4xmp4k5) | BD | 1,199 | asking | 2024-01 | 0 | Bangladesh, second site | CC BY 4.0 |
| [us_marketcheck_used](https://huggingface.co/datasets/Marketcheck/us_used_car_inventory_data) | US | 1,000 | asking | 2022-11 – 2026-05 | 120 | **MSRP and days on market on every row** | Unknown |
| [us_marketcheck_new](https://huggingface.co/datasets/Marketcheck/us_new_car_inventory_data) | US | 1,000 | asking | 2024-09 – 2026-05 | 93 | New-car list price on every row | Unknown |

### What had to be corrected in the sources

Worth knowing, because each one would have produced a wrong number if taken at face value:

- **Hungary, `eu_commercial_2023`:** the dataset's own description file says the price is in EUR,
  but the values are forint (an Opel Combo Cargo at 9,264,904 is about €24,000, not €9.2m). Using
  the stated currency dropped every Hungarian row past the €1,000,000 ceiling. HUF is used instead.
- **New Zealand, `nz_findcars`:** the columns are named `Price_USD` and `Mileage_Miles`, but the
  publisher's `clean_data.py` parses the raw Manheim NZ fields without converting them, so they are
  NZD and kilometres. The same script **fills missing mileage with the (make, model, year) median**
  and does not mark which values were filled, so mileage is not read at all.
- **eBay 2006:** the `maker` column contains `.` on 1,387 rows. Because the loader builds the
  model-matching pattern from the list of makes, that `.` acted as a wildcard and invented a model
  for about 20,000 rows. Makes are now escaped and the junk make is dropped.
- **Spain, `es_2020_11`:** `car_engine_type` and `car_door_num` are identical columns holding
  whichever attribute the advert listed first (gearbox, doors or power), so there is **no usable
  fuel column**; only the gearbox values are read. The file also repeats its own header 7,603 times.
- **Singapore:** a price of 128,105 repeats on 4,625 unrelated listings, so it is a placeholder and
  those rows are dropped.
- **Latvia:** the dataset's own dictionary lists `c` as both cabriolet and coupe. The later files,
  which spell the words out, run 510 Kupeja to 122 Kabriolets; the coded files run 9,091 `c` to
  2,420 `ca` — the same 4:1 split, so `c` is coupe and `ca` is cabriolet.
- **Nigeria:** the file has a second `Car Name.1` column showing a different vehicle from the one
  the row's price belongs to (the two agree on 1.2% of rows). Only `Car Name` is read.

### The one source we could check against an official statistic

Latvia is the only dataset where an independent measurement of the same thing exists, so it is the
best evidence we have that these scraped adverts track a real market. Building a quality-adjusted
price index from the 52 monthly snapshots (holding model, age, mileage, fuel, gearbox and body
fixed) and comparing it with Eurostat's official Latvian second-hand car index (HICP CP07112):

- **The two series correlate at 0.958** across all 52 months. They rise and fall together.
- **They disagree on size.** Ours rises 42% between January 2019 and December 2023; the official
  Latvian index rises 8.8%.
- **Latvia's own official series is the odd one out, not ours.** Over the same window Eurostat has
  Lithuania at +38.4% and Estonia at +38.1% — neighbouring, structurally similar import-driven used
  markets, both close to our Latvian figure. Across the 37 geographies in that table the range runs
  from −24% to +44%, so European used-car inflation was extremely uneven.

We cannot settle from this data which measurement is closer to the truth — ours is asking prices,
HICP is a statistical office's own basket of transactions. What can be said is that our number sits
with its neighbours and moves in step with the official series. Full working in
`analysis/latvia_time_report.md`.

### Checked and rejected

| Source | Why not |
|---|---|
| Latvian 2018 file | It was downloaded, but **no 2018 record exists** in the author's Mendeley catalogue (checked via DataCite across all 39 of their datasets), so the file has no citable source. Deleted; the series runs 2019–2023. |
| `nz_manheim` (HF `impsk/nz-manheim-auction-2023-2025`) | The same Manheim NZ damaged-vehicle channel as `nz_findcars`, 5,228 rows against 20,167. Dropped to avoid double-counting one auction house. |
| Lithuania, inside `eu_commercial_2023` | Its file has no header row, so its 2,916 rows cannot be assigned to columns with confidence. The other 15 countries are loaded. |
| Romania and Sweden, inside `eu_commercial_2023` | Loaded, but the source itself has a price on only ~4–5% of their rows, so few survive. |
| eBay `bookvalue` | The file carries an Edmunds appraisal on 62% of rows. That is a valuation of the **used** car, not a list price, so it is deliberately not loaded into `new_price`; it stays in the raw file for a separate appraisal-versus-price analysis. |
| Paid or gated | Rebrowser (30-day samples), Carvana (AWS account), Larsen dealer auctions (request access), Manheim index (proprietary). |
| Too small or niche | GitHub scrapes of one model, a 600-lot classic-car auction, city fleet sales. |
| Aggregates or wrappers | The Autoza index, the EC car-price PDF reports, FIPE API wrappers. |
| Possibly synthetic | tc-llm UK. |

### The hole in the collection

Worth stating plainly, because it shapes what to collect next (`analysis/price_types_report.md`).
The collection's **3.4 million advert prices (3.8 million before the audit) are almost all European**, while **every sale and
auction price is North American**:

| Price type | Rows | Where |
|---|---|---|
| asking (advert) | 3,814,027 | mostly Europe |
| sale (recorded transaction) | 425,974 | Washington State only, electric vehicles only |
| auction | 94,194 | US and Canada |

Because of that split, an advert price and a sale price can only be compared on about 190 US cars,
which is far too few. **The advert-based models cannot be translated into expected sale prices**,
and no asking-to-sale factor should be quoted from this data. The single most valuable thing to add
to the collection is therefore not another advert scrape in another country: it is **one European
source with realised transaction prices** — a national registration file that records a sale price,
as Washington State does.

### Licence to check before publishing

`uz_avtoelon` is published "for research and educational purposes only", which is not an open
licence. `us_carsandbids` and `pt_standvirtual` have no licence file at all. `us_marketcheck_*`,
`sg_sgcarmart`, `eg_hatla2ee` and `ng_cars45` state no licence. Cite them, and check before reusing
anything outside the analysis.

## Reference tables (`data/reference/`, built by `build_reference.py`)

These are not listings. They are the yardsticks the value model measures against.

| File | What it is | Source |
|---|---|---|
| `price_indices.parquet` | **6,918 monthly index values.** Eurostat HICP second-hand motor cars (5,234 rows, 39 countries, 1996-01 – 2025-12), ONS D7E9 UK (464, 1988-01 – 2026-08), INSEE France (336, 1998-01 – 2025-12), US CPI used cars (884, 1953-01 – 2026-08) | Eurostat, ONS, INSEE, FRED |
| `new_car_price_indices.parquet` | **5,942 monthly index values.** Eurostat HICP **new** motor cars (CP07111), 41 countries, 1996-01 – 2025-12. Added 2026-09-20 for `analysis/discount_passthrough.py`. **Deliberately a separate file:** `analysis/latvia_time.py` selects its series with `str.contains("Eurostat")`, so a second Eurostat series inside `price_indices.parquet` would silently break the project's only external validation | Eurostat |
| `dvm_new_prices.parquet` | 6,333 UK model-years, 1998–2021: the entry price plus the min, median and max across that year's trims | DVM-CAR |
| `rdw_new_prices.parquet` | Dutch official new-car catalogue price by make, model and registration year, aggregated on RDW's server from 8,863,469 priced passenger cars | [RDW](https://opendata.rdw.nl/Voertuigen/Open-Data-RDW-Gekentekende_voertuigen/m9d7-ebf2) |
| `fipe_history.parquet` | Brazil's official FIPE monthly valuation by model and model year, including the 0 km price | [fipeX](https://huggingface.co/datasets/alanwgt/fipex-veiculos-brasil) |
| `nl_transfer_hazard.parquet` | **Added 2026-09-21 for the readiness engine.** How often a Dutch car of each age changes keeper, and the official new price of the vintages still on the road. 1,376 rows: three populations (all, domestic-registered, including cars since exported) x two brand sets (all, the group's) x two twelve-month windows x single years of age. Numerator and denominator come out of the same register, so the hazard is a count over a count | [RDW](https://opendata.rdw.nl/Voertuigen/Open-Data-RDW-Gekentekende_voertuigen/m9d7-ebf2), CC0 |
| `uk_mot_panel.parquet` | **Added 2026-09-21 for `analysis/readiness_model.py`.** A quarter-sample of UK cars tested in March 2024 with ten fields and a label - whether the car was ever tested again through July 2025. The only public per-car replacement outcome anywhere in the collection | [DVSA](https://open.data.dvsa.gov.uk/mot-anonymised/index.html), OGL v3.0 |

**The reference tables join to the listings**, and the match rates are measured rather than assumed
(`analysis/value_retained.py`): **UK 69.9%**, **Netherlands 65.0%**, **Brazil 59.4%**, US 100%
(Marketcheck already carries an MSRP per row). 661,503 listings now have a borrowed new price in
`data/unified/value_retained.parquet`, each tagged with the source it came from. An early version
of `build_reference.py` lowercased names without applying the same normalisation as
`build_unified.py`, so `mercedes-benz` never matched `mercedes benz`; fixing that lifted the UK
match rate from 52% to 64% and the Dutch from 52% to 65%.

**The Eurostat code had to be checked.** The old COICOP code `071120` and the plausible-looking
`CP071120` both return an empty dimension. The live code under COICOP 2018 is **`CP07112`**
("Second-hand motor cars"), unit `I15` (2015=100), on dataset `prc_hicp_midx`. The INSEE series
001763645 is labelled "Séries arrêtées" but still returns data to December 2025.

## Streamed, never stored: UK DVSA anonymised MOT (added 2026-09-21)

The readiness engine's layer 2 and its learned model both need a fleet-wide odometer, and the UK
MOT register is the only European source that publishes one. It is **not** in `data/` and never
will be: the 2024 and 2025 releases are **4.5 GB each**. `mot_stream.py` serves byte ranges to
Python's `zipfile` so only what is read is fetched, and nothing but the small panel above is
written to disk.

| What | Detail |
|---|---|
| Coverage | Every MOT test in Great Britain, 2005 to 2025. ~38m tests a year |
| Fields | test and vehicle id, date, class, type, result, **odometer**, postcode area, make, model, colour, fuel, engine size, date of first use |
| Licence | Open Government Licence v3.0 |
| Identity | `vehicle_id` is derived from the registration and the VIN and **is stable across releases** - verified in `analysis/readiness_mot_id_report.md` |

**Three things about the files that cost time:**

- **The releases are not one format.** 2024 and 2025 are comma-separated, carry a `completed_date`
  and are split into **stored** monthly members, so any month can be range-read on its own. 2022
  and 2023 are **pipe-separated, 14 columns, deflate64**, one member each, **sorted by test date** -
  so a prefix of those is a January sample, not a random one. Deflate64 needs `zipfile-deflate64`.
- **The May 2025 release of test year 2024 is heavily duplicated** - 1,520,095 rows for 957,030
  distinct tests in one month. The June 2026 release is clean. Use the newer one.
- **`vehicle_id` must never be sampled on directly.** It is stable but not a uniform hash, and its
  structure tracks the car: even ids are 31.8% of the file and average **16.3 years and 101,410
  miles** against **6.9 years and 51,667** for odd ids. Ids *are* uniform mod 3 and mod 5, so a
  count check passes and an attribute check is the one that catches it. `readiness_model.mix()` is
  a splitmix64 of the id and samples cleanly.

## What the data supported (analysis, 2026-09-17)

The drivers analysis (`analysis/drivers.py`) used **17 of the 30 sources, 3,039,150 used cars** before
the audit; after it, **16 of the 29 sources, 2,617,260 used cars**.
The other 13 were not rejected as bad data: each one is either a different kind of price or too
thin for a within-model estimate. This is the honest coverage picture.

| Not used | Why |
|---|---|
| `us_wa_ev_sales` (425,974), `us_ebay_2006` (45,811), `us_carsandbids` (26,975), `ca_gcsurplus` (21,408) | Sale and auction prices, not advertised prices. Analysed separately, never mixed in. |
| `nz_findcars` (20,167) | Its mileage is deliberately not read (the publisher imputes it), and the model needs mileage. |
| `id_2025` (14,890), `uz_avtoelon` (2,618), `ng_cars45` (1,327), `bd_bikroy` (1,199) | Fewer than 5,000 rows survive the age / mileage / price filter. |
| `jo_jucars_2024` (9,380), `sg_sgcarmart` (7,931) | Too few cars per make-model group to measure a within-model effect. |
| `us_marketcheck_new` (1,000) | All new cars, so out of scope for a used-car model. |
| `us_marketcheck_used` (1,000) | Only 937 usable rows. Still the most valuable 1,000 rows we have, because of the MSRP column. |

**What the analysis found about the data itself**, from `analysis/lodo_report.md` and
`analysis/curve_report.md`:

- **More rows are not the point; the right market is.** A dataset whose market is also covered by
  another dataset loses only **2.8%** accuracy when its own data is taken away. A dataset that is
  the only one from its market loses **30.6%**. Another million Latvian cars does not teach you
  Egypt. Collecting a new *country* is worth far more than collecting more rows in a country we
  already have.
- **Accuracy saturates after about three datasets, but stability does not.** Going from one dataset
  to three cuts the error by 6.4%; three to fifteen adds only 2.3% more. Over the same range the
  spread of the age estimate falls from 2.52 to 0.10 percentage points. The case for having
  collected 30 sources is *confidence in the number*, not a better prediction.
- **Borrowing between markets pays only on thin slices.** At 100 local cars it cuts the error 14.7%
  and prevents an unusable model; by 250 cars the gain is under 1%.

So the honest ranking of what each source is worth: a **new country** beats a bigger file, a **new
price type** (sale, auction) beats another advert scrape, and a **new column** (MSRP, damage,
days on market) beats another row.

## Other candidates (not downloaded)

| Dataset | Why not used |
|---|---|
| [US used cars (CarGurus, 3M)](https://www.kaggle.com/datasets/ananaymital/us-used-cars-dataset) | US, Sept 2020, 2.13 GB zipped (too big for our disk) |
| [Craigslist vehicles](https://www.kaggle.com/datasets/austinreese/craigslist-carstrucks-data) | US, 2021 |
| Rebrowser [CarGurus](https://huggingface.co/datasets/rebrowser/carguruscom-dataset) / [AutoTrader US](https://huggingface.co/datasets/rebrowser/autotrader-dataset) | Free part is a 30,000-row sample of the last 30 days; full data is paid and starts late 2025 |
| [10 million used car listings](https://www.kaggle.com/datasets/zsarpong/10-million-used-car-listings) | Description says "synthetic augmentation" |
| [Germany cars (ZenRows)](https://www.kaggle.com/datasets/ander289386/cars-germany), [German Car Insights](https://www.kaggle.com/datasets/yaminh/german-car-insights), [Spain 2018](https://www.kaggle.com/datasets/harturo123/online-adds-of-used-cars), [AutoScout24 Feb 2020 sample](https://www.kaggle.com/datasets/promptcloud/autoscout-automotive-data), [EU used cars 40k](https://www.kaggle.com/datasets/alemazz11/cars-europe), [Dutch used cars](https://www.kaggle.com/datasets/pedro2025/used-cars-market) | Few columns, one day, likely duplicates, or no listing date |

## Recommendation for the value model

Updated 2026-09-17, after the analysis.

| Role | Data | Notes |
|---|---|---|
| **Main model** | **UK Oct 2022 (718,233 cars) + Latvia (680,025) + Poland ×4 (618,392)** | The three largest usable blocks. Latvia is the one to lead with: it is the only source with a real monthly series, Jan 2019 – Dec 2023. |
| **Change over time** | **`lv_ss`, 52 monthly snapshots** | The only dataset that can track the market month by month. Treat rows as observations, not cars: an advert that stays up appears every month. See `analysis/latvia_time_report.md`. |
| **Real sale prices** | **`us_wa_ev_sales` (425,974)** | Recorded transactions, not adverts, with a sale date. EV-only and US, so it is a separate study, never pooled with advert prices. |
| **Damage and residual risk** | **`nz_findcars` (20,167) + `us_carsandbids` title brands** | The only sources that say a car was damaged. |
| **EV stress test** | **UK Oct 2022 (9,867 used EVs) + `us_wa_ev_sales` (340,376 EV rows, 141,602 of them used sales)** | The UK set gives advert prices, Washington gives realised ones. |
| **Value retained vs new price** | **`data/reference/`: DVM (UK), RDW (NL), FIPE (BR), Marketcheck MSRP (US)** | Only the two 1,000-row Marketcheck samples carry a new price per row today; joining the reference tables is what makes this work at scale. |

The Poland-only plan in the previous version of this table is superseded: Poland's four snapshots
are still useful, but as four of seventeen studies rather than as the main model.

## Price-cut study (Step 3): what the data can and cannot do

### Why the planned setups fail (counted)

1. **Tesla's Jan 2023 cuts, Poland:** the last Poland data before the cut with Teslas is April–May 2021 (27 Model 3s, no Model Y). P2 (May 2022) has no Teslas at all. The gap is too long and the numbers too small.
2. **Tesla's 13–14 Apr 2023 cut, inside P3:** P3 is a scrape of active listings, so it's dominated by recently created ads. Used Model 3/Y listings created before the cut: **8**. After (14–23 Apr): 124. Other used EVs: 110 before, 1,490 after. Too few before the cut.
3. **German EV bonus 2016 (DE/CZ data):** EV labels are wrong and there is no country column. Not usable.
4. **UK Oct 2022:** one snapshot, no "after".

**Conclusion (superseded on 2026-09-17).** That was true of the Kaggle-only data. It is no longer
true: **`us_wa_ev_sales` has 141,602 used-EV sales with a real sale date, running continuously from
2012 to 2026.** That spans Tesla's January 2023 cuts with a genuine before period, a genuine after
period, and a natural control group of non-Tesla used EVs — the proper event study this section
says is impossible. It is US and EV-only, and the price field needs filtering (some rows have a
sale date written into the price column), but the design is available.

**The study has now been run** (`analysis/tesla_event.py`, `analysis/tesla_event_report.md`), and
the answer is a negative one. Comparing 9,060 used Tesla sales with 17,765 other used-EV sales
month by month, the Tesla premium over the rest of the used-EV market went from **+13.1%**
(Jan-Aug 2022) to zero by December 2022, then to **−5.4%** in the three months after the cut and
**−6.1%** for the rest of 2023. **About 68% of that repricing happened before the cut was
announced**, the slide starting in September 2022. Parallel trends fails, so no causal number can
be taken from this event, and the alternatives below remain the honest fallback for a
euro-per-euro pass-through figure.

What the study does establish is about timing rather than size: the used market repriced Teslas
months ahead of the manufacturer's announcement.

### Best available alternatives (ranked)

**A. Our own measurement, on real data (recommended): how UK list-price changes show up in used prices (DVM-CAR).**
- Use the 2018 UK adverts matched to each model-year's new entry price.
- Compare the same model across registration years whose list price was cut or raised. Hold age, mileage, body and fuel constant, with model and year fixed effects.
- Output: € of used price per € of new list price, with a confidence range.
- Real variation available (counted): 335 year-on-year cuts over 5%, and 8,693 ads for model-years right after such a cut, across 163 models.
- **Caveats:**
  - This measures lasting list-price changes, not short-term discounts.
  - A price change can come with a spec or trim change (entry price = cheapest trim).
  - UK 2018, not the merged group's market today.

**B. A published before/after measurement, cited as a cross-check (not ours).**
- [iSeeCars](https://www.iseecars.com/tesla-pricing-study) (US, >1.4M listings of 2020–2021 model years) compared 3–11 Jan with 15–31 Jan 2023, around Tesla's 13 Jan cut. Used Model 3 fell −5.2% (−$2,354) and used Model Y −5.0% (−$2,816).
  - It had no control group.
  - It reports that used Model 3 prices had already fallen 16.8% between Sept and Dec 2022.
- [Recurrent with Black Book](https://www.recurrentauto.com/research/tesla-price-cuts-drive-affordability-in-the-ev-market) (30 Oct 2023): Tesla cut new prices by about 25% over 2023. Used Model 3/Y wholesale values fell about $21,000 from Oct 2022 to Oct 2023, and the wider EV market lost about 22% in 2023.
- To turn these into a € per € figure we still need sourced US new-price cut sizes per trim. Any ratio will be rough, with no control group.

**C. Paid data for a proper Tesla event study:** full historical listings, e.g. Marketcheck (not checked: price and coverage unknown).

### Documented price cuts (for reference)

| Event | Date | Size | Source | Status |
|---|---|---|---|---|
| Tesla cuts, Poland | article dated 16 Jan 2023 | Model 3 base 244,990 → 219,990 PLN (−10.2%). Model 3 versions −6.9% to −10.5%. Model Y −9.1% to −17.5%. | [autokatalog.pl](https://autokatalog.pl/blog/2023/tesla-obnizki-cen-w-polsce-2023) | One source opened |
| Tesla cuts, US and Germany | 13 Jan 2023 | Germany about 1–17% by configuration; US 6–20% (Reuters calculations) | [CNBC](https://www.cnbc.com/2023/01/13/tesla-cuts-prices-in-us-and-europe-to-stoke-sales.html), [CNN](https://www.cnn.com/2023/01/13/business/tesla-price-cuts/index.html) | From search summaries; pages blocked for me |
| Tesla cuts, Europe | night of 13–14 Apr 2023 | 5–10% on most trims in most countries (per search summary) | [Electrek](https://electrek.co/2023/04/14/tesla-cuts-prices-on-model-3-model-y-by-up-to-10-in-europe-elsewhere/), [InsideEVs](https://insideevs.com/news/662432/more-tesla-price-cuts-10-percent-europe-abroad/) | To confirm, including the size in Poland |
| German EV bonus starts | cars registered from 18 May 2016; applications from 2 July 2016 | half paid by government, half by the maker | [BAFA](https://www.bafa.de/SharedDocs/Pressemitteilungen/DE/Energie/2016_16_emob.html) (now 404), [Wikipedia (de)](https://de.wikipedia.org/wiki/Umweltbonus) | Not needed now (data unusable) |

## Practical notes

- **Disk:** 1.8 GB free after downloads. Deleting DE/CZ frees 420 MB, and converting the CSVs to Parquet frees much more.
- **Kaggle:** the CLI signs in with the user's own token at `~/.kaggle/access_token`.
- **Licenses:** all are scraped listings, and the Kaggle license is the uploader's claim. P4 is "Unknown". DVM-CAR is non-commercial only. Cite each source on slides.
