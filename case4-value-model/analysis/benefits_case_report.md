# X21: the benefits case

`analysis/benefits_case.py`. What the programme gets back, lever by lever, on X20's reach, and whether it pays for itself against a reference class, a stress and switching values. EUR millions, advert-price bases as the value-at-risk workbook's. The workbook's Benefits sheet computes the same with live formulas; the audit checks one against the other.

## Coverage: where each phase runs

The group's (PSA + FCA brands) share of new-car registrations, EU and EFTA (the UK is not in the file). The pilot is France, where X14 sized the Phase 2 pilot; the core markets are those above the largest break in the ranked shares.

| market set | markets | 2024 share (%) | 2025 share (%) |
|---|---|---|---|
| pilot | FR | 28.1 | 27.5 |
| core | FR, IT, DE, ES | 80.9 | 79.1 |
| next largest | BE | 3.0 | 3.3 |

Phase 1 earns nothing (the baseline is being certified). Claims controls run in the pilot from Phase 2; retention, resale execution and the little-history engine in the core markets from Phase 3; targeting from Phase 4; every market after the exit (solution doc 8.1). The pilot's randomised arm in Phase 2 is left out: it is small (x14_pilot_share_fr) and measures rather than earns.

## The levers

Yearly benefit at full coverage, EUR m, on each source scenario (X20). Each euro sits in one class only.

| lever | class | starts in | every source | without the joint ventures' data | without dealers' VIN-level evidence | measured by |
|---|---|---|---|---|---|---|
| Claims controls | recovered | Phase 2 | 23.4 | 23.4 | 8.7 | Phase 1: duplicate precision and the certified leakage baseline (gate_dup_*) |
| Retention at the upgrade moment | recovered | Phase 3 | 38.8 | 0.0 | 38.8 | Phase 2: uplift over a randomised control group (gate_uplift_pp) |
| Resale execution: days cut | recovered | Phase 3 | 16.3 | 16.3 | 16.3 | Phase 3: days to sale on returns against the pre-programme record (X22) |
| Resale execution: own retail | recovered | Phase 3 | 8.5 | 8.5 | 8.5 | Phase 3: retail margin per routed car against the trade (X22) |
| Income targeting (X5) | upper bound, needs a holdout | Phase 4 | 18.5 | 5.0 | 18.5 | Phase 3: randomised incentive holdouts |
| Little-history cars priced as known cars | tail reduced, one year in ten | Phase 3 | 20.7 | 20.7 | 20.7 | Phase 3: little-history error (kpi_thin_error_points) |
| **Committed, expected a year** | recovered | | **87.0** | **48.2** | **72.3** | Phase 4 exit (below) |

- **Priced, not recovered (no euro here):** the level charge on contracts where the customer holds the option (X6) and the buy-back book's cold premium (X19). On the book the level counts both ways and gains on average (X18); a charge moves a tail cost into a price. Lenders price a market-wide collateral risk too (`fliegel_*`), so it is not a margin the group alone can keep.
- **Enablers (no euro of their own):** X19's transfer price and the operating metric, X13's band, the ledger. They are how the counted levers happen; counting them again would count the same euro twice.
- **Targeting is shown, never committed:** X5's figure assumes income is known exactly, and the uplift test found no model beating plain response targeting (X15). Only a randomised holdout on the incentive's level can turn it into a benefit.
- **The incentive's average level is in the same class, unsized (skeptic B2, X24).** Whether the group spends too much on average is a question public data can't answer: demand models set margins by assuming prices maximise profit, and discount series move with demand. The one long-run measurement we found: carmakers' promotions raised firm value for 43% of brands, against 81% for new models (US data, `pauwels_*`). The same randomised holdout measures it, read over a window long enough to catch sales pulled forward (`x5_pull_forward`) and net of each discount euro's resale cost (X5). No euro is counted.
- **The tail lever is an upper bound in the one-in-ten column:** little-history cars' one-year curve error falling from the no-history band to the own-data band, at the measured joint share (X18). It arrives as the ledger's own sales make them known cars.

## The headline split

