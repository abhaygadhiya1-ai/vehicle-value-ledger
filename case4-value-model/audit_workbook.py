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
    L1 = v["eu_revenue_eur_m"] * v["incentive_pct_revenue"] / 100 * (v["process_leak_pct"] + v["targeting_leak_pct"]) / 100
    L2 = v["eu_shipments"] * v["finance_penetration"] / 100 * v["upgrade_capture_uplift"] / 100 * v["margin_per_repeat_sale"] / 1e6
    thin = v["thin_share_of_book"] / 100
    curve1 = (v["curve_1y_p80_known"] / 2 / v["retained_1y_pooled"] * (1 - thin)
              + v["curve_1y_p80_unknown"] / 2 / v["retained_1y_pooled"] * thin)
    L3 = lambda lvl: v["buyback_payables_current_eur_m"] * (abs(v[lvl]) / 100 + curve1)  # noqa: E731
    return L1, L2, L3, curve1


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
L1, L2, L3, curve1 = model(V)
S = wb["Summary"]
base = {"Leak 1": L1, "Leak 2": L2, "Leak 3": L3("level_1y_p10_core")}
swap_ids = ["incentive_pct_revenue", "process_leak_pct", "targeting_leak_pct", "finance_penetration",
            "upgrade_capture_uplift", "margin_per_repeat_sale", "thin_share_of_book"]
for which, src in (("low", LO), ("high", HI)):
    v2 = dict(V)
    for k in swap_ids:
        v2[k] = src[k]
    a, b, c, _ = model(v2)
    base[f"Leak 1 {which}"], base[f"Leak 2 {which}"], base[f"Leak 3 {which}"] = a, b, c("level_1y_p10_core")
for leak in ("Leak 1", "Leak 2", "Leak 3"):
    _, r = row_by_label(S, leak)
    check(f"Summary {leak} base", r[2].value, base[leak])
    check(f"Summary {leak} low", r[1].value, base[f"{leak} low"])
    check(f"Summary {leak} high", r[3].value, base[f"{leak} high"])
total = L1 + L2 + L3("level_1y_p10_core")
_, r = row_by_label(S, "Total value at risk a year")
check("Summary total base", r[2].value, total)
check("Summary total low", r[1].value, base["Leak 1 low"] + base["Leak 2 low"] + base["Leak 3 low"])
check("Summary total high", r[3].value, base["Leak 1 high"] + base["Leak 2 high"] + base["Leak 3 high"])
_, r = row_by_label(S, "Total under the stress level shock")
check("Summary stress total", r[2].value, L1 + L2 + L3("level_1y_worst"))
for label, part in (("Disclosed exposure, measured shocks", L3("level_1y_p10_core")),
                    ("Measured timing, assumed conversion", L2), ("Assumed throughout", L1)):
    _, r = row_by_label(S, label)
    check(f"Summary split {label} EUR", r[1].value, part)
    share = r[2].value
    check(f"Summary split {label} share", share, part / total)
labels = {r["id"]: r["label"] for r in rows}
for k in swap_ids:
    _, r = row_by_label(S, labels[k])
    lo_v, hi_v = dict(V), dict(V)
    lo_v[k], hi_v[k] = LO[k], HI[k]
    a = model(lo_v); b = model(hi_v)
    tl = a[0] + a[1] + a[2]("level_1y_p10_core")
    th = b[0] + b[1] + b[2]("level_1y_p10_core")
    check(f"Sensitivity {k} low", r[2].value, tl)
    check(f"Sensitivity {k} high", r[3].value, th)
    check(f"Sensitivity {k} swing", r[4].value, abs(th - tl))

# ---- Leak 1 sheet ----
W1 = wb["Leak 1 - Incentives"]
spend = V["eu_revenue_eur_m"] * V["incentive_pct_revenue"] / 100
check("Leak1 spend", row_by_label(W1, "Incentive spend")[0], spend)
check("Leak1 process", row_by_label(W1, "    Claims paid twice")[0], spend * V["process_leak_pct"] / 100)
check("Leak1 targeting", row_by_label(W1, "    Incentives paid on sales")[0], spend * V["targeting_leak_pct"] / 100)
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
_, r = row_by_label(W2, "Equity covers the next deposit")
for j, col in enumerate(("D", "F", "H")):
    checks += 1
    want = first.get(col, "not within the term")
    if r[1 + j].value != want:
        problems.append(f"Leak2 window {col}: workbook {r[1 + j].value} vs recomputed {want}")
