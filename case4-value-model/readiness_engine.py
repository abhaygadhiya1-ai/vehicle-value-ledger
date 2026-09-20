"""The readiness engine: how likely one car is to come to market, and when.

`value_engine.predict_value()` answers what a car is worth. This answers whether it is about to
move. Together they are the two halves of a vehicle value ledger: what the asset is worth, and
when it becomes a transaction.

    readiness(age_years=5, mileage_km=120_000)
    -> {"probability": 0.33, "low": 0.29, "high": 0.37, ...}

Two layers, each measured, each with its own report:

  * **Layer 1, the level** - `analysis/readiness_base.py`. The share of Dutch cars of that age
    whose keeper changed in the last twelve months, from RDW's own register.
  * **Layer 2, the multiplier** - `analysis/readiness_mileage.py`. How much more likely a car is
    to move when it has been driven harder than its own age cohort, from the UK MOT register.

**Layer 2 barely moves the default answer, and that is a measured result rather than a bug.**
Mileage predicts *leaving the fleet* strongly (1.54x per doubling against the cohort) and predicts
*coming to market* not at all (1.03x). The hardest-driven cars are scrapped or exported rather
than advertised. The engine defaults to `event="to_market"`, which is the ledger's event, so its
mileage multiplier sits near 1; `event="fleet_exit"` gives the strong one, and answers a different
question. **Ranking a customer list by mileage surfaces cars about to be scrapped, not customers
about to buy.**

The two compose cleanly because layer 2 is normalised to average 1 over the fleet's own mileage
distribution. A car on exactly its cohort's mileage gets layer 1 unchanged, and the multiplier can
move one car without moving the total.

**Layer 3 is missing on purpose.** A forcing event - a contract ending, a warranty expiring - is
the third thing that should be in here, and `HANDOFF.md` records the measurement showing it cannot
be recovered from public data: across 300,096 European adverts with a real registration month, the
excess over trend at 36 months is +0.0%. That is not a gap in this file. It is the argument for
the ledger, because the group's own contract dates are the only place the third layer exists.

**What this predicts is that a car comes to market, not that a customer is ready to replace.**
Those are different events and the public data can only see the first.

**The band is narrower than the truth, and deliberately so.** It carries the sampling error in the
two measurements and nothing else. On cohorts of three hundred thousand cars that error is tiny,
which is why a typical car's band comes back a fraction of a point wide. The uncertainty that
actually matters is not in the band and cannot be put there:

  * the level is **Dutch**, and this project has measured three times that a shape travels between
    markets while a level does not;
  * the mileage multiplier is **British**, from a different fleet and a different event;
  * a **keeper change is not a customer deciding to replace**, and the gap between them is an
    assumption, not an estimate.

Read the band as "how well we measured this", never as "how sure we are about your car".

Usage: .venv/bin/python readiness_engine.py        # worked examples
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
BASE = HERE / "analysis" / "readiness_base_hazard.csv"
EFFECT = HERE / "analysis" / "readiness_mileage_effect.csv"
ELASTICITY = HERE / "analysis" / "readiness_mileage_elasticity.csv"

DEFAULT_EVENT = "to_market"
DRAWS = 4_000
SEED = 20260921


class ReadinessEngine:
    """Layers 1 and 2, loaded from the reports that measured them.

    Nothing is typed into this file. Every number is read from the CSV its analysis wrote, which
    is the project's rule: a constant copied into a script is a constant that goes stale.
    """

    def __init__(self, brands="all", event=DEFAULT_EVENT):
        base = pd.read_csv(BASE)
        self.brands = brands
        self.event = event
        suffix = "_st" if brands == "stellantis" else ""
        self.ages = base["age_years"].to_numpy(int)
        self.rate = base[f"rate{suffix}"].to_numpy(float)
        self.parc = base[f"parc{suffix}"].to_numpy(float)
        self.movers = base[f"movers{suffix}"].to_numpy(float)

        el = pd.read_csv(ELASTICITY).set_index("event")
        if event not in el.index:
            raise ValueError(f"event must be one of {list(el.index)}")
        self.b = float(el.loc[event, "elasticity"])
        self.b_se = float(el.loc[event, "se"])

        eff = pd.read_csv(EFFECT)
        eff = eff[eff["event"] == event]
        # the cohort's own median mileage, recovered from the decile table it was cut on
        med = (eff["median_km"] / eff["ratio"]).groupby(eff["age"]).median()
        self.median_km = med.sort_index()
        # deciles are equal-sized, so the fleet average of the multiplier is their mean
        self.normaliser = float(np.mean(eff["ratio"].to_numpy(float) ** self.b))

    def cohort_median_km(self, age_years):
        """Typical mileage for a car of that age, from the UK parc."""
        return float(np.interp(age_years, self.median_km.index.to_numpy(float),
                               self.median_km.to_numpy(float)))

    def base_rate(self, age_years):
        """Layer 1 at that age, with the binomial spread of the count behind it."""
        r = float(np.interp(age_years, self.ages, self.rate))
        n = float(np.interp(age_years, self.ages, self.parc))
        return r, float(np.sqrt(max(r * (1 - r), 1e-12) / n))

    def multiplier(self, age_years, mileage_km, cohort_median_km=None, b=None):
        med = cohort_median_km or self.cohort_median_km(age_years)
        b = self.b if b is None else b
        return (mileage_km / med) ** b / self.normaliser

    def readiness(self, age_years, mileage_km=None, horizon_months=12,
                  cohort_median_km=None):
        """The chance this car comes to market within the horizon, with an 80% band.

        `mileage_km=None` gives layer 1 alone - the answer for a car whose odometer is unknown,
        which is most of a used market and is worth being able to say.
        """
        rate, rate_se = self.base_rate(age_years)
        rng = np.random.default_rng(SEED)
        draw_rate = np.clip(rng.normal(rate, rate_se, DRAWS), 1e-6, 0.999)
        if mileage_km is None:
            mult, annual = 1.0, draw_rate
        else:
            draw_b = rng.normal(self.b, self.b_se, DRAWS)
            med = cohort_median_km or self.cohort_median_km(age_years)
            mult = self.multiplier(age_years, mileage_km, med, self.b)
            factor = (mileage_km / med) ** draw_b / self.normaliser
            annual = np.clip(draw_rate * factor, 1e-6, 0.999)
        horizon = 1 - (1 - annual) ** (horizon_months / 12)
        point = 1 - (1 - np.clip(rate * mult, 1e-6, 0.999)) ** (horizon_months / 12)
        return {
            "probability": float(point),
            "low": float(np.quantile(horizon, 0.10)),
            "high": float(np.quantile(horizon, 0.90)),
            "base_rate": rate,
            "mileage_multiplier": float(mult),
            "cohort_median_km": None if mileage_km is None
            else float(cohort_median_km or self.cohort_median_km(age_years)),
            "horizon_months": horizon_months,
            "driver": "age" if mileage_km is None or abs(np.log(mult)) < 0.1 else "mileage",
        }


def readiness(age_years, mileage_km=None, horizon_months=12, brands="all",
              event=DEFAULT_EVENT, cohort_median_km=None):
    """One call, for a caller that does not want to hold an engine."""
    return ReadinessEngine(brands=brands, event=event).readiness(
        age_years, mileage_km, horizon_months, cohort_median_km)


def rank(cars, horizon_months=12, brands="all", event=DEFAULT_EVENT):
    """Score a book of cars and sort it. This is the shape a contact list actually needs:
    not "is this car ready" but "which of these thirty thousand first"."""
    engine = ReadinessEngine(brands=brands, event=event)
    out = []
    for car in cars:
        r = engine.readiness(car["age_years"], car.get("mileage_km"), horizon_months)
        out.append({**car, **r})
    return pd.DataFrame(out).sort_values("probability", ascending=False, ignore_index=True)


if __name__ == "__main__":
    engine = ReadinessEngine()
    print(f"layer 1: Dutch keeper changes by age, {len(engine.ages)} ages")
    print(f"layer 2: elasticity {engine.b:.3f} (se {engine.b_se:.3f}) on '{engine.event}'")
    print()
    print("A five-year-old car, driven three different ways")
    med = engine.cohort_median_km(5)
    for label, km in (("half its cohort", med / 2), ("typical", med), ("twice", med * 2)):
        r = engine.readiness(5, km)
        print(f"  {label:16s} {km:7,.0f} km  ->  {r['probability']:.1%} "
              f"({r['low']:.1%} to {r['high']:.1%}) in 12 months")
    print()
    print("The same car, at each age, on its cohort's typical mileage")
    for age in (3, 5, 7, 9, 12):
        r = engine.readiness(age, engine.cohort_median_km(age))
        print(f"  age {age:2d}  {r['probability']:.1%} in 12 months, "
              f"{engine.readiness(age, engine.cohort_median_km(age), 3)['probability']:.1%} "
              "in 3")
