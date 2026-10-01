"""X22: gates that can be read inside each phase, and a stop.

Skeptic F4: two gates could not be read inside the programme (the residual-cost gate waits 36-48 months for contracts to
return; the adherence gate is undefined under a hard band) and nothing said when to stop. This checks, gate by gate,
that each can be read inside its own phase on the data that phase produces, and sets what happens when it is missed.

- **Phase 1.** Duplicate precision is read on an audit sample of flagged claims (an exact binomial lower bound); recall
  on duplicates seeded into the claims stream with known answers (X1's method; its synthetic results are never
  evidence, its method is). The back-up trigger: the certified leak rate below which claims controls do not repay the
  first two phases' build cost on the benefits case's decision basis (X21), where the doc already says to start with
  residual value instead.
- **Phase 2.** The retention uplift, the group's flag randomised within dealers (X15), read on orders signed inside the
  phase by customers whose contracts end in its first half, with one interim look (O'Brien-Fleming). A significant
  result at the design's power overstates the effect (Gelman & Carlin), so the lower bound goes into the benefits case.
- **Phase 3.** The engine on the cars the buy-back book returns inside the phase: its 80% band's coverage, and its
  car-specific error against the bought guide's on the same cars, level removed. The band decision from pricers' first
  proposals, logged before the cap, against X13's break-evens. Resale execution on randomised returns.
- **Exit.** X21's derived gate and floor.

The switch trigger, the Phase 2 money gate and the floor depend on build cost, so each has one value per X25 build
scenario (analysis/programme_cost.py), and so does the funding each gate releases (the next phase's cost). No scenario
is chosen: the table shows their range and a second table each one.

Every gate has pre-agreed outcomes (Olechowski, Eppinger & Joglekar 2017: Go, Waiver with re-review, Delay, Back-up,
Kill), so a miss is an operating decision, not a political one (Keil & Montealegre 2000).

Usage: .venv/bin/python analysis/gates.py   (writes analysis/gates_report.md; seconds)
"""
import math
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import beta, binom, binomtest, multivariate_normal, norm

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import benefits_case as bc  # noqa: E402

OUT = HERE / "gates_report.md"
# "If the true value were" grids for sizing, not estimates: the samples are sized before the phase starts.
PRECISION_IF = (0.93, 0.95, 0.97)
RECALL_IF = (0.75, 0.80, 0.85)
UPLIFT_IF_SHARE = (0.5, 1.0, 1.5)     # the true uplift as a share of the gate
RHO_GUIDE = (0.25, 0.50, 0.75)        # correlation between the engine's and the guide's errors on the same car
MAD_TO_SD = norm.ppf(0.75)            # a normal spread's median absolute deviation over its standard deviation


def cp_lower(k, n, conf):
    """One-sided exact (Clopper-Pearson) lower confidence bound for a proportion."""
    return 0.0 if k == 0 else beta.ppf(1 - conf, k, n - k + 1)


def n_for_bound(threshold, p_true, conf, power, n_max=20000):
    """Smallest sample whose one-sided exact lower bound clears `threshold` with probability `power` when the true
    proportion is `p_true`."""
    for n in range(10, n_max):
        if cp_lower(n, n, conf) < threshold:
            continue
        lo, hi = 0, n                       # the lower bound rises with the count: the least count that clears it
        while lo < hi:
            mid = (lo + hi) // 2
            lo, hi = (lo, mid) if cp_lower(mid, n, conf) >= threshold else (mid + 1, hi)
        if binom.sf(lo - 1, n, p_true) >= power:
            return n
    return None


def obf_two_looks(alpha, power):
    """O'Brien-Fleming with one interim look at half the information, two-sided: the two critical values and how much
    larger the most the trial can need is than a single test's sample."""
    corr = math.sqrt(0.5)
    cov = [[1, corr], [corr, 1]]

    def reject(c, drift):
        c1, c2 = c * math.sqrt(2), c
        mean = [drift * math.sqrt(0.5), drift]
        inside = multivariate_normal(mean, cov).cdf([c1, c2], lower_limit=[-c1, -c2])
        return 1 - inside

    lo, hi = 1.5, 3.5
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if reject(mid, 0.0) > alpha else (lo, mid)
    c = (lo + hi) / 2
    fixed = norm.ppf(1 - alpha / 2) + norm.ppf(power)
    lo, hi = fixed, fixed * 1.2
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if reject(c, mid) >= power else (mid, hi)
    drift = (lo + hi) / 2
    return c * math.sqrt(2), c, (drift / fixed) ** 2, reject(c, 0.0), reject(c, drift)


