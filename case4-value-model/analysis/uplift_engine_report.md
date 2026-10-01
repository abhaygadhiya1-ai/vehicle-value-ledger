# The uplift engine, built and validated on a randomised trial

64,000 customers, randomly assigned by the publisher: a third got no e-mail, two thirds got one. 32,103 held out. The outcome is a visit. **Across everyone the campaign lifts visits by +6.1%** - that is what an untargeted send buys.

The question is not who visits. It is who visits *because they were contacted*. Those are different people, and the table says how different.

| Model | Qini | Uplift in the top 10% | 95% range | Against an untargeted send |
|---|---|---|---|---|
| Class transformation | +32.4 | +7.97% | +5.44% to +11.54% | 1.30x |
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
| Class transformation, top-decile uplift, mean of 10 refits | +6.19 |
| Two-model (T-learner), top-decile uplift, mean of 10 refits | +7.49 |
| Response model (the usual way), top-decile uplift, mean of 10 refits | +8.77 |

## The result, which is not the one the technique is usually sold with

**No uplift model beats the ordinary response model.** The best uplift approach here is two-model (t-learner); against the response model its top-decile uplift differs by **-0.14% (-3.36% to +2.88%)**, a range that comfortably contains zero.

What *is* clear is that a response model is worth having: its top decile shows +8.85% against +6.83% for a random tenth, and +6.1% for sending to everybody.

**So the honest recommendation is not "build an uplift model".** It is: build the measurement first, and let it decide. On this dataset the extra machinery earns nothing over a plain response model, and a team that had assumed otherwise would have spent a quarter finding out. The group's own pilot may well answer differently - automotive replacement is a considered, once-every-few-years decision, where who-would-have-anyway and who-can-be-moved plausibly diverge far more than they do for a clothing e-mail. **That is a reason to measure it, not a reason to assume it.**

## Does the answer depend on the training draw?

The bootstrap above resamples the held-out customers; the models stay fixed. Here each model is refitted on 10 random 80% subsamples of the training half and scored on the same held-out half.

| Model | Top-decile uplift, mean | lowest | highest | Qini, mean | Qini, lowest | Qini, highest |
|---|---|---|---|---|---|---|
| Class transformation | +6.19% | +4.48% | +7.46% | +9.7 | -48.2 | +46.7 |
| Two-model (T-learner) | +7.49% | +6.10% | +8.57% | +2.6 | -25.5 | +34.1 |
| Response model (the usual way) | +8.77% | +7.52% | +9.83% | +61.1 | +50.5 | +71.0 |

**The response model barely moves; the uplift models fall and scatter.** Averaged over the refits, the uplift models reach +6.19% and +7.49% in the top decile, against the response model's +8.77%; a random tenth gives +6.83%. The single fit in the first table is one draw. Uplift is a small difference between two noisy rates, and a model fitted to it learns noise as readily as signal. So the negative result stands, and firmer: on this trial the response model is the steadier one, and no refit average favours an uplift model.

## What transfers and what does not

- **No coefficient transfers.** This is a 2008 clothing retailer's e-mail campaign. Nothing in it is about cars, finance, or a five-figure decision.
- **The machine and the test transfer.** `qini()`, `uplift_at()`, `bootstrap()` and the three estimators take any table with a randomised flag and an outcome. Pointed at the group's own pilot they answer the same question about the group's own customers - including the question of whether uplift modelling is worth doing at all.
- **It needs a randomised holdout, and that is the ask.** Uplift cannot be measured on past campaign data, because whoever was contacted was chosen. A pilot has to hold back a random control group. That is a business decision before it is a technical one, and it is the single thing the group must supply that no public data can.
- **The outcome is a visit, not a purchase.** Conversion in this data is under one per cent, too thin to rank on.
- **One trial here.** A negative on Hillstrom is not a negative everywhere; it is the reason to run the test rather than the answer to it. `uplift_second.py` repeats the test on two more public trials, each tested for randomisation first.