| | expected a year | one year in ten |
|---|---|---|
| At risk (the headline, two measures) | 205.6 | 298.1 |
| Addressable: what the levers can reach, every source (Data reach sheet) | 160.1 | - |
| Planned benefit, committed levers | 87.0 | 107.6 |
| The same at the reference class (McKinsey-Oxford software: 17% short) | 72.2 | 89.3 |
| Upper bound beside it, never committed: income targeting | 18.5 | 18.5 |
| Certified today | 0 | 0 |

Every committed rate is an assumption (`recoverable_share`, `upgrade_capture_uplift`, `x17_days_cut`, `x17_share_routed`) on a disclosed or measured base, so all of the planned benefit needs the pilot. Nothing is certified until Finance certifies the Phase 1 baseline. The one-in-ten column adds only the tail lever: the level itself is priced, never recovered, so its reach is not a benefit's reach and is left blank.

## The cases

| case | benefits realised (%) | build cost (% of plan) | months a phase | source |
|---|---|---|---|---|
| plan | 100 | 100 | 6.0 | the register |
| reference class | 83 | 166 | 8.0 | McKinsey-Oxford, software projects (`mckox_sw_*`) |
| stress, 25% of benefits | 25 | 500 | 8.0 | Flyvbjerg-Budzier's stress test (`fb_stress_*`), phases as the reference class |
| stress, 50% of benefits | 50 | 500 | 8.0 | the same, the stress's high end |
| adverse ends | 83 | 166 | 8.0 | the reference class, with every assumed rate at the end of its register range that hurts the case, together: the low ends of `process_leak_pct`, `recoverable_share`, `upgrade_capture_uplift`, `margin_per_repeat_sale`, `x17_days_cut`, `x17_share_routed` and the high end of `run_cost_eur_m_year` (committed benefit 20.0 a year at full coverage) |

## Payback by build scenario

X25 priced one work list four ways (`analysis/programme_cost_report.md`); none is chosen here. Build cost is paid at the start of each phase at the case's overrun; benefits and the run cost accrue evenly. The loss if the programme stops at a gate is the build cost spent so far less the benefit earned so far.

| scenario | build, EUR m | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|---|---|---|---|---|---|
| 1. In-house, no AI | 15.6 | 4.03 | 4.01 | 4.35 | 3.17 |
| 2. Buy and outsource | 30.9 | 8.02 | 8.09 | 9.08 | 5.68 |
| 3. In-house with AI | 15.2 | 3.94 | 3.93 | 4.26 | 3.12 |
| 4. Cheapest route per workstream | 15.2 | 3.94 | 3.93 | 4.26 | 3.12 |

| scenario | case | payback month | loss if stopped at the Phase 1 gate (negative: a gain) | at Phase 2 | at Phase 3 | at Phase 4 |
|---|---|---|---|---|---|---|
| 1. In-house, no AI | plan | 13.6 | 4.0 | 4.8 | -26.1 | -58.1 |
| 1. In-house, no AI | reference class | 19.4 | 6.7 | 9.7 | -21.9 | -55.5 |
| 1. In-house, no AI | stress, 25% of benefits | 70.2 | 20.2 | 39.1 | 49.2 | 53.4 |
| 1. In-house, no AI | stress, 50% of benefits | 40.9 | 20.2 | 38.0 | 36.4 | 28.9 |
| 1. In-house, no AI | adverse ends | 42.7 | 6.7 | 13.0 | 11.4 | 7.7 |
| 2. Buy and outsource | plan | 15.7 | 8.0 | 12.8 | -13.3 | -42.8 |
| 2. Buy and outsource | reference class | 23.8 | 13.3 | 23.1 | -0.6 | -30.0 |
| 2. Buy and outsource | stress, 25% of benefits | none within ten years | 40.1 | 79.5 | 113.2 | 129.9 |
| 2. Buy and outsource | stress, 50% of benefits | 64.8 | 40.1 | 78.4 | 100.4 | 105.4 |
| 2. Buy and outsource | adverse ends | 78.3 | 13.3 | 26.4 | 32.6 | 33.1 |
| 3. In-house with AI | plan | 13.5 | 3.9 | 4.6 | -26.3 | -58.4 |
| 3. In-house with AI | reference class | 19.3 | 6.5 | 9.4 | -22.3 | -56.0 |
| 3. In-house with AI | stress, 25% of benefits | 69.0 | 19.7 | 38.2 | 47.8 | 51.7 |
| 3. In-house with AI | stress, 50% of benefits | 40.4 | 19.7 | 37.2 | 35.0 | 27.2 |
| 3. In-house with AI | adverse ends | 42.0 | 6.5 | 12.8 | 10.9 | 7.2 |
| 4. Cheapest route per workstream | plan | 13.5 | 3.9 | 4.6 | -26.3 | -58.4 |
| 4. Cheapest route per workstream | reference class | 19.3 | 6.5 | 9.4 | -22.3 | -56.0 |
| 4. Cheapest route per workstream | stress, 25% of benefits | 69.0 | 19.7 | 38.2 | 47.8 | 51.7 |
| 4. Cheapest route per workstream | stress, 50% of benefits | 40.4 | 19.7 | 37.2 | 35.0 | 27.2 |
| 4. Cheapest route per workstream | adverse ends | 42.0 | 6.5 | 12.8 | 10.9 | 7.2 |

