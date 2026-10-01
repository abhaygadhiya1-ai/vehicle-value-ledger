# X11 part 2: can one Finnish car be followed from one snapshot to the next?

Snapshots of Traficom's open vehicle file, a year apart. Every vehicle in traffic use is a row; passenger cars (M1
and M1G) are kept. A car present in one and absent a year later has left traffic use, which part 3 relates to its
mileage. This part checks, on 2025 against 2026, that the follow-up can be done and what the odometer field means.
Part 3 adds 2024 (`fi_exit_report.md`).

| snapshot | file | sha1 | data date | encoding | rows | jarnro gaps | cars (M1, M1G) |
|---|---|---|---|---|---|---|---|
| 2024-10 | Ajoneuvojen_avoin_data_5_25.csv | NVNQP6V2NGPLWRMBRTWBSS3LVFS7XDBI | 2024-06-30 | latin-1 | 5,373,623 | 0 | 2,836,469 |
| 2025-09 | Ajoneuvojen_avoin_data_5_29.csv | 6BNXLGVRXNT5EL7YTEWECWJGS62B7N2T | 2025-06-30 | utf-8 | 5,281,968 | 0 | 2,760,681 |
| 2026-07 | TieliikenneAvoinData_30_06_2026.csv | BCWHZZXSUM4TCR2EQWMLG66FMQWCYNPO | 2026-06-30 | latin-1 | 5,296,749 | 45 | 2,766,102 |

The data date is the latest first-registration date in the file: 30 June of each year, exactly a year apart. The 2026
file is named for it. Its `jarnro` skips a few numbers (the gaps are in Traficom's file; the raw lines match the
parsed rows). The releases differ in encoding; each is read as the same text.

## `jarnro` is a row number, not an id

For cars carrying the same `jarnro` in both files, first-registration date and model agree from row 1 to row
11 and almost never after (from row 12 on). The number counts rows in each release; it cannot follow a car.

## A key of fixed attributes

On the 1,597,527 cars that the first four attributes (exact first-registration date, first 10 VIN characters, make,
model) match one to one, how often does each other attribute differ a year later?

| attribute | in key | differs on K0 pairs |
|---|---|---|
| kayttoonottopvm | yes | 0.010% |
| variantti | yes | 0.216% |
| versio | yes | 0.223% |
| tyyppihyvaksyntanro | yes | 0.224% |
| kaupallinenNimi | yes | 0.013% |
| omamassa | yes | 0.021% |
| teknSuurSallKokmassa | yes | 0.017% |
| ajonKokPituus | yes | 0.028% |
| ajonLeveys | yes | 0.011% |
| ajonKorkeus | yes | 0.085% |
| iskutilavuus | yes | 0.013% |
| suurinNettoteho | yes | 0.028% |
| sylintereidenLkm | yes | 0.027% |
| korityyppi | yes | 0.028% |
| ovienLukumaara | yes | 0.113% |
| istumapaikkojenLkm | yes | 0.019% |
| vaihteisto | yes | 0.072% |
| kayttovoima | yes | 0.006% |
| vari | K3 only | 0.078% |
| kunta | no | 15.478% |
| ajoneuvonkaytto | no | 2.087% |

The fixed attributes almost never change, and many differences are a blank on one side. Colour changes rarely
and separates many identical cars registered on the same day. Municipality and use change, so they are left out.

| key | attributes | unique in 2025 | unique in 2026 | found a year later | 1-3-year-olds not found | readings that fell | 2026 cars first registered before 1 Jul 2025, not in 2025 |
|---|---|---|---|---|---|---|---|
| K0 | 4 | 63.5% | 64.4% | 91.7% | 3.18% | 0.35% | 5.83% |
| K1 | 9 | 73.4% | 74.2% | 91.9% | 3.21% | 0.33% | 5.41% |
| K2 | 22 | 75.0% | 75.8% | 91.7% | 3.26% | 0.32% | 5.47% |
| K3 | 23 | 88.4% | 88.8% | 92.0% | 3.17% | 0.31% | 4.79% |

Each key uses only cars unique on it in both files. **K3 is chosen:** all fixed attributes plus colour. It is
unique for the most cars, and it does best on every check that needs no ground truth. Three checks follow.

- **Readings that fell.** A car's odometer reading should not fall. On K3 pairs it falls for
  0.31%, which bounds wrong matches plus clocked or replaced odometers.
- **Young cars not found.** Cars of 1-3 years seldom leave traffic use, so their rate caps how often the key loses a car.
- **Unmatched 2026 cars.** A 2026 car first registered before July 2025 and not found in 2025 is a re-entry from lay-up,
  a car whose key twin left (so it became unique), or a key failure.

**How many losses are key failures?** There are two bounds.

- **Lower bound.** A lost 2025 car and an unmatched 2026 car that agree on a shorter key, unique in each whole file,
  are probably one car with a changed attribute. That describes 1.6% of lost cars on K1, and
  3.5% on K0 (4.1% of lost 1-3-year-olds). This misses a change in the first four
  attributes, which the table shows the file almost never makes.
- **Upper bound.** Suppose every lost 1-3-year-old were a key failure. Then the key would lose
  3.17% of cars at any age. Part 3 compares cars within one age cohort, so an
  error that doesn't depend on mileage dilutes the contrast; it doesn't create one.

The cars K3 cannot separate are mostly pairs of identical cars registered on the same day in the same colour;
missing fields explain few. The key-unique share by age runs from 86.6% to 97.6%. Part 3 measures
within age cohorts, so this changes the weights between ages, not the comparison within one.

## The odometer reading, and when it is taken

Traficom's rule for passenger cars (verified 26 September 2026 at
https://traficom.fi/fi/autoilijat/katsastus/katsastusajankohdat-ajoneuvoluokittain):

