"""X14 part 4: an outside anchor for leak 1's claims line (skeptic B9).

Leak 1's claims line was eu_revenue x incentive_pct_revenue (8%, an ASSUMPTION) x process_leak_pct. The group's 20-F
does publish the flow that line is about. Note 21 carries a "Sales incentives" provision with a roll-forward: the
estimated cost of incentive programmes offered to dealers and consumers is booked against revenue when the car is sold
to the dealer ("additional provisions"), and the provision is used up as the programmes are claimed and paid
("settlements"). Invoice price discounts need not pass through it, so it is the claims-based part of incentive
spend, which is the part leak 1's claims line is about.

The figures are worldwide; the 20-F gives no regional split. This script divides each year's additions and
settlements by the group's net revenues, the same basis as `eu_revenue_eur_m` (segment net revenues, themselves net of
incentives). The central case is the latest year's additions: the incentive cost of that year's sales, which is the
claims those sales will generate. Settlements mix years (in 2025 they paid down a provision built up in 2024), so they
bound the range with the additions: the range is the lowest and highest of the four ratios. Applying a worldwide ratio to Europe is the one judgement left, and it is named in the
limits.

Usage: .venv/bin/python analysis/incentive_anchor.py   (writes analysis/incentive_anchor_report.md)
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_unified import md_table  # noqa: E402

OUT = HERE / "incentive_anchor_report.md"
REGISTER = HERE.parent / "assumptions.csv"
REVENUE = {2025: "group_revenue_eur_m", 2024: "group_revenue_2024_eur_m"}
# The rest of Note 21's roll-forward for the Sales incentives line (EUR m), used only to check that the additions and
# settlements in the register were read from the right row: opening balance, then unused amounts, translation
# differences, transfers to held for sale, change in scope and other, then the closing balance.
ROLLFORWARD = {2025: dict(opening=6343, other=-23 - 411 + 0 - 34 + 38, closing=5321),
               2024: dict(opening=6031, other=-4 + 214 - 21 + 0 + 4, closing=6343)}


def main():
    reg = pd.read_csv(REGISTER).set_index("id")
    val = lambda k: float(reg.at[k, "value"])  # noqa: E731
    rows = []
    for year, rev in REVENUE.items():
        for flow in ("additions", "settlements"):
            spend = val(f"sales_incentive_{flow}_{year}_eur_m")
            rows.append({"year": year, "flow": flow, "EUR m": f"{spend:,.0f}",
                         "net revenues, EUR m": f"{val(rev):,.0f}",
                         "share of net revenues (%)": round(100 * spend / val(rev), 2)})
    t = pd.DataFrame(rows)
    shares = t["share of net revenues (%)"]
    central = t[(t["year"] == 2025) & (t["flow"] == "additions")]["share of net revenues (%)"].iloc[0]
    summary = pd.DataFrame([
        {"figure": "incentive claims, share of net revenues, central (2025 additions)", "value": central},
        {"figure": "the same, lowest of the four ratios", "value": shares.min()},
        {"figure": "the same, highest of the four ratios", "value": shares.max()},
        {"figure": "our former assumption, incentive_pct_revenue (%)", "value": val("incentive_pct_revenue")}])
    old_lo, old_hi = reg.at["incentive_pct_revenue", "low"], reg.at["incentive_pct_revenue", "high"]
    checks = []
    for year, rf in ROLLFORWARD.items():
        closing = rf["opening"] + val(f"sales_incentive_additions_{year}_eur_m") \
            - val(f"sales_incentive_settlements_{year}_eur_m") + rf["other"]
        checks.append({"check": f"{year}: opening + additions - settlements + other movements = closing (Note 21)",
                       "got": f"{closing:,.0f} vs {rf['closing']:,.0f}", "passes": closing == rf["closing"]})
    checks += [
        {"check": "the register's closing balance for 2025 equals Note 21's",
         "got": f"{val('sales_incentive_provision_2025_eur_m'):,.0f}",
         "passes": val("sales_incentive_provision_2025_eur_m") == ROLLFORWARD[2025]["closing"]},
        {"check": "every ratio sits inside the former assumption's range",
         "got": f"{shares.min()} to {shares.max()} within {old_lo:g} to {old_hi:g}",
         "passes": bool(shares.min() >= old_lo and shares.max() <= old_hi)}]
    checks = pd.DataFrame(checks)

    text = f"""# Leak 1's outside anchor: the group's own incentive claims (X14 part 4)

The group's 20-F (FY2025, Note 21) carries a sales-incentive provision. What it adds each year is the estimated cost of
incentive programmes on cars sold to dealers; what it settles is the programmes claimed and paid. Both are worldwide.
As a share of the group's net revenues:

{md_table(t)}

{md_table(summary)}

The group's claims-based incentive programmes cost about {central:.1f}% of net revenues, below our former
assumption of {val("incentive_pct_revenue"):g}% and inside its range. Leak 1's claims line now uses the central figure,
with the lowest and highest of the four ratios as its range (`x14_incentive_claims_*`).

## The leak rate beside it

What share of claims is paid wrongly stays an assumption (`process_leak_pct`), because no carmaker publishes one. The
closest audited analogue is the European Court of Auditors' error rate on EU spending paid out on claims. It was
{val("eca_error_complex_rules_2024"):g}% in 2024 where the rules are complex and beneficiaries claim reimbursement of
costs, below 2% for simple entitlement payments, and {val("eca_error_overall_2024"):g}% overall (`eca_error_*`). Dealer
incentive programmes have complex rules (stacking, eligibility dates, fleet or retail), so our
{val("process_leak_pct"):g}% sits at the simple-rules end: conservative. No published rate was found for how much a
claim audit recovers; `recoverable_share` stays an assumption.

## Checks

{md_table(checks)}

## Limits

- **Worldwide, applied to Europe.** The 20-F gives no regional split, and North America carries heavy incentives in
  some years. Europe's ratio could be higher or lower; the ledger measures it from the group's own claims.
- **Claims-based spend only.** Price discounts at invoice need not pass through the provision, so total incentive
  spend is higher. Leak 1's claims line is about claims, so this is its base. The per-car P&L's
  `pl_incentive_pct_list` (a share of list price, a different base) is unchanged.
- **Two years.** The range is the variation across 2024 and 2025 and across additions and settlements, not a
  confidence interval.
- **An analogue for the leak rate.** The Court of Auditors audits public grants, not dealer claims; it shows the
  order of magnitude of error in claim-based payments under complex rules, after controls.
"""
    OUT.write_text(text)
    print(md_table(t))
    print(md_table(summary))
    print(md_table(checks))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
