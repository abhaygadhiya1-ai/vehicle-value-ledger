"""X25 parts 4-7: the programme's build cost in four scenarios, from one work list, and its reading.

The same arithmetic as the workbook's "Programme cost" and "Work list" sheets, written apart from the builder so the
audit can check one against the other (as analysis/benefits_case.py does for the Benefits sheet).

The four bases price the same work (`work_list.csv`, part 1):
  1. In-house, no AI: person-months x the loaded cost of an employee (register `x25_loaded_*`, Eurostat) x overhead.
     The central team sits in France and Italy (`x25_loc_fr_pct`); data stewards and change leads sit in the four core
     markets once those markets are live (Phase 3 on).
  2. Buy and outsource: an integrator delivers the build roles at a public rate card (Deloitte's G-Cloud 14, the
     ceiling, UK); the group keeps the roles it cannot hand over (legal counsel, Finance's certification, independent
     model validation) at base 1's cost.
  3. In-house with AI (part 4): base 1 less the time the evidence says AI saves, plus the tools' seats. Engineers and
     data scientists save on the share of their week that coding, debugging and review take (Microsoft's Time Warp),
     at the gain each study measured: central Cui et al. (field experiments), upper Peng et al. (one task), adverse
     METR 2025 (experienced developers slower). Every other role saves the time Danish chatbot adopters report
     (Humlum & Vestergaard), with no adverse gain. A saving becomes a cost saving only because the team is sized to it.
  4. The cheapest route per workstream: for each workstream the cheapest of bases 1-3 (central), except the value logic
     (the per-car store and the value engine), which the group always builds.
Platform, data and licences (`inv_platform_eur_m`) and change delivery beyond the programme's own change leads
(`inv_change_eur_m`) are the same in every base.

Run from case4-value-model/: .venv/bin/python analysis/programme_cost.py (seconds). Writes programme_cost_report.md.
"""
import csv
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

from work_list import ROLES  # noqa: E402  (the pay group of each role; one home)

PHASES = (1, 2, 3, 4)
CORE = ("fr", "it", "de", "es")
MARKET_FACING = ("data_steward", "change_lead")          # in the markets once they are live
CODERS = ("engineer", "data_scientist")                 # the roles the coding studies measured
ALWAYS_BUILT = ("ws01", "ws04")                         # the per-car store and the value engine
# base 2: the rate-card level each handed-over role is bought at (Deloitte G-Cloud 14, SFIA)
INTEGRATOR = {"engineer": "dl_gc14_dev_l4_gbp_day", "data_scientist": "dl_gc14_dev_l5_gbp_day",
              "architect": "dl_gc14_arch_l5_gbp_day", "product_owner": "dl_gc14_arch_l4_gbp_day",
              "change_lead": "dl_gc14_arch_l4_gbp_day", "programme_manager": "dl_gc14_arch_l6_gbp_day",
              "data_steward": "dl_gc14_dev_l3_gbp_day"}
KEPT = ("legal_counsel", "finance_analyst", "model_validator")
CASES = ("central", "upper", "adverse")
# The four build scenarios, shown side by side; none is chosen (the user, 27 September)
SCENARIOS = [("b1", "1. In-house, no AI"), ("b2", "2. Buy and outsource"), ("b3", "3. In-house with AI"),
             ("b4", "4. Cheapest route per workstream")]


def register():
    with open(ROOT / "assumptions.csv", newline="", encoding="utf-8") as f:
        return {r["id"]: float(r["value"]) for r in csv.DictReader(f) if r["value"]}


