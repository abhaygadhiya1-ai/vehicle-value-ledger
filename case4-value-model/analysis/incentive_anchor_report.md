# Leak 1's outside anchor: the group's own incentive claims (X14 part 4)

The group's 20-F (FY2025, Note 21) carries a sales-incentive provision. What it adds each year is the estimated cost of
incentive programmes on cars sold to dealers; what it settles is the programmes claimed and paid. Both are worldwide.
As a share of the group's net revenues:

| year | flow | EUR m | net revenues, EUR m | share of net revenues (%) |
|---|---|---|---|---|
| 2025 | additions | 10,362 | 153,508 | 6.75 |
| 2025 | settlements | 10,954 | 153,508 | 7.14 |
| 2024 | additions | 10,229 | 156,878 | 6.52 |
| 2024 | settlements | 10,110 | 156,878 | 6.44 |

| figure | value |
|---|---|
| incentive claims, share of net revenues, central (2025 additions) | 6.75 |
| the same, lowest of the four ratios | 6.44 |
| the same, highest of the four ratios | 7.14 |
| our former assumption, incentive_pct_revenue (%) | 8.0 |

The group's claims-based incentive programmes cost about 6.8% of net revenues, below our former
assumption of 8% and inside its range. Leak 1's claims line now uses the central figure,
with the lowest and highest of the four ratios as its range (`x14_incentive_claims_*`).

## The leak rate beside it

What share of claims is paid wrongly stays an assumption (`process_leak_pct`), because no carmaker publishes one. The
closest audited analogue is the European Court of Auditors' error rate on EU spending paid out on claims. It was
5.2% in 2024 where the rules are complex and beneficiaries claim reimbursement of
costs, below 2% for simple entitlement payments, and 3.6% overall (`eca_error_*`). Dealer
incentive programmes have complex rules (stacking, eligibility dates, fleet or retail), so our
2% sits at the simple-rules end: conservative. No published rate was found for how much a
claim audit recovers; `recoverable_share` stays an assumption.

## Checks

| check | got | passes |
|---|---|---|
| 2025: opening + additions - settlements + other movements = closing (Note 21) | 5,321 vs 5,321 | True |
| 2024: opening + additions - settlements + other movements = closing (Note 21) | 6,343 vs 6,343 | True |
| the register's closing balance for 2025 equals Note 21's | 5,321 | True |
| every ratio sits inside the former assumption's range | 6.44 to 7.14 within 5 to 12 | True |

## Limits

- **Worldwide, applied to Europe.** The 20-F gives no regional split, and North America carries heavy incentives in
  some years. Europe's ratio could be higher or lower; the ledger measures it from the group's own claims.
- **Claims-based spend only.** Price discounts at invoice need not pass through the provision, so total incentive
  spend is higher. Leak 1's claims line is about claims, so this is its base. The per-car P&L's
  `pl_incentive_pct_list` (a share of list price, a different base) is unchanged.
- **Two years.** The range is the variation across 2024 and 2025 and across additions and settlements, not a
  confidence interval.
- **An analogue for the leak rate.** The Court of Auditors audits public grants, not dealer claims; it shows the
  order of magnitude of error in claim-based payments under complex rules, after controls.
