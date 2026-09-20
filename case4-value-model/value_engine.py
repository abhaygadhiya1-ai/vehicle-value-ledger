"""The value engine: what is this car worth now, and what will it be worth later?

`predict_value()` takes the fields a company actually holds at a moment in a car's life and returns
a value with a low/high band - and, more usefully, says **which kind of uncertainty** is making the
band wide, because the kinds have different remedies.

The design is the one the rest of this project measured rather than assumed:

  * **The level is bought fresh.** The price level for a make and model comes from that market's own
    recent listings of about the car's age, never from another market or another year.
    `one_car_report.md` showed a handful of current cars recovers almost all of the error in a
    four-year-stale model. A straight-line age curve cannot follow the real curve at every age, so
    one level over all ages leans one way at some ages; taking it from cars within a year of the
    car's age removes that lean and cuts the typical error (`engine_check_report.md`).
  * **The shape leans on other markets only as far as local noise justifies.** Slopes are fitted on
    this market's own recent cars and blended with every other market's dataset that carries the
    query fields, each refitted on exactly those fields, by how precisely the market measures each
    effect. `field_sets_report.md` showed the blend lands on the local answer wherever local data is
    plentiful, and `lodo_report.md` that borrowing pays on thin slices.
  * **The band is split.** How well the model fits this car, how fast it will depreciate, and where
    the whole market's level will be. Curve uncertainty is a modelling problem that more local data
    fixes; level uncertainty is not a modelling problem at all and has to be priced.
    `level_risk_report.md` measured the second at many times the first over three years.

The band is an 80% band, p10 to p90, the same percentiles the level risk is quoted at. The three
sources are treated as independent and combined by simulation, not by multiplying their edges
together: three p10s at once is far rarer than one in ten. The fit part comes from cars of the same
make and model within a year of the car's age, because the spread widens a lot with age - taken over
every age, the band is too wide for young cars and too narrow for old ones (`engine_check_report.md`,
which measures both designs on held-out cars and checks the value against five other markets).

One caution about reading the band. For a single car the largest term is usually how well the
model fits that car. For a whole book it is the market level, because per-car errors are roughly
independent and average away across thousands of vehicles while a level move hits every one of them
together. Both are true; they are measured at different levels of aggregation.

Not a production service. It loads and fits on demand, which is fine for a few queries and wrong
for a live system; a deployed version would precompute the levels and coefficients nightly.

Usage: .venv/bin/python value_engine.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "analysis"))
import level_risk  # noqa: E402
from drivers import effect  # noqa: E402
from field_sets import EUROPE, MIN_ROWS, columns, levels, load, qualifies, solve  # noqa: E402

LATVIA_MONTHLY = HERE / "analysis" / "latvia_monthly.csv"

# Measured elsewhere; quoted so every number the engine returns is traceable.
LEVEL_WINDOW_MONTHS = 12     # only recent local cars may set the price level
THIN_SLICE_CARS = 250        # lodo_report.md: below this, borrowing still pays
_AGE = effect("age_years")   # drivers.py's pooled age effect: its 95% prediction interval and t
RATE_PREDICTION = (float(np.expm1(_AGE["pi_lo"])), float(np.expm1(_AGE["pi_hi"])))
T975_DF15 = float(_AGE["t975"])

BAND = (10, 90)              # an 80% band, the percentiles the level risk is quoted at
AGE_NEIGHBOURS = 1.0         # the fit spread comes from the same model within this many years of age
MIN_NEIGHBOURS = 30          # fewer than this, and every age of the model is used instead
DRAWS = 20_000
SEED = 0


def centred(d, feats):
    """Rows complete on these fields, with each make-model's own mean subtracted from y and X."""
    km = float(np.nanmedian(d["mileage_km"].to_numpy(float) / d["age_years"].to_numpy(float)))
    X = columns(d, feats, km)
    y = pd.Series(np.log(d["price_eur"].to_numpy(float)), index=d.index)
    g = d["make"].astype(str) + "|" + d["model"].astype(str)
    keep = X.notna().all(axis=1) & np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X, g = y[keep], X[keep], g[keep]
    means = levels(y, X, g)
    if means.empty:
        return None
    ok = g.isin(means.index)
    ref = means.loc[g[ok]]
    return (X[ok].to_numpy(float) - ref[list(X.columns)].to_numpy(float),
            y[ok].to_numpy() - ref["_y"].to_numpy(), list(X.columns))


