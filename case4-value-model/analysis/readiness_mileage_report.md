# Layer 2: mileage against the cohort

Layer 1 says how likely a car of a given age is to come to market. This says which car. Mileage is always measured against the car's own age cohort, so decile 1 is the least-driven tenth of five-year-olds and decile 10 the most-driven tenth - otherwise the result would only be saying that older cars have driven further.

**The two events disagree, and the disagreement is the finding.**

- **Leaving the fleet rises steadily with mileage.** The most-driven tenth is 2.9 times as likely to go as the least-driven; a car on twice its cohort's mileage is **1.54 times** as likely to disappear.
- **Coming to market does not.** A car on twice its cohort's mileage is **1.03 times** as likely to be advertised - which is to say, no different. The profile is not flat but arched: the middle of the mileage range is over-represented among adverts at 1.05x, and **both ends are under-represented**, the most-driven tenth at 0.84x and the least-driven at 0.85x.

Read together they say something an engine has to respect: **mileage predicts disposal, not sale.** The hardest-driven cars do not reach a forecourt - they leave the fleet. A readiness model that ranks customers by mileage would surface cars about to be scrapped or exported, which is not the same list as customers about to buy.

## Part 1: leaving the fleet, measured per car

3,039,129 cars tested in March 2024, looked for again from December 2024 to July 2025. **8.7% never came back.** A car that is not tested again has been scrapped, exported or laid up; DVSA publishes no disposal flag, so this is the public proxy and it is a proxy.

| Mileage decile | Mileage vs cohort median | Hazard vs cohort average |
|---|---|---|
| 1 | 0.36x | 0.61x |
| 2 | 0.57x | 0.65x |
| 3 | 0.71x | 0.72x |
| 4 | 0.83x | 0.80x |
| 5 | 0.94x | 0.88x |
| 6 | 1.06x | 0.97x |
| 7 | 1.19x | 1.07x |
| 8 | 1.35x | 1.17x |
| 9 | 1.57x | 1.33x |
| 10 | 2.08x | 1.78x |

Holding age fixed, **a car on twice its cohort's mileage is 1.54 times as likely to leave the fleet** (elasticity 0.626, standard error 0.026).

**Is the follow-up window wide enough?** A car that returned three months after the window closed would be counted as gone. This is where the returns actually landed:

| Follow-up month | Returns | Share |
|---|---|---|
| 2024-12 | 20,144 | 0.7% |
| 2025-01 | 39,363 | 1.4% |
| 2025-02 | 338,434 | 12.2% |
| 2025-03 | 1,965,028 | 70.8% |
| 2025-04 | 282,869 | 10.2% |
| 2025-05 | 63,858 | 2.3% |
| 2025-06 | 36,642 | 1.3% |
| 2025-07 | 29,563 | 1.1% |

Returns peak in **2025-03**, the anniversary month. The two edge months hold 0.7% and 1.1% of them, so the window is not clipping the tail.

## Part 2: coming to market, the density-ratio estimator

354,112 UK adverts of October 2022 against 9,287,573 MOT tests of the same September to November. No car is matched to itself: the estimator compares the mileage distribution of the cars that came to market with that of the fleet at the same age. A value of 1.00 means that tenth of the fleet is represented among the adverts exactly in proportion to its size.

| Mileage decile | Mileage vs cohort median | Hazard vs cohort average |
|---|---|---|
| 1 | 0.35x | 0.85x |
| 2 | 0.56x | 0.96x |
| 3 | 0.70x | 1.01x |
| 4 | 0.82x | 1.02x |
| 5 | 0.94x | 1.05x |
| 6 | 1.06x | 1.05x |
| 7 | 1.20x | 1.04x |
| 8 | 1.38x | 1.06x |
| 9 | 1.65x | 1.05x |
| 10 | 2.34x | 0.84x |

Holding age fixed, **a car on twice its cohort's mileage is 1.03 times as likely to be on the market** (elasticity 0.041, standard error 0.024) - and a single slope is the wrong summary of an arched profile. The deciles are the result; the elasticity is only there to be composed with layer 1.

> **TRAP, and it cost a wrong answer once already.** The 2022 MOT file is one member > sorted by test date, so reading a prefix of it gives a **January** parc - and a January > odometer is three quarters of a year short of an October one. Priced that way the > estimator returned an elasticity of 0.194 and a confident story about high-mileage > cars flooding the market. Matching the parc to the advert month killed it. **Always > match the odometer month.**

## The two events against each other

| Event | Where | Per car? | Elasticity | Twice the mileage |
|---|---|---|---|---|
| Leaves the tested fleet | MOT panel, 2024 to 2025 | yes | 0.626 | 1.54x |
| Comes to market | UK adverts vs MOT parc, 2022 | no | 0.041 | 1.03x |

## What this is not

- **Two different events, and they answer differently.** Leaving the fleet is the end of a car's life; coming to market is a car changing hands. Neither is 'the customer is ready to replace'.
- **Part 2 carries an assumption part 1 does not.** The adverts are a sample of the cars that came to market, and the estimator treats that sample as representative at each age. A site that carries more mid-mileage stock would produce exactly this arch.
- **Advert mileage is what the seller typed; MOT mileage is what a tester read.** Different instruments, and part 2 compares one with the other.
- **It is British.** The UK parc is the only European fleet with a public odometer. Layer 1 is Dutch. This layer is a shape, which the project has measured three times is the half that travels.
- **Nothing here sees a car younger than three.** An MOT starts at three, so the first lease cycle is invisible in the parc.
