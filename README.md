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
> Stellantis.** "€206m a year expected at risk, €298m in a one-in-ten-year market" are modelled
> exposures under stated assumptions: none of the first and about three-tenths of the second rest
> on measured shocks, the rest on disclosed figures with rates we assume, on published studies and
> on assumptions we label as ours. It is not a statement about that company's actual
> performance, controls or results, and nothing here is investment advice.

---

## The rule we worked to

**No number is invented.** Every figure is one of five things, and `assumptions.csv` says which:

| Tier | What it means | Count |
|---|---|---|
| `MEASURED` | our own analysis, re-read out of the report that produced it | 456 |
| `SOURCED` | published, with a URL | 354 |
| `ASSUMPTION` | our judgement, with a low, a high and a stated basis | 29 |
| `TARGET` | a level the team chose — a phase gate or a KPI threshold | 31 |
| `SYNTHETIC` | a result from one of our two prototypes, run on a made-up world (`leak1/`, `ledger/`): it tests the tool and says nothing about the group | 50 |

Two scripts keep that honest rather than promising it:

- **`check_assumptions.py`** re-reads all 920 figures out of the exact table cell or sentence
  the `anchor` column names, and fails if one has drifted or come from the wrong row. We test it
  by substituting values from neighbouring cells; it rejects them.
- **`audit_workbook.py`** recomputes every workbook output with formulas written independently
  of the builder — **3,122 checks, 0 problems** — and refuses to let a `TARGET` or `SYNTHETIC`
  figure feed a value-at-risk formula, so neither a commitment nor a made-up figure can be quoted
  as evidence.

---

## What we measured

**3,879,498 used-car listings · 29 public sources · 31 countries.** Every headline is an
advertised-price result unless marked realised, and we say so. Each claim below carries the caveat it must travel with.

