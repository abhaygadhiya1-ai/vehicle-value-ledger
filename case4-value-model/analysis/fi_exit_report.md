# X11 part 3: mileage and leaving the fleet, Finland beside the UK

**The UK result holds in Finland.** For cars of 10-20 years, which both countries inspect every year, a car on twice
its age cohort's mileage is **1.84 times** as likely to leave the fleet within a year in Finland
(elasticity 0.882, standard error 0.036), and **1.91 times** in the UK
(0.930, 0.026). The difference is 1.1 standard errors. Both figures come from the same
method and the same functions, on two registers.

| ages 10-20, cars inspected in the year before | Finland | UK |
|---|---|---|
| elasticity | 0.882 | 0.930 |
| standard error | 0.036 | 0.026 |
| twice the mileage | 1.84x | 1.91x |
| difference, in standard errors | 1.1 |  |

Across ages 4-20 the Finnish figure is 1.73 times (elasticity 0.790, standard error
0.032); the UK's published figure, for ages 3-20, is 1.54 times (0.626). At
4-9 the two designs differ. A Finnish car inspected in the year before the baseline is not due again in the
follow-up year, because it is on a two-year cycle, while a UK car is due every year. So the whole-range figures are
not like for like; the 10-20 band is.

In the main sample (cars inspected in the year to 30 June 2025, ages 4-20), 6.1% had left
traffic use by 30 June 2026. That means scrapped, exported or laid up: Finland's open file lists only vehicles in
traffic use, and gives no reason.

## The decile profile

The main Finnish sample beside the UK's part 1. The UK columns are recomputed with the UK script's own `pooled()`
from its saved cells; refitting those cells reproduces its saved elasticity exactly.

| mileage decile | Finland: mileage vs cohort median | Finland: exit vs cohort average | UK: mileage vs cohort median | UK: exit vs cohort average |
|---|---|---|---|---|
| 1 | 0.40x | 0.61x | 0.36x | 0.61x |
| 2 | 0.59x | 0.61x | 0.57x | 0.65x |
| 3 | 0.73x | 0.68x | 0.71x | 0.72x |
| 4 | 0.84x | 0.73x | 0.83x | 0.80x |
| 5 | 0.95x | 0.82x | 0.94x | 0.88x |
| 6 | 1.05x | 0.92x | 1.06x | 0.97x |
| 7 | 1.17x | 1.03x | 1.19x | 1.07x |
| 8 | 1.31x | 1.21x | 1.35x | 1.17x |
| 9 | 1.48x | 1.43x | 1.57x | 1.33x |
| 10 | 1.79x | 1.95x | 2.08x | 1.78x |

## The checks

| sample | ages | cars | exit rate | elasticity | se | twice the mileage | decile 10 / decile 1 |
|---|---|---|---|---|---|---|---|
| Main: inspected in the year before the baseline | 4-20 | 1,280,604 | 6.1% | 0.790 | 0.032 | 1.73x | 3.2x |
| Main, ages 4-9 | 4-9 | 362,603 | 3.6% | 0.622 | 0.057 | 1.54x | 3.1x |
| Main, ages 10-20 (yearly inspections) | 10-20 | 918,001 | 7.1% | 0.882 | 0.036 | 1.84x | 3.3x |
| Main, domestic cars only | 4-20 | 1,043,394 | 5.7% | 0.805 | 0.036 | 1.75x | 3.4x |
| All readings, fresh or not | 4-20 | 1,650,648 | 6.1% | 0.637 | 0.033 | 1.55x | 2.7x |
| All readings, ages 10-20 | 10-20 | 1,000,641 | 7.7% | 0.792 | 0.036 | 1.73x | 2.9x |

- **Staleness.** At ages 4-9, cars not inspected in the year before the baseline left at
  3.9%, and cars that were inspected at 3.6%. The rates barely differ.
  What staleness changes is the mileage: a reading up to two years old ranks a car below its true place in the
  cohort. With every reading, fresh or not, the elasticity falls from 0.790 to 0.637. That
  is why the main sample keeps only fresh readings.
