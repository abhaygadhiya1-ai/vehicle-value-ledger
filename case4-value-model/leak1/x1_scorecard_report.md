# X1 scorecard: every world, every layer

**Synthetic.** These figures measure our tool in worlds that we or a blind red team built. They say nothing about the
group's leak rate. The catch rates are unit tests of our own code, not evidence of real performance (skeptic A14).
What carries over is rankings, failures and engineering facts.

Written by `leak1/scorecard.py`; re-run it rather than editing this file.

## The runs

Round 1 has no blind run: its code was never frozen, and the fixes that followed it changed three detector files. Its
blind result survives only as the written record in the X1 notes. Each later round's blind run uses the code frozen
before the round (a tag in this folder's local repo); its detector files match the hashes recorded before the round.

"Hard rules on legitimate claims" counts legitimate live claims that break at least one hard rule. It must be zero in
our world (the self-check). In a red-team world, a non-zero count is a finding, with two exceptions that can be
rightly flagged: a claim labelled legitimate that is the original of a leak claim (the truth table's `dup_of`), and one
on a car whose vehicle record the red team falsified (its own change log), judged against the true record. The X1
notes discuss each case.

| run | world | code | claims | leak claims | leak EUR (k) | hard rules on legitimate claims | of which the original of a leak claim | of which on a car whose record the red team changed | layer1_keys | layer2_splink | layer3_rules | final flags (hash) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ours | data/synthetic | today's | 171999 | 4623 | 3,169 | 0 | 0 | 0 | c71e15756eec | ea1789a93022 | 5d11979508f2 | fb3d2c93bc29 |
| RT1 post hoc | data/synthetic_redteam | today's | 167744 | 1324 | 519 | 4 | 0 | 4 | c71e15756eec | ea1789a93022 | 5d11979508f2 | 343aa275302a |
| RT2 blind | data/synthetic_redteam2 | redteam2-frozen | 169159 | 1929 | 1,229 | 0 | 0 | 0 | c71e15756eec | ea1789a93022 | 7943c1dd849f | 85d1a87fbffc |
| RT2 post hoc | data/synthetic_redteam2 | today's | 169159 | 1929 | 1,229 | 498 | 495 | 3 | c71e15756eec | ea1789a93022 | 5d11979508f2 | 2f6354896548 |
| RT3 blind | data/synthetic_redteam3 | redteam3-frozen | 167696 | 2570 | 728 | 0 | 0 | 0 | c71e15756eec | ea1789a93022 | d769ec4dd0e4 | bbd9306802cf |
| RT3 post hoc | data/synthetic_redteam3 | today's | 167696 | 2570 | 728 | 0 | 0 | 0 | c71e15756eec | ea1789a93022 | 5d11979508f2 | 5e4539f5384e |
| RT4 blind | data/synthetic_redteam4 | redteam4-frozen | 167247 | 516 | 259 | 0 | 0 | 0 | c71e15756eec | ea1789a93022 | 5d11979508f2 | 7c6688a08f5b |
| RT4 post hoc | data/synthetic_redteam4 | today's | 167247 | 516 | 259 | 0 | 0 | 0 | c71e15756eec | ea1789a93022 | 5d11979508f2 | 7c6688a08f5b |

## Headline, by stage

Stages are cumulative: keys (layer 1), + matching (layer 2), + hard rules (layer 3's hard rules), + gaming rule (its
statistical timing rule), + keeper check (part 7b's register keeper check), + contract check (part 9's fleet check
against the JV's contracts), + complete sources (the review rules on the sources written after round 3; layer 3 in
full). The last four are review rules: they hold a claim for a person to decide. A flag means "do not pay this claim as filed". Scoring is strict and per claim. Frozen code that predates a
rule leaves its stage unchanged.

| run and stage | flagged | precision (%) | recall (%) | euro recall (%) | false alarms per 1,000 legitimate | review load per 1,000 claims |
|---|---|---|---|---|---|---|
| Ours · keys | 2627 | 47.1 | 26.8 | 30.6 | 8.30 | 15.3 |
| Ours · + matching | 1238 | 99.7 | 26.7 | 30.6 | 0.02 | 7.2 |
| Ours · + hard rules | 3534 | 99.9 | 76.4 | 89.6 | 0.02 | 20.5 |
| Ours · + gaming rule | 8798 | 46.5 | 88.4 | 94.9 | 28.14 | 51.2 |
| Ours · + keeper check | 9811 | 46.7 | 99.1 | 99.6 | 31.24 | 57.0 |
| Ours · + contract check | 10055 | 45.6 | 99.1 | 99.6 | 32.69 | 58.5 |
| Ours · + complete sources | 10094 | 45.4 | 99.1 | 99.6 | 32.93 | 58.7 |
| RT1 post hoc · keys | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT1 post hoc · + matching | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT1 post hoc · + hard rules | 1328 | 99.7 | 100.0 | 100.0 | 0.02 | 7.9 |
| RT1 post hoc · + gaming rule | 6128 | 21.6 | 100.0 | 100.0 | 28.87 | 36.5 |
| RT1 post hoc · + keeper check | 6650 | 19.9 | 100.0 | 100.0 | 32.00 | 39.6 |
| RT1 post hoc · + contract check | 6650 | 19.9 | 100.0 | 100.0 | 32.00 | 39.6 |
| RT1 post hoc · + complete sources | 6650 | 19.9 | 100.0 | 100.0 | 32.00 | 39.6 |
| RT2 blind · keys | 495 | 100.0 | 25.7 | 47.7 | 0.00 | 2.9 |
| RT2 blind · + matching | 495 | 100.0 | 25.7 | 47.7 | 0.00 | 2.9 |
| RT2 blind · + hard rules | 495 | 100.0 | 25.7 | 47.7 | 0.00 | 2.9 |
| RT2 blind · + gaming rule | 5388 | 10.8 | 30.1 | 50.3 | 28.74 | 31.9 |
| RT2 blind · + keeper check | 5388 | 10.8 | 30.1 | 50.3 | 28.74 | 31.9 |
| RT2 blind · + contract check | 5388 | 10.8 | 30.1 | 50.3 | 28.74 | 31.9 |
| RT2 blind · + complete sources | 5388 | 10.8 | 30.1 | 50.3 | 28.74 | 31.9 |
| RT2 post hoc · keys | 495 | 100.0 | 25.7 | 47.7 | 0.00 | 2.9 |
| RT2 post hoc · + matching | 495 | 100.0 | 25.7 | 47.7 | 0.00 | 2.9 |
| RT2 post hoc · + hard rules | 2146 | 76.8 | 85.4 | 75.2 | 2.98 | 12.7 |
| RT2 post hoc · + gaming rule | 6938 | 23.8 | 85.4 | 75.2 | 31.63 | 41.0 |
| RT2 post hoc · + keeper check | 7445 | 22.1 | 85.4 | 75.2 | 34.66 | 44.0 |
| RT2 post hoc · + contract check | 7966 | 24.2 | 100.0 | 100.0 | 36.10 | 47.1 |
| RT2 post hoc · + complete sources | 7966 | 24.2 | 100.0 | 100.0 | 36.10 | 47.1 |
| RT3 blind · keys | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT3 blind · + matching | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT3 blind · + hard rules | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT3 blind · + gaming rule | 4994 | 1.4 | 2.8 | 4.1 | 29.81 | 29.8 |
| RT3 blind · + keeper check | 5516 | 1.3 | 2.8 | 4.1 | 32.97 | 32.9 |
| RT3 blind · + contract check | 5516 | 1.3 | 2.8 | 4.1 | 32.97 | 32.9 |
| RT3 blind · + complete sources | 5516 | 1.3 | 2.8 | 4.1 | 32.97 | 32.9 |
| RT3 post hoc · keys | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT3 post hoc · + matching | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT3 post hoc · + hard rules | 2116 | 100.0 | 82.3 | 58.3 | 0.00 | 12.6 |
| RT3 post hoc · + gaming rule | 7024 | 30.7 | 83.9 | 61.0 | 29.48 | 41.9 |
| RT3 post hoc · + keeper check | 7546 | 28.6 | 83.9 | 61.0 | 32.64 | 45.0 |
| RT3 post hoc · + contract check | 8007 | 29.5 | 92.1 | 91.8 | 34.16 | 47.7 |
| RT3 post hoc · + complete sources | 8181 | 30.6 | 97.3 | 98.6 | 34.40 | 48.8 |
| RT4 blind · keys | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT4 blind · + matching | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT4 blind · + hard rules | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT4 blind · + gaming rule | 4814 | 0.0 | 0.0 | 0.0 | 28.87 | 28.8 |
| RT4 blind · + keeper check | 5336 | 0.0 | 0.0 | 0.0 | 32.00 | 31.9 |
| RT4 blind · + contract check | 5580 | 0.0 | 0.0 | 0.0 | 33.47 | 33.4 |
| RT4 blind · + complete sources | 5619 | 0.0 | 0.0 | 0.0 | 33.70 | 33.6 |
| RT4 post hoc · keys | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT4 post hoc · + matching | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT4 post hoc · + hard rules | 0 |  | 0.0 | 0.0 | 0.00 | 0.0 |
| RT4 post hoc · + gaming rule | 4814 | 0.0 | 0.0 | 0.0 | 28.87 | 28.8 |
| RT4 post hoc · + keeper check | 5336 | 0.0 | 0.0 | 0.0 | 32.00 | 31.9 |
| RT4 post hoc · + contract check | 5580 | 0.0 | 0.0 | 0.0 | 33.47 | 33.4 |
| RT4 post hoc · + complete sources | 5619 | 0.0 | 0.0 | 0.0 | 33.70 | 33.6 |

## Review load, by unit

The gaming rule holds every volume claim of a flagged dealer-quarter: the car's recorded dealer, in the quarter of its
sale event. A reviewer therefore checks the dealer-quarter once, not each held claim. Review units are the claims
flagged before the gaming rule, one each, plus the dealer-quarters holding claims, one each. "With a leak claim" means
at least one held claim is a leak: the dealer-quarter was worth reviewing.

| run | claims flagged before the gaming rule | claims held by the gaming rule | dealer-quarters held: A | dealer-quarters held: B | dealer-quarters held | of which with a leak claim | review units | review units per 1,000 claims |
|---|---|---|---|---|---|---|---|---|
| Ours | 3534 | 5264 | 84 | 24 | 108 | 8 | 3642 | 21.2 |
| RT1 post hoc | 1328 | 4800 | 77 | 24 | 101 | 0 | 1429 | 8.5 |
| RT2 blind | 495 | 4893 | 79 | 29 | 108 | 8 | 603 | 3.6 |
| RT2 post hoc | 2146 | 4792 | 77 | 24 | 101 | 0 | 2247 | 13.3 |
| RT3 blind | 0 | 4994 | 82 | 29 | 111 | 6 | 111 | 0.7 |
| RT3 post hoc | 2116 | 4908 | 81 | 27 | 108 | 3 | 2224 | 13.3 |
| RT4 blind | 0 | 4814 | 78 | 24 | 102 | 0 | 102 | 0.6 |
| RT4 post hoc | 0 | 4814 | 78 | 24 | 102 | 0 | 102 | 0.6 |

The full pipeline, counted the same way. The gaming rule, the keeper check and the two complete-source rules hold
dealer-quarters, so a dealer-quarter any of them holds is one unit. Every other flag is one claim, the contract
check's included.

| run | full pipeline: claims flagged one by one | full pipeline: of which by the contract check | full pipeline: dealer-quarters held | full pipeline: of which with a leak claim | full pipeline: review units | full pipeline: review units per 1,000 claims |
|---|---|---|---|---|---|---|
| Ours | 3778 | 244 | 123 | 14 | 3901 | 22.7 |
| RT1 post hoc | 1328 | 0 | 108 | 0 | 1436 | 8.6 |
| RT2 blind | 495 | 0 | 108 | 8 | 603 | 3.6 |
| RT2 post hoc | 2667 | 521 | 108 | 0 | 2775 | 16.4 |
| RT3 blind | 0 | 0 | 118 | 6 | 118 | 0.7 |
| RT3 post hoc | 2577 | 461 | 126 | 12 | 2703 | 16.1 |
| RT4 blind | 244 | 244 | 111 | 0 | 355 | 2.1 |
| RT4 post hoc | 244 | 244 | 111 | 0 | 355 | 2.1 |

## Matching under noise: Splink against the plain rule

Our world only, from the part 6b stress test (`stress.py`, run through its own functions). Noise touches only what a
detector reads. Level 0 is the clean world, level 1 uses the rates in `spec.py` (ASSUMPTION settings) and level 2
doubles them. The band is the claims layer 1 could not link: real claims with a broken key, and phantom orders with no
car. The plain rule links a claim to the car of the same dealer whose key is within two edits. The ranking is the
finding, not the levels (A14).

| level and method | band claims | right car | wrong car | no car | phantoms linked | phantoms held | precision (%) | recall (%) | false alarms per 1,000 legitimate | review load per 1,000 claims |
|---|---|---|---|---|---|---|---|---|---|---|
| level 0 · layer 1 only |  |  |  |  |  |  | 47.1 | 26.8 | 8.30 | 15.3 |
| level 0 · Splink | 2338 | 2107 | 0 | 0 | 0 | 231 | 99.7 | 26.7 | 0.02 | 7.2 |
| level 0 · plain rule | 2338 | 2107 | 0 | 0 | 10 | 221 | 99.7 | 26.6 | 0.02 | 7.2 |
| level 1 · layer 1 only |  |  |  |  |  |  | 47.1 | 26.8 | 8.29 | 15.3 |
| level 1 · Splink | 2336 | 1847 | 0 | 258 | 1 | 230 | 87.2 | 26.7 | 1.08 | 8.2 |
| level 1 · plain rule | 2336 | 1703 | 0 | 402 | 12 | 219 | 81.6 | 26.5 | 1.65 | 8.7 |
| level 2 · layer 1 only |  |  |  |  |  |  | 47.1 | 26.8 | 8.30 | 15.3 |
| level 2 · Splink | 2337 | 1526 | 0 | 580 | 1 | 230 | 76.2 | 26.6 | 2.29 | 9.4 |
| level 2 · plain rule | 2337 | 1371 | 0 | 735 | 12 | 219 | 71.6 | 26.5 | 2.91 | 10.0 |

Where each method fails: of the real band claims hit by each kind of noise, the share left without a car. A claim can
be hit by several kinds.

| level and noise | real band claims hit | left without a car, Splink (%) | left without a car, plain rule (%) |
|---|---|---|---|
| level 1 · fleet batch | 449 | 14.7 | 17.6 |
| level 1 · invoice price | 391 | 20.2 | 20.5 |
| level 1 · date keyed off | 212 | 14.6 | 19.8 |
| level 1 · wrong dealer code | 38 | 50.0 | 100.0 |
| level 1 · heavy typo | 683 | 36.2 | 54.8 |
| level 1 · none of these | 808 | 0.0 | 0.0 |
| level 2 · fleet batch | 449 | 30.5 | 35.0 |
| level 2 · invoice price | 762 | 33.2 | 34.8 |
| level 2 · date keyed off | 428 | 27.3 | 35.0 |
| level 2 · wrong dealer code | 87 | 59.8 | 100.0 |
| level 2 · heavy typo | 1291 | 43.8 | 54.3 |
| level 2 · none of these | 304 | 0.0 | 0.0 |

## Leaks, by type

The share of each leak type's claims flagged by the end of each stage, and the share of its euros caught in the end.

| run and leak | claims | leak EUR (k) | keys (%) | + matching (%) | + hard rules (%) | + gaming rule (%) | + keeper check (%) | + contract check (%) | + complete sources (%) | euro recall (%) |
|---|---|---|---|---|---|---|---|---|---|---|
| Ours · late_claim | 1645 | 1,373 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Ours · quarter_end_gaming | 1089 | 327 | 0.0 | 0.0 | 0.0 | 51.2 | 96.7 | 96.7 | 96.7 | 96.7 |
| Ours · vin_typo | 825 | 666 | 99.9 | 99.5 | 99.5 | 99.5 | 99.5 | 99.5 | 99.5 | 99.6 |
| Ours · illegal_stack | 651 | 499 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Ours · pre_vin_claim | 231 | 214 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Ours · cross_system_duplicate | 182 | 91 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT1 post hoc · rt_rooftop_pooling | 559 | 168 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT1 post hoc · rt_system_shopping | 359 | 136 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT1 post hoc · rt_fake_conquest | 232 | 116 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT1 post hoc · rt_order_backdate | 126 | 65 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT1 post hoc · rt_programme_period | 48 | 35 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT2 blind · rt_volume_transfer | 614 | 206 | 0.0 | 0.0 | 0.0 | 13.0 | 13.0 | 13.0 | 13.0 | 15.1 |
| RT2 blind · rt_delta_credit_refile | 495 | 586 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT2 blind · rt_vat_gross_in_a | 493 | 98 | 0.0 | 0.0 | 0.0 | 1.2 | 1.2 | 1.2 | 1.2 | 0.4 |
| RT2 blind · rt_fleet_upcode | 281 | 304 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT2 blind · rt_order_forward_date | 46 | 34 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT2 post hoc · rt_volume_transfer | 614 | 206 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT2 post hoc · rt_delta_credit_refile | 495 | 586 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT2 post hoc · rt_vat_gross_in_a | 493 | 98 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT2 post hoc · rt_fleet_upcode | 281 | 304 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 |
| RT2 post hoc · rt_order_forward_date | 46 | 34 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT3 blind · list_price_inflation | 1400 | 133 | 0.0 | 0.0 | 0.0 | 0.6 | 0.6 | 0.6 | 0.6 | 0.3 |
| RT3 blind · transfer_pooling | 378 | 114 | 0.0 | 0.0 | 0.0 | 6.3 | 6.3 | 6.3 | 6.3 | 8.6 |
| RT3 blind · straw_tradein_conquest | 332 | 166 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT3 blind · fleet_relabel | 210 | 225 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT3 blind · slow_handover_selfreg | 162 | 46 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT3 blind · placeholder_order | 88 | 43 | 0.0 | 0.0 | 0.0 | 45.5 | 45.5 | 45.5 | 45.5 | 44.7 |
| RT3 post hoc · list_price_inflation | 1400 | 133 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT3 post hoc · transfer_pooling | 378 | 114 | 0.0 | 0.0 | 91.3 | 91.3 | 91.3 | 91.3 | 91.3 | 100.0 |
| RT3 post hoc · straw_tradein_conquest | 332 | 166 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| RT3 post hoc · fleet_relabel | 210 | 225 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 |
| RT3 post hoc · slow_handover_selfreg | 162 | 46 | 0.0 | 0.0 | 24.1 | 24.1 | 24.1 | 24.1 | 77.8 | 77.3 |
| RT3 post hoc · placeholder_order | 88 | 43 | 0.0 | 0.0 | 0.0 | 45.5 | 45.5 | 45.5 | 100.0 | 100.0 |
| RT4 blind · credit_parking | 199 | 64 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT4 blind · third_party_prereg | 111 | 32 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT4 blind · laundered_conquest | 92 | 46 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT4 blind · straw_fleet_lease | 80 | 85 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT4 blind · late_selfreg_shift | 34 | 32 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT4 post hoc · credit_parking | 199 | 64 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT4 post hoc · third_party_prereg | 111 | 32 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT4 post hoc · laundered_conquest | 92 | 46 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT4 post hoc · straw_fleet_lease | 80 | 85 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT4 post hoc · late_selfreg_shift | 34 | 32 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Legitimate claims, by type

The share of each legitimate label flagged by the end of each stage: the false alarms.

| run and label | claims | keys (%) | + matching (%) | + hard rules (%) | + gaming rule (%) | + keeper check (%) | + contract check (%) | + complete sources (%) |
|---|---|---|---|---|---|---|---|---|
| Ours · clean | 160481 | 0.0 | 0.0 | 0.0 | 2.9 | 3.2 | 3.3 | 3.3 |
| Ours · legit_reversal | 3399 | 0.0 | 0.0 | 0.0 | 1.1 | 1.3 | 1.3 | 1.3 |
| Ours · legit_vin_blank | 1895 | 0.0 | 0.0 | 0.0 | 2.3 | 2.3 | 2.3 | 2.6 |
| Ours · legit_key_typo | 1571 | 88.5 | 0.0 | 0.0 | 2.7 | 2.8 | 3.1 | 3.1 |
| Ours · legit_gamed_car | 30 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 6.7 | 6.7 |
| RT1 post hoc · clean | 164436 | 0.0 | 0.0 | 0.0 | 2.9 | 3.2 | 3.2 | 3.2 |
| RT1 post hoc · rt_legit_a_boundary | 1014 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT1 post hoc · rt_legit_twin_vins | 970 | 0.0 | 0.0 | 0.0 | 1.0 | 1.2 | 1.2 | 1.2 |
| RT2 blind · clean | 166203 | 0.0 | 0.0 | 0.0 | 2.9 | 2.9 | 2.9 | 2.9 |
| RT2 blind · rt_legit_full_reversal | 891 | 0.0 | 0.0 | 0.0 | 0.2 | 0.2 | 0.2 | 0.2 |
| RT2 blind · rt_legit_self_corrected | 136 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT2 post hoc · clean | 166203 | 0.0 | 0.0 | 0.3 | 3.2 | 3.5 | 3.6 | 3.6 |
| RT2 post hoc · rt_legit_full_reversal | 891 | 0.0 | 0.0 | 0.0 | 0.2 | 0.2 | 0.2 | 0.2 |
| RT2 post hoc · rt_legit_self_corrected | 136 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT3 blind · clean | 163782 | 0.0 | 0.0 | 0.0 | 2.9 | 3.3 | 3.3 | 3.3 |
| RT3 blind · legit_fleet_tradein | 938 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT3 blind · legit_delivery_batch | 406 | 0.0 | 0.0 | 0.0 | 24.6 | 24.6 | 24.6 | 24.6 |
| RT3 post hoc · clean | 163782 | 0.0 | 0.0 | 0.0 | 2.9 | 3.2 | 3.4 | 3.4 |
| RT3 post hoc · legit_fleet_tradein | 938 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.5 | 0.5 |
| RT3 post hoc · legit_delivery_batch | 406 | 0.0 | 0.0 | 0.0 | 24.6 | 24.6 | 26.8 | 26.8 |
| RT4 blind · clean | 166569 | 0.0 | 0.0 | 0.0 | 2.9 | 3.2 | 3.3 | 3.4 |
| RT4 blind · genuine_resale_31d | 87 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT4 blind · dealer_trade_to_target | 75 | 0.0 | 0.0 | 0.0 | 18.7 | 18.7 | 18.7 | 18.7 |
| RT4 post hoc · clean | 166569 | 0.0 | 0.0 | 0.0 | 2.9 | 3.2 | 3.3 | 3.4 |
| RT4 post hoc · genuine_resale_31d | 87 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RT4 post hoc · dealer_trade_to_target | 75 | 0.0 | 0.0 | 0.0 | 18.7 | 18.7 | 18.7 | 18.7 |

## Checks that passed

- The frozen code of each blind run matches every hash recorded before its round.
- In every run, adding the gaming rule only adds `gaming_suspect` flags to claims no hard rule flagged, adding the
  keeper check only adds `self_registration_suspect` flags, adding the contract check only adds
  `contract_contradicted` and `fleet_unverified` flags, and adding the complete sources only adds
  `first_keeper_suspect` and `order_change_suspect` flags, each to claims no earlier rule flagged.
- In every run, each dealer-quarter the gaming rule flags holds at least one claim, so the table's counts are the rule's own.

## Round 2: what the post-hoc fixes changed

Every claim whose final flag differs between the blind run (frozen code) and the post-hoc run (today's code), by the
two flags. "passed" means no flag. The post-hoc code adds `wrong_amount` and reads each car's dealer and order date
from the OEM's record instead of the dealer-reported one; the red team corrupted both in the record.

| change | claims | of which leak claims |
|---|---|---|
| passed → wrong_amount | 980 | 487 |
| passed → volume_not_earned | 534 | 534 |
| passed → self_registration_suspect | 507 | 0 |
| passed → fleet_unverified | 421 | 198 |
| passed → contract_contradicted | 100 | 83 |
| gaming_suspect → volume_not_earned | 80 | 80 |
| passed → outside_years | 46 | 46 |
| gaming_suspect → passed | 27 | 0 |
| passed → gaming_suspect | 14 | 0 |
| gaming_suspect → wrong_amount | 8 | 6 |
| passed → late_claim | 3 | 0 |
