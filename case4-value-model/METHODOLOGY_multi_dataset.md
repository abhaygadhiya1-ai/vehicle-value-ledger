# How to use many car-price datasets together

> **Audit, 2026-09-17: results below are from before the audit.** It found duplicate UK adverts and a
> partly generated French dataset, fixed both, and re-ran every step. Superseded here: 4,334,195
> listings from 30 sources (now 3,879,498 from 29); 17 datasets and 3,039,150 cars in step 3 (now 16
> and 2,617,260, pooled −9.2%); step 7's 14.7% pooling gain at 100 cars (now 4.3%) and the +2.8% vs
> +30.6% sibling gap (now +2.7% vs +31.6%, and no gap inside Europe); UK value retained 79% (now 66%
> for 2018 adverts, 90% for October 2022); the 0.958 correlation (a levels correlation; 0.90 as
> 12-month changes). Current figures and their status: `../Case4_Audit.md`.

**Short answer:** yes, there are established ways to do this. The trick is to **not** throw every dataset into one big pile and train one model. Treat each dataset as a separate "study" of the same question ("what drives a car's value?"), then combine them in ways that respect their differences. The differences are country, year, currency, asking vs sale price, and which columns exist.

**Status, 2026-09-17.** All eight steps have been run on 30 sources and 4,334,195 listings. Results are recorded under each step below, with the script and report that produced them. Step 5's answer is largely a negative one: the collection cannot link advert prices to sale prices, and that gap is documented rather than papered over.

| Step | Status | Script | Report |
|---|---|---|---|
| 1. One set of columns, one currency | done | `build_unified.py`, `build_reference.py` | `data/unified/build_report.md` |
| 2. Compare shapes, not price levels | done, and shown to be necessary | - | - |
| 3. Same model per dataset, then pool | done | `analysis/drivers.py` | `analysis/drivers_report.md` |
| 4. One pooled model that borrows strength | done | `analysis/drivers.py` | `analysis/drivers_report.md` |
| 5. Link asking, sale and auction prices | done; 2 of 3 pairs not estimable | `analysis/price_types.py` | `analysis/price_types_report.md` |
| 6. Borrow missing columns | done | `build_reference.py`, `analysis/value_retained.py` | `analysis/value_retained_report.md` |
| 7. Prove more datasets help | done | `analysis/lodo.py`, `analysis/curve.py` | `analysis/lodo_report.md`, `analysis/curve_report.md` |
| 8. Time and cause-and-effect | done | `analysis/tesla_event.py`, `analysis/latvia_time.py` | `analysis/tesla_event_report.md`, `analysis/latvia_time_report.md` |

## Proposed method

### 1. Make the data comparable (done)
- **One set of columns** for every source (`build_unified.py`). Each row keeps its `source`, `country`, `price_type` and `date_basis`, so nothing is silently mixed.
- **One currency:** € using ECB monthly rates, or World Bank annual rates where the ECB has none.
- **One point in time:** adjust prices for used-car inflation with the official second-hand car price indices (`data/reference/price_indices.parquet`). A 2021 Polish price and a 2025 German price are not comparable until this is done.
- **Price type kept apart:** asking prices (adverts), sale prices (Washington State records) and auction prices (New Zealand, Cars & Bids) are different things.

**Where this got to:** 4,334,195 rows from 30 sources in 31 countries. The reference tables are built: 6,918 monthly index values across 40 geographies (including euro-area and EU aggregates), RDW Dutch catalogue prices for 51,525 make-model-years, DVM UK entry prices for 6,333 model-years, and 5,862,218 monthly FIPE valuations for Brazil, 2001-2026. The index adjustment itself is available but not yet applied to the listings.

