# Readiness times value: where the money moves

The ledger's claim is that how likely a car is to move and what it is worth belong on the same record. This is the smallest demonstration of it: for the Dutch fleet, the value of the cars that will change hands in the next twelve months, by age.

    cars of that age  x  share that change keeper in a year  x  what one is worth

The first two come from RDW's register (`readiness_base_report.md`). The third is RDW's **official catalogue price** for the cars of that vintage still on the road, multiplied by how much of it a Dutch car of that age still holds - measured in `value_retained_report.md` against that same official price.

**EUR 12.9 billion a year of metal crosses the Dutch market, EUR 2.3 billion of it the group's own brands.** 881,723 cars change keeper, 185,038 of them the group's.

The biggest single age is **1**, at EUR 2.57bn, and it gets there on price rather than on hazard - only 18.1% of those cars move. **The replacement wave is ages four to six, which carry EUR 3.89bn between them (30% of the total) on 226,347 cars.** That is where a high hazard meets a car still worth something, and it is the part of the age range a contact list has to be pointed at.

| What | Figure |
|---|---|
| Value crossing the Dutch market in a year | 12.9 |
| ...of which the group's own brands | 2.3 |
| Cars changing keeper | 881,723 |
| Value in the wave, ages four to six | 3.89 |
| What pricing it from our own adverts would have said | 30.9 |

*(EUR billions except the car count. In a table so each figure has its own cell for `check_assumptions.py`.)*

| Age | Cars on the road | Change keeper in a year | Official new price | Still worth | Used value | Value crossing the market |
|---|---|---|---|---|---|---|
| 1 | 397,744 | 18.1% | EUR 43,418 | 82% | EUR 35,786 | EUR 2.57bn |
| 2 | 384,712 | 14.1% | EUR 43,640 | 68% | EUR 29,575 | EUR 1.60bn |
| 3 | 366,257 | 15.5% | EUR 42,200 | 60% | EUR 25,327 | EUR 1.43bn |
| 4 | 304,160 | 20.5% | EUR 37,601 | 55% | EUR 20,707 | EUR 1.29bn |
| 5 | 300,112 | 27.8% | EUR 35,349 | 48% | EUR 16,803 | EUR 1.40bn |
| 6 | 305,234 | 26.4% | EUR 32,853 | 45% | EUR 14,792 | EUR 1.19bn |
| 7 | 375,015 | 16.5% | EUR 30,899 | 39% | EUR 12,172 | EUR 0.75bn |
| 8 | 372,869 | 15.6% | EUR 26,155 | 39% | EUR 10,302 | EUR 0.60bn |
| 9 | 340,434 | 15.1% | EUR 24,779 | 36% | EUR 8,867 | EUR 0.46bn |
| 10 | 306,233 | 15.3% | EUR 23,090 | 27% | EUR 6,122 | EUR 0.29bn |
| 11 | 314,340 | 15.4% | EUR 22,791 | 31% | EUR 7,037 | EUR 0.34bn |
| 12 | 277,454 | 15.7% | EUR 20,885 | 31% | EUR 6,470 | EUR 0.28bn |
| 13 | 287,423 | 16.0% | EUR 19,935 | 27% | EUR 5,419 | EUR 0.25bn |
| 14 | 326,617 | 16.6% | EUR 17,676 | 22% | EUR 3,868 | EUR 0.21bn |
| 15 | 357,649 | 17.4% | EUR 17,299 | 24% | EUR 4,072 | EUR 0.25bn |

**The five biggest ages carry 64% of it** (1, 2, 3, 4, 5 years).

## Why the price is not taken from our own adverts

It was, first, and the answer was wrong. Our Dutch adverts give a median asking price of **EUR 99,950 for a 2-year-old car** on 483 adverts, and the curve is not even monotone in age: that is one premium dealer scrape, not a market. Priced that way the total comes out at **EUR 30.9bn against EUR 12.9bn** here. **Do not price this from the listings.**

It is the same failure `readiness_base_report.md` found in its third check, from the other side: our listings are good for shapes pooled across many sources and bad for a level in one country. **What survives from them is the retention ratio**, because a scrape that over-represents expensive cars biases the advert price and the catalogue price together, and the bias divides out. The level comes from the register instead.

## What this is and is not

- **It is not the value-at-risk model.** `../Case4_Value_at_Risk.xlsx` prices what the group loses when a residual is wrong. This prices the flow of metal across a market. They are different quantities: do not add them, and do not present one as the other.
- **The retention curve is measured on advert prices**, so it inherits the project's standing caveat that an advert is not a sale (`price_types_report.md`). It reproduces the project's independently measured 62% at three years for the Netherlands.
- **The group-brand figure carries no price assumption of its own beyond the market curve**: its cars and its rate are both measured for the group's brands specifically.
- **Dutch.** The level is local; the project has measured three times that a shape travels between markets and a level does not.
