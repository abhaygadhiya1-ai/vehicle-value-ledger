"""X20: which data the ledger needs, who holds it, the route to it, and the fallback if refused.

Skeptic F6: the single view rests on data the group doesn't fully control. The finance contracts sit in joint ventures
with partner banks in every large EU market (X14); independent dealers report the incentive claims, and X1's red teams
showed a knowing dealer moves to facts no source records; customer contact needs consent. This script does two things.

1. **Measures one route:** how much of the group's EU registrations sit in markets whose vehicle register lets the
   group check a sold car independently, per car, without the dealer. The route by market comes from part 1's
   sources (register rows cited in the table); the registrations are the EU's CO2 monitoring register (the cache
   X9 built), the group's brands as `merger_diversification.py` tags them. 2024 is final; 2025 (provisional) is a check.
2. **Writes the per-source map** the design rests on: for each source, who holds it, the legal basis, the route, the
   precedent or rule, the fallback if refused, and the lever that needs it. Every row cites register rows or reports.

Checks: every market is in exactly one class; shares sum to one; the two years agree on the classes' order; every
register row the map cites exists.

Usage: .venv/bin/python analysis/data_reach.py   (writes analysis/data_reach_report.md; seconds)
"""
import csv
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import merger_diversification as md  # noqa: E402
from build_unified import md_table  # noqa: E402

OUT = HERE / "data_reach_report.md"
REGISTER = HERE.parent / "assumptions.csv"
CACHE = HERE.parent / "data" / "reference" / "x9_eea_registrations_fuel.parquet"
YEAR, CHECK_YEAR = 2024, 2025

# The route each market's vehicle register gives the group for an independent per-car check of a sale (part 1).
ROUTES = {
    "open, bulk, free": {"NL": "RDW open data (used throughout this project; current keeper only)"},
    "per car, open to anyone, paid: spot checks": {"ES": "`dgt_reports_open`",
                                                    "IT": "`aci_visura_open` (three a day per tax code)"},
    "no route for a claim check": {"DE": "`kba_register_private_access`", "FR": "`histovec_holder_only`",
                                   "FI": "Traficom: anonymised open snapshots (X11), per-car service for authenticated users"},
}
NOT_CHECKED = "not checked"

# The per-source map. Register ids in backticks are checked to exist.
MAP = [
    ("Incentive claims (dealer-submitted)", "Independent dealers; the group pays",
     "Fraud prevention (`gdpr_fraud_legitimate_interest`) and the incentive programme's own terms",
     "VIN-level proof of sale and an audit right written into each programme; an exchange that implements the "
     "agreement is exempt (`vber_info_exchange_dual`)",
     "X1: a knowing dealer moves to facts no source records, so checks need independent sources",
     "Independent checks where a register is open (section 1), the group's own records (price list, shipments), "
     "and the finance contract where the group's partner financed the car", "Leak 1, claims"),
    ("Buyer attributes for targeted incentives", "Dealers; the finance partners (credit applications)",
     "The sales or credit contract; automated personalised prices must be disclosed (X5)",
     "Where the group is the seller (agency markets, `x14_agency_share_2025p`); elsewhere a joint programme with "
     "the finance partner (`gdpr_joint_controllers`)",
     "X5: the gain assumes income known exactly, the best case",
     "Targeting by segment (model, fuel, region) without personal data; a customer rebate claimed with income "
     "evidence (unmeasured)", "Leak 1, targeting"),
    ("Finance contracts: end dates, balances, whether the group carries the residual",
     "The joint ventures (Santander CF; BNP Paribas PF; Leasys), not the group",
     "The joint venture's contract with the customer",
     "An Art 26 arrangement for a shared upgrade programme, or keyed matching that returns cohort-level timing "
     "(pseudonymised data stay personal: `edpb_pseudonymised_personal`)",
     "X14: brand and bank already run joint consumer campaigns and loyalty offers (SFSE 2025)",
     "Cohort-level timing from public registers (X3's 48- and 60-month waves) and the readiness engine; the "
     "partner contacts its own customers", "Leak 2; X19's internal prices"),
    ("Consent to contact a finance customer", "The joint venture (its own soft opt-in); the group only for "
     "its own buyers and app users", "Consent, or the seller's soft opt-in for its own similar products "
     "(`eprivacy_soft_optin`)",
     "The partner sends the upgrade offer (a new finance contract is its own similar product); the group supplies "
     "the timing", "Art 13(2) keeps the opt-in with the seller", "Cohort-level campaigns without customer-level "
     "flags", "Leak 2"),
    ("Buy-back commitments, returns and resale", "The group (its own repurchase contracts, 20-F)",
     "The contract", "The group's own records", "`stellantis_buyback_forms`", "None needed",
     "Leak 3 (pricing, execution); X19's internal prices"),
    ("A returned car's odometer, battery and condition", "The car (the maker as data holder); the rental firm "
     "or leasing company as user", "A contract with the user for non-personal data "
     "(`data_act_user_owner_lessee`); consent for a private driver's data (`eprivacy_terminal_consent`, "
     "`edpb_connected_vehicle_terminal`)",
     "A data clause in the group's own buy-back and lease contracts (the counterparty is the user); the design "
     "duty for cars placed on the market after 12 September 2026 (`data_act_design_duty_date`)",
     "`cnil_ubeeqo_fine_eur`: read events at return, never location streams",
     "Inspection at intake (X17's condition report) and the battery regulation's state-of-health read (X9)",
     "Leak 3 (value engine, condition, EVs)"),
    ("Realised resale prices", "The group's remarketing; Aramis (60.54%, listed)", "The group's own sales; "
     "Aramis's public disclosures", "Own operations; Aramis publishes quarterly (X10)",
     "X10: Aramis's realised price moves with the official indices", "Aramis's quarterly disclosures",
     "Leak 3 audit; X19's metric audit"),
    ("Keeper changes and odometer readings", "National registers", "Each register's own terms",
     "By market (section 1)", "`dgt_reports_open`, `kba_register_private_access`, `histovec_holder_only`",
     "None where closed", "Leak 1 checks; readiness"),
    ("Used-car price level", "Eurostat, ONS (public)", "Open data", "Open", "X6-X8", "None needed",
     "Leak 3 level (priced, re-marked)"),
]