def work():
    with open(ROOT / "work_list.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def where(role, phase):
    return "markets" if role in MARKET_FACING and phase >= 3 else "central"


def rates(V):
    """Per role: EUR a month in-house (central, in the markets, in the hub), from an integrator, the AI saving by
    case, and the tools' seats a month."""
    oh = 1 + V["x25_overhead_pct"] / 100
    days_month = V["x25_days_per_fte_year"] / 12
    fr = V["x25_loc_fr_pct"] / 100
    touched = (V["ai_timewarp_coding_pct"] + V["ai_timewarp_debugging_pct"] + V["ai_timewarp_review_pct"]) / 100
    effect = {"central": 1 - 1 / (1 + V["ai_cui_tasks_pct"] / 100), "upper": V["ai_peng_faster_pct"] / 100,
              "adverse": -V["ai_metr25_time_pct"] / 100}
    out = {}
    for role, (grp, _) in ROLES.items():
        L = lambda cc: V[f"x25_loaded_{grp.lower()}_{cc}_eur"]
        r = {"central": (fr * L("fr") + (1 - fr) * L("it")) / 12 * oh,
             "markets": sum(L(cc) for cc in CORE) / 4 / 12 * oh,
             "hub": L("pl") / 12 * oh,
             "integrator": V[INTEGRATOR[role]] / V["x25_gbp_per_eur"] * days_month if role in INTEGRATOR else None,
             "seat": ((V["gh_copilot_enterprise_usd_user_month"] if role in CODERS else 0)
                      + V["claude_team_std_usd_seat_month"]) / V["x25_usd_per_eur"]}
        for c in CASES:
            r[f"save_{c}"] = touched * effect[c] if role in CODERS else (V["hv_time_savings_pct"] / 100 if c != "adverse" else 0)
        out[role] = r
    return out


def model(V, rows):
    R = rates(V)
    pm_month = V["x21_phase_months"]
    days_month = V["x25_days_per_fte_year"] / 12
    lines = []
    for w in rows:
        role, p, fte = w["role"], int(w["phase"]), float(w["fte"])
        pm = fte * pm_month
        r, loc = R[role], where(role, int(w["phase"]))
        c = {"ws": w["workstream"], "phase": p, "role": role, "pm": pm, "b1": pm * r[loc] / 1e6}
        c["b2"] = pm * r["integrator"] / 1e6 if role in INTEGRATOR else c["b1"]
        for k in CASES:
            s = r[f"save_{k}"]
            c[f"b3_people_{k}"] = pm * (1 - s) * r[loc] / 1e6
            c[f"b3_tools_{k}"] = pm * (1 - s) * r["seat"] / 1e6
        c["b3"] = c["b3_people_central"] + c["b3_tools_central"]
        # sensitivities: the integrator's days at Consip's Italian public team-day; its engineers offshore; the
        # in-house coders in the lower-cost hub (coordination overhead not costed)
        c["b2_consip"] = pm * V["consip_svi_eur_team_day"] * days_month / 1e6 if role in INTEGRATOR else c["b1"]
        c["b2_offshore"] = (pm * V["dl_gc14_off_dev_l4_gbp_day"] / V["x25_gbp_per_eur"] * days_month / 1e6
                            if role == "engineer" else c["b2"])
        c["b1_hub"] = pm * r["hub"] / 1e6 if role in CODERS else c["b1"]
        c["b1_no_oh"] = c["b1"] / (1 + V["x25_overhead_pct"] / 100)
        lines.append(c)

    tot = lambda key, f=lambda c: True: sum(c[key] for c in lines if f(c))
    fixed = V["inv_platform_eur_m"] + V["inv_change_eur_m"]
    ws_ids = sorted({c["ws"] for c in lines})
    per_ws = {}
    for ws in ws_ids:
        inw = lambda c, ws=ws: c["ws"] == ws
        b = {"b1": tot("b1", inw), "b2": tot("b2", inw), "b3": tot("b3", inw)}
        allowed = ("b1", "b3") if ws.startswith(ALWAYS_BUILT) else ("b1", "b2", "b3")
        pick = min(allowed, key=lambda k: b[k])
        per_ws[ws] = {**b, "rule": "always built" if ws.startswith(ALWAYS_BUILT) else "cheapest", "pick": pick,
                      "b4": b[pick]}
    for c in lines:
        c["b4"] = c[per_ws[c["ws"]]["pick"]]
    base = {
        "b1": {"people": tot("b1"), "tools": 0.0},
        "b2": {"people": tot("b2"), "tools": 0.0},
        "b3": {"people": tot("b3_people_central"), "tools": tot("b3_tools_central")},
        "b3_upper": {"people": tot("b3_people_upper"), "tools": tot("b3_tools_upper")},
        "b3_adverse": {"people": tot("b3_people_adverse"), "tools": tot("b3_tools_adverse")},
        "b4": {"people": sum(v["b4"] for v in per_ws.values()), "tools": 0.0},
        "b2_consip": {"people": tot("b2_consip"), "tools": 0.0},
        "b2_offshore": {"people": tot("b2_offshore"), "tools": 0.0},
        "b1_hub": {"people": tot("b1_hub"), "tools": 0.0},
    }
    for b in base.values():
        b["platform"], b["change"] = V["inv_platform_eur_m"], V["inv_change_eur_m"]
        b["total"] = b["people"] + b["tools"] + fixed
    by_phase = {k: [tot(k, lambda c, p=p: c["phase"] == p) + fixed / 4 for p in PHASES]
                for k in ("b1", "b2", "b3", "b4")}
    # switching values
    oh = V["x25_overhead_pct"] / 100
    A1 = tot("b1_no_oh")                                      # base 1 people before overhead
    kept = lambda c: c["role"] not in INTEGRATOR
    A2r = tot("b1_no_oh", kept)                               # the roles base 2 keeps, before overhead
    S = tot("b2", lambda c: c["role"] in INTEGRATOR)          # the integrator's bill
    int_days = sum(c["pm"] for c in lines if c["role"] in INTEGRATOR) * days_month
    switch = {"overhead_pct": 100 * (S / (A1 - A2r) - 1),
              "day_rate_eur": (base["b1"]["people"] - tot("b2", kept)) * 1e6 / int_days,
              "integrator_days": int_days}
    return {"rates": R, "lines": lines, "per_ws": per_ws, "base": base, "by_phase": by_phase, "switch": switch,
            "pm": tot("pm"), "fixed": fixed, "overhead": oh}


# ---------------------------------------------------------------------------------------------- part 6: reading it
CAP_ROLES = ("engineer", "data_scientist", "architect")          # create the software (IAS 38; the 20-F's policy)
CAP_WS = ("ws01", "ws02", "ws03", "ws04", "ws05", "ws06", "ws07", "ws08")   # the software workstreams


def bounds():
    with open(ROOT / "assumptions.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return ({r["id"]: float(r["low"]) for r in rows if r["low"]}, {r["id"]: float(r["high"]) for r in rows if r["high"]})


def reading(V, rows, M):
    """Each base's build schedule read through X21's own benefit model (analysis/benefits_case.py): value, payback,
    cash lost if stopped at each gate, the overlay cases; plus the hiring lag that would flip the choice, the share
    that can be capitalised, the pay premium at which in-house costs as much as buying, and the assumption ranges."""
    import benefits_case as bc
    cases = bc.cases(V)
    r_lo, r_hi = V["stla_wacc_pretax_low_pct"], V["stla_wacc_pretax_high_pct"]
    h5, h10 = 12 * V["gb_appraisal_it_example_years"], 12 * V["gb_appraisal_default_years"]
    sched = {k: M["by_phase"][k] for k, _ in SCENARIOS}
    sched["bridge"] = [M["by_phase"]["b2"][0]] + M["by_phase"]["b4"][1:]      # a what-if, not a scenario

    def npv(costs, case="plan", h=h5, rate=r_hi, delay=0.0):
        """NPV at the start; a hiring delay shifts the whole programme later and leaves less of the horizon."""
        return bc.pv(V, cases[case], h - delay, rate, costs=costs)["npv"] / (1 + rate / 100) ** (delay / 12)

    out = {"sched": sched, "value": {}, "rates": (r_lo, r_hi), "horizons": (h5, h10)}
    for k, costs in sched.items():
        out["value"][k] = {"build": sum(costs), "payback": bc.payback_month(V, cases["plan"], costs=costs),
                           "stops": bc.stop_losses(V, cases["plan"], costs=costs),
                           "npv": {(c, h, r): npv(costs, c, h, r) for c in cases for h in (h5, h10) for r in (r_lo, r_hi)}}

    # the in-house hiring lag at which buying time pays: base 4 started d months late against a start at once
    def lag(rival, case="plan"):
        target = npv(sched[rival], case)
        f = lambda d: npv(sched["b4"], case, delay=d) - target
        if f(0) <= 0:
            return 0.0
        lo, hi = 0.0, 24.0
        if f(hi) > 0:
            return None
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
        return (lo + hi) / 2
    out["lag"] = {(rival, case): lag(rival, case) for rival in ("bridge", "b2")
                  for case in ("plan", "reference class", "stress, 50% of benefits")}

    # what can be capitalised: the engineering roles' cost in the software workstreams, in-house or bought (the group
    # controls the software either way, so the IFRIC SaaS decision does not apply); seats, platform subscriptions,
    # change, governance, pilots and programme management are expensed
    cap_key = {"b1": "b1", "b2": "b2", "b3": "b3_people_central"}
    cap = {}
    for k in ("b1", "b2", "b3", "b4"):
        def line_cost(c, k=k):
            if k != "b4":
                return c[cap_key[k]]
            pick = M["per_ws"][c["ws"]]["pick"]
            return c[cap_key[pick]]
        c_sum = sum(line_cost(c) for c in M["lines"] if c["role"] in CAP_ROLES and c["ws"][:4] in CAP_WS)
        cap[k] = {"cap": c_sum, "total": M["base"][k]["total"], "share": c_sum / M["base"][k]["total"]}
    out["cap"] = cap

    # the pay premium over the occupation-group mean, on every in-house professional (OC2) role, at which in-house
    # (base 1) costs as much as buying the build (base 2): a premium on the roles base 2 keeps moves both sides
    target = M["base"]["b2"]["people"]
    oc2 = sum(c["b1"] for c in M["lines"] if ROLES[c["role"]][0] == "OC2")
    oc2_kept = sum(c["b1"] for c in M["lines"] if ROLES[c["role"]][0] == "OC2" and c["role"] not in INTEGRATOR)
    rest = M["base"]["b1"]["people"] - oc2
    # base 1 at premium p: rest + oc2 (1 + p); base 2 at p: target + oc2_kept p
    out["premium"] = {"b1_vs_b2": 100 * (target - rest - oc2) / (oc2 - oc2_kept)}

    # the assumption ranges this model adds (the register's low and high)
    lo, hi = bounds()
    sens = {}
    for rid in ("x25_overhead_pct", "x25_loc_fr_pct", "x25_days_per_fte_year"):
        sens[rid] = {end: model(dict(V, **{rid: val[rid]}), rows)["base"] for end, val in (("low", lo), ("high", hi))}
    out["sens"] = sens
    return out

def fm(x, d=1):
    return f"{x:,.{d}f}"


def report(V, rows, M):
    R, B = M["rates"], M["base"]
    out = ["# The programme's build cost on four bases (X25 parts 4-6)", "",
           "The same work list (`work_list.csv`, part 1) priced four ways; EUR millions over the 24-month build unless",
           "stated. The workbook's \"Programme cost\" and \"Work list\" sheets hold the same arithmetic as formulas, and the",
           "audit checks them against this script. Built by `analysis/programme_cost.py`.", "",
           "## Part 4: what AI saves, by role", "",
           "Engineers and data scientists: the share of the week coding, debugging and review take (Time Warp, about "
           f"{fm(V['ai_timewarp_coding_pct'] + V['ai_timewarp_debugging_pct'] + V['ai_timewarp_review_pct'], 0)}%) times each "
           "study's gain. Central: Cui et al.'s field experiments (more completed tasks, read as less time a task). Upper: "
           "Peng et al.'s single task. Adverse: METR's early-2025 trial, where experienced developers took longer. Every "
           "other role: the time Danish chatbot adopters report saving (Humlum & Vestergaard), with none in the adverse "
           "case. Seats: Copilot Enterprise for the coders plus a Claude Team seat for everyone, converted at the ECB rate.",
           "", "| Role | Saving, central | Saving, upper | Saving, adverse | Seats (EUR a month) |",
           "|---|---:|---:|---:|---:|"]
    for role, r in R.items():
        out.append(f"| {role} | {fm(100 * r['save_central'])}% | {fm(100 * r['save_upper'])}% | "
                   f"{fm(100 * r['save_adverse'])}% | {fm(r['seat'], 2)} |")
    out += ["", "## What a person-month costs, by role (EUR)", "",
            "In-house: the loaded cost of an employee in manufacturing (Eurostat), plus overhead, where the role sits. "
            "Integrator: the public rate card's day rate (Deloitte, G-Cloud 14, UK, a ceiling) in euros, times the working "
            "days in a month. Blank: the group keeps the role.", "",
            "| Role | In-house, central team | In-house, in the four markets | In-house, the hub | Integrator |",
            "|---|---:|---:|---:|---:|"]
    for role, r in R.items():
        integ = fm(r["integrator"], 0) if r["integrator"] else ""
        out.append(f"| {role} | {fm(r['central'], 0)} | {fm(r['markets'], 0)} | {fm(r['hub'], 0)} | {integ} |")
    out += ["", "## The four bases", "",
            "| Base | People | AI tools | Platform, data and licences | Change delivery | Total |",
            "|---|---:|---:|---:|---:|---:|"]
    names = {"b1": "1. In-house, no AI", "b2": "2. Buy and outsource (rate card)", "b3": "3. In-house with AI, central",
             "b3_upper": "3. In-house with AI, upper gain", "b3_adverse": "3. In-house with AI, adverse",
             "b4": "4. Cheapest route per workstream", "b2_consip": "2 at Consip's Italian public team-day",
             "b2_offshore": "2 with the integrator's engineers offshore", "b1_hub": "1 with the coders in the hub"}
    for k, n in names.items():
        b = B[k]
        out.append(f"| {n} | {fm(b['people'])} | {fm(b['tools'], 2)} | {fm(b['platform'])} | {fm(b['change'])} | "
                   f"{fm(b['total'])} |")
    out += ["", "Base 4 carries base 3's tools within its people column (each workstream's cost is priced whole).", "",
            "## Base 4: each workstream's cheapest route", "",
            "| Workstream | Base 1 | Base 2 | Base 3 | Rule | Chosen | Base 4 |", "|---|---:|---:|---:|---|---|---:|"]
    lab = {"b1": "in-house", "b2": "integrator", "b3": "in-house with AI"}
    for ws, v in M["per_ws"].items():
        out.append(f"| {ws} | {fm(v['b1'], 2)} | {fm(v['b2'], 2)} | {fm(v['b3'], 2)} | {v['rule']} | {lab[v['pick']]} | "
                   f"{fm(v['b4'], 2)} |")
    s = M["switch"]
    out += ["", "## Switching values", "",
            "| Switching value | Value |", "|---|---:|",
            f"| Overhead on in-house cost at which bases 1 and 2 cost the same (%) | {fm(s['overhead_pct'])} |",
            f"| One integrator day rate for every handed-over role at which bases 1 and 2 cost the same (EUR) | "
            f"{fm(s['day_rate_eur'], 0)} |",
            f"| Integrator days in base 2 | {fm(s['integrator_days'], 0)} |", "",
            "## By phase (EUR m; platform and change delivery spread evenly)", "",
            "| Base | Phase 1 | Phase 2 | Phase 3 | Phase 4 |", "|---|---:|---:|---:|---:|"]
    for k in ("b1", "b2", "b3", "b4"):
        out.append(f"| {names[k]} | " + " | ".join(fm(x) for x in M["by_phase"][k]) + " |")
    out += reading_report(V, M, reading(V, rows, M))
    out += ["", "## What this is and is not", "",
            "- Build cost only, over the 24 months. The run cost after month 24, the risk overlay, time to benefit, NPV,",
            "  spend at each gate and the accounting view are part 6's reading.",
            "- Base 2's rates are a UK public framework's maximums: a ceiling. The switching day rate says how far an",
            "  integrator's price must fall before handing the work over is cheaper; Consip's Italian public team-day is a",
            "  floor far below any carmaker's market, shown only as the other end.",
            "- Base 3's saving counts only because the teams are sized to it: most chatbot users move saved time to other",
            "  tasks (`hv_reallocated_pct`). No adoption or training cost is counted; none is sourced.",
            "- The hub line moves engineers and data scientists to the lower-cost hub's pay and counts no coordination",
            "  cost; no source sizes one, so it is an upper bound on the saving."]
    return out


def reading_report(V, M, X):
    B = M["base"]
    r_lo, r_hi = X["rates"]
    h5, h10 = X["horizons"]
    nm = dict(SCENARIOS, bridge="What-if: 4, with an integrator for Phase 1")
    pb = lambda x: "none within ten years" if x is None else fm(x)
    out = ["", "## Part 6: reading it", "",
           "Each scenario's build schedule read through X21's own benefit model (`analysis/benefits_case.py`: the same",
           "benefits, run cost, horizons and overlay cases); only the build cost by phase changes. Rates are the group's",
           f"pre-tax WACC range ({fm(r_lo)}% and {fm(r_hi)}%); the benefits case is judged at the high end. No scenario is",
           "chosen: each is shown."]
    out += ["", "### Value, payback and cash at risk by scenario", "",
            f"NPV in EUR m at {fm(r_hi)}% (the plan and the reference class: McKinsey-Oxford's overruns on cost, schedule and "
            "benefits), payback in months (the plan), and cash lost if the programme stops at the end of Phase 1 or 2.", "",
            f"| Scenario | Build | Payback | NPV, {fm(h5 / 12, 0)} years | NPV, {fm(h10 / 12, 0)} years | "
            f"NPV, {fm(h5 / 12, 0)} years, reference class | Lost if stopped after Phase 1 | Lost if stopped after Phase 2 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for k, v in X["value"].items():
        n = v["npv"]
        out.append(f"| {nm[k]} | {fm(v['build'])} | {pb(v['payback'])} | {fm(n[('plan', h5, r_hi)])} | "
                   f"{fm(n[('plan', h10, r_hi)])} | {fm(n[('reference class', h5, r_hi)])} | {fm(v['stops'][0])} | "
                   f"{fm(v['stops'][1])} |")
    lag = lambda x: "never within 24 months" if x is None else fm(x)
    out += ["", "### Hiring lag: when buying time pays", "",
            "No public source gives months to hire data specialists (Eurostat measures only how many recruiters find "
            "vacancies hard to fill: `x25_ict_hardfill_*`), so the lag is read as a switching value: how late an in-house "
            f"start (base 4) could be before a start at once is worth its price, at {fm(r_hi)}% over {fm(h5 / 12, 0)} years.", "",
            "| In-house hiring lag at which it pays to buy, months | The plan | The reference class | Stress, 50% of benefits |",
            "|---|---:|---:|---:|",
            f"| An integrator for Phase 1 only | " + " | ".join(lag(X['lag'][('bridge', c)]) for c in
                ("plan", "reference class", "stress, 50% of benefits")) + " |",
            f"| The whole build bought | " + " | ".join(lag(X['lag'][('b2', c)]) for c in
                ("plan", "reference class", "stress, 50% of benefits")) + " |",
            "", "The integrator's own mobilisation is not costed: the lag is the head start an integrator must have over "
            "the in-house team, so a slower integrator needs a longer in-house lag to pay.",
            "", "### The accounting view", "",
            "The group's 2025 20-F capitalises the part of internal-use software development that is \"directly "
            "attributable internal or external costs necessary to create the software or improve its performance\" and "
            "expenses the rest. The engineering roles' cost in the software workstreams (ws01-ws08) is capitalisable in "
            "every base: the group controls the software whether its staff or an integrator builds it, so the IFRIC SaaS "
            "decision does not apply. Seats, platform subscriptions, change, governance, pilots and programme management "
            "are expensed. The 20-F states no useful life for internal-use software.", "",
            "| Base | Capitalisable (EUR m) | Expensed in the build (EUR m) | Capitalisable share |", "|---|---:|---:|---:|"]
    for k, c in X["cap"].items():
        out.append(f"| {nm[k]} | {fm(c['cap'])} | {fm(c['total'] - c['cap'])} | {fm(100 * c['share'])}% |")
    out += ["", "### Pay and assumptions", "",
            "| Switching value | Value |", "|---|---:|",
            f"| Pay premium over the occupation-group mean, every in-house professional, at which base 1 costs as much as "
            f"base 2 (%) | {fm(X['premium']['b1_vs_b2'])} |",
            "", "| Assumption at its low and high end | Base 1, low | Base 1, high | Base 2, low | Base 2, high | "
            "Base 4, low | Base 4, high |", "|---|---:|---:|---:|---:|---:|---:|"]
    for rid, v in X["sens"].items():
        out.append(f"| {rid} | {fm(v['low']['b1']['total'])} | {fm(v['high']['b1']['total'])} | "
                   f"{fm(v['low']['b2']['total'])} | {fm(v['high']['b2']['total'])} | {fm(v['low']['b4']['total'])} | "
                   f"{fm(v['high']['b4']['total'])} |")
    return out

def main():
    V, rows = register(), work()
    M = model(V, rows)
    (HERE / "programme_cost_report.md").write_text("\n".join(report(V, rows, M)) + "\n", encoding="utf-8")
    B = M["base"]
    print("  ".join(f"{k} {B[k]['total']:.1f}" for k in ("b1", "b2", "b3", "b3_upper", "b3_adverse", "b4")))
    print(f"switching: overhead {M['switch']['overhead_pct']:.0f}%, day rate EUR {M['switch']['day_rate_eur']:.0f}")


if __name__ == "__main__":
    main()
