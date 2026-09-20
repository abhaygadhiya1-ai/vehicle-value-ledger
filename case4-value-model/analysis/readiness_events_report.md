# Layer 3: the contract-end spike that is not there

A three-year lease ending should put a bulge of cars on the market at 36 months old. This looks for it, and does not find it. **That is the result, and it is the reason the readiness engine has three layers rather than four.**

The test fits the number of adverts at each age in months to a smooth curve in age, plus which source the advert came from, plus the calendar month the car was registered in, plus one term for each contract length. The contract term is the excess over what the ages either side lead you to expect.

## The answer

202,906 European adverts from the 3 sources that record a registration month: `de_2023`, `eu_2025_11`, `pt_standvirtual`.

| Contract length | Excess adverts | Low | High |
|---|---|---|---|
| 24 months | -9.1% | -26.9% | +13.2% |
| 36 months | -16.9% | -31.4% | +0.7% |
| 48 months | -3.9% | -18.4% | +13.2% |
| 60 months | +20.0% | +4.0% | +38.5% |

**At 36 months, the contract length a lease book is built on, there is no bulge: -16.9% (-31.4% to +0.7%).** A car coming off a three-year lease is remarketed weeks to months later, at a spread of ages, and the event smears away.

The one positive reading is +20.0% at 60 months, and the next two tables are what happens when it is taken apart.

## Taking the 60-month reading apart

**One source produces all of it.**

| Source | Adverts | 24 months | 36 months | 48 months | 60 months |
|---|---|---|---|---|---|
| de_2023 | 135,391 | +5.3% | -27.5% | +4.6% | +7.5% |
| eu_2025_11 | 55,274 | -43.6% | +55.5% | -6.6% | +94.6% |
| pt_standvirtual | 12,241 | +9.1% | +1.0% | -8.6% | -1.4% |

`eu_2025_11` reads +94.6% at 60 months; the other two read +7.5% and -1.4%. That source is a single day's scrape whose registration years are lumpy - it carries several times as many cars of one registration year as of its neighbours - and in a November 2025 snapshot that lump sits at about sixty months old. **It is the composition of one scrape, not a contract.**

**And the specification moves it.** The trend column is how flexible the underlying age curve is; the window column is how many months either side of the contract date count as the event.

| Trend | Window | 24 months | 36 months | 48 months | 60 months |
|---|---|---|---|---|---|
| 3 | 0 | -19.5% | -23.7% | -1.9% | +19.2% |
| 3 | 1 | -22.7% | -24.0% | +2.5% | +30.7% |
| 3 | 2 | -18.6% | -20.6% | +8.0% | +22.4% |
| 4 | 0 | -1.8% | -14.9% | -6.6% | +12.3% |
| 4 | 1 | -8.1% | -17.2% | -4.3% | +20.6% |
| 4 | 2 | -2.7% | -13.4% | -0.1% | +11.5% |
| 5 | 0 | -3.7% | -14.3% | -5.9% | +11.1% |
| 5 | 1 | -9.1% | -16.9% | -3.9% | +20.0% |
| 5 | 2 | -3.8% | -13.0% | +0.4% | +10.9% |
| 6 | 0 | -7.7% | -11.9% | -9.6% | +7.1% |
| 6 | 1 | -11.3% | -14.2% | -6.3% | +16.8% |
| 6 | 2 | -5.8% | -9.8% | -1.9% | +8.0% |

Across twelve specifications the 36-month reading is negative in every one (-24.0% to -9.8%), and the 60-month reading swings from +7.1% to +30.7%. **A result that needs one source and one specification is not a result.**

## The trap, shown rather than described

The same test on the sources that record only a registration *year* (1,325,202 adverts), without the calendar control - which for those sources would absorb the very thing being shown, because their calendar month *is* their age. Every car in them lands on a whole number of years:

| Contract length | Apparent excess |
|---|---|
| 24 months | +385.2% |
| 36 months | +716.4% |
| 48 months | +342.7% |
| 60 months | +77.4% |

**Any analysis of age at listing has to filter to month-precision sources first.** This is the trap already in `HANDOFF.md`, measured here so it cannot be forgotten.

## Does the calendar control matter?

A snapshot maps age in months onto the calendar month a car was registered in, one for one. A market that registers heavily in one month therefore bumps every twelfth month of age for reasons that have nothing to do with a contract. With the control in, each contract length is measured against the *other* whole-year ages, which is the right question. Without it:

| Contract length | Excess, no calendar control | Excess, with it |
|---|---|---|
| 24 months | -6.0% | -9.1% |
| 36 months | -15.1% | -16.9% |
| 48 months | -1.4% | -3.9% |
| 60 months | +21.3% | +20.0% |

## What this does and does not say

- **It does not say contracts do not end.** It says the ending does not show up in a public advert. Cars come back, sit in a compound, get prepared, and reach a forecourt over the following weeks and months.
- **It is the argument for the ledger.** The third layer of the engine exists only in the group's own contract dates. No amount of public data recovers it, and that is now a measurement rather than an assertion.
- **These numbers supersede the prose in `HANDOFF.md`** (+0.0% at 36, -4.8% at 48, -8.6% at 24), which came from a different and looser specification with no calendar control and no robustness check. The conclusion is the same and the figures are not; quote these, because a script writes them.
- **Adverts are not returns.** These are asking prices on public sites, and a lease return that goes straight to auction never appears in them at all.
- **Three European snapshots of different dates.** Source and calendar-month effects are absorbed; a difference in how long adverts stay up is not.