class ValueEngine:
    """Fits once, then answers questions about one market."""

    def __init__(self, market, verbose=True, as_of=None):
        """`as_of` answers as the engine would have on that date, for backtesting: only listings
        up to it, in every market, and only index history up to it. Without it the engine uses
        everything and sets the level from the market's latest twelve months."""
        self.market = market
        self.verbose = verbose
        self.cutoff = pd.Timestamp(as_of) if as_of is not None else None
        d = load()
        d = d[d["country"].isin(EUROPE) & d["price_eur"].notna()]
        if self.cutoff is not None:
            d = d[pd.to_datetime(d["listing_date"], errors="coerce") <= self.cutoff]
        self.by_source = {s: g for s, g in d.groupby("source", observed=True)
                          if len(g) >= MIN_ROWS}
        local = d[d["country"] == market]
        # The level must be bought FRESH. Mixing listing years would straddle two price eras and
        # inflate every band - which is the exact mistake latvia_time_report.md warns about.
        dates = pd.to_datetime(local["listing_date"], errors="coerce")
        self.as_of = self.cutoff if self.cutoff is not None else dates.max()
        keep = dates >= (self.as_of - pd.DateOffset(months=LEVEL_WINDOW_MONTHS))
        self.local = local[keep.fillna(False)]
        if self.verbose:
            print(f"{market}: {len(local):,} local listings, {len(self.local):,} of them within "
                  f"{LEVEL_WINDOW_MONTHS} months of {self.as_of:%Y-%m} and used to set the level; "
                  f"{len(self.by_source)} European sources available to lean on for the shape")
        self._shape_cache = {}
        self._level_moves = self._load_level_moves()
        rates = np.log1p(pd.read_csv(LATVIA_MONTHLY)["depreciation_pct_per_year"] / 100)
        # Curve uncertainty per year of horizon, as a standard deviation of the log annual rate.
        self._rate_sd = {"known": float(rates.std()),
                         "thin": float(np.diff(np.log1p(RATE_PREDICTION))[0] / 2 / T975_DF15)}

    def _load_level_moves(self):
        """Log moves in the market level over each horizon: level_risk_report.md's common window
        and core markets, so the band matches the figures quoted there."""
        series = level_risk.load()
        end = level_risk.COMMON_END
        if self.cutoff is not None:
            end = min(end, self.cutoff.strftime("%Y-%m"))
        months_in_window = len(pd.period_range(level_risk.COMMON_START, end, freq="M"))
        out = {}
        for k in (12, 24, 36, 48, 60):
            moves = []
            for geo in level_risk.CORE:
                s = series.get((level_risk.EUROSTAT, geo))
                if s is None:
                    continue
                s = s[(s.index >= level_risk.COMMON_START) & (s.index <= end)]
                if len(s) == months_in_window:
                    moves.append(np.log1p(level_risk.moves(s, k).to_numpy() / 100))
            if moves and sum(len(m) for m in moves):
                out[k] = np.concatenate(moves)
        return out

    def _shape(self, feats):
        """This market's own slopes, leaning on other markets only as far as local noise justifies.

        The same blend as the hierarchical column of field_sets.py: each coefficient is weighted
        toward the local estimate by how precisely the local cars measure it. A coefficient the
        local cars cannot measure at all - every car automatic, say - comes wholly from the pool.
        """
        key = tuple(feats)
        if key in self._shape_cache:
            return self._shape_cache[key]
        XtX = Xty = None
        betas, used = [], []
        for src, d in self.by_source.items():
            d = d[d["country"] != self.market]
            if len(d) < MIN_ROWS or not qualifies(d, feats):
                continue
            got = centred(d, feats)
            if got is None or len(got[1]) < MIN_ROWS:
                continue
            Xc, yc, cols = got
            A, b = Xc.T @ Xc, Xc.T @ yc
            XtX = A if XtX is None else XtX + A
            Xty = b if Xty is None else Xty + b
            betas.append(solve(A, b))
            used.append(src)
        if XtX is None:
            raise ValueError(f"no other market's dataset carries all of {feats}")
        pooled = solve(XtX, Xty)
        beta, weight = pooled, np.zeros(len(pooled))
        own = centred(self.local, feats)
        if own is not None and len(own[1]) > len(cols):
            Xc, yc, _ = own
            A = Xc.T @ Xc
            beta_own = solve(A, Xc.T @ yc)
            resid_var = float(np.mean((yc - Xc @ beta_own) ** 2))
            tau2 = np.maximum(np.vstack(betas + [beta_own]).var(axis=0, ddof=1), 1e-12)
            var_own = np.diag(np.linalg.pinv(A)) * resid_var
            weight = np.where(np.diag(A) > 1e-9, tau2 / (tau2 + var_own), 0.0)
            beta = weight * beta_own + (1 - weight) * pooled
        self._shape_cache[key] = (beta, cols, used, weight)
        return self._shape_cache[key]

    def _level(self, make, model, feats, beta, cols, age):
        """This model's price level in this market, and the scatter around it, from its cars of
        about this age - or from every age when fewer than MIN_NEIGHBOURS are that close."""
        g = self.local[(self.local["make"] == make) & (self.local["model"] == model)]
        km = float(np.nanmedian(self.local["mileage_km"].to_numpy(float)
                                / self.local["age_years"].to_numpy(float)))
        if not len(g):
            return None
        X = columns(g, feats, km)
        y = np.log(g["price_eur"].to_numpy(float))
        keep = X.notna().all(axis=1).to_numpy() & np.isfinite(y) & np.isfinite(X).all(axis=1)
        if not keep.sum():
            return None
        resid = y[keep] - X[keep][cols].to_numpy(float) @ beta
        near = np.abs(g["age_years"].to_numpy(float)[keep] - age) <= AGE_NEIGHBOURS
        spread = resid[near] if near.sum() >= MIN_NEIGHBOURS else resid
        mean = float(np.mean(spread))
        return {"level": mean, "scatter": spread - mean, "n": int(keep.sum()),
                "n_scatter": len(spread), "km_per_year": km}

    def predict(self, make, model, age_years, horizon_years=0, **fields):
        """Value now, or `horizon_years` from now at today's market level, with an 80% band."""
        feats = ["age"] + [f for f in ("mileage", "fuel", "gearbox", "body", "power", "engine")
                           if fields.get(f) is not None]
        beta, cols, used, weight = self._shape(feats)
        end_age = age_years + horizon_years
        lvl = self._level(make, model, feats, beta, cols, end_age)
        if lvl is None:
            raise ValueError(f"no {make} {model} listings in {self.market} to set a level")

        # A car keeps being driven: project its reading at its own rate, or the market's if new.
        mileage = fields.get("mileage")
        if mileage is not None:
            per_year = mileage / age_years if age_years > 0 else lvl["km_per_year"]
            mileage = mileage + per_year * horizon_years
        row = pd.DataFrame([{"age_years": end_age,
                             "mileage_km": mileage if mileage is not None
                             else lvl["km_per_year"] * end_age,
                             "fuel": fields.get("fuel"), "transmission": fields.get("gearbox"),
                             "body_type": fields.get("body"), "power_kw": fields.get("power"),
                             "engine_cc": fields.get("engine")}])
        X = columns(row, feats, lvl["km_per_year"])[cols].to_numpy(float)
        value = float(np.exp(lvl["level"] + (X @ beta)[0]))

        thin = lvl["n"] < THIN_SLICE_CARS
        rng = np.random.default_rng(SEED)
        parts = {"how well the model fits this car": rng.choice(lvl["scatter"], DRAWS),
                 "the depreciation curve": (rng.normal(0, self._rate_sd["thin" if thin else "known"],
                                                       DRAWS) * horizon_years),
                 "the market level": np.zeros(DRAWS)}
        if horizon_years > 0:
            months = min(self._level_moves, key=lambda m: abs(m - horizon_years * 12))
            parts["the market level"] = rng.choice(self._level_moves[months], DRAWS)
        low, high = np.percentile(value * np.exp(sum(parts.values())), BAND)
        return {
            "value_eur": value,
            "low_eur": float(low),
            "high_eur": float(high),
            "driven_by": max(parts, key=lambda k: parts[k].var()),
            "local_cars_setting_the_level": lvl["n"],
            "local_cars_setting_the_fit_spread": lvl["n_scatter"],
            "thin_slice": thin,
            "fields_used": feats,
            "mileage_at_valuation_km": row["mileage_km"].iloc[0] if "mileage" in feats else None,
            "datasets_behind_the_shape": len(used),
            "shape_weight_on_local": float(np.mean(weight)),
        }


