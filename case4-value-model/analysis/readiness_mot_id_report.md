# Does the MOT vehicle id follow a car across releases?

Layer 2 of the readiness engine needs to follow one car from one year's MOT test to the next. That is only possible if the anonymised `vehicle_id` means the same car in every release. DVSA's user guide says it is derived from the registration and the VIN. This checks it.

## The answer

| Test | Figure |
|---|---|
| Tests published in both the May 2025 and the June 2026 release of 2024 | 202,060 |
| ...with an identical vehicle id | 0.9999 |
| January 2024 cars carrying an odometer | 681,853 |
| ...found again in January or February 2025 | 249,716 |
| ...whose make and model agree | 1.0000 |
| ...whose first-use date agrees | 1.0000 |
| ...whose odometer has not gone backwards | 0.9929 |
| Make and model agreeing by chance | 0.0088 |
| First-use date agreeing by chance | 0.0007 |

**The id follows the car.** Two releases built thirteen months apart, by pipelines that do not even format the odometer the same way, agree on the vehicle id for 99.99% of the tests they share. Following a car into the next year, make, model and first-use date agree on every pair, against chance rates of 0.88% and 0.07%.

## What the remainder is

- **0.71% of followed cars show a lower odometer a year later.** That is the rate of mis-keyed and rolled-back readings, and it is the reason DfT's own note on MOT odometers cleans the pairs before annualising them. It is not evidence against the id.
- **0.01% of shared tests disagree on the id.** A handful of vehicles are re-keyed between releases; at this rate it changes nothing.

## What this does not settle

- **An MOT starts at three years.** The id is stable, but there is no record at all of a car's first three years, so a 24- or 36-month contract cycle is invisible in this data.
- **A test is not a transaction.** The id lets a car be followed; it does not say who owns it, or that it changed hands. MOT records carry no keeper.
- **It is anonymised on purpose.** The id is derived from the registration and the VIN, and cannot be turned back into either.
