"""X25 part 1: the programme's work list, checked and totalled.

`work_list.csv` holds the work every costing base prices: the roadmap's four 6-month phases x eleven workstreams x
roles, as the average number of full-time people in the phase, each row with the gates it serves and its basis. Every
figure in it is an ASSUMPTION (no source can size this exact programme); this script checks it and reads it:

1. The list is complete and well-formed: known roles, phases 1-4, a basis on every row, and every phase gate in the
   register staffed in its own phase.
2. Totals by phase, workstream and role, and by pay group (the occupation groups the wage data use).
3. A parametric check, COCOMO II.2000 (register rows `cocomo_*`): does the engineering part of the work fit a 24-month
   schedule, and what does compressing it cost? COCOMO sizes software work only, so it reads the engineering roles.
A gate named by its family (`gate_exit_floor_eur_m`) stands for its one-row-per-scenario register rows (X25).

Run from case4-value-model/: .venv/bin/python analysis/work_list.py (seconds). Writes analysis/work_list_report.md.
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PHASE_MONTHS = 6          # the roadmap: four phases of six months (solution doc 8.1; x21_phase_months)
PHASES = (1, 2, 3, 4)

# role -> (pay group in Eurostat's Structure of Earnings Survey, one-digit ISCO-08, and why)
ROLES = {
    "engineer": ("OC2", "data, software and integration engineers: ISCO 25, professionals"),
    "data_scientist": ("OC2", "data scientists and ML engineers: professionals"),
    "architect": ("OC2", "solution, data and security architects: professionals"),
    "product_owner": ("OC2", "product owners and business analysts: professionals"),
    "model_validator": ("OC2", "independent model validation (second line): professionals"),
    "legal_counsel": ("OC2", "data-protection and contract lawyers: ISCO 26, professionals"),
    "change_lead": ("OC2", "change, training and pilot leads: professionals"),
    "finance_analyst": ("OC2", "benefit certification in Finance: ISCO 24, professionals"),
    "programme_manager": ("OC1", "programme director and programme office leads: managers"),
    "data_steward": ("OC3", "review-queue data stewards: ISCO 3, technicians and associate professionals"),
}
ENGINEERING = ("engineer", "data_scientist", "architect")      # what COCOMO II sizes
NON_PHASE_GATES = {"gate_read_confidence_pct", "gate_read_power_pct"}   # apply to every gate, staffed by none


def register():
    with open(ROOT / "assumptions.csv", newline="", encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def load():
    with open(ROOT / "work_list.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check(rows, reg):
    problems = []
    for i, r in enumerate(rows, 2):
        if r["role"] not in ROLES:
            problems.append(f"line {i}: unknown role {r['role']!r}")
        if int(r["phase"]) not in PHASES:
            problems.append(f"line {i}: phase {r['phase']} outside 1-4")
        if not float(r["fte"]) > 0:
            problems.append(f"line {i}: FTE must be positive")
        if len(r["basis"].strip()) < 20:
            problems.append(f"line {i}: no basis")
        for g in filter(None, r["gates"].split(";")):
            if g not in reg and not family_rows(g, reg):
                problems.append(f"line {i}: gate {g} not in the register")
    # every phase gate is staffed in its own phase (the phase is the register label's "Phase n")
    for gid, g in reg.items():
        if not gid.startswith("gate_") or gid in NON_PHASE_GATES:
            continue
        fam = re.sub(r"_s\d(?=_(eur_m|pct)$)", "", gid)       # a per-scenario row is staffed through its family
        m = re.match(r"Phase (\d)", g["label"])
        if not m:
            problems.append(f"{gid}: no phase in its label")
            continue
        n = int(m.group(1))
        if not any(fam in r["gates"].split(";") and int(r["phase"]) == n for r in rows):
            problems.append(f"{gid}: Phase {n} gate with no staffed row in Phase {n}")
    return problems


def family_rows(family, reg):
    """The per-scenario register rows of a gate family: gate_exit_floor_eur_m -> gate_exit_floor_s1_eur_m, ..."""
    return [k for k in reg if re.sub(r"_s\d(?=_(eur_m|pct)$)", "", k) == family and k != family]


def fmt(x, d=1):
    return f"{x:,.{d}f}"


def main():
    reg, rows = register(), load()
    problems = check(rows, reg)
    val = lambda k: float(reg[k]["value"])
    by = defaultdict(float)
    for r in rows:
        f, p, ws, role = float(r["fte"]), int(r["phase"]), r["workstream"], r["role"]
        by[("phase", p)] += f
        by[("ws", ws, p)] += f
        by[("role", role, p)] += f
        by[("group", ROLES[role][0], p)] += f
    pm = lambda f: f * PHASE_MONTHS
    total_pm = pm(sum(by[("phase", p)] for p in PHASES))
    peak = max(by[("phase", p)] for p in PHASES)
    months = PHASE_MONTHS * len(PHASES)

    # COCOMO II.2000 on the engineering roles: E at nominal scale factors, the nominal schedule, and the compression
    a, b, c, d = (val(k) for k in ("cocomo_a", "cocomo_b", "cocomo_c", "cocomo_d"))
    e = b + 0.01 * val("cocomo_sf_nominal_sum")
    eng_pm = pm(sum(by[("role", ro, p)] for ro in ENGINEERING for p in PHASES))
    tdev = c * eng_pm ** (d + 0.2 * (e - b))
    ratio = months / tdev
    sced = ("none (at or beyond nominal)" if ratio >= 1 else
            f"between 1.00 and {val('cocomo_sced_85_em'):.2f} (between 85% and 100% of nominal)" if ratio >= 0.85 else
            f"between {val('cocomo_sced_85_em'):.2f} and {val('cocomo_sced_75_em'):.2f} (75% to 85% of nominal)" if ratio >= 0.75 else
            "beyond the model's range (under 75% of nominal)")
    # the same engineering effort that COCOMO would schedule in exactly 24 months
    pm_at_24 = (months / c) ** (1 / (d + 0.2 * (e - b)))

    out = ["# The programme's work list (X25 part 1)", "",
           "What every costing base prices: the roadmap's four 6-month phases x eleven workstreams x ten roles, in the",
           "average number of full-time people in each phase. **Every figure in `work_list.csv` is an ASSUMPTION** with",
           "its basis on the row; this report checks the list and reads it. Built by `analysis/work_list.py`.", "",
           "## Checks", ""]
    out += [f"- {p}" for p in problems] if problems else [
        f"- {len(rows)} rows, every one with a known role, a phase from 1 to 4, a positive FTE and a basis.",
        "- Every phase gate in the register (`gate_*`, except the two that apply to every gate) is staffed in its own",
        "  phase by at least one row that names it."]
    out += ["", "## People by phase (average FTE in the phase)", "",
            "| Workstream | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Person-months |", "|---|---:|---:|---:|---:|---:|"]
    for ws in sorted({r["workstream"] for r in rows}):
        v = [by[("ws", ws, p)] for p in PHASES]
        out.append(f"| {ws} | " + " | ".join(fmt(x) for x in v) + f" | {fmt(pm(sum(v)), 0)} |")
    v = [by[("phase", p)] for p in PHASES]
    out.append("| All workstreams | " + " | ".join(fmt(x) for x in v) + f" | {fmt(total_pm, 0)} |")
    out += ["", "## People by role", "",
            "| Role | Pay group | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Person-months |", "|---|---|---:|---:|---:|---:|---:|"]
    for role, (grp, why) in ROLES.items():
        v = [by[("role", role, p)] for p in PHASES]
        out.append(f"| {role} | {grp} | " + " | ".join(fmt(x) for x in v) + f" | {fmt(pm(sum(v)), 0)} |")
    out += ["", "| Pay group | Person-months | Share |", "|---|---:|---:|"]
    for grp, name in (("OC1", "Managers (OC1)"), ("OC2", "Professionals (OC2)"), ("OC3", "Technicians (OC3)")):
        g = pm(sum(by[("group", grp, p)] for p in PHASES))
        out.append(f"| {name} | {fmt(g, 0)} | {fmt(100 * g / total_pm)}% |")
    out += ["", "Pay groups are the one-digit ISCO-08 groups in which Eurostat's Structure of Earnings Survey publishes",
            "earnings by activity (`earn_ses22_49`): " + "; ".join(f"{k}: {v[1]}" for k, v in ROLES.items()) + ".",
            "", "## The work list in one table", "",
            "| Measure | Value |", "|---|---:|",
            f"| Person-months over the programme | {fmt(total_pm, 0)} |",
            f"| Average people over {months} months | {fmt(total_pm / months)} |",
            f"| Peak people in a phase | {fmt(peak)} |",
            f"| Engineering person-months (engineers, data scientists, architects) | {fmt(eng_pm, 0)} |",
            f"| Engineering share of all person-months | {fmt(100 * eng_pm / total_pm)}% |",
            "", "## COCOMO II.2000: does the engineering work fit 24 months?", "",
            "COCOMO II sizes software development, not governance, legal, change or finance work, so it reads only the",
            "engineering roles. It is used backwards: not to size the work (a prototype's code says nothing about a",
            "production system's size) but to ask whether the planned engineering effort fits the roadmap's schedule at",
            "the model's nominal settings.", "",
            "| COCOMO II.2000 reading | Value |", "|---|---:|",
            f"| Scale exponent E at nominal scale factors | {e:.4f} |",
            f"| Engineering effort (person-months) | {fmt(eng_pm, 0)} |",
            f"| Nominal schedule for that effort (months) | {tdev:.1f} |",
            f"| The roadmap's schedule as a share of nominal | {fmt(100 * ratio)}% |",
            f"| Engineering effort COCOMO would schedule in exactly {months} months | {fmt(pm_at_24, 0)} |", "",
            f"Schedule compression effort multiplier (SCED, Table 34): {sced}. "
            f"TDEV = C x PM^(D + 0.2 (E - B)), with A, B, C, D and the scale factors from the register (`cocomo_*`).",
            "", "## What this is and is not", "",
            "- It is the programme's own team. Business-as-usual staff are not charged: the people who decide held",
            "  claims, the pricers and the dealers' staff do their jobs with the new tools; the change workstream pays",
            "  for their training.",
            "- It is one list for every base. Base 1 prices it at in-house wages, base 2 at vendor prices and an",
            "  integrator's rates, base 3 with AI tools on the share of each role's work the studies measured.",
            "- The rows carry no ranges. Stacking a guessed range on every guessed cell would add invented numbers; the",
            "  uncertainty enters once, at the total, from sourced reference classes (McKinsey-Oxford's overruns, the",
            "  Green Book's optimism bias) and from this report's COCOMO check.",
            "- Three roadmap gates have no register row (the monthly mark against the retailer's realised prices, the",
            "  engine recalibrated on backfilled returns, the legal basis for each source); their rows name them in the",
            "  basis instead."]
    (HERE / "work_list_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:12]) if problems else f"work list: {len(rows)} rows, {fmt(total_pm, 0)} person-months, "
          f"engineering {fmt(eng_pm, 0)}; COCOMO nominal schedule {tdev:.1f} months ({fmt(100 * ratio)}% of it used)")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
