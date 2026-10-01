"""X6 part 1: what the market level costs a residual, per euro, over the life of a contract.

A residual set today assumes a market level at the contract's end. If the level turns out lower, the lessor loses the
difference on every car that comes back. Priced on the historical distribution, the fair charge is the expected
shortfall, E[max(0, assumed - realised)], per euro of residual.

Same panel as `level_risk.py`: Eurostat HICP second-hand car indices, the EU markets with every month of the common
window, each market weighted equally (all its overlapping windows), and the group's largest markets apart. The index
holds a car's age constant (HICP manual, section 12.3.6.3), so its move is the level, not depreciation.

Two assumptions for the residual:
  no change  the level at return equals today's. When the level has been rising, this leaves a cushion.
  median     the level moves by the median move over the same horizon: right on average, with no cushion. A guide
             that forecasts better than the drift does better (skeptic B5; X7 tests it), so for one that does, this
             is an upper bound.

For each, at 12 to 60 months: the expected shortfall (the fair premium), the chance of any shortfall, and the average
shortfall in the worst tenth of windows. Overlapping windows share months and markets share shocks, so the effective
sample is far smaller than the window count; the report shows both.

Part 2 turns the share into euros: the residual at the contract's end (price x value retained), times the expected
shortfall, and the level monthly charge that, set aside at the ECB deposit rate, covers it when the car comes back.

Part 3 adds what holding the risk costs: the capital CRR Article 134(7) ties to a leased car's residual, charged at
the banks' cost of equity, and a Black-Scholes put on the index as a cross-check. It then sets both beside the
published benchmarks: a modelled insurance premium and rating agencies' residual haircuts.

Part 4 back-tests the charge: in sample, vintage by vintage, and out of sample on each core market's full history,
with each vintage's charge set only from windows that had already ended. The group's own disclosure is not a
back-test: its "decrease in value" on buy-back cars is scheduled depreciation, not a loss.

Part 5 asks whether the charge should move with the level. The signal is how far the level sits above its own
average of the previous 36 months when a contract starts. A charge that rises with it is fitted on all other markets
and scored on the one left out, against the flat charge; a placebo shifts each market's signal in time.

Usage: .venv/bin/python analysis/level_charge.py   (writes analysis/level_charge_report.md)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from build_unified import md_table  # noqa: E402
from level_risk import COMMON_END, COMMON_START, CORE, EUROPE, EUROSTAT, load, moves, pooled  # noqa: E402

OUT = HERE / "level_charge_report.md"
REGISTER = HERE.parent / "assumptions.csv"
HORIZONS = (12, 24, 36, 48, 60)


def shortfall(move, assumed=0.0):
    """Per euro of residual: what is lost when the level ends below what the residual assumed. Fractions."""
    return np.maximum(0.0, (assumed - np.asarray(move, dtype=float)) / (1 + assumed))


def charge(move, strike="no change"):
    """The expected shortfall, the chance of any, and the average in the worst tenth of windows."""
    move = np.asarray(move, dtype=float)
    assumed = 0.0 if strike == "no change" else float(np.median(move))
    loss = shortfall(move, assumed)
    worst = np.sort(move)[: int(np.ceil(0.1 * len(move)))]
    return {"assumed": assumed, "expected": float(loss.mean()), "chance": float((loss > 0).mean()),
            "worst_tenth": float(shortfall(worst, assumed).mean())}


def monthly(loss, months, rate=0.0):
    """The level monthly charge that, set aside each month end at `rate` a year, covers `loss` at the end."""
    if rate == 0:
        return loss / months
    j = (1 + rate) ** (1 / 12) - 1
    return loss * j / ((1 + j) ** months - 1)


def capital_cost(residual, months, ratio, spread):
    """What the capital CRR 134(7) ties to one residual costs over the contract.

    Each month the risk-weighted amount is residual / t, with t the greater of 1 and the whole years left, to the
    nearest year. The capital is `ratio` of that, charged at `spread` a year.
    """
    total = 0.0
    for m in range(months):
        t = max(1, int((months - m) / 12 + 0.5))
        total += ratio * residual / t * spread / 12
    return total


def put_value(sigma, rate, years):
    """Black-Scholes value, per unit of strike, of a put struck at the forward: e^(-rT) x (2N(sigma/2) - 1).

    `sigma` is the standard deviation of the log move over the whole horizon, so no square-root-of-time scaling is
    applied: the index's moves are autocorrelated, and the horizon's own dispersion already carries that.
    """
    return np.exp(-rate * years) * (2 * norm.cdf(sigma / 2) - 1)


def common_panel():
    """The markets with every month of the common window, as `level_risk.py` selects them."""
    euro = {g: s for (series, g), s in load().items() if series == EUROSTAT and g in EUROPE}
    months = len(pd.period_range(COMMON_START, COMMON_END, freq="M"))
    common = {}
    for g, s in euro.items():
        w = s[(s.index >= COMMON_START) & (s.index <= COMMON_END)]
        if len(w) == months:
            common[g] = w
    return common, [g for g in CORE if g in common], months


def effective_sample(panel, geos, k, months):
    """Non-overlapping windows, shrunk for markets moving together: N / (1 + (N - 1) x mean pairwise correlation)."""
    table = pd.DataFrame({g: moves(panel[g], k) for g in geos})
    corr = table.corr().to_numpy()
    rho = float(corr[np.triu_indices(len(geos), 1)].mean())
    per_market = (months - 1) // k
    return per_market, rho, per_market * len(geos) / (1 + (len(geos) - 1) * rho)


def checks(by_set):
    rows = []

    def check(name, expected, got, tol):
        rows.append({"check": name, "expected": round(expected, 6), "got": round(got, 6),
                     "passes": abs(got - expected) <= tol})

    toy = [-0.2, -0.1, 0.0, 0.1, 0.2]
    c = charge(toy)
    check("toy, no change: expected shortfall (0.2 + 0.1) / 5", 0.06, c["expected"], 1e-12)
    check("toy, no change: chance of a shortfall, 2 of 5", 0.4, c["chance"], 1e-12)
    check("toy, no change: worst tenth is the one worst window, -20%", 0.2, c["worst_tenth"], 1e-12)
    drift = [-0.1, 0.0, 0.1, 0.2, 0.3]
    check("toy with drift, median strike: (0.2 + 0.1) / 1.1 / 5", 0.3 / 1.1 / 5, charge(drift, "median")["expected"],
          1e-12)
    check("toy with drift, no change: 0.1 / 5", 0.02, charge(drift)["expected"], 1e-12)

    reg = pd.read_csv(REGISTER).set_index("id")["value"]
    for row, (label, k, q) in {"level_1y_p10": ("all", 12, 10), "level_1y_p10_core": ("core", 12, 10),
                               "level_3y_p10": ("all", 36, 10), "level_3y_p10_core": ("core", 36, 10),
                               "level_3y_p50": ("all", 36, 50)}.items():
        check(f"same panel as level_risk.py: p{q} of {k}-month moves, {label}, reproduces `{row}`",
              float(reg[row]), round(float(np.percentile(by_set[label][k], q)) * 100, 1), 1e-9)
    return pd.DataFrame(rows)


def part2(by_set, n_markets):
    """Euros per contract and per month, for a group-typical car and the sample Corsa."""
    reg = pd.read_csv(REGISTER).set_index("id")
    rate = reg.at["ecb_deposit_rate", "value"] / 100
    group_price = reg.at["eu_revenue_eur_m", "value"] * 1e6 / reg.at["eu_shipments", "value"]
    corsa_price = reg.at["new_car_price_eur", "value"]
    kept = {36: reg.at["retained_3y_uk", "value"] / 100, 48: reg.at["retained_4y_uk", "value"] / 100}

    rows = []
    for car, price in (("group car", group_price), ("Corsa", corsa_price)):
        for k in (36, 48):
            for strike in ("median", "no change"):
                sets = ["core", "all"] if (car, k, strike) == ("group car", 48, "median") else ["core"]
                for label in sets:
                    c = charge(by_set[label][k], strike)
                    residual = price * kept[k]
                    loss = residual * c["expected"]
                    name = f"{car}, {k} months, {strike}" + (f", all {n_markets} markets" if label == "all" else "")
                    rows.append({"case": name, "residual (EUR)": round(residual),
                                 "expected shortfall (% of residual)": round(100 * c["expected"], 2),
                                 "expected loss per contract (EUR)": round(loss),
                                 "per month, undiscounted (EUR)": round(loss / k, 2),
                                 "per month at the ECB rate (EUR)": round(monthly(loss, k, rate), 2),
                                 "worst tenth per contract (EUR)": round(residual * c["worst_tenth"])})
    table = pd.DataFrame(rows)

    out = []

    def check(name, expected, got, tol):
        out.append({"check": name, "expected": round(expected, 6), "got": round(got, 6),
                    "passes": abs(got - expected) <= tol})

    corsa4 = corsa_price * kept[48]
    # Solution doc 6.6: a EUR 7,062 residual, EUR 544 at the core p10 fall and EUR 1,907 at the worst fall on record.
    check("the Corsa's residual (list x value retained at 4 years) is the solution doc's EUR 7,062", 7062,
          round(corsa4), 0)
    check("x the core-market p10 three-year fall gives the doc's EUR 544", 544,
          round(corsa4 * abs(reg.at["level_3y_p10_core", "value"]) / 100), 0)
    check("x the worst three-year fall gives the doc's EUR 1,907", 1907,
          round(corsa4 * abs(reg.at["level_3y_worst", "value"]) / 100), 0)
    check("monthly charge at a 0% rate is the loss spread evenly: 1,000 / 12", 1000 / 12, monthly(1000, 12), 1e-12)
    c = monthly(1000, 48, rate)
    balance = 0.0
    for _ in range(48):
        balance = balance * (1 + rate) ** (1 / 12) + c
    check("the ECB-rate charge, set aside each month for 48 months, grows back to the 1,000 due", 1000, balance, 1e-9)
    check("setting it aside at a positive rate costs less a month than spreading it evenly", 1.0,
          float(c < 1000 / 48), 0)
    checks2 = pd.DataFrame(out)
    assert checks2["passes"].all(), checks2[~checks2["passes"]]

    text = f"""