def register_ids():
    return {r["id"] for r in csv.DictReader(open(REGISTER, encoding="utf-8"))}


def group_registrations(year):
    d = md.clean(pd.read_parquet(CACHE).assign(n=lambda f: f["n"].astype(float)))
    n, _ = md.mix(d, year)
    return n["merged"]


def main():
    ids = register_ids()
    route_of = {m: cls for cls, ms in ROUTES.items() for m in ms}
    tables, shares = {}, {}
    for year in (YEAR, CHECK_YEAR):
        n = group_registrations(year)
        cls = n.index.map(lambda m: route_of.get(m, NOT_CHECKED))
        s = n.groupby(cls).sum() / n.sum()
        shares[year] = s
        tables[year] = n
    order = [*ROUTES, NOT_CHECKED]

    ck = []

    def check(name, ok, got):
        ck.append({"check": name, "got": got, "passes": bool(ok)})

    for year in (YEAR, CHECK_YEAR):
        check(f"{year}: shares sum to one", abs(shares[year].sum() - 1) < 1e-12, round(float(shares[year].sum()), 12))
    check("every mapped market has registrations in 2024", all(m in tables[YEAR].index for m in route_of),
          ", ".join(sorted(m for m in route_of if m not in tables[YEAR].index)) or "all present")
    check("each market sits in one class", len(route_of) == sum(len(v) for v in ROUTES.values()), len(route_of))
    rank = lambda y: list(shares[y].reindex(order).fillna(0).sort_values(ascending=False).index)  # noqa: E731
    check("the classes rank the same in 2024 and 2025", rank(YEAR) == rank(CHECK_YEAR), " > ".join(rank(YEAR)))
    cited = set(re.findall(r"`([a-z0-9_]+)`", " ".join(" ".join(r) for r in MAP) + " ".join(
        v for ms in ROUTES.values() for v in ms.values())))
    missing = sorted(c for c in cited if c not in ids)
    check("every register row the map cites exists", not missing, ", ".join(missing) or f"{len(cited)} cited")
    ck = pd.DataFrame(ck)
    all_ok = bool(ck["passes"].all())

    route_table = pd.DataFrame([
        {"register route": c, "markets": ", ".join(ROUTES.get(c, {})) or "the rest",
         f"share of the group's registrations, {YEAR} (%)": round(100 * float(shares[YEAR].get(c, 0.0)), 1),
         f"the same, {CHECK_YEAR} provisional (%)": round(100 * float(shares[CHECK_YEAR].get(c, 0.0)), 1),
         "source": "; ".join(ROUTES.get(c, {}).values()) or "not researched"} for c in order])
    spot = "per car, open to anyone, paid: spot checks"
    verified = shares[YEAR].get("open, bulk, free", 0.0) + shares[YEAR].get(spot, 0.0)
    verified_c = shares[CHECK_YEAR].get("open, bulk, free", 0.0) + shares[CHECK_YEAR].get(spot, 0.0)
    summary = pd.DataFrame([
        {"measure": "any independent per-car route (NL, ES, IT)", f"{YEAR} (%)": round(100 * verified, 1),
         f"{CHECK_YEAR} provisional (%)": round(100 * verified_c, 1)},
        {"measure": "in bulk (NL)", f"{YEAR} (%)": round(100 * shares[YEAR].get("open, bulk, free", 0.0), 1),
         f"{CHECK_YEAR} provisional (%)": round(100 * shares[CHECK_YEAR].get("open, bulk, free", 0.0), 1)},
    ])
    top = tables[YEAR].sort_values(ascending=False).head(10)
    markets = pd.DataFrame({"market": top.index, f"group registrations, {YEAR}": top.astype(int).values,
                            "share (%)": (100 * top / tables[YEAR].sum()).round(1).values,
                            "register route": [route_of.get(m, NOT_CHECKED) for m in top.index]})
    source_map = pd.DataFrame(MAP, columns=["source", "who holds it", "legal basis", "route", "precedent or rule",
                                            "fallback if refused", "lever that needs it"])

    findings = [
        f"- **An independent per-car check of a sale is open in markets holding {100 * verified:.1f}% of the group's "
        f"{YEAR} EU registrations,** in bulk only in the Netherlands "
        f"({100 * shares[YEAR].get('open, bulk, free', 0.0):.1f}%); Spain and Italy answer anyone per car for a fee, "
        "Italy three a day per tax code, so there they serve sampled spot checks. "
        "Germany and France, two of the three largest markets, are closed to it: Germany's register answers only "
        "road-traffic claims, France's "
        f"history report only its holder ({100 * shares[YEAR].get('no route for a claim check', 0.0):.1f}% with "
        "Finland). So the claims control rests mainly on sources the group can require by contract (proof of sale "
        "and an audit right, exempt under the block exemption) and on the group's own records, with registers as a "
        "check where open.",
        "- **What the joint ventures hold is what leak 2 needs:** contract end dates, balances and the consent to "
        "contact. The group cannot take them, and a partner's opt-in never passes to it; but the partner may offer "
        "its own customer a new finance contract. So the fallback is a division of labour: the group supplies the "
        "timing (cohort-level, from public registers and the readiness engine, or customer-level under an Art 26 "
        "arrangement), the partner makes the contact.",
        "- **Leak 3 needs no partner's permission:** the buy-back commitments are the group's own, the price level is "
        "public, Aramis publishes realised prices, and a returned car's data can be read under the group's own "
        "contract with the rental firm or leasing company, which the Data Act treats as the car's user.",
    ]
    lines = [
        "# X20: data rights and fallbacks, source by source",
        "",
        f"_Generated by `analysis/data_reach.py`. The group's new-car registrations by Member State from the EU's CO2 "
        f"monitoring register (EEA, final {YEAR}, provisional {CHECK_YEAR}; the UK is not in it), its brands as "
        "`merger_diversification.py` tags them; the register routes and the map from X20 part 1's sources (register "
        "rows cited). Real data, nothing synthetic._",
        "",
        "## Checks",
        "",
        md_table(ck.assign(passes=ck["passes"].map({True: "yes", False: "NO"}))),
        "",
        f"All checks pass: {'yes' if all_ok else 'NO'}.",
        "",
        "## What it shows",
        "",
        *findings,
        "",
        "## 1. Which registers let the group check a sale independently",
        "",
        md_table(route_table),
        "",
        md_table(summary),
        "",
        "### The group's ten largest EU markets",
        "",
        md_table(markets),
        "",
        "## 2. The map: each source, its holder, its route and its fallback",
        "",
        md_table(source_map),
        "",
        "## Limits",
        "",
        "- **Routes were checked for six markets;** the rest are 'not checked', not 'closed'.",
        "- **The Netherlands' open data give the current keeper only** (the project's RDW trap), enough to see that a "
        "car left the dealer, not its whole history.",
        "- **The UK is outside the EU register;** the group's UK sales are not in these shares.",
        "- **A route is not a right to use:** each check still needs its GDPR basis (fraud prevention) and a balancing "
        "test, and each joint programme an Art 26 arrangement. The joint ventures' contract terms are not public.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(route_table.drop(columns=["source"]).to_string(index=False))
    print(summary.to_string(index=False))
    print(f"wrote {OUT.name}; checks pass: {all_ok}")


if __name__ == "__main__":
    main()
