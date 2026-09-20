# A learned readiness model, and whether it earns its place

759,541 UK cars tested in March 2024, followed to July 2025; **8.7% never came back.** A gradient-boosted model over ten fields against the two-layer engine we already have.

AUC is the chance the model scores a car that left above one that stayed - 0.5 is a coin toss. Lift is how many more leavers the top slice holds than the population average, which is what a contact list actually cares about.

## What each layer of data is worth

The engine is built in tiers, and `TIERS` in the script is the whole extension point. Each tier is what a company knows at a stage of joining its data up, and the model is refitted after each one. **When the group's own contract, equity and service records arrive they become a tier here, and nothing else changes.**

Two columns, because they answer different questions. **AUC** is ranking across all cars, and age dominates it. **Within-age AUC** ranks only cars of the same age, which is what a call list actually is - and it is where knowing *which* car pays.

| Tier | Fields | AUC | Within-age AUC | Lift, top 10% |
|---|---|---|---|---|
| Age alone | 1 | 0.664 | 0.500 | 2.49x |
| + how far it has gone | 3 | 0.698 | 0.618 | 2.92x |
| + what the car is | 7 | 0.709 | 0.643 | 3.20x |
| + where it is, and how it just did | 10 | 0.712 | 0.648 | 3.20x |
| + last year's test (a service history, arriving late) | 15 | 0.723 | 0.667 | 3.34x |

**Knowing what the car is takes within-age ranking from 0.618 to 0.643.** That is the answer to "surely two cars of the same age are not the same car": they are not. At 12 years old the share leaving the fleet runs from **5.3% for a Golf to 12.9% for an Astra** - a **2.4x spread at one age**, across the eight commonest models. A global AUC hides that, because age already separates most pairs; the within-age column does not.

**And the last tier is the point of the whole design.** A year of prior test history - the public stand-in for a service record - arrived after the model was built, and cost one line in `TIERS`. It took within-age ranking from 0.648 to 0.667 and the top-tenth list from 3.20x to 3.34x. **The group's contract dates, equity and service visits go in the same way.**

## Against what it has to beat

| Model | AUC | Within-age AUC | Lift, top 10% | Lift, top 20% |
|---|---|---|---|---|
| Age curve alone | 0.664 | 0.500 | 2.49x | 2.10x |
| The two-layer engine (age x mileage) | 0.694 | 0.618 | 2.86x | 2.27x |
| Neural net, every field | 0.703 | 0.635 | 3.10x | 2.35x |
| Learned, every field | 0.723 | 0.667 | 3.34x | 2.50x |

**Learning beats the lookup, and the size of the win matters more than the fact of it.** Most of the gain is already in the two-layer engine: age alone gives **0.664**, adding mileage takes it to **0.694**. Everything else the register knows - what the car is, where it is, whether it just failed - is worth a further **+0.030**, to **0.723**. In the terms a call list cares about that is **2.86x** to **3.34x** in the top tenth, or about 17% more leavers for the same number of calls.

So: worth building, and not a revolution. The two-layer engine was not leaving much on the table, which is a useful thing to know before anyone budgets for a modelling programme - and it is the opposite of what the uplift engine found, which is why both were tested instead of either being taken on faith.

**A neural network on the same fields reaches AUC 0.703.** Boosted trees are the right tool for a table of ten columns, and this is the measurement rather than an opinion; the net is included because it is the first thing anyone asks about.

## Where the gain comes from

Each field shuffled in turn, and the AUC it costs:

| Field | AUC lost when shuffled |
|---|---|
| age | +0.040 |
| prev_km | +0.020 |
| model | +0.016 |
| km | +0.009 |
| years_since_test | +0.009 |
| region | +0.008 |
| km_rate_ratio | +0.008 |
| result | +0.004 |
| make | +0.002 |
| km_ratio | +0.001 |
| prev_fail | +0.001 |
| km_per_year | +0.000 |
| colour | +0.000 |
| cc | +0.000 |
| fuel | +0.000 |

## Does it get the level right, not just the order?

AUC says the model ranks. It does not say a car it calls 12% leaves 12% of the time, and a level is what a euro figure needs.

| Decile of predicted risk | Predicted | Actually left | Cars |
|---|---|---|---|
| 1 | 2.6% | 2.9% | 22,797 |
| 2 | 3.4% | 3.7% | 22,797 |
| 3 | 4.0% | 3.9% | 22,797 |
| 4 | 4.6% | 4.6% | 22,797 |
| 5 | 5.4% | 5.4% | 22,796 |
| 6 | 6.4% | 6.1% | 22,796 |
| 7 | 7.7% | 7.3% | 22,796 |
| 8 | 9.8% | 9.6% | 22,796 |
| 9 | 14.2% | 14.5% | 22,796 |
| 10 | 28.3% | 29.1% | 22,796 |

