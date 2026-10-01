# The retail-to-trade gap, bounded; and how trade swings against retail

`analysis/trade_gap.py`. Skeptic B10: the value engine is calibrated on asking prices, but the group sells most returns at trade. No public series prices the same car at retail and then at trade (X10: Aramis's trade and retail cars are different cars). A retailer that buys at trade and sells at retail earns the gap on the same car, so its audited accounts bound it. Then US data show how the gap moves with the market.

## 1. The gap on the same young car, from two retailers' accounts

Each figure is a share of the car's retail price, with finance, warranty and other services taken out of the price.

| bound | source | what it counts | gap (%) |
|---|---|---|---|
| floor | Motorpoint FY26, UK (`motorpoint_fy26_*`) | retail gross profit (GBP 88.4m) less all its commissions (GBP 59.7m), over car revenue (GBP 1,071.1m); preparation already deducted | 2.7 |
| Aramis, services at full margin | Aramis FY2025, the group's own (`aramis_fy25_*`) | gross profit before transport and refurbishing (EUR 414.4m) less all services revenue (EUR 123.7m), over car revenue (EUR 2,255.9m) | 12.9 |
| ceiling | Aramis FY2025 | the same with services at no margin | 18.4 |
| the engine's typical error, for comparison | `engine_err_typical` | its error on cars it has never seen | 10.5 |

- **Why the floor is a floor.** Motorpoint buys nearly new cars mostly through fleet and bulk channels (`motorpoint_fy26_sourcing`), the trade the group's returns are sold into. Its cost of sales already holds preparation and transport, and no service can earn more than its revenue, so what it earned on the car over its trade price is at least this.
- **Why the ceiling is a ceiling.** Aramis's gross profit before transport and refurbishing, with its services earning nothing, is the most its cars earned over what it paid. It buys partly from private sellers, and a buyer of private cars pays them less than trade: Auto1 buys cars from consumers and resells them to dealers at a gross profit of EUR 957 a car (`auto1_merchant_gpu_q1_2026_eur`). So on Aramis's mix the gap at trade is no larger. Its B2B line (older cars sold to the trade) and its pre-registered cars sit in the average.
- **Aramis's own spend on transport and refurbishing** is 5.9% of its car revenue: part of any gap a retailer earns pays for making the car retail-ready.
- **Reading.** For a young car, the trade price sits between about 3% and 18% below the retail price, on average over these retailers' mixes; the group's own retailer earns at least about 13% over what it paid, before making the car retail-ready. The engine's typical error lies inside that range. So B10 is right that the gap is of the engine's order, and it is bounded: under a fifth of the price. It is a level offset that realised trade prices on the returns measure (the Phase 2 gate), plus any discount off the asking price, which X10 could not size from averages.

## 2. US data: does the gap move with the market?

The Manheim index (US wholesale auction prices, adjusted for mix, mileage and season: `manheim_index_method`) against the US CPI for used cars (retail transactions, seasonally adjusted), monthly, 1997-01 to 2025-11: 335 twelve-month changes.

| measure | trade (Manheim) | retail (CPI) | ratio |
|---|---|---|---|
| standard deviation of 12-month changes (%) | 9.2 | 8.4 | 1.09 |
| one-in-ten-year 12-month change, p10 (%) | -5.3 | -6.6 | 0.81 |
| worst 12-month change (%) | -14.9 (2022-12) | -13.4 (2023-02) | 1.11 |
| mean 12-month change (%) | 3.0 | 1.0 | |

| how they move together | value |
|---|---|
| months by which trade leads retail (best correlation) | 2 |
| correlation at that lead | 0.84 |
| correlation in the same month | 0.72 |
| points of trade change per point of retail change, same month | 0.78 |
| the same, trade leading by the best lead | 0.92 |

Every year in which either fell, December to December (independent years):

| year | trade (%) | retail (%) | trade over retail |
|---|---|---|---|
| 2001 | -1.2 | -1.9 | 0.64 |
| 2002 | -3.8 | -5.5 | 0.68 |
| 2003 | 2.8 | -11.8 | one rose |
| 2006 | -0.4 | -2.1 | 0.19 |
| 2007 | -1.2 | 0.5 | one rose |
| 2008 | -11.3 | -7.6 | 1.48 |
| 2011 | -1.3 | 4.4 | one rose |
| 2012 | -2.2 | -1.9 | 1.16 |
| 2013 | -2.0 | 2.2 | one rose |
| 2014 | 2.3 | -4.3 | one rose |
| 2015 | 1.5 | -1.3 | one rose |
| 2016 | -0.6 | -3.1 | 0.19 |
| 2017 | 5.6 | -1.0 | one rose |
| 2019 | 2.5 | -0.1 | one rose |
| 2022 | -14.9 | -8.8 | 1.68 |
| 2023 | -7.0 | -1.3 | 5.54 |
| 2024 | 0.4 | -4.7 | one rose |

- **Reading.** Over the year, US trade and retail prices move about one for one, and trade moves first (the lead above). Trade swings only a little wider in general (the ratio of standard deviations), and its one-in-ten-year fall is no deeper than retail's. In the two market-wide slumps, 2008 and 2022-23, trade fell further (the table), and in 2003 and 2014-17 retail fell while trade did not. So the gap does move, mostly in timing: a mark on retail or asking indices is late at a turn, as X10 found for Germany's asking prices, and it can understate a slump at trade.
- **No multiplier is carried into the workbook.** Two slumps are too few to set a ratio, and the rest of the record shows none; X6's charge stays a floor for X10's reasons.
- **Limits.** US data, one market; the two indices adjust for quality differently (the CPI's quality adjustment, Manheim's mix and mileage within its classes), which can open gaps over years. No European public series prices the trade (auction results are private: the dead ends in `notes/Case4_Extensions.md`).

## What this changes

- **B10 moves from unmeasured to bounded.** The gap is between the floor and the ceiling above; Phase 1's mark starts from that range and Phase 2 measures it on the returns (the gates report's B10 rows).
- **The mark turns with trade.** US trade leads retail by a couple of months, so the ledger's re-mark should read the group's own trade results as they come (its returns' auction prices), not only indices.
- **The headline does not move.** Leak 3 is sized on percentage moves of the level and the curve, not on the engine's price level.

## Checks

| check | got | passes |
|---|---|---|
| Motorpoint's retail gross profit per car, from revenue, cost of sales and cars sold, is its stated GBP 1,368 (within GBP 1; cars are rounded to hundreds) | GBP 1,368.4 | yes |
| Aramis's GPU, from gross profit less transport and refurbishing over retail cars, is its stated EUR 2,359 (within EUR 1) | EUR 2,359.2 | yes |
| Aramis's retail, trade and services revenue add up to its total (within EUR 0.1m) | 2,379.6 vs 2,379.6 | yes |
| the bounds are in order: floor below Aramis's lowest below the ceiling | 2.7 < 12.9 < 18.4 | yes |
| the Manheim 12-month changes, recomputed from its index, equal the file's own column within 0.0001, every month but 2023-01 (the month Cox rebased the index) | largest gap 9.0e-05 over 334 months; 2.5e-04 in 2023-01 | yes |
| both indices have every month from January 1997 to November 2025 | 347 and 347 of 347 | yes |
| the same months are compared for both | 335 twelve-month changes | yes |

All checks pass.
