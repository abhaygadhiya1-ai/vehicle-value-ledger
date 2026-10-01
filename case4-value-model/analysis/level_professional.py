"""X7 part 3: did a professional forecast the level better than "no change"?

Skeptic B5: residual guides forecast the level, so their error, not no change's, is the right comparison. No guide
publishes its accuracy (checked twice). The closest public record is a lessor's result on the cars it sells: sale
price against book value, where the book value is the residual set at contract start, depreciated. Europe's largest
lessor discloses both lines every year.

The professional's error for a sale year: proceeds of cars sold over their cost (written-down value plus disposal
costs), less 1. Positive means the cars sold above the residual. Read from the register (SOURCED rows `ald_*` and
`ayvens_*`, from the annual registration documents).

No change's error for the same sale year: the used-car index's move over the contract (ALD's full-service leases "are
typically for a duration of 36 to 48 months", registration documents 2020 and 2021), the level when the car sold
against the level when the contract started, averaged over the sale year's months. It is shown at 36 and 48 months,
for France (the lessor's home market) and for the equal mean of the group's large markets it also serves (FR, IT,
ES, DE, NL). Both errors are "realised over assumed, less 1".

Clean years: ALD 2018-2022, before the LeasePlan merger. For 2022 the margin is taken against the original residual:
ALD cut depreciation that year for cars expected to sell above book, and discloses the per-car result had it not.
Ayvens 2023-2025 are shown for information only: LeasePlan's cars were revalued to market at acquisition, and the
depreciation cuts were reversed in 2024-25, so those margins are not residual errors.

What it can show: if the professional's residual anticipated the level, its margin should move much less than no
change's error across years. If the margin tracks the level move, the professional did about as well as no change.
Five clean years make this a description, not a test.

Checks: the per-car result times the cars sold reproduces proceeds less cost, within the rounding of the three
stated figures (EUR 1 per car, 1,000 cars, EUR 0.1m).

Usage: .venv/bin/python analysis/level_professional.py   (writes analysis/level_professional_report.md)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
from level_risk import EUROSTAT, load  # noqa: E402

OUT = HERE / "level_professional_report.md"
REGISTER = HERE.parent / "assumptions.csv"
CLEAN = (2018, 2019, 2020, 2021, 2022)     # ALD before the LeasePlan merger
AFTER = (2023, 2024, 2025)                 # Ayvens: information only
MARKETS = ("FR", "IT", "ES", "DE", "NL")
CONTRACTS = (36, 48)


def lessor(reg):
    """Per sale year: the margin over book, reported and against the original residual."""
    rows = []
    for y in CLEAN + AFTER:
        who = "ald" if y in CLEAN else "ayvens"
        proceeds, cost = reg[f"{who}_car_proceeds_{y}"], reg[f"{who}_car_cost_{y}"]
        units = reg.get(f"{who}_used_cars_sold_k_{y}", np.nan)
        clean = proceeds - reg["ald_ucs_per_unit_ex_depr_2022"] * units / 1000 if y == 2022 else cost
        rows.append({"year": y, "who": who, "proceeds": proceeds, "cost": cost, "units_k": units,
                     "per_unit": reg[f"{who}_ucs_per_unit_{y}"], "margin": proceeds / cost - 1,
                     "margin_original": proceeds / clean - 1})
    return pd.DataFrame(rows)


def level_moves(series, years, k):
    """Per sale year: the mean over its months of the level against k months earlier, less 1."""
    out = {}
    for y in years:
        months = [f"{y}-{m:02d}" for m in range(1, 13)]
        starts = [str(pd.Period(m, freq="M") - k) for m in months]
        pairs = [(series[m], series[s]) for m, s in zip(months, starts) if m in series.index and s in series.index]
        out[y] = np.mean([a / b - 1 for a, b in pairs]) if len(pairs) == 12 else np.nan
    return out


def main():
    reg = pd.read_csv(REGISTER).set_index("id")["value"].astype(float)
    book = lessor(reg)
    euro = {g: s for (series, g), s in load().items() if series == EUROSTAT and g in MARKETS}
    moves = {}
    for k in CONTRACTS:
        per_market = {g: level_moves(euro[g], CLEAN + AFTER, k) for g in MARKETS}
        moves[("FR", k)] = per_market["FR"]
        moves[("mean", k)] = {y: np.mean([per_market[g][y] for g in MARKETS]) if all(
            np.isfinite(per_market[g][y]) for g in MARKETS) else np.nan for y in CLEAN + AFTER}

    table = book[["year", "proceeds", "cost"]].copy()
    table["cars sold (k)"] = book["units_k"].map(lambda v: "" if np.isnan(v) else f"{v:.0f}")
    table["margin over book"] = book["margin"].map(lambda v: f"{v:+.1%}")
    table["against the original residual"] = [f"{m:+.1%}" if y == 2022 else "" for y, m in
                                              zip(book["year"], book["margin_original"])]
    for (where, k), mv in moves.items():
        label = "France" if where == "FR" else "5-market mean"
        table[f"no change, {k}m, {label}"] = [f"{mv[y]:+.1%}" if np.isfinite(mv[y]) else "" for y in book["year"]]
    table["proceeds"] = table["proceeds"].map(lambda v: f"{v:,.1f}")
    table["cost"] = table["cost"].map(lambda v: f"{v:,.1f}")
    table["basis"] = ["ALD, clean" if y in CLEAN else "Ayvens, information only" for y in book["year"]]

    clean = book[book["year"].isin(CLEAN)].set_index("year")
    pro = np.where(clean.index == 2022, clean["margin_original"], clean["margin"])
    summary = []
    for (where, k), mv in moves.items():
        nc = np.array([mv[y] for y in CLEAN])
        ok = np.isfinite(nc)
        slope = float(np.polyfit(nc[ok], pro[ok], 1)[0]) if ok.sum() >= 3 else np.nan
        summary.append({"no change measured on, contract":
                        f"{'France' if where == 'FR' else '5-market mean'}, {k} months",
                        "years": f"{ok.sum()} of {len(CLEAN)}",
                        "professional RMSE": f"{np.sqrt(np.mean(pro[ok] ** 2)):.1%}",
                        "no change RMSE": f"{np.sqrt(np.mean(nc[ok] ** 2)):.1%}",
                        "professional mean": f"{np.mean(pro[ok]):+.1%}", "no change mean": f"{np.mean(nc[ok]):+.1%}",
                        "slope of margin on level move": "" if np.isnan(slope) else f"{slope:.2f}"})

    peak = CLEAN[-1]
    by_market = pd.DataFrame([{"market": g, **{f"no change, {k}m": f"{level_moves(euro[g], [peak], k)[peak]:+.1%}"
                                                for k in CONTRACTS}} for g in MARKETS])
    pro_peak = float(clean.loc[peak, "margin_original"])
    beyond = sum(level_moves(euro[g], [peak], k)[peak] < pro_peak for g in MARKETS for k in CONTRACTS)
    fr = euro["FR"]
    fr_2021 = fr["2021-12"] / fr["2020-12"] - 1
    as24 = reg["autoscout24_fr_avg_price_2021_pct"] / 100

    checks = []
    for r in book.itertuples():
        stated = reg[f"{r.who}_car_proceeds_{r.year}"] - reg[f"{r.who}_car_cost_{r.year}"]
        if np.isfinite(r.units_k):
            implied = r.per_unit * r.units_k / 1000
            checks.append({"check": f"{r.year}: the per-car result times the cars sold reproduces proceeds less cost "
                                    "(within the rounding of both to the stated digits)",
                           "got": f"{implied:,.1f} vs {stated:,.1f}",
                           "passes": abs(implied - stated) <= (r.per_unit + r.units_k) * 0.5 / 1000 + 0.1})
        else:
            checks.append({"check": f"{r.year}: cars sold are not stated; the per-car result implies "
                                    f"{stated / r.per_unit * 1000:,.0f} thousand cars", "got": "not checked",
                           "passes": True})

    lines = [
        "# X7 part 3: did a professional forecast the level better than \"no change\"?",
        "",
        "Generated by `analysis/level_professional.py`; the method is in its docstring. The professional is Europe's "
        "largest lessor (ALD, since 2023 Ayvens). Its error is the margin on the cars it sold: proceeds over the cost "
        "of cars sold (their written-down book value), less 1, from its annual registration documents (register rows "
        "`ald_*` and `ayvens_*`). No change's error is the used-car index's move over the contract. Both are "
        "\"realised over assumed, less 1\"; positive means the level ended above what was assumed.",
        "",
        "## Year by year",
        "",
        md_table(table[["year", "basis", "proceeds", "cost", "cars sold (k)", "margin over book",
                        "against the original residual"] + [c for c in table.columns if c.startswith("no change")]]),
        "",
        "Proceeds and cost in EUR m. For 2022 the margin is also shown against the original residual: ALD cut "
        "depreciation that year for cars expected to sell above book, which moved part of the gain into the leasing "
        "margin, and it discloses the per-car result had it not.",
        "",
        f"## The clean years, {CLEAN[0]}-{CLEAN[-1]}",
        "",
        md_table(pd.DataFrame(summary)),
        "",
        "The slope asks how much of the index's move over the contract showed up in the lessor's margin. Near 0 would "
        "mean the residual anticipated the move. Near 1 would mean it did not, so the professional did about as well "
        "as no change. Above 1, as here, it did not anticipate the move *and* the prices the lessor met moved more "
        "than the index (next section): the index understates the level a lessor faces, so the index-based no-change "
        "error is not a fair yardstick in percentage terms.",
        "",
        "**What survives the basis problem:** the lessor's margin ran "
        f"{', '.join(f'{m:+.1%}' for m in pro[:3])} in {CLEAN[0]}-{CLEAN[2]}, a small cushion, then "
        f"{pro[3]:+.1%} in {CLEAN[3]} and {pro[4]:+.1%} in {CLEAN[4]} against the original residual. The residuals on "
        f"the {CLEAN[3]}-{CLEAN[4]} sales, set in {CLEAN[3] - 4}-{CLEAN[4] - 3}, carried no foresight of the "
        "2021-22 rise: the professional missed it, as no "
        "change did. The one public record of a professional's residual error gives no sign that it forecast the "
        "level.",
        "",
        f"## {peak}: the lessor's miss against each market's index move",
        "",
        md_table(by_market),
        "",
        f"The lessor's {peak} margin against the original residual, {pro_peak:+.1%}, exceeds the index move in "
        f"{beyond} of {len(MARKETS) * len(CONTRACTS)} market-and-contract cases.",
        "",
        "## France's official index missed the 2021 rise",
        "",
        f"From December 2020 to December 2021, Eurostat's French used-car index (CP07112) moved {fr_2021:+.1%}. "
        f"AutoScout24's French barometer put the average advertised used-car price {as24:+.1%} over the same months "
        "(register row `autoscout24_fr_avg_price_2021_pct`). An average over all adverts shifts with the mix, but not "
        "by that much in a year. France is the longest history in part 1 and in X6's back-tests, and the lessor's "
        "home market, so level moves measured on the French index understate what French sellers met.",
        "",
        "## Checks",
        "",
        md_table(pd.DataFrame(checks)),
        "",
        "## Limits",
        "",
        "- **Five clean years,** so this describes; it does not test. One of them (2022) is the largest level move on "
        "record.",
        "- **The margin is not only the level.** It mixes the market level with the cars' condition and mix, "
        "remarketing channels and costs, and policy: ALD says its 2021 margin was also helped by the 2020 contract "
        "extensions, which lowered book values, and it booked a COVID stress on residuals in 2020.",
        "- **Different prices.** The lessor sells mostly at auction and to traders; the index is retail. The "
        "lessor's markets are wider than the five used here, and its contract lengths vary.",
        "- **One lessor.** No residual guide publishes its accuracy, so this is the closest public record, not the "
        "guides' own error.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(table.to_string(index=False))
    print(pd.DataFrame(summary).to_string(index=False))
    print(pd.DataFrame(checks)[["got", "passes"]].to_string(index=False))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
