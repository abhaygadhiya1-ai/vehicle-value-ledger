# Follow the Euro, Car by Car

The evidence behind our answer to **Case 4 — Data & AI Strategy for an Automotive Merger**
(Capgemini L'Innovateur 9.0, Round 1).

This repository is here so that every number on our slides can be checked. It holds the code,
the analysis reports and the value-at-risk workbook. It does not hold the slides, and it does
not hold the raw data — see [What is not here](#what-is-not-here).

---

## The rule we worked to

**No number is invented.** Every figure is one of four things, and `assumptions.csv` says which:

| Tier | What it means | Count |
|---|---|---|
| `MEASURED` | our own analysis, re-read out of the report that produced it | 80 |
| `SOURCED` | published, with a URL | 23 |
| `ASSUMPTION` | our judgement, with a low, a high and a stated basis | 22 |
| `TARGET` | a level the team chose — a phase gate or a KPI threshold | 19 |

Two scripts keep that honest rather than promising it:

- **`check_assumptions.py`** re-reads all 144 figures out of the exact table cell or sentence
  the `anchor` column names, and fails if one has drifted or come from the wrong row. We test it
  by substituting values from neighbouring cells; it rejects them.
- **`audit_workbook.py`** recomputes every workbook output with formulas written independently
  of the builder — **574 checks, 0 problems** — and refuses to let a `TARGET` feed a
  value-at-risk formula, so a commitment can never be quoted as evidence.

---

## What we measured

**3,879,498 used-car listings · 29 public sources · 31 countries.** Every headline is an
advertised-price result and we say so. Each claim below carries the caveat it must travel with.

| Claim | Figure | Caveat |
|---|---|---|
| A residual value is mostly a bet on the market, not on the car | Over three years the market level moves **26.5** points of list price; the depreciation curve **3.5**. About 8× | Official price indices, not realised prices; the 36-month windows overlap |
| The shape of depreciation travels between markets; the price level does not | Shown three independent ways — across datasets, across time, and on one car | All three use advertised prices |
| Age alone costs a used car about 9% a year | **−9.2%**, 16 datasets, 2,617,260 cars | Mileage held fixed. A lease-age car that is also being driven loses about 12% |
| Twenty-five current cars recover almost everything a full refit could | 2018 model on 2022 cars: 41.4% error → **11.9%** re-anchored on 25 cars → 10.5% for a full refit. **96%** recovered, median of 500 draws | One model, one country, two different scrapes |
| The value engine's band is honest on cars it has never seen | The 80% band holds **80%** of held-out UK cars, 74–82% across age bands | Advertised prices; today's value only |
| **A discount given at the new sale is still working against the car at resale** | A car bought **10%** below its model's usual price resells **3.1%** lower. **Every euro of incentive costs another 18–47 cents** when the car comes back | **An upper bound.** See below |

### The discount pass-through, in detail

This is the one thing the case asks for that a market-level analysis cannot answer, so most of
the work went into showing why, and then finding a way round it.

- **The market-level test fails, and not just once.** Across **27 European markets and ten
  years** of Eurostat's new-car (CP07111) and second-hand (CP07112) indices, nothing follows a
  new-car price move (**−0.013**) and *more precedes it* (**+0.056**). Our earlier event study
  around a real manufacturer price cut failed the same way — 68% of the repricing came first —
  and its figures stay withdrawn. An index mixing every vintage also dilutes one cohort's
  discount roughly tenfold, so the test has little power even in principle.
- **The per-car link can be measured.** Washington State title transfers carry a realised price
  *and* a vehicle id, and a car can be sold more than once, so **35,552 resales are of cars also
  on record at their own new sale**. The question stops being "did the market move?" and becomes
  "did *this car*, bought at a deeper discount, fetch less?"
- **It passes a placebo the event study never had.** Give each car a second, fake discount — the
  deal its model was offering *twelve months after it was bought*. A car cannot be affected by a
  discount that had not happened yet, so that coefficient has to be zero. It is
  (**+0.033, t +0.7**), while the car's own deal holds at **+0.243**.
- **Caveats, which are not optional.** Our estimate is **an upper bound**: the source carries no
  trim field, so part of a cheap new price is a cheaper car. We sized that rather than waving at
  it — on AutoScout24 a pre-registered car looks **10.3%** cheaper than a new one on make and
  model, and **−1.1%**, indistinguishable from zero, once the exact version is matched. *A
  discount is invisible in market data.* The published UK figure (Holweg & Kattuman, auction
  prices 1999–2004) is 6.5% at 36 months plus 1.5% at once — about twice ours. **Quote the range,
  never one end.**

Full working: [`analysis/discount_passthrough_report.md`](case4-value-model/analysis/discount_passthrough_report.md).

### Results that are usefully negative

We state these rather than hiding them.

- **Advertised prices cannot be converted into sale prices from this data.** 3.4M advert prices,
  96% European; every sale and auction price we hold is North American.
- **Depreciation did not speed up or slow down** through the 2021–22 shortage — 52 monthly refits
  all between −13.2% and −11.7% a year. The level moved instead.
- **One claim we withdrew after auditing ourselves.** We had argued that what transfers between
  markets is market coverage rather than row count. Inside Europe it does not hold.

---

## The value-at-risk model

`Case4_Value_at_Risk.xlsx` is live formulas over `assumptions.csv` — no number is typed into a
formula, and moving any assumption to its bound moves every downstream figure.

**€913m a year at risk; €1,460m in the worst market year measured; €367 per vehicle.** A third
rests on disclosed figures and measured shocks; two-thirds on assumptions, mostly incentive
leakage — which is itself the point, because the group discloses no total incentive spend.

The **Prior discounting** sheet is a *decomposition, not a fourth leak*: those euros are already
counted, in leak 1 as spend and in leak 3 as residual exposure, and are cut there by cause
instead of by business. Adding them again would be double counting.

---

## Reproducing it

```bash
python -m venv .venv && .venv/bin/pip install -r case4-value-model/requirements.txt
cd case4-value-model
.venv/bin/python download_data.py      # fetches every source from its original home
.venv/bin/python build_unified.py      # ~2 min -> data/unified/listings.parquet
.venv/bin/python build_reference.py    # new-car prices and official price indices
for s in drivers lodo curve tesla_event latvia_time value_retained price_types \
         level_risk one_car what_matters field_sets engine_check one_model_gbm \
         discount_passthrough; do .venv/bin/python analysis/$s.py; done
.venv/bin/python check_assumptions.py  # every figure traces to its stated source
.venv/bin/python build_var_model.py    # rebuilds the workbook
.venv/bin/python audit_workbook.py     # 574 independent checks
```

Some sources need a Kaggle login. The analysis loop order matters: `drivers` and `latvia_time`
write CSVs that `level_risk` reads, and `level_risk` writes one that `what_matters` reads.

### Layout

| Path | What it is |
|---|---|
| `case4-value-model/loaders/` | one module per data source — `INFO`, `download()`, `load()`, auto-discovered |
| `case4-value-model/analysis/` | one script and one report per question |
| `case4-value-model/assumptions.csv` | every input with its tier, source, anchor and caveat |
| `case4-value-model/value_engine.py` | `predict_value()` — a value, an 80% band, and which uncertainty drives the band |
| `case4-value-model/DATASETS.md` | every dataset found, used or rejected, with reasons |
| `case4-value-model/METHODOLOGY_multi_dataset.md` | how many datasets are combined, step by step, each with its result |

---

## What is not here

- **The listings data.** 2.9 GB of raw files and a 97 MB unified table, and more importantly
  several sources carry no licence or a research-only one — see *"Licence to check before
  publishing"* in `DATASETS.md`. None of it is redistributed. The scripts rebuild all of it from
  the original sources, which is the stronger claim anyway.
- **The case material.** Capgemini's own, not ours to republish.
- **The slides and the written strategy.**
- **Our internal working notes** — the audit trail, the session handoff and the storyline. A few
  published files still refer to them by name; nothing depends on them to run.

One dataset in `loaders/` is **rejected and kept deliberately**: `fr_2023`, where a quarter of
the rows are generated. Its loader stays so the rejection stays visible.

---

## Sources and licence

Every dataset is listed with its origin and licence in `DATASETS.md`. Published figures we rely
on are cited with URLs in the reports that use them — principally Stellantis' FY2025 annual
report and Form 20-F, Eurostat HICP, ONS, INSEE, Washington State DOL, RDW, and Holweg &
Kattuman on discount pass-through.

Code is MIT (see `LICENSE`). The reports and figures are CC BY 4.0. The underlying datasets
remain under their own licences and are not redistributed here.