## Value

Net present value at the group's pre-tax WACC range (9.5-19.0%, `stla_wacc_*`), over the Green Book's five-year IT example and its ten-year default, the build inside both. EUR m.

| scenario | case | 5 years, highest WACC | 5 years, lowest | 10 years, highest | 10 years, lowest |
|---|---|---|---|---|---|
| 1. In-house, no AI | plan | 178.5 | 229.4 | 293.1 | 438.6 |
| 1. In-house, no AI | reference class | 117.2 | 155.6 | 211.1 | 327.1 |
| 1. In-house, no AI | stress, 25% of benefits | -28.8 | -23.3 | -5.4 | 19.4 |
| 1. In-house, no AI | stress, 50% of benefits | 15.0 | 33.2 | 68.8 | 131.4 |
| 1. In-house, no AI | adverse ends | 1.2 | 5.6 | 13.1 | 27.5 |
| 2. Buy and outsource | plan | 164.8 | 215.0 | 279.4 | 424.2 |
| 2. Buy and outsource | reference class | 95.4 | 132.2 | 189.3 | 303.7 |
| 2. Buy and outsource | stress, 25% of benefits | -94.5 | -93.9 | -71.1 | -51.2 |
| 2. Buy and outsource | stress, 50% of benefits | -50.8 | -37.4 | 3.0 | 60.9 |
| 2. Buy and outsource | adverse ends | -20.7 | -17.8 | -8.7 | 4.0 |
| 3. In-house with AI | plan | 178.8 | 229.7 | 293.3 | 438.9 |
| 3. In-house with AI | reference class | 117.7 | 156.1 | 211.6 | 327.6 |
| 3. In-house with AI | stress, 25% of benefits | -27.4 | -21.8 | -4.0 | 20.9 |
| 3. In-house with AI | stress, 50% of benefits | 16.4 | 34.7 | 70.2 | 132.9 |
| 3. In-house with AI | adverse ends | 1.6 | 6.1 | 13.6 | 28.0 |
| 4. Cheapest route per workstream | plan | 178.8 | 229.7 | 293.3 | 438.9 |
| 4. Cheapest route per workstream | reference class | 117.7 | 156.1 | 211.6 | 327.6 |
| 4. Cheapest route per workstream | stress, 25% of benefits | -27.4 | -21.8 | -4.0 | 20.9 |
| 4. Cheapest route per workstream | stress, 50% of benefits | 16.4 | 34.7 | 70.2 | 132.9 |
| 4. Cheapest route per workstream | adverse ends | 1.6 | 6.1 | 13.6 | 28.0 |

