# X22: gates that can be read inside each phase, and a stop

`analysis/gates.py`. Each gate is checked for whether the phase it closes produces the data to read it, and each has outcomes agreed before the programme starts: Go, Waiver with re-review, Delay, Back-up or Kill (Olechowski, Eppinger & Joglekar, ICED 2017). Agreed triggers turn a stop from a political fight into an operating decision (Keil & Montealegre, 2000); 30-40% of IS projects show some escalation of commitment (`kmr_escalation_*`). Every reading is held to 95% confidence and sized for 80% power (TARGET rows), and read by Finance with at least two reviewers from outside the programme (`gpd_feasibility_outside_min`, a UK precedent).

Three gates depend on build cost: the Phase 1 switch trigger, the Phase 2 money gate and the floor. Each has one value per X25 build scenario (`analysis/programme_cost_report.md`), and so does the funding a gate releases, the next phase's cost. No scenario is chosen: the table gives their range, and the table after it each scenario.

## The gates

| phase | gate | read on | readable inside the phase because | if missed | releases, next phase's cost (EUR m) |
|---|---|---|---|---|---|
| 1 | VIN link and dealer crosswalk, each at least 95% of claim value | the claim spine | a count over every claim | Delay: the next phase's funding waits; the build continues on Phase 1's money | 3.9-8.1 |
| 1 | Duplicate precision at least 90% | an audit of flagged claims, exact lower bound | 179 audited flags if the true precision is 95% (below) | Waiver with re-review: flags go to review, not to hold, until it reads | |
| 1 | Duplicate recall at least 70% | duplicates seeded into the claims stream with known answers | 119 seeded if the true recall is 80%; seeds cost nothing | Waiver with re-review | |
| 1 | Leakage baseline certified by Finance | the certified leak rate | Finance certifies it in the phase | **Back-up** if it is below the switch trigger (0.60-1.22% by build scenario, `gate_leak_switch_s1..s4_pct`): start with residual value, as the doc already says | |
| 1 | The ledger's monthly mark reconciled against Aramis's quarterly realised price per car (skeptic B10); the mark at trade starts 2.7-18.4% below the engine's asking price (the same-car gap bounded from audited accounts, `x24_gap_*`; a discount off asking comes on top) and reads the group's own trade results as they come (US trade leads retail by 2 months, `x24_us_lead_months`) | Aramis Group's published quarterly figures (`x10_aramis_*`) | quarterly, and Phase 1 spans two quarters | Waiver with re-review: the gap is explained before Phase 3 relies on the mark | |
| 1 | Legal basis agreed (X20's three items) | the signed terms | each is a signature | Back-up: the named fallback, and the exit gate's second line | |
| 2 | The engine recalibrated on the realised resale prices of the returns the ledger backfills (the asking-to-trade offset, skeptic B10; measured, it replaces Phase 1's bounded range) | the backfilled returns' sale prices | the backfill is a Phase 2 deliverable | Delay: Phase 3's engine gate is not read on an engine calibrated to asking prices | |
| 2 | Ledger reconciles to the general ledger within 0.5% | monthly close | every month | Delay | 4.3-9.1 |
| 2 | Claims recoveries certified in the pilot market at least EUR 2.0-4.0m a year by build scenario, annualised (`gate_claims_recovered_s1..s4_eur_m`, derived: what claims controls earn there at the switch trigger) | recoveries Finance certifies over the phase | the controls run in the pilot from Phase 2 | Back-up: residual value first; the claims lever is not scaled. Certified money, not only data quality, releases Phase 3's funding (skeptic A12) | |
| 2 | Retention uplift at least 2 points, lower bound above zero | orders signed inside the phase by customers whose contracts end in its first half; the group's flag randomised within dealers; one interim look | the pilot takes 46% of France's first-half contract endings (81% with spillover) | Back-up: cohort-level timing; the exit gate's second line; the lower bound, not the point estimate, enters the benefits case | |
| 3 | The engine's 80% band covers 75-85% of returned cars' realised prices | cars the buy-back book returns in the phase, level removed | 246 cars against an order of 120,000 returns in the core markets | Waiver with re-review: recalibrate by market and age (X15) and read again | 3.1-5.7 |
| 3 | The engine's car-specific error no worse than the bought guide's by more than 1 point | the same returned cars, both predictions as of the contract's start, the index move removed | 1499 paired cars if the two errors correlate 0.5 | **Back-up:** the guide keeps the price; the engine stays challenger and band-maker (F7) | |
| 3 | The band decision | pricers' first proposals, logged before the cap, against realised prices | 123 sold cars | Not pass or fail: engine only below X13's first break-even, the tied band between, the full band above the second | |
| 3 | Resale execution: at least 5 days cut, and routed cars' margin over the trade at least 0% after all costs | returns randomised between the old process and the new | sized in Phase 2 from the ledger's backfilled returns, which give the spread of days to sale | Back-up: the lever is not scaled; the case holds without it (X21) | |
| 3 | The certified run rate in the live markets at least the floor (`gate_exit_floor_s1..s4_eur_m`, 11.1-20.1 derived by build scenario) | Finance, annualised over the phase | claims controls have run since Phase 2 and the other levers through Phase 3 | **Kill:** Phase 4 is not funded (skeptic A13's named stop) | |
| 4 | Run-rate benefits certified at least the derived gate (`gate_benefits_eur_m`, 58.4 with every source) | Finance, against control groups | the levers live in the core markets | Waiver with re-review between the floor (11.1-20.1 by build scenario) and the gate: stay in the live markets; **Kill** below the floor: no run cost committed | |

## The gates that depend on build cost, by scenario

X21's Benefits sheet, each scenario's build cost by phase (`analysis/programme_cost_report.md`). EUR m unless stated. Loss if stopped: build cost spent less benefit earned by the gate (negative: a gain).

| | 1. In-house, no AI | 2. Buy and outsource | 3. In-house with AI | 4. Cheapest route per workstream |
|---|---|---|---|---|
| build cost over the four phases | 15.6 | 30.9 | 15.2 | 15.2 |
| Phase 1 switch trigger, % of claims-based spend | 0.61 | 1.22 | 0.60 | 0.60 |
| Phase 2 money gate, a year in the pilot | 2.0 | 4.0 | 2.0 | 2.0 |
| the floor from the Phase 3 gate, a year | 11.3 | 20.1 | 11.1 | 11.1 |
| released at the Phase 1 gate (Phase 2's cost) | 4.0 | 8.1 | 3.9 | 3.9 |
| released at the Phase 2 gate (Phase 3's cost) | 4.4 | 9.1 | 4.3 | 4.3 |
| released at the Phase 3 gate (Phase 4's cost) | 3.2 | 5.7 | 3.1 | 3.1 |
| loss if stopped at the gates of Phases 1, 2, 3, 4: the reference class | 6.7; 9.7; -21.9; -55.5 | 13.3; 23.1; -0.6; -30.0 | 6.5; 9.4; -22.3; -56.0 | 6.5; 9.4; -22.3; -56.0 |
| loss if stopped at the gates of Phases 1, 2, 3, 4: Flyvbjerg-Budzier's stress, 25% of benefits | 20.2; 39.1; 49.2; 53.4 | 40.1; 79.5; 113.2; 129.9 | 19.7; 38.2; 47.8; 51.7 | 19.7; 38.2; 47.8; 51.7 |

Scenarios 3 and 4 have the same build schedule: at rate-card prices every workstream's cheapest route is in-house with AI (X25).

In every scenario the loss if stopped grows gate by gate under the stress, so the first gate is where a stop saves most, and the one that must read cleanly (checked below).

## Phase 1: the audit, the seeds and the switch

Smallest sample whose exact one-sided lower bound clears the gate with the stated power, if the true value is as shown (a sizing grid, not an estimate).

| if the true precision is | audited flags |
|---|---|
| 93% | 549 |
| 95% | 179 |
| 97% | 76 |

| if the true recall is | seeded duplicates |
|---|---|
| 75% | 501 |
| 80% | 119 |
| 85% | 49 |

**The switch trigger:** 0.60-1.22% of claims-based incentive spend by build scenario (today's assumption `process_leak_pct` is 2%). Below it, claims controls do not repay the first two phases' build cost at the reference-class overrun within five years at the group's highest WACC, X21's decision basis. It is proportional to that cost, so the dearest build needs the highest leak rate. The whole programme still pays at a zero leak rate in every scenario (X21's switching values), so the trigger decides the order, not whether to go on: residual value first, as the doc already says when incentive spend is far below the assumption.

## Phase 2: the retention pilot

- **Size inside the phase.** Both arms of the chosen design (17,644 customers; 31,366 with a quarter of the uplift spilling over, X15) against France's contracts ending in the phase's first half (38,624 if as many end as start, `sfse_contracts_fr_2025`): 46% (81%). Enrolling the first half leaves the second half for orders to be signed before the gate.
- **One interim look** at half the customers, O'Brien-Fleming: critical values 2.797 at the look and 1.977 at the end, for 0.8% more customers at most (checked: the two-look design keeps the stated confidence and power). It lets the pilot stop early for a clear result either way at almost no cost.
- **Why the lower bound is carried.** Read only when significant, an estimate overstates the true uplift (Gelman & Carlin). At the design's standard error:

| true uplift (points) | power | sign-error rate | expected exaggeration if significant |
|---|---|---|---|
| 1.0 | 0.29 | 1.3e-03 | 1.85 |
| 2.0 | 0.80 | 1.2e-06 | 1.12 |
| 3.0 | 0.99 | 3.6e-10 | 1.01 |

A pilot that lands exactly on the gate has a lower bound of 0.6 points. That, not the point estimate, replaces `upgrade_capture_uplift` in the benefits case. Published nudge effects shrink from 8.7 to 1.4 points at scale, about 70% of it selective publication (`dvl_*`): one pre-registered arm and a powered sample remove that source; the lower bound covers the rest.

## Phase 3: the engine, the band and execution

- **Coverage:** 246 returned cars put a correctly calibrated 80% band inside 75-85% 95 times in 100.
- **Against the guide:** the engine's typical error (10.5%, a median absolute error) as a normal spread of 15.6 points; the paired difference's spread depends on how far the two errors move together on the same car:

| correlation of the two errors | paired cars needed |
|---|---|
| 0.25 | 2248 |
| 0.50 | 1499 |
| 0.75 | 750 |

- **Returns available:** the book due within a year (`buyback_payables_current_eur_m`), the core markets' share, one phase, at Aramis's realised retail price per car (EUR 17,722, `aramis_fy25_b2c_*`): an order of 120,000 cars. A retail price is above what the group pays back, so the count errs low. Every Phase 3 read needs a small fraction of it.
- **The band decision:** sold cars with a logged first proposal needed to tell apart pricer information (rho², X13) at the break-evens:

| decision | from | to | sold cars |
|---|---|---|---|
| engine only, or the tied band | 0 | 0.05 | 123 |
| the tied band, or the full band | 0.05 | 0.20 | 100 |

- **Why the adherence gate goes:** under a hard band every price is inside it, so the share inside is 100% by construction; and a share of adherence rewards deploying where people already comply (Goodhart). What the band needs to know is how much of the engine's error pricers can see, which the logged proposals measure.
- **Why the residual-cost gate goes:** contracts written in Phase 3 return 36-48 months later, and their loss is mostly the level, which nothing forecasts beyond a quarter (X7). Its 15% was also about twice the one published gain from a residual model's loss function (`dress_asym_cost_cut_pct`, 8%). The cars returning now answer the engine's question inside the phase.

## What this does not show

- **The sizing grids are hypothetical true values,** not estimates; the samples are fixed before each phase.
- **France's contract endings assume a steady book** (as many end as start); the pilot also needs its dealers' customers to be reachable in time.
- **The engine's spread is a normal approximation** from a median absolute error on adverts; the paired correlation with the guide is unknown until Phase 3's first cars, so the grid is shown.
- **The count of returns is an order of magnitude** from euros and a retail price per car.
- **O'Brien-Fleming assumes an immediate outcome;** orders signed inside the phase are one, by design.

## Checks

| check | got | passes |
|---|---|---|
| 1. In-house, no AI: at the switch trigger, claims controls repay exactly the first two phases' build cost | 0.611% | yes |
| 1. In-house, no AI: the programme still pays at a zero leak rate | survives at zero | yes |
| 1. In-house, no AI: under the stress, the loss if stopped grows gate by gate | 20.2 < 39.1 < 49.2 < 53.4 | yes |
| 2. Buy and outsource: at the switch trigger, claims controls repay exactly the first two phases' build cost | 1.224% | yes |
| 2. Buy and outsource: the programme still pays at a zero leak rate | survives at zero | yes |
| 2. Buy and outsource: under the stress, the loss if stopped grows gate by gate | 40.1 < 79.5 < 113.2 < 129.9 | yes |
| 3. In-house with AI: at the switch trigger, claims controls repay exactly the first two phases' build cost | 0.598% | yes |
| 3. In-house with AI: the programme still pays at a zero leak rate | survives at zero | yes |
| 3. In-house with AI: under the stress, the loss if stopped grows gate by gate | 19.7 < 38.2 < 47.8 < 51.7 | yes |
| 4. Cheapest route per workstream: at the switch trigger, claims controls repay exactly the first two phases' build cost | 0.598% | yes |
| 4. Cheapest route per workstream: the programme still pays at a zero leak rate | survives at zero | yes |
| 4. Cheapest route per workstream: under the stress, the loss if stopped grows gate by gate | 19.7 < 38.2 < 47.8 < 51.7 | yes |
| the exact lower bound matches scipy's Clopper-Pearson | 0.8977 | yes |
| a truer detector needs a smaller audit | 549 > 179 > 76 | yes |
| the pilot's size reproduces X14's share of France's year | 11.4% | yes |
| the two-look design keeps the stated confidence | 0.05000 | yes |
| and has the stated power at its inflated size | 0.80000 | yes |
| the exaggeration at the design's power reproduces Gelman & Carlin | 1.125 | yes |
| more correlated errors need fewer paired cars | 2248 > 1499 > 750 | yes |
| X13's break-evens are ordered | 0.224 < 0.447 | yes |

All checks pass.
