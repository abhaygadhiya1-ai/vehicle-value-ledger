"""Audit the value-at-risk workbook: recompute every output from assumptions.csv by hand and compare.

The formulas here are written independently of build_var_model.py, so a mistake shared by the two
would have to be made twice. It also checks every named cell points at its own input row, every
formula carries a stored result, and no number other than a unit conversion or month arithmetic is
typed into a formula.

Usage: .venv/bin/python audit_workbook.py   (after build_var_model.py)
"""
import csv
import math
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

HERE = Path(__file__).parent
CSV = HERE / "assumptions.csv"
WB = HERE.parent / "Case4_Value_at_Risk.xlsx"

rows = list(csv.DictReader(CSV.open()))
V = {r["id"]: float(r["value"]) for r in rows if r["value"]}
LO = {r["id"]: float(r["low"]) for r in rows if r["low"]}
HI = {r["id"]: float(r["high"]) for r in rows if r["high"]}
wb_f = load_workbook(WB)
wb = load_workbook(WB, data_only=True)
problems, checks = [], 0


def close(a, b, tol=1e-6):
    return a is not None and b is not None and math.isclose(float(a), float(b), rel_tol=tol, abs_tol=1e-9)


def check(label, got, want):
    global checks
    checks += 1
    if not close(got, want):
        problems.append(f"{label}: workbook {got} vs recomputed {want}")


def row_by_label(ws, text, col=2):
    for r in ws.iter_rows():
        if r[0].value and str(r[0].value).strip().startswith(text.strip()):
            return r[col - 1].value, r
    problems.append(f"label not found on {ws.title}: {text}")
    return None, None


def model(v):
    L1 = (v["eu_revenue_eur_m"] * v["x14_incentive_claims_central"] / 100 * v["process_leak_pct"] / 100
          + v["eu_revenue_eur_m"] * v["x5_targeting_gain_central"] / 100)
    L2 = v["sfse_eu_nv_contracts_2025"] * v["upgrade_capture_uplift"] / 100 * v["margin_per_repeat_sale"] / 1e6
    thin = v["thin_share_of_book"] / 100
    curve1 = (v["curve_1y_p80_known"] / 2 / v["retained_1y_pooled"] * (1 - thin)
              + v["curve_1y_p80_unknown"] / 2 / v["retained_1y_pooled"] * thin)
    cur = v["buyback_payables_current_eur_m"]
    execu = cur * (v["x17_days_cut"] * v["x17_day_cost_central"] / 10000
                   + v["x17_share_routed"] / 100 * v["x17_channel_gain_after_costs"] / 100)  # resale execution (X17)
    # One year in ten, the level and the curve take their joint p10 as a measured share of their sum (X18); the sum
    # is the upper end. Expected a year, the level and curve count both ways, floored at zero (a gain is no leak).
    share = {"level_1y_p10_book": v["x18_joint_share_book"], "level_1y_p10_core": v["x18_joint_share_stress"]}
    L3 = lambda lvl: cur * (abs(v[lvl]) / 100 + curve1) * share[lvl] / 100 + execu  # noqa: E731
    return L1, L2, L3, curve1


def expected_leak3(v):
    """Leak 3 expected a year (X18): the two-sided level and curve line, floored at zero, plus resale execution."""
    cur = v["buyback_payables_current_eur_m"]
    execu = cur * (v["x17_days_cut"] * v["x17_day_cost_central"] / 10000
                   + v["x17_share_routed"] / 100 * v["x17_channel_gain_after_costs"] / 100)
    return cur * max(0.0, v["x18_exp_twosided_book"]) / 100 + execu


def sum_leak3(v, lvl):
    """Leak 3 with the level and the curve at their separate p10s, added: the upper end."""
    thin = v["thin_share_of_book"] / 100
    curve1 = (v["curve_1y_p80_known"] / 2 / v["retained_1y_pooled"] * (1 - thin)
              + v["curve_1y_p80_unknown"] / 2 / v["retained_1y_pooled"] * thin)
    cur = v["buyback_payables_current_eur_m"]
    return cur * (abs(v[lvl]) / 100 + curve1) + expected_leak3(v) - cur * max(0.0, v["x18_exp_twosided_book"]) / 100


# ---- named cells point at their own row ----
ws_a = wb_f["Assumptions"]
for name, dn in wb_f.defined_names.items():
    m = re.match(r"Assumptions!\$C\$(\d+)", dn.attr_text)
    checks += 1
    if not m:
        problems.append(f"named cell {name} does not point at Assumptions column C: {dn.attr_text}")
        continue
    r = int(m.group(1))
    if ws_a.cell(r, 1).value != name:
        problems.append(f"named cell {name} points at row of {ws_a.cell(r, 1).value}")
    elif not close(wb["Assumptions"].cell(r, 3).value, V[name]):
        problems.append(f"named cell {name} value {wb['Assumptions'].cell(r, 3).value} vs CSV {V[name]}")
valued = {r["id"] for r in rows if r["value"]}
missing = valued - set(wb_f.defined_names.keys())
checks += 1
if missing:
    problems.append(f"inputs with a value but no named cell: {sorted(missing)}")

# ---- Summary ----
# Leak 3's base is the group's own book's one-in-ten-year fall; the stress a core market's, on the whole book.
BASE, STRESS = "level_1y_p10_book", "level_1y_p10_core"
L1, L2, L3, curve1 = model(V)
L3E = expected_leak3(V)
S = wb["Summary"]


def row_after(ws, title, text, col):
    """The first row starting with `text` below the row whose first cell starts with `title`."""
    seen = False
    for r in ws.iter_rows():
        v = str(r[0].value or "").strip()
        if v.startswith(title):
            seen = True
        elif seen and v.startswith(text.strip()):
            return r[col - 1].value, r
    problems.append(f"label not found on {ws.title} after {title}: {text}")
    return None, None


