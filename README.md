# Vehicle Value Ledger

One record per car, across the new-car business, the captive finance arm and the used-car
business. This is the evidence behind our answer to **Case 4 — Data & AI Strategy for an
Automotive Merger** (Capgemini L'Innovateur 9.0, Round 1), presented as *Follow the Euro,
Car by Car*.

This repository is here so that every number on our slides can be checked. It holds the code,
the analysis reports and the value-at-risk workbook. It does not hold the slides, and it does
not hold the raw data — see [What is not here](#what-is-not-here).

> **Please read this before the numbers.** This is student competition work. It is not affiliated
> with, authorised by, or endorsed by Capgemini or Stellantis. **The company in the case is
> anonymous.** We use **Stellantis as a same-scale public proxy** for it, because its scale and
> structure match the case and because its financial disclosures are public and checkable — which
> is the only way an outside team can build an evidenced answer at all.
>
> **The figures here are therefore a model of the case's fictional group, not a finding about
> Stellantis.** "€913m a year at risk" is a modelled exposure under stated assumptions, two-thirds
> of it resting on assumptions we label as ours. It is not a statement about that company's actual
> performance, controls or results, and nothing here is investment advice.

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

### When a car comes back: the readiness engine

A second engine, built the same way. `value_engine.py` says what a car is worth;
`readiness_engine.py` says when it becomes a transaction. The base rate comes from the Dutch RDW
register, which records for every car both its first admission and the date its **current keeper**
took it on — so the share of cars of each age that changed hands in the last twelve months is a
count over a count, out of one official file, at single years of age.

| Claim | Figure | Caveat |
|---|---|---|
| Replacement is not flat in age — it peaks at five years | **27.8%** of five-year-old Dutch cars change keeper in a year against **15.1%** at nine. **1.84×** | Dutch; a keeper change is not a customer deciding to replace |
| The peak is an age effect, not a lucky cohort | The register's previous twelve months, uncensored, put the peak at **five years too**, correlation **0.94** across ages | The un-censoring assumes one year is independent of the next |
| It matches a count made by somebody else | **1,931,085** keeper changes against BOVAG and RDC's published **2,124,429** Dutch used-car sales: **−9.1%** | Low in the direction the method predicts; treat the level as good to about ten per cent |
| **Mileage predicts disposal, not sale** | Twice a cohort's mileage makes a car **1.54×** as likely to leave the UK fleet and **1.03×** as likely to be advertised | 3,039,129 MOT-tracked cars; "not tested again" mixes scrappage, export and laid up |
| **There is no contract-end spike to find** | Excess adverts at 36 months: **−16.9%** (−31.4% to +0.7%), negative in all twelve specifications tried | Three European sources that record a registration month |

### Is any of it actually a model?

The two layers above are a measured rate times a measured multiplier — traceable, and not learning
anything. So we built the learned version on the only public data with a **per-car outcome**:
759,541 UK cars tested in March 2024 and looked for again through July 2025.

**It is built in tiers, and that is the design point.** Each tier is what a company knows at a
stage of joining its data up. Adding a tier is one line.

| Tier | AUC | **Same-age AUC** | Leavers in the top tenth |
|---|---|---|---|
| Age alone | 0.664 | 0.500 | 2.49× |
| + how far it has gone | 0.698 | 0.618 | 2.92× |
| + what the car is | 0.709 | 0.643 | 3.20× |
| + where it is, and how it just did | 0.712 | 0.648 | 3.20× |
| **+ last year's test** | **0.723** | **0.667** | **3.34×** |

**Read the same-age column.** A call list is built from cars of similar age, so the question is
whether the model can tell one twelve-year-old from another — and there, what the car *is* matters:
at twelve years old the share leaving the fleet runs from **5.3% for a Golf to 12.9% for an Astra**.
A global AUC hides that, because age already separates most pairs.

**The last tier is the proof.** A year of prior test history — the public stand-in for a service
record — arrived after the model was built and cost one line. Boosted trees beat a neural network
(0.723 to 0.703), and the model is calibrated within 0.8 points across all ten risk deciles.

**Its weakest slice is the one that matters.** AUC **0.615** on cars aged three to six, against
0.717 on eleven-to-fifteens. Public data can see why an old car dies — mileage, a failed test.
It cannot see why a young one changes hands, because that is a contract date and an equity
position. **The engine is weakest exactly where the company's own data would be strongest**, and
that is where the next tier goes.

That last one is the point. A three-year lease ending leaves no trace in any public advert — cars
come back, sit in a compound, get prepared, and reach a forecourt over the following weeks. **The
third layer of a replacement model exists only in the company's own contract dates**, and that is
now a measurement rather than an assertion.

### Results that are usefully negative

We state these rather than hiding them.

- **Advertised prices cannot be converted into sale prices from this data.** 3.4M advert prices,
  96% European; every sale and auction price we hold is North American.
- **Depreciation did not speed up or slow down** through the 2021–22 shortage — 52 monthly refits
  all between −13.2% and −11.7% a year. The level moved instead.
- **One claim we withdrew after auditing ourselves.** We had argued that what transfers between
  markets is market coverage rather than row count. Inside Europe it does not hold.
- **Uplift modelling did not beat an ordinary response model** on the one public trial with a
  genuinely randomised treatment (Hillstrom, 64,000 customers). Top-decile uplift **+8.6%**
  against **+8.9%** — a gap of −0.14 points, range −3.4 to +2.9. Every model beat sending at
  random; which model was used did not separate. So the recommendation is to build the
  measurement first and let it decide, not to assume the technique pays.
- **Nothing public predicts which car comes to *market*, beyond its age.** Two independent
  methods agree: a mileage elasticity of 1.03× per doubling, and a classifier free to use make and
  fuel that gains **+0.009** from the odometer. Getting there needed one artefact closed first —
  **30.9% of advert mileages are exact multiples of a thousand miles against 0.11% of MOT
  readings**, so a classifier can identify the *file* from the digits and score a meaningless
  0.737.
- **Our own listings cannot price one national market.** Asked for the value of the cars changing
  hands in the Netherlands, our Dutch adverts say €30.9bn and official catalogue prices say
  €13.0bn — a 2.4× overstatement, because that scrape is premium dealer stock. Pooled across many
  sources our listings give good shapes; in one country they give a bad level.

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
.venv/bin/python build_reference.py nlhazard      # Dutch keeper-change hazard by age
.venv/bin/python analysis/readiness_mot_id.py     # is the MOT vehicle id stable across releases?
.venv/bin/python analysis/readiness_base.py       # readiness layer 1
.venv/bin/python analysis/readiness_mileage.py    # layer 2 — ~25 min, streams 4.6 GB, stores none
.venv/bin/python analysis/readiness_events.py     # layer 3, the negative
.venv/bin/python analysis/readiness_market.py     # layer 4
.venv/bin/python analysis/readiness_value.py      # readiness x value
.venv/bin/python analysis/uplift_engine.py        # the uplift engine
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
| `case4-value-model/readiness_engine.py` | `readiness()` — the chance a car comes to market, and `rank()` for a whole book |
| `case4-value-model/mot_stream.py` | reads the 4.5 GB UK MOT archives over HTTP range requests, storing none of it |
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

**Affiliation and accuracy.** Independent student work for a case competition, not affiliated with
or endorsed by Capgemini or Stellantis. Stellantis is used as a public same-scale proxy for the
case's anonymous group; figures derived from its disclosures are cited to the filing they come
from, and any error in reading them is ours. Trade marks belong to their owners. Provided as-is,
with no warranty — see `LICENSE`.
