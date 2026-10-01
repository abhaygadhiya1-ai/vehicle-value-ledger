"""X14 part 3: does the chosen Phase 2 pilot fit inside one market's customers?

X15 sized the pilot (the group's own upgrade flag randomised customer by customer within each dealer) in customers
per arm, and compared both arms with a year of the whole European book. That is not the feasibility test: a pilot runs
in one or two markets, on the customers whose contract ends in its window. This script puts the two arms beside a
year of each market's financed contracts, which stand in for a year of its contract ends.

Each market's contracts come from the group's finance arm, Stellantis Financial Services Europe (SFSE, annual report
2025): the count where the report gives one (France, Belgium-Luxembourg, Austria), else its penetration rate times
the group's new-car registrations there. SFSE's rate is over cars and vans; the EU CO2 register holds cars only, so an
estimate from it leaves the vans out and is low, which makes the pilot's share of it high: conservative for the
question asked. The check on the three disclosed counts shows by how much. The UK has no registrations in the EU
register after 2020, and SFSE gives no 2025 rate for the Netherlands or Portugal, so those three are left out.

The customers per arm are X15's (`x15_pilot_blocked_customers`, `x15_pilot_blocked_spill25_customers`): the gate at
power 80%, base retention 50%, ICC 0.1. A year's new contracts stand in for a year's contract ends; contracts written
three or four years earlier end now, and SFSE's European count was lower in 2023 than in 2025, so the stand-in is
generous for the markets that grew.

Usage: .venv/bin/python analysis/pilot_markets.py   (writes analysis/pilot_markets_report.md)
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
from ev_exposure import CACHE, clean  # noqa: E402

OUT = HERE / "pilot_markets_report.md"
REGISTER = HERE.parent / "assumptions.csv"
YEAR = 2025  # provisional in the EU register, the year SFSE's rates are for
# market: (EU register Member States, penetration row, disclosed count row or None, finance partner per the 20-F)
MARKETS = {
    "France": (["FR"], "sfse_pen_fr_2025", "sfse_contracts_fr_2025", "Santander CF joint venture"),
    "Italy": (["IT"], "sfse_pen_it_2025", None, "Santander CF joint venture"),
    "Germany": (["DE"], "sfse_pen_de_2025", None, "BNP Paribas PF joint venture"),
    "Spain": (["ES"], "sfse_pen_es_2025", None, "Santander CF joint venture"),
    "Poland": (["PL"], "sfse_pen_pl_2025", None, "Santander CF joint venture"),
    "Belgium-Luxembourg": (["BE", "LU"], "sfse_pen_be_lu_2025", "sfse_contracts_be_lu_2025",
                           "Santander CF joint venture"),
    "Austria": (["AT"], "sfse_pen_at_2025", "sfse_contracts_at_2025", "BNP Paribas PF joint venture"),
}


def main():
    reg = pd.read_csv(REGISTER).set_index("id")["value"].astype(str)
    num = lambda k: float(reg[k])  # noqa: E731
    per_arm, per_arm_spill = num("x15_pilot_blocked_customers"), num("x15_pilot_blocked_spill25_customers")
    need, need_spill = 2 * per_arm, 2 * per_arm_spill

    d = clean(pd.read_parquet(CACHE))
    group = d[d["group"].isin(("PSA", "FCA"))]
    cars = group[group["Year"] == YEAR].groupby("MS")["n"].sum()
    prior = group[group["Year"] == YEAR - 1].groupby("MS")["n"].sum()

    rows, checks = [], []
    for market, (ms, pen_id, count_id, partner) in MARKETS.items():
        regs = float(cars.reindex(ms).fillna(0).sum())
        est = regs * num(pen_id) / 100
        contracts = num(count_id) if count_id else est
        rows.append({"market": market, "finance partner": partner,
                     f"group car registrations {YEAR}": f"{regs:,.0f}",
                     "SFSE penetration (%)": f"{num(pen_id):g}",
                     "contracts a year": f"{contracts:,.0f}",
                     "basis": "disclosed" if count_id else "rate x car registrations (vans left out)",
                     "both arms, share of a year (%)": f"{100 * need / contracts:.0f}",
                     "with spillover, share of a year (%)": f"{100 * need_spill / contracts:.0f}",
                     "months of contract ends, with spillover": f"{12 * need_spill / contracts:.1f}"})
        ratio = regs / float(prior.reindex(ms).fillna(0).sum())
        checks.append({"check": f"{market}: {YEAR} provisional registrations within 30% of {YEAR - 1}'s final",
                       "got": f"{ratio:.2f} times", "passes": bool(0.7 <= ratio <= 1.3)})
        if count_id:
            checks.append({"check": f"{market}: rate x car registrations is below the disclosed count (vans left out)",
                           "got": f"{est:,.0f} vs {contracts:,.0f} ({100 * est / contracts:.0f}%)",
                           "passes": bool(est < contracts)})
    table = pd.DataFrame(rows)
    shares = pd.to_numeric(table["with spillover, share of a year (%)"])
    fits = table.loc[shares <= 50, "market"].tolist()
    most = table.loc[(shares > 50) & (shares <= 100), "market"].tolist()
    over = table.loc[shares > 100, "market"].tolist()
    europe = num("sfse_eu_nv_contracts_2025")
    covered = sum(float(r["contracts a year"].replace(",", "")) for r in rows)
    checks.append({"check": "the seven markets' contracts do not exceed SFSE's European total",
                   "got": f"{covered:,.0f} of {europe:,.0f} ({100 * covered / europe:.0f}%)",
                   "passes": bool(covered <= europe)})
    checks = pd.DataFrame(checks)
    summary = pd.DataFrame([
        {"figure": "customers needed, both arms (the gate, power 80%, base 50%, ICC 0.1)", "value": f"{need:,.0f}"},
        {"figure": "the same, with a quarter of the uplift spilling over", "value": f"{need_spill:,.0f}"},
        {"figure": "France: both arms, share of a year's contracts (%)",
         "value": table.set_index("market").at["France", "both arms, share of a year (%)"]},
        {"figure": "France: both arms with spillover, share of a year's contracts (%)",
         "value": table.set_index("market").at["France", "with spillover, share of a year (%)"]},
        {"figure": "Austria: both arms with spillover, share of a year's contracts (%)",
         "value": table.set_index("market").at["Austria", "with spillover, share of a year (%)"]},
        {"figure": "Belgium-Luxembourg: both arms with spillover, share of a year's contracts (%)",
         "value": table.set_index("market").at["Belgium-Luxembourg", "with spillover, share of a year (%)"]},
        {"figure": "markets where both arms with spillover take half a year's contracts or less",
         "value": str(len(fits))}])

    text = f"""# Does the Phase 2 pilot fit inside one market? (X14 part 3)

