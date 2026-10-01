# What an in-house person costs, and the exchange rates (X25 part 3)

Official statistics for base 1's pay, and the ECB's rates for vendor prices quoted in USD and GBP. Built by
`analysis/programme_rates.py` from Eurostat and ECB downloads (cached in `data/raw/x25_rates/`).

## Loaded annual cost of an employee, manufacturing, 2025 terms

Mean annual gross earnings from the Structure of Earnings Survey 2022 (`earn_ses22_49`; manufacturing, NACE C;
enterprises with 10 or more employees), carried to 2025 with the growth of hourly wages and salaries in
manufacturing (`lc_lci_lev`, D11, 2022 to 2025), plus employer labour costs other than wages and salaries
(`lc_lci_lev`, D12_D4_MD5 over D11, 2025). No overhead for offices, equipment or management is included.

| Country and group | Earnings 2022 (EUR a year) | Wage growth 2022-2025 | Employer costs on pay | Loaded cost 2025 (EUR a year) |
|---|---:|---:|---:|---:|
| France, managers (OC1) | 90,617 | 1.103 | 46.7% | 146,669 |
| France, professionals (OC2) | 69,293 | 1.103 | 46.7% | 112,155 |
| France, technicians (OC3) | 42,822 | 1.103 | 46.7% | 69,310 |
| Germany, managers (OC1) | 132,064 | 1.115 | 31.0% | 193,017 |
| Germany, professionals (OC2) | 90,146 | 1.115 | 31.0% | 131,752 |
| Germany, technicians (OC3) | 69,295 | 1.115 | 31.0% | 101,277 |
| Italy, managers (OC1) | 171,330 | 1.120 | 40.8% | 270,174 |
| Italy, professionals (OC2) | 53,835 | 1.120 | 40.8% | 84,894 |
| Italy, technicians (OC3) | 43,299 | 1.120 | 40.8% | 68,279 |
| Spain, managers (OC1) | 67,684 | 1.139 | 37.6% | 106,038 |
| Spain, professionals (OC2) | 49,988 | 1.139 | 37.6% | 78,315 |
| Spain, technicians (OC3) | 41,533 | 1.139 | 37.6% | 65,068 |
| Poland, managers (OC1) | 32,870 | 1.489 | 22.1% | 59,795 |
| Poland, professionals (OC2) | 21,150 | 1.489 | 22.1% | 38,475 |
| Poland, technicians (OC3) | 17,381 | 1.489 | 22.1% | 31,619 |

The occupation groups are one-digit ISCO-08, the finest the survey publishes by activity: a data engineer and a finance analyst are both professionals (OC2). Data specialists may earn more than their group's mean; the model takes that as a sensitivity, not a figure.

## Paid annual holidays, manufacturing, 2022

Mean annual holidays in days (`earn_ses22_51`; manufacturing, 10 or more employees), for the working-days assumption (`x25_days_per_fte_year`).

| Country and group | Holidays (days a year) |
|---|---:|
| France, managers (OC1) | 28.0 |
| France, professionals (OC2) | 28.0 |
| France, technicians (OC3) | 28.0 |
| Germany, managers (OC1) | 29.0 |
| Germany, professionals (OC2) | 29.0 |
| Germany, technicians (OC3) | 28.0 |
| Italy, managers (OC1) | 28.0 |
| Italy, professionals (OC2) | 24.0 |
| Italy, technicians (OC3) | 23.0 |
| Spain, managers (OC1) | 24.0 |
| Spain, professionals (OC2) | 25.0 |
| Spain, technicians (OC3) | 25.0 |
| Poland, managers (OC1) | 25.0 |
| Poland, professionals (OC2) | 25.0 |
| Poland, technicians (OC3) | 25.0 |

## Hard-to-fill ICT vacancies, manufacturing, 2024

Share of enterprises that recruited or tried to recruit ICT specialists and had vacancies that were hard to fill (`isoc_ske_itrcrn2`; 10 or more employees). It measures difficulty, not months to hire.

| Country | Recruiting enterprises with hard-to-fill ICT vacancies |
|---|---:|
| France | 56.1% |
| Germany | 72.7% |
| Italy | 61.5% |
| Spain | 23.1% |
| Poland | 35.4% |

## Exchange rates

ECB euro reference rates, monthly averages, the latest twelve months (units of currency per euro).

| Currency | Units per euro, twelve-month average | First month | Last month |
|---|---:|---|---|
| GBP | 0.8674 | 2025-09 | 2026-08 |
| USD | 1.1638 | 2025-09 | 2026-08 |