def predict_value(market, make, model, age_years, horizon_years=0, **fields):
    """One-shot convenience wrapper. Build a ValueEngine directly for repeated queries."""
    return ValueEngine(market, verbose=False).predict(
        make, model, age_years, horizon_years=horizon_years, **fields)


def show(title, r):
    band = f"{r['low_eur']:,.0f} - {r['high_eur']:,.0f}"
    print(f"\n{title}")
    print(f"  value      EUR {r['value_eur']:,.0f}")
    print(f"  80% band   EUR {band}  "
          f"({(r['low_eur'] / r['value_eur'] - 1) * 100:+.0f}% / "
          f"{(r['high_eur'] / r['value_eur'] - 1) * 100:+.0f}%)")
    print(f"  driven by  {r['driven_by']}")
    if r["mileage_at_valuation_km"] is not None:
        print(f"  mileage    {r['mileage_at_valuation_km']:,.0f} km at valuation")
    print(f"  level set by {r['local_cars_setting_the_level']:,} local cars"
          f"{'  [THIN SLICE]' if r['thin_slice'] else ''}; fit spread from "
          f"{r['local_cars_setting_the_fit_spread']:,} of about this age")
    print(f"  shape      {r['shape_weight_on_local']:.0%} from local cars, blended with "
          f"{r['datasets_behind_the_shape']} other-market datasets; fields: "
          f"{', '.join(r['fields_used'])}")