| Claim | Figure | Caveat |
|---|---|---|
| A residual value is mostly a bet on the market, not on the car | Over three years the market level moves **26.5** points of list price; the depreciation curve **3.5**. Three to eight times: about 8× on the whole spread, about 3× on the downside alone (p10 **−10.0%**), the only side a buy-back book bears | Official price indices, not realised prices; the 36-month windows overlap. The spread is the error of assuming the level never moves; one residual guide's own record against that is in [`level_guide_report.md`](case4-value-model/analysis/level_guide_report.md) |
| The shape of depreciation travels between markets; the price level does not | Shown three independent ways — across datasets, across time, and on one car | All three use advertised prices |
| Age alone costs a used car about 9% a year | **−9.2%**, 16 datasets, 2,617,260 cars | Mileage held fixed. A lease-age car that is also being driven loses about 12% |
| Twenty-five current cars recover almost everything a full refit could | 2018 model on 2022 cars: 41.4% error → **11.9%** re-anchored on 25 cars → 10.5% for a full refit. **96%** recovered, median of 500 draws | One model, one country, two different scrapes |
| The value engine's band is honest on cars it has never seen | The 80% band holds **80%** of held-out UK cars, 74–82% across age bands | Advertised prices; today's value only |
| **An electric car's residual risk is the market level, not a faster curve** | In Polish adverts the used-EV level fell **19** points against petrol between May 2022 and summer 2023, same model and age (**18** without Tesla; hybrids **3**). With the model held, EVs lose value no faster with age in 4 of 6 European sources, and the value engine prices today's EVs as well as petrol cars. On a long realised record EVs' bad year is about **3×** the market's | Asking prices; one slump in one market. The 3× is **US data** (Washington title transfers). Full working: [`ev_level_report.md`](case4-value-model/analysis/ev_level_report.md) |
| **A discount given at the new sale is still working against the car at resale** | A car bought **10%** below its model's usual price resells **3.1%** lower. **Every euro taken off the price costs another 18–47 cents** when the car comes back | **An upper bound.** See below |
| **A pricer's override band should follow the engine's own uncertainty** | The value engine's calibrated 80% band has a median half-width of **23%**, and **74%** of adverts lie more than 5% from its price. The band flags the engine's big errors: rank correlation **0.35** with the error, and the widest fifth of bands holds **35%** of all of it. Tied to that band at the same ±5% average, the cap runs from **3.4%** on 2–4-year-old cars to **8.2%** at 12 years and older, and in our model it is never worse than a flat ±5% | Advertised prices, held-out cars in 8 markets. The pricer is modelled: how much of the engine's error a pricer can see is unmeasured for cars, so it is swept. Behaviour comes from public experiments (Dietvorst et al. 2018; Poursabzi-Sangdeh et al. 2021, **US data**). Full working: [`override_band_report.md`](case4-value-model/analysis/override_band_report.md) |
| **The market level's price depends on who holds the option** | The group's buy-back contracts bring the cars back (20-F), so gains count against losses. Counted both ways, a 12-month contract in the core markets costs nothing on average (**−1.15%** of the residual, a gain), against **1.04%** if only losses counted. Started with the level in the bottom third of its gap to its three-year average, it costs **1.01** points of residual more (**0.93** on the UK's 1988–2026 record) | Official price indices (retail, overlapping windows), core markets with their full series. Relative, not a loss on average: a cold start is about break-even both ways in the core markets. The group's own book is too short to test. Full working: [`level_price_book_report.md`](case4-value-model/analysis/level_price_book_report.md) |
| **Most of the group's sales can't be checked against a public register** | An independent per-car check of a dealer's sale is open in markets holding **37.2%** of the group's 2024 EU registrations: Spain and Italy answer anyone per car for a fee (Italy three a day per tax code), and only the Netherlands in bulk (**2.1%**). France and Germany, two of its three largest markets, are closed to it (**45.9%** with Finland): Germany's register answers only road-traffic claims, France's history report only its holder | Six markets' routes checked at source; the rest (**16.9%**) not checked. EU register, so no UK. A route still needs its GDPR basis (fraud prevention). Full working and the source-by-source map: [`data_reach_report.md`](case4-value-model/analysis/data_reach_report.md) |
| **Built any of four ways, the programme pays for itself on large software projects' record, and funding phase by phase with a named stop caps the loss when it doesn't** | At plan the levers we count (claims controls, retention at the upgrade moment, resale execution) earn **€87.0m** a year across Europe, **€72.2m** after large software projects' average benefit shortfall (McKinsey–Oxford: 17%). One work list, priced four ways, costs **€15.2m** to **€30.9m** to build; none is chosen. On that record, with its 66% cost overrun and phases a third longer, the programme pays back at month **19** to **24** and is worth **€95m** to **€118m** over five years at the group's highest pre-tax WACC (19%). In every build scenario no single assumed rate breaks it, and it survives losing **66–81%** of all its benefits at once. The exit gate is derived from it: **€58m** a year in the markets live at month 24, not the old €80m | Every counted rate is our assumption over a disclosed or measured base, so nothing is certified before the pilot. The reference class is IT projects across industries (2012), not carmakers' data programmes. It fails Flyvbjerg and Budzier's stress (five times the cost, a quarter of the benefits: **−€27m** to **−€95m** over five years; stopping at the first gate loses **€20m** to **€40m**), and at our own ranges' adverse ends together it is about break-even built in-house (**€1–2m**) and negative bought (**−€21m**). Without the joint ventures' data the gate is **€32m**. Full working: [`benefits_case_report.md`](case4-value-model/analysis/benefits_case_report.md) |
| **Every gate can be read inside its own phase, and each says in advance what happens if it's missed** | Phase 1: an audit of **179** flagged claims settles duplicate precision (if the true precision is 95%) and **119** seeded duplicates settle recall; below a certified leak rate of **0.60–1.22%**, depending on the build scenario, the programme starts with residual value instead. Phase 2: **€2.0–4.0m** a year of claims recoveries certified in the pilot market releases Phase 3's funding, and the retention pilot takes **46%** of France's contracts ending in the phase's first half, with one interim look costing **0.8%** more customers. Phase 3: **246** returned cars test the engine's band and about **1,500** its error against the bought guide, out of an order of **120,000** returns in the core markets; below **€11–20m** a year certified (the floor, by build scenario), Phase 4 is not funded | Sizes are for hypothetical true values at 95% confidence and 80% power, set before each phase; the engine's spread is a normal approximation, the returns an order of magnitude, and France's endings assume a steady book. A pilot that lands on its gate has a lower bound of **0.6** points, and that, not the estimate, enters the benefits case. Full working: [`gates_report.md`](case4-value-model/analysis/gates_report.md) |
| **Realised: the group's own used-car prices move with the market level** | Aramis Group, **60.54%** owned by Stellantis, publishes what it is paid per car each quarter. Its year-on-year change correlates **0.73** with the official indices at its country weights (**0.82** without France, whose index lags), and swings wider: **+30.3%** against **+9.3%** in April–June 2022 | Realised retail prices, but an average over Aramis's own mix (country, age, price range); 17 quarters, one boom and one normalisation. In Germany, average asking prices turned about a year after average prices paid (X10) |
| **Realised: a returned car's trade price sits a bounded distance below retail** | A retailer that buys at trade and sells at retail earns the gap on the same car, so its audited accounts bound it. For a young car, trade sits **2.7%** to **18.4%** below the retail price: the floor from Motorpoint (UK, which buys nearly new cars mostly through fleet and bulk channels; its commissions taken out), the ceiling from Aramis (the group's own retailer, its services earning nothing). The value engine's typical error, **10.5%**, lies inside. Trade and retail move about one for one over a year, trade **2** months first; trade fell further only in the 2008 and 2022 slumps | Audited averages over each retailer's mix, not the group's returns; a discount off the asking price comes on top. The one-for-one result is **US data** (Manheim wholesale against the US CPI for used cars). Phase 2 measures the gap on the returns. Full working: [`trade_gap_report.md`](case4-value-model/analysis/trade_gap_report.md) |
| **Every residual guide we checked forecasts the market level, and only one publishes its record** | ALG's patented method adjusts its depreciation curve with forecast housing prices, real wages and fuel prices; J.D. Power, which owns ALG and since March 2024 Eurotax, Glass's and Schwacke, names inflation and supply shortages; the lessor ALD (now Ayvens) set residuals from its own sales, trade guides and country factors. So splitting the curve from the level is the industry's practice, not our insight: what we add is not paying for the level forecast | A patent and product pages describe methods, not today's production models. The one published record is cap hpi's (UK, scored against its own guide values). Sources in the register (`alg_method_patent`, `jdpower_*`, `ald_rv_setting_method`) |

