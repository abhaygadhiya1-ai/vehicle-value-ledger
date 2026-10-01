"""X21: the benefits case. Benefits by lever, payback by build scenario, the exit gate derived.

Skeptic F1: the chain jumped from risk to ask. This sizes what the programme gets back, lever by lever, on X20's reach,
in the headline's two measures (X18), and tests it the way the Green Book and the IT-project literature say a case
should be tested: against a reference class, a stress, and switching values.

- **Levers, each euro in one class.** Recovered and counted: claims controls (the claims line times
  `recoverable_share`), retention (leak 2), resale execution (X17). An upper bound that needs a holdout: income
  targeting (X5), shown, never committed. Tail reduced: the engine on little-history cars, one year in ten only. Priced, not
  recovered (the level charge, the cold premium) and enablers (the transfer price, the metric, the band): no euro.
- **Ramp.** The roadmap's phases (solution doc 8.1): nothing in Phase 1 (the baseline is being certified); claims
  controls in the pilot market in Phase 2; retention, resale execution and the little-history engine in the core markets
  from Phase 3; targeting from Phase 4; every market after the exit. Coverage is the group's share of registrations
  (EU and EFTA, the UK not in the file): the pilot is France (X14), the core markets the four above the break.
- **Cases.** Plan; reference class (McKinsey-Oxford's software row: benefits short, cost over, phases longer); the
  Flyvbjerg-Budzier stress (cost +400%, 25-50% of benefits). Build cost follows each of X25's four build scenarios
  (analysis/programme_cost.py: the work list priced in-house, bought, in-house with AI, and the cheapest route per
  workstream), phase by phase; the run cost starts at the exit. No scenario is chosen: each is shown.
- **Judged** on the reference class over the Green Book's five-year IT example at the group's highest pre-tax WACC,
  and shown at the low WACC and over ten years. Switching values are the Green Book's method for benefits (4.1).
- **The exit gate** is the reference-class run rate of the committed levers in the markets live at month 24 (the same
  in every scenario). The floor below which the programme does not repay itself, the Phase 1 switch trigger and the
  Phase 2 money gate depend on build cost, so each has one value per scenario (X22).

`model(V)` holds the arithmetic so `audit_workbook.py` can check the workbook's formulas against it.

Usage: .venv/bin/python analysis/benefits_case.py   (writes analysis/benefits_case_report.md; seconds)
"""
import csv
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import merger_diversification as md  # noqa: E402

REGISTER = HERE.parent / "assumptions.csv"
WORKBOOK = HERE.parent.parent / "Case4_Value_at_Risk.xlsx"
CACHE = HERE.parent / "data" / "reference" / "x9_eea_registrations_fuel.parquet"
OUT = HERE / "benefits_case_report.md"
YEAR, CHECK_YEAR = 2024, 2025
PILOT = "FR"          # X14 sized the Phase 2 pilot in France (x14_pilot_share_fr)
PHASES = 4
POST_YEARS = 9        # enough years after the exit to cover a ten-year horizon
REACH = ("every", "no_jv", "no_dealer")
REACH_LABEL = {"every": "every source", "no_jv": "without the joint ventures' data",
               "no_dealer": "without dealers' VIN-level evidence"}
# The roadmap (solution doc 8.1): the first phase each lever earns in. Committed levers count in the cash case.
LEVERS = [  # key, label, class, starts in phase, committed
    ("claims", "Claims controls", "recovered", 2, True),
    ("retention", "Retention at the upgrade moment", "recovered", 3, True),
    ("exec_days", "Resale execution: days cut", "recovered", 3, True),
    ("exec_route", "Resale execution: own retail", "recovered", 3, True),
    ("targeting", "Income targeting (X5)", "upper bound, needs a holdout", 4, False),
    ("tail", "Little-history cars priced as known cars", "tail reduced, one year in ten", 3, False),
]
GATE_OF = {"claims": "Phase 1: duplicate precision and the certified leakage baseline (gate_dup_*)",
           "retention": "Phase 2: uplift over a randomised control group (gate_uplift_pp)",
           "exec_days": "Phase 3: days to sale on returns against the pre-programme record (X22)",
           "exec_route": "Phase 3: retail margin per routed car against the trade (X22)",
           "targeting": "Phase 3: randomised incentive holdouts",
           "tail": "Phase 3: little-history error (kpi_thin_error_points)"}


def register(col="value"):
    return {r["id"]: float(r[col]) for r in csv.DictReader(open(REGISTER, encoding="utf-8")) if r[col]}


