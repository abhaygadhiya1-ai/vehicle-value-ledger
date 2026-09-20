# Layer 1: the base hazard by age

How often a Dutch car changes hands, by age, over the twelve months September 2025 to September 2026. Source: RDW's open vehicle register (https://opendata.rdw.nl/resource/m9d7-ebf2, CC0), aggregated on RDW's own server.

Numerator and denominator come out of the same file. The numerator is a car whose current keeper took it on inside the window; the denominator is every car of that age on the road. A first registration is not a keeper change and is excluded, or age 0 would read 100% by construction.

**The population is cars first put on Dutch plates when new.** An imported used car registers a keeper change the day it arrives, and imports are a large share of the parc at exactly the ages that matter, so leaving them in would invent a replacement wave.

**18.2% of the fleet changes hands in a year.** The rate is far from flat: it peaks at **27.8% at 5 years** and falls to **15.1% at 9** - **1.84 times** as many cars come to market at the peak as at the quietest age.

## Headline

*These figures sit in a table so that `check_assumptions.py` can pin each one to its own cell. A sentence holding several figures cannot tell them apart.*

| What | Figure |
|---|---|
| Changes hands in a year, whole fleet | 18.2% |
| Peak rate | 27.8% |
| Age at the peak | 5 |
| Quietest rate | 15.1% |
| Age at the quietest | 9 |
| Peak against quietest | 1.84 |
| Group brands, share of the Dutch fleet | 21.5% |
| Cars in the measurement | 6,759,930 |

## The hazard by age

| Age | Cars on the road | Changed keeper | Rate | Group brands: cars | Group brands: rate |
|---|---|---|---|---|---|
| 1 | 397,744 | 71,802 | 18.1% | 40,054 | 31.1% |
| 2 | 384,712 | 54,208 | 14.1% | 36,913 | 20.1% |
| 3 | 366,257 | 56,595 | 15.5% | 46,841 | 16.9% |
| 4 | 304,160 | 62,462 | 20.5% | 49,643 | 19.8% |
| 5 | 300,112 | 83,399 | 27.8% | 46,979 | 28.9% |
| 6 | 305,234 | 80,486 | 26.4% | 54,446 | 27.6% |
| 7 | 375,015 | 61,996 | 16.5% | 71,759 | 16.1% |
| 8 | 372,869 | 58,149 | 15.6% | 81,501 | 16.2% |
| 9 | 340,434 | 51,519 | 15.1% | 80,773 | 16.1% |
| 10 | 306,233 | 46,837 | 15.3% | 75,667 | 16.4% |
| 11 | 314,340 | 48,524 | 15.4% | 70,645 | 16.7% |
| 12 | 277,454 | 43,547 | 15.7% | 69,825 | 17.8% |
| 13 | 287,423 | 45,911 | 16.0% | 65,468 | 17.6% |
| 14 | 326,617 | 54,061 | 16.6% | 81,201 | 18.2% |
| 15 | 357,649 | 62,227 | 17.4% | 96,782 | 18.7% |
| 16 | 317,625 | 58,394 | 18.4% | 91,883 | 19.6% |
| 17 | 229,459 | 44,221 | 19.3% | 62,343 | 21.2% |
| 18 | 252,895 | 51,658 | 20.4% | 70,007 | 22.8% |
| 19 | 224,166 | 46,252 | 20.6% | 63,222 | 23.0% |
| 20 | 194,616 | 41,317 | 21.2% | 51,890 | 23.3% |
| 21 | 151,216 | 32,364 | 21.4% | 38,694 | 22.5% |
| 22 | 131,601 | 28,010 | 21.3% | 38,352 | 22.4% |
| 23 | 102,741 | 20,793 | 20.2% | 29,770 | 20.7% |
| 24 | 80,150 | 16,113 | 20.1% | 20,761 | 19.9% |
| 25 | 59,208 | 11,187 | 18.9% | 14,914 | 18.7% |

The group's own brands are 21% of the Dutch fleet and follow the same curve (rank correlation 0.79 across ages). The shape is a property of the fleet, not of a brand mix.

## Same age, different cars

The curve above is an average, and an average is not a prediction about a car. These are the 24 makes with at least 3,000 cars registered in 2021, so **every one of them is exactly 5 years old**:

| Make | Cars on the road | Changed keeper | Group brand |
|---|---|---|---|
| Skoda | 17,135 | 34.8% |  |
| Ford | 16,251 | 32.8% |  |
| Peugeot | 18,281 | 32.7% | yes |
| Audi | 11,824 | 31.8% |  |
| Seat | 7,120 | 31.5% |  |
| Tesla | 3,470 | 31.3% |  |
| Bmw | 16,238 | 30.2% |  |
| Mercedes-Benz | 10,465 | 29.6% |  |
| Mitsubishi | 3,445 | 29.1% |  |
| Volkswagen | 30,027 | 28.3% |  |
| Opel | 14,451 | 28.0% | yes |
| Volvo | 15,173 | 27.9% |  |
| Kia | 27,459 | 27.7% |  |
| Mini | 5,721 | 27.1% |  |
| Mazda | 6,280 | 26.7% |  |
| Citroen | 8,556 | 26.0% | yes |
| Nissan | 5,881 | 25.4% |  |
| Renault | 15,503 | 24.8% |  |
| Toyota | 22,611 | 23.0% |  |
| Fiat | 4,169 | 22.8% | yes |
| Hyundai | 12,517 | 21.8% |  |
| Dacia | 3,133 | 21.5% |  |
| Lynk&Co | 3,219 | 21.3% |  |
| Suzuki | 6,351 | 19.8% |  |

*In a table so each figure has its own cell for the checker.*