### The discount pass-through, in detail

This is the one thing the case asks for that a market-level analysis cannot answer, so most of
the work went into showing why, and then finding a way round it.

- **The market-level test fails, and not just once.** Across **32 European markets and ten
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
| **Mileage predicts disposal, not sale** | Twice a cohort's mileage makes a car **1.54×** as likely to leave the UK fleet and **1.03×** as likely to be advertised. The disposal half replicates in Finland's register: at 10–20 years, where both inspect yearly, **1.84×** against the UK's **1.91×** | 3,039,129 MOT-tracked cars; "not tested again" mixes scrappage, export and laid up. Finland: three yearly Traficom snapshots, cars followed on fixed attributes; leaving traffic use includes lay-ups. The sale half is UK-only |
| **No spike at 36 months; a clear wave at 60 months and a weaker one at 48** | Excess adverts at 36 months: **−16.9%** (−31.4% to +0.7%), negative in all twelve specifications tried. In the Dutch register (X3, `analysis/lease_end_report.md`), excess keeper changes against the local age trend: **+10.3%** at 36 months (placebo p 0.19), **+42.5%** at 48 months (p 0.06), **+71.1%** at 60 months (p 0.02), and the 60-month wave recurs in cars registered in 2018-19 | Adverts smear the date, so only the register shows the waves. A keeper change is a car coming to market, not a customer deciding. The cause (lease terms, a company-car tax lock) is not verified |

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
  96% European; every sale and auction price we hold is North American. The gap to trade is bounded from
  retailers' audited accounts instead (the claims table).
