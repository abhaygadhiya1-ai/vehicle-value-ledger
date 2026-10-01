# Does the Phase 2 pilot fit inside one market? (X14 part 3)

The pilot randomises the group's own upgrade flag customer by customer within each dealer (X15, decision of 26
September). It needs 17,644 customers in its two arms, or 31,366 if a quarter of the uplift spills
over to unflagged customers (`pilot_size_report.md`). This report puts that beside a year of each market's financed
contracts, which stand in for a year of its contract ends. Sources and method are in the script's docstring.

| market | finance partner | group car registrations 2025 | SFSE penetration (%) | contracts a year | basis | both arms, share of a year (%) | with spillover, share of a year (%) | months of contract ends, with spillover |
|---|---|---|---|---|---|---|---|---|
| France | Santander CF joint venture | 452,150 | 27.5 | 154,496 | disclosed | 11 | 20 | 2.4 |
| Italy | Santander CF joint venture | 409,685 | 28.6 | 117,170 | rate x car registrations (vans left out) | 15 | 27 | 3.2 |
| Germany | BNP Paribas PF joint venture | 276,855 | 33.8 | 93,577 | rate x car registrations (vans left out) | 19 | 34 | 4.0 |
| Spain | Santander CF joint venture | 160,842 | 21.9 | 35,224 | rate x car registrations (vans left out) | 50 | 89 | 10.7 |
| Poland | Santander CF joint venture | 30,128 | 48.8 | 14,702 | rate x car registrations (vans left out) | 120 | 213 | 25.6 |
| Belgium-Luxembourg | Santander CF joint venture | 59,248 | 26.6 | 22,128 | disclosed | 80 | 142 | 17.0 |
| Austria | BNP Paribas PF joint venture | 29,687 | 56.7 | 22,411 | disclosed | 79 | 140 | 16.8 |

Markets where both arms, with spillover, take half a year's contracts or less: France, Italy, Germany.

| figure | value |
|---|---|
| customers needed, both arms (the gate, power 80%, base 50%, ICC 0.1) | 17,644 |
| the same, with a quarter of the uplift spilling over | 31,366 |
| France: both arms, share of a year's contracts (%) | 11 |
| France: both arms with spillover, share of a year's contracts (%) | 20 |
| Austria: both arms with spillover, share of a year's contracts (%) | 140 |
| Belgium-Luxembourg: both arms with spillover, share of a year's contracts (%) | 142 |
| markets where both arms with spillover take half a year's contracts or less | 3 |

## What it means

- **The pilot fits in one large market.** France, the one large market with a disclosed count, holds the two arms,
  spillover included, in a small share of one year's contract ends. The others that fit (Italy, Germany)
  do so on estimated counts, which leave vans out and so understate them.
- **The smaller markets don't fit in a year.** With spillover, Spain would need most of a year's
  contract ends and Poland, Belgium-Luxembourg, Austria more than a year's. Not every customer reaching a contract end is
  reachable, so they would need a window of more than a year. The gate is best tested in France, Italy, Germany; the
  smaller markets join in Phase 3.
- **Every candidate market's contracts sit in a joint venture** with a partner bank (the 20-F: Santander CF in France,
  Italy, Spain, Belgium, Poland and the Netherlands; BNP Paribas PF in Germany, Austria and the UK). The flag needs
  each contract's end date and the customer's consent to be contacted, and both sit with the joint venture. SFSE's
  2025 report credits "opérations conjointes B2C" (joint consumer campaigns with the brands, Spain) and "le poids
  important des offres fidélisantes" (the weight of loyalty offers), so brand and bank already act together on
  retention. Whether a customer-level randomised flag is allowed under each joint venture's contracts and privacy
  terms is not public. It is a Phase 1 data-access task, not a finding.

## Checks

| check | got | passes |
|---|---|---|
| France: 2025 provisional registrations within 30% of 2024's final | 0.93 times | True |
| France: rate x car registrations is below the disclosed count (vans left out) | 124,341 vs 154,496 (80%) | True |
| Italy: 2025 provisional registrations within 30% of 2024's final | 0.91 times | True |
| Germany: 2025 provisional registrations within 30% of 2024's final | 0.90 times | True |
| Spain: 2025 provisional registrations within 30% of 2024's final | 1.01 times | True |
| Poland: 2025 provisional registrations within 30% of 2024's final | 0.89 times | True |
| Belgium-Luxembourg: 2025 provisional registrations within 30% of 2024's final | 1.03 times | True |
| Belgium-Luxembourg: rate x car registrations is below the disclosed count (vans left out) | 15,760 vs 22,128 (71%) | True |
| Austria: 2025 provisional registrations within 30% of 2024's final | 1.29 times | True |
| Austria: rate x car registrations is below the disclosed count (vans left out) | 16,833 vs 22,411 (75%) | True |
| the seven markets' contracts do not exceed SFSE's European total | 459,708 of 646,138 (71%) | True |

## Limits

- A year's new contracts stand in for a year's contract ends. Contracts end three or four years after signing, and
  SFSE's European count grew from 2023 to 2025, so the stand-in is generous where a market grew. Austria's count rose
  60% in 2025, so the ends coming up are fewer than its 2025 count.
- Only markets with a 2025 SFSE rate and EU-register registrations are shown. The UK (no registrations in the EU
  register after 2020), the Netherlands and Portugal (no 2025 rate) are missing.
- Germany's rate is a floor ("à plus de 33,8%").
- The customers per arm are X15's at base retention 50%, the largest size; any other base rate needs fewer. They
  exclude the wholly unflagged dealers that measure spillover.
- Registrations for 2025 are provisional in the EU register.