The decision basis (the reference class, five years, highest WACC) on each source scenario: 1. In-house, no AI: every source 117.2, without the joint ventures' data 53.8, without dealers' VIN-level evidence 91.2; 2. Buy and outsource: every source 95.4, without the joint ventures' data 31.9, without dealers' VIN-level evidence 69.4; 3. In-house with AI: every source 117.7, without the joint ventures' data 54.2, without dealers' VIN-level evidence 91.7; 4. Cheapest route per workstream: every source 117.7, without the joint ventures' data 54.2, without dealers' VIN-level evidence 91.7.

## Switching values

The Green Book gives no default for benefit shortfall and asks for switching values instead (4.1): how far an input can move before the case stops paying. On the decision basis, for each build scenario.

| input | today | 1. In-house, no AI | 2. Buy and outsource | 3. In-house with AI | 4. Cheapest route per workstream |
|---|---|---|---|---|---|
| share of benefits that can be lost (%) | 0 | 81 | 66 | 81 | 81 |
| build cost overrun absorbed (% of plan) | 66 (reference) | 947 | 427 | 969 | 969 |
| run cost (EUR m a year) | 5.0 | 101.9 | 83.9 | 102.3 | 102.3 |
| process_leak_pct | 2 | survives at zero | survives at zero | survives at zero | survives at zero |
| recoverable_share | 30 | survives at zero | survives at zero | survives at zero | survives at zero |
| upgrade_capture_uplift | 3 | survives at zero | survives at zero | survives at zero | survives at zero |
| margin_per_repeat_sale | 2000 | survives at zero | survives at zero | survives at zero | survives at zero |
| x17_days_cut | 10 | survives at zero | survives at zero | survives at zero | survives at zero |
| x17_share_routed | 5 | survives at zero | survives at zero | survives at zero | survives at zero |

The build overrun a case absorbs is set against the Green Book's unmitigated upper bound for ICT (200%) and Flyvbjerg-Budzier's stress (400%); no reference class exists for operating cost (Green Book 4.1).

## The exit gate, derived

The Phase 4 exit gate was set at EUR 80m a year, 'above' an older controls figure and 'about four times the ask' (skeptic B1), the single ask X25 retired: true by construction. Derived instead: the run rate the committed levers earn in the markets live at month 24 at the reference class, which Finance can certify against control groups. It depends on benefits only, so it is the same in every scenario.

| | run rate at the exit, EUR m a year |
|---|---|
| gate, every source | 58.4 |
| gate, without the joint ventures' data | 32.4 |
| gate, without dealers' VIN-level evidence | 48.5 |
| on our own adverse ends (every assumed rate at once) | 13.4 |

The gates that depend on build cost, one per scenario (to X22): the floor, below which the decision basis is worth nothing; the Phase 1 switch trigger, the certified leak rate below which claims controls do not repay the first two phases; the Phase 2 money gate, what claims controls then earn in the pilot market.

| gate | 1. In-house, no AI | 2. Buy and outsource | 3. In-house with AI | 4. Cheapest route per workstream |
|---|---|---|---|---|
| floor, EUR m a year | 11.3 | 20.1 | 11.1 | 11.1 |
| Phase 1 switch trigger, % of claims-based spend | 0.61 | 1.22 | 0.60 | 0.60 |
| Phase 2 money gate, EUR m a year | 2.0 | 4.0 | 2.0 | 2.0 |

