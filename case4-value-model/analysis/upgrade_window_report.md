# The upgrade window, with the first year measured

`analysis/upgrade_window.py`. Skeptic B11: the Leak 2 sheet's "month 12" was where its search began, because the UK curve has whole-year ages and so no first year. Here the first year is measured on Dutch adverts with exact ages (the continental 2025 scrape) against the RDW catalogue price of each make, model and year, within model. The contract (deposit, term, rate) and the level shocks are the Leak 2 sheet's own.

2,606 adverts, 90 makes and models, up to five years old. Bootstrap: 300 draws of whole models, so the range carries the uncertainty of which models are in the sample.

## Value retained by age, share of list

| age (months) | adverts | within model | raw median | 80% range (bootstrap) |
|---|---|---|---|---|
| 0-3 | 328 | 87.2 | 96.0 | 82.2-92.2 |
| 3-6 | 364 | 82.0 | 80.9 | 76.7-87.4 |
| 6-9 | 337 | 81.0 | 84.4 | 76.7-85.0 |
| 9-12 | 257 | 79.4 | 82.0 | 75.5-83.1 |
| 12-18 | 186 | 71.3 | 78.6 | 67.4-75.0 |
| 18-24 | 219 | 72.4 | 71.2 | 68.3-75.8 |
| 24-36 | 224 | 61.5 | 61.6 | 58.5-64.1 |
| 36-48 | 258 | 60.0 | 58.2 | 55.6-66.5 |
| 48-60 | 433 | 55.0 | 49.8 | 51.4-60.3 |

A car loses most of its first year's value in its first months, and the within-model curve holds the model mix fixed: the raw medians of the youngest bins swing with whichever models are young (a few premium models dominate the first quarter).

## The window: when equity first covers the next deposit

The sample contract: a 15% deposit, 48 months at 7% (`loan_*`). Searched from month 1; a level shock moves every month's value.

| market level | month | 80% range (bootstrap) | draws where it never opens in the term |
|---|---|---|---|
| level as measured | 18 | 14-20 | 0% |
| level -7.7% (p10) | 21 | 19-25 | 0% |
| level -27% (worst) | 33 | 32-34 | 0% |

## What this does and doesn't change

- **The Leak 2 sheet keeps the UK curve** (the sample car is British, and X19's trade-off and the Per car sheet read it), but its window row is a bound: with no sub-year ages it can only say the window is open by month 12.
- **The months quoted are these.** They are measured, and the first year is no longer a line drawn from list.
- **Leak 2's euros do not move:** they are contracts times an assumed uplift times an assumed margin, not the window.
- **Limits:** Dutch asking prices in one scrape (2025), not transactions; the RDW catalogue price is a model year's list price, so options and trims above it lift the youngest cars (some sit above 100%); the curve's level is the sample's average model.

## Checks

| check | got | passes |
|---|---|---|
| the balance equals the Leak 2 sheet's | largest gap 2.8e-14 | yes |
| the within-model estimator recovers a known curve despite a skewed model mix | 0.0035 | yes |
| at three years the curve agrees with the register's Dutch figure (retained_3y_nl), within 3 points | 60.7 vs 60 | yes |
| the curve falls from the first bin to the last | 0.872 > 0.550 | yes |
| a deeper fall never opens the window sooner | 18 <= 21 <= 33 | yes |
| every bootstrap draw had every age bin | 300 of 300 | yes |

All checks pass.