## Part 2: euros per contract and per month

The residual is the car's price times the share of list it keeps at the contract's end (`retained_3y_uk`,
`retained_4y_uk`). The expected loss per contract is that residual times part 1's expected shortfall, over the group's
core markets. It falls due when the car comes back. The monthly charge is the level amount that, set aside at each
month end at the ECB deposit rate (`ecb_deposit_rate`, {100 * rate:g}%), covers it then.

- **Group car:** Enlarged Europe's net revenue per vehicle, EUR {group_price:,.0f} (`eu_revenue_eur_m` /
  `eu_shipments`). It is a scale, not a list price: net revenue is after incentives and includes more than car sales.
- **Corsa:** the solution doc's sample car, list EUR {corsa_price:,.0f} (`new_car_price_eur`), the entry trim.

"Worst tenth" is the average loss in the worst 10% of windows. It is not a charge: it is what a bad decile costs one
contract, a guide to what the group must be able to absorb.

{md_table(table)}

**Read the median rows.** They price a residual that is right on average. The no-change rows show what the decade's
rising level did for a residual set at today's level.

### What it is and isn't

- **It is the expected loss, not a price.** Holding the risk also ties up capital, and part 3 adds its cost.
- **The same caveats as part 1:** a handful of independent episodes, one decade that includes the 2021–22 shortage,
  and retail index prices rather than auction prices.