def retrodesign(effect, se, alpha):
    """Gelman & Carlin (2014): power, sign-error rate and exaggeration ratio of a two-sided test read only when
    significant, for a true effect and a standard error."""
    z = norm.ppf(1 - alpha / 2)
    lam = effect / se
    hi, lo = norm.sf(z - lam), norm.cdf(-z - lam)
    p = hi + lo
    e_hi = lam * hi + norm.pdf(z - lam)          # E[X; X > z] for X ~ N(lam, 1)
    e_lo = -lam * lo + norm.pdf(-z - lam)        # E[-X; X < -z]
    return p, lo / p, (e_hi + e_lo) / p / lam


def fisher_n(r0, r1, conf, power):
    """Cars needed to tell a correlation r1 from r0, one-sided, Fisher's z."""
    return math.ceil(((norm.ppf(conf) + norm.ppf(power)) / (math.atanh(r1) - math.atanh(r0))) ** 2 + 3)


def span(vals, d):
    """A value that differs by build scenario, as its range: '0.60-1.22'; one number if they all round the same."""
    lo, hi = f"{min(vals):.{d}f}", f"{max(vals):.{d}f}"
    return lo if lo == hi else f"{lo}-{hi}"


def main():
    import programme_cost as pc
    SC = dict(pc.SCENARIOS)
    V = bc.register()
    ends = {"low": bc.register("low"), "high": bc.register("high")}
    M = bc.model(V, ends)
    S = M["scen"]                     # benefits_case.model, one entry per build scenario, as the Benefits sheet has it
    conf, power = V["gate_read_confidence_pct"] / 100, V["gate_read_power_pct"] / 100
    alpha = 1 - conf
    out, ck = {}, []

    def check(name, ok, got):
        ck.append((name, got, bool(ok)))

    # ---- Phase 1 ----
    prec = {p: n_for_bound(V["gate_dup_precision_pct"] / 100, p, conf, power) for p in PRECISION_IF}
    rec = {r: n_for_bound(V["gate_dup_recall_pct"] / 100, r, conf, power) for r in RECALL_IF}
    ref = M["cases"]["reference class"]
    stress = "stress, 25% of benefits"
    for sk, sc in M["costs"].items():
        Vs = dict(V, process_leak_pct=S[sk]["leak_switch"])
        claims = bc.pv(Vs, ref, 12 * V["gb_appraisal_it_example_years"], V["stla_wacc_pretax_high_pct"],
                       costs=sc)["ben"]["claims"]
        check(f"{SC[sk]}: at the switch trigger, claims controls repay exactly the first two phases' build cost",
              abs(claims - S[sk]["pv_phases_12"]) < 1e-9, f"{S[sk]['leak_switch']:.3f}%")
        check(f"{SC[sk]}: the programme still pays at a zero leak rate", S[sk]["switch_rate"]["process_leak_pct"] is None,
              "survives at zero")
        st = S[sk]["stops"][stress]
        check(f"{SC[sk]}: under the stress, the loss if stopped grows gate by gate", all(a < b for a, b in zip(st, st[1:])),
              " < ".join(f"{x:.1f}" for x in st))
    sw = [S[sk]["leak_switch"] for sk in M["costs"]]
    money = [S[sk]["claims_gate_pilot"] for sk in M["costs"]]
    floor = [S[sk]["floor"] for sk in M["costs"]]
    nxt = {p: [sc[p] for sc in M["costs"].values()] for p in (1, 2, 3)}   # funding a gate releases: the next phase's cost
    lb = cp_lower(95, 100, 0.95)
    ref_lb = binomtest(95, 100).proportion_ci(confidence_level=0.90, method="exact").low
    check("the exact lower bound matches scipy's Clopper-Pearson", abs(lb - ref_lb) < 1e-9, f"{lb:.4f}")
    check("a truer detector needs a smaller audit", prec[0.97] < prec[0.95] < prec[0.93],
          " > ".join(str(prec[p]) for p in PRECISION_IF))

    # ---- Phase 2 ----
    both = 2 * V["x15_pilot_blocked_customers"]
    both_spill = 2 * V["x15_pilot_blocked_spill25_customers"]
    year_fr = V["sfse_contracts_fr_2025"]
    check("the pilot's size reproduces X14's share of France's year", round(100 * both / year_fr) ==
          V["x14_pilot_share_fr"], f"{100 * both / year_fr:.1f}%")
    half_phase = year_fr * V["x21_phase_months"] / 2 / 12   # contracts ending in the phase's first half, steady state
    out["pilot_share_half"] = 100 * both / half_phase
    out["pilot_share_half_spill"] = 100 * both_spill / half_phase
    c1, c2, inflation, a_got, p_got = obf_two_looks(alpha, power)
    out["obf"] = (c1, c2, inflation)
    check("the two-look design keeps the stated confidence", abs(a_got - alpha) < 1e-4, f"{a_got:.5f}")
    check("and has the stated power at its inflated size", abs(p_got - power) < 1e-4, f"{p_got:.5f}")
    se = V["gate_uplift_pp"] / (norm.ppf(1 - alpha / 2) + norm.ppf(power))
    rd80 = retrodesign(V["gate_uplift_pp"], se, alpha)
    check("the exaggeration at the design's power reproduces Gelman & Carlin",
          abs(rd80[2] - V["gc_exaggeration_80_power"]) < 0.005, f"{rd80[2]:.3f}")
    uplift_rows = [(s * V["gate_uplift_pp"], *retrodesign(s * V["gate_uplift_pp"], se, alpha)) for s in UPLIFT_IF_SHARE]
    out["lower_at_gate"] = V["gate_uplift_pp"] - norm.ppf(1 - alpha / 2) * se

    # ---- Phase 3 ----
    p_band = 0.80
    tol = V["gate_engine_coverage_tol_pts"] / 100
    n_cov = math.ceil(norm.ppf(1 - alpha / 2) ** 2 * p_band * (1 - p_band) / tol ** 2)
    sd = V["engine_err_typical"] / MAD_TO_SD
    pair = {rho: math.ceil(((norm.ppf(conf) + norm.ppf(power)) * sd * math.sqrt(2 * (1 - rho))
                            / V["gate_engine_margin_pts"]) ** 2) for rho in RHO_GUIDE}
    price_per_car = V["aramis_fy25_b2c_revenue_eur_m"] / V["aramis_fy25_b2c_units"]
    returns_core = V["buyback_payables_current_eur_m"] * V["x21_cov_core_2024"] / 100 * V["x21_phase_months"] / 12 \
        / price_per_car
    out.update(n_cov=n_cov, pair=pair, returns_core=returns_core, price_per_car=price_per_car * 1e6)
    check("more correlated errors need fewer paired cars", pair[0.75] < pair[0.50] < pair[0.25],
          " > ".join(str(pair[r]) for r in RHO_GUIDE))
    r_fixed, r_full = math.sqrt(V["x13_be_fixed_vs_engine"]), math.sqrt(V["x13_be_full_vs_fixed"])
    n_band = {"engine only, or the tied band": fisher_n(0.0, r_fixed, conf, power),
              "the tied band, or the full band": fisher_n(r_fixed, r_full, conf, power)}
    out["n_band"] = n_band
    check("X13's break-evens are ordered", 0 < r_fixed < r_full, f"{r_fixed:.3f} < {r_full:.3f}")

    # ---- the report ----
    ck = pd.DataFrame(ck, columns=["check", "got", "passes"])
    ok = bool(ck["passes"].all())
    L = []
    w = L.append
    w("# X22: gates that can be read inside each phase, and a stop\n")
    w("`analysis/gates.py`. Each gate is checked for whether the phase it closes produces the data to read it, and "
      "each has outcomes agreed before the programme starts: Go, Waiver with re-review, Delay, Back-up or Kill "
      "(Olechowski, Eppinger & Joglekar, ICED 2017). Agreed triggers turn a stop from a political fight into an "
      "operating decision (Keil & Montealegre, 2000); 30-40% of IS projects show some escalation of commitment "
      "(`kmr_escalation_*`). Every reading is held to "
      f"{V['gate_read_confidence_pct']:.0f}% confidence and sized for {V['gate_read_power_pct']:.0f}% power (TARGET "
      "rows), and read by Finance with at least two reviewers from outside the programme (`gpd_feasibility_outside_min`, "
      "a UK precedent).\n")
    w("Three gates depend on build cost: the Phase 1 switch trigger, the Phase 2 money gate and the floor. Each has one "
      "value per X25 build scenario (`analysis/programme_cost_report.md`), and so does the funding a gate releases, the "
      "next phase's cost. No scenario is chosen: the table gives their range, and the table after it each scenario.\n")
    w("## The gates\n")
    w("| phase | gate | read on | readable inside the phase because | if missed | releases, next phase's cost (EUR m) |")
    w("|---|---|---|---|---|---|")
    w(f"| 1 | VIN link and dealer crosswalk, each at least {V['gate_vin_link_pct']:.0f}% of claim value | the claim "
      "spine | a count over every claim | Delay: the next phase's funding waits; the build continues on Phase 1's "
      f"money | {span(nxt[1], 1)} |")
    w(f"| 1 | Duplicate precision at least {V['gate_dup_precision_pct']:.0f}% | an audit of flagged claims, exact lower "
      f"bound | {prec[0.95]} audited flags if the true precision is 95% (below) | Waiver with re-review: flags go to "
      "review, not to hold, until it reads | |")
    w(f"| 1 | Duplicate recall at least {V['gate_dup_recall_pct']:.0f}% | duplicates seeded into the claims stream "
      f"with known answers | {rec[0.80]} seeded if the true recall is 80%; seeds cost nothing | Waiver with re-review | |")
    w(f"| 1 | Leakage baseline certified by Finance | the certified leak rate | Finance certifies it in the phase | "
      f"**Back-up** if it is below the switch trigger ({span(sw, 2)}% by build scenario, "
      "`gate_leak_switch_s1..s4_pct`): start with residual value, as the doc already says | |")
    w("| 1 | The ledger's monthly mark reconciled against Aramis's quarterly realised price per car (skeptic B10); "
      f"the mark at trade starts {V['x24_gap_floor_pct']:g}-{V['x24_gap_ceiling_pct']:g}% below the engine's asking "
      "price (the same-car gap bounded from audited accounts, `x24_gap_*`; a discount off asking comes on top) and reads the group's own trade results as "
      f"they come (US trade leads retail by {V['x24_us_lead_months']:.0f} months, `x24_us_lead_months`) | "
      "Aramis Group's published quarterly figures (`x10_aramis_*`) | quarterly, and Phase 1 spans two quarters | "
      "Waiver with re-review: the gap is explained before Phase 3 relies on the mark | |")
    w("| 1 | Legal basis agreed (X20's three items) | the signed terms | each is a signature | Back-up: the named "
      "fallback, and the exit gate's second line | |")
    w("| 2 | The engine recalibrated on the realised resale prices of the returns the ledger backfills (the asking-to-"
      "trade offset, skeptic B10; measured, it replaces Phase 1's bounded range) | the backfilled returns' sale prices "
      "| the backfill is a Phase 2 deliverable | "
      "Delay: Phase 3's engine gate is not read on an engine calibrated to asking prices | |")
    w(f"| 2 | Ledger reconciles to the general ledger within {V['gate_gl_reconcile_pct']:.1f}% | monthly close | "
      "every month | Delay | " + f"{span(nxt[2], 1)} |")
    w(f"| 2 | Claims recoveries certified in the pilot market at least EUR {span(money, 1)}m a year by build scenario, "
      "annualised (`gate_claims_recovered_s1..s4_eur_m`, derived: what claims controls earn there at the switch "
      "trigger) | recoveries Finance certifies over the phase | the controls run in the pilot from Phase 2 | Back-up: "
      "residual value first; the claims lever is not scaled. Certified money, not only data quality, releases Phase "
      "3's funding (skeptic A12) | |")
    w(f"| 2 | Retention uplift at least {V['gate_uplift_pp']:.0f} points, lower bound above zero | orders signed "
      "inside the phase by customers whose contracts end in its first half; the group's flag randomised within "
      f"dealers; one interim look | the pilot takes {out['pilot_share_half']:.0f}% of France's first-half contract "
      f"endings ({out['pilot_share_half_spill']:.0f}% with spillover) | Back-up: cohort-level timing; the exit gate's "
      "second line; the lower bound, not the point estimate, enters the benefits case | |")
    w(f"| 3 | The engine's 80% band covers {100 * p_band - V['gate_engine_coverage_tol_pts']:.0f}-"
      f"{100 * p_band + V['gate_engine_coverage_tol_pts']:.0f}% of returned cars' realised prices | cars the buy-back "
      f"book returns in the phase, level removed | {n_cov} cars against an order of {round(returns_core, -4):,.0f} returns in "
      "the core markets | Waiver with re-review: recalibrate by market and age (X15) and read again | "
      f"{span(nxt[3], 1)} |")
    w(f"| 3 | The engine's car-specific error no worse than the bought guide's by more than "
      f"{V['gate_engine_margin_pts']:.0f} point | the same returned cars, both predictions as of the contract's start, "
      f"the index move removed | {pair[0.50]} paired cars if the two errors correlate 0.5 | **Back-up:** the guide "
      "keeps the price; the engine stays challenger and band-maker (F7) | |")
    w("| 3 | The band decision | pricers' first proposals, logged before the cap, against realised prices | "
      f"{max(n_band.values())} sold cars | Not pass or fail: engine only below X13's first break-even, the tied band "
      "between, the full band above the second | |")
    w(f"| 3 | Resale execution: at least {V['gate_days_cut_days']:.0f} days cut, and routed cars' margin over the "
      f"trade at least {V['gate_route_margin_pct']:.0f}% after all costs | returns randomised between the old "
      "process and the new | sized in Phase 2 from the ledger's backfilled returns, which give the spread of days to "
      "sale | Back-up: the lever is not scaled; the case holds without it (X21) | |")
    w(f"| 3 | The certified run rate in the live markets at least the floor (`gate_exit_floor_s1..s4_eur_m`, "
      f"{span(floor, 1)} derived by build scenario) | Finance, annualised over the phase | claims controls have run "
      "since Phase 2 and the other levers through Phase 3 | **Kill:** Phase 4 is not funded (skeptic A13's named "
      "stop) | |")
    w(f"| 4 | Run-rate benefits certified at least the derived gate (`gate_benefits_eur_m`, {M['gate']['every']:.1f} "
      f"with every source) | Finance, against control groups | the levers live in the core markets | Waiver with "
      f"re-review between the floor ({span(floor, 1)} by build scenario) and the gate: stay in the live markets; "
      "**Kill** below the floor: no run cost committed | |\n")

    w("## The gates that depend on build cost, by scenario\n")
    w("X21's Benefits sheet, each scenario's build cost by phase (`analysis/programme_cost_report.md`). EUR m unless "
      "stated. Loss if stopped: build cost spent less benefit earned by the gate (negative: a gain).\n")
    w("| | " + " | ".join(SC[sk] for sk in M["costs"]) + " |")
    w("|---|" + "---|" * len(M["costs"]))
    w("| build cost over the four phases | " + " | ".join(f"{sum(sc):.1f}" for sc in M["costs"].values()) + " |")
    w("| Phase 1 switch trigger, % of claims-based spend | " + " | ".join(f"{x:.2f}" for x in sw) + " |")
    w("| Phase 2 money gate, a year in the pilot | " + " | ".join(f"{x:.1f}" for x in money) + " |")
    w("| the floor from the Phase 3 gate, a year | " + " | ".join(f"{x:.1f}" for x in floor) + " |")
    for p in (1, 2, 3):
        w(f"| released at the Phase {p} gate (Phase {p + 1}'s cost) | " + " | ".join(f"{x:.1f}" for x in nxt[p]) + " |")
    for n_, lab in (("reference class", "the reference class"), (stress, "Flyvbjerg-Budzier's stress, 25% of benefits")):
        w(f"| loss if stopped at the gates of Phases 1, 2, 3, 4: {lab} | " +
          " | ".join("; ".join(f"{x:.1f}" for x in S[sk]["stops"][n_]) for sk in M["costs"]) + " |")
    w("")
    if all(abs(a - b) < 1e-9 for a, b in zip(M["costs"]["b3"], M["costs"]["b4"])):
        w("Scenarios 3 and 4 have the same build schedule: at rate-card prices every workstream's cheapest route is "
          "in-house with AI (X25).\n")
    w("In every scenario the loss if stopped grows gate by gate under the stress, so the first gate is where a stop "
      "saves most, and the one that must read cleanly (checked below).\n")

    w("## Phase 1: the audit, the seeds and the switch\n")
    w("Smallest sample whose exact one-sided lower bound clears the gate with the stated power, if the true value is "
      "as shown (a sizing grid, not an estimate).\n")
    w("| if the true precision is | audited flags |")
    w("|---|---|")
    for p in PRECISION_IF:
        w(f"| {100 * p:.0f}% | {prec[p]} |")
    w("")
    w("| if the true recall is | seeded duplicates |")
    w("|---|---|")
    for r in RECALL_IF:
        w(f"| {100 * r:.0f}% | {rec[r]} |")
    w("")
    w(f"**The switch trigger:** {span(sw, 2)}% of claims-based incentive spend by build scenario (today's assumption "
      f"`process_leak_pct` is {V['process_leak_pct']:g}%). Below it, claims controls do not repay the first two "
      "phases' build cost at the reference-class overrun within five years at the group's highest WACC, X21's decision "
      "basis. It is proportional to that cost, so the dearest build needs the highest leak rate. The whole programme "
      "still pays at a zero leak rate in every scenario (X21's switching values), so the trigger decides the order, "
      "not whether to go on: residual value first, as the doc already says when incentive spend is far below the "
      "assumption.\n")

    w("## Phase 2: the retention pilot\n")
    w(f"- **Size inside the phase.** Both arms of the chosen design ({both:,.0f} customers; {both_spill:,.0f} with a "
      f"quarter of the uplift spilling over, X15) against France's contracts ending in the phase's first half "
      f"({half_phase:,.0f} if as many end as start, `sfse_contracts_fr_2025`): {out['pilot_share_half']:.0f}% "
      f"({out['pilot_share_half_spill']:.0f}%). Enrolling the first half leaves the second half for orders to be "
      "signed before the gate.")
    w(f"- **One interim look** at half the customers, O'Brien-Fleming: critical values {c1:.3f} at the look and "
      f"{c2:.3f} at the end, for {100 * (inflation - 1):.1f}% more customers at most (checked: the two-look design "
      "keeps the stated confidence and power). It lets the pilot stop early for a clear result either way at almost "
      "no cost.")
    w("- **Why the lower bound is carried.** Read only when significant, an estimate overstates the true uplift "
      "(Gelman & Carlin). At the design's standard error:\n")
    w("| true uplift (points) | power | sign-error rate | expected exaggeration if significant |")
    w("|---|---|---|---|")
    for eff, pw, s_err, ex in uplift_rows:
        w(f"| {eff:.1f} | {pw:.2f} | {s_err:.1e} | {ex:.2f} |")
    w(f"\nA pilot that lands exactly on the gate has a lower bound of {out['lower_at_gate']:.1f} points. That, not "
      "the point estimate, replaces `upgrade_capture_uplift` in the benefits case. Published nudge effects shrink "
      f"from {V['dvl_academic_pp']:.1f} to {V['dvl_nudge_unit_pp']:.1f} points at scale, about "
      f"{V['dvl_publication_share_pct']:.0f}% of it selective publication (`dvl_*`): one pre-registered arm and a "
      "powered sample remove that source; the lower bound covers the rest.\n")

    w("## Phase 3: the engine, the band and execution\n")
    w(f"- **Coverage:** {n_cov} returned cars put a correctly calibrated 80% band inside "
      f"{100 * p_band - V['gate_engine_coverage_tol_pts']:.0f}-{100 * p_band + V['gate_engine_coverage_tol_pts']:.0f}% "
      f"{V['gate_read_confidence_pct']:.0f} times in 100.")
    w(f"- **Against the guide:** the engine's typical error ({V['engine_err_typical']:g}%, a median absolute error) as a "
      f"normal spread of {sd:.1f} points; the paired difference's spread depends on how far the two errors move "
      "together on the same car:\n")
    w("| correlation of the two errors | paired cars needed |")
    w("|---|---|")
    for r in RHO_GUIDE:
        w(f"| {r:.2f} | {pair[r]} |")
    w(f"\n- **Returns available:** the book due within a year (`buyback_payables_current_eur_m`), the core markets' "
      f"share, one phase, at Aramis's realised retail price per car (EUR {out['price_per_car']:,.0f}, "
      f"`aramis_fy25_b2c_*`): an order of {round(returns_core, -4):,.0f} cars. A retail price is above what the group pays back, "
      "so the count errs low. Every Phase 3 read needs a small fraction of it.")
    w("- **The band decision:** sold cars with a logged first proposal needed to tell apart pricer information "
      "(rho², X13) at the break-evens:\n")
    w("| decision | from | to | sold cars |")
    w("|---|---|---|---|")
    w(f"| engine only, or the tied band | 0 | {V['x13_be_fixed_vs_engine']:.2f} | {n_band['engine only, or the tied band']} |")
    w(f"| the tied band, or the full band | {V['x13_be_fixed_vs_engine']:.2f} | {V['x13_be_full_vs_fixed']:.2f} | "
      f"{n_band['the tied band, or the full band']} |\n")
    w("- **Why the adherence gate goes:** under a hard band every price is inside it, so the share inside is 100% by "
      "construction; and a share of adherence rewards deploying where people already comply (Goodhart). What the band "
      "needs to know is how much of the engine's error pricers can see, which the logged proposals measure.")
    w("- **Why the residual-cost gate goes:** contracts written in Phase 3 return 36-48 months later, and their loss is "
      "mostly the level, which nothing forecasts beyond a quarter (X7). Its 15% was also about twice the one published "
      f"gain from a residual model's loss function (`dress_asym_cost_cut_pct`, {V['dress_asym_cost_cut_pct']:.0f}%). "
      "The cars returning now answer the engine's question inside the phase.\n")

    w("## What this does not show\n")
    w("- **The sizing grids are hypothetical true values,** not estimates; the samples are fixed before each phase.")
    w("- **France's contract endings assume a steady book** (as many end as start); the pilot also needs its dealers' "
      "customers to be reachable in time.")
    w("- **The engine's spread is a normal approximation** from a median absolute error on adverts; the paired "
      "correlation with the guide is unknown until Phase 3's first cars, so the grid is shown.")
    w("- **The count of returns is an order of magnitude** from euros and a retail price per car.")
    w("- **O'Brien-Fleming assumes an immediate outcome;** orders signed inside the phase are one, by design.\n")
    w("## Checks\n")
    w("| check | got | passes |")
    w("|---|---|---|")
    for n_, g, p in ck.itertuples(index=False):
        w(f"| {n_} | {g} | {'yes' if p else '**NO**'} |")
    w(f"\n{'All checks pass.' if ok else 'A CHECK FAILED.'}")
    OUT.write_text("\n".join(L) + "\n")
    print(ck.to_string(index=False))
    print("prec", prec, "rec", rec, "switch", [round(x, 3) for x in sw], "money", [round(x, 2) for x in money],
          "floor", [round(x, 1) for x in floor])
    print("pilot share half", round(out["pilot_share_half"], 1), round(out["pilot_share_half_spill"], 1),
          "obf", [round(x, 4) for x in out["obf"]], "lower at gate", round(out["lower_at_gate"], 2))
    print("n_cov", n_cov, "pair", pair, "returns", round(returns_core), "band", n_band)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