total = L1 + L2 + L3(BASE)            # one year in ten
total_e = L1 + L2 + L3E                # expected a year
cur_book = V["buyback_payables_current_eur_m"]
for leak, e, t in (("Leak 1", L1, L1), ("Leak 2", L2, L2), ("Leak 3", L3E, L3(BASE))):
    _, r = row_by_label(S, leak)
    check(f"Summary {leak} expected", r[1].value, e)
    check(f"Summary {leak} one in ten", r[2].value, t)
_, r = row_by_label(S, "Total value at risk a year")
check("Summary total expected", r[1].value, total_e)
check("Summary total one in ten", r[2].value, total)
_, r = row_by_label(S, "Upper end, in no total")
check("Summary upper end expected", r[1].value, total_e + cur_book * V["x18_exp_onesided_book"] / 100)
check("Summary upper end one in ten", r[2].value, L1 + L2 + sum_leak3(V, BASE))
_, r = row_by_label(S, "Stress: the whole book")
check("Summary stress total", r[2].value, L1 + L2 + L3(STRESS))
_, r = row_by_label(S, "Stress, upper end")
check("Summary stress upper end", r[2].value, L1 + L2 + sum_leak3(V, STRESS))
targeting = V["eu_revenue_eur_m"] * V["x5_targeting_gain_central"] / 100
_, r = row_by_label(S, "Total without the targeting line")
check("Summary expected without targeting", r[1].value, total_e - targeting)
check("Summary one in ten without targeting", r[2].value, total - targeting)

swap_ids = ["process_leak_pct",
            "upgrade_capture_uplift", "margin_per_repeat_sale", "thin_share_of_book", "x17_days_cut", "x17_share_routed"]
rng = {}
for which, src in (("low", LO), ("high", HI), ("base", V)):
    v2 = dict(V)
    if which != "base":
        for k in swap_ids:
            v2[k] = src[k]
        v2["x5_targeting_gain_central"] = V[f"x5_targeting_gain_{which}"]  # a derived range: two rows of its own
        v2["x14_incentive_claims_central"] = V[f"x14_incentive_claims_{which}"]  # the same
        v2["x17_day_cost_central"] = V[f"x17_day_cost_{which}"]  # the same
        if which == "high":  # the retail gain: after all costs at low and base, before operating costs at high
            v2["x17_channel_gain_after_costs"] = V["x17_channel_gain_before_opex"]
    a, b, c, _ = model(v2)
    e = expected_leak3(v2)
    rng[which] = {"Leak 1": a, "Leak 2": b, "Leak 3, expected a year": e, "Leak 3, one year in ten": c(BASE),
                  "Total, expected a year": a + b + e, "Total, one year in ten": a + b + c(BASE)}
for label in rng["base"]:
    for j, which in enumerate(("low", "base", "high")):
        check(f"Summary range {label} {which}", row_after(S, "Range from the assumed inputs", label, 2 + j)[0],
              rng[which][label])

exec3 = cur_book * (V["x17_days_cut"] * V["x17_day_cost_central"] / 10000
                    + V["x17_share_routed"] / 100 * V["x17_channel_gain_after_costs"] / 100)
for label, e, t in (("Disclosed exposure, measured shocks", L3E - exec3, L3(BASE) - exec3),
                    ("Measured costs, assumed reach", exec3, exec3),
                    ("Measured timing, assumed conversion", L2, L2),
                    ("Disclosed base, assumed leak rate", L1 - targeting, L1 - targeting),
                    ("Derived from published studies", targeting, targeting)):
    _, r = row_by_label(S, label)
    check(f"Summary split {label} expected EUR", r[1].value, e)
    check(f"Summary split {label} expected share", r[2].value, e / total_e)
    check(f"Summary split {label} one in ten EUR", r[3].value, t)
    check(f"Summary split {label} one in ten share", r[4].value, t / total)
labels = {r["id"]: r["label"] for r in rows}
for k in swap_ids:
    _, r = row_by_label(S, labels[k])
    lo_v, hi_v = dict(V), dict(V)
    lo_v[k], hi_v[k] = LO[k], HI[k]
    a = model(lo_v); b = model(hi_v)
    tl = a[0] + a[1] + a[2](BASE)
    th = b[0] + b[1] + b[2](BASE)
    check(f"Sensitivity {k} low", r[2].value, tl)
    check(f"Sensitivity {k} high", r[3].value, th)
    check(f"Sensitivity {k} swing", r[4].value, abs(th - tl))
    check(f"Sensitivity {k} expected swing", r[5].value,
          abs((b[0] + b[1] + expected_leak3(hi_v)) - (a[0] + a[1] + expected_leak3(lo_v))))

# ---- Leak 1 sheet ----
W1 = wb["Leak 1 - Incentives"]
spend = V["eu_revenue_eur_m"] * V["x14_incentive_claims_central"] / 100
check("Leak1 spend", row_by_label(W1, "Incentive claims")[0], spend)
check("Leak1 process", row_by_label(W1, "    Claims paid twice")[0], spend * V["process_leak_pct"] / 100)
check("Leak1 targeting", row_by_label(W1, "    Profit lost by giving every buyer")[0], targeting)
check("Leak1 total", row_by_label(W1, "Value at risk, leak 1")[0], L1)
check("Leak1 recoverable", row_by_label(W1, "Of which a controls layer")[0],
      spend * V["process_leak_pct"] / 100 * V["recoverable_share"] / 100)