The pilot randomises the group's own upgrade flag customer by customer within each dealer (X15, decision of 26
September). It needs {need:,.0f} customers in its two arms, or {need_spill:,.0f} if a quarter of the uplift spills
over to unflagged customers (`pilot_size_report.md`). This report puts that beside a year of each market's financed
contracts, which stand in for a year of its contract ends. Sources and method are in the script's docstring.

{md_table(table)}

Markets where both arms, with spillover, take half a year's contracts or less: {", ".join(fits)}.

{md_table(summary)}

## What it means

- **The pilot fits in one large market.** France, the one large market with a disclosed count, holds the two arms,
  spillover included, in a small share of one year's contract ends. The others that fit ({", ".join(m for m in fits if m != "France")})
  do so on estimated counts, which leave vans out and so understate them.
- **The smaller markets don't fit in a year.** With spillover, {", ".join(most) or "none"} would need most of a year's
  contract ends and {", ".join(over) or "none"} more than a year's. Not every customer reaching a contract end is
  reachable, so they would need a window of more than a year. The gate is best tested in {", ".join(fits)}; the
  smaller markets join in Phase 3.
- **Every candidate market's contracts sit in a joint venture** with a partner bank (the 20-F: Santander CF in France,
  Italy, Spain, Belgium, Poland and the Netherlands; BNP Paribas PF in Germany, Austria and the UK). The flag needs
  each contract's end date and the customer's consent to be contacted, and both sit with the joint venture. SFSE's
  2025 report credits "opérations conjointes B2C" (joint consumer campaigns with the brands, Spain) and "le poids
  important des offres fidélisantes" (the weight of loyalty offers), so brand and bank already act together on
  retention. Whether a customer-level randomised flag is allowed under each joint venture's contracts and privacy
  terms is not public. It is a Phase 1 data-access task, not a finding.

## Checks

{md_table(checks)}

## Limits

- A year's new contracts stand in for a year's contract ends. Contracts end three or four years after signing, and
  SFSE's European count grew from 2023 to 2025, so the stand-in is generous where a market grew. Austria's count rose
  60% in 2025, so the ends coming up are fewer than its 2025 count.
- Only markets with a 2025 SFSE rate and EU-register registrations are shown. The UK (no registrations in the EU
  register after 2020), the Netherlands and Portugal (no 2025 rate) are missing.
- Germany's rate is a floor ("à plus de 33,8%").
- The customers per arm are X15's at base retention 50%, the largest size; any other base rate needs fewer. They
  exclude the wholly unflagged dealers that measure spillover.
- Registrations for {YEAR} are provisional in the EU register.
"""
    OUT.write_text(text)
    print(md_table(table))
    print(md_table(checks))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