The gate is set with the joint-venture arrangement agreed at Phase 1 (X22's named legal basis); on the named fallback it is the second line. The floor reads a certified run rate as where the rates landed, so the whole benefit profile scales with it: the gate times the share of benefits that can be lost (the switching value). Both are in the markets live at month 24.

### The reference class, period by period, for each scenario (EUR m)

**1. In-house, no AI**

| period | months | build cost | benefit | run cost | cumulative |
|---|---|---|---|---|---|
| Phase 1 | 0-8 | 6.7 | 0.0 | 0.0 | -6.7 |
| Phase 2 | 8-16 | 6.7 | 3.6 | 0.0 | -9.7 |
| Phase 3 | 16-24 | 7.2 | 38.8 | 0.0 | 21.9 |
| Phase 4 | 24-32 | 5.3 | 38.8 | 0.0 | 55.5 |
| Year 1 after the exit | 32-44 | 0.0 | 72.2 | 5.0 | 122.7 |
| Year 2 after the exit | 44-56 | 0.0 | 72.2 | 5.0 | 189.8 |
| Year 3 after the exit | 56-68 | 0.0 | 72.2 | 5.0 | 257.0 |
| Year 4 after the exit | 68-80 | 0.0 | 72.2 | 5.0 | 324.2 |
| Year 5 after the exit | 80-92 | 0.0 | 72.2 | 5.0 | 391.4 |
| Year 6 after the exit | 92-104 | 0.0 | 72.2 | 5.0 | 458.6 |
| Year 7 after the exit | 104-116 | 0.0 | 72.2 | 5.0 | 525.8 |
| Year 8 after the exit | 116-120 | 0.0 | 24.5 | 1.7 | 548.6 |

**2. Buy and outsource**

| period | months | build cost | benefit | run cost | cumulative |
|---|---|---|---|---|---|
| Phase 1 | 0-8 | 13.3 | 0.0 | 0.0 | -13.3 |
| Phase 2 | 8-16 | 13.4 | 3.6 | 0.0 | -23.1 |
| Phase 3 | 16-24 | 15.1 | 38.8 | 0.0 | 0.6 |
| Phase 4 | 24-32 | 9.4 | 38.8 | 0.0 | 30.0 |
| Year 1 after the exit | 32-44 | 0.0 | 72.2 | 5.0 | 97.2 |
| Year 2 after the exit | 44-56 | 0.0 | 72.2 | 5.0 | 164.4 |
| Year 3 after the exit | 56-68 | 0.0 | 72.2 | 5.0 | 231.6 |
| Year 4 after the exit | 68-80 | 0.0 | 72.2 | 5.0 | 298.8 |
| Year 5 after the exit | 80-92 | 0.0 | 72.2 | 5.0 | 366.0 |
| Year 6 after the exit | 92-104 | 0.0 | 72.2 | 5.0 | 433.2 |
| Year 7 after the exit | 104-116 | 0.0 | 72.2 | 5.0 | 500.4 |
| Year 8 after the exit | 116-120 | 0.0 | 24.5 | 1.7 | 523.2 |

**3. In-house with AI**

| period | months | build cost | benefit | run cost | cumulative |
|---|---|---|---|---|---|
| Phase 1 | 0-8 | 6.5 | 0.0 | 0.0 | -6.5 |
| Phase 2 | 8-16 | 6.5 | 3.6 | 0.0 | -9.4 |
| Phase 3 | 16-24 | 7.1 | 38.8 | 0.0 | 22.3 |
| Phase 4 | 24-32 | 5.2 | 38.8 | 0.0 | 56.0 |
| Year 1 after the exit | 32-44 | 0.0 | 72.2 | 5.0 | 123.2 |
| Year 2 after the exit | 44-56 | 0.0 | 72.2 | 5.0 | 190.4 |
| Year 3 after the exit | 56-68 | 0.0 | 72.2 | 5.0 | 257.6 |
| Year 4 after the exit | 68-80 | 0.0 | 72.2 | 5.0 | 324.8 |
| Year 5 after the exit | 80-92 | 0.0 | 72.2 | 5.0 | 392.0 |
| Year 6 after the exit | 92-104 | 0.0 | 72.2 | 5.0 | 459.1 |
| Year 7 after the exit | 104-116 | 0.0 | 72.2 | 5.0 | 526.3 |
| Year 8 after the exit | 116-120 | 0.0 | 24.5 | 1.7 | 549.2 |

**4. Cheapest route per workstream**

| period | months | build cost | benefit | run cost | cumulative |
|---|---|---|---|---|---|
| Phase 1 | 0-8 | 6.5 | 0.0 | 0.0 | -6.5 |
| Phase 2 | 8-16 | 6.5 | 3.6 | 0.0 | -9.4 |
| Phase 3 | 16-24 | 7.1 | 38.8 | 0.0 | 22.3 |
| Phase 4 | 24-32 | 5.2 | 38.8 | 0.0 | 56.0 |
| Year 1 after the exit | 32-44 | 0.0 | 72.2 | 5.0 | 123.2 |
| Year 2 after the exit | 44-56 | 0.0 | 72.2 | 5.0 | 190.4 |
| Year 3 after the exit | 56-68 | 0.0 | 72.2 | 5.0 | 257.6 |
| Year 4 after the exit | 68-80 | 0.0 | 72.2 | 5.0 | 324.8 |
| Year 5 after the exit | 80-92 | 0.0 | 72.2 | 5.0 | 392.0 |
| Year 6 after the exit | 92-104 | 0.0 | 72.2 | 5.0 | 459.1 |
| Year 7 after the exit | 104-116 | 0.0 | 72.2 | 5.0 | 526.3 |
| Year 8 after the exit | 116-120 | 0.0 | 24.5 | 1.7 | 549.2 |

## What this does not show

- **The rates are assumptions.** Every committed lever rests on an assumed rate over a disclosed or measured base. The switching values say which one the case leans on; the gates measure them.
- **The reference class is large IT projects, 2012, across industries,** not data programmes in carmakers. Public-sector data-management projects overrun in the tail twice as often as the average (`bf_public_datamgmt_outlier_pct`): the reason the phase gates and a stop matter more than the mean.
- **Coverage is registrations, EU and EFTA,** as a proxy for every lever's base; the UK is missing from the file.
- **The tail lever uses the measured joint share at the margin,** an approximation, and is an upper bound.
- **The merger's own synergy record** (EUR 8.4bn against 5bn, `stla_synergies_*`) is not a reference class: it was a merger, and it was counted by those paid on it. It sets the convention (net of implementation costs, cash) and the reason benefits are certified by Finance against control groups.

## Checks

| check | got | passes |
|---|---|---|
| the pilot market is the group's largest, both years | FR, FR | yes |
| the core markets are the same set in both years | FR, IT, DE, ES | yes |
| the break: the smallest core share over the largest other | 3.06 | yes |
| every lever's reach equals the workbook's Data reach sheet | largest gap 1.42e-14 | yes |
| claims controls equal the Leak 1 sheet's recovered line | 23.398 | yes |
| the committed benefit sits inside the expected column | 87.0 < 205.6 | yes |
| 1. In-house, no AI: at a zero rate, build cost is the schedule's sum | 15.6 | yes |
| 1. In-house, no AI: NPV falls as the rate rises | high < low | yes |
| 1. In-house, no AI: at its switching value, the build overrun zeroes the decision basis | -2.84e-14 | yes |
| 1. In-house, no AI: losing the switching share of benefits zeroes the value | -3.55e-15 | yes |
| 2. Buy and outsource: at a zero rate, build cost is the schedule's sum | 30.9 | yes |
| 2. Buy and outsource: NPV falls as the rate rises | high < low | yes |
| 2. Buy and outsource: at its switching value, the build overrun zeroes the decision basis | 0.00e+00 | yes |
| 2. Buy and outsource: losing the switching share of benefits zeroes the value | 0.00e+00 | yes |
| 3. In-house with AI: at a zero rate, build cost is the schedule's sum | 15.2 | yes |
| 3. In-house with AI: NPV falls as the rate rises | high < low | yes |
| 3. In-house with AI: at its switching value, the build overrun zeroes the decision basis | 0.00e+00 | yes |
| 3. In-house with AI: losing the switching share of benefits zeroes the value | 0.00e+00 | yes |
| 4. Cheapest route per workstream: at a zero rate, build cost is the schedule's sum | 15.2 | yes |
| 4. Cheapest route per workstream: NPV falls as the rate rises | high < low | yes |
| 4. Cheapest route per workstream: at its switching value, the build overrun zeroes the decision basis | 0.00e+00 | yes |
| 4. Cheapest route per workstream: losing the switching share of benefits zeroes the value | 0.00e+00 | yes |
| every adverse end is an assumption's own low or high | 7 inputs | yes |
| the stress at 25% of benefits is worth less than at 50% | 25% < 50% | yes |

All checks pass.