- the first inspection is due at the latest 4 years after the car's date of first use (*käyttöönottopäivä*);
- after that, at the latest 2 years after the previous one;
- once more than 10 years have passed since first use, yearly;
- a car inspected at 8-9 years is still due by 10 years 0 months;
- privately used cars 40 years past their year of first use are inspected every 2 years (since 14 May 2020).

`matkamittarilukema` is "the last odometer reading found during the inspection". It is dated by the inspection, not
by the snapshot.

| age (years since first use) | reading, 2025 | reading, 2026 | found cars | reading changed in the year | the rule over that year |
|---|---|---|---|---|---|
| 0 | 4.0% | 3.9% | 62,945 | 2.0% | none due before 4 |
| 1 | 10.4% | 10.2% | 70,829 | 2.7% | none due before 4 |
| 2 | 18.6% | 16.2% | 80,909 | 8.7% | none due before 4 |
| 3 | 30.8% | 30.8% | 86,457 | 86.5% | first, by 4 |
| 4 | 98.1% | 98.0% | 113,241 | 19.8% | not due (4, 6, 8) |
| 5 | 99.7% | 99.7% | 100,083 | 80.0% | due (4, 6, 8) |
| 6 | 99.9% | 99.9% | 103,043 | 22.9% | not due (4, 6, 8) |
| 7 | 99.9% | 99.9% | 119,370 | 32.6% | not due (mostly before the reform: 3, 5, 7, 9) |
| 8 | 99.9% | 99.9% | 118,487 | 75.5% | due (before the reform: 3, 5, 7, 9) |
| 9 | 99.9% | 99.9% | 112,956 | 97.4% | due by 10 y 0 m |
| 10 | 100.0% | 99.9% | 97,507 | 97.5% | yearly |
| 11 | 100.0% | 100.0% | 97,589 | 97.7% | yearly |
| 12 | 99.9% | 100.0% | 87,832 | 97.6% | yearly |
| 13 | 99.9% | 99.9% | 100,847 | 97.5% | yearly |
| 14 | 99.9% | 99.9% | 96,094 | 97.2% | yearly |
| 15-19 | 99.9% | 99.9% | 399,700 | 95.7% | yearly |
| 20-29 | 100.0% | 100.0% | 318,959 | 91.7% | yearly |
| 30+ | 97.7% | 98.0% | 74,290 | 47.2% | yearly |

**Readings under 4 years are imports.** A used import is inspected when it is first registered in Finland, so
it carries a reading. A domestic car rarely does before its first periodic inspection:

| age | imported | reading if imported | reading if not |
|---|---|---|---|
| 0 | 0.8% | 73.4% | 3.5% |
| 1 | 6.7% | 87.4% | 4.8% |
| 2 | 14.8% | 93.3% | 5.7% |
| 3 | 21.8% | 95.0% | 12.8% |

**The reform of 20 May 2018 shows in the data.** Trafi's page on the new intervals (updated 18 May 2018, Internet
Archive capture of 27 May 2018:
https://web.archive.org/web/20180527194205/https://www.trafi.fi/tieliikenne/katsastus/uudet_katsastusajat)
says: "Seuraava katsastus määräytyy edellisen katsastuksen mukaan. Vasta kun ajoneuvo katsastetaan hyväksytysti uusien
säännösten voimassaoloaikana, seuraavan katsastuksen ajankohta määräytyy uusien säännösten mukaisesti." That is: the
next inspection follows from the previous one, and only after a pass under the new rules does the new schedule apply.
Its examples: a car first used on 20 May 2018 is first due by 20 May 2022. Since the reform, the date also rolls
from the last inspection, not from first use. So a car inspected early moves its whole cycle forward.

The data show two cycles. Cars first used before the reform keep the old first inspection at 3 years, then take
2-year steps: 3, 5, 7, 9. Later cars follow 4, 6, 8. For domestic cars (imports start their cycle at import), the
two cycles predict opposite years for the 2016-18 cohorts, and the data follow the one each cohort's first-use
date gives:

| first used | cars | reading changed in the year | odd cycle (3, 5, 7, 9) predicts | even cycle (4, 6, 8) predicts | the rule for this cohort |
|---|---|---|---|---|---|
| 2015H2 | 39,034 | 98.1% | due | due | odd |
| 2016H1 | 49,040 | 97.1% | due | due | odd |
| 2016H2 | 40,193 | 76.3% | due | not due | odd |
| 2017H1 | 49,329 | 81.8% | due | not due | odd |
| 2017H2 | 40,907 | 29.2% | not due | due | odd |
| 2018H1 | 52,512 | 31.2% | not due | due | odd |
| 2018H2 | 37,519 | 24.5% | due | not due | even |
| 2019H1 | 45,872 | 13.5% | due | not due | even |

(The old first inspection at 3 years is from secondary sources, not opened at Traficom. The data show it as the
odd cycle. Predictions use each half-year's median first-use date, so a cohort crossing a deadline mixes.)

**What part 3 must do.** A reading is up to two years old for cars of 4-10 years, and up to one year old after 10.
Within an age cohort, a car just inspected and one due next month carry readings a year apart. Part 3 therefore
compares mileage within cohorts of the same age and first-use half-year, or uses cars whose reading changed in the
year before the baseline. Domestic cars under 4 carry almost no reading and are left out, as the UK's under-3s are.

## Limits

- **Leaving traffic use is a proxy.** It covers scrapping, export and temporary lay-up. Finland publishes no per-car
  reason in this file. A laid-up car can return, as the unmatched 2026 cars show.
- **K3 drops the non-unique cars:** identical cars registered on the same day. They are excluded, not guessed.
- **One pair of snapshots, one year.**