# ---- Leak 2 sheet ----
W2 = wb["Leak 2 - Upgrade timing"]
curve = [100, V["retained_1y_uk"], V["retained_2y_uk"], V["retained_3y_uk"], V["retained_4y_uk"], V["retained_5y_uk"]]
for j, want in enumerate(curve):
    check(f"Leak2 curve year {j}", W2.cell(7, 2 + j).value, want)
dep, n, apr = V["loan_deposit_pct"], V["loan_term_months"], V["loan_apr"] / 1200
head = 17
first = {}
for m in range(61):
    bal = 0 if m >= n else (100 - dep) * ((1 + apr) ** n - (1 + apr) ** m) / ((1 + apr) ** n - 1)
    a = min(4, m // 12)
    val = curve[a] + (m / 12 - a) * (curve[a + 1] - curve[a])
    vals = {"B": bal, "C": val, "D": val - bal,
            "F": val * (1 + V["level_3y_p10_core"] / 100) - bal,
            "H": val * (1 + V["level_3y_worst"] / 100) - bal}
    r = head + 1 + m
    for col, want in vals.items():
        check(f"Leak2 month {m} {col}", W2[f"{col}{r}"].value, want)
    for col in ("D", "F", "H"):
        if m >= 12 and col not in first and vals[col] >= dep:
            first[col] = m
_, rn = row_by_label(W2, "Measured with the first year")
for j, name in enumerate(["window_nl_measured_m", "window_nl_p10_m", "window_nl_worst_m"]):
    check(f"Leak 2 measured window {name}", rn[1 + j].value, V[name])
_, r = row_by_label(W2, "Equity covers the next deposit")
for j, col in enumerate(("D", "F", "H")):
    checks += 1
    want = first.get(col, "not within the term")
    if r[1 + j].value != want:
        problems.append(f"Leak2 window {col}: workbook {r[1 + j].value} vs recomputed {want}")
contracts = V["sfse_eu_nv_contracts_2025"]
check("Leak2 contracts", row_by_label(W2, "Contracts financed")[0], contracts)
check("Leak2 retained", row_by_label(W2, "    Extra customers")[0], contracts * V["upgrade_capture_uplift"] / 100)
check("Leak2 total", row_by_label(W2, "Value at risk, leak 2")[0], L2)

# ---- Leak 3 sheet ----
W3 = wb["Leak 3 - Residual value"]
cur, book = V["buyback_payables_current_eur_m"], V["buyback_payables_eur_m"]
thin = V["thin_share_of_book"] / 100
curve3 = (V["curve_p80_known"] / 2 / V["retained_3y_pooled"] * (1 - thin)
          + V["curve_p80_unknown"] / 2 / V["retained_3y_pooled"] * thin)
expect3 = [
    ("Payables for buy-back agreements, the whole book", book),
    ("Exposure a year", cur),
    ("    Base: the group's book, spread", cur * abs(V[BASE]) / 100),
    ("    Stress: the whole book in a core market's bad year", cur * abs(V[STRESS]) / 100),
    ("    Reference, in no total: p10 across all 26", cur * abs(V["level_1y_p10"]) / 100),
    ("    Reference, in no total: the worst twelve-month", cur * abs(V["level_1y_worst"]) / 100),
    ("    Reference, in no total: the battery-EV slice", cur * V["x9_group_bev_share_2024"] / 100
     * abs(V["x9_pl_ev_slump_gap"]) / 100),
    ("    Curve error on the part of the book", cur * V["curve_1y_p80_known"] / 2 / V["retained_1y_pooled"] * (1 - thin)),
    ("    Curve error on little-history cars", cur * V["curve_1y_p80_unknown"] / 2 / V["retained_1y_pooled"] * thin),
    ("    Days cut from the time to sale", cur * V["x17_days_cut"] * V["x17_day_cost_central"] / 10000),
    ("    A share of returns retailed in-house", cur * V["x17_share_routed"] / 100 * V["x17_channel_gain_after_costs"] / 100),
    ("Priced, not recovered: the level at its p10 (base)", cur * abs(V[BASE]) / 100),
    ("Recoverable: the car and its sale", cur * curve1 + exec3),
    ("    Level and curve, expected a year, both sides counted", cur * max(0.0, V["x18_exp_twosided_book"]) / 100),
    ("    Reference, in no total: the same on the UK's 1988-2026 record", cur * V["x18_exp_twosided_uk_long"] / 100),
    ("    Upper end, in no total: only losses counted, per contract", cur * V["x18_exp_onesided_book"] / 100),
    ("Value at risk, leak 3, expected a year", L3E),
    ("    Level and curve together, one year in ten (base)", L3(BASE) - exec3),
    ("Value at risk, leak 3, one year in ten (base", L3(BASE)),
    ("Value at risk, leak 3, one year in ten (stress", L3(STRESS)),
    ("    Upper end, in no total: the level and the curve at their p10s at once (base)", sum_leak3(V, BASE)),
    ("    Upper end, in no total: the same under the stress", sum_leak3(V, STRESS)),
    ("    Resale execution: days cut and in-house retail", exec3),
    ("    Decrease in value on assets sold with a buy-back commitment, 2023", V["buyback_value_decrease_2023_eur_m"]),
    ("    Decrease in value on assets sold with a buy-back commitment, 2024", V["buyback_value_decrease_2024_eur_m"]),
    ("    Decrease in value on assets sold with a buy-back commitment, 2025", V["buyback_value_decrease_2025_eur_m"]),
    ("    Base: the group's book over 36 months", book * (abs(V["level_3y_p10_book"]) / 100 + curve3)),
    ("    Stress: the whole book in a core market's bad three years", book * (abs(V["level_3y_p10_core"]) / 100 + curve3)),
    ("    Reference, in no total: the worst three-year", book * (abs(V["level_3y_worst"]) / 100 + curve3)),
    ("    Pooling the group's markets", cur * V["curve_1y_p80_unknown"] / 2 / V["retained_1y_pooled"] * thin * V["pooling_gain_100"] / 100),
    ("    Re-marking monthly", book * (abs(V["level_3m_p5"]) - abs(V["level_1m_p5"])) / 100),
]
for label, want in expect3:
    check(f"Leak3 {label.strip()}", row_by_label(W3, label)[0], want)

# ---- Per car ----
# Recomputed from the inputs, not from the workbook's own leak sheets.
PC = wb["Per car"]
lst = V["new_car_price_eur"]
ship = V["eu_shipments"]
pl = {
    "Sale margin": lst * V["pl_sale_margin_pct_list"] / 100,
    "less incentives": -lst * V["pl_incentive_pct_list"] / 100,
    "plus finance income": V["pl_finance_income_eur"],
    "less credit losses": V["pl_credit_loss_eur"],
    "plus service and parts margin": V["pl_service_parts_eur"],
    "less warranty cost": -lst * V["pl_warranty_pct_list"] / 100,
    "less reconditioning, logistics and holding": V["pl_recon_logistics_eur"],
    "plus remarketing margin": V["pl_remarketing_margin_eur"],
}
check("Per car list price", row_by_label(PC, "List price when new")[0], lst)
for label, want in pl.items():
    check(f"Per car {label}", row_by_label(PC, label)[0], want)
central = sum(pl.values())
check("Per car lifetime value", row_by_label(PC, "Lifetime value per car")[0], central)
dn_level = -lst * V["retained_4y_uk"] / 100 * abs(V["level_3y_p10_core"]) / 100
dn_curve = -lst * V["curve_p80_known"] / 100
check("Per car downside level", row_by_label(PC, "Residual downside - market level")[0], dn_level)
check("Per car downside curve", row_by_label(PC, "Residual downside - curve error")[0], dn_curve)
check("Per car bad market", row_by_label(PC, "Lifetime value in a bad market")[0],
      central + dn_level + dn_curve)

for label, name in (("Level charge: expected loss per 48-month contract", "x6_loss_contract_group_48m"),
                    ("Level charge per month, set aside at the ECB rate", "x6_charge_month_group_48m"),
                    ("Capital cost of holding it", "x6_capital_contract_group_48m"),
                    ("Price to hold the level risk per contract", "x6_price_contract_group_48m"),
                    ("Average loss in the worst tenth of windows", "x6_worst_tenth_group_48m"),
                    ("Charge with the level below its 3-year average", "x6_charge_cold_48m"),
                    ("Charge in the middle tercile", "x6_charge_middle_48m"),
                    ("Share of losses a charge set from past data covered", "x6_oos_coverage_48m")):
    check(f"Per car X6 {name}", row_by_label(PC, "    " + label)[0] if not label.startswith("Price")
          else row_by_label(PC, label)[0], V[name])
check("Per car X9 battery-EV contract", row_by_label(PC, "    Expected level loss on a battery-EV contract")[0],
      V["x6_loss_contract_group_48m"] * V["x9_us_ratio_48m_median"])
check("Per car leak 2 per financed contract", row_by_label(PC, "Leak 2 at risk per financed contract")[0],
      L2 * 1e6 / V["sfse_eu_nv_contracts_2025"])
# Each of the three is rounded to the euro in the register, so their sum may differ by one euro.
checks += 1
if abs(V["x6_loss_contract_group_48m"] + V["x6_capital_contract_group_48m"] - V["x6_price_contract_group_48m"]) > 1:
    problems.append("Per car X6: the price to hold is not the expected loss plus the capital cost (to the euro)")

aoi24 = V["eu_aoi_2024_eur_m"] * 1e6 / V["eu_shipments_2024"]
aoi25 = V["eu_aoi_eur_m"] * 1e6 / ship
check("Per car revenue per vehicle", row_by_label(PC, "Enlarged Europe net revenue per vehicle")[0],
      V["eu_revenue_eur_m"] * 1e6 / ship)
check("Per car result 2024", row_by_label(PC, "Operating result per vehicle, 2024")[0], aoi24)
check("Per car result 2025", row_by_label(PC, "Operating result per vehicle, 2025")[0], aoi25)
check("Per car swing", row_by_label(PC, "Swing between the two years")[0], aoi24 - aoi25)
for label, part in (("Leak 1 at risk per vehicle", L1), ("Leak 2 at risk per vehicle", L2),
                    ("Leak 3 at risk per vehicle, expected a year", L3E),
                    ("Leak 3 at risk per vehicle, one year in ten", L3(BASE))):
    check(f"Per car {label}", row_by_label(PC, label)[0], part * 1e6 / ship)
check("Per car total expected", row_by_label(PC, "Total at risk per vehicle, expected a year")[0],
      total_e * 1e6 / ship)
check("Per car total one in ten", row_by_label(PC, "Total at risk per vehicle, one year in ten")[0],
      total * 1e6 / ship)
check("Per car stress", row_by_label(PC, "Under the stress level shock")[0],
      (L1 + L2 + L3(STRESS)) * 1e6 / ship)
check("Per car leakage vs 2025 result", row_by_label(PC, "Leakage against the 2025 result")[0],
      -(total_e * 1e6 / ship) / aoi25)

sys.path.insert(0, str(HERE / "analysis"))
import programme_cost as pcm  # noqa: E402

PCM = pcm.model(V, pcm.work())
check("Per car value at risk", row_by_label(PC, "Value at risk a year, expected")[0], total_e)
for sk, slabel in pcm.SCENARIOS:
    cost = PCM["base"][sk]["total"]
    check(f"Per car programme cost {sk}", row_by_label(PC, f"Programme cost over 24 months, {slabel}")[0], cost)
    check(f"Per car break-even share {sk}",
          row_by_label(PC, f"Share of it the programme must capture to break even, {slabel}")[0], cost / total_e)

seen_n = []
for row in PC.iter_rows(min_col=1, max_col=3):
    n = row[0].value
    if isinstance(n, int) and n in (1, 10, 100, 1000, 10000):
        seen_n.append(n)
        check(f"Per car error at n={n}", row[1].value, V["engine_err_typical"] / math.sqrt(n))
        check(f"Per car level at n={n}", row[2].value, V["level_points"])
checks += 1
if seen_n != [1, 10, 100, 1000, 10000]:
    problems.append(f"Per car averaging table has rows {seen_n}")

# ---- a target, or a figure from a synthetic world, never reaches a value-at-risk formula ----
# One check over the whole workbook, in the same style as the stored-value sweep below.
targets = {r["id"] for r in rows if r["tier"] in ("TARGET", "SYNTHETIC")}
leaked = [f"{ws.title}!{c.coordinate} uses {n}"
          for ws in wb_f if ws.title not in ("Assumptions", "Provenance")
          for row in ws.iter_rows() for c in row
          if isinstance(c.value, str) and c.value.startswith("=")
          for n in targets if re.search(rf"\b{re.escape(n)}\b", c.value)]
checks += 1
if leaked:
    problems.append(f"a target the team chose, or a synthetic figure, reaches a formula: {leaked[:3]}")

# ---- Prior discounting ----
# Recomputed from the inputs. This sheet is a decomposition of leak 1 and leak 3, not an
# addition, so the headline below must be unchanged by it - which the totals above already test.
PD = wb["Prior discounting"]
disc = V["pl_incentive_pct_list"]
given = lst * disc / 100
resid = lst * V["retained_4y_uk"] / 100
share_lo = 1 - (1 - disc / 100) ** V["dpt_passthrough"]
share_hi = (V["hk_passthrough_36m"] + V["hk_passthrough_now"]) / 100 * disc / 10
for label, want in [
    ("Share of a deeper deal still there at resale", V["dpt_passthrough"]),
    ("Published: % of residual lost at 36 months", V["hk_passthrough_36m"]),
    ("Published: the same in the same month", V["hk_passthrough_now"]),
    ("Discount assumed given", disc),
    ("List price when new", lst),
    ("Incentive given at the new sale", given),
    ("Residual value when it comes back", resid),
    ("Share of that residual lost, measured (low)", share_lo),
    ("Share of that residual lost, published (high)", share_hi),
    ("Residual lost to the discount, low", resid * share_lo),
    ("Residual lost to the discount, high", resid * share_hi),
    ("Cost at resale per euro of incentive given, low", resid * share_lo / given),
    ("Cost at resale per euro of incentive given, high", resid * share_hi / given),
    ("Buy-back residual falling due within a year", V["buyback_payables_current_eur_m"]),
    ("Of that, traceable to our own prior discounting - low",
     V["buyback_payables_current_eur_m"] * share_lo),
    ("Of that, traceable to our own prior discounting - high",
     V["buyback_payables_current_eur_m"] * share_hi),
]:
    check(f"Prior discounting {label}", row_by_label(PD, label)[0], want)
# ---- Internal prices (X19) ----
# Recomputed from the inputs: the Leak 2 loan and value curve above, the Prior discounting shares, the finance arm's
# margin from SFSE's figures, X6's and X19's level prices, the early-repayment caps.
IP = wb["Internal prices"]
resid4 = lst * V["retained_4y_uk"] / 100
for label, lo_want, hi_want in (
        ("Resale value lost per euro of incentive", resid4 * share_lo / given, resid4 * share_hi / given),
        ("On the sample car's incentive", resid4 * share_lo, resid4 * share_hi),
        ("What one more euro of discount costs the group", -(1 + resid4 * share_lo / given),
         -(1 + resid4 * share_hi / given))):
    _, r = row_by_label(IP, label)
    check(f"Internal {label} low", r[1].value, lo_want)
    check(f"Internal {label} high", r[2].value, hi_want)
holding = (V["crr_total_capital_ratio"] + V["crd_conservation_buffer"]) / 100 * (V["eba_bank_coe"] - V["ecb_deposit_rate"])
for label, want in (("Customer-option contract, 48 months", V["x6_price_share_group_48m"]),
                    ("on the sample car's 48-month residual", resid4 * V["x6_price_share_group_48m"] / 100),
                    ("Buy-back contract, a year or less", max(0.0, V["x19_core_all_two_12m"])),
                    ("plus when the level starts in its cold third", V["x19_core_cold_premium_12m"]),
                    ("plus the cost of holding the tail", holding),
                    ("the holding cost on the buy-back book", V["buyback_payables_current_eur_m"] * holding / 100),
                    ("the cold premium on the same book",
                     V["buyback_payables_current_eur_m"] * V["x19_core_cold_premium_12m"] / 100),
                    ("The pricer's override band, cars 2-4 years", V["x13_tied_cap_young"]),
                    ("cars 12 years and older", V["x13_tied_cap_old"]),
                    ("Share of the buy-back book that comes back within a year",
                     V["buyback_payables_current_eur_m"] / V["buyback_payables_eur_m"]),
                    ("Group brands' share of new cars registered", V["selfreg_group_monthend_share"]),
                    ("other brands, same period", V["selfreg_other_monthend_share"]),
                    ("Revenue gain when one firm removed", V["misra_nair_revenue_gain_pct"])):
    check(f"Internal {label}", row_by_label(IP, label)[0], want)


# Own names: `n` is reused above for the Per car sheet's averaging table.
TERM, DEP, APR = int(V["loan_term_months"]), V["loan_deposit_pct"], V["loan_apr"] / 1200
CURVE = [100, V["retained_1y_uk"], V["retained_2y_uk"], V["retained_3y_uk"], V["retained_4y_uk"], V["retained_5y_uk"]]


def bal(m):
    return 0 if m >= TERM else (100 - DEP) * ((1 + APR) ** TERM - (1 + APR) ** m) / ((1 + APR) ** TERM - 1)


def val(m):
    a = min(4, m // 12)
    return CURVE[a] + (m / 12 - a) * (CURVE[a + 1] - CURVE[a])


fin_rate = ((V["sfse_pnb_ifrs8_2025_eur_m"] - V["sfse_cor_ifrs8_2025_eur_m"])
            / (V["sfse_cor_ifrs8_2025_eur_m"] / (V["sfse_cor_pct_outstanding_2025"] / 100)))
for j, k in enumerate((int(LO["x19_pull_forward_months"]), int(V["x19_pull_forward_months"]),
                       int(HI["x19_pull_forward_months"]))):
    s = TERM - k
    avg_old = sum(bal(m) for m in range(s, TERM)) / k
    avg_new = sum(bal(m) for m in range(0, k)) / k
    cap = V["ccd2_early_repayment_cap_pct"] if k > 12 else V["ccd2_early_repayment_cap_last_year_pct"]
    for label, want in (("Months pulled forward", k),
                        ("Old contract's balance at the switch", bal(s) * lst / 100),
                        ("Car value at the switch", val(s) * lst / 100),
                        ("Customer's equity at the switch less the next deposit", (val(s) - bal(s) - DEP) * lst / 100),
                        ("A younger car: value at the switch", (val(s) - val(TERM)) * lst / 100),
                        ("Finance arm's margin a year per euro outstanding", fin_rate),
                        ("Finance arm, taker refinances with the group", fin_rate * (avg_new - avg_old) / 100 * lst * k / 12),
                        ("Finance arm, taker finances elsewhere", -fin_rate * avg_old / 100 * lst * k / 12),
                        ("most it may charge for early repayment",
                         min(cap / 100 * bal(s), V["loan_apr"] / 100 * avg_old * k / 12) * lst / 100),
                        ("Retained sale: contribution per customer won", V["margin_per_repeat_sale"]),
                        ("Retention gain per customer contacted",
                         V["upgrade_capture_uplift"] / 100 * V["margin_per_repeat_sale"])):
        check(f"Internal trade-off k={k} {label}", row_by_label(IP, label, 2 + j)[0], want)
lifetime = central
x6_lvl = resid4 * V["x6_price_share_group_48m"] / 100
for label, lo_want, hi_want in (("Lifetime value per car, the Per car sheet's P&L", lifetime, lifetime),
                                ("less the incentive's resale cost", -resid4 * share_lo, -resid4 * share_hi),
                                ("less the level's price to hold", -x6_lvl, -x6_lvl),
                                ("Predicted lifetime value at sale", lifetime - resid4 * share_lo - x6_lvl,
                                 lifetime - resid4 * share_hi - x6_lvl)):
    _, r = row_by_label(IP, label)
    check(f"Internal metric {label} low", r[1].value, lo_want)
    check(f"Internal metric {label} high", r[2].value, hi_want)

# ---- Data reach (X20) ----
DR = wb["Data reach"]
claims1 = V["eu_revenue_eur_m"] * V["x14_incentive_claims_central"] / 100 * V["process_leak_pct"] / 100
exp_risk = V["buyback_payables_current_eur_m"] * max(0.0, V["x18_exp_twosided_book"]) / 100
reach = {
    "Leak 1, claims": (claims1, claims1, claims1 * V["x20_reg_route_any_2024"] / 100),
    "Leak 1, targeting": (targeting * V["finance_penetration"] / 100, targeting * V["x14_agency_share_2025p"] / 100,
                          targeting * V["finance_penetration"] / 100),
    "Leak 2, upgrade moments": (L2, 0.0, L2),
    "Leak 3, resale execution": (exec3, exec3, exec3),
    "Leak 3, level and curve": (exp_risk, exp_risk, exp_risk),
}
for label, wants in reach.items():
    _, r = row_by_label(DR, label)
    for j, want in enumerate(wants):
        check(f"Data reach {label} col {j}", r[1 + j].value, want)
sums = [sum(w[j] for w in reach.values()) for j in range(3)]
_, r = row_by_label(DR, "Reachable, expected a year")
_, rs = row_by_label(DR, "Share of the expected column")
for j in range(3):
    check(f"Data reach total col {j}", r[1 + j].value, sums[j])
    check(f"Data reach share col {j}", rs[1 + j].value, sums[j] / total_e)

# ---- Benefits (X21) ----
# Checked against analysis/benefits_case.py's model, written apart from the builder's formulas: the same arithmetic in
# Python, so a slip in either shows here.
sys.path.insert(0, str(HERE / "analysis"))
import benefits_case as bc  # noqa: E402

BM = bc.model(V, {"low": LO, "high": HI})
BS = wb["Benefits"]
lever_label = {k: lab for k, lab, *_ in bc.LEVERS}
for k, lab in lever_label.items():
    _, r = row_by_label(BS, lab)
    for j, reach in enumerate(bc.REACH):
        check(f"Benefits lever {k} {reach}", r[3 + j].value, BM["rates"][reach][k])
    check(f"Benefits lever {k} adverse", r[6].value, BM["adverse"]["rates"][k])
_, r = row_by_label(BS, "Committed, expected a year")
for j, reach in enumerate(bc.REACH):
    check(f"Benefits committed {reach}", r[3 + j].value, BM["committed"][reach])
check("Benefits committed adverse", r[6].value, BM["adverse"]["committed"])
check("Benefits claims = Leak 1's recovered line", BM["rates"]["every"]["claims"],
      row_by_label(W1, "Of which a controls layer actually recovers")[0])
check("Benefits execution = leak 3's execution", BM["rates"]["every"]["exec_days"] + BM["rates"]["every"]["exec_route"],
      exec3)
check("Benefits retention = leak 2", BM["rates"]["every"]["retention"], L2)
import programme_cost as pc  # noqa: E402

SCN = dict(pc.SCENARIOS)
for name, c in list(BM["cases"].items()) + [(bc.ADVERSE_CASE, BM["cases"]["reference class"])]:
    rr = [x for x in BS.iter_rows() if x[0].value == name and x[4].value is not None and x[5].value is None]
    if rr:
        check(f"Benefits case {name} benefits", rr[0][1].value, c["b"])
        check(f"Benefits case {name} build", rr[0][2].value, c["c"])
        check(f"Benefits case {name} months", rr[0][3].value, c["m"])
    else:
        problems.append(f"Benefits case parameters not found: {name}")
case_rows = {r[0].value: r for r in BS.iter_rows() if isinstance(r[0].value, str) and isinstance(r[6].value, (int, float))}
for sk, sc in BM["costs"].items():
    Sb = BM["scen"][sk]
    for name in Sb["payback"]:
        r = case_rows.get(f"{SCN[sk]}, {name}")
        if r is None:
            problems.append(f"Benefits payback and value row not found: {SCN[sk]}, {name}")
            continue
        want = Sb["payback"][name]
        checks += 1
        if want is None and r[1].value != "none within ten years" or want is not None and not close(r[1].value, want):
            problems.append(f"Benefits payback {sk} {name}: workbook {r[1].value} vs recomputed {want}")
        for ph in range(4):
            check(f"Benefits stop {sk} {name} Phase {ph + 1}", r[2 + ph].value, Sb["stops"][name][ph])
        for j, key in enumerate([("5y", "high"), ("5y", "low"), ("10y", "high"), ("10y", "low")]):
            check(f"Benefits value {sk} {name} {key}", r[6 + j].value, Sb["npv"][(name, *key)])
# switching values and the gates that depend on build cost: one column per scenario, in the scenarios' order
cols = {sk: 1 + j for j, sk in enumerate(BM["costs"])}
for label, key in (("Share of benefits that can be lost", "switch_share_lost"),
                   ("Build cost overrun absorbed", "switch_build_overrun_pct"),
                   ("Run cost at which it stops paying", "switch_run_cost"),
                   ("Floor: below this", "floor"), ("Phase 1 switch trigger", "leak_switch"),
                   ("Phase 2 money gate", "claims_gate_pilot")):
    _, r = row_by_label(BS, label)
    for sk, j in cols.items():
        check(f"Benefits {label} {sk}", r[j].value, BM["scen"][sk][key])
for a in bc.model(V, {"low": LO, "high": HI})["scen"][next(iter(BM["costs"]))]["switch_rate"]:
    _, r = row_by_label(BS, f"{a}: the value at which it stops paying")
    for sk, j in cols.items():
        sv, got = BM["scen"][sk]["switch_rate"][a], r[j].value
        checks += 1
        if (sv is None and got != "survives at zero") or (sv is not None and not close(got, sv)):
            problems.append(f"Benefits switching {a} {sk}: workbook {got} vs recomputed {sv}")
for label, reach in [("Gate, every source", "every"), ("Gate, on the named fallback", "no_jv"),
                     ("Gate, without dealers' VIN-level evidence", "no_dealer")]:
    check(f"Benefits {label}", row_by_label(BS, label)[0], BM["gate"][reach])
check("Benefits gate on adverse ends", row_by_label(BS, "On our own adverse ends")[0], BM["adverse"]["gate"])
# the register's per-scenario gate rows carry the derived gates, rounded
for n, sk in enumerate(BM["costs"], start=1):
    for family, key, tol in (("gate_claims_recovered_eur_m", "claims_gate_pilot", 0.05),
                             ("gate_leak_switch_pct", "leak_switch", 0.005), ("gate_exit_floor_eur_m", "floor", 0.5)):
        rid = bc.scenario_gate_id(family, n)
        checks += 1
        if rid not in V or abs(V[rid] - BM["scen"][sk][key]) > tol:
            problems.append(f"{rid} {V.get(rid)} is not the derived {key} {BM['scen'][sk][key]:.3f}, rounded")
checks += 1
if abs(V["gate_benefits_eur_m"] - BM["gate"]["every"]) > 0.5:
    problems.append(f"gate_benefits_eur_m {V['gate_benefits_eur_m']} is not the derived gate "
                    f"{BM['gate']['every']:.2f}, rounded")
ref_b = BM["cases"]["reference class"]["b"]
reach_every = sums[0]
split = [("At risk (the headline)", total_e, total),
         ("Addressable: what the levers can reach", reach_every, None),
         ("Planned benefit, committed levers", BM["committed"]["every"],
          BM["committed"]["every"] + BM["rates"]["every"]["tail"]),
         ("The same at the reference class", ref_b * BM["committed"]["every"],
          ref_b * (BM["committed"]["every"] + BM["rates"]["every"]["tail"])),
         ("Upper bound beside it, never committed", BM["rates"]["every"]["targeting"],
          BM["rates"]["every"]["targeting"])]
for label, e, t in split:
    _, r = row_by_label(BS, label)
    check(f"Benefits split {label} expected", r[1].value, e)
    if t is not None:
        check(f"Benefits split {label} one in ten", r[2].value, t)
for label, e, t in split[1:4]:
    _, r = row_by_label(S, label)
    check(f"Summary benefits {label} expected", r[1].value, e)
    if t is not None:
        check(f"Summary benefits {label} one in ten", r[2].value, t)

# ---- Programme cost and Work list (X25) ----
# Checked against analysis/programme_cost.py's model, written apart from the builder's formulas.
PW = pc.work()
PM_ = pc.model(V, PW)
PC, WL = wb["Programme cost"], wb["Work list"]
for role, rr in PM_["rates"].items():
    _, row = row_by_label(PC, role)
    if row is None:
        continue
    for j, key in ((2, "central"), (3, "markets"), (4, "hub")):
        check(f"Programme cost {role} in-house {key}", row[j].value, rr[key])
    if rr["integrator"] is not None:
        check(f"Programme cost {role} integrator", row[5].value, rr["integrator"])
    for j, key in ((6, "save_central"), (7, "save_upper"), (8, "save_adverse"), (9, "seat")):
        check(f"Programme cost {role} {key}", row[j].value, rr[key])
wl_cols = {"b1": 7, "b2": 8, "b3_people_central": 9, "b3_tools_central": 10, "b3_people_upper": 11,
           "b3_tools_upper": 12, "b3_people_adverse": 13, "b3_tools_adverse": 14, "b2_consip": 15, "b2_offshore": 16,
           "b1_hub": 17, "b4": 18}
wl_rows = list(WL.iter_rows(min_row=2, max_row=len(PW) + 1))
checks += 1
if len(wl_rows) != len(PW) or any(float(r[3].value) != float(w["fte"]) or r[2].value != w["role"]
                                  for r, w in zip(wl_rows, PW)):
    problems.append("Work list sheet does not hold work_list.csv row for row")
for r, line in zip(wl_rows, PM_["lines"]):
    check(f"Work list {r[0].row} person-months", r[4].value, line["pm"])
    for key, j in wl_cols.items():
        check(f"Work list {r[0].row} {key}", r[j].value, line[key])
for label, key in (("1. In-house, no AI", "b1"), ("2. Buy and outsource", "b2"), ("3. In-house with AI, central", "b3"),
                   ("3. In-house with AI, upper", "b3_upper"), ("3. In-house with AI, adverse", "b3_adverse"),
                   ("4. Cheapest route per workstream", "b4"), ("2 at Consip", "b2_consip"), ("2 with the integrator", "b2_offshore"),
                   ("1 with the coders", "b1_hub")):
    _, row = row_by_label(PC, label)
    if row is None:
        continue
    b = PM_["base"][key]
    check(f"Programme cost {key} people", row[1].value, b["people"] + (b["tools"] if key == "b4" else 0))
    if key != "b4":
        check(f"Programme cost {key} tools", row[2].value, b["tools"])
    check(f"Programme cost {key} total", row[5].value, b["total"])
for ws_name, v in PM_["per_ws"].items():
    _, row = row_by_label(PC, ws_name)
    if row is None:
        continue
    for j, key in ((1, "b1"), (2, "b2"), (3, "b3"), (6, "b4")):
        check(f"Programme cost {ws_name[:4]} {key}", row[j].value, v[key])
    checks += 1
    if row[4].value != v["rule"]:
        problems.append(f"Programme cost {ws_name[:4]} rule: {row[4].value} vs {v['rule']}")
check("Programme cost overhead switching value", row_by_label(PC, "Overhead on in-house cost")[0],
      PM_["switch"]["overhead_pct"])
check("Programme cost day-rate switching value", row_by_label(PC, "One integrator day rate")[0],
      PM_["switch"]["day_rate_eur"])
check("Programme cost integrator days", row_by_label(PC, "Integrator days in base 2")[0], PM_["switch"]["integrator_days"])
seen_phase = [r for r in PC.iter_rows() if r[0].value in ("1. In-house, no AI", "2. Buy and outsource (rate card)",
                                                          "3. In-house with AI, central", "4. Cheapest route per workstream")
              and r[4].value is not None and r[5].value is None]
for r, key in zip(seen_phase, ("b1", "b2", "b3", "b4")):
    for p in range(4):
        check(f"Programme cost {key} Phase {p + 1}", r[1 + p].value, PM_["by_phase"][key][p])
checks += 1
if len(seen_phase) != 4:
    problems.append(f"Programme cost by-phase rows found: {len(seen_phase)}")

# ---- every formula cell has a stored value; no typed constant inputs in formulas ----
empty = sum(1 for ws in wb_f for r in ws.iter_rows() for c in r
            if isinstance(c.value, str) and c.value.startswith("=") and wb[ws.title][c.coordinate].value is None)
checks += 1
if empty:
    problems.append(f"{empty} formula cells without a stored value")
literal = set()
for ws in wb_f:
    for r in ws.iter_rows():
        for c in r:
            if isinstance(c.value, str) and c.value.startswith("="):
                for num in re.findall(r"(?<![A-Za-z_$\d.])(\d+(?:\.\d+)?)(?![\d_A-Za-z])", c.value):
                    literal.add(num)
print(f"{checks} checks, {len(problems)} problems")
for p in problems[:40]:
    print("  PROBLEM", p)
print("numeric literals found inside formulas:", sorted(literal, key=float))
print(f"headline: expected {total_e:,.1f}  one in ten {total:,.1f}  stress {L1 + L2 + L3(STRESS):,.1f}  "
      f"(leak3 expected {L3E:,.1f}, one in ten {L3(BASE):,.1f}; upper ends {L1 + L2 + sum_leak3(V, BASE):,.1f} "
      f"and {L1 + L2 + sum_leak3(V, STRESS):,.1f})")
sys.exit(1 if problems else 0)
