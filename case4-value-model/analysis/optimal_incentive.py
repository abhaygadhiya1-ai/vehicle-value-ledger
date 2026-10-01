"""X5: when does an incentive pay? One condition, one small function, and its inputs from the register.

An incentive of s euros per car buys extra sales. It is also paid on every car that would have sold anyway, and a car
sold cheaper resells cheaper. Per baseline car (a car that would have sold with no incentive):

  cars sold    q(s) = 1 + e * t * s / p         only the part t*s that reaches the buyer's price moves the buyer
  cost         B    = 1 + r * t * g             one euro spent, plus the resale value the group loses with it
  new margin   A    = (1 - f - k) * m           the margin on an extra car that is new to the group
  profit(s)    = (q(s) - 1) * A - q(s) * s * B

  p  price before the incentive          m  the group's margin on one extra car
  e  own-price elasticity (positive)     t  pass-through: the share of the spend that reaches the buyer's price,
                                            set by the incentive's type (customer rebate, dealer bonus)
  r  resale value lost per euro of price cut, on a car whose resale the group bears
  g  share of cars whose resale the group bears (leases and buy-backs)
  f  share of the extra sales only pulled forward from later months
  k  share of the extra sales taken from the group's own other brands

profit(s) is a quadratic, so the answer has a closed form (see the report). The response is linear: the elasticity is
read at today's price, so this is a local answer for incentives that are small against the price. The resale cost is
not discounted, though it falls due years later.

Part 1's example and checks use round illustrative numbers. Part 2 reads the inputs from `assumptions.csv`: the
resale cost per euro of price cut comes from the same rows and formula as the workbook's Prior discounting sheet. It
then tests whether the sourced margins and elasticities agree with each other (the Lerner check). Part 4 takes
today's uniform incentive as the best uniform one and derives what giving each income quartile its own incentive
earns, by fuel, across the 2025 fuel mix, one input at a time.
Usage: .venv/bin/python analysis/optimal_incentive.py   (writes analysis/optimal_incentive_report.md)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_unified import md_table  # noqa: E402

OUT = HERE / "optimal_incentive_report.md"
REGISTER = HERE.parent / "assumptions.csv"
ELASTICITIES = ["x5_elast_ch_avg", "x5_elast_ch_lowinc", "x5_elast_ch_highinc", "x5_scrap_nontargeted"]
MARGINS = ["x5_markup_grv", "pl_sale_margin_pct_list"]


def optimal_incentive(*, price, margin, elasticity, pass_through, resale_cost=0.0, group_bears=0.0,
                      pulled_forward=0.0, from_sister=0.0, spend=0.0, floor=0.0):
    """The profit-maximising incentive per car, and what spending `spend` per car costs against it.

    Euro results are per baseline car. `first_euro_return` is what the first euro of spend earns back; an incentive
    pays at all only if it is above 1. `floor` is the lowest spend allowed: below zero, it takes back part of an
    incentive already paid (part 4 measures spend from today's level).
    """
    slope = elasticity * pass_through / price
    cost = 1 + resale_cost * pass_through * group_bears
    new_margin = (1 - pulled_forward - from_sister) * margin

    def profit(s):
        q = 1 + slope * s
        return (q - 1) * new_margin - q * s * cost

    first_euro = slope * new_margin / cost
    best = max(floor, (new_margin / cost - 1 / slope) / 2) if slope > 0 else floor
    return {
        "first_euro_return": first_euro,
        "optimal_spend": best,
        "profit_at_optimum": profit(best),
        "profit_at_spend": profit(spend),
        "profit_lost": profit(best) - profit(spend),
        "spend_above_optimum": max(spend - best, 0.0) * (1 + slope * spend),
        "profit": profit,
    }


# Round numbers chosen so the arithmetic can be done by hand. Illustrative, not estimates.
EXAMPLE = dict(price=20_000, margin=5_000, elasticity=10, pass_through=0.8, resale_cost=0.25, group_bears=0.5,
               pulled_forward=0.2, from_sister=0.0, spend=1_000)
# The same example worked by hand (see the report), to the cent.
BY_HAND = {"first_euro_return": 16 / 11, "optimal_spend": 568.18, "profit_at_optimum": 142.05,
           "profit_at_spend": 60.00, "profit_lost": 82.05, "spend_above_optimum": 604.55}


def checks():
    rows = []

    def check(name, expected, got, tol):
        rows.append({"check": name, "expected": round(expected, 4), "got": round(got, 4),
                     "passes": abs(got - expected) <= tol})

    ex = optimal_incentive(**EXAMPLE)
    for key, value in BY_HAND.items():
        check(f"example: {key.replace('_', ' ')}", value, ex[key], 0.01 if key != "first_euro_return" else 1e-9)

    grid = np.arange(0, 5_000, 0.01)
    check("example: optimum found by a search over every cent from 0 to 5,000",
          grid[np.argmax(ex["profit"](grid))], ex["optimal_spend"], 0.01)
    h = 0.01
    check("example: slope of profit at the optimum", 0.0,
          (ex["profit"](ex["optimal_spend"] + h) - ex["profit"](ex["optimal_spend"] - h)) / (2 * h), 1e-6)

    zero = optimal_incentive(**{**EXAMPLE, "elasticity": 0})
    check("no response: optimal spend", 0.0, zero["optimal_spend"], 0)
    cost = 1 + EXAMPLE["resale_cost"] * EXAMPLE["pass_through"] * EXAMPLE["group_bears"]
    check("no response: profit lost = the spend times its cost", EXAMPLE["spend"] * cost, zero["profit_lost"], 1e-9)

    # A list price that already maximises profit has elasticity x margin / price = 1 (the Lerner rule).
    lerner = dict(EXAMPLE, elasticity=EXAMPLE["price"] / EXAMPLE["margin"], pass_through=1.0, resale_cost=0.0,
                  pulled_forward=0.0)
    at_lerner = optimal_incentive(**lerner)
    check("price already optimal, full pass-through, no resale cost: first-euro return", 1.0,
          at_lerner["first_euro_return"], 1e-12)
    check("the same: optimal spend", 0.0, at_lerner["optimal_spend"], 1e-9)
    check("the same with pass-through 0.8: optimal spend", 0.0,
          optimal_incentive(**{**lerner, "pass_through": 0.8})["optimal_spend"], 0)

    by_resale = [optimal_incentive(**{**EXAMPLE, "resale_cost": r})["optimal_spend"] for r in (0, 0.25, 0.5)]
    check("optimal spend falls as the resale cost rises", 1.0, float(np.all(np.diff(by_resale) < 0)), 0)
    by_forward = [optimal_incentive(**{**EXAMPLE, "pulled_forward": f})["optimal_spend"] for f in (0, 0.2, 0.4)]
    check("optimal spend falls as more extra sales are only pulled forward", 1.0,
          float(np.all(np.diff(by_forward) < 0)), 0)
    return pd.DataFrame(rows)


def resale_cost_per_euro(reg):
    """Resale value lost per euro of price cut, (low, high): the workbook's Prior discounting sheet, per euro.

    Both ends read the car at its 48-month return (`retained_4y_uk`) after a cut of `pl_incentive_pct_list`. The low end
    is ours (`dpt_passthrough`, an upper bound on its own terms); the high end is published (Holweg and Kattuman).
    """
    cut = reg.at["pl_incentive_pct_list", "value"] / 100
    kept = reg.at["retained_4y_uk", "value"] / 100
    low = kept * (1 - (1 - cut) ** reg.at["dpt_passthrough", "value"]) / cut
    per_10pct = (reg.at["hk_passthrough_36m", "value"] + reg.at["hk_passthrough_now", "value"]) / 100
    return low, kept * per_10pct / 0.10


def lerner_check(reg):
    """What each sourced elasticity implies for the margin at a profit-maximising list price, and the reverse.

    One model: margin share = 1 / e. The group, whose extra sales partly come from its own other brands (share k,
    a plain-logit lower bound from its market share): margin share = 1 / (e * (1 - k)).
    """
    k = reg.at["x5_group_share_eu", "value"] / 100
    by_elasticity = pd.DataFrame([{"elasticity": reg.at[i, "label"], "register row": i, "e": abs(reg.at[i, "value"])}
                                  for i in ELASTICITIES])
    by_elasticity["margin it implies, one model (%)"] = (100 / by_elasticity["e"]).round(1)
    by_elasticity["margin it implies, the group (%)"] = (100 / (by_elasticity["e"] * (1 - k))).round(1)
    by_margin = pd.DataFrame([{
        "margin": reg.at[i, "label"], "register row": i, "tier": reg.at[i, "tier"],
        "margin (%)": reg.at[i, "value"], "high end (%)": reg.at[i, "high"],
    } for i in MARGINS])
    by_margin["elasticity it implies, one model"] = (100 / by_margin["margin (%)"]).round(2)
    by_margin["elasticity it implies, the group"] = (100 / (by_margin["margin (%)"] * (1 - k))).round(2)
    return by_elasticity, by_margin, k


def inputs_table(reg, resale):
    def row(symbol, meaning, ids):
        cells = []
        for i in ids:
            lo, hi = reg.at[i, "low"], reg.at[i, "high"]
            span = f" ({lo:g} to {hi:g})" if pd.notna(lo) and pd.notna(hi) else ""
            cells.append(f"`{i}` {reg.at[i, 'value']:g}{span} {reg.at[i, 'tier']}")
        return {"symbol": symbol, "input": meaning, "register rows": "; ".join(cells)}

    table = [
        row("e", "own-price elasticity (model level, then market level)", ELASTICITIES),
        row("m/p", "margin on an extra car, as a share of price", MARGINS),
        row("t", "pass-through: customer rebate, dealer discount", ["rebate_passthrough", "dealer_passthrough_low"]),
        {"symbol": "r", "input": "resale value lost per euro of price cut",
         "register rows": f"{resale[0]:.3f} to {resale[1]:.3f}, from `dpt_passthrough`, `hk_passthrough_36m`, "
                          "`hk_passthrough_now`, `retained_4y_uk`, `pl_incentive_pct_list`"},
        row("g", "share of cars whose resale the group bears", ["finance_penetration"]),
        row("f", "share of extra sales only pulled forward", ["x5_pull_forward"]),
        row("k", "share of extra sales taken from sister brands (plain-logit lower bound)", ["x5_group_share_eu"]),
        row("s/p", "incentive spend today, as a share of list price", ["pl_incentive_pct_list"]),
    ]
    return pd.DataFrame(table)


def targeting_value(*, margin, sensitivities, pass_through, resale_cost=0.0, group_bears=0.0, pulled_forward=0.0,
                    from_sister=0.0, current_spend=0.0):
    """What giving each equal-sized buyer group its own incentive earns over one incentive for all.

    Measured from today, with today's price set to 1: `margin` is the margin on an extra car at today's price and
    `current_spend` today's incentive, both as shares of that price. Today's uniform incentive is taken as the best
    uniform one. That fixes the average buyer's response, so each group needs only its price sensitivity relative to
    the average. Returns the gain per baseline car (a share of price), each group's change in spend, and the closed
    form the gain equals when no group's incentive is taken below zero.
    """
    rel = np.asarray(sensitivities, dtype=float) / np.mean(sensitivities)
    shared = dict(pass_through=pass_through, resale_cost=resale_cost, group_bears=group_bears,
                  pulled_forward=pulled_forward, from_sister=from_sister)
    net = margin - resale_cost * pass_through * group_bears * current_spend
    new = (1 - pulled_forward - from_sister) * net
    average = (1 + resale_cost * pass_through * group_bears) / (pass_through * new)
    groups = [optimal_incentive(price=1, margin=net, elasticity=r * average, floor=-current_spend, **shared)
              for r in rel]
    return {"gain": float(np.mean([g["profit_at_optimum"] for g in groups])),
            "change": [g["optimal_spend"] for g in groups],
            "closed_form": float(new / 4 * np.mean((rel - 1) ** 2 / rel)),
            "average_elasticity": average}


FUELS = ["petrol", "diesel", "electric", "hybrid"]


def quartiles(reg, fuel):
    return [abs(reg.at[f"x5_elast_ch_{fuel}_q{q}", "value"]) for q in range(1, 5)]


def fuel_mix(reg, hybrids_as_petrol=False):
    """2025 shares of the four fuels in the Swiss study, from ACEA's counts ('others' left out)."""
    n = {key: reg.at[f"x5_acea25_{key}", "value"] for key in ["bev", "phev", "hev", "petrol", "diesel"]}
    mix = {"petrol": n["petrol"] + (n["hev"] if hybrids_as_petrol else 0), "diesel": n["diesel"],
           "electric": n["bev"], "hybrid": n["phev"] + (0 if hybrids_as_petrol else n["hev"])}
    return {fuel: count / sum(mix.values()) for fuel, count in mix.items()}


def part4(reg):
    """The targeting value by fuel, across the 2025 mix, one input at a time; the type saving; its checks."""
    resale = resale_cost_per_euro(reg)
    central = dict(margin=reg.at["x5_markup_grv", "value"] / 100,
                   pass_through=reg.at["rebate_passthrough", "value"] / 100, resale_cost=resale[0],
                   group_bears=reg.at["finance_penetration", "value"] / 100,
                   pulled_forward=reg.at["x5_pull_forward", "value"] / 100,
                   from_sister=reg.at["x5_group_share_eu", "value"] / 100,
                   current_spend=reg.at["pl_incentive_pct_list", "value"] / 100)
    revenue = reg.at["eu_revenue_eur_m", "value"]
    workbook_line = (reg.at["targeting_leak_pct", "value"] / 100 * reg.at["incentive_pct_revenue", "value"] / 100
                     * revenue)

    def mix_gain(inputs, hybrids_as_petrol=False):
        mix = fuel_mix(reg, hybrids_as_petrol)
        return sum(mix[f] * targeting_value(sensitivities=quartiles(reg, f), **inputs)["gain"] for f in FUELS)

    mix = fuel_mix(reg)
    by_fuel = []
    for fuel in FUELS:
        sens = quartiles(reg, fuel)
        tv = targeting_value(sensitivities=sens, **central)
        rel = np.array(sens) / np.mean(sens)
        by_fuel.append({"fuel": fuel, **{f"q{q} vs average": round(r, 3) for q, r in enumerate(rel, 1)},
                        "spread": round(float(np.mean((rel - 1) ** 2 / rel)), 4),
                        "q1 spend change (% of price)": round(100 * tv["change"][0], 2),
                        "q4 spend change (% of price)": round(100 * tv["change"][3], 2),
                        "gain (% of revenue)": round(100 * tv["gain"], 4),
                        "2025 share (%)": round(100 * mix[fuel], 1)})
    by_fuel = pd.DataFrame(by_fuel)

    one_at_a_time = [
        ("central", {}, False),
        (f"margin: the group's 2024 gross margin ({reg.at['pl_sale_margin_pct_list', 'high']:g}%)",
         {"margin": reg.at["pl_sale_margin_pct_list", "high"] / 100}, False),
        (f"pull-forward {reg.at['x5_pull_forward', 'low']:g}%",
         {"pulled_forward": reg.at["x5_pull_forward", "low"] / 100}, False),
        (f"pull-forward {reg.at['x5_pull_forward', 'high']:g}%",
         {"pulled_forward": reg.at["x5_pull_forward", "high"] / 100}, False),
        ("no sales taken from sister brands", {"from_sister": 0.0}, False),
        ("all hybrid-electric cars counted as petrol", {}, True),
        (f"pass-through of a dealer discount ({reg.at['dealer_passthrough_low', 'value']:g}%)",
         {"pass_through": reg.at["dealer_passthrough_low", "value"] / 100}, False),
        ("resale cost, high end", {"resale_cost": resale[1]}, False),
        ("the group bears no car's resale (every financed car a loan)", {"group_bears": 0.0}, False),
        (f"today's incentive {reg.at['pl_incentive_pct_list', 'high']:g}% of price",
         {"current_spend": reg.at["pl_incentive_pct_list", "high"] / 100}, False),
    ]
    cases = []
    for name, change, hybrids_as_petrol in one_at_a_time:
        inputs = {**central, **change}
        gain = mix_gain(inputs, hybrids_as_petrol)
        cases.append({"case": name, "gain (% of revenue)": round(100 * gain, 4),
                      "gain (% of today's incentive spend)": round(100 * gain / inputs["current_spend"], 1),
                      "EUR m a year, scale only": round(gain * revenue, 1)})
    cases = pd.DataFrame(cases)
    low, high = cases.iloc[cases["gain (% of revenue)"].idxmin()], cases.iloc[cases["gain (% of revenue)"].idxmax()]
    cases = pd.concat([cases, pd.DataFrame([{**low.to_dict(), "case": "range, low"},
                                            {**high.to_dict(), "case": "range, high"}])], ignore_index=True)

    rebate_lo, rebate_hi = reg.at["rebate_passthrough", "low"], reg.at["rebate_passthrough", "high"]
    dealer_lo, dealer_hi = reg.at["dealer_passthrough_low", "low"], reg.at["dealer_passthrough_low", "high"]
    type_saving = pd.DataFrame([
        {"comparison": "customer rebate instead of dealer discount, low", "saving per euro of dealer discount (%)":
         round(100 * (1 - dealer_hi / rebate_lo), 1)},
        {"comparison": "customer rebate instead of dealer discount, high", "saving per euro of dealer discount (%)":
         round(100 * (1 - dealer_lo / rebate_hi), 1)},
    ])

    rows = []

    def check(name, expected, got, tol):
        rows.append({"check": name, "expected": round(expected, 6), "got": round(got, 6),
                     "passes": abs(got - expected) <= tol})

    petrol = targeting_value(sensitivities=quartiles(reg, "petrol"), **central)
    check("petrol: the four groups solved one by one add up to the closed form", petrol["closed_form"],
          petrol["gain"], 1e-12)
    check("petrol: no group's incentive is taken below zero", 1.0,
          float(min(petrol["change"]) > -central["current_spend"]), 0)
    check("no spread between groups: targeting earns nothing", 0.0,
          targeting_value(sensitivities=[1.9] * 4, **central)["gain"], 1e-15)
    no_resale = {**central, "resale_cost": 0.0}
    check("pass-through cancels: gain at 30% equals gain at 90%",
          targeting_value(sensitivities=quartiles(reg, "petrol"), **{**no_resale, "pass_through": 0.3})["gain"],
          targeting_value(sensitivities=quartiles(reg, "petrol"), **{**no_resale, "pass_through": 0.9})["gain"],
          1e-12)
    no_spend = {**central, "current_spend": 0.0}
    check("resale cost cancels when nothing is spent today: gain at the low end equals the high end",
          targeting_value(sensitivities=quartiles(reg, "petrol"), **no_spend)["gain"],
          targeting_value(sensitivities=quartiles(reg, "petrol"), **{**no_spend, "resale_cost": resale[1]})["gain"],
          1e-12)
    k = central["from_sister"]
    check("gain scales with the share of extra sales new to the group", (1 - 0.5 - k) / (1 - k),
          targeting_value(sensitivities=quartiles(reg, "petrol"), **{**central, "pulled_forward": 0.5})["gain"]
          / targeting_value(sensitivities=quartiles(reg, "petrol"), **{**central, "pulled_forward": 0.0})["gain"],
          1e-12)
    floored = targeting_value(sensitivities=[1, 1, 1, 0.05], **{**central, "current_spend": 0.01})
    check("a group that should get less than nothing is cut to zero incentive, not below", -0.01,
          floored["change"][3], 1e-15)
    check("that cut leaves the gain below the uncut closed form", 1.0,
          float(floored["gain"] < floored["closed_form"]), 0)
    average = optimal_incentive(price=1, margin=central["margin"] - resale[0] * central["pass_through"]
                                * central["group_bears"] * central["current_spend"],
                                elasticity=petrol["average_elasticity"], pass_through=central["pass_through"],
                                resale_cost=resale[0], group_bears=central["group_bears"],
                                pulled_forward=central["pulled_forward"], from_sister=k)
    check("the anchor: today's incentive is the best one for the average buyer (first-euro return 1)", 1.0,
          average["first_euro_return"], 1e-12)
    # The study's Table 5 (PDF p. 26) gives each fuel's all-buyer elasticity; its four quartiles must average to it.
    for fuel, table5 in zip(FUELS, [1.896, 1.867, 1.739, 1.802]):
        check(f"transcription: {fuel} quartiles average to Table 5", table5, float(np.mean(quartiles(reg, fuel))),
              0.0015)
    checks4 = pd.DataFrame(rows)
    assert checks4["passes"].all(), checks4[~checks4["passes"]]

    central_row = cases.iloc[0]
    text = f"""
## Part 4: what targeting is worth, the level, and the type

Part 3, our own natural experiment, is optional and was not run.

### The anchor, and why

Part 2 found that no sourced margin and elasticity agree. That leaves three ways to go on.

- **Take one raw pair.** Then the pair decides the answer. The Swiss elasticity with the 26% margin says no incentive
  pays at all. That is the sources disagreeing, not a finding.
- **Assume the list price is right.** Then every uniform incentive loses money by assumption.
- **Assume today's transaction price is right:** the group's current uniform incentive is its best uniform one. This
  is the assumption structural demand models make, and the 26% margin is derived under it, so the margin and the
  anchor agree by construction. **Part 4 uses this one.**

What the anchor gives, and what it costs:

1. **The level of the incentive can't be judged from public data.** The anchor assumes it is right. If the group
   spends too much on average, that part of the leak is real but not measured here. Only a randomised holdout on the
   incentive's level can measure it.
2. **What targeting is worth can be derived.** Today's incentive fixes the average buyer's response. So each buyer
   group needs only its price sensitivity relative to the average, ρ. The elasticity level and the pass-through then
   cancel, and so does the resale cost, apart from the resale cost of today's incentive, which trims the margin on an
   extra car (checks below). The gain per baseline car is `(1 − f − k)·m/4 × mean((ρ − 1)²/ρ)`, for equal-sized
   groups. The contradiction part 2 found does not reach it.

### What targeting on income is worth, by fuel

Each fuel's buyers are split into income quartiles (quartile 1 is the lowest income), and a targeted policy gives each
quartile its own incentive. "Spread" is `mean((ρ − 1)²/ρ)`. Spend changes are shares of today's price: + means more
than today, − less. Central inputs: margin {100 * central['margin']:g}%,
pull-forward {100 * central['pulled_forward']:g}%, sister brands {100 * k:g}%, today's incentive
{100 * central['current_spend']:g}% of price.

{md_table(by_fuel)}

Income matters for petrol and diesel buyers. For electric cars the order reverses (richer buyers are more
price-sensitive), and for hybrids it hardly matters. The 2025 shares count ACEA's hybrid-electric cars, mild hybrids
included, as hybrids.

### Across the 2025 market, one input at a time

{md_table(cases)}

On Enlarged Europe's net revenue, the central case is EUR {central_row['EUR m a year, scale only']:,.1f}m a year. The
line it replaces in the workbook was EUR {workbook_line:,.1f}m, built from two assumptions (`targeting_leak_pct` ×
`incentive_pct_revenue`). Net revenue includes more than car sales, so the euro figure is a little high.

### What this is, and what it isn't

- **It is targeting on income alone, with income known exactly.** Buyers also differ within a quartile, and the study
  doesn't report that spread, so better data could earn more.
- **It may earn less in practice.** Our uplift test found no model that beat a plain response model at picking out
  buyers. And the group already varies incentives by channel (fleet deals, finance offers), which may track income, so
  part of this gain may already be earned.
- **Swiss buyers of 2017 to 2019.** A quartile's elasticity is a mean over the cars that group chose. If, as in most
  such models, sensitivity scales with the car's price, richer buyers choosing dearer cars narrows the measured gap,
  so the spread at any one car is probably wider.
- **A price personalised by automated decision-making must be disclosed** to the buyer (EU Directive 2019/2161, which
  added point (ea) to Article 6(1) of the Consumer Rights Directive).

### The type of incentive

For the same cut in the buyer's price, a customer rebate costs less than a dealer discount, because more of it reaches
the buyer. The saving per euro of dealer discount, from the two pass-through ranges:

{md_table(type_saving)}

US data (Busse et al.). An upper bound on the saving, because what a dealer keeps may buy selling effort, which this
doesn't value. It is why the ledger must record each incentive's type.

### Checks (part 4)

{md_table(checks4)}
"""
    return text, checks4, cases


def main():
    ex = optimal_incentive(**EXAMPLE)
    table = checks()
    assert table["passes"].all(), table[~table["passes"]]
    e, t, p, m = EXAMPLE["elasticity"], EXAMPLE["pass_through"], EXAMPLE["price"], EXAMPLE["margin"]
    r, g, f, s = EXAMPLE["resale_cost"], EXAMPLE["group_bears"], EXAMPLE["pulled_forward"], EXAMPLE["spend"]
    B, A, slope = 1 + r * t * g, (1 - f) * m, e * t / p
    part1 = f"""# X5: when does an incentive pay?

_Generated by `analysis/optimal_incentive.py`. No data yet: the example uses round illustrative numbers, not
estimates. Part 2 sources the inputs._

## The condition

Take one more euro of incentive on every car. It costs that euro on **every** car sold, including the ones that would
have sold anyway, plus the resale value the group loses because each car was sold cheaper. It earns the margin on the
extra buyers it brings, counting only buyers who are new to the group. Per baseline car:

- cars sold: `q(s) = 1 + e·t·s/p`. Only the part `t·s` that reaches the buyer's price moves the buyer;
- the cost of one euro spent, per car sold: `B = 1 + r·t·g`;
- the margin on an extra car that is new to the group: `A = (1 − f − k)·m`;
- the profit from spending `s`: `profit(s) = (q(s) − 1)·A − q(s)·s·B`.

| symbol | meaning |
|---|---|
| p | price before the incentive |
| m | the group's margin on one extra car |
| e | own-price elasticity: % more cars for a 1% lower price |
| t | pass-through: the share of the spend that reaches the buyer's price. Set by the incentive's type |
| r | resale value lost per euro of price cut, on a car whose resale the group bears |
| g | share of cars whose resale the group bears (leases, buy-backs) |
| f | share of the extra sales only pulled forward from later months |
| k | share of the extra sales taken from the group's own other brands |

`profit(s)` is a quadratic in `s`, so the answer has a closed form:

- **first-euro return** `R = e·t·A / (p·B)`. An incentive pays at all only if `R > 1`;
- **optimal spend** `s* = (A/B − p/(e·t)) / 2` when `R > 1`, and 0 otherwise;
- **profit lost by spending `s`** is `(e·t·B/p)·(s − s*)²` when `s* > 0`. It grows with the square of the overspend.

The response is linear, with the elasticity read at today's price. So it is a local answer, for incentives that are
small against the price. The resale cost is not discounted, although it falls due years later.

## What the condition says before any data

1. **The incentive's type enters twice.** Pass-through `t` sets how many buyers a euro moves. It also sets the resale
   cost, because a car's resale value follows the price it was bought at. A dealer bonus that the dealer keeps does not
   lower that price, so it moves few buyers and carries little resale cost.
2. **If the list price already maximises profit, a uniform incentive cannot pay.** A profit-maximising price
   satisfies `e·m/p = 1` (the Lerner rule). Then `R = t·(1 − f)/B` for a single model, which is at most 1, and
   below 1 once any of the spend stops short of the buyer, any sale is only pulled forward, or any resale cost is
   borne. With sister brands at the same margin, the group's price rule is roughly `e·(1 − k)·m/p = 1`, and the
   conclusion holds. So an incentive earns its place only where it reaches buyers, or moments, that are more
   price-sensitive than the average buyer the list price was set for.
3. **So the leak is not the spend on buyers who would have bought anyway.** That spend is the built-in cost of any
   incentive, and the condition already charges for it. The leak is spend where `R < 1` (its optimum is zero), plus
   spend above `s*` where `R > 1`. The value lost is the profit given up, not the euros spent.
4. **The margin and the elasticity have to agree.** Because of point 2, inputs taken from unrelated sources can decide
   the answer on their own. Part 2 checks the pair against each other.

## A worked example (illustrative numbers)

Price p = {p:,}, margin m = {m:,}, elasticity e = {e}, pass-through t = {t}, resale cost r = {r} per euro, the group
bears resale on g = {g} of cars, f = {f} of extra sales pulled forward, none taken from sister brands (k = 0). Actual
spend s = {s:,} per car. Here e·m/p = {e * m / p}, far above the 1 of an optimal list price: these buyers are much
more price-sensitive than the list price assumes (point 2). That is what lets an incentive pay.

- B = 1 + {r} × {t} × {g} = {B:.2f}. A = (1 − {f}) × {m:,} = {A:,.0f}. Extra cars per euro: {e} × {t} / {p:,} =
  {slope:.4f}.
- R = {slope:.4f} × {A:,.0f} / {B:.2f} = 16/11 = {ex['first_euro_return']:.4f}. Above 1, so some incentive pays.
- s* = ({A:,.0f}/{B:.2f} − {p:,}/({e} × {t})) / 2 = ({A / B:,.2f} − {p / (e * t):,.0f}) / 2 =
  **{ex['optimal_spend']:,.2f}** per car.
- At s*: q = {1 + slope * ex['optimal_spend']:.5f}; profit = {1 + slope * ex['optimal_spend'] - 1:.5f} × {A:,.0f} −
  {1 + slope * ex['optimal_spend']:.5f} × {ex['optimal_spend']:,.2f} × {B:.2f} = **{ex['profit_at_optimum']:,.2f}** per
  baseline car.
- At s = {s:,}: q = {1 + slope * s:.1f}; profit = {slope * s:.1f} × {A:,.0f} − {1 + slope * s:.1f} × {s:,} × {B:.2f} =
  **{ex['profit_at_spend']:,.2f}**. Profit lost: **{ex['profit_lost']:,.2f}** = {slope * B:.5f} ×
  ({s:,} − {ex['optimal_spend']:,.2f})². Spend above the optimum: {s - ex['optimal_spend']:,.2f} ×
  {1 + slope * s:.1f} = {ex['spend_above_optimum']:,.2f}.

So overspending by {s - ex['optimal_spend']:,.0f} a car costs {ex['profit_lost']:,.0f} of profit per baseline car,
not {ex['spend_above_optimum']:,.0f}: part of the extra spend still buys cars.

## Checks (part 1)

"Expected" comes from the hand arithmetic above or from what the check requires; 1 means true.

{md_table(table)}
"""
    reg = pd.read_csv(REGISTER).set_index("id")
    resale = resale_cost_per_euro(reg)
    by_e, by_m, k = lerner_check(reg)
    implied_m = by_e["margin it implies, one model (%)"]
    top_margin = max(by_m["margin (%)"].max(), by_m["high end (%)"].max())
    implied_e = by_m["elasticity it implies, one model"]
    agree = implied_m.min() <= top_margin
    ratio = reg.at["x5_elast_ch_lowinc", "value"] / reg.at["x5_elast_ch_avg", "value"]
    checks2 = pd.DataFrame([
        {"check": "resale cost, low end, matches the workbook's 18 cents per euro", "expected": 18,
         "got": round(resale[0] * 100, 2), "passes": round(resale[0] * 100) == 18},
        {"check": "resale cost, high end, matches the workbook's 47 cents per euro", "expected": 47,
         "got": round(resale[1] * 100, 2), "passes": round(resale[1] * 100) == 47},
    ])
    assert checks2["passes"].all(), checks2
    verdict = ("**At least one sourced pair agrees.**" if agree else
               f"**No sourced pair agrees.** At a profit-maximising list price, the elasticities imply margins of "
               f"{implied_m.min():.0f}% to {implied_m.max():.0f}% for one model. The sourced margins are at most "
               f"{top_margin:g}%. Read the other way, the margins need elasticities of {implied_e.min():.1f} to "
               f"{implied_e.max():.1f}, and no source here measures more than {by_e['e'].max():g}.")
    part2 = f"""
## Part 2: the inputs, from the register

The price drops out: set it to 1 and every euro figure becomes a share of the price. Each input is a row of
`assumptions.csv`, with its source and caveat there.

{md_table(inputs_table(reg, resale))}

The resale cost per euro of price cut, {resale[0]:.3f} to {resale[1]:.3f}, uses the same rows and formula as the
workbook's Prior discounting sheet, so it is the "18 to 47 cents" quoted elsewhere. In the condition it applies only
to the part of the spend that reaches the buyer (`t`), and only on the share `g` of cars whose resale the group bears.
`g` is `finance_penetration`, the disclosed share of the group's new cars its finance arm funds in Europe: a proxy,
not a bound. A loan leaves the resale with the buyer, while buy-back sales and Leasys, outside that share, leave it with
the group. The one-at-a-time table shows `g` at zero.

### The Lerner check: do the margin and the elasticity agree?

A list price that maximises profit satisfies `e·m/p = 1` for one model, and `e·(1 − k)·m/p = 1` for the group, whose
extra sales partly come from its own other brands (k = {k:.3f}, from `x5_group_share_eu`).

{md_table(by_e)}

{md_table(by_m)}

{verdict}

So at least one of three things is true, and these sources can't say which:

1. the Swiss elasticities are too low for the group's market (Switzerland, 2017-2019 buyers);
2. list prices are not set to maximise profit on the average buyer (for example because of CO2 fleet targets or
   dealer volume targets);
3. the margins understate the margin on an extra car.

A bias that the study shares across all its buyers cancels in the ratio between them: the lowest income quartile is
{ratio:.3f} times as price-sensitive as the average buyer, in the same study and model. Part 4 builds on those ratios,
using every quartile.

### Checks (part 2)

{md_table(checks2)}
"""
    text4, checks4, cases = part4(reg)
    OUT.write_text(part1 + part2 + text4)
    print(md_table(table))
    print(md_table(checks2))
    print(md_table(by_e))
    print(md_table(by_m))
    print(md_table(checks4))
    print(md_table(cases))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