- **The value retained is the UK's (2018 adverts, entry trim)**, the curve the workbook uses. Shares of list are
  flattered by the entry trim.

### Checks (part 2)

{md_table(checks2)}
"""
    return text, table, checks2


def part3(by_set):
    """The price of holding the risk: expected loss plus the cost of capital, an option cross-check, benchmarks."""
    reg = pd.read_csv(REGISTER).set_index("id")
    rate = reg.at["ecb_deposit_rate", "value"] / 100
    group_price = reg.at["eu_revenue_eur_m", "value"] * 1e6 / reg.at["eu_shipments", "value"]
    kept = {36: reg.at["retained_3y_uk", "value"] / 100, 48: reg.at["retained_4y_uk", "value"] / 100}
    minimum = reg.at["crr_total_capital_ratio", "value"] / 100
    ratio = minimum + reg.at["crd_conservation_buffer", "value"] / 100
    coe_lo, coe_hi = reg.at["eba_bank_coe", "low"] / 100, reg.at["eba_bank_coe", "high"] / 100
    central_spread = coe_lo - rate

    rows = []
    for k in (36, 48):
        residual = group_price * kept[k]
        loss = residual * charge(by_set["core"][k], "median")["expected"]
        cap = capital_cost(residual, k, ratio, central_spread)
        rows.append({"case": f"group car, {k} months", "residual (EUR)": round(residual),
                     "expected loss (EUR)": round(loss), "capital cost (EUR)": round(cap),
                     "price to hold it (EUR)": round(loss + cap),
                     "price per month, undiscounted (EUR)": round((loss + cap) / k, 2),
                     "price (% of residual)": round(100 * (loss + cap) / residual, 2)})
    table = pd.DataFrame(rows)

    residual48 = group_price * kept[48]
    capital = pd.DataFrame([
        {"capital basis": name, "ratio (%)": round(100 * r, 1), "charged at (%)": round(100 * sp, 1),
         "capital cost per contract (EUR)": round(capital_cost(residual48, 48, r, sp)),
         "per month (EUR)": round(capital_cost(residual48, 48, r, sp) / 48, 2)}
        for name, r, sp in [
            ("minimum, net of the ECB rate", minimum, coe_lo - rate),
            ("with the conservation buffer, net of the ECB rate (central)", ratio, coe_lo - rate),
            ("with the buffer, the bracket's high end, net", ratio, coe_hi - rate),
            ("with the buffer, the high end, gross", ratio, coe_hi)]])

    option = []
    for k in (36, 48):
        logs = np.log1p(by_set["core"][k])
        sigma = float(logs.std())
        option.append({"months": k, "dispersion of the log move": round(sigma, 4),
                       "Black-Scholes put, undiscounted (% of residual)": round(100 * put_value(sigma, 0, k / 12), 2),
                       "historical expected shortfall, median strike (%)": round(
                           100 * charge(by_set["core"][k], "median")["expected"], 2)})
    option = pd.DataFrame(option)

    worst_core = 100 * charge(by_set["core"][48], "median")["worst_tenth"]
    worst_all = 100 * charge(by_set["all"][48], "median")["worst_tenth"]
    bench = pd.DataFrame([
        {"benchmark": reg.at[i, "label"], "register row": i, "value (%)": reg.at[i, "value"]}
        for i in ["gh_rv_premium_low", "gh_rv_premium_high", "sp_eu_rv_haircut_bbb", "sp_eu_rv_haircut_aaa",
                  "dbrs_sfse_rv_loss_bbbh", "dbrs_sfse_rv_loss_aa"]])

    out = []

    def check(name, expected, got, tol):
        out.append({"check": name, "expected": round(expected, 6), "got": round(got, 6),
                    "passes": abs(got - expected) <= tol})

    check("capital, 12-month contract: the whole residual is weighted all year, 10,000 x 10% x 10%", 100.0,
          capital_cost(10_000, 12, 0.10, 0.10), 1e-9)
    # 48 months: 7 months with 4 years left (to the nearest), 12 with 3, 12 with 2 and 17 with 1.
    check("capital, 48-month contract: 7/4 + 12/3 + 12/2 + 17/1 = 28.75 month-units of the residual",
          10_000 * 0.10 * 0.10 / 12 * 28.75, capital_cost(10_000, 48, 0.10, 0.10), 1e-9)
    rng = np.random.default_rng(7)
    sigma = float(option.loc[option["months"] == 48, "dispersion of the log move"].iloc[0])
    draws = np.exp(sigma * rng.standard_normal(1_000_000) - sigma ** 2 / 2)
    payoff = np.maximum(0.0, 1 - draws)
    check("Black-Scholes put against a million simulated moves (within 3 standard errors)",
          put_value(sigma, 0, 4), float(payoff.mean()), 3 * float(payoff.std()) / 1000)
    check("a put is worth less than its strike", 1.0, float(put_value(0.5, rate, 4) < 1), 0)
    check("a put gains value as dispersion rises", 1.0, float(put_value(0.3, 0, 4) > put_value(0.2, 0, 4)), 0)
    check("holding the risk costs more than its expected loss", 1.0,
          float((table["price to hold it (EUR)"] > table["expected loss (EUR)"]).all()), 0)
    checks3 = pd.DataFrame(out)
    assert checks3["passes"].all(), checks3[~checks3["passes"]]

    share48 = float(table.loc[table["case"] == "group car, 48 months", "price (% of residual)"].iloc[0])
    el48 = 100 * charge(by_set["core"][48], "median")["expected"]
    # The prose below states these comparisons; fail loudly if a re-run ever reverses one.
    assert reg.at["gh_rv_premium_high", "value"] < el48
    assert abs(worst_core - reg.at["sp_eu_rv_haircut_bbb", "value"]) < 5
    higher = (option["Black-Scholes put, undiscounted (% of residual)"]
              > option["historical expected shortfall, median strike (%)"])
    tail = ("The option price is higher at both horizons: more of the decade's dispersion lies above the median than "
            "below it (the shortage years), and a lognormal model spreads it evenly, so it overstates the downside."
            if higher.all() else
            "The option price is lower at both horizons: the historical left tail is heavier than a lognormal model "
            "allows." if (~higher).all() else
            "The two cross at different horizons, so the historical distribution is not lognormal.")
    text = f"""