def main():
    engine = ValueEngine("GB")

    show("Vauxhall Corsa, 3 years old, today",
         engine.predict("vauxhall", "corsa", 3, mileage=45_000, fuel="petrol",
                        gearbox="manual", body="hatchback"))
    show("Vauxhall Corsa, 3 years old today, valued 3 years out",
         engine.predict("vauxhall", "corsa", 3, horizon_years=3, mileage=45_000,
                        fuel="petrol", gearbox="manual", body="hatchback"))
    show("Same car today, valued without its odometer reading",
         engine.predict("vauxhall", "corsa", 3, fuel="petrol", gearbox="manual",
                        body="hatchback"))

    ev = engine.local[engine.local["fuel"].astype("string") == "electric"]
    if len(ev):
        top = (ev["make"].astype(str) + "|" + ev["model"].astype(str)).value_counts()
        make, model = top.index[0].split("|")
        show(f"Most-listed electric car in GB: {make} {model}, 3 years old, 3 years out",
             engine.predict(make, model, 3, horizon_years=3, mileage=45_000,
                            fuel="electric", gearbox="automatic"))

    print("\nEvery figure traces to a report: the level and fit spread to this market's own recent "
          "listings, the shape to field_sets_report.md, the curve band to latvia_time_report.md "
          "and drivers_report.md, the level band to level_risk_report.md.")
    print("\nA value 3 years out is at today's market level; the band says how far the level and "
          "the curve could move it. For ONE car, how well the model fits that particular car is "
          "usually the biggest unknown. For a BOOK of thousands, those fit errors are independent "
          "and average away, while a market move hits every car at once and does not. That is why "
          "this engine reports fit error per car and the value-at-risk model applies a level shock "
          "to the whole book.")


if __name__ == "__main__":
    main()