- **Imports.** Used imports enter the cycle at registration. On domestic cars alone the elasticity is
  0.805.
- **The UK the same way, by age band:**

| UK sample | ages | elasticity | se | twice the mileage | decile 10 / decile 1 |
|---|---|---|---|---|---|
| UK, all ages | 3-20 | 0.626 | 0.026 | 1.54x | 2.9x |
| UK, ages 4-9 | 4-9 | 0.487 | 0.030 | 1.40x | 2.5x |
| UK, ages 10-20 | 10-20 | 0.930 | 0.026 | 1.91x | 4.0x |

## Laid-up cars: gone, or only resting?

The 2024 snapshot as a baseline, followed to 2025, with 2026 as a later look. Of the cars gone in 2025,
31.3% were back in traffic use in 2026: laid up, not disposed of. Ages 10-20, all readings; at
those ages inspections are yearly, so almost every reading is under a year old.

| sample | ages | cars | exit rate | elasticity | se | twice the mileage | decile 10 / decile 1 |
|---|---|---|---|---|---|---|---|
| Baseline 2024: gone in 2025 | 10-20 | 1,003,828 | 8.1% | 0.829 | 0.036 | 1.78x | 3.0x |
| Baseline 2024: still gone in 2026 (permanent) | 10-20 | 1,003,828 | 5.6% | 1.113 | 0.050 | 2.16x | 4.3x |
| Baseline 2024: back in 2026 (laid up) | 10-20 | 1,003,828 | 2.5% | 0.314 | 0.023 | 1.24x | 1.4x |
| Baseline 2025: gone in 2026 (a year later) | 10-20 | 1,000,641 | 7.7% | 0.792 | 0.036 | 1.73x | 2.9x |

**The gradient belongs to permanent exits.** For cars still gone a year later the elasticity is
1.113. For cars that came back it is 0.314: laid-up cars are only mildly more driven than their
cohort. So lay-ups dilute the all-exits figure, and high mileage marks disposal. The last row repeats the 2024 row's
definition a year later (0.792 against 0.829), so the result is not a fluke of one year.

## Limits

- **A proxy, like the UK's.** "Left traffic use" covers scrapping, export and lay-up. The UK's covers the same
  plus an MOT missed. Neither register gives a reason per car. The 2026 look splits off the lay-ups that
  returned within a year, not the ones that will return later.
- **The key drops cars it cannot follow:** identical cars registered on one day. An error independent of mileage
  would dilute the gradient, not create it (`fi_register_report.md`).
- **Three snapshots, one country.**

## Coming to market: not tested in Finland (part 4)

The UK's second result is that mileage does not predict a car being advertised. It needs adverts, and no Finnish
car-advert dataset is in hand. The one Finnish source is the van file in `eu_commercial_2023`: 6,553 adverts
("European Used Commercial Car On-line Market Monitoring in 2023", issued 22 December 2023:
https://doi.org/10.17632/kz6hh7832p). It cannot carry the test, for four reasons.

- **The listing month holds; the year is inferred.** 96% of adverts give a day and a Finnish month
  name, and 80% of those fall in December or January. None gives a year. Since the dataset
  was issued in December 2023, the scrape is most likely around December 2022 to January 2023.
- **The parc would be out of step.** The matching register would be the Archive's March 2023 capture. Its
  readings date from each van's last inspection, up to a year earlier even at yearly-inspection ages, while an
  advert's mileage is current. That pushes adverts into higher parc deciles and makes a slope on its own. There is
  no earlier snapshot to keep only fresh readings, as part 3 does.
- **Too few.** At the yearly-inspection ages (10-20), 1,848 adverts carry a date and a believable
  mileage: 83-242 per age cohort. The UK test used 354,112 car adverts.
- **Vans, not cars.**

**Decided (26 September, on solution quality):** result 2 stays UK-only and says so. A Finnish van test would be
weaker than the result it checks, and a staleness correction would rest on an assumption. The disposal half, which
needs no adverts, is the half Finland replicates above.