## Part 3: the price of holding it

### Expected loss plus the cost of capital

A bank that leases the car holds capital against its residual. CRR Article 134(7) weights a residual at
`residual / t`, where t is the greater of 1 and the whole years of the lease left (`crr_residual_rwea_rule`). So the
weight rises as the contract runs down: 1/4, 1/3, 1/2, then the whole residual in the last year of a 48-month lease.
The capital is the 8% minimum (`crr_total_capital_ratio`) plus the 2.5% conservation buffer
(`crd_conservation_buffer`), {100 * ratio:g}% of that weight. It is charged at the banks' cost of equity, net of the
ECB deposit rate the capital itself earns: {100 * coe_lo:g}%, the low end of the most common bracket in the EBA's
survey (`eba_bank_coe`), less {100 * rate:g}%.

{md_table(table)}

The capital cost under other bases, 48-month contract, group car:

{md_table(capital)}

This applies to a bank's leases. The manufacturer's own buy-back book sits outside bank capital rules, so there the
cost of holding is the group's own cost of equity on whatever buffer it keeps.

### An option price, as a cross-check

A Black-Scholes put struck at the forward, on the dispersion of the core markets' log moves over the whole horizon,
set beside part 1's historical expected shortfall for a residual that is right on average. No market exists in which
to hedge the level, so no one can trade at this price. It is a check on part 1, not a price.

{md_table(option)}

{tail}

### Against the published benchmarks

{md_table(bench)}

- **The modelled insurance premium is below our expected loss alone** ({el48:.2f}% of the residual at 48 months).
  Goldberg and Hegde's fair premium is
  {reg.at['gh_rv_premium_low', 'value']:g}–{reg.at['gh_rv_premium_high', 'value']:g}% of the insured value. Holding the
  risk costs {share48:g}% of the residual here, including capital. Their premium comes from US wholesale prices of
  1990–2006. The same paper finds realised losses of 7–12%, driven by residuals set too high, and warns that insurers
  would have lost heavily. The lesson for the ledger is that the risk that sank those lessors was where the
  residual was set, not the market's volatility.
- **The rating agencies' stresses sit close to our worst tenth.** Our average loss in the worst tenth of 48-month
  windows is {worst_core:.1f}% of the residual in the core markets ({worst_all:.1f}% across all markets).
  S&P's BBB haircut for a typical European deal is {reg.at['sp_eu_rv_haircut_bbb', 'value']:g}%, and DBRS's BBB (high)
  estimate on the group's own Spanish deal is {reg.at['dbrs_sfse_rv_loss_bbbh', 'value']:g}%. A rating stress is
  meant to be rarer than one year in ten. So either the decade's tail is heavy, or the agencies' base residuals already
  carry a cushion.
- **Make or buy can't be settled from public prices.** No European residual-value insurance price is published. What
  the ledger can do is put an insurer's quote beside this model's price to hold, contract by contract.

### Checks (part 3)

{md_table(checks3)}
"""
    return text, table, checks3


def windows(series, k):
    """Every k-month window of one market: start month, move (fraction)."""
    v = series.to_numpy(dtype=float)
    return pd.DataFrame({"start": series.index[:-k], "move": v[k:] / v[:-k] - 1})


def in_sample(panel, geos, k, strike):
    """The full-sample flat charge against each start year's realised shortfall, the same markets and window."""
    pooled_moves = pooled(panel, geos, k) / 100
    c = charge(pooled_moves, strike)
    rows = []
    for g in geos:
        w = windows(panel[g], k)
        w["realised"] = shortfall(w["move"], c["assumed"])
        w["charge"] = c["expected"]
        w["market"] = g
        rows.append(w)
    return pd.concat(rows)


def out_of_sample(series_by_geo, geos, k, min_past=24):
    """Each market's own full history: at each start month, the median-strike charge from windows already ended."""
    rows = []
    for g in geos:
        w = windows(series_by_geo[g], k)
        moves_ = w["move"].to_numpy()
        for i in range(len(w)):
            past = moves_[: max(0, i - k + 1)]  # windows starting at j end at j + k, on or before start i
            if len(past) < min_past:
                continue
            assumed = float(np.median(past))
            rows.append({"market": g, "start": w["start"].iloc[i], "last past start": w["start"].iloc[i - k],
                         "charge": float(shortfall(past, assumed).mean()),
                         "realised": float(shortfall(moves_[i], assumed))})
    return pd.DataFrame(rows)


def by_vintage(frame):
    frame = frame.assign(year=frame["start"].astype(str).str[:4])
    g = frame.groupby("year").agg(contracts=("realised", "size"), markets=("market", "nunique"),
                                  charge=("charge", "sum"), realised=("realised", "sum")).reset_index()
    g["coverage"] = ["no shortfall" if r == 0 else "above 10" if c / r > 10 else f"{c / r:.2f}"
                     for c, r in zip(g["charge"], g["realised"])]
    g["ratio"] = [c / r if r > 0 else np.inf for c, r in zip(g["charge"], g["realised"])]
    g["charge (% of residual, mean)"] = (100 * g["charge"] / g["contracts"]).round(2)
    g["realised (% of residual, mean)"] = (100 * g["realised"] / g["contracts"]).round(2)
    return g[["year", "markets", "contracts", "charge (% of residual, mean)", "realised (% of residual, mean)",
              "coverage", "ratio"]]


