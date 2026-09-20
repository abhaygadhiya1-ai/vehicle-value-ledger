# The uplift engine, built and validated on a randomised trial

64,000 customers, randomly assigned by the publisher: a third got no e-mail, two thirds got one. 32,103 held out. The outcome is a visit. **Across everyone the campaign lifts visits by +6.1%** - that is what an untargeted send buys.

The question is not who visits. It is who visits *because they were contacted*. Those are different people, and the table says how different.

| Model | Qini | Uplift in the top 10% | 95% range | Against an untargeted send |
|---|---|---|---|---|
| Class transformation | +66.5 | +8.64% | +5.73% to +11.72% | 1.41x |
| Two-model (T-learner) | +41.2 | +9.02% | +5.72% to +11.83% | 1.48x |
| Response model (the usual way) | +60.1 | +8.85% | +5.99% to +11.96% | 1.45x |
| Random | -21.3 | +6.83% | +4.47% to +9.33% | 1.12x |

## Headline

*In a table so `check_assumptions.py` can pin each figure to its own cell.*

| What | Figure |
|---|---|
| Best uplift model against the response model, top decile | -0.14 |
| ...low end of its range | -3.36 |
| ...high end of its range | +2.88 |
| Customers in the trial | 64,000 |

## The result, which is not the one the technique is usually sold with

**Every model beats sending at random, and no uplift model beats the ordinary response model.** The best uplift approach here is two-model (t-learner); against the response model its top-decile uplift differs by **-0.14% (-3.36% to +2.88%)**, a range that comfortably contains zero.

What *is* clear is that modelling at all is worth it: the top decile chosen by a model shows +8.64% against +6.83% for a random tenth, and +6.1% for sending to everybody.

**So the honest recommendation is not "build an uplift model".** It is: build the measurement first, and let it decide. On this dataset the extra machinery earns nothing over a plain response model, and a team that had assumed otherwise would have spent a quarter finding out. The group's own pilot may well answer differently - automotive replacement is a considered, once-every-few-years decision, where who-would-have-anyway and who-can-be-moved plausibly diverge far more than they do for a clothing e-mail. **That is a reason to measure it, not a reason to assume it.**

## What transfers and what does not

- **No coefficient transfers.** This is a 2008 clothing retailer's e-mail campaign. Nothing in it is about cars, finance, or a five-figure decision.
- **The machine and the test transfer.** `qini()`, `uplift_at()`, `bootstrap()` and the three estimators take any table with a randomised flag and an outcome. Pointed at the group's own pilot they answer the same question about the group's own customers - including the question of whether uplift modelling is worth doing at all.
- **It needs a randomised holdout, and that is the ask.** Uplift cannot be measured on past campaign data, because whoever was contacted was chosen. A pilot has to hold back a random control group. That is a business decision before it is a technical one, and it is the single thing the group must supply that no public data can.
- **The outcome is a visit, not a purchase.** Conversion in this data is under one per cent, too thin to rank on.
- **One dataset.** A negative on Hillstrom is not a negative everywhere; it is the reason to run the test rather than the answer to it.