contracts = V["eu_shipments"] * V["finance_penetration"] / 100
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
    ("    Base: a bad year", cur * abs(V["level_1y_p10_core"]) / 100),
    ("    Wider: p10 across all 26", cur * abs(V["level_1y_p10"]) / 100),
    ("    Stress: the worst twelve-month", cur * abs(V["level_1y_worst"]) / 100),
    ("    Curve error on the part of the book", cur * V["curve_1y_p80_known"] / 2 / V["retained_1y_pooled"] * (1 - thin)),
    ("    Curve error on the thin slice", cur * V["curve_1y_p80_unknown"] / 2 / V["retained_1y_pooled"] * thin),
    ("Value at risk, leak 3 a year (base", L3("level_1y_p10_core")),
    ("Value at risk, leak 3 a year (stress", L3("level_1y_worst")),
    ("    Decrease in value on assets sold with a buy-back commitment, 2023", V["buyback_value_decrease_2023_eur_m"]),
    ("    Decrease in value on assets sold with a buy-back commitment, 2024", V["buyback_value_decrease_2024_eur_m"]),
    ("    Decrease in value on assets sold with a buy-back commitment, 2025", V["buyback_value_decrease_2025_eur_m"]),
    ("    Base: a bad three years", book * (abs(V["level_3y_p10_core"]) / 100 + curve3)),
    ("    Stress: the worst three-year", book * (abs(V["level_3y_worst"]) / 100 + curve3)),
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

aoi24 = V["eu_aoi_2024_eur_m"] * 1e6 / V["eu_shipments_2024"]
aoi25 = V["eu_aoi_eur_m"] * 1e6 / ship
check("Per car revenue per vehicle", row_by_label(PC, "Enlarged Europe net revenue per vehicle")[0],
      V["eu_revenue_eur_m"] * 1e6 / ship)
check("Per car result 2024", row_by_label(PC, "Operating result per vehicle, 2024")[0], aoi24)
check("Per car result 2025", row_by_label(PC, "Operating result per vehicle, 2025")[0], aoi25)
check("Per car swing", row_by_label(PC, "Swing between the two years")[0], aoi24 - aoi25)
for label, part in (("Leak 1 at risk per vehicle", L1), ("Leak 2 at risk per vehicle", L2),
                    ("Leak 3 at risk per vehicle", L3("level_1y_p10_core"))):
    check(f"Per car {label}", row_by_label(PC, label)[0], part * 1e6 / ship)
check("Per car total at risk", row_by_label(PC, "Total at risk per vehicle")[0], total * 1e6 / ship)
check("Per car worst year", row_by_label(PC, "In the worst year on record")[0],
      (L1 + L2 + L3("level_1y_worst")) * 1e6 / ship)
check("Per car leakage vs 2025 result", row_by_label(PC, "Leakage against the 2025 result")[0],
      -(total * 1e6 / ship) / aoi25)

cost = V["inv_people_eur_m"] + V["inv_platform_eur_m"] + V["inv_change_eur_m"]
check("Per car programme cost", row_by_label(PC, "Programme cost over 24 months")[0], cost)
check("Per car value at risk", row_by_label(PC, "Value at risk a year")[0], total)
check("Per car break-even share",
      row_by_label(PC, "Share of it the programme must capture")[0], cost / total)

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

# ---- a target never reaches a value-at-risk formula ----
# One check over the whole workbook, in the same style as the stored-value sweep below.
targets = {r["id"] for r in rows if r["tier"] == "TARGET"}
leaked = [f"{ws.title}!{c.coordinate} uses {n}"
          for ws in wb_f if ws.title not in ("Assumptions", "Provenance")
          for row in ws.iter_rows() for c in row
          if isinstance(c.value, str) and c.value.startswith("=")
          for n in targets if re.search(rf"\b{re.escape(n)}\b", c.value)]
checks += 1
if leaked:
    problems.append(f"a target the team chose reaches a formula: {leaked[:3]}")

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
print(f"headline: total {total:,.1f}  stress {L1 + L2 + L3('level_1y_worst'):,.1f}  leak3 {L3('level_1y_p10_core'):,.1f}")
sys.exit(1 if problems else 0)