- **Public data can't say whether the group spends too much on incentives on average.** Demand models assume prices
  already maximise profit, and discount series rise when demand falls, so neither can test it. The one long-run
  study we found (**US data**, 1996–2001) saw carmakers' promotions raise firm value for **43%** of brands, against
  **81%** for new models: a direction, not a figure for the group. The pilot's randomised holdout measures it, and we
  count nothing for it ([`benefits_case_report.md`](case4-value-model/analysis/benefits_case_report.md)).
- **Depreciation did not speed up or slow down** through the 2021–22 shortage — 52 monthly refits
  all between −13.2% and −11.7% a year. The level moved instead.
- **One claim we withdrew after auditing ourselves.** We had argued that what transfers between
  markets is market coverage rather than row count. Inside Europe it does not hold.
- **Uplift modelling did not beat an ordinary response model** on two public randomised trials:
  Hillstrom's e-mail trial (64,000 customers) and a 20% sample of Criteo's advertising holdout, adjusted
  for its slightly unequal arms. In the top tenth the best uplift model differed from the response model
  by −0.14 points on Hillstrom (range −3.4 to +2.9) and +0.29 on Criteo (range −0.24 to +0.84).
  Refitted ten times on subsamples of Hillstrom's training half, the two uplift models averaged +6.2
  and +7.5 points in the top tenth against the response model's +8.8; a random tenth gives +6.8. A
  third benchmark, Lenta's SMS data, failed our randomisation test, so it counts for nothing either way
  ([`uplift_engine_report.md`](case4-value-model/analysis/uplift_engine_report.md),
  [`uplift_second_report.md`](case4-value-model/analysis/uplift_second_report.md)). So the
  recommendation is to build the measurement first and let it decide, not to assume the technique pays.
- **Nothing public predicts which car comes to *market*, beyond its age.** Two independent
  methods agree: a mileage elasticity of 1.03× per doubling, and a classifier free to use make and
  fuel that gains **+0.009** from the odometer. Getting there needed one artefact closed first —
  **30.9% of advert mileages are exact multiples of a thousand miles against 0.11% of MOT
  readings**, so a classifier can identify the *file* from the digits and score a meaningless
  0.737.
- **People give a model the same weight whether it is right or badly wrong.** In a public experiment where
  lay people priced New York apartments (**US data**), the median weight on the model's price was **0.50** both on
  typical apartments and on the one it overpriced by 85%. On that one, **79%** of their own first prices were closer to
  the sale price than the model's. A band tied to the model's uncertainty only helps if the uncertainty flags such
  errors: there, a local uncertainty measure missed it and bought nothing
  ([`band_replay_report.md`](case4-value-model/analysis/band_replay_report.md)).
- **Our own listings cannot price one national market.** Asked for the value of the cars changing
  hands in the Netherlands, our Dutch adverts say €30.9bn and official catalogue prices say
  €12.9bn — a 2.4× overstatement, because that scrape is premium dealer stock. Pooled across many
  sources our listings give good shapes; in one country they give a bad level.

---

## The value-at-risk model

`Case4_Value_at_Risk.xlsx` is live formulas over `assumptions.csv` — no number is typed into a
formula, and moving any assumption to its bound moves every downstream figure.

**Two measures, side by side and never added: €206m expected a year; €298m in a one-in-ten-year
market; €456m under the stress.** Per car shipped, €83 and €120. The first is what to budget, the
second what a bad year costs: an expected loss is a cost, a tail is held by a price or by capital
(the Basel convention). The two differ only in leak 3's market level and depreciation curve
([`headline_measures_report.md`](case4-value-model/analysis/headline_measures_report.md)). The
group's buy-back contracts bring the cars back (a repurchase obligation, or a customer's put
expected to be exercised: 20-F), so a rising market pays for a falling one. On the book's own
2016–2025 record the level and curve *gained* on average, so they add nothing to the expected
figure. One year in ten they cost €92m: their joint p10, about seven-tenths of their two p10s
added, because adding them describes a year in which both fail at once, rarer than one in ten.
Both upper ends are shown, in no total: €267m expected if every buy-back were a customer's put
struck at the residual, and €340m, our earlier single figure, if the level and the curve failed
together (€504m under the stress).

