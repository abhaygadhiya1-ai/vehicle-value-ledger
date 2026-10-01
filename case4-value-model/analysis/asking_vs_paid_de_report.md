# X10 part 2: German asking prices against what German buyers paid

**The free German figures show no measurable gap, because the mix decides the answer.** DAT's survey puts the
average used car bought by a German private buyer in 2023 at EUR 18,620. Depending on the mix they are
weighted to, the June 2023 AutoScout24 adverts ask 0.96 to 1.49 times that.
- **At the official mix** of every car that changed owner in 2023 (KBA: mean age and the ten largest brands),
  asking and paid nearly coincide: 1.05. Without near-new cars it is 1.02, and with the top 1% of
  asking prices dropped, 0.96.
- **At younger mixes,** asking runs well above paid.

DAT publishes the mix of cars bought only in its paid report. The ratio moves by far more across mixes than a
negotiated discount plausibly could, so comparing an average advert with an average purchase says nothing about
the discount on one car.

| mix the adverts are weighted to | adverts | effective adverts | mean age | mean asking (EUR) | DAT paid (EUR) | asking / paid |
|---|---|---|---|---|---|---|
| as listed (the adverts' own mix) | 242,546 | 242,546 | 6.9 | 25,946 | 18,620 | 1.39 |
| mean age 6 | 242,546 | 235,810 | 6.0 | 27,799 | 18,620 | 1.49 |
| mean age 7 | 242,546 | 242,484 | 7.0 | 25,778 | 18,620 | 1.38 |
| mean age 8 | 242,546 | 233,100 | 8.0 | 23,931 | 18,620 | 1.29 |
| mean age 9 | 242,546 | 210,080 | 9.0 | 22,233 | 18,620 | 1.19 |
| mean age 10.2 (KBA: all 2023 ownership changes) | 242,546 | 172,353 | 10.2 | 20,366 | 18,620 | 1.09 |
| KBA: mean age and the ten largest brands | 242,546 | 165,149 | 10.2 | 19,604 | 18,620 | 1.05 |
| KBA age and brands, cars 1 year and older | 214,870 | 166,436 | 10.2 | 18,997 | 18,620 | 1.02 |
| KBA age and brands, top 1% of asking prices dropped | 240,120 | 164,642 | 10.2 | 17,940 | 18,620 | 0.96 |

- **Weights.** Effective adverts count how many equally weighted adverts the weights are worth. The official mix is
  older than the adverts' own, so reaching it leans on older cars. The lowest count is 164,642, so no row rests
  on a few cars.
- **Brands.** The adverts against the official mix of ownership changes (KBA's ten largest brands, the rest as
  other):

| brand | KBA share of 2023 ownership changes | share of adverts |
|---|---|---|
| audi | 7.7% | 8.5% |
| bmw | 8.4% | 8.1% |
| mercedes | 10.5% | 11.1% |
| opel | 9.1% | 8.1% |
| vw | 20.9% | 13.5% |
| fiat | 2.6% | 1.8% |
| hyundai | 2.5% | 2.8% |
| renault | 3.4% | 3.4% |
| seat | 3.1% | 4.7% |
| skoda | 4.1% | 5.5% |
| other | 27.6% | 32.4% |

## What the ratio contains

The advert mean and the paid mean differ for three reasons, and this comparison can't pull them apart.

- **Negotiation:** a buyer pays less than the asking price for the same car. This is the discount X10 is after.
- **Composition the weights can't reach:** mileage, trim and segment within a brand and age, and the mix DAT's
  buyers actually had.
- **Stock against flow:** adverts are a snapshot of stock, which overweights cars that sell slowly. It also
  overweights dealers: DAT's buyers bought 29% of their used cars privately,
  while `de_2023` does not record the seller.

Composition alone moves the ratio from 0.96 to 1.49. A discount of a few per cent would be lost inside that
spread.

## What it means for the solution

- **No figure for "adverts overstate paid prices by X%" in Germany, from us or from any team using averages.** Such
  a figure reads composition, not a discount.
- **Every headline stays labelled as an advert price,** as before. A per-car value quoted in euros (the value engine,
  the sample car in 6.6) is an asking price.
- **The question that matters moves to time and to single cars.** Leak 3 and X6 use percentage moves of indices, and
  a steady gap cancels in a percentage move. What would matter is a gap that widens when the market falls. The
  next section tests that. The discount on one car needs per-car data; the Danish route is closed to us (X10 part 1).

## Limits

- **One snapshot of adverts.** `de_2023` is dated by its upload to Kaggle (24 June 2023), not by a scrape date,
  and has no listing dates. DAT's figure covers purchases across 2023.
- **DAT's figure is a survey.** Buyers report what they paid, possibly with extras or a trade-in folded in. DAT
  doesn't publish its sample size or questions in the free short report.
- **The official mix covers every ownership change,** commercial keepers included, not only DAT's private buyers.
- **Germany only, one year.**

## Does the gap move with the market? (X10 part 3b)

Three German measures, year on year. Asking and paid are both plain averages over what was listed or bought. The
official index holds the kind of car fixed.

| year | asking, average (AutoScout24) | paid, average (DAT) | asking less paid (points) | official index, like for like |
|---|---|---|---|---|
| 2022 | +19.0% | +19.4% | -0.4 | +21.2% |
| 2023 | +4.0% | -1.0% | +5.0 | +9.4% |
| 2024 | -6.1% | -0.1% | -6.0 | +1.3% |
| 2025 (November on November) | +3.1% | -1.6% | +4.6 | +4.8% |

- **Asking turned a year after paid.** In 2023 the average asking price still rose 4.0%, while the average
  paid fell 1.0%; AutoScout24's record month was March 2023 (EUR 29,333). In 2024
  asking fell 6.1% and paid fell 0.1%. Over the two years together asking fell 2.3% and paid
  fell 1.1%. So the gap opened at the turn and closed within two years, with asking no higher against paid
  than before. In 2025 the two parted again: asking rose 3.1%, paid fell 1.6%.
- **Like for like, prices kept rising.** The official index rose 9.4% in 2023 (+10.8% over
  2023-24). It fell 5.0% from its 2023 high (December 2023) into 2024, and reached its highest
  level in December 2025. Both averages can fall while like-for-like prices rise when the mix bought and
  listed shifts to cheaper cars. These figures can't say which cars shifted.
- **Asking lags realised prices, as in part 3a.** Aramis's realised price per car (about half of it France) stopped rising in
  early 2023. Germany's average paid turned in 2023 and its average asking price in 2024. The like-for-like indices
  (Germany's, and France's smoothed one) had not turned by then. They measure something else, and part 3a shows
  France's lagging.

**What it means for the solution.**
- **An advert-based mark is late at a turn.** A ledger marked only on asking prices would carry the book above what
  buyers pay for about a year after the market turns. The re-mark needs a realised signal beside the adverts: the
  group's own sales (Aramis, and the resale book itself once the ledger holds it).
- **No sign that asking-based falls understate paid falls over two years in Germany.** Over 2023-24 the asking
  average fell at least as far as the paid one. The risk shown is timing, not a lasting gap. 2025's renewed parting
  is one year and can't be read yet. X6's charge on percentage moves stands.
- **The engine is like for like, as the official index is.** It holds model, age and mileage fixed, so a mix shift
  doesn't move its values. An average-price series, asking or paid, would mislead the ledger.

**Limits.**
- **Annual averages, four years, one country.**
- **The two averages cover different populations:** AutoScout24's listings, largely dealers, against DAT's
  surveyed purchases, which include private sales.
- **AutoScout24's year figures come from its December reviews,** whose basis for the year isn't stated. The 2024
  stated change differs from the two year figures' ratio (`agpi_change_2024`'s caveat). The 2022 and 2023 figures
  are trade-press reprints of AutoScout24's reviews.
- **The official index's source today is unconfirmed,** and in 2003 it covered cars up to ten years old.