def run_rates(V, reach="every"):
    """Each lever's yearly benefit at full coverage, EUR m, as the workbook's formulas have it."""
    claims_line = V["eu_revenue_eur_m"] * V["x14_incentive_claims_central"] / 100 * V["process_leak_pct"] / 100
    book = V["buyback_payables_current_eur_m"]
    return {
        "claims": claims_line * V["recoverable_share"] / 100
        * (V["x20_reg_route_any_2024"] / 100 if reach == "no_dealer" else 1),
        "retention": 0.0 if reach == "no_jv" else
        V["sfse_eu_nv_contracts_2025"] * V["upgrade_capture_uplift"] / 100 * V["margin_per_repeat_sale"] / 1e6,
        "exec_days": book * V["x17_days_cut"] * V["x17_day_cost_central"] / 10000,
        "exec_route": book * V["x17_share_routed"] / 100 * V["x17_channel_gain_after_costs"] / 100,
        "targeting": V["eu_revenue_eur_m"] * V["x5_targeting_gain_central"] / 100
        * (V["x14_agency_share_2025p"] if reach == "no_jv" else V["finance_penetration"]) / 100,
        "tail": book * V["thin_share_of_book"] / 100 * (V["curve_1y_p80_unknown"] - V["curve_1y_p80_known"]) / 2
        / V["retained_1y_pooled"] * V["x18_joint_share_book"] / 100,
    }


def coverage(V, phase):
    """Share of the group's volume live in a phase; after the exit, everything."""
    return {1: 0.0, 2: V["x21_cov_pilot_2024"] / 100, 3: V["x21_cov_core_2024"] / 100,
            4: V["x21_cov_core_2024"] / 100}.get(phase, 1.0)


def cases(V):
    m = V["x21_phase_months"]
    slow = m * (1 + V["mckox_sw_schedule_overrun_pct"] / 100)
    return {
        "plan": dict(b=1.0, c=1.0, m=m),
        "reference class": dict(b=1 - V["mckox_sw_benefit_shortfall_pct"] / 100,
                                c=1 + V["mckox_sw_cost_overrun_pct"] / 100, m=slow),
        "stress, 25% of benefits": dict(b=V["fb_stress_benefit_low_pct"] / 100,
                                        c=1 + V["fb_stress_cost_overrun_pct"] / 100, m=slow),
        "stress, 50% of benefits": dict(b=V["fb_stress_benefit_high_pct"] / 100,
                                        c=1 + V["fb_stress_cost_overrun_pct"] / 100, m=slow),
    }


def periods(V, case, horizon_months, reach="every", costs=None):
    """Cash by period: four phases, then years after the exit. Each row: label, start and length (months), build
    cost (paid at the start), benefit by lever and run cost (accrued evenly), all EUR m, clipped to the horizon.
    `costs`: the build cost of each phase (a scenario's schedule)."""
    rates = run_rates(V, reach)
    b, c, m = case["b"], case["c"], case["m"]
    out = []
    for p in range(1, PHASES + 1):
        start = (p - 1) * m
        f = max(0.0, min(1.0, (horizon_months - start) / m))
        ben = {k: b * rates[k] * coverage(V, p) * m / 12 * f
               for k, _, _, s, com in LEVERS if com and p >= s}
        out.append(dict(label=f"Phase {p}", start=start, length=m * f, cost=c * costs[p - 1] if f else 0,
                        ben=ben, run=0.0))
    for j in range(1, POST_YEARS + 1):
        start = PHASES * m + 12 * (j - 1)
        f = max(0.0, min(1.0, (horizon_months - start) / 12))
        ben = {k: b * rates[k] * f for k, _, _, s, com in LEVERS if com}
        out.append(dict(label=f"Year {j} after the exit", start=start, length=12 * f, cost=0.0, ben=ben,
                        run=V["run_cost_eur_m_year"] * f))
    return out


def pv(V, case, horizon_months, rate_pct, reach="every", costs=None):
    """Present values at the start: build cost at each phase's start, benefits and run cost at the middle of the
    part of each period inside the horizon."""
    r = rate_pct / 100
    out = {"build": 0.0, "run": 0.0, "ben": {k: 0.0 for k, *_ in LEVERS}}
    for x in periods(V, case, horizon_months, reach, costs):
        if x["length"] <= 0:
            continue
        mid = (x["start"] + x["length"] / 2) / 12
        out["build"] += x["cost"] / (1 + r) ** (x["start"] / 12)
        out["run"] += x["run"] / (1 + r) ** mid
        for k, v in x["ben"].items():
            out["ben"][k] += v / (1 + r) ** mid
    out["ben_total"] = sum(out["ben"].values())
    out["npv"] = out["ben_total"] - out["build"] - out["run"]
    return out