### 2. Compare shapes, not price levels (done, and shown to be necessary)
€ levels differ a lot between countries (taxes, incomes, e.g. Singapore's COE, Dutch car tax). How fast value falls travels much better between markets. So use relative targets:
- **Log price:** effects read as percentages ("each extra year = −x%").
- **Value retained** = price ÷ new price, where a new price is known: RDW catalogue prices (NL), DVM entry prices (UK), Marketcheck MSRP (US), FIPE new-car values (Brazil).

**Where this got to:** this turned out to be not just a preference but a requirement. Every model in steps 3, 4 and 7 absorbs a fixed effect per make and model, so an effect is measured by comparing a car with the *same model*, never a Fiat 500 against a Porsche. In step 7 the price level always had to be supplied by the held-out market itself; a model trained elsewhere cannot predict a market's price level at all, only the shape of its depreciation.

### 3. Estimate the drivers in each dataset, then combine the results (done)
This is how medical research combines several trials. It's called a **two-stage meta-analysis**.
1. Fit the **same simple model** in every dataset: log price explained by age, mileage, fuel, body, power, gearbox, owners, accident/damage flags where present, plus make/model.
2. **Pool** each driver's effect across datasets with a random-effects meta-analysis. You get one combined estimate with a confidence range, and a measure of **how much it varies between markets**.

**What came out** (`analysis/drivers_report.md`, 17 datasets, 3,039,150 used cars, advertised prices only):

| Driver | Pooled effect | 95% range | Same driver in the step-4 pooled model |
|---|---|---|---|
| one more year of age | **−9.0%** | −10.0% to −7.9% | −10.8% |
| 10% more mileage | **−1.1%** | −1.3% to −0.9% | −1.3% |
| 10% more power (kW) | **+4.7%** | +4.4% to +5.1% | not in the core set |
| automatic instead of manual | **+10.4%** | +9.2% to +11.6% | +15.1% |
| diesel instead of petrol | +1.6% | −0.4% to +3.6% | −1.7% |

Three things to carry forward:
- **Age, mileage, power and gearbox are solid.** Consistent in sign across every dataset, and the two independent ways of combining the datasets agree.
- **Fuel type is not a reliable global driver.** Diesel changes sign between the two methods and runs from −6.7% to +15.1% across markets. Any claim about diesel or EV resale has to be made per market.
- **I² is about 100% on nearly every driver, which is expected rather than alarming.** With hundreds of thousands of cars per dataset the sampling error is tiny, so any real difference between markets dominates it. The honest quantity to quote is the spread across markets: age runs from −13.3% a year (UK, DVM) to −4.9% (Egypt).

Body type is the one weak row: because a make-and-model fixed effect is absorbed first, body type barely varies within a model name, so those coefficients should not be read as "SUVs are worth less".

### 4. One pooled model that borrows strength (done)
For the value engine itself:
- **Multilevel (mixed-effects) model:** shared effects for everyone, plus adjustments per country, source and make/model. Thin groups (Latvia, EVs, rare models) borrow information from large ones instead of being noisy on their own.
- **Gradient boosting with source and country as features**, or boosting with mixed effects (e.g. the GPBoost library). This gives better accuracy and non-linear curves.
- **Prediction ranges:** quantile models, or intervals checked on held-out data. This feeds the "wide range → human review" rule.

**What came out:** a single regression over 2,755,231 cars with a fixed effect per source, make and model (6,692 groups) agrees closely with the meta-analysis, which is the reassuring outcome: the answer does not depend on how the datasets are combined.

**But the borrowing does nothing at this scale.** Empirical-Bayes shrinkage weights came out at ≈1.000 for every dataset, meaning each one is precise enough to keep its own estimate. That is worth stating plainly rather than dressing up: with datasets this large, partial pooling collapses to the local answer. Step 7 shows where it does earn its keep. The boosting and quantile-interval parts of this step have not been built yet.

### 5. Link asking, sale and auction prices (done; the main finding is a gap in the data)
Where a market has two price types, estimate the gap (for example US asking prices from Marketcheck vs Washington State sale prices for the same models, age and mileage). Then an asking-price model can be translated into an expected sale price, with the uncertainty stated. Never mix the levels without this adjustment.

**What came out** (`analysis/price_types_report.md`). All three price types exist - 3,814,027 asking rows, 425,974 sale, 94,194 auction - but only one of the three pairs can actually be compared:

| Pair | Shared make-models | Rows on the thin side | Estimable |
|---|---|---|---|
| asking vs sale | 71 | 190 | **no** |
| asking vs auction | 236 | 543 | **no** |
| sale vs auction | 77 | 11,532 | yes |

**The collection has a structural hole, and finding it is the useful result.** Its 3.8 million advert prices are almost entirely European, while every sale and auction price is North American. Inside the US the only advert source is a 1,000-row Marketcheck sample and the only sale source is electric-vehicle registrations, so they share a couple of hundred cars. **No asking-to-sale adjustment factor can be honestly quoted from this data**, which means the advert-based models in step 3 cannot yet be translated into expected sale prices. That is a limit to state on a slide, not one to hide.

For the pair that does work - Washington sale records against Cars & Bids auctions, on the 53 make-models both cover and within the age and mileage range where both have cars - **a car at auction fetches +7.3% against an equivalent recorded sale** (95% range +5.2% to +9.5%). Raw medians put the gap at +33% to +44%; controlling for model, mileage and month removes most of it.

That sign is backwards from the usual expectation and should not be read as "auctions pay more". Cars & Bids is a curated enthusiast marketplace rather than a trade auction, and Washington's prices are self-reported on a title transfer that sets the excise tax due. **What the pair does establish is that price types differ by much more than noise even after controlling for the car**, which is exactly why `build_unified.py` keeps `price_type` as a column and never pools them.

### 6. Borrow missing columns from another dataset (done)
Some datasets lack a field that another one has. **Statistical matching** (data fusion) fills this in on shared keys. Examples:
- attach RDW new prices to European listings by make, model and year
- attach FIPE depreciation curves by model

Mark every borrowed value as borrowed.

**What came out** (`analysis/value_retained_report.md`). New-car prices were borrowed from four independent references and written to `data/unified/value_retained.parquet`, **661,503 listings**, each row carrying a `new_price_source` column saying where its price came from.

| Market | Reference | Match rate | Value retained at 3 years |
|---|---|---|---|
| UK | DVM-CAR entry price | 69.9% of 943,016 | **79%** |
| NL | RDW catalogue price | 65.0% of 12,269 | **62%** |
| US | Marketcheck MSRP (already on the row) | 100% of 690 | **68%** |
| BR | FIPE 0 km valuation (computed inside FIPE) | 59.4% | **76%** |

**The useful part is that this agrees with the regressions from a completely independent direction.** Reading an annual rate off the ten-year share gives UK −10.2%, NL −12.6% and US −9.2% a year. Step 3, which never sees a new price at all and works only from the slope of log price against age, put the pooled rate at 9-11% a year. Two different methods on different inputs land in the same place.

**A bug found here, worth recording.** `build_reference.py` originally lowercased make and model but did not apply the same normalisation as `build_unified.py`, so the reference tables said `mercedes-benz` while the listings said `mercedes benz` and those rows silently failed to match. Fixing it lifted the UK match rate from 52% to 64% and the Dutch from 52% to 65%. A join that half-works looks exactly like a join that works, so match rates are reported in the output rather than assumed.

Brazil's curve is much flatter than the others (55% retained at ten years against 34% in the UK). New-car inflation was the obvious explanation and was measured rather than assumed: FIPE's own 0 km series rises a median 1.2% a year, nowhere near enough. An official valuation table being smoothed by construction is the more likely cause, so Brazil should not be shown next to the advert-based markets as if it were the same measurement.

### 7. Prove that more datasets actually help (done)
This tests the hypothesis directly:
- **Leave-one-dataset-out:** train on all datasets but one, test on the one left out. Compare with a model trained on that dataset alone.
- **Learning curve by number of datasets:** add datasets one at a time and track accuracy and the stability of driver estimates.
- If adding a dataset makes things worse, it's too different: keep it separate or down-weight it.

**What came out** (`analysis/lodo_report.md` and `analysis/curve_report.md`, 15 markets held out in turn):

1. **A market's own data wins whenever it has enough of it.** A model trained on the other 15 datasets never beat a locally fitted one (0 of 15 markets). Naive stacking of all rows is actively *worse* than local, because the other markets outnumber the held-out one. A proper hierarchical blend matched or beat local on 14 of 15, by collapsing back to the local answer — the correct behaviour, not a failure.
2. **Borrowing pays exactly when a slice is thin.** Cutting the local training data down: at 100 local cars, borrowing cuts the error by 14.7% and stops one market's own fit from blowing up entirely; by 250 cars the gain is under 1%; by 25,000 it is nil. This is the argument for a shared ledger: it is worth real money for a new market, a newly merged brand or an EV line with two years of history, and worth nothing for an established market.
3. **What transfers is the market, not the row count.** Datasets whose market is also covered by a sibling dataset pay a median penalty of only **+2.8%** when their own data is removed; datasets that are the only one from their market pay **+30.6%**. Paired within market, a training set of one dataset does 17.2% worse if it contains nothing from the held-out market's own country. Another million cars from Latvia does not teach you Egypt.
4. **Accuracy saturates after about three datasets; stability does not.** Going from one dataset to three cuts the error 6.4%, and from three to fifteen adds only 2.3% more. But the spread of the age estimate across random dataset orderings falls from 2.52 to 0.10 percentage points. **That is the real return on collecting fifteen datasets: not a better prediction, but an estimate that no longer depends on which data you happened to have.**
5. **It does not rescue the hardest market.** While the median market improves, Jordan does not move at all. A market whose prices are set by something the others do not share cannot be borrowed into.

### 8. Time and cause-and-effect questions (done)
Use the datasets with real dates for before/after studies. The Washington State used-EV sales around Tesla's January 2023 price cut are the best case, with other EVs as the comparison group. Price indices provide market-wide context.

**What came out of the Tesla event study** (`analysis/tesla_event_report.md`, 26,825 used EV sales in Washington State, 2022-2023, 9,060 of them Tesla). Used Teslas are compared with other used EVs month by month, with a fixed effect per make, model and model year:

| Period | Tesla vs other used EVs |
|---|---|
| Jan-Aug 2022 | **+13.1%**, a stable premium |
| Sep-Dec 2022 | slides to 0% — **four months before the cut** |
| Jan-Mar 2023 | −5.4% |
| Apr-Dec 2023 | −6.1%, flat |

**About 68% of the repricing happened before Tesla announced anything**, so the answer is a negative one, and it is worth more than a fake number: **this event cannot be used to measure how a new-car price cut feeds into used values.** Parallel trends fails badly, January 2023 was the first of a series of cuts rather than a single treatment, and the control group (other used EVs) was itself softening through 2023.

The finding that survives is about *timing*: the used market repriced Teslas months ahead of the manufacturer's own announcement. A residual-value model that waits for official price actions is already too late. That is a direct argument for the ledger watching used-market signals rather than manufacturer announcements.

**What came out of the Latvian time series** (`analysis/latvia_time_report.md`, 707,190 used adverts across 52 monthly snapshots, Jan 2019 - Dec 2023, with May-Dec 2021 missing). Two things were measured month by month: a quality-adjusted price index, and the age coefficient from step 3 refitted inside each month.

**The result is the opposite of what the step expected, and more useful.** The 9%-a-year rate is not drifting. In Latvia the monthly rate stayed between **−13.2% and −11.7% a year in all 52 months** (standard deviation 0.38 points), including right through the 2021-22 shortage: −12.8% before the pandemic, −12.2% during it, −12.1% in 2023. Over the same months the price **level** went from 100 to a peak of 155 and back to 142.

So the depreciation curve moved **up and down, not steeper or flatter**. This is the same lesson step 7 gave from a different direction: there, shapes transferred between markets while levels did not; here, shapes hold still over time while levels do not. **Shape is the stable, portable thing in used-car value; level is local and perishable.** The design rule that follows is concrete — re-estimate the level often, re-fit the age curve rarely.

The index also doubles as a data-quality check, the only one in the project against an official statistic: it correlates **0.958** with Eurostat's Latvian second-hand car index, though it rises 42% against the official 8.8%. Latvia's neighbours (Lithuania +38.4%, Estonia +38.1%) sit with our figure rather than with Latvia's official one. See `DATASETS.md`.

**Still unbuilt.** The event study uses 2022-2023 of the Washington series only; the source runs 2012-2026, so the same design could be pointed at later Tesla cuts or at the 2020-2021 used-price spike, where the pre-period may behave better than it does around January 2023.

### Known risks
- **Asking prices:** adverts overstate sale prices, and unsold cars stay listed longer. Step 5 tried to measure by how much and could not: the collection has no market with both advert and sale prices for the same cars. Every headline figure in this project is therefore an advert-price result until a European transaction source is found.
- **Different markets:** taxes, subsidies and fleet mix differ, so effects can truly differ, not just be noise. Step 7 measured this: the difference between markets is real and large, not sampling noise.
- **Duplicates:** the same car can appear in several scrapes or sources.
- **Repeated observations.** `lv_ss` is a monthly panel with no advert id, so an advert that stays up appears once per snapshot, and a large share of its rows repeat an earlier row's make, model, year, mileage, engine, fuel, gearbox and body. Rows are observations, not unique cars. The analyses above do not cluster standard errors by car, which makes the confidence ranges on that source narrower than they should be. `pt_standvirtual` was scraped weekly too, but every advert carries an id and `build_unified.py` keeps each id once, so it is not a panel in the unified table.
- **Naive pooling is a real trap.** Stacking every dataset's rows together was worse than using local data alone on every market tested. Pooling has to be weighted by how precisely each market measures itself.
- **Unclear dates and licenses:** some sources have them; see `data/unified/build_report.md` and `DATASETS.md`.