In the one-in-ten figure, 31% rests on disclosed figures and measured shocks (leak 3's level and
curve). 8% is value lost in the resale itself, measured costs over an assumed reach: a day a
returned car waits and the group's own retail margin over the trade are measured, the days cut and
the share of returns retailed in-house are ours
([`time_in_stock_report.md`](case4-value-model/analysis/time_in_stock_report.md),
[`recovery_levers_report.md`](case4-value-model/analysis/recovery_levers_report.md)). 26% is
incentive claims paid wrongly: the claims are the group's own, from the sales-incentive provision
in its 20-F (worldwide; no regional total is disclosed), and the share paid wrongly is our
assumption ([`incentive_anchor_report.md`](case4-value-model/analysis/incentive_anchor_report.md)).
13% is upgrade moments missed, on the contracts the group's finance arm reports and an assumed
conversion. The last 21% is what paying every buyer the same incentive costs, derived from
published studies
([`optimal_incentive_report.md`](case4-value-model/analysis/optimal_incentive_report.md)). **None
of the expected figure is measured:** it rests on disclosed bases with rates we assume and on that
derived targeting line. What we measured best is a tail. The targeting line replaced an assumed
line of €462m; without it, the two figures are €142m and €234m. Whether the group spends too much
*on average* is not sized: public data can't say, and only the pilot's randomised holdout can.

The **Internal prices** sheet turns the ledger into decisions, with no figure added to the totals
(they are transfers inside the group). One more euro of discount costs the group €1.18–1.47 once
its resale cost on a car the group takes back is counted, so that cost is charged to the sales side
at sale: paid on a margin that includes it, the sales side's own best discount is the group's
(Weinberg, 1975), and the group already pays its leasing programmes subvention that its 20-F says
rises when residuals fall. Pulling an upgrade 12 months forward on the sample car *raises* the
finance arm's margin by €273 if the customer refinances with the group, and costs it €55 if not,
of which the EU's new early-repayment cap lets it recover €14. So the decision turns on how many
customers an offer wins that would not have come back anyway, which the pilot's holdout measures.
The operating metric is predicted lifetime value at sale, and its audit arrives in time: 67% of the
buy-back book comes back within a year.

The **Data reach** sheet shows what each lever can work on when a data source is missing. With
every source, 78% of the expected figure is within reach; without the joint ventures' data, 52%
(leak 2 needs their contract dates and customer consent, and a partner's marketing opt-in never
passes to the group); without dealers' VIN-level proof of sale, 54% (leak 1's claims then rest on
the few registers that answer per car). Leak 3 needs no partner: the buy-back book is the group's
own, and under the EU Data Act the rental firm or leasing company is the car's "user", so a clause
in the group's own contracts reaches a returned car's data.

The **Benefits** sheet turns reach into what the programme gets back, with no figure added to the totals. Each euro
sits in one class: *recovered* (claims controls, retention, resale execution: €87.0m a year at plan), an *upper bound*
that needs a randomised holdout (income targeting, shown and never committed), or the *tail cut* one year in ten
(little-history cars priced as known cars). The level charge is a price, not a saving, and the internal prices are how the counted
levers happen, so neither carries a euro of its own. Benefits start phase by phase in the markets live: France in
Phase 2, the four core markets (81% of the group's EU registrations) in Phases 3 and 4, every market after month 24.
The case is tested the way the UK Treasury's Green Book asks, since it sets no default for a benefit shortfall and asks
for switching values instead: against large software projects' record (McKinsey–Oxford: 66% over budget, 33% late, 17%
short of benefits), against Flyvbjerg and Budzier's stress (400% over budget, a quarter to half of the benefits) and
against our own ranges' adverse ends. **The exit gate is derived, not chosen:** what the counted levers earn in the
markets live at month 24 on that record, €58m a year with the joint ventures' data and €32m without it. The old €80m,
"about four times" the old single ask, sat above what our own plan earns there. Below the floor, €11m to €20m
a year depending on how the programme is built, the case is worth nothing: the named stop.