def payback_month(V, case, reach="every", costs=None):
    """The month cumulative cash turns positive: build cost paid at each phase's start, benefits and run cost
    accrued evenly. None if not within the longest horizon."""
    cum = 0.0
    for x in periods(V, case, 12 * V["gb_appraisal_default_years"], reach, costs):
        cum -= x["cost"]
        net = sum(x["ben"].values()) - x["run"]
        if cum < 0 <= cum + net and net > 0:
            return x["start"] + x["length"] * (-cum / net)
        cum += net
    return None if cum < 0 else 0.0


def stop_losses(V, case, reach="every", costs=None):
    """Cash lost if the programme stops at the end of each phase: build cost released so far less benefits
    earned so far (benefits stop too)."""
    out, cum = [], 0.0
    for x in periods(V, case, 12 * V["gb_appraisal_default_years"], reach, costs)[:PHASES]:
        cum += x["cost"] - sum(x["ben"].values())
        out.append(cum)
    return out


SWITCH = [  # assumption, the lever part its benefit is proportional to
    ("process_leak_pct", "claims"), ("recoverable_share", "claims"),
    ("upgrade_capture_uplift", "retention"), ("margin_per_repeat_sale", "retention"),
    ("x17_days_cut", "exec_days"), ("x17_share_routed", "exec_route")]
# Every assumed rate at the end of its register range that hurts the case, together: the joint downside of our own
# ranges, on the reference class.
ADVERSE_CASE = "adverse ends"
ADVERSE = {"process_leak_pct": "low", "recoverable_share": "low", "upgrade_capture_uplift": "low",
           "margin_per_repeat_sale": "low", "x17_days_cut": "low", "x17_share_routed": "low",
           "run_cost_eur_m_year": "high"}


def adverse(V, ends):
    """V with every assumed rate at its adverse end; `ends` maps "low"/"high" to the register's columns."""
    return dict(V, **{a: ends[e][a] for a, e in ADVERSE.items()})


def scenario_gate_id(family, n):
    """The register row of a gate derived from build cost, for scenario n: gate_exit_floor_eur_m -> gate_exit_floor_s1_eur_m."""
    for unit in ("_eur_m", "_pct"):
        if family.endswith(unit):
            return family[: -len(unit)] + f"_s{n}" + unit
    raise ValueError(family)


def schedules(V):
    """Each X25 scenario's build cost by phase, EUR m (analysis/programme_cost.py; the workbook's Programme cost sheet)."""
    import programme_cost as pc
    M = pc.model(V, pc.work())
    return {k: M["by_phase"][k] for k, _ in pc.SCENARIOS}


def model(V, ends=None, costs=None):
    """Everything the Benefits sheet shows, from the register alone. `ends` holds the register's low and high
    columns, for the adverse case; `costs` each scenario's build cost by phase (default: X25's four scenarios)."""
    costs = schedules(V) if costs is None else costs
    cs = cases(V)
    ref = cs["reference class"]
    short, long_ = 12 * V["gb_appraisal_it_example_years"], 12 * V["gb_appraisal_default_years"]
    hi, lo = V["stla_wacc_pretax_high_pct"], V["stla_wacc_pretax_low_pct"]
    rates = {r: run_rates(V, r) for r in REACH}
    committed = [k for k, _, _, _, com in LEVERS if com]
    runs = {n: (V, c) for n, c in cs.items()}
    if ends is not None:
        runs[ADVERSE_CASE] = (adverse(V, ends), ref)
    out = {"rates": rates,
           "committed": {r: sum(rates[r][k] for k in committed) for r in REACH},
           "cases": cs, "costs": costs}
    gate = {r: ref["b"] * out["committed"][r] * coverage(V, PHASES) for r in REACH}
    out["gate"] = gate
    out["scen"] = {}
    for sk, sc in costs.items():
        o = {"payback": {n: payback_month(v, c, costs=sc) for n, (v, c) in runs.items()},
             "stops": {n: stop_losses(v, c, costs=sc) for n, (v, c) in runs.items()},
             "npv": {(n, h, w): pv(v, c, H, rate, costs=sc)["npv"] for n, (v, c) in runs.items()
                     for h, H in (("5y", short), ("10y", long_)) for w, rate in (("high", hi), ("low", lo))},
             "npv_reach": {r: pv(V, ref, short, hi, r, costs=sc)["npv"] for r in REACH}}
        base = pv(V, ref, short, hi, costs=sc)
        npv = base["npv"]
        o["basis"] = base
        o["switch_share_lost"] = npv / base["ben_total"]
        o["switch_build_overrun_pct"] = (ref["c"] * (base["ben_total"] - base["run"]) / base["build"] - 1) * 100
        o["switch_run_cost"] = V["run_cost_eur_m_year"] * (base["ben_total"] - base["build"]) / base["run"]
        o["switch_rate"] = {a: (V[a] * (1 - npv / base["ben"][k]) if 1 - npv / base["ben"][k] > 0 else None)
                            for a, k in SWITCH}
        # A run rate certified at the exit says where the rates landed, so the whole benefit profile scales with it:
        # the floor is the exit run rate at which the decision basis is worth nothing.
        o["floor"] = gate["every"] * (1 - o["switch_share_lost"])
        # X22's Phase 1 back-up trigger: the leak rate at which claims controls alone repay the first two phases'
        # build cost on the decision basis. Below it, start with residual value (the doc's own condition).
        per = periods(V, ref, short, costs=sc)
        pv12 = sum(x["cost"] / (1 + hi / 100) ** (x["start"] / 12) for x in per[:2])
        o["leak_switch"] = V["process_leak_pct"] * pv12 / base["ben"]["claims"]
        o["pv_phases_12"] = pv12
        # X22's Phase 2 money gate (skeptic A12): what claims controls must be recovering, annualised, in the pilot
        # market at the switch trigger, so certified money, not only data quality, releases Phase 3's funding.
        o["claims_gate_pilot"] = rates["every"]["claims"] * o["leak_switch"] / V["process_leak_pct"] * coverage(V, 2)
        out["scen"][sk] = o
    if ends is not None:
        Va = runs[ADVERSE_CASE][0]
        out["adverse"] = dict(rates=run_rates(Va), committed=sum(run_rates(Va)[k] for k in committed),
                              gate=ref["b"] * sum(run_rates(Va)[k] for k in committed) * coverage(V, PHASES))
    return out


