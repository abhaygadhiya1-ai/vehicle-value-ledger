"""X14 part 6: how much of the group's European car sales go through the agency model?

Leak 1 is about incentive claims that dealers file. Under a genuine agency model the carmaker sets the price and pays
the agent a fee, so the dealer-claim process leak 1 audits is replaced there. Stellantis kept the traditional dealer
model in Europe "with the exception of Austria, Belgium, Luxembourg, and the Netherlands, where the transition to the
agency model has already begun in 2023" (MarketScreener, 13 May 2025, quoting the head of Europe; WardsAuto, 19 May
2025). This script measures those four markets' share of the group's new-car registrations in the EU CO2 register
(X9's cache: EU, Norway and Iceland, no UK from 2021), by year.

Usage: .venv/bin/python analysis/agency_share.py   (writes analysis/agency_share_report.md)
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
from ev_exposure import CACHE, clean  # noqa: E402

OUT = HERE / "agency_share_report.md"
AGENCY = ["AT", "BE", "LU", "NL"]


def main():
    d = clean(pd.read_parquet(CACHE))
    group = d[d["group"].isin(("PSA", "FCA"))]
    by = group.pivot_table(index="Year", columns=group["MS"].isin(AGENCY), values="n", aggfunc="sum")
    t = pd.DataFrame({"group registrations": by.sum(axis=1).map("{:,.0f}".format),
                      "in the four agency markets": by[True].map("{:,.0f}".format),
                      "agency share (%)": (100 * by[True] / by.sum(axis=1)).round(1)})
    t.index.name = "year"
    t = t.reset_index()
    t["status"] = t["year"].map(lambda y: "provisional" if y == 2025 else "final")
    latest_final = t[t["status"] == "final"]["year"].max()
    summary = pd.DataFrame([
        {"figure": f"agency share of the group's registrations, {latest_final}",
         "value": t.set_index("year").at[latest_final, "agency share (%)"]},
        {"figure": "agency share, 2025 (provisional)", "value": t.set_index("year").at[2025, "agency share (%)"]}])
    by_market = (group[group["Year"] == latest_final].groupby("MS")["n"].sum().reindex(AGENCY)
                 .map("{:,.0f}".format).rename(f"group registrations {latest_final}").reset_index())

    text = f"""# How much of the group's sales go through the agency model? (X14 part 6)

The group kept the dealer model in Europe except in Austria, Belgium, Luxembourg and the Netherlands, which moved to
agency in 2023 (sources in the script's docstring). Their share of the group's new-car registrations in the EU CO2
register:

{md_table(t)}

{md_table(by_market)}

{md_table(summary)}

## What it means

- **Leak 1's dealer-claim process covers almost all of the group's European sales.** The four agency markets are a
  small share, so leak 1 is not split by channel: no sourced leakage rate exists per channel, and the split would move
  the total by less than its own range. Under agency the incentive is set in the price, and the agent's fee and bonus
  become the claims to audit.
- **Agency changes who sets the price, which is what competition law turns on** (Regulation (EU) 2022/720, Art. 4(a);
  Vertical Guidelines paras 30-34). In the four agency markets the group sets the retail price. Everywhere else it may
  only recommend one, and an incentive that makes the recommendation a fixed or minimum price in practice is a
  hardcore restriction.

## Limits

- Cars only, and the EU register has no UK after 2020, so the share is of the group's registrations in the EU, Norway
  and Iceland, not of Enlarged Europe's shipments.
- Agency may cover some brands or channels only; the sources give the countries, not the brand split.
- Registrations for 2025 are provisional.
"""
    OUT.write_text(text)
    print(md_table(t))
    print(md_table(summary))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