Every gate is read inside its own phase, on data that phase produces, and each has its outcome agreed before the
programme starts: go, waive with a re-review, delay, switch to a back-up plan, or stop. Two old gates were retired. A
cut in the cost of residual error could not be read for 36 to 48 months, when the contracts come back. Adherence to
the engine is 100% by construction when pricers work inside a hard band. In their place, the engine is tested on the
cars the buy-back book returns now, and the band is set from pricers' first proposals, logged before the cap. A
retention pilot that only just passes overstates its effect, so the benefits case takes its lower bound. And money,
not only data quality, releases Phase 3's funding: claims recoveries certified in the pilot market. Three gates
depend on build cost (the leak rate that reorders the work, the money gate and the floor), so each has one value per
build scenario.

The **Programme cost** and **Work list** sheets price the build. One work list (90 rows: eleven workstreams, four
phases, ten roles; 816 person-months, 34 people on average) is costed four ways, and none is chosen: in-house at
Eurostat's loaded cost of employing each role's occupation group in manufacturing, €15.6m; bought, at a public
integrator's rate card (Deloitte's G-Cloud 14 maximum rates, UK: a ceiling), €30.9m; in-house with AI, at the gains
the studies measured on the task types they measured, €15.2m (€14.9m at the largest measured gain, €15.8m if AI slows
experienced developers as in METR's trial); and each workstream's cheapest of the three, €15.2m, since at rate-card
prices every workstream is cheapest in-house with AI. Platform (€4m) and change delivery (€3m) are the same in every
scenario and are still our own unquoted assumptions, nearly half of an in-house build. Handing work over becomes cheaper only if an integrator bills below about €575 a day across every role it
takes. Speed can outweigh cost: an integrator for Phase 1 pays if an in-house team would start more than 0.8 months
late (1.7 on large software projects' record), and no public source gives months to hire. Between 28% and 44% of the
build can be capitalised under the group's own policy. The effort in each row is our assumption, with its basis;
COCOMO II.2000 puts the engineering part at 25.7 months' nominal schedule, so 24 months is a mild squeeze
([`programme_cost_report.md`](case4-value-model/analysis/programme_cost_report.md),
[`work_list_report.md`](case4-value-model/analysis/work_list_report.md)).

In a one-in-ten-year market, leak 3's market shock is the group's own book's one-in-ten-year fall,
its markets weighted as it sells. The stress is a Europe-wide bad year as deep as a core market's one-in-ten, which the
book's nine years of index history do not contain. It is not extreme: the UK market as a whole
fell further than that one year in ten over 1988–2026
([`merger_diversification_report.md`](case4-value-model/analysis/merger_diversification_report.md)).

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
.venv/bin/python analysis/readiness_events.py     # the advert test: no bulge at 36 months
.venv/bin/python analysis/lease_end.py            # the register: waves at 48 and 60 months
.venv/bin/python analysis/lease_timing.py         # layer 3, the monthly timing (holdout-tested)
.venv/bin/python analysis/readiness_market.py     # layer 4
.venv/bin/python analysis/self_registration.py    # leak 1: dealer self-registrations in the register
for s in merger_fingerprint merger_events merger_composition merger_kba; do \
    .venv/bin/python analysis/$s.py; done         # leak 1: the merger's fingerprint (X2)
.venv/bin/python analysis/readiness_value.py      # readiness x value
.venv/bin/python analysis/uplift_engine.py        # the uplift engine
for s in agency_share aramis_prices asking_vs_paid_de band_replay conformal_bands data_reach \
         entity_resolution ev_bands ev_exposure ev_level ev_level_us fi_exit fi_register \
         headline_measures incentive_anchor keeper_history lease_mechanism level_charge \
         level_forecast level_guide level_indicators level_long level_price_book level_professional \
         level_regimes merger_diversification merger_fuel merger_italy merger_italy_images \
         optimal_incentive override_band pilot_markets pilot_size readiness_advert_model \
         readiness_model recovery_levers time_in_stock trade_gap upgrade_window uplift_second \
         programme_rates work_list programme_cost; do \
    .venv/bin/python analysis/$s.py; done         # the later questions, in this order; a few take 10-20 min
.venv/bin/python check_assumptions.py  # every figure traces to its stated source
.venv/bin/python build_var_model.py    # rebuilds the workbook
.venv/bin/python audit_workbook.py     # recomputes every workbook output independently
.venv/bin/python analysis/benefits_case.py   # the benefits case, checked against the workbook's stored values
.venv/bin/python analysis/gates.py           # the gates, read through the benefits case
```

`self_registration.py` and `keeper_history.py` query the Dutch register live, with no cache, so a re-run
reflects the register as it is that day and can move their figures slightly (keepers change); their reports are
dated to their pull. Every other script re-runs to the same report.

Some sources need a Kaggle login. The analysis loop order matters: `drivers` and `latvia_time`
write CSVs that `level_risk` reads, and `level_risk` writes one that `what_matters` reads.

**The two prototypes.** `leak1/` builds a synthetic leak-1 world (real Dutch registrations from
RDW, with made-up VINs, dealers, claims and finance contracts: `population.py`, `generate.py`,
`inject.py`) and runs the claims detector on it (`layer1_keys.py`, `layer2_splink.py`,
`layer3_rules.py`). `ledger/` builds the vehicle value ledger from that world (`store.py --rebuild`,
`decisions.py`, `remark.py`, `readiness.py`, `returns.py`, `pnl.py`). Each script's docstring gives
its usage. Their figures are the `SYNTHETIC` tier: they test the tools, never the group. Without
our cache, `returns.py --pull` reads the Dutch register live, so its dates move with the register
as above; `runtime.py`'s seconds depend on the machine.

Two of their reports can be read here but not re-run. `scorecard.py` sets the detector beside
blind red-team rounds, which were scored on code frozen in a local history that is not published,
against worlds built by the red team's own scripts, which stay private. `layer4_llm.py score` reads
LLM answers (Claude agents, one batch file each) cached with the private data.

### Layout

| Path | What it is |
|---|---|
| `case4-value-model/loaders/` | one module per data source — `INFO`, `download()`, `load()`, auto-discovered |
| `case4-value-model/analysis/` | one script and one report per question |
| `case4-value-model/assumptions.csv` | every input with its tier, source, anchor and caveat |
| `case4-value-model/value_engine.py` | `predict_value()` — a value, an 80% band, and which uncertainty drives the band |
| `case4-value-model/readiness_engine.py` | `readiness()` — the chance a car comes to market, and `rank()` for a whole book |
| `case4-value-model/mot_stream.py` | reads the 4.5 GB UK MOT archives over HTTP range requests, storing none of it |
| `case4-value-model/leak1/` | leak 1's claims detector and the synthetic world it is tested on, one report per part |
| `case4-value-model/ledger/` | the vehicle value ledger prototype: an append-only event store with one record per car, and its reports |
| `case4-value-model/ledger/dashboard/` | the ledger's dashboard: open `index.html` in a browser. The group's figures come from the register and the workbook; the prototype's are real Dutch cars, dates and catalogue prices with synthetic claims, contracts, buyer labels and resale prices. `export.py` writes its data, `npm run build` in `app/` the page |
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
- **The prototypes' worlds and store.** Rebuilt by the scripts in `leak1/` and `ledger/`, except
  the red-team worlds and the cached LLM answers (see *The two prototypes* above).
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
remain under their own licences and are not redistributed here. The dashboard's page also
carries third-party code, icons and the IBM Plex Sans fonts, each under its own licence: see
`THIRD_PARTY_NOTICES.txt` and the `LICENSE-*.txt` files beside it in `ledger/dashboard/`.

**Affiliation and accuracy.** Independent student work for a case competition, not affiliated with
or endorsed by Capgemini or Stellantis. Stellantis is used as a public same-scale proxy for the
case's anonymous group; figures derived from its disclosures are cited to the filing they come
from, and any error in reading them is ours. Trade marks belong to their owners. Provided as-is,
with no warranty — see `LICENSE`.
