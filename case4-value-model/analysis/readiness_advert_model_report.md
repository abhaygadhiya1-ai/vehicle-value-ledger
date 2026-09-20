# Can a model tell which cars come to market?

354,112 UK adverts of October 2022 against 3,095,658 cars tested in the September-to-November parc. A classifier is trained to tell one from the other; that is the density-ratio estimator in `readiness_mileage.py`, done with a model instead of a slope, so it can use what the car *is* and not only how far it has gone.

AUC 0.5 means the model cannot tell an advertised car from one on the road - which would mean nothing public predicts coming to market.

| What the model may use | AUC |
|---|---|
| Age only | 0.662 |
| Age, odometer, odometer against the cohort | 0.671 |
| ...and make and fuel | 0.722 |

**Mileage adds +0.009 over age alone** - which matches the elasticity of 0.041 in `readiness_mileage_report.md`, reached a second way and by a method free to find any shape it likes. **Mileage does not predict coming to market.**

**Make and fuel add a further +0.051, and that number cannot be believed.** A density ratio over makes is only a replacement signal if the adverts are a fair sample of the cars coming to market. They are one site's stock, and a site's brand mix is not the fleet's. Nothing in this data separates *Brand X changes hands more often* from *Brand X is over-represented on this website*, and the second needs no explaining.

**The comparison that makes the point:** in `readiness_model_report.md`, where the outcome is observed per car and no sampling stands between the model and the truth, **make is worth +0.002 of AUC** - almost nothing. Here it is worth +0.082. A field that barely matters when you can watch the cars, and matters greatly when you are comparing two files, is telling you about the files.

**So the answer to the question in the title is: age, and then not much that can be trusted.** Which is the ledger's argument reached with a model - if public data cannot say which car comes to market beyond its age, the contract date, the equity and the service history the group holds are not a refinement. They are the signal.

## What each field is worth

| Field | AUC lost when shuffled |
|---|---|
| age | +0.107 |
| make | +0.082 |
| km | +0.021 |
| fuel | +0.020 |
| km_ratio | +0.006 |

## What this settles

- **It is the same conclusion the slope gave, reached a second way.** `readiness_mileage_report.md` found a mileage elasticity of 0.041 on this event - nothing - and a model free to use make and fuel does not rescue it.
- **It is the argument for the ledger, made with a model.** If public data cannot say which car comes to market beyond its age, then the contract date, the equity and the service history that only the group holds are not a nice-to-have. They are the signal.
- **The obvious cheat is closed, and it was large.** A seller types 100,000 and a tester reads 98,432: **30.9% of advert mileages are exact multiples of a thousand miles against 0.11% of MOT readings, a 280x difference.** Left alone a classifier identifies the file from the digits and scores AUC 0.737 that has nothing to do with replacement. Both sides are rounded to the nearest thousand miles before anything is fitted.
- **Other file differences may remain.** One October scrape against a three-month parc, and a site's brand mix is not the fleet's. Whatever is left of that inflates this AUC rather than deflating it, which makes a low number the safer error.
- **The commonest 200 makes are kept** and the rest pooled into one bucket, because a boosted tree takes at most 255 levels.
- **Make is normalised on both sides** with `build_unified.norm_name` and `MAKE_ALIASES`, or the register's Ford would not be the adverts' Ford.
