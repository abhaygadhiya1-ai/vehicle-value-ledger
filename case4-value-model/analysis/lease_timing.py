"""X3 part 2: does a monthly timing curve earn its place in the readiness engine? A holdout test.

Part 1 (`lease_end.py`) found keeper-change waves at 48 and 60 months in the Dutch register. The readiness engine's
layer 1 knows age only in whole years and interpolates between them, so it cannot see a wave. Before a monthly layer
goes into the engine, it has to predict better than the yearly curve on data it has not seen.

Train on the 12 calendar months from 24 to 13 months before the latest full month; predict each age's monthly
keeper-change hazard in the latest 12 months:

  A  yearly: the training hazard averaged over each year of age (months 12y to 12y+11), placed at the year's middle
     and interpolated linearly across months. This is what the engine does today.
  B  monthly: the training hazard at each month of age, as measured.

Scored on ages 13 to 108 months, and apart on 36 to 72 months (the three-to-six-year band where the engine is weakest),
as the Poisson deviance of the predicted keeper changes against the observed ones, and as the car-weighted mean
absolute error of the hazard. A year-to-year change in the market's level hits both predictions equally, so both are
also scored after scaling each to the holdout's total ("shape only"). B also carries more sampling noise than A,
because it estimates each month separately; the test counts that against it.

Same population and data as part 1: domestic cars on the road, RDW register, nothing synthetic.
Usage: .venv/bin/python analysis/lease_timing.py   (after lease_end.py has cached the monthly table)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from build_unified import md_table  # noqa: E402
from lease_end import WINDOWS, hazard, monthly  # noqa: E402

OUT = HERE / "lease_timing_report.md"
CURVE = HERE / "lease_timing_curve.csv"
AGES = (13, 108)
BAND = (36, 72)
ENGINE_AGES = (13, 96)  # a 12-month horizon from 96 months ends at 107, inside the tested ages
HORIZONS = (3, 12)


def yearly(h):
    """The engine's view: each year of age's average hazard, at the year's middle month, interpolated across months."""
    y = h.assign(year=(h.index // 12)).groupby("year")[["n", "parc"]].sum()
    mid = y.index * 12 + 5.5
    rate = y["n"] / y["parc"]
    return pd.Series(np.interp(h.index, mid, rate), index=h.index)


def score(pred, obs, ages, match):
    o = obs.loc[ages[0]:ages[1]]
    p = pred.loc[o.index]
    if match:  # shape only: scale the prediction to the holdout's total keeper changes
        p = p * o["n"].sum() / (p * o["parc"]).sum()
    mu = p * o["parc"]
    y = o["n"]
    deviance = 2 * float(np.sum(np.where(y > 0, y * np.log(y / mu), 0) - (y - mu)))
    mae = float(np.sum(o["parc"] * np.abs(o["n"] / o["parc"] - p)) / o["parc"].sum())
    return deviance, mae


def calendar_year_curve(d, windows):
    """Layer 1's own definition, on the given 12 windows: cars grouped by registration year, age in years the year the
    window ends minus that year, and the share whose current keeper took them on inside the window
    (`build_reference.build_nl_hazard`)."""
    all_ = d[d["brands"] == "all"]
    parc = all_[all_["kind"] == "parc"].groupby(all_["c"].dt.year)["n"].sum()
    moved = all_[(all_["kind"] == "moved") & all_["window"].isin(windows)]
    movers = moved.groupby(moved["c"].dt.year)["n"].sum()
    end_year = (pd.Timestamp(windows[-1]) + pd.offsets.MonthBegin(1)).year
    rate = (movers / parc).dropna()
    rate.index = end_year - rate.index
    return rate[rate.index >= 1].sort_index()


def forward(h, ages, k):
    """The chance of at least one keeper change in the next k months of age, from a monthly hazard by age."""
    return pd.Series([1 - np.prod(1 - h.reindex(range(a, a + k)).to_numpy()) for a in ages], index=list(ages))


def engine_backtest(d, train, test):
    """The readiness engine's forward chance for a car of each age in months, built from the training year only and
    scored against the holdout year's own forward chance at that age:
      A  the engine today: layer 1 (calendar-year ages, interpolated) compounded over the horizon;
      B  layer 3 as first coded: A's monthly rate times the monthly curve's shape over its yearly view;
      C  the fix: the forward chance straight from the monthly curve, which is on the same age axis as the target.
    Weighted by the holdout's cars at each age."""
    ht, hh = hazard(d, "all", train), hazard(d, "all", test)
    mt, mh = ht["n"] / ht["parc"], hh["n"] / hh["parc"]
    shape = mt / yearly(ht)
    l1 = calendar_year_curve(d, train)
    ages = range(ENGINE_AGES[0], ENGINE_AGES[1] + 1)
    w = hh["parc"].reindex(list(ages)).to_numpy()
    rows, examples = [], []
    for k in HORIZONS:
        obs = forward(mh, ages, k)
        annual = pd.Series(np.interp(np.array(ages) / 12, l1.index, l1.to_numpy()), index=list(ages))
        monthly_l1 = 1 - (1 - annual) ** (1 / 12)
        pred = {"A: engine today": 1 - (1 - annual) ** (k / 12),
                "B: layer 3 as first coded": pd.Series(
                    [1 - np.prod(1 - np.clip(monthly_l1[a] * shape.reindex(range(a, a + k)).to_numpy(), 0, 0.999))
                     for a in ages], index=list(ages)),
                "C: monthly curve": forward(mt, ages, k)}
        row = {"horizon (months)": k}
        for name, p in pred.items():
            err = np.abs(p - obs).to_numpy()
            row[f"{name[:1]}: mean abs error (points)"] = round(100 * float(np.sum(w * err) / w.sum()), 2)
            row[f"{name[:1]}: worst age (points)"] = round(100 * float(err.max()), 2)
        rows.append(row)
        for a in (48, 60, 72):
            examples.append({"age (months)": a, "horizon (months)": k, "holdout": round(100 * obs[a], 1),
                             **{name: round(100 * pred[name][a], 1) for name in pred}})
    return pd.DataFrame(rows), pd.DataFrame(examples)


def main():
    d = monthly()
    windows = sorted(d["window"].dropna().unique())
    train, test = windows[-2 * WINDOWS:-WINDOWS], windows[-WINDOWS:]
    ht, hh = hazard(d, "all", train), hazard(d, "all", test)
    pred = {"A: yearly (the engine today)": yearly(ht), "B: monthly": ht["n"] / ht["parc"]}

    rows = []
    for ages, label in ((AGES, f"{AGES[0]} to {AGES[1]} months"), (BAND, f"{BAND[0]} to {BAND[1]} months")):
        for match in (False, True):
            row = {"test": f"{label}, {'shape only' if match else 'level and shape'}"}
            for name, p in pred.items():
                dev, mae = score(p, hh, ages, match)
                row[f"{name[:1]}: deviance"] = round(dev, 1)
                row[f"{name[:1]}: mean abs error (points)"] = round(100 * mae, 4)
            row["deviance saved by B (%)"] = round(100 * (1 - row["B: deviance"] / row["A: deviance"]), 1)
            rows.append(row)
    table = pd.DataFrame(rows)

    # the curve the engine would use: the latest 12 months, at each month of age, beside the yearly view
    latest = hazard(d, "all", test)
    curve = pd.DataFrame({"age_months": latest.index, "movers": latest["n"].astype(int).to_numpy(),
                          "parc": latest["parc"].astype(int).to_numpy(),
                          "monthly_hazard": (latest["n"] / latest["parc"]).round(6).to_numpy(),
                          "yearly_view": yearly(latest).round(6).to_numpy()})
    curve.to_csv(CURVE, index=False)
    engine, examples = engine_backtest(d, train, test)

    OUT.write_text(f"""# X3 part 2: does a monthly timing curve beat the yearly one on a holdout year?

_Generated by `analysis/lease_timing.py`. Real RDW register data (public domain), not synthetic._

Trained on keeper changes from {pd.Timestamp(train[0]):%B %Y} to {pd.Timestamp(train[-1]):%B %Y}; tested on
{pd.Timestamp(test[0]):%B %Y} to {pd.Timestamp(test[-1]):%B %Y}. A is the engine's yearly curve, interpolated across
months; B is the monthly curve with its waves. Lower deviance and error are better. "Shape only" scales each
prediction to the holdout's total, so a change in the market's level between the two years does not count.

{md_table(table)}

The curve for the engine, from the latest 12 months, is written to `analysis/lease_timing_curve.csv`: the monthly
hazard at each month of age beside the yearly view.

## The engine's own answer, back-tested

The engine answers "the chance this car comes to market in the next k months". Each version is built from the
training year only and scored against the holdout year's forward chance at each age in months from
{ENGINE_AGES[0]} to {ENGINE_AGES[1]}, weighted by the holdout's cars at that age. A is the engine today (layer 1:
calendar-year ages, interpolated); B is layer 3 as first coded (A's rate times the monthly shape); C takes the
forward chance straight from the monthly curve, on the same age axis as the target.

{md_table(engine)}

At three ages (%):

{md_table(examples)}
""")
    print(md_table(table))
    print(md_table(engine))
    print(md_table(examples))
    print(f"wrote {OUT.relative_to(HERE.parent)} and {CURVE.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