def part4(panel, core, by_set):
    """Back-tests of the median-strike charge, and what the group's own buy-back disclosure can and can't say."""
    reg = pd.read_csv(REGISTER).set_index("id")
    full = {g: s for (series, g), s in load().items() if series == EUROSTAT and g in core}

    sections, summary = [], []
    for k in (36, 48):
        ins = in_sample(panel, core, k, "median")
        oos = out_of_sample(full, core, k)
        sections.append((k, by_vintage(ins), by_vintage(oos), oos))
        for name, frame in (("in sample", ins), ("out of sample", oos)):
            summary.append({"test": f"{k} months, {name}", "contracts": len(frame),
                            "first start": str(frame["start"].min()), "last start": str(frame["start"].max()),
                            "coverage over all vintages": round(frame["charge"].sum() / frame["realised"].sum(), 2)})
    summary = pd.DataFrame(summary)

    depreciation = 100 - reg.at["retained_1y_pooled", "value"]
    group = pd.DataFrame([
        {"year": y, "decrease in value (EUR m)": reg.at[f"buyback_value_decrease_{y}_eur_m", "value"],
         "buy-back assets at year end (EUR m)": reg.at[a, "value"] if a else "",
         "decrease / assets (%)": round(100 * reg.at[f"buyback_value_decrease_{y}_eur_m", "value"]
                                        / reg.at[a, "value"], 1) if a else ""}
        for y, a in ((2023, None), (2024, "buyback_assets_2024_eur_m"), (2025, "buyback_assets_eur_m"))])

    out = []

    def check(name, expected, got, tol):
        out.append({"check": name, "expected": round(expected, 6), "got": round(got, 6),
                    "passes": abs(got - expected) <= tol})

    for k, _, _, oos in sections:
        ins = in_sample(panel, core, k, "median")
        check(f"{k} months, in sample: the flat charge covers exactly the losses summed over all vintages", 1.0,
              ins["charge"].sum() / ins["realised"].sum(), 1e-9)
        look_ahead = (pd.PeriodIndex(oos["last past start"], freq="M") + k > pd.PeriodIndex(oos["start"], freq="M")).sum()
        check(f"{k} months, out of sample: no charge uses a window that had not ended", 0, float(look_ahead), 0)
    toy = pd.Series([100.0, 100, 100, 90, 110], index=pd.period_range("2020-01", periods=5, freq="M").astype(str))
    w = windows(toy, 2)
    check("toy windows of 2 months: moves 0%, -10%, +10%", 0.0, float(np.abs(w["move"].to_numpy()
          - np.array([0.0, -0.1, 0.1])).max()), 1e-12)
    check("the 2025 decrease is 9.9% of year-end buy-back assets (358 / 3,616)", 358 / 3616 * 100,
          float(group.loc[group["year"] == 2025, "decrease / assets (%)"].iloc[0]), 0.05)
    checks4 = pd.DataFrame(out)
    assert checks4["passes"].all(), checks4[~checks4["passes"]]

    k48 = next(x for x in sections if x[0] == 48)
    oos48, ins48 = k48[2], k48[1]
    early = oos48[oos48["year"].astype(int) <= 2014]
    early_markets = set(k48[3].loc[k48[3]["start"].astype(str).str[:4].astype(int) <= 2014, "market"])
    assert early_markets == {"FR"}, early_markets  # the sentence below says the early test is France alone
    short = int((early["ratio"] < 0.5).sum())
    cov = {row["test"]: row["coverage over all vintages"] for _, row in summary.iterrows()}
    lossy = ins48[np.isfinite(ins48["ratio"])]
    verdict = f"""**What the back-tests say.**

- **Out of sample, a charge set from the past fell short for years at a time.** Over all vintages it covered
  {cov['36 months, out of sample']:g} of the realised shortfall on 36-month contracts and
  {cov['48 months, out of sample']:g} on 48-month ones. Until 2014 the test is one market, France, where the charge
  was below half the realised shortfall in {short} of {len(early)} start years from {early['year'].min()} to 2014.
  The residual assumed the past median drift would continue; the level then rose more slowly than that, or fell.
  The later vintages, which came back
  into the 2021–22 shortage, had almost no shortfall and flatter the totals.
- **In sample, the start year matters more than the average.** For 48-month contracts, coverage ran from
  {lossy['ratio'].min():.2f} (start year {lossy.loc[lossy['ratio'].idxmin(), 'year']}) to
  {lossy['ratio'].max():.2f} (start year {lossy.loc[lossy['ratio'].idxmax(), 'year']}).
- **So a flat charge is not enough on its own.** It needs the monthly re-mark, capital for the years it falls short,
  and a residual that does not build in the past drift."""

    blocks = []
    for k, ins_t, oos_t, oos in sections:
        ins_t, oos_t = ins_t.drop(columns="ratio"), oos_t.drop(columns="ratio")
        spans = oos.groupby("market")["start"].agg(["min", "max"]).reset_index()
        spans.columns = ["market", "first start", "last start"]
        blocks.append(f"""### {k}-month contracts

In sample, by start year (core markets, {COMMON_START} to {COMMON_END}):

{md_table(ins_t)}

Out of sample, by start year (each market's own history; which years each market covers is below):

{md_table(oos_t)}

{md_table(spans)}
""")

    text = f"""
## Part 4: would the charge have covered the losses?

Two back-tests of the median-strike charge, per euro of residual. **In sample** uses the flat charge from parts 1 and
2 on every contract in the common window, and asks which start years lost more than it. Over all vintages it covers
the losses exactly, by construction; the point is the spread between years. **Out of sample** sets each contract's
charge from its own market's history only, using windows that had already ended when the contract started (at least
24 of them), with the residual at that history's median move. That is what a lessor could have charged at the time.
"Coverage" is the charge collected over the shortfall realised: below 1, the charge fell short.

{md_table(summary)}

{verdict}

{chr(10).join(blocks)}
### The group's own disclosure is not a back-test

The 20-F reports a "decrease in value" on cars sold with a buy-back commitment. Its accounting policy says what that
is: "the difference between the cost of the vehicle and the estimated net residual value is recognized within Cost of
revenues ... over the contractual term". That is scheduled depreciation to an expected residual, not a loss against
it. As a share of year-end buy-back assets it matches a year of ordinary depreciation (1 minus `retained_1y_pooled`,
{depreciation:.1f}%):

{md_table(group)}

The group discloses no gains or losses at disposal for this book, so no public figure can back-test the level charge
against the group's own results. That is what the ledger would record: each car's sale price against its residual.

### Checks (part 4)

{md_table(checks4)}
"""
    return text, summary, checks4


