# The programme's build cost on four bases (X25 parts 4-6)

The same work list (`work_list.csv`, part 1) priced four ways; EUR millions over the 24-month build unless
stated. The workbook's "Programme cost" and "Work list" sheets hold the same arithmetic as formulas, and the
audit checks them against this script. Built by `analysis/programme_cost.py`.

## Part 4: what AI saves, by role

Engineers and data scientists: the share of the week coding, debugging and review take (Time Warp, about 25%) times each study's gain. Central: Cui et al.'s field experiments (more completed tasks, read as less time a task). Upper: Peng et al.'s single task. Adverse: METR's early-2025 trial, where experienced developers took longer. Every other role: the time Danish chatbot adopters report saving (Humlum & Vestergaard), with none in the adverse case. Seats: Copilot Enterprise for the coders plus a Claude Team seat for everyone, converted at the ECB rate.

| Role | Saving, central | Saving, upper | Saving, adverse | Seats (EUR a month) |
|---|---:|---:|---:|---:|
| engineer | 5.2% | 13.9% | -4.8% | 50.70 |
| data_scientist | 5.2% | 13.9% | -4.8% | 50.70 |
| architect | 3.0% | 3.0% | 0.0% | 17.19 |
| product_owner | 3.0% | 3.0% | 0.0% | 17.19 |
| model_validator | 3.0% | 3.0% | 0.0% | 17.19 |
| legal_counsel | 3.0% | 3.0% | 0.0% | 17.19 |
| change_lead | 3.0% | 3.0% | 0.0% | 17.19 |
| finance_analyst | 3.0% | 3.0% | 0.0% | 17.19 |
| programme_manager | 3.0% | 3.0% | 0.0% | 17.19 |
| data_steward | 3.0% | 3.0% | 0.0% | 17.19 |

## What a person-month costs, by role (EUR)

In-house: the loaded cost of an employee in manufacturing (Eurostat), plus overhead, where the role sits. Integrator: the public rate card's day rate (Deloitte, G-Cloud 14, UK, a ceiling) in euros, times the working days in a month. Blank: the group keeps the role.

| Role | In-house, central team | In-house, in the four markets | In-house, the hub | Integrator |
|---|---:|---:|---:|---:|
| engineer | 10,125 | 10,178 | 3,848 | 27,265 |
| data_scientist | 10,125 | 10,178 | 3,848 | 34,874 |
| architect | 10,125 | 10,178 | 3,848 | 38,573 |
| product_owner | 10,125 | 10,178 | 3,848 | 34,874 |
| model_validator | 10,125 | 10,178 | 3,848 |  |
| legal_counsel | 10,125 | 10,178 | 3,848 |  |
| change_lead | 10,125 | 10,178 | 3,848 | 34,874 |
| finance_analyst | 10,125 | 10,178 | 3,848 |  |
| programme_manager | 19,607 | 17,897 | 5,980 | 44,386 |
| data_steward | 6,890 | 7,598 | 3,162 | 23,038 |

## The four bases

| Base | People | AI tools | Platform, data and licences | Change delivery | Total |
|---|---:|---:|---:|---:|---:|
| 1. In-house, no AI | 8.6 | 0.00 | 4.0 | 3.0 | 15.6 |
| 2. Buy and outsource (rate card) | 23.9 | 0.00 | 4.0 | 3.0 | 30.9 |
| 3. In-house with AI, central | 8.2 | 0.03 | 4.0 | 3.0 | 15.2 |
| 3. In-house with AI, upper gain | 7.8 | 0.03 | 4.0 | 3.0 | 14.9 |
| 3. In-house with AI, adverse | 8.8 | 0.03 | 4.0 | 3.0 | 15.8 |
| 4. Cheapest route per workstream | 8.2 | 0.00 | 4.0 | 3.0 | 15.2 |
| 2 at Consip's Italian public team-day | 3.1 | 0.00 | 4.0 | 3.0 | 10.1 |
| 2 with the integrator's engineers offshore | 19.6 | 0.00 | 4.0 | 3.0 | 26.6 |
| 1 with the coders in the hub | 5.9 | 0.00 | 4.0 | 3.0 | 12.9 |

Base 4 carries base 3's tools within its people column (each workstream's cost is priced whole).

## Base 4: each workstream's cheapest route

| Workstream | Base 1 | Base 2 | Base 3 | Rule | Chosen | Base 4 |
|---|---:|---:|---:|---|---|---:|
| ws01 Data integration and the per-car store | 1.43 | 4.08 | 1.36 | always built | in-house with AI | 1.36 |
| ws02 Entity resolution and VIN linkage | 1.10 | 3.41 | 1.06 | cheapest | in-house with AI | 1.06 |
| ws03 Claims controls and the rulebook map | 0.82 | 2.55 | 0.79 | cheapest | in-house with AI | 0.79 |
| ws04 Value engine re-mark and level charge | 0.91 | 2.91 | 0.87 | always built | in-house with AI | 0.87 |
| ws05 Readiness upgrade queue and retention pilot | 0.82 | 2.73 | 0.79 | cheapest | in-house with AI | 0.79 |
| ws06 Resale tools pricing desk channel and days | 0.52 | 1.60 | 0.50 | cheapest | in-house with AI | 0.50 |
| ws07 Dashboards | 0.24 | 0.68 | 0.23 | cheapest | in-house with AI | 0.23 |
| ws08 MLOps and model risk | 0.43 | 0.79 | 0.41 | cheapest | in-house with AI | 0.41 |
| ws09 Data rights privacy and governance | 0.36 | 0.45 | 0.35 | cheapest | in-house with AI | 0.35 |
| ws10 Change training and pilot operations | 0.61 | 2.09 | 0.59 | cheapest | in-house with AI | 0.59 |
| ws11 Programme management and benefit certification | 1.33 | 2.60 | 1.30 | cheapest | in-house with AI | 1.30 |

