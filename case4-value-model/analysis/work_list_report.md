# The programme's work list (X25 part 1)

What every costing base prices: the roadmap's four 6-month phases x eleven workstreams x ten roles, in the
average number of full-time people in each phase. **Every figure in `work_list.csv` is an ASSUMPTION** with
its basis on the row; this report checks the list and reads it. Built by `analysis/work_list.py`.

## Checks

- 90 rows, every one with a known role, a phase from 1 to 4, a positive FTE and a basis.
- Every phase gate in the register (`gate_*`, except the two that apply to every gate) is staffed in its own
  phase by at least one row that names it.

## People by phase (average FTE in the phase)

| Workstream | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Person-months |
|---|---:|---:|---:|---:|---:|
| ws01 Data integration and the per-car store | 7.0 | 6.0 | 7.0 | 3.5 | 141 |
| ws02 Entity resolution and VIN linkage | 6.0 | 4.0 | 6.0 | 5.0 | 126 |
| ws03 Claims controls and the rulebook map | 5.5 | 4.0 | 3.0 | 1.0 | 81 |
| ws04 Value engine re-mark and level charge | 5.0 | 4.0 | 4.0 | 2.0 | 90 |
| ws05 Readiness upgrade queue and retention pilot | 2.0 | 6.0 | 4.0 | 1.5 | 81 |
| ws06 Resale tools pricing desk channel and days | 0.0 | 2.0 | 5.0 | 1.5 | 51 |
| ws07 Dashboards | 1.5 | 1.0 | 1.0 | 0.5 | 24 |
| ws08 MLOps and model risk | 2.0 | 2.0 | 2.0 | 1.0 | 42 |
| ws09 Data rights privacy and governance | 2.5 | 1.5 | 1.5 | 0.5 | 36 |
| ws10 Change training and pilot operations | 1.0 | 2.0 | 4.0 | 3.0 | 60 |
| ws11 Programme management and benefit certification | 3.5 | 3.5 | 4.0 | 3.0 | 84 |
| All workstreams | 36.0 | 36.0 | 41.5 | 22.5 | 816 |

## People by role

| Role | Pay group | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Person-months |
|---|---|---:|---:|---:|---:|---:|
| engineer | OC2 | 13.0 | 13.0 | 14.0 | 7.0 | 282 |
| data_scientist | OC2 | 8.0 | 7.0 | 7.0 | 2.5 | 147 |
| architect | OC2 | 1.5 | 1.0 | 1.0 | 0.5 | 24 |
| product_owner | OC2 | 4.5 | 3.0 | 2.0 | 0.5 | 60 |
| model_validator | OC2 | 1.0 | 1.0 | 1.0 | 0.5 | 21 |
| legal_counsel | OC2 | 2.5 | 1.5 | 1.5 | 0.5 | 36 |
| change_lead | OC2 | 1.0 | 4.0 | 7.0 | 4.0 | 96 |
| finance_analyst | OC2 | 1.5 | 1.5 | 1.5 | 1.0 | 33 |
| programme_manager | OC1 | 2.0 | 2.0 | 2.5 | 2.0 | 51 |
| data_steward | OC3 | 1.0 | 2.0 | 4.0 | 4.0 | 66 |

| Pay group | Person-months | Share |
|---|---:|---:|
| Managers (OC1) | 51 | 6.2% |
| Professionals (OC2) | 699 | 85.7% |
| Technicians (OC3) | 66 | 8.1% |

Pay groups are the one-digit ISCO-08 groups in which Eurostat's Structure of Earnings Survey publishes
earnings by activity (`earn_ses22_49`): engineer: data, software and integration engineers: ISCO 25, professionals; data_scientist: data scientists and ML engineers: professionals; architect: solution, data and security architects: professionals; product_owner: product owners and business analysts: professionals; model_validator: independent model validation (second line): professionals; legal_counsel: data-protection and contract lawyers: ISCO 26, professionals; change_lead: change, training and pilot leads: professionals; finance_analyst: benefit certification in Finance: ISCO 24, professionals; programme_manager: programme director and programme office leads: managers; data_steward: review-queue data stewards: ISCO 3, technicians and associate professionals.

## The work list in one table

| Measure | Value |
|---|---:|
| Person-months over the programme | 816 |
| Average people over 24 months | 34.0 |
| Peak people in a phase | 41.5 |
| Engineering person-months (engineers, data scientists, architects) | 453 |
| Engineering share of all person-months | 55.5% |

## COCOMO II.2000: does the engineering work fit 24 months?

COCOMO II sizes software development, not governance, legal, change or finance work, so it reads only the
engineering roles. It is used backwards: not to size the work (a prototype's code says nothing about a
production system's size) but to ask whether the planned engineering effort fits the roadmap's schedule at
the model's nominal settings.

| COCOMO II.2000 reading | Value |
|---|---:|
| Scale exponent E at nominal scale factors | 1.0997 |
| Engineering effort (person-months) | 453 |
| Nominal schedule for that effort (months) | 25.7 |
| The roadmap's schedule as a share of nominal | 93.6% |
| Engineering effort COCOMO would schedule in exactly 24 months | 367 |

Schedule compression effort multiplier (SCED, Table 34): between 1.00 and 1.14 (between 85% and 100% of nominal). TDEV = C x PM^(D + 0.2 (E - B)), with A, B, C, D and the scale factors from the register (`cocomo_*`).

## What this is and is not

- It is the programme's own team. Business-as-usual staff are not charged: the people who decide held
  claims, the pricers and the dealers' staff do their jobs with the new tools; the change workstream pays
  for their training.
- It is one list for every base. Base 1 prices it at in-house wages, base 2 at vendor prices and an
  integrator's rates, base 3 with AI tools on the share of each role's work the studies measured.
- The rows carry no ranges. Stacking a guessed range on every guessed cell would add invented numbers; the
  uncertainty enters once, at the total, from sourced reference classes (McKinsey-Oxford's overruns, the
  Green Book's optimism bias) and from this report's COCOMO check.
- Three roadmap gates have no register row (the monthly mark against the retailer's realised prices, the
  engine recalibrated on backfilled returns, the legal basis for each source); their rows name them in the
  basis instead.