LOOKBACK = 36


def signal_windows(series, k, lookback=LOOKBACK):
    """Per start month: the level's log gap above its average log over the previous `lookback` months, and the
    k-month move that followed (a fraction)."""
    logs = np.log(series.to_numpy(dtype=float))
    idx = np.arange(lookback, len(logs) - k)
    gap = np.array([logs[i] - logs[i - lookback:i].mean() for i in idx])
    move = np.exp(logs[idx + k] - logs[idx]) - 1
    return pd.DataFrame({"start": series.index[idx], "gap": gap, "move": move})


def slope(x, y):
    x, y = np.asarray(x), np.asarray(y)
    return float(((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum())


def leave_one_out(frames, k):
    """For each market left out: fit charge = a + b x gap on the others (median strike from their moves), and
    predict its windows' shortfall with it and with the flat charge from the same markets."""
    rows = []
    for held in frames:
        train = pd.concat([f for g, f in frames.items() if g != held])
        test = frames[held]
        assumed = float(np.median(train["move"]))
        s_train = shortfall(train["move"], assumed)
        b = slope(train["gap"], s_train)
        a = float(s_train.mean() - b * train["gap"].mean())
        rows.append(pd.DataFrame({"market": held, "start": test["start"].to_numpy(),
                                  "realised": shortfall(test["move"], assumed),
                                  "moving": np.maximum(0.0, a + b * test["gap"].to_numpy()),
                                  "flat": float(s_train.mean())}))
    return pd.concat(rows)


def placebo(frames, k, n=1000, seed=11):
    """Pooled slope of shortfall on gap with each market's gap shifted in time by a random offset of at least k."""
    rng = np.random.default_rng(seed)
    pooled_moves = np.concatenate([f["move"].to_numpy() for f in frames.values()])
    assumed = float(np.median(pooled_moves))
    s = shortfall(pooled_moves, assumed)
    gaps = [f["gap"].to_numpy() for f in frames.values()]
    out = []
    for _ in range(n):
        shifted = []
        for g in gaps:
            lo, hi = k, len(g) - k
            shifted.append(np.roll(g, rng.integers(lo, hi)) if hi > lo else rng.permutation(g))
        out.append(slope(np.concatenate(shifted), s))
    return np.array(out), slope(np.concatenate(gaps), s)


def part5():
    """Should the charge move with the level? Leave-one-market-out against the flat charge, and a placebo."""
    full = {g: s for (series, g), s in load().items() if series == EUROSTAT and g in EUROPE}
    results, terciles, summaries = [], [], {}
    for k in (36, 48):
        frames = {g: signal_windows(s, k) for g, s in full.items()}
        frames = {g: f for g, f in frames.items() if len(f) >= 24}
        lomo = leave_one_out(frames, k)
        placebos, actual = placebo(frames, k)
        sq = lomo.assign(moving=(lomo["realised"] - lomo["moving"]) ** 2, flat=(lomo["realised"] - lomo["flat"]) ** 2)
        per_market = sq.groupby("market")[["moving", "flat"]].sum()
        gain = 1 - sq["moving"].sum() / sq["flat"].sum()
        peak = sq[sq["start"].astype(str).str[:4].isin(["2021", "2022"])]
        peak_gain = 1 - peak["moving"].sum() / peak["flat"].sum() if len(peak) else np.nan
        pooled_f = pd.concat(frames.values())
        assumed = float(np.median(pooled_f["move"]))
        pooled_f = pooled_f.assign(shortfall=shortfall(pooled_f["move"], assumed))
        cuts = np.quantile(pooled_f["gap"], [1 / 3, 2 / 3])
        for name, lo, hi in (("cold", -np.inf, cuts[0]), ("middle", cuts[0], cuts[1]), ("hot", cuts[1], np.inf)):
            part = pooled_f[(pooled_f["gap"] > lo) & (pooled_f["gap"] <= hi)]
            terciles.append({"level at the start": f"{k} months, {name}",
                             "gap above its 36-month average (%)": (
                                 f"up to {100 * np.expm1(hi):+.1f}" if name == "cold" else
                                 f"above {100 * np.expm1(lo):+.1f}" if name == "hot" else
                                 f"{100 * np.expm1(lo):+.1f} to {100 * np.expm1(hi):+.1f}"),
                             "windows": len(part),
                             "expected shortfall (% of residual)": round(100 * float(part["shortfall"].mean()), 2),
                             "worst tenth (%)": round(100 * float(np.sort(part["shortfall"].to_numpy())[::-1][
                                 : int(np.ceil(0.1 * len(part)))].mean()), 2)})
        results.append({"test": f"{k} months", "markets": len(frames), "windows": len(pooled_f),
                        "pooled slope of shortfall on gap": round(actual, 3),
                        "placebo p, two-sided": round(float((np.abs(placebos) >= abs(actual)).mean()), 3),
                        "markets where the moving charge errs less": f"{int((per_market['moving'] < per_market['flat']).sum())} of {len(per_market)}",
                        "error saved by the moving charge, left-out markets (%)": round(100 * gain, 1),
                        "the same, contracts started 2021-22 (%)": round(100 * peak_gain, 1) if np.isfinite(peak_gain) else "none"})
        summaries[k] = (lomo, frames)
    table = pd.DataFrame(results)
    terc = pd.DataFrame(terciles)

    out = []

    def check(name, expected, got, tol):
        out.append({"check": name, "expected": round(expected, 6), "got": round(got, 6),
                    "passes": abs(got - expected) <= tol})

    toy = pd.Series(np.exp([0.0, 0.0, 0.0, 0.3, 0.3]), index=pd.period_range("2020-01", periods=5, freq="M").astype(str))
    w = signal_windows(toy, 1, lookback=3)
    check("toy: after three flat months the level jumps 0.3 in logs, so the gap is 0.3", 0.3, float(w["gap"].iloc[0]),
          1e-12)
    check("toy: the move that followed is exp(0) - 1 = 0", 0.0, float(w["move"].iloc[0]), 1e-12)
    x, y = np.array([0.0, 1, 2, 3]), np.array([1.0, 3, 5, 7])
    check("slope of a straight line y = 1 + 2x", 2.0, slope(x, y), 1e-12)
    lomo48, frames48 = summaries[48]
    check("leave-one-out: every market held out once", float(len(frames48)), float(lomo48["market"].nunique()), 0)
    check("leave-one-out: every window predicted once", float(sum(len(f) for f in frames48.values())),
          float(len(lomo48)), 0)
    again, actual_again = placebo(frames48, 48)
    check("the placebo is reproducible with its seed", float(again.mean()), float(placebo(frames48, 48)[0].mean()),
          1e-15)
    checks5 = pd.DataFrame(out)
    assert checks5["passes"].all(), checks5[~checks5["passes"]]

    row36 = table.loc[table["test"] == "36 months"].iloc[0]
    row48 = table.loc[table["test"] == "48 months"].iloc[0]
    signal = all(r["error saved by the moving charge, left-out markets (%)"] > 0 and r["placebo p, two-sided"] < 0.1
                 for r in (row36, row48))
    signs = {np.sign(r["pooled slope of shortfall on gap"]) for r in (row36, row48)}
    peak = row36["the same, contracts started 2021-22 (%)"]
    es = {r["level at the start"]: r["expected shortfall (% of residual)"] for _, r in terc.iterrows()}
    if signal and signs == {-1.0}:
        # The sentences below state these orderings; fail loudly if a re-run ever reverses one.
        assert all(es[f"{k} months, cold"] > es[f"{k} months, middle"] for k in (36, 48))
        hot36 = "more" if es["36 months, hot"] > es["36 months, middle"] else "less"
        verdict = (
            "**There is a signal, and it is about falling levels, not hot ones.** Contracts started when the level "
            "sat below its own three-year average lost far more: "
            f"{es['36 months, cold']:g}% of the residual at 36 months against {es['36 months, middle']:g}% in the "
            f"middle tercile, and {es['48 months, cold']:g}% against {es['48 months, middle']:g}% at 48 months. "
            "Declines persisted over the length of a contract. The slope is beyond what shifting the signal in time "
            "produces, and a charge that moves with the level errs less on markets it never saw.\n\n"
            "**On the hot side the evidence is weak.** At 36 months the hot tercile lost "
            f"{hot36} than the middle ({es['36 months, hot']:g}% against {es['36 months, middle']:g}%). For 36-month "
            "contracts started in 2021–22, near the shortage's peak, "
            + (f"the moving charge saved {peak:g}% of the flat charge's error, so it did better even there."
               if isinstance(peak, float) and peak > 0 else
               f"the moving charge's error was {abs(peak):g}% above the flat charge's: it did worse, because it cut "
               "the charge near the top.")
            + " The reversal of 2021–22 is only partly in the data: 48-month contracts can't start after 2021 here, "
            "and the 36-month ones started in 2022 end in 2025.\n\n"
            "**So the re-mark's action is one-sided.** When the level falls below its own three-year average, raise "
            "the charge on new contracts, or lower their residuals. Never cut the charge because the level runs hot.")
    elif signal and signs == {1.0}:
        verdict = ("**The level's position earns a place in the charge.** A level running hot predicted a larger "
                   "shortfall, beyond what shifting the signal in time produces, and the moving charge errs less on "
                   "markets it never saw. So the re-mark has an action: raise the charge on new contracts when the "
                   "level sits high above its own three-year average.")
    else:
        verdict = ("**The level's position does not earn a place in the charge.** Either the moving charge does not "
                   "err less on the markets it never saw, or its slope is within what shifting the signal in time "
                   "produces, or the two horizons disagree. The flat charge stands, and the re-mark's action is to "
                   "re-price the book, not to vary the charge.")

    text = f"""
## Part 5: should the charge move with the level?

The signal is how far the level sits above its own average of the previous {LOOKBACK} months when a contract starts
(in logs): positive when it has been running hot. The outcome is part 1's shortfall for a residual right on average
(the median move of the markets used). All EU markets with a full history are used, each from its first possible
start, so older series (France from 1996) bring more cycles. A charge `a + b × gap` is fitted on all markets but one
and scored on the one left out, against the flat charge from the same markets. The placebo shifts each market's
signal by at least one contract length, 1,000 times, and asks how often a slope at least as far from zero comes out
by chance.

{md_table(table)}

The charge by where the level sits when the contract starts (all markets pooled, terciles of the gap):

{md_table(terc)}

{verdict}

**The same caveat as every part: few independent episodes.** The hottest levels in most series are the 2021–22
shortage, so one episode carries much of the signal. Windows overlap within a market, so the squared errors are
not independent either.

### Checks (part 5)

{md_table(checks5)}
"""
    return text, table, checks5


def main():
    panel, core, months = common_panel()
    geos = sorted(panel)
    by_set = {"all": {k: pooled(panel, geos, k) / 100 for k in HORIZONS},
              "core": {k: pooled(panel, core, k) / 100 for k in HORIZONS}}
    table = checks(by_set)
    assert table["passes"].all(), table[~table["passes"]]

    rows = []
    for label, name in (("all", f"all {len(geos)} markets"), ("core", f"core {len(core)}")):
        for k in HORIZONS:
            m = by_set[label][k]
            for strike in ("no change", "median"):
                c = charge(m, strike)
                rows.append({"markets": name, "months": k, "residual assumes": strike,
                             "assumed move (%)": round(100 * c["assumed"], 1),
                             "expected shortfall (% of residual)": round(100 * c["expected"], 2),
                             "chance of a shortfall (%)": round(100 * c["chance"], 1),
                             "worst tenth, average shortfall (%)": round(100 * c["worst_tenth"], 2)})
    result = pd.DataFrame(rows)

    sample = []
    for k in HORIZONS:
        per_market, rho, eff = effective_sample(panel, geos, k, months)
        sample.append({"months": k, "windows": len(by_set["all"][k]),
                       "non-overlapping per market": per_market,
                       "mean correlation between markets": round(rho, 2),
                       "effective independent windows (rough)": round(eff, 1)})
    sample = pd.DataFrame(sample)

    by_market = []
    for g in core:
        row = {"market": g}
        for k in (36, 48):
            m = moves(panel[g], k) / 100
            row[f"{k}m median move (%)"] = round(100 * float(np.median(m)), 1)
            for strike in ("no change", "median"):
                row[f"{k}m, {strike} (%)"] = round(100 * charge(m, strike)["expected"], 2)
        by_market.append(row)
    by_market = pd.DataFrame(by_market)

    part1 = f"""# X6: pricing the market level

## Part 1: what the market level costs a residual, per euro

_Generated by `analysis/level_charge.py`. Eurostat HICP second-hand car indices (CP07112), the same panel as
`level_risk.py`: {len(geos)} EU markets with every month from {COMMON_START} to {COMMON_END}, each weighted equally;
"core" is the group's largest markets ({', '.join(core)}). Real data, nothing synthetic._

### What is priced

A residual set today assumes a market level at the contract's end. If the level ends lower, the lessor loses the
difference on every car that comes back. On the historical distribution, the fair charge is the **expected shortfall**
per euro of residual: `E[max(0, assumed − realised) / (1 + assumed)]`. The index holds a car's age constant, so its
move is the level, not depreciation.

Two assumptions for the residual:

- **no change:** the level at return equals today's. When the level has been rising, as it did over this window,
  such a residual carries a cushion, so it falls short less often;
- **median:** the level moves by the median move over the same horizon. The residual is right on average, with no
  cushion. A residual guide that forecasts better than the drift would do better (skeptic B5; X7 tests whether any
  can), so for such a guide this is an upper bound.

The median version is the charge for a residual set at a central forecast. The no-change version shows how much of
this decade's apparent safety was the drift.

"Worst tenth" is the average shortfall in the worst 10% of windows: a tail measure, not a premium.

### The charge per euro of residual

{md_table(result)}

Here the median is pooled across markets: one drift for all of them, so a market whose drift differs from it counts
that difference as risk. The by-market table below uses each market's own median.

### By market, core markets: expected shortfall (% of residual)

{md_table(by_market)}

A market whose level only rose over the window shows a no-change charge near zero. That is the decade's drift, not
an absence of risk; the median column removes it.

### How much data this really is

Windows overlap, and markets move together, so the window count overstates the evidence. "Effective independent
windows" divides the non-overlapping windows by `1 + (N − 1) × mean correlation between markets`: a rough guide, not
a formal effective sample size.

{md_table(sample)}

### Limits

- **One period.** The window runs from {COMMON_START} to {COMMON_END}. It includes the 2021–22 shortage, when used
  prices rose, so shortfalls from windows starting before it are rare. The median strike removes the average drift
  but not the shape of that one episode.
- **Retail, not auction.** The index prices dealer and advertised sales, not the auction prices a lessor gets, so the
  group's own shortfall has basis risk against it.
- **Market-wide.** A national index is an average across makes, fuels and ages; one model can fall further.

### Checks (part 1)

{md_table(table)}
"""
    text2, table2, checks2 = part2(by_set, len(geos))
    text3, table3, checks3 = part3(by_set)
    text4, table4, checks4 = part4(panel, core, by_set)
    text5, table5, checks5 = part5()
    OUT.write_text(part1 + text2 + text3 + text4 + text5)
    print(md_table(table5))
    print(md_table(checks5))
    print(md_table(table4))
    print(md_table(checks4))
    print(md_table(table3))
    print(md_table(checks3))
    print(md_table(table2))
    print(md_table(checks2))
    print(md_table(result))
    print(md_table(sample))
    print(md_table(table))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