# ---- coverage from the registrations ----

def shares(year):
    d = md.clean(pd.read_parquet(CACHE).assign(n=lambda f: f["n"].astype(float)))
    n, _ = md.mix(d, year)
    return (n["merged"] / n["merged"].sum()).sort_values(ascending=False)


def core_of(s):
    """The markets above the largest relative break in the ranked shares, within the top ten."""
    top = s.head(10).values
    k = max(range(1, 10), key=lambda i: top[i - 1] / top[i])
    return list(s.index[:k])


def fmt(x, d=1):
    return "none within ten years" if x is None else f"{x:,.{d}f}"


def main():
    s24, s25 = shares(YEAR), shares(CHECK_YEAR)
    core24, core25 = core_of(s24), core_of(s25)
    cov = {"pilot": round(100 * s24[PILOT], 1), "core": round(100 * s24[core24].sum(), 1)}  # as registered
    V = register()
    V["x21_cov_pilot_2024"], V["x21_cov_core_2024"] = cov["pilot"], cov["core"]
    ends = {"low": register("low"), "high": register("high")}
    M = model(V, ends)

    ck = []

    def check(name, ok, got):
        ck.append((name, got, bool(ok)))

    check("the pilot market is the group's largest, both years", s24.index[0] == PILOT == s25.index[0],
          f"{s24.index[0]}, {s25.index[0]}")
    check("the core markets are the same set in both years", set(core24) == set(core25), ", ".join(core24))
    brk = s24[core24].min() / s24.drop(core24).max()
    check("the break: the smallest core share over the largest other", brk > 2, f"{brk:.2f}")
    wb = load_workbook(WORKBOOK, data_only=True)
    reach = {r[0].value: [c.value for c in r[1:4]] for r in wb["Data reach"].iter_rows(min_row=5)
             if r[0].value and r[1].value is not None and not isinstance(r[1].value, str)}
    R = M["rates"]
    claims_line = {r: R[r]["claims"] / (V["recoverable_share"] / 100) for r in REACH}
    mirrors = [("Leak 1, claims", [claims_line[r] for r in REACH]),
               ("Leak 1, targeting", [R[r]["targeting"] for r in REACH]),
               ("Leak 2, upgrade moments", [R[r]["retention"] for r in REACH]),
               ("Leak 3, resale execution", [R[r]["exec_days"] + R[r]["exec_route"] for r in REACH])]
    worst = max(abs(a - b) for lab, ours in mirrors for a, b in zip(ours, reach[lab]))
    check("every lever's reach equals the workbook's Data reach sheet", worst < 1e-6, f"largest gap {worst:.2e}")
    w1 = [r for r in wb["Leak 1 - Incentives"].iter_rows() if r[0].value == "Of which a controls layer actually recovers"]
    check("claims controls equal the Leak 1 sheet's recovered line", abs(w1[0][1].value - R["every"]["claims"]) < 1e-6,
          f"{w1[0][1].value:.3f}")
    summ = {r[0].value: [c.value for c in r[1:3]] for r in wb["Summary"].iter_rows() if r[0].value}
    at_risk = summ["Total value at risk a year"]
    check("the committed benefit sits inside the expected column", M["committed"]["every"] < at_risk[0],
          f"{M['committed']['every']:.1f} < {at_risk[0]:.1f}")
    short = 12 * V["gb_appraisal_it_example_years"]
    import programme_cost as pcm
    SC = dict(pcm.SCENARIOS)
    ref = M["cases"]["reference class"]
    for sk, sc in M["costs"].items():
        S = M["scen"][sk]
        plan_pv = pv(V, M["cases"]["plan"], short, V["stla_wacc_pretax_high_pct"], costs=sc)
        zero_rate = pv(V, M["cases"]["plan"], 12 * V["gb_appraisal_default_years"], 0.0, costs=sc)
        check(f"{SC[sk]}: at a zero rate, build cost is the schedule's sum", abs(zero_rate["build"] - sum(sc)) < 1e-9,
              f"{zero_rate['build']:.1f}")
        check(f"{SC[sk]}: NPV falls as the rate rises",
              plan_pv["npv"] < pv(V, M["cases"]["plan"], short, V["stla_wacc_pretax_low_pct"], costs=sc)["npv"], "high < low")
        c_star = dict(ref, c=1 + S["switch_build_overrun_pct"] / 100)
        npv2 = pv(V, c_star, short, V["stla_wacc_pretax_high_pct"], costs=sc)["npv"]
        check(f"{SC[sk]}: at its switching value, the build overrun zeroes the decision basis", abs(npv2) < 1e-6, f"{npv2:.2e}")
        lost = pv(V, dict(ref, b=ref["b"] * (1 - S["switch_share_lost"])), short, V["stla_wacc_pretax_high_pct"],
                  costs=sc)["npv"]
        check(f"{SC[sk]}: losing the switching share of benefits zeroes the value", abs(lost) < 1e-6, f"{lost:.2e}")
    check("every adverse end is an assumption's own low or high",
          all(a in ends[e] and a in V for a, e in ADVERSE.items()), f"{len(ADVERSE)} inputs")
    s1 = M["scen"][next(iter(M["costs"]))]
    check("the stress at 25% of benefits is worth less than at 50%",
          s1["npv"][("stress, 25% of benefits", "5y", "high")] < s1["npv"][("stress, 50% of benefits", "5y", "high")],
          "25% < 50%")
    ck = pd.DataFrame(ck, columns=["check", "got", "passes"])
    ok = bool(ck["passes"].all())

    L = []
    w = L.append
    w("# X21: the benefits case\n")
    w("`analysis/benefits_case.py`. What the programme gets back, lever by lever, on X20's reach, and whether it pays "
      "for itself against a reference class, a stress and switching values. EUR millions, advert-price bases as the "
      "value-at-risk workbook's. The workbook's Benefits sheet computes the same with live formulas; the audit checks "
      "one against the other.\n")
    w("## Coverage: where each phase runs\n")
    w("The group's (PSA + FCA brands) share of new-car registrations, EU and EFTA (the UK is not in the file). The pilot "
      "is France, where X14 sized the Phase 2 pilot; the core markets are those above the largest break in the ranked "
      "shares.\n")
    w("| market set | markets | 2024 share (%) | 2025 share (%) |")
    w("|---|---|---|---|")
    w(f"| pilot | {PILOT} | {cov['pilot']:.1f} | {100 * s25[PILOT]:.1f} |")
    w(f"| core | {', '.join(core24)} | {cov['core']:.1f} | {100 * s25[core25].sum():.1f} |")
    w(f"| next largest | {s24.drop(core24).index[0]} | {100 * s24.drop(core24).iloc[0]:.1f} | "
      f"{100 * s25.drop(core25).iloc[0]:.1f} |\n")
    w("Phase 1 earns nothing (the baseline is being certified). Claims controls run in the pilot from Phase 2; "
      "retention, resale execution and the little-history engine in the core markets from Phase 3; targeting from Phase 4; "
      "every market after the exit (solution doc 8.1). The pilot's randomised arm in Phase 2 is left out: it is small "
      "(x14_pilot_share_fr) and measures rather than earns.\n")

    w("## The levers\n")
    w("Yearly benefit at full coverage, EUR m, on each source scenario (X20). Each euro sits in one class only.\n")
    w("| lever | class | starts in | every source | without the joint ventures' data | without dealers' VIN-level "
      "evidence | measured by |")
    w("|---|---|---|---|---|---|---|")
    for k, lab, cls, st, com in LEVERS:
        w(f"| {lab} | {cls} | Phase {st} | " + " | ".join(f"{R[r][k]:.1f}" for r in REACH) + f" | {GATE_OF[k]} |")
    w("| **Committed, expected a year** | recovered | | " + " | ".join(f"**{M['committed'][r]:.1f}**" for r in REACH)
      + " | Phase 4 exit (below) |\n")
    w("- **Priced, not recovered (no euro here):** the level charge on contracts where the customer holds the option "
      "(X6) and the buy-back book's cold premium (X19). On the book the level counts both ways and gains on average "
      "(X18); a charge moves a tail cost into a price. Lenders price a market-wide collateral risk too (`fliegel_*`), "
      "so it is not a margin the group alone can keep.")
    w("- **Enablers (no euro of their own):** X19's transfer price and the operating metric, X13's band, the ledger. "
      "They are how the counted levers happen; counting them again would count the same euro twice.")
    w("- **Targeting is shown, never committed:** X5's figure assumes income is known exactly, and the uplift test "
      "found no model beating plain response targeting (X15). Only a randomised holdout on the incentive's level can "
      "turn it into a benefit.")
    w("- **The incentive's average level is in the same class, unsized (skeptic B2, X24).** Whether the group spends "
      "too much on average is a question public data can't answer: demand models set margins by assuming prices "
      "maximise profit, and discount series move with demand. The one long-run measurement we found: carmakers' "
      f"promotions raised firm value for {V['pauwels_promo_longrun_pos_pct']:.0f}% of brands, against "
      f"{V['pauwels_npi_longrun_pos_pct']:.0f}% for new models (US data, `pauwels_*`). The same randomised holdout "
      "measures it, read over a window long enough to catch sales pulled forward (`x5_pull_forward`) and net of each "
      "discount euro's resale cost (X5). No euro is counted.")
    w("- **The tail lever is an upper bound in the one-in-ten column:** little-history cars' one-year curve error falling "
      "from the no-history band to the own-data band, at the measured joint share (X18). It arrives as the ledger's "
      "own sales make them known cars.\n")

    exp, one = at_risk
    w("## The headline split\n")
    w("| | expected a year | one year in ten |")
    w("|---|---|---|")
    w(f"| At risk (the headline, two measures) | {exp:.1f} | {one:.1f} |")
    reach_tot = sum(reach[lab][0] for lab, _ in mirrors)
    w(f"| Addressable: what the levers can reach, every source (Data reach sheet) | {reach_tot:.1f} | - |")
    w(f"| Planned benefit, committed levers | {M['committed']['every']:.1f} | "
      f"{M['committed']['every'] + R['every']['tail']:.1f} |")
    w(f"| The same at the reference class (McKinsey-Oxford software: {V['mckox_sw_benefit_shortfall_pct']:.0f}% short) | "
      f"{ref['b'] * M['committed']['every']:.1f} | {ref['b'] * (M['committed']['every'] + R['every']['tail']):.1f} |")
    w(f"| Upper bound beside it, never committed: income targeting | {R['every']['targeting']:.1f} | "
      f"{R['every']['targeting']:.1f} |")
    w("| Certified today | 0 | 0 |\n")
    w("Every committed rate is an assumption (`recoverable_share`, `upgrade_capture_uplift`, `x17_days_cut`, "
      "`x17_share_routed`) on a disclosed or measured base, so all of the planned benefit needs the pilot. Nothing is "
      "certified until Finance certifies the Phase 1 baseline. The one-in-ten column adds only the tail lever: the "
      "level itself is priced, never recovered, so its reach is not a benefit's reach and is left blank.\n")

    w("## The cases\n")
    w("| case | benefits realised (%) | build cost (% of plan) | months a phase | source |")
    w("|---|---|---|---|---|")
    src = {"plan": "the register", "reference class": "McKinsey-Oxford, software projects (`mckox_sw_*`)",
           "stress, 25% of benefits": "Flyvbjerg-Budzier's stress test (`fb_stress_*`), phases as the reference class",
           "stress, 50% of benefits": "the same, the stress's high end"}
    for n, c in M["cases"].items():
        w(f"| {n} | {100 * c['b']:.0f} | {100 * c['c']:.0f} | {c['m']:.1f} | {src[n]} |")
    w(f"| {ADVERSE_CASE} | {100 * ref['b']:.0f} | {100 * ref['c']:.0f} | {ref['m']:.1f} | the reference class, with "
      "every assumed rate at the end of its register range that hurts the case, together: the low ends of "
      "`process_leak_pct`, `recoverable_share`, `upgrade_capture_uplift`, `margin_per_repeat_sale`, `x17_days_cut`, "
      f"`x17_share_routed` and the high end of `run_cost_eur_m_year` (committed benefit {M['adverse']['committed']:.1f} "
      "a year at full coverage) |")
    w("")
    w("## Payback by build scenario\n")
    w("X25 priced one work list four ways (`analysis/programme_cost_report.md`); none is chosen here. Build cost is "
      "paid at the start of each phase at the case's overrun; benefits and the run cost accrue evenly. The loss if the "
      "programme stops at a gate is the build cost spent so far less the benefit earned so far.\n")
    w("| scenario | build, EUR m | " + " | ".join(f"Phase {p}" for p in range(1, PHASES + 1)) + " |")
    w("|---|---|" + "---|" * PHASES)
    for sk, sc in M["costs"].items():
        w(f"| {SC[sk]} | {sum(sc):.1f} | " + " | ".join(f"{x:.2f}" for x in sc) + " |")
    w("")
    w("| scenario | case | payback month | loss if stopped at the Phase 1 gate (negative: a gain) | at Phase 2 | "
      "at Phase 3 | at Phase 4 |")
    w("|---|---|---|---|---|---|---|")
    for sk in M["costs"]:
        S = M["scen"][sk]
        for n in S["payback"]:
            w(f"| {SC[sk]} | {n} | {fmt(S['payback'][n])} | " + " | ".join(f"{x:.1f}" for x in S["stops"][n]) + " |")
    w("")
    w("## Value\n")
    w(f"Net present value at the group's pre-tax WACC range ({V['stla_wacc_pretax_low_pct']:.1f}-"
      f"{V['stla_wacc_pretax_high_pct']:.1f}%, `stla_wacc_*`), over the Green Book's five-year IT example and its "
      "ten-year default, the build inside both. EUR m.\n")
    w("| scenario | case | 5 years, highest WACC | 5 years, lowest | 10 years, highest | 10 years, lowest |")
    w("|---|---|---|---|---|---|")
    for sk in M["costs"]:
        S = M["scen"][sk]
        for n in S["payback"]:
            w(f"| {SC[sk]} | {n} | " + " | ".join(f"{S['npv'][(n, h, r)]:.1f}" for h, r in
                                                  (("5y", "high"), ("5y", "low"), ("10y", "high"), ("10y", "low"))) + " |")
    w("")
    A = M["adverse"]
    w("The decision basis (the reference class, five years, highest WACC) on each source scenario: " +
      "; ".join(f"{SC[sk]}: " + ", ".join(f"{REACH_LABEL[r]} {M['scen'][sk]['npv_reach'][r]:.1f}" for r in REACH)
                for sk in M["costs"]) + ".\n")
    w("## Switching values\n")
    w("The Green Book gives no default for benefit shortfall and asks for switching values instead (4.1): how far an "
      "input can move before the case stops paying. On the decision basis, for each build scenario.\n")
    w("| input | today | " + " | ".join(SC[sk] for sk in M["costs"]) + " |")
    w("|---|---|" + "---|" * len(M["costs"]))
    w(f"| share of benefits that can be lost (%) | 0 | " +
      " | ".join(f"{100 * M['scen'][sk]['switch_share_lost']:.0f}" for sk in M["costs"]) + " |")
    w(f"| build cost overrun absorbed (% of plan) | {V['mckox_sw_cost_overrun_pct']:.0f} (reference) | " +
      " | ".join(f"{M['scen'][sk]['switch_build_overrun_pct']:.0f}" for sk in M["costs"]) + " |")
    w(f"| run cost (EUR m a year) | {V['run_cost_eur_m_year']:.1f} | " +
      " | ".join(f"{M['scen'][sk]['switch_run_cost']:.1f}" for sk in M["costs"]) + " |")
    for a, k in SWITCH:
        cells = []
        for sk in M["costs"]:
            sv = M["scen"][sk]["switch_rate"][a]
            cells.append("survives at zero" if sv is None else f"{sv:.2f}")
        w(f"| {a} | {V[a]:g} | " + " | ".join(cells) + " |")
    w("")
    w(f"The build overrun a case absorbs is set against the Green Book's unmitigated upper bound for ICT "
      f"({V['gb_ob_capex_upper_ict_pct']:.0f}%) and Flyvbjerg-Budzier's stress ({V['fb_stress_cost_overrun_pct']:.0f}%); "
      "no reference class exists for operating cost (Green Book 4.1).\n")
    w("## The exit gate, derived\n")
    w("The Phase 4 exit gate was set at EUR 80m a year, 'above' an older controls figure and 'about four times the "
      "ask' (skeptic B1), the single ask X25 retired: true by construction. Derived instead: the run rate the committed levers earn in the markets "
      "live at month 24 at the reference class, which Finance can certify against control groups. It depends on "
      "benefits only, so it is the same in every scenario.\n")
    w("| | run rate at the exit, EUR m a year |")
    w("|---|---|")
    for r in REACH:
        w(f"| gate, {REACH_LABEL[r]} | {M['gate'][r]:.1f} |")
    w(f"| on our own adverse ends (every assumed rate at once) | {A['gate']:.1f} |")
    w("")
    w("The gates that depend on build cost, one per scenario (to X22): the floor, below which the decision basis is "
      "worth nothing; the Phase 1 switch trigger, the certified leak rate below which claims controls do not repay "
      "the first two phases; the Phase 2 money gate, what claims controls then earn in the pilot market.\n")
    w("| gate | " + " | ".join(SC[sk] for sk in M["costs"]) + " |")
    w("|---|" + "---|" * len(M["costs"]))
    w("| floor, EUR m a year | " + " | ".join(f"{M['scen'][sk]['floor']:.1f}" for sk in M["costs"]) + " |")
    w("| Phase 1 switch trigger, % of claims-based spend | " +
      " | ".join(f"{M['scen'][sk]['leak_switch']:.2f}" for sk in M["costs"]) + " |")
    w("| Phase 2 money gate, EUR m a year | " +
      " | ".join(f"{M['scen'][sk]['claims_gate_pilot']:.1f}" for sk in M["costs"]) + " |")
    w("")
    w("The gate is set with the joint-venture arrangement agreed at Phase 1 (X22's named legal basis); on the named "
      "fallback it is the second line. The floor reads a certified run rate as where the rates landed, so the whole "
      "benefit profile scales with it: the gate times the share of benefits that can be lost (the switching value). "
      "Both are in the markets live at month 24.\n")
    w("### The reference class, period by period, for each scenario (EUR m)\n")
    for sk, sc in M["costs"].items():
        w(f"**{SC[sk]}**\n")
        w("| period | months | build cost | benefit | run cost | cumulative |")
        w("|---|---|---|---|---|---|")
        cum = 0.0
        for x in periods(V, ref, 12 * V["gb_appraisal_default_years"], costs=sc):
            if x["length"] <= 0:
                continue
            bsum = sum(x["ben"].values())
            cum += bsum - x["cost"] - x["run"]
            w(f"| {x['label']} | {x['start']:.0f}-{x['start'] + x['length']:.0f} | {x['cost']:.1f} | {bsum:.1f} | "
              f"{x['run']:.1f} | {cum:.1f} |")
        w("")
    w("## What this does not show\n")
    w("- **The rates are assumptions.** Every committed lever rests on an assumed rate over a disclosed or measured "
      "base. The switching values say which one the case leans on; the gates measure them.")
    w("- **The reference class is large IT projects, 2012, across industries,** not data programmes in carmakers. "
      "Public-sector data-management projects overrun in the tail twice as often as the average "
      "(`bf_public_datamgmt_outlier_pct`): the reason the phase gates and a stop matter more than the mean.")
    w("- **Coverage is registrations, EU and EFTA,** as a proxy for every lever's base; the UK is missing from the file.")
    w("- **The tail lever uses the measured joint share at the margin,** an approximation, and is an upper bound.")
    w("- **The merger's own synergy record** (EUR 8.4bn against 5bn, `stla_synergies_*`) is not a reference class: it "
      "was a merger, and it was counted by those paid on it. It sets the convention (net of implementation costs, "
      "cash) and the reason benefits are certified by Finance against control groups.\n")
    w("## Checks\n")
    w("| check | got | passes |")
    w("|---|---|---|")
    for n, g, p in ck.itertuples(index=False):
        w(f"| {n} | {g} | {'yes' if p else '**NO**'} |")
    w(f"\n{'All checks pass.' if ok else 'A CHECK FAILED.'}")
    OUT.write_text("\n".join(L) + "\n")
    print(ck.to_string(index=False))
    print("coverage", {k: round(v, 1) for k, v in cov.items()}, "core", core24)
    print("committed", {r: round(v, 1) for r, v in M["committed"].items()},
          "payback (plan)", {sk: round(M["scen"][sk]["payback"]["plan"], 1) for sk in M["costs"]})
    print("gate", {r: round(v, 1) for r, v in M["gate"].items()},
          "floor", {sk: round(M["scen"][sk]["floor"], 1) for sk in M["costs"]},
          "adverse", round(M["adverse"]["committed"], 1), round(M["adverse"]["gate"], 1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