Predicted against actual across the ten deciles: the largest gap is **0.8%**, from 2.6% at the safest tenth to 28.3% at the riskiest against 2.9% and 29.1% actual.

## Where it works and where it does not

One AUC over a million cars hides the slices it fails on. `engine_check.py` does this for the value engine; this is the same test for readiness.

| Slice | Cars | Left the fleet | AUC |
|---|---|---|---|
| aged 3-6 | 69,334 | 5.8% | 0.615 |
| aged 7-10 | 73,983 | 5.5% | 0.639 |
| aged 11-15 | 55,547 | 10.3% | 0.717 |
| aged 16-20 | 29,100 | 20.9% | 0.705 |
| Ford | 31,154 | 8.9% | 0.725 |
| Vauxhall | 20,924 | 11.1% | 0.749 |
| Volkswagen | 20,659 | 7.8% | 0.712 |
| Bmw | 12,257 | 9.2% | 0.712 |
| Audi | 11,905 | 8.4% | 0.708 |
| Mercedes-Benz | 11,775 | 8.7% | 0.686 |

AUC runs **0.615 to 0.749** across slices against 0.723 overall, and the weakest slice is **aged 3-6**.

**That weakness is the one that matters, and it is not an accident.** The model is far better at spotting an old car about to be scrapped than a young one about to change hands - and young cars are exactly the ones a lease book holds. What separates a sixteen-year-old that dies from one that survives is visible in a register: mileage, a failed test, what the car is. What separates a four-year-old that gets replaced from one that does not is a contract date, an equity position and a conversation with a dealer - **none of which is in any public file.** The engine is weakest exactly where the group's own data would be strongest, and that is the ledger's argument in one number.

## A reason a dealer can read

The five highest-scoring cars in the held-out set, with why:

| Score | Car | Why the model says so |
|---|---|---|
| 69% | Ford, 281,667 km | 18 years old; driven 67% above cars its age; and 7.0x their yearly rate in the last year; failed this test |
| 67% | Peugeot, 173,241 km | 20 years old; about average mileage for its age; and 6.0x their yearly rate in the last year; failed this test; Peugeots leave the fleet more often than average |
| 67% | Peugeot, 204,983 km | 20 years old; driven 22% above cars its age; failed this test; Peugeots leave the fleet more often than average |
| 67% | Renault, 229,226 km | 19 years old; driven 36% above cars its age; and 6.1x their yearly rate in the last year; failed this test; Renaults leave the fleet more often than average |
| 66% | Audi, 286,897 km | 20 years old; driven 71% above cars its age |

Those are all old cars, because that is what the model is best at. **The same five, restricted to the ages a lease book actually holds:**

| Score | Car | Why the model says so |
|---|---|---|
| 38% | Vauxhall, 319,750 km | 6 years old; 4.7x the mileage of cars its age; and 5.9x their yearly rate in the last year; Vauxhalls leave the fleet more often than average |
| 33% | Jaguar, 184,001 km | 6 years old; 2.7x the mileage of cars its age; and 78% harder in the last year |
| 31% | Vauxhall, 317,394 km | 6 years old; 4.6x the mileage of cars its age; and 6.4x their yearly rate in the last year; failed this test; Vauxhalls leave the fleet more often than average |
| 29% | Nissan, 160,367 km | 5 years old; 2.9x the mileage of cars its age; and 3.7x their yearly rate in the last year; failed this test |
| 28% | Jaguar, 188,974 km | 6 years old; 2.8x the mileage of cars its age; and 91% harder in the last year |

The scores are far lower and the reasons thinner, which is the honest picture: on a four-year-old, public data has little to say beyond mileage. That is the gap the group's contract dates close.

## What it is not

- **It predicts a car leaving the fleet, not a customer replacing it.** The MOT register carries no keeper, no contract and no price. Those live in the group's own book, and that gap is the ledger's argument, not a limitation this model can design away.
- **It is a black box, and for this use that is acceptable.** Choosing whom to call is marketing, not credit. The project's standing position - **no AI in a credit decision**, for the reasons in the solution document - is untouched by this.
- **British, and three years old at the youngest.** An MOT starts at three, so the first contract cycle is invisible.
- **The label is a proxy.** 'Not tested again' mixes scrappage, export and a car laid up.
- **Rare makes and models are pooled.** The commonest 200 levels of each are kept and everything else becomes one 'other' bucket, because a boosted tree takes at most 255 levels and a model with a handful of cars teaches nothing.
- **One car in four** is kept, by a mixing hash of the id, to hold the panel to a workable size. Sampling the raw id instead would have been a disaster: even ids are 31.8% of the file and average 16.3 years against 6.9 for odd ones. The train/test split is a fixed seed, so the held-out set is the same on every run.