| What | Figure |
|---|---|
| Lowest make at the peak age | 19.8% |
| Highest make at the peak age | 34.8% |
| Spread across makes at one age | 1.75 |
| Spread across the fifteen largest makes | 1.60 |
| Lowest of the fifteen largest | 21.8% |
| Group brands, lowest | 22.8% |
| Group brands, highest | 32.7% |

**A 1.75x spread at a single age** (1.60x across the fifteen largest makes, which is what the deck figure has room to show), and the group's own four brands alone run 22.8% to 32.7%. The age curve says which year to look at and nothing about which car in it. That is the measured reason the engine needs a layer beyond age, and it is on the same register.

## Check 1: against a count made by somebody else

| What | Count |
|---|---|
| Keeper changes in the register, twelve months, every car | 1,931,085 |
| ...of which the car is still on Dutch plates today | 1,855,299 |
| Used-car sales published by BOVAG and RDC for 2025 | 2,124,429 |
| Difference against BOVAG | -9.1% |

**9.1% below** a figure collected a different way, by the motor trade's own body, and low in the direction the method predicts. A snapshot shows only the *current* keeper, so a car that changed hands twice inside the year counts once. At a rate of about 18% a year the share of movers that move again within the window is of the order of a tenth, which is the size of the gap. *That is an explanation of the direction and rough size, not a measurement of the difference.* Treat the level as good to about ten per cent, and never quote it as exact.

## Check 2: is it age, or is it the 2021 cars?

A single snapshot cannot tell a wave that follows a car's age from one that follows a registration year. The register carries the answer, because the twelve months before last are still visible through cars that have not moved since - censored, and put back by dividing by the chance of not moving since.

| Age | Previous year, as seen | Previous year, uncensored | Latest year, same age |
|---|---|---|---|
| 2 | 11.8% | 14.0% | 14.1% |
| 3 | 12.3% | 15.5% | 15.5% |
| 4 | 15.9% | 22.0% | 20.5% |
| 5 | 22.3% | 30.3% | 27.8% |
| 6 | 20.8% | 24.9% | 26.4% |
| 7 | 13.2% | 15.6% | 16.5% |
| 8 | 12.3% | 14.5% | 15.6% |
| 9 | 12.0% | 14.1% | 15.1% |
| 10 | 12.2% | 14.4% | 15.3% |
| 11 | 12.1% | 14.3% | 15.4% |
| 12 | 12.1% | 14.4% | 15.7% |
| 13 | 12.2% | 14.6% | 16.0% |
| 14 | 12.4% | 15.0% | 16.6% |
| 15 | 13.0% | 15.9% | 17.4% |
| 16 | 13.4% | 16.6% | 18.4% |
| 17 | 13.6% | 17.1% | 19.3% |
| 18 | 13.7% | 17.3% | 20.4% |
| 19 | 13.7% | 17.4% | 20.6% |
| 20 | 13.8% | 17.5% | 21.2% |

The peak sits at **5 years in the earlier window** and at **5 years in the later one**, and the two curves agree across ages at a correlation of **0.94**. The wave travels with the car's age, not with a registration year, so it is not the 2021 cohort. *The correction assumes one year is independent of the next, which is not quite true; it locates the peak, it does not measure the level a second time.*

## Check 3: against our own adverts - this one fails

If the curve is real, the Dutch adverts in the collection should thin out and thicken with it. This is adverts per thousand cars on the road, by year of registration, from `eu_2025_11` (13,430 used Dutch adverts, 8 November 2025). The population is every car on the road, imports included, because an advert does not care where the car came from.

| Registered | Adverts per 1,000 cars | Keeper-change rate |
|---|---|---|
| 2024 | 1.9 | 16.8% |
| 2023 | 0.7 | 18.4% |
| 2022 | 2.1 | 22.7% |
| 2021 | 1.6 | 25.1% |
| 2020 | 4.5 | 24.0% |
| 2019 | 1.4 | 17.0% |
| 2018 | 1.4 | 16.2% |
| 2017 | 1.1 | 15.7% |
| 2016 | 1.2 | 15.8% |
| 2015 | 1.2 | 15.9% |
| 2014 | 1.4 | 16.3% |
| 2013 | 0.3 | 16.7% |
| 2012 | 0.4 | 17.1% |
| 2011 | 0.4 | 18.0% |
| 2010 | 0.5 | 19.0% |
| 2009 | 0.5 | 20.3% |
| 2008 | 0.4 | 21.0% |
| 2007 | 0.6 | 21.1% |
| 2006 | 0.9 | 21.6% |

**Rank correlation 0.14 over registrations 2005 to 2023. The adverts do not recover the curve, and this check fails.** It fails for a readable reason rather than because the curve is wrong: one site on one day carries 2,165 adverts of 2020 cars and only 135 of 2013 cars, a swing no fleet produces. What a scrape holds is the stock that site happened to have, and the share of keeper changes that reach any one forecourt is not flat in age.

**This is the argument for taking layer 1 from the register rather than from our own listings.** The handoff's design put the shape in the listings and the level in official statistics; the register carries both, and the listings turn out not to be able to check it. Stating that is better than pooling the two and hoping.

## What this is not

- **A keeper change is not a sale to a new customer.** It counts a car going into a dealer's stock, a lease company handing a car to its buyer, and a car moving inside a family. It is the closest public event to "the car came to market", and it is not the same event as "the customer was ready to replace".
- **It is Dutch.** The project has measured three times that the shape of a used-car effect travels between markets and the level does not. The level here is Dutch, and the Netherlands taxes cars unusually (BPM) and leases them heavily.
- **Imports run the other way.** 37% of Dutch cars aged four to six were imported used, and every one of them books a keeper change on arrival. That is why the headline uses the domestic population.
- **One snapshot, one year.** The window is twelve months to September 2026; check 2 is what stands in for a second year.
