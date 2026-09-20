# Layer 4: does the market level change which cars come to market?

Latvia, 2019-01 to 2023-12, 52 monthly snapshots of ss.com, 936,494 listing rows. Over that window our quality-adjusted Latvian price index rises **71%**, so there is a real market move to test against - this is the window that contains the shortage.

**Volume is not used, on purpose.** `lv_ss` carries no advert id, so a car that stays listed is counted again in every snapshot and a month's row count is as much a fact about the scrape as about the market. For the record, log rows against log price correlate at -0.11, and **that number should not be quoted**: it cannot be told apart from the scraper changing size.

What *can* be measured is composition - the mix of what is on sale, which is a ratio inside a month, so the size of the scrape divides out. Each row below is the effect of a **10% stronger market**, with a linear time trend and calendar-month effects taken out.

| Measure | Effect of a 10% stronger market | t | Unit |
|---|---|---|---|
| Median age on sale, against our quality-adjusted index | +0.449 | +4.1 | years per 10% of price |
| Share aged 15+, against our quality-adjusted index | +0.039 | +12.2 | points per 10% |
| Median mileage on sale, against our quality-adjusted index | +5,686 | +9.9 | km per 10% of price |
| Share over 250,000 km, against our quality-adjusted index | +0.028 | +8.5 | points per 10% |
| Median age on sale, against Eurostat's official index | +0.709 | +3.7 | years per 10% of price |
| Share aged 15+, against Eurostat's official index | +0.066 | +12.6 | points per 10% |
| Median mileage on sale, against Eurostat's official index | +9,980 | +11.7 | km per 10% of price |
| Share over 250,000 km, against Eurostat's official index | +0.050 | +10.4 | points per 10% |

The strongest reading is **Share aged 15+** against Eurostat's official index: +0.066 points per 10%, t +12.6. The two indices agree on the sign of 4 of 4 measures.

## What to take from it

- **There are two readings and this data cannot separate them.** Either a stronger market pulls older, harder-driven cars onto the market that would otherwise have stayed on the road - which is a hazard effect and the one the engine would want - or those cars simply sell more slowly and pile up in what is on display. Without an advert id `lv_ss` shows the cars that *are* on sale, not the cars that *came* on sale, so both produce exactly this table. **Do not present it as proof of the first reading.** What argues mildly against the second is that the window is the shortage, when cheap old cars sold unusually fast, but that is an argument, not a measurement.
- **One market, and an unusual one.** Latvia over 2019-2023 contains the shortage. The project has measured that the level moved and the depreciation *rate* did not (`latvia_time_report.md`: 52 months all between -13.2% and -11.7% a year).
- **It does not give the engine a coefficient.** Layer 4 in the engine remains the value side - `level_risk.py` and `value_engine.py` already price what the market level does to the money. What this adds is whether the level moves the *hazard*, and on this data the honest answer is a composition effect of the size in the table, measured on a stock.