## Switching values

| Switching value | Value |
|---|---:|
| Overhead on in-house cost at which bases 1 and 2 cost the same (%) | 259.9 |
| One integrator day rate for every handed-over role at which bases 1 and 2 cost the same (EUR) | 575 |
| Integrator days in base 2 | 13,310 |

## By phase (EUR m; platform and change delivery spread evenly)

| Base | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|---|---:|---:|---:|---:|
| 1. In-house, no AI | 4.0 | 4.0 | 4.4 | 3.2 |
| 2. Buy and outsource (rate card) | 8.0 | 8.1 | 9.1 | 5.7 |
| 3. In-house with AI, central | 3.9 | 3.9 | 4.3 | 3.1 |
| 4. Cheapest route per workstream | 3.9 | 3.9 | 4.3 | 3.1 |

## Part 6: reading it

Each scenario's build schedule read through X21's own benefit model (`analysis/benefits_case.py`: the same
benefits, run cost, horizons and overlay cases); only the build cost by phase changes. Rates are the group's
pre-tax WACC range (9.5% and 19.0%); the benefits case is judged at the high end. No scenario is
chosen: each is shown.

### Value, payback and cash at risk by scenario

NPV in EUR m at 19.0% (the plan and the reference class: McKinsey-Oxford's overruns on cost, schedule and benefits), payback in months (the plan), and cash lost if the programme stops at the end of Phase 1 or 2.

| Scenario | Build | Payback | NPV, 5 years | NPV, 10 years | NPV, 5 years, reference class | Lost if stopped after Phase 1 | Lost if stopped after Phase 2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1. In-house, no AI | 15.6 | 13.6 | 178.5 | 293.1 | 117.2 | 4.0 | 4.8 |
| 2. Buy and outsource | 30.9 | 15.7 | 164.8 | 279.4 | 95.4 | 8.0 | 12.8 |
| 3. In-house with AI | 15.2 | 13.5 | 178.8 | 293.3 | 117.7 | 3.9 | 4.6 |
| 4. Cheapest route per workstream | 15.2 | 13.5 | 178.8 | 293.3 | 117.7 | 3.9 | 4.6 |
| What-if: 4, with an integrator for Phase 1 | 19.3 | 14.2 | 174.7 | 289.3 | 110.9 | 8.0 | 8.7 |

### Hiring lag: when buying time pays

No public source gives months to hire data specialists (Eurostat measures only how many recruiters find vacancies hard to fill: `x25_ict_hardfill_*`), so the lag is read as a switching value: how late an in-house start (base 4) could be before a start at once is worth its price, at 19.0% over 5 years.

| In-house hiring lag at which it pays to buy, months | The plan | The reference class | Stress, 50% of benefits |
|---|---:|---:|---:|
| An integrator for Phase 1 only | 0.8 | 1.7 | 14.3 |
| The whole build bought | 2.6 | 5.7 | never within 24 months |

The integrator's own mobilisation is not costed: the lag is the head start an integrator must have over the in-house team, so a slower integrator needs a longer in-house lag to pay.

### The accounting view

The group's 2025 20-F capitalises the part of internal-use software development that is "directly attributable internal or external costs necessary to create the software or improve its performance" and expenses the rest. The engineering roles' cost in the software workstreams (ws01-ws08) is capitalisable in every base: the group controls the software whether its staff or an integrator builds it, so the IFRIC SaaS decision does not apply. Seats, platform subscriptions, change, governance, pilots and programme management are expensed. The 20-F states no useful life for internal-use software.

| Base | Capitalisable (EUR m) | Expensed in the build (EUR m) | Capitalisable share |
|---|---:|---:|---:|
| 1. In-house, no AI | 4.6 | 11.0 | 29.3% |
| 2. Buy and outsource | 13.6 | 17.3 | 44.1% |
| 3. In-house with AI | 4.3 | 10.9 | 28.4% |
| 4. Cheapest route per workstream | 4.3 | 10.9 | 28.4% |

### Pay and assumptions

| Switching value | Value |
|---|---:|
| Pay premium over the occupation-group mean, every in-house professional, at which base 1 costs as much as base 2 (%) | 248.1 |

| Assumption at its low and high end | Base 1, low | Base 1, high | Base 2, low | Base 2, high | Base 4, low | Base 4, high |
|---|---:|---:|---:|---:|---:|---:|
| x25_overhead_pct | 14.9 | 16.3 | 30.8 | 31.0 | 14.6 | 15.9 |
| x25_loc_fr_pct | 15.4 | 15.8 | 30.8 | 30.9 | 15.0 | 15.5 |
| x25_days_per_fte_year | 15.6 | 15.6 | 29.8 | 31.4 | 15.2 | 15.2 |

## What this is and is not

- Build cost only, over the 24 months. The run cost after month 24, the risk overlay, time to benefit, NPV,
  spend at each gate and the accounting view are part 6's reading.
- Base 2's rates are a UK public framework's maximums: a ceiling. The switching day rate says how far an
  integrator's price must fall before handing the work over is cheaper; Consip's Italian public team-day is a
  floor far below any carmaker's market, shown only as the other end.
- Base 3's saving counts only because the teams are sized to it: most chatbot users move saved time to other
  tasks (`hv_reallocated_pct`). No adoption or training cost is counted; none is sourced.
- The hub line moves engineers and data scientists to the lower-cost hub's pay and counts no coordination
  cost; no source sizes one, so it is an upper bound on the saving.
