"""Build the value-at-risk workbook from `assumptions.csv`.

Every number in the model is a live formula pointing at a named cell on the Assumptions sheet.
No constant is typed into a formula, so a reader can change one input and watch the answer move,
and "nothing is invented" can be checked by inspection rather than taken on trust.

Each input carries a tier - MEASURED, SOURCED or ASSUMPTION - and the Summary sheet splits the
answer by tier, so the committee can see how much of the number is evidence and how much is
judgement. TARGET and SYNTHETIC rows are listed on the Assumptions sheet but never feed a formula.

openpyxl writes formulas without their results, so a viewer that does not recalculate - a Mac
preview, an email attachment, a cloud drive - would show empty cells. When LibreOffice is installed
the workbook is recalculated and saved once more, which stores every result beside its formula.

Usage: .venv/bin/python build_var_model.py
"""
import csv
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

HERE = Path(__file__).parent
CSV = HERE / "assumptions.csv"
OUT = HERE.parent / "Case4_Value_at_Risk.xlsx"
BUILD_REPORT = HERE / "data" / "unified" / "build_report.md"

def collection_size():
    """Rows and sources behind the MEASURED tier, read from the build report so it cannot go stale.

    This sentence carried a typed 4.3 million until 2026-09-17, which the audit had already
    retired (the duplicate UK adverts and the rejected French set took it to 3.9 million).
    """
    m = re.search(r"\*\*([\d,]+) rows\*\* from (\d+) sources", BUILD_REPORT.read_text())
    if not m:
        raise SystemExit(f"cannot read the row and source counts from {BUILD_REPORT}")
    return int(m.group(1).replace(",", "")), int(m.group(2))


TIER_FILL = {"MEASURED": "D6E9D6", "SOURCED": "DCE4F2", "ASSUMPTION": "FBE6CC",
             "TARGET": "EAE0F0", "SYNTHETIC": "E4E4E4"}
HEAD = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(bold=True, color="FFFFFF", size=11)
TITLE = Font(bold=True, size=14, color="1F3864")
BOLD = Font(bold=True)
NOTE = Font(italic=True, size=9, color="595959")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
EURM = '#,##0;[Red]-#,##0'
PCT1 = '0.0'
PCT2 = '0.0%'

# The whole model in one place. Each leak is an expression over defined names, in EUR millions.
# The sensitivity sheet re-emits these with a single name swapped for a literal, which is why
# they live here as strings rather than being typed into cells by hand.
# Leak 1's targeting line is the profit lost by giving every buyer the same incentive, derived in
# analysis/optimal_incentive_report.md (X5) as a share of revenue. It replaced an assumed share of spend.
# Its claims line takes the group's own claims-based incentive spend, the 20-F's sales-incentive provision over net
# revenues (worldwide, analysis/incentive_anchor_report.md, X14); it replaced an assumed share of revenue.
LEAK1_CLAIMS = "eu_revenue_eur_m * x14_incentive_claims_central/100 * process_leak_pct/100"
LEAK1_TARGETING = "eu_revenue_eur_m * x5_targeting_gain_central/100"
LEAK1 = f"({LEAK1_CLAIMS} + {LEAK1_TARGETING})"
# Leak 2 counts the contracts the group's finance arm wrote in Europe, a disclosed figure (X14); it
# replaced an assumed share of shipments.
LEAK2 = ("sfse_eu_nv_contracts_2025 * upgrade_capture_uplift/100 "
         "* margin_per_repeat_sale / 1000000")
# Leak 3 is a yearly figure like the other two. The part of the buy-back book that comes back within
# twelve months - disclosed as the current portion of the payables - meets at most a year of market
# movement, so it takes the one-year level shock and the one-year curve error; the rest is counted
# in the year it falls due. The level shock is a one-sided downside at p10. The curve spreads are
# p10-p90 bands, so half of one is the distance from the centre to p10: the same one-in-ten. Added,
# the two downsides are a year in which both happen at once, rarer than one in ten. The base level
# shock is the group's own book's one-in-ten-year fall, its markets weighted as it sells (X8); the
# stress is a Europe-wide bad year as deep as a core market's one-in-ten, which the book's nine years
# of history do not hold.
CURVE = ("(curve_1y_p80_known/2/retained_1y_pooled * (1 - thin_share_of_book/100) "
         "+ curve_1y_p80_unknown/2/retained_1y_pooled * thin_share_of_book/100)")
LEAK3_RISK = f"buyback_payables_current_eur_m * (ABS({{level}})/100 + {CURVE})"
# The headline in two measures (X18, analysis/headline_measures_report.md). One year in ten, the level and the curve
# take their joint p10, applied as its measured share of the sum above, so the thin share still moves it; the sum
# stays beside it as the upper end. Expected a year, the buy-back book counts both sides (the 20-F's contracts bring
# the cars back): on the book's own record the level and curve gained on average, and a gain is not a leak, so the
# line is floored at zero. The one-sided figure (X6's case) and the UK's long record sit beside it, in no total.
JOINT = {"base": "x18_joint_share_book", "stress": "x18_joint_share_stress"}
LEAK3_EXPECTED_RISK = "buyback_payables_current_eur_m * MAX(0, x18_exp_twosided_book)/100"
# Resale execution (X17): value the group can recover when the car comes back, an expected yearly loss. Days cut from
# the time to sale at the measured cost of a day in stock (analysis/time_in_stock_report.md), and a share of returns
# retailed in-house at Aramis's measured margin over the trade (analysis/recovery_levers_report.md). The daily cost is
# per EUR 10,000 of car, hence the division.
LEAK3_EXEC = ("buyback_payables_current_eur_m * (x17_days_cut * x17_day_cost_central/10000 "
              "+ x17_share_routed/100 * x17_channel_gain_after_costs/100)")
LEVELS = {"base": "level_1y_p10_book", "stress": "level_1y_p10_core"}
# The whole book over a three-year lease, shown on the leak 3 sheet for context. Not a yearly figure.
CURVE_3Y = ("(curve_p80_known/2/retained_3y_pooled * (1 - thin_share_of_book/100) "
            "+ curve_p80_unknown/2/retained_3y_pooled * thin_share_of_book/100)")
BOOK_3Y = f"buyback_payables_eur_m * (ABS({{level}})/100 + {CURVE_3Y})"

def leak3_sum(level="base"):
    """The level and the curve at their separate p10s, added, plus resale execution: the one-in-ten column's upper
    end (both at once)."""
    return f"({LEAK3_RISK.format(level=LEVELS[level])} + {LEAK3_EXEC})"


def leak3_risk(level="base"):
    """The level and the curve together, one year in ten: their joint p10 (X18)."""
    return f"({LEAK3_RISK.format(level=LEVELS[level])}) * {JOINT[level]}/100"


def leak3(level="base"):
    """Leak 3 one year in ten."""
    return f"({leak3_risk(level)} + {LEAK3_EXEC})"


def leak3_expected():
    """Leak 3 expected a year."""
    return f"({LEAK3_EXPECTED_RISK} + {LEAK3_EXEC})"


def total(level="base"):
    """The headline in a one-in-ten-year market (base) or the stress."""
    return f"{LEAK1} + {LEAK2} + {leak3(level)}"


def total_sum(level="base"):
    """The same with the level and the curve added at their separate p10s: the upper end."""
    return f"{LEAK1} + {LEAK2} + {leak3_sum(level)}"


def total_expected():
    """The headline expected a year."""
    return f"{LEAK1} + {LEAK2} + {leak3_expected()}"


def swap(expr, name, value):
    """Replace one defined name with a literal, for one-at-a-time sensitivity.

    Word boundaries matter here: names butt straight up against operators
    (`finance_penetration/100`), and one name can be a prefix of another
    (`level_3y_p10` inside `level_3y_p10_core`). An underscore counts as a word
    character, so \\b handles both.
    """
    return re.sub(rf"\b{re.escape(name)}\b", str(value), expr)


def style_header(ws, row, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill, cell.font = HEAD, HEAD_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")


def put(ws, row, label, formula=None, fmt=EURM, bold=False, note=None, indent=0):
    ws.cell(row=row, column=1, value=("    " * indent) + label).font = BOLD if bold else Font()
    if formula is not None:
        c = ws.cell(row=row, column=2, value=formula)
        c.number_format, c.font = fmt, BOLD if bold else Font()
    if note:
        ws.cell(row=row, column=3, value=note).font = NOTE
    return row + 1


def read_rows():
    return list(csv.DictReader(CSV.open()))


def sheet_assumptions(wb, rows):
    ws = wb.create_sheet("Assumptions")
    cols = ["id", "label", "value", "low", "high", "unit", "tier", "source", "url", "as_of",
            "caveat", "used_in"]
    ws.append([c.replace("_", " ") for c in cols])
    style_header(ws, 1, len(cols))
    named = {}
    for i, r in enumerate(rows, start=2):
        for j, c in enumerate(cols, start=1):
            v = r[c]
            if c in ("value", "low", "high") and v not in ("", None):
                v = float(v)
            cell = ws.cell(row=i, column=j, value=v)
            cell.border = BOX
            cell.alignment = Alignment(wrap_text=c in ("label", "source", "caveat"),
                                       vertical="top")
            if c == "tier" and r["tier"] in TIER_FILL:
                cell.fill = PatternFill("solid", fgColor=TIER_FILL[r["tier"]])
        if r["value"]:
            named[r["id"]] = f"Assumptions!$C${i}"
    for width, col in zip([26, 44, 12, 9, 9, 14, 13, 40, 44, 11, 52, 14], cols):
        ws.column_dimensions[get_column_letter(cols.index(col) + 1)].width = width
    ws.freeze_panes = "B2"
    for name, ref in named.items():
        wb.defined_names.add(DefinedName(name, attr_text=ref))
    return named


def sheet_leak1(wb):
    ws = wb.create_sheet("Leak 1 - Incentives")
    ws["A1"], ws["A1"].font = "Leak 1: the spend nobody can see", TITLE
    r = 3
    ws.cell(row=r, column=1, value=(
        "The claims line takes the group's own claims-based incentive spend: the sales-incentive "
        "provision in its 20-F (Note 21), worldwide, as a share of net revenue "
        "(analysis/incentive_anchor_report.md). No regional total is disclosed, and the share of "
        "claims paid wrongly is an assumption. The targeting line is derived from published studies and one "
        "assumption (analysis/optimal_incentive_report.md). Neither is a measurement of the group in Europe: "
        "that is the reason the ledger has to be built."
    )).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 46
    r += 2
    ws.cell(row=r, column=1, value="EUR millions a year, Enlarged Europe").font = BOLD
    r += 1
    r = put(ws, r, "Incentive claims (the group's own share of revenue, applied to Europe)",
            "=eu_revenue_eur_m * x14_incentive_claims_central/100",
            note="eu_revenue_eur_m x x14_incentive_claims_central (20-F Note 21, worldwide)")
    r = put(ws, r, "Claims paid twice, wrongly or too late", "=" + LEAK1_CLAIMS,
            indent=1, note="process_leak_pct")
    r = put(ws, r, "Profit lost by giving every buyer the same incentive", "=" + LEAK1_TARGETING,
            indent=1, note="x5_targeting_gain_central: what giving each income quartile its own incentive "
                           "earns, derived in X5")
    r = put(ws, r, "Value at risk, leak 1", "=" + LEAK1, bold=True)
    r += 1
    r = put(ws, r, "Of which a controls layer actually recovers",
            "=eu_revenue_eur_m * x14_incentive_claims_central/100 * process_leak_pct/100 "
            "* recoverable_share/100",
            note="leakage that exists is not leakage you can recover")
    r += 1
    ws.cell(row=r, column=1, value="Not sized here, on purpose").font = BOLD
    r += 1
    ws.cell(row=r, column=1, value=(
        "Spend above the best uniform level. The targeting line takes today's uniform incentive as the "
        "best uniform one, so it cannot say whether the group spends too much on average. Public "
        "data cannot either: the published margins and price sensitivities disagree. Only a "
        "randomised holdout on the incentive's level measures it.")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 46
    r += 1
    ws.cell(row=r, column=1, value=(
        "Pass-through leakage - money meant for the buyer that the dealer keeps - is real and "
        "measured in the literature (buyers receive 70-90% of a customer rebate but only 30-40% of "
        "a dealer discount, Busse et al. 2006, US data). It is not converted into euros here "
        "because that would need a second assumption about how the group's spend splits between "
        "the two kinds of programme. The ledger measures it per programme instead of assuming it."
    )).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 60
    ws.column_dimensions["A"].width = 58
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 60
    return ws


def sheet_leak2(wb, by_id):
    ws = wb.create_sheet("Leak 2 - Upgrade timing")
    ws["A1"], ws["A1"].font = "Leak 2: the moment nobody catches", TITLE
    ws["A3"] = ("The upgrade moment is when the car is worth more than the balance still owed on "
                "it. Both sides are held as a share of the list price, so no currency or exchange "
                "rate enters. The value curve is the measured UK retained-value curve from the 2018 "
                "adverts, before the shortage; the balance "
                "is a straight amortising contract.")
    ws["A3"].font, ws["A3"].alignment = NOTE, Alignment(wrap_text=True)
    ws.row_dimensions[3].height = 46

    ws["A5"], ws["A5"].font = "Measured value curve (share of list price)", BOLD
    ws["A6"] = "years"
    for j, y in enumerate(range(0, 6)):
        ws.cell(row=6, column=2 + j, value=y)
    ws["A7"] = "retained"
    ws.cell(row=7, column=2, value=100)
    for j, name in enumerate(["retained_1y_uk", "retained_2y_uk", "retained_3y_uk",
                              "retained_4y_uk", "retained_5y_uk"]):
        ws.cell(row=7, column=3 + j, value=f"={name}")
    gap = float(by_id["retained_3y_uk_2022"]["value"]) - float(by_id["retained_3y_uk"]["value"])
    ws["H7"] = ("<- analysis/value_retained_report.md (UK 2018 adverts; entry-trim caveat "
                f"applies; October 2022 ran {gap:.0f} points higher at three years)")
    ws["H7"].font = NOTE

    ws["A9"], ws["A9"].font = "Contract", BOLD
    ws["A10"], ws["B10"] = "deposit, % of list", "=loan_deposit_pct"
    ws["A11"], ws["B11"] = "term, months", "=loan_term_months"
    ws["A12"], ws["B12"] = "interest rate, % a year", "=loan_apr"
    ws["A13"], ws["B13"] = "amount financed, % of list", "=100 - loan_deposit_pct"
    ws["C13"] = "no discount assumed, so this is the conservative case"
    ws["C13"].font = NOTE

    ws["A15"] = ("The trigger is not simply positive equity. On a 48-month contract the balance "
                 "falls faster than the car does, so the customer is above water almost at once. "
                 "The moment that matters commercially is when the car's equity covers the deposit "
                 "on the next one, which is the line used below.")
    ws["A15"].font, ws["A15"].alignment = NOTE, Alignment(wrap_text=True)
    ws.row_dimensions[15].height = 32

    head = 17
    ws.cell(row=head, column=1, value="month")
    p10, worst = by_id["level_3y_p10_core"]["value"], by_id["level_3y_worst"]["value"]
    for j, t in enumerate([
            "balance owed",
            "car value, level as measured", "equity",
            f"car value, level {p10}% (p10)", f"equity at {p10}%",
            f"car value, level {worst}% (worst)", f"equity at {worst}%"]):
        ws.cell(row=head, column=2 + j, value=t)
    style_header(ws, head, 8)

    months = 61
    for m in range(months):
        r = head + 1 + m
        ws.cell(row=r, column=1, value=m)
        # Balance: an annuity payment on the financed amount, or zero once the term is over.
        ws.cell(row=r, column=2, value=(
            f"=IF(A{r}>=loan_term_months,0,"
            f"(100-loan_deposit_pct)*((1+loan_apr/1200)^loan_term_months-(1+loan_apr/1200)^A{r})"
            f"/((1+loan_apr/1200)^loan_term_months-1))"))
        # Value: linear interpolation between the two nearest anchors on the measured curve.
        # The lower anchor is clamped at year 4 so the upper one stays inside B7:G7.
        anchor = f"MIN(4,INT(A{r}/12))"
        ws.cell(row=r, column=3, value=(
            f"=INDEX($B$7:$G$7,{anchor}+1)+(A{r}/12-{anchor})"
            f"*(INDEX($B$7:$G$7,{anchor}+2)-INDEX($B$7:$G$7,{anchor}+1))"))
        ws.cell(row=r, column=4, value=f"=C{r}-B{r}")
        ws.cell(row=r, column=5, value=f"=C{r}*(1+level_3y_p10_core/100)")
        ws.cell(row=r, column=6, value=f"=E{r}-B{r}")
        ws.cell(row=r, column=7, value=f"=C{r}*(1+level_3y_worst/100)")
        ws.cell(row=r, column=8, value=f"=G{r}-B{r}")
        for c in range(2, 9):
            ws.cell(row=r, column=c).number_format = PCT1

    last = head + months
    r = last + 2
    ws.cell(row=r, column=1,
            value="Equity covers the next deposit from month, UK curve (searched from month 12: a 12 means by month 12)"
            ).font = BOLD
    # The value curve is only measured from one year old. Before that it is a straight line from
    # 100% of list, which puts equity equal to the deposit at month 0 by construction, so the
    # search starts at the first measured point rather than report an artefact.
    first = head + 1 + 12
    for j, col in enumerate(["D", "F", "H"]):
        ws.cell(row=r, column=2 + j, value=(
            f"=IFERROR(MATCH(TRUE,INDEX(${col}${first}:${col}${last}>=loan_deposit_pct,0),0)+11,"
            f"\"not within the term\")"))
    ws.cell(row=r + 1, column=2, value="level as measured")
    ws.cell(row=r + 1, column=3, value=f"level {p10}%")
    ws.cell(row=r + 1, column=4, value=f"level {worst}%")
    for c in (2, 3, 4):
        ws.cell(row=r + 1, column=c).font = NOTE
    # The months to quote (skeptic B11): measured on Dutch adverts with exact ages, the first year included, on this
    # sheet's contract and level shocks (analysis/upgrade_window_report.md).
    r += 2
    ws.cell(row=r, column=1, value=(
        "Measured with the first year (Dutch adverts, exact ages): equity covers the next deposit from month")).font = BOLD
    for j, name in enumerate(["window_nl_measured_m", "window_nl_p10_m", "window_nl_worst_m"]):
        ws.cell(row=r, column=2 + j, value=f"={name}")

    r += 2
    ws.cell(row=r, column=1, value=(
        "A fall in the market level pushes the upgrade window months later, and a rise pulls it "
        "forward. That shift is the measured part of this leak: it comes from the value curve and "
        "the level moves, not from judgement. Turning it into euros needs the three assumptions "
        "below, and those should be replaced by a randomised pilot rather than defended. The UK curve's "
        "window is searched from month 12 because UK adverts carry whole-year ages, so its first twelve "
        "months are a line drawn from the list price, which would put equity equal to the deposit at "
        "month 0; a 12 there means only 'by month 12'. The months to quote are the measured row: Dutch "
        "adverts with exact ages, the first year included, within model (analysis/upgrade_window_report.md).")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 62
    r += 2
    ws.cell(row=r, column=1, value="EUR millions a year").font = BOLD
    r += 1
    r = put(ws, r, "Contracts financed or leased through the group",
            "=sfse_eu_nv_contracts_2025", fmt='#,##0',
            note="sfse_eu_nv_contracts_2025: SFSE's new-car contracts in Europe, 2025 (Leasys fleet leases excluded)")
    r = put(ws, r, "Extra customers retained by contacting them at the right moment",
            "=sfse_eu_nv_contracts_2025 * upgrade_capture_uplift/100", fmt='#,##0',
            indent=1, note="upgrade_capture_uplift")
    r = put(ws, r, "Value at risk, leak 2", "=" + LEAK2, bold=True,
            note="x margin_per_repeat_sale")
    ws.column_dimensions["A"].width = 52
    for c in "BCDEFGH":
        ws.column_dimensions[c].width = 17
    return ws


def sheet_leak3(wb, by_id):
    v = {k: by_id[k]["value"] for k in ("level_1y_p10_book", "level_1y_p10_core", "level_1y_p10",
                                        "level_1y_worst", "level_3y_p10_book", "level_3y_p10_core",
                                        "level_3y_worst", "x8_leak3_base_book_eur",
                                        "x8_leak3_base_book_nofr_eur", "level_1y_p10_uk_long",
                                        "x9_group_bev_share_2024", "x9_pl_ev_slump_gap",
                                        "curve_1y_p80_known", "curve_1y_p80_unknown",
                                        "retained_1y_pooled", "pooling_gain_100",
                                        "pooling_gain_250", "buyback_payables_eur_m")}
    ws = wb.create_sheet("Leak 3 - Residual value")
    ws["A1"], ws["A1"].font = "Leak 3: the value nobody recovers", TITLE
    ws["A3"] = ("This is the leak the evidence actually reaches, and it is a yearly figure like the "
                "other two, in two measures: expected a year, and one year in ten (X18). The exposure is "
                "the part of the group's disclosed buy-back book that comes back within twelve months; "
                "the shocks are measured, not assumed.")
    ws["A3"].font, ws["A3"].alignment = NOTE, Alignment(wrap_text=True)
    ws.row_dimensions[3].height = 32

    r = 5
    r = put(ws, r, "Payables for buy-back agreements, the whole book", "=buyback_payables_eur_m",
            note="Stellantis 20-F FY2025, Note 24")
    r = put(ws, r, "Exposure a year: the part due within one year", "=buyback_payables_current_eur_m",
            bold=True, note="Note 24, current column; the rest is counted in the year it falls due")
    r += 1
    ws.cell(row=r, column=1, value="Market level over the next twelve months").font = BOLD
    r += 1
    r = put(ws, r, f"Base: the group's book, spread across its markets (p10, {v['level_1y_p10_book']}%)",
            "=buyback_payables_current_eur_m * ABS(level_1y_p10_book)/100", indent=1,
            note=f"France on the euro-area index; France's own index gives {v['x8_leak3_base_book_eur']}m, "
                 f"without France {v['x8_leak3_base_book_nofr_eur']}m. A floor: the index understates what a "
                 "lessor meets (merger_diversification_report.md)")
    r = put(ws, r, f"Stress: the whole book in a core market's bad year (p10, {v['level_1y_p10_core']}%)",
            "=buyback_payables_current_eur_m * ABS(level_1y_p10_core)/100", indent=1,
            note=f"a Europe-wide bad year the book's short history lacks; the UK market fell "
                 f"{abs(float(v['level_1y_p10_uk_long']))}% one year in ten over 1988-2026 (ONS)")
    r = put(ws, r, f"Reference, in no total: p10 across all 26 EU markets, as if the book sat in one "
                   f"({v['level_1y_p10']}%)",
            "=buyback_payables_current_eur_m * ABS(level_1y_p10)/100", indent=1)
    r = put(ws, r, f"Reference, in no total: the worst twelve-month move in any market ({v['level_1y_worst']}%)",
            "=buyback_payables_current_eur_m * ABS(level_1y_worst)/100", indent=1)
    r = put(ws, r, f"Reference, in no total: the battery-EV slice in an EV-only slump like Poland's 2022-23 "
                   f"({v['x9_group_bev_share_2024']}% of the book at {v['x9_pl_ev_slump_gap']} points)",
            "=buyback_payables_current_eur_m * x9_group_bev_share_2024/100 * ABS(x9_pl_ev_slump_gap)/100", indent=1,
            note="X9: the group's 2024 registrations mix as a proxy for the book; one European slump, not a "
                 "one-in-ten year; on top of the market's own fall")
    r += 1
    ws.cell(row=r, column=1,
            value="The car itself over one year - what a value model can fix").font = BOLD
    r += 1
    r = put(ws, r, "Curve error on the part of the book with its own history",
            "=buyback_payables_current_eur_m * curve_1y_p80_known/2/retained_1y_pooled "
            "* (1 - thin_share_of_book/100)", indent=1,
            note=f"half of a {v['curve_1y_p80_known']}-point p10-p90 spread, on "
                 f"{v['retained_1y_pooled']} retained: centre to p10")
    r = put(ws, r, "Curve error on little-history cars (new brands, new markets, electrified lines)",
            "=buyback_payables_current_eur_m * curve_1y_p80_unknown/2/retained_1y_pooled "
            "* thin_share_of_book/100", indent=1,
            note=f"half of a {v['curve_1y_p80_unknown']}-point 80% interval; thin_share_of_book is "
                 "the one assumption here")
    r += 1
    ws.cell(row=r, column=1,
            value="The sale itself over one year - what the group can recover (X17)").font = BOLD
    r += 1
    r = put(ws, r, "Days cut from the time to sale, at the measured cost of a day in stock",
            "=buyback_payables_current_eur_m * x17_days_cut * x17_day_cost_central/10000", indent=1,
            note="x17_days_cut days (an assumption, anchored to DAT, INDICATA and Auto Trader) at "
                 "x17_day_cost_central per EUR 10,000 a day: ageing at fixed mileage plus financing "
                 "(time_in_stock_report.md)")
    r = put(ws, r, "A share of returns retailed in-house instead of sold to the trade",
            "=buyback_payables_current_eur_m * x17_share_routed/100 * x17_channel_gain_after_costs/100",
            indent=1, note="x17_share_routed of returns at Aramis's EBITDA per retail car as a share of its price; "
                           "before operating costs the gain is x17_channel_gain_before_opex (recovery_levers_report.md)")
    r = put(ws, r, "Priced, not recovered: the level at its p10 (base)",
            "=buyback_payables_current_eur_m * ABS(level_1y_p10_book)/100",
            note="no model forecasts it (X7): priced into each contract and re-marked (X6)")
    r = put(ws, r, "Recoverable: the car and its sale (the curve at its p10, plus resale execution)",
            f"=buyback_payables_current_eur_m * {CURVE} + {LEAK3_EXEC}",
            note="the curve errors a value model cuts, plus resale execution; with the line above, "
                 "the level and the curve at their separate p10s")
    r += 1
    ws.cell(row=r, column=1, value="Leak 3 in two measures (X18)").font = BOLD
    r += 1
    r = put(ws, r, "Level and curve, expected a year, both sides counted",
            "=" + LEAK3_EXPECTED_RISK, indent=1,
            note="the 20-F's contracts bring the cars back (stellantis_buyback_forms), so gains count: on the "
                 "book's own record a residual at no change gained on average (x18_exp_twosided_book); a gain "
                 "is not a leak, so zero (headline_measures_report.md)")
    r = put(ws, r, "Reference, in no total: the same on the UK's 1988-2026 record",
            "=buyback_payables_current_eur_m * x18_exp_twosided_uk_long/100", indent=1,
            note="UK data, several cycles: a residual at no change lost a fraction of a percent a year")
    r = put(ws, r, "Upper end, in no total: only losses counted, per contract",
            "=buyback_payables_current_eur_m * x18_exp_onesided_book/100", indent=1,
            note="as if every buy-back were a customer's put struck at the residual (X6's case); where a put "
                 "caps the group's upside, the truth lies between zero and this")
    r = put(ws, r, "Value at risk, leak 3, expected a year", "=" + leak3_expected(), bold=True,
            note="the level and curve line above plus resale execution")
    r = put(ws, r, "Level and curve together, one year in ten (base)", "=" + leak3_risk("base"), indent=1,
            note="their joint p10, x18_joint_share_book of the sum of their separate p10s: the two are "
                 "independent, and in Latvia the curve moved against the level (x18_lv_curve_level_corr_12m)")
    r = put(ws, r, "Value at risk, leak 3, one year in ten (base level shock)", "=" + leak3("base"), bold=True,
            note="plus resale execution, at its expected value")
    r = put(ws, r, "Value at risk, leak 3, one year in ten (stress level shock)", "=" + leak3("stress"),
            note="the joint p10 is x18_joint_share_stress of the sum under the stress")
    r = put(ws, r, "Upper end, in no total: the level and the curve at their p10s at once (base)",
            "=" + leak3_sum("base"), indent=1, note="both going wrong together: a year rarer than one in ten")
    r = put(ws, r, "Upper end, in no total: the same under the stress", "=" + leak3_sum("stress"), indent=1)
    r += 1
    ws.cell(row=r, column=1, value="What the group books on these cars: scheduled depreciation, not a loss").font = BOLD
    r += 1
    for year in (2023, 2024, 2025):
        r = put(ws, r, f"Decrease in value on assets sold with a buy-back commitment, {year}",
                f"=buyback_value_decrease_{year}_eur_m", indent=1,
                note=("contracts of 12 months or less only" if year == 2025 else None))
    ws.cell(row=r, column=1, value=(
        "Each car's cost less its estimated residual, depreciated over the contract (20-F FY2025 "
        "accounting policy): an expected cost, not a loss against the residual, so it cannot check the "
        "rows above. As a share of year-end buy-back assets it is about a year's ordinary depreciation "
        "(level_charge_report.md). The group discloses no gains or losses at disposal for this book; "
        "the ledger would record them car by car.")
    ).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 46
    r += 2
    ws.cell(row=r, column=1, value="For context: the whole book over a three-year lease "
                                   "(not a yearly figure)").font = BOLD
    r += 1
    r = put(ws, r, f"Base: the group's book over 36 months, spread across its markets "
                   f"(p10, {v['level_3y_p10_book']}%)",
            "=" + BOOK_3Y.format(level="level_3y_p10_book"), indent=1,
            note=f"level plus curve over 36 months, on all {float(v['buyback_payables_eur_m']):,.0f}m")
    r = put(ws, r, f"Stress: the whole book in a core market's bad three years (p10, {v['level_3y_p10_core']}%)",
            "=" + BOOK_3Y.format(level="level_3y_p10_core"), indent=1)
    r = put(ws, r, f"Reference, in no total: the worst three-year move in any market ({v['level_3y_worst']}%)",
            "=" + BOOK_3Y.format(level="level_3y_worst"), indent=1)
    r += 1
    ws.cell(row=r, column=1, value="What the programme actually buys").font = BOLD
    r += 1
    r = put(ws, r, "Resale execution: days cut and in-house retail (above), a year",
            "=" + LEAK3_EXEC, indent=1, note="costs measured, reach assumed; the pilot measures both on the ledger")
    r = put(ws, r, "Pooling the group's markets, on little-history cars only, a year",
            "=buyback_payables_current_eur_m * curve_1y_p80_unknown/2/retained_1y_pooled "
            "* thin_share_of_book/100 * pooling_gain_100/100", indent=1,
            note=f"lodo_report.md: {v['pooling_gain_100']}% error cut at 100 local cars, "
                 f"{v['pooling_gain_250']}% by 250")
    r = put(ws, r, "Re-marking monthly instead of quarterly",
            "=buyback_payables_eur_m * (ABS(level_3m_p5)-ABS(level_1m_p5))/100", indent=1,
            note="exposure carried unseen between reviews on the whole book, not a loss avoided")
    r += 1
    ws.cell(row=r, column=1, value=(
        "The level shock is not something the programme removes. No model forecasts the market "
        "level; the ledger's job there is to price it into the decision and re-mark it often. What "
        "the programme does remove is a share of the curve error, exactly where the book has little history, "
        "and the value lost in the sale itself: days a returned car waits and cars sold to the trade "
        "that the group's own retail would sell for more (X17).")
    ).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 60
    ws.column_dimensions["A"].width = 66
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 62
    return ws


def sheet_per_car(wb, pc):
    """Everything the deliverables quote per car, derived rather than typed.

    Four blocks: the lifetime profit and loss for the worked example car, the group's own result
    per vehicle beside the leakage per vehicle, what share of the leakage the programme has to
    capture to pay for itself, and why a per-car model error and a market-level move behave
    differently as the book grows. Nothing here feeds the Summary; it divides it.
    """
    ws = wb.create_sheet("Per car")
    ws["A1"], ws["A1"].font = "One car, and the book divided by it", TITLE

    r = 3
    ws.cell(row=r, column=1, value="Lifetime profit and loss, euros for one car").font = BOLD
    r += 1
    ws.cell(row=r, column=1, value=(
        "The worked example is a Vauxhall Corsa, entry trim, on a 48-month contract. Every line "
        "below is an ASSUMPTION with a stated basis and a range on the Assumptions sheet, except "
        "the list price and the two residual downsides, which are measured. A contribution "
        "figure, not an operating result."))
    ws.cell(row=r, column=1).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    r += 2

    r = put(ws, r, "List price when new", "=new_car_price_eur", note="MEASURED - one_car_report.md")
    first = r
    r = put(ws, r, "Sale margin", "=new_car_price_eur * pl_sale_margin_pct_list/100",
            note="share of list; bracketed by the group's own gross margin", indent=1)
    r = put(ws, r, "less incentives", "=-new_car_price_eur * pl_incentive_pct_list/100",
            note="ASSUMPTION - a share of list (pl_incentive_pct_list); leak 1 uses the 20-F's claims ratio instead", indent=1)
    r = put(ws, r, "plus finance income", "=pl_finance_income_eur",
            note="net of rate support, an internal transfer", indent=1)
    r = put(ws, r, "less credit losses", "=pl_credit_loss_eur",
            note="a European captive's published cost of risk", indent=1)
    r = put(ws, r, "plus service and parts margin", "=pl_service_parts_eur", indent=1)
    r = put(ws, r, "less warranty cost", "=-new_car_price_eur * pl_warranty_pct_list/100",
            note="share of list; bracketed by published accrual rates", indent=1)
    r = put(ws, r, "Residual outcome, central case", None,
            note="realised resale equals the contractual residual, so nothing here", indent=1)
    r = put(ws, r, "less reconditioning, logistics and holding", "=pl_recon_logistics_eur", indent=1)
    r = put(ws, r, "plus remarketing margin", "=pl_remarketing_margin_eur", indent=1)
    last = r - 1
    central = r
    r = put(ws, r, "Lifetime value per car", f"=SUM(B{first}:B{last})", bold=True)
    r += 1
    bad = r
    r = put(ws, r, "Residual downside - market level, p10 in the core markets",
            "=-new_car_price_eur * retained_4y_uk/100 * ABS(level_3y_p10_core)/100",
            note="MEASURED - the residual set at signing, times a bad three years", indent=1)
    r = put(ws, r, "Residual downside - curve error",
            "=-new_car_price_eur * curve_p80_known/100",
            note="MEASURED - points of list price", indent=1)
    r = put(ws, r, "Lifetime value in a bad market", f"=B{central} + SUM(B{bad}:B{bad + 1})",
            bold=True)
    r += 2

    ws.cell(row=r, column=1, value="Pricing the market level on one contract (X6), euros").font = BOLD
    r += 1
    ws.cell(row=r, column=1, value=(
        "A group-typical car on a 48-month bank lease, residual right on average, core markets. Not in the "
        "headline: leak 3 is a one-in-ten year on the buy-back book, this is the price of one lease's level "
        "risk. Source: analysis/level_charge_report.md.")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 32
    r += 1
    r = put(ws, r, "Level charge: expected loss per 48-month contract", "=x6_loss_contract_group_48m",
            note="MEASURED - residual x the expected shortfall", indent=1)
    r = put(ws, r, "Level charge per month, set aside at the ECB rate", "=x6_charge_month_group_48m",
            "#,##0.00", note="MEASURED", indent=1)
    r = put(ws, r, "Capital cost of holding it (CRR Article 134(7))", "=x6_capital_contract_group_48m",
            note="MEASURED - 8% + 2.5% of residual/t, at a 10% cost of equity net of the ECB rate", indent=1)
    r = put(ws, r, "Price to hold the level risk per contract", "=x6_price_contract_group_48m", bold=True,
            note="MEASURED - the figure to set beside an insurer's quote")
    r = put(ws, r, "Average loss in the worst tenth of windows", "=x6_worst_tenth_group_48m",
            note="MEASURED - what a bad decile costs one contract; capital, not the charge, covers it", indent=1)
    r = put(ws, r, "Charge with the level below its 3-year average, % of residual", "=x6_charge_cold_48m",
            "0.00", note="MEASURED - declines persisted: raise the charge when the level falls", indent=1)
    r = put(ws, r, "Charge in the middle tercile, % of residual", "=x6_charge_middle_48m", "0.00",
            note="MEASURED - never cut the charge because the level runs hot", indent=1)
    r = put(ws, r, "Share of losses a charge set from past data covered", "=x6_oos_coverage_48m", "0.00",
            note="MEASURED - out-of-sample back-test: a flat charge alone falls short", indent=1)
    r = put(ws, r, "Expected level loss on a battery-EV contract, if EV risk runs as on the US record",
            "=x6_loss_contract_group_48m * x9_us_ratio_48m_median", indent=1,
            note="US DATA (X9): battery EVs' 48-month expected shortfall against the market's at the same strike "
                 "(x9_us_ratio_48m_median; its 90% range in the register); Europe's evidence is one slump")
    r += 2

    ws.cell(row=r, column=1, value="The book divided by the cars in it, euros a vehicle").font = BOLD
    r += 2
    r = put(ws, r, "Enlarged Europe net revenue per vehicle, 2025",
            "=eu_revenue_eur_m*1000000/eu_shipments")
    y24 = r
    r = put(ws, r, "Operating result per vehicle, 2024",
            "=eu_aoi_2024_eur_m*1000000/eu_shipments_2024")
    y25 = r
    r = put(ws, r, "Operating result per vehicle, 2025",
            "=eu_aoi_eur_m*1000000/eu_shipments")
    r = put(ws, r, "Swing between the two years", f"=B{y24}-B{y25}",
            note="what one bad year cost, per vehicle")
    r += 1
    for label, expr in (("Leak 1 at risk per vehicle", LEAK1),
                        ("Leak 2 at risk per vehicle", LEAK2),
                        ("Leak 3 at risk per vehicle, expected a year", leak3_expected()),
                        ("Leak 3 at risk per vehicle, one year in ten", leak3("base"))):
        r = put(ws, r, label, f"=({expr})*1000000/eu_shipments", indent=1)
    tot = r
    r = put(ws, r, "Total at risk per vehicle, expected a year", f"=({total_expected()})*1000000/eu_shipments",
            bold=True, note="each leak spread over every car shipped; the leaks cover different cars (below)")
    r = put(ws, r, "Total at risk per vehicle, one year in ten", f"=({total('base')})*1000000/eu_shipments",
            bold=True, note="leak 3's level and curve at their joint one-in-ten (X18)")
    r = put(ws, r, "Under the stress level shock", f"=({total('stress')})*1000000/eu_shipments",
            note="the whole book in a core market's bad year")
    r = put(ws, r, "Leakage against the 2025 result per vehicle, expected a year", f"=-B{tot}/B{y25}",
            "0.0", note="the expected yearly leakage is this many times the loss the group reported per vehicle")
    r = put(ws, r, "Leak 2 at risk per financed contract", f"=({LEAK2})*1000000/sfse_eu_nv_contracts_2025",
            note="the cars leak 2 is about: the contracts SFSE wrote in Europe (sfse_eu_nv_contracts_2025)")
    r += 1
    ws.cell(row=r, column=1, value=(
        "Which cars each leak covers (X14, skeptic B6). Leak 1: every car sold to a dealer with an "
        "incentive programme, in every channel. Leak 2: the contracts the group's finance arm writes, "
        "private and business, in joint ventures with Santander CF and BNP Paribas PF; Leasys's fleet "
        "leases are left out. Leak 3: cars sold with a repurchase commitment and due back within a year. "
        "The 20-F names no buyer except the group's own leasing and rental joint ventures (Leasys, and the "
        "Santander and BNP ventures, Note 29): part of their lease residuals comes back to the group this way. "
        "Most of the book is due within a year, the term of a rental fleet, but its mix is not published. "
        "No count of buy-back cars is disclosed, so leak 3 has no per-car divisor of its own.")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 92
    r += 2

    ws.cell(row=r, column=1, value="What the programme has to capture to pay for itself").font = BOLD
    r += 2
    var = r
    r = put(ws, r, "Value at risk a year, expected, EUR m", f"={total_expected()}",
            note="a programme pays for itself out of the yearly expected cost, not out of a bad year (X18)")
    for sk, slabel in X25_SCENARIOS:
        r = put(ws, r, f"Programme cost over 24 months, {slabel}, EUR m", f"='Programme cost'!$F${pc['total'][sk]}")
        r = put(ws, r, f"Share of it the programme must capture to break even, {slabel}", f"=B{r - 1}/B{var}", "0.0%")
    ws.cell(row=r, column=1, value=(
        "Four build scenarios from the Programme cost sheet (X25), none chosen. Against what is at risk, not what the "
        "programme gets back: the Benefits sheet sizes that lever by lever, with payback for each scenario and "
        "switching values (X21).")).font = NOTE
    r += 1
    r += 2

    ws.cell(row=r, column=1, value=(
        "Why a better model cannot shrink the book's risk")).font = BOLD
    r += 1
    ws.cell(row=r, column=1, value=(
        "Per-car errors are roughly independent, so they average away as one over the square root "
        "of the number of cars. A level move is common to every car and does not average away at "
        "all."))
    ws.cell(row=r, column=1).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    r += 2
    head = r
    for j, t in enumerate(["cars in the book", "average per-car model error, %",
                           "market level move over 3 years, points of list"]):
        ws.cell(row=head, column=1 + j, value=t)
    style_header(ws, head, 3)
    r += 1
    for n in (1, 10, 100, 1000, 10000):
        ws.cell(row=r, column=1, value=n)
        ws.cell(row=r, column=2, value=f"=engine_err_typical/SQRT(A{r})").number_format = "0.00"
        ws.cell(row=r, column=3, value="=level_points").number_format = PCT1
        r += 1

    ws.column_dimensions["A"].width = 58
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 60
    return ws


L2 = "'Leak 2 - Upgrade timing'"
L2_BAL, L2_VAL = f"{L2}!$B$18:$B$78", f"{L2}!$C$18:$C$78"   # months 0-60, share of list (sheet_leak2)
# The finance arm's margin a year per euro outstanding, after credit losses (SFSE 2025, IFRS 8): banking income less
# the cost of risk, over the average outstanding the cost of risk and its share imply.
FIN_RATE = ("(sfse_pnb_ifrs8_2025_eur_m - sfse_cor_ifrs8_2025_eur_m)"
            "/(sfse_cor_ifrs8_2025_eur_m/(sfse_cor_pct_outstanding_2025/100))")
# The discount's resale cost on the sample car, as the Prior discounting sheet computes it (low: our measurement;
# high: the published pass-through).
RESID_4Y = "new_car_price_eur * retained_4y_uk/100"
GIVEN = "new_car_price_eur * pl_incentive_pct_list/100"
SHARE_LO = "(1 - (1 - pl_incentive_pct_list/100)^dpt_passthrough)"
SHARE_HI = "((hk_passthrough_36m + hk_passthrough_now)/100 * pl_incentive_pct_list/10)"
LIFETIME = ("new_car_price_eur*pl_sale_margin_pct_list/100 - new_car_price_eur*pl_incentive_pct_list/100 "
            "+ pl_finance_income_eur + pl_credit_loss_eur + pl_service_parts_eur "
            "- new_car_price_eur*pl_warranty_pct_list/100 + pl_recon_logistics_eur + pl_remarketing_margin_eur")
HOLDING = "(crr_total_capital_ratio + crd_conservation_buffer)/100 * (eba_bank_coe - ecb_deposit_rate)"


def sheet_internal(wb, rows):
    """X19: the internal prices that put one business's cost into another's decision, one worked trade-off, and the
    operating metric. Transfers inside the group, so no headline moves."""
    ws = wb.create_sheet("Internal prices")
    ws["A1"], ws["A1"].font = "Internal prices: from seeing to deciding (X19)", TITLE
    ws["A2"] = ("A ledger that shows lifetime cost changes no decision made by a business paid on its own P&L. These "
                "prices put each business's cost into the others' decisions, at the moment of sale. They are "
                "transfers inside the group, so no value-at-risk figure moves. The sample car is the Per car sheet's.")
    ws["A2"].font, ws["A2"].alignment = NOTE, Alignment(wrap_text=True)
    ws.row_dimensions[2].height = 32
    row_of = {r["id"]: i for i, r in enumerate(rows, start=2)}
    k_of = {"B": f"Assumptions!$D${row_of['x19_pull_forward_months']}", "C": "x19_pull_forward_months",
            "D": f"Assumptions!$E${row_of['x19_pull_forward_months']}"}

    r = 4
    ws.cell(row=r, column=1, value="1. The discount's resale cost, charged to the business that gives it").font = BOLD
    r += 1
    for j, t in enumerate(["", "low (measured)", "high (published)"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 3)
    r += 1
    for label, lo, hi, fmt in [
            ("Resale value lost per euro of incentive, EUR", f"{RESID_4Y}*{SHARE_LO}/({GIVEN})",
             f"{RESID_4Y}*{SHARE_HI}/({GIVEN})", "0.00"),
            ("On the sample car's incentive, EUR per car", f"{RESID_4Y}*{SHARE_LO}", f"{RESID_4Y}*{SHARE_HI}", EURM),
            ("What one more euro of discount costs the group, EUR", f"-(1 + {RESID_4Y}*{SHARE_LO}/({GIVEN}))",
             f"-(1 + {RESID_4Y}*{SHARE_HI}/({GIVEN}))", "0.00")]:
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value="=" + lo).number_format = fmt
        ws.cell(row=r, column=3, value="=" + hi).number_format = fmt
        r += 1
    ws.cell(row=r, column=1, value=(
        "Charged at sale to the sales side, on cars the group will take back (the buy-back book and contracts where it "
        "carries the residual); on the rest the cost falls on the buyer, and through the brand's used prices on later "
        "residuals (unmeasured). Why it works: paid on a margin that includes this cost, the sales side's own best "
        "discount is the group's (weinberg_margin_commission). It extends a price that exists: the group already pays "
        "subvention to its leasing programmes and says a residual fall raises it (stellantis_subvention_residual). "
        "Subvention is already inside the incentive provision (stellantis_subvention_incentive), so charge the resale "
        "cost on the price the buyer pays, never twice. A range until the pilot calibrates it: the low end is an upper "
        "bound on our own data.")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 88
    r += 2

    ws.cell(row=r, column=1, value="2. The market level, priced by book").font = BOLD
    r += 1
    r = put(ws, r, "Customer-option contract, 48 months: price to hold, % of residual", "=x6_price_share_group_48m",
            "0.00", note="X6: one-sided expected loss plus CRR 134(7) capital; bank leases and the "
                                            "joint ventures' residuals that come back through repurchase agreements")
    r = put(ws, r, "    on the sample car's 48-month residual, EUR", f"={RESID_4Y} * x6_price_share_group_48m/100")
    r = put(ws, r, "Buy-back contract, a year or less: expected level cost, both sides counted, % of residual",
            "=MAX(0, x19_core_all_two_12m)", "0.00",
            note="the 20-F's contracts bring the cars back: on average a gain (x19_core_all_two_12m), so zero")
    r = put(ws, r, "    plus when the level starts in its cold third, % of residual", "=x19_core_cold_premium_12m", "0.00",
            note="the core markets; the UK's long record agrees (x19_uk_cold_premium_12m). Never cut it when hot (X6)")
    r = put(ws, r, "    plus the cost of holding the tail, % of residual a year", "=" + HOLDING, "0.00",
            note="X6's capital rule, as if a bank held it: a residual of a year or less weighs 100%, 8% plus the 2.5% "
                 "buffer, at banks' cost of equity net of the ECB rate. A convention: the book sits outside CRR")
    r = put(ws, r, "    the holding cost on the buy-back book due within a year, EUR m",
            f"=buyback_payables_current_eur_m * {HOLDING}/100")
    r = put(ws, r, "    the cold premium on the same book, EUR m, in a year that starts cold",
            "=buyback_payables_current_eur_m * x19_core_cold_premium_12m/100")
    r = put(ws, r, "The pricer's override band, cars 2-4 years, %", "=x13_tied_cap_young", "0.0",
            note="X13: tied to the engine's calibrated band, ±5% on average")
    r = put(ws, r, "    cars 12 years and older, %", "=x13_tied_cap_old", "0.0")
    r += 1

    ws.cell(row=r, column=1, value="3. One worked trade-off: pulling an upgrade forward (per customer, sample car)").font = BOLD
    r += 1
    for j, t in enumerate(["", "months at their low", "base", "months at their high"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 4)
    r += 1
    first = r
    for label, expr, fmt in [
            ("Months pulled forward", "{k}", "0"),
            ("Old contract's balance at the switch, EUR",
             f"INDEX({L2_BAL},loan_term_months-{{k}}+1)*new_car_price_eur/100", EURM),
            ("Car value at the switch, EUR", f"INDEX({L2_VAL},loan_term_months-{{k}}+1)*new_car_price_eur/100", EURM),
            ("Customer's equity at the switch less the next deposit, EUR",
             f"(INDEX({L2_VAL},loan_term_months-{{k}}+1)-INDEX({L2_BAL},loan_term_months-{{k}}+1)-loan_deposit_pct)"
             f"*new_car_price_eur/100", EURM),
            ("A younger car: value at the switch less at the contract's end, EUR",
             f"(INDEX({L2_VAL},loan_term_months-{{k}}+1)-INDEX({L2_VAL},loan_term_months+1))*new_car_price_eur/100",
             EURM),
            ("Finance arm's margin a year per euro outstanding, after credit losses", FIN_RATE, "0.00%"),
            ("Finance arm, taker refinances with the group: margin on the new balance less the old, EUR",
             f"{FIN_RATE}*(AVERAGE(INDEX({L2_BAL},1):INDEX({L2_BAL},{{k}}))"
             f"-AVERAGE(INDEX({L2_BAL},loan_term_months-{{k}}+1):INDEX({L2_BAL},loan_term_months)))"
             f"/100*new_car_price_eur*{{k}}/12", EURM),
            ("Finance arm, taker finances elsewhere: margin given up on the old balance, EUR",
             f"-{FIN_RATE}*AVERAGE(INDEX({L2_BAL},loan_term_months-{{k}}+1):INDEX({L2_BAL},loan_term_months))"
             f"/100*new_car_price_eur*{{k}}/12", EURM),
            ("    most it may charge for early repayment from 20 November 2026, EUR",
             f"MIN(IF({{k}}>12,ccd2_early_repayment_cap_pct,ccd2_early_repayment_cap_last_year_pct)/100"
             f"*INDEX({L2_BAL},loan_term_months-{{k}}+1),loan_apr/100"
             f"*AVERAGE(INDEX({L2_BAL},loan_term_months-{{k}}+1):INDEX({L2_BAL},loan_term_months))*{{k}}/12)"
             f"*new_car_price_eur/100", EURM),
            ("Retained sale: contribution per customer won, EUR", "margin_per_repeat_sale", EURM),
            ("Retention gain per customer contacted, EUR", "upgrade_capture_uplift/100*margin_per_repeat_sale", EURM)]:
        ws.cell(row=r, column=1, value=label)
        for col in "BCD":
            ws[f"{col}{r}"] = "=" + expr.format(k=k_of[col])
            ws[f"{col}{r}"].number_format = fmt
        r += 1
    ws.cell(row=r, column=1, value=(
        "What the trade-off says. Interest: a customer who refinances with the group replaces a nearly repaid balance "
        "with a new one, so the finance arm earns more over those months, not less; only a customer who finances "
        "elsewhere costs it the old margin, and from November 2026 it may recover little of that (Directive (EU) "
        "2023/2225, Art. 29). The retained sale is worth far more than either. The customer's equity covers the next "
        "deposit, so no subsidy is needed to make the switch possible. The younger car's extra value is the "
        "customer's equity; what more young cars do to the market level is not measured. So the decision turns on "
        "one number: how many customers the offer wins that would not have come back anyway. Every euro paid to "
        "someone who would have upgraded regardless is lost, no model yet picks them out (X15), so the pilot's "
        "randomised holdout measures the uplift before any offer is set. Later contracts shift earlier too; this "
        "block counts only the months pulled forward.")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 118
    r += 2

    ws.cell(row=r, column=1, value="4. The operating metric: predicted lifetime value at sale (sample car)").font = BOLD
    r += 1
    for j, t in enumerate(["", "low (measured)", "high (published)"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 3)
    r += 1
    for label, lo, hi in [
            ("Lifetime value per car, the Per car sheet's P&L, EUR", LIFETIME, LIFETIME),
            ("less the incentive's resale cost, EUR", f"-{RESID_4Y}*{SHARE_LO}", f"-{RESID_4Y}*{SHARE_HI}"),
            ("less the level's price to hold, customer-option contract, EUR",
             f"-{RESID_4Y}*x6_price_share_group_48m/100", f"-{RESID_4Y}*x6_price_share_group_48m/100"),
            ("Predicted lifetime value at sale, EUR",
             f"{LIFETIME} - {RESID_4Y}*{SHARE_LO} - {RESID_4Y}*x6_price_share_group_48m/100",
             f"{LIFETIME} - {RESID_4Y}*{SHARE_HI} - {RESID_4Y}*x6_price_share_group_48m/100")]:
        ws.cell(row=r, column=1, value=label).font = BOLD if label.startswith("Predicted") else Font()
        ws.cell(row=r, column=2, value="=" + lo).number_format = EURM
        ws.cell(row=r, column=3, value="=" + hi).number_format = EURM
        r += 1
    r = put(ws, r, "Share of the buy-back book that comes back within a year",
            "=buyback_payables_current_eur_m/buyback_payables_eur_m", "0%",
            note="so realised values audit the metric within a year for most of the book, not 36-48 months later")
    ws.cell(row=r, column=1, value=(
        "The metric is known at sale and set by the engines, not by the seller: the sale margin and incentive, the "
        "incentive's resale cost, the level's price for the contract's book, finance income and the rest of the "
        "Per car P&L. Realised value is the audit: the buy-back book comes back within a year for the most part, "
        "Aramis publishes realised prices every quarter (X10), leases come back in waves at 48 and 60 months (X3), "
        "and the engine's calibrated band sets how far a realised value may miss before the prediction counts as "
        "wrong (X15). A shadow scorecard runs it from Phase 2. Guard against gaming (Kerr, Goodhart): the seller "
        "sets no input the engines use, overrides stay inside the band, and every prediction is audited when the car "
        "comes back. Only the deal terms move it, which is the point: one more euro of discount lowers it by more "
        "than a euro (section 1).")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 104
    r += 2

    ws.cell(row=r, column=1, value="Why a price changes behaviour here").font = BOLD
    r += 1
    r = put(ws, r, "Group brands' share of new cars registered in a month's last 3 days, %",
            "=selfreg_group_monthend_share", "0.0", note="the Netherlands, before the agency model: target timing")
    r = put(ws, r, "    other brands, same period, %", "=selfreg_other_monthend_share", "0.0")
    r = put(ws, r, "Revenue gain when one firm removed its salespeople's gamed quotas, %", "=misra_nair_revenue_gain_pct",
            "0", note="US data, one firm (Misra and Nair 2011): pay design moves a sales force a lot")
    ws.column_dimensions["A"].width = 66
    for c in "BCD":
        ws.column_dimensions[c].width = 18
    ws.column_dimensions["E"].width = 60
    return ws


def sheet_reach(wb):
    """X20: what each lever can reach of the expected column with every source, without the joint ventures' data,
    and without dealers' VIN-level evidence. Reach, not benefit: X21 turns it into benefits."""
    ws = wb.create_sheet("Data reach")
    ws["A1"], ws["A1"].font = "Data reach: what each lever can work on, by source (X20)", TITLE
    ws["A2"] = ("EUR millions a year, the expected column. Each cell is the part of a leak the programme can act on "
                "when a source is missing: reach, not a benefit (X21 sizes benefits on it). The map of sources, "
                "holders, routes and fallbacks is in analysis/data_reach_report.md.")
    ws["A2"].font, ws["A2"].alignment = NOTE, Alignment(wrap_text=True)
    ws.row_dimensions[2].height = 32
    head = 4
    for j, t in enumerate(["lever", "every source", "without the joint ventures' data",
                           "without dealers' VIN-level evidence", "what limits it"]):
        ws.cell(row=head, column=1 + j, value=t)
    style_header(ws, head, 5)
    r = head + 1
    first = r
    for label, a, b, c, note in [
            ("Leak 1, claims", LEAK1_CLAIMS, LEAK1_CLAIMS, f"{LEAK1_CLAIMS} * x20_reg_route_any_2024/100",
             "every claim passes through the group; without proof of sale, only markets whose register answers "
             "per car (NL, ES, IT: x20_reg_route_any_2024), and there by sampled spot checks"),
            ("Leak 1, targeting", f"{LEAK1_TARGETING} * finance_penetration/100",
             f"{LEAK1_TARGETING} * x14_agency_share_2025p/100", f"{LEAK1_TARGETING} * finance_penetration/100",
             "floors: buyers whose income the finance partner sees (finance_penetration), or, without it, buyers "
             "the group sells to itself (agency markets); a rebate claimed with income evidence could reach more"),
            ("Leak 2, upgrade moments", LEAK2, None, LEAK2,
             "customer-level timing and contact sit with the joint ventures; without them, cohort-level timing "
             "only (X3's waves), whose conversion is unmeasured"),
            ("Leak 3, resale execution", LEAK3_EXEC, LEAK3_EXEC, LEAK3_EXEC,
             "the buy-back book is the group's own"),
            ("Leak 3, level and curve", LEAK3_EXPECTED_RISK, LEAK3_EXPECTED_RISK, LEAK3_EXPECTED_RISK,
             "zero in the expected column (X18); the one-in-ten line is the group's own book in every case")]:
        ws.cell(row=r, column=1, value=label)
        for j, expr in enumerate((a, b, c)):
            ws.cell(row=r, column=2 + j, value=("=" + expr) if expr is not None else 0).number_format = EURM
        ws.cell(row=r, column=5, value=note).font = NOTE
        r += 1
    last = r - 1
    ws.cell(row=r, column=1, value="Reachable, expected a year").font = BOLD
    for j, col in enumerate("BCD"):
        c = ws.cell(row=r, column=2 + j, value=f"=SUM({col}{first}:{col}{last})")
        c.number_format, c.font = EURM, BOLD
    tot = r
    r += 1
    ws.cell(row=r, column=1, value="Share of the expected column")
    for j, col in enumerate("BCD"):
        ws.cell(row=r, column=2 + j, value=f"={col}{tot}/({total_expected()})").number_format = "0%"
    r += 2
    ws.cell(row=r, column=1, value=(
        "Read it with the map. Leak 3 needs no partner's permission: the buy-back commitments are the group's own, "
        "the price level is public, Aramis publishes realised prices, and a returned car's data can be read under the "
        "group's own contract with the rental firm or leasing company, which the Data Act treats as the car's user "
        "(data_act_user_owner_lessee). Leak 2 needs the joint ventures: the fallback is a division of labour, the "
        "group's timing and the partner's contact (its own soft opt-in covers a new finance contract, "
        "eprivacy_soft_optin), under an Art 26 arrangement for anything customer-level. Leak 1's claims control "
        "rests on what the group can require by contract, since the registers of its two largest markets are closed "
        "to it (x20_reg_no_route_2024).")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 104
    ws.column_dimensions["A"].width = 34
    for c in "BCD":
        ws.column_dimensions[c].width = 20
    ws.column_dimensions["E"].width = 80
    return ws


# The benefits case (X21, analysis/benefits_case_report.md): each lever's yearly benefit at full coverage, EUR m. Claims
# controls are the Leak 1 sheet's recovered line; retention is leak 2 itself, which is what contacting at the right
# moment earns; resale execution is X17's two levers; targeting is X5's line on the buyers whose income the finance
# partner sees (an upper bound, never committed); the tail lever is the thin slice priced as a known car, the one-year
# curve term's cut at the measured joint share (one year in ten only, an upper bound).
BEN = {
    "claims": f"{LEAK1_CLAIMS} * recoverable_share/100",
    "retention": LEAK2,
    "exec_days": "buyback_payables_current_eur_m * x17_days_cut * x17_day_cost_central/10000",
    "exec_route": "buyback_payables_current_eur_m * x17_share_routed/100 * x17_channel_gain_after_costs/100",
    "targeting": f"{LEAK1_TARGETING} * finance_penetration/100",
    "tail": ("buyback_payables_current_eur_m * thin_share_of_book/100 * (curve_1y_p80_unknown - curve_1y_p80_known)"
             "/2/retained_1y_pooled * x18_joint_share_book/100"),
}
COMMITTED = ("claims", "retention", "exec_days", "exec_route")
# Label, class, the roadmap's first earning phase (solution doc 8.1), and the gate that measures it.
BEN_ROWS = {
    "claims": ("Claims controls", "recovered", 2,
               "Phase 1: duplicate precision and the leakage baseline Finance certifies"),
    "retention": ("Retention at the upgrade moment", "recovered", 3,
                  "Phase 2: uplift over a randomised control group"),
    "exec_days": ("Resale execution: days cut", "recovered", 3, "Phase 3: days to sale on returns (X22)"),
    "exec_route": ("Resale execution: own retail", "recovered", 3, "Phase 3: margin per routed car (X22)"),
    "targeting": ("Income targeting (X5)", "upper bound, needs a holdout", 4, "Phase 3: randomised incentive holdouts"),
    "tail": ("Little-history cars priced as known cars", "tail reduced, one year in ten", 3, "Phase 3: little-history error"),
}
# The adverse case: every assumed rate a committed lever rests on at the end of its range that hurts the case.
ADVERSE_LOW = ("process_leak_pct", "recoverable_share", "upgrade_capture_uplift", "margin_per_repeat_sale",
               "x17_days_cut", "x17_share_routed")
PERIODS = [f"Phase {p}" for p in range(1, 5)] + [f"Year {j} after the exit" for j in range(1, 10)]
EURM1 = '#,##0.0;[Red]-#,##0.0'


def ben_reach(key, reach):
    """A lever's benefit when a source is missing (X20's fallbacks)."""
    e = BEN[key]
    if reach == "no_jv" and key == "retention":
        return "0"
    if reach == "no_jv" and key == "targeting":
        return swap(e, "finance_penetration", "x14_agency_share_2025p")
    if reach == "no_dealer" and key == "claims":
        return f"{e} * x20_reg_route_any_2024/100"
    return e


def sheet_benefits(wb, rows, phase_rows):
    """X21: what the programme gets back, lever by lever on X20's reach, and whether it pays for itself against a
    reference class, a stress and switching values. analysis/benefits_case.py holds the same arithmetic in Python,
    and the audit checks this sheet against it. Build cost is each X25 scenario's phase cost (the Programme cost
    sheet): no single ask, no scenario chosen, and no TARGET row in any formula."""
    ws = wb.create_sheet("Benefits")
    row_of = {r["id"]: i for i, r in enumerate(rows, start=2)}
    ws["A1"], ws["A1"].font = "Benefits: what the programme gets back, and whether it pays (X21)", TITLE
    ws["A2"] = ("EUR millions. Each euro sits in one lever class: recovered and counted; an upper bound that needs a "
                "holdout (shown, never committed); the tail cut one year in ten. The level charge and the cold premium "
                "are priced, not recovered, and the transfer price, the metric and the band are how the counted levers "
                "happen, so none of them carries a euro of its own. Tested the Green Book's way: a reference class, a "
                "stress and switching values (analysis/benefits_case_report.md).")
    ws["A2"].font, ws["A2"].alignment = NOTE, Alignment(wrap_text=True)
    ws.merge_cells("A2:H2")
    ws.row_dimensions[2].height = 58

    # ---- the levers ----
    r = 4
    ws.cell(row=r, column=1, value="The levers: yearly benefit at full coverage").font = BOLD
    r += 1
    for j, t in enumerate(["lever", "class", "earns from", "every source", "without the joint ventures' data",
                           "without dealers' VIN-level evidence", "every source, our adverse ends", "measured by"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 8)
    r += 1
    lev = {}
    for key, (label, cls, start, gate) in BEN_ROWS.items():
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=cls)
        ws.cell(row=r, column=3, value=f"Phase {start}")
        adverse = BEN[key]
        for n in ADVERSE_LOW:
            adverse = swap(adverse, n, f"Assumptions!$D${row_of[n]}")
        for j, expr in enumerate([ben_reach(key, "every"), ben_reach(key, "no_jv"), ben_reach(key, "no_dealer"),
                                  adverse]):
            ws.cell(row=r, column=4 + j, value="=" + expr).number_format = EURM1
        ws.cell(row=r, column=8, value=gate).font = NOTE
        lev[key] = r
        r += 1
    first, last = lev[COMMITTED[0]], lev[COMMITTED[-1]]
    ws.cell(row=r, column=1, value="Committed, expected a year").font = BOLD
    for col in "DEFG":
        c = ws.cell(row=r, column="ABCDEFG".index(col) + 1, value=f"=SUM({col}{first}:{col}{last})")
        c.number_format, c.font = EURM1, BOLD
    committed = r
    r += 2

    # ---- coverage and horizons ----
    ws.cell(row=r, column=1, value="Coverage: the share of the group's volume live, by period").font = BOLD
    r += 1
    ws.cell(row=r, column=1, value="period")
    for j, t in enumerate(PERIODS):
        ws.cell(row=r, column=2 + j, value=t)
    style_header(ws, r, 1 + len(PERIODS))
    r += 1
    ws.cell(row=r, column=1, value="share live (Phase 1: none; the pilot; the core markets; after the exit, all)")
    for j in range(len(PERIODS)):
        v = (0 if j == 0 else "=x21_cov_pilot_2024/100" if j == 1 else "=x21_cov_core_2024/100" if j < 4 else 1)
        ws.cell(row=r, column=2 + j, value=v).number_format = "0%"
    cov = r
    r += 1
    h5, h10 = r, r + 1
    r = put(ws, r, "Short horizon, months (the Green Book's five-year IT example)",
            "=gb_appraisal_it_example_years*12", "0")
    r = put(ws, r, "Long horizon, months (the Green Book's ten-year default)", "=gb_appraisal_default_years*12", "0")
    r += 1

    # ---- the cases ----
    ws.cell(row=r, column=1, value="The cases").font = BOLD
    r += 1
    for j, t in enumerate(["case", "benefits realised", "build cost, share of plan", "months a phase", "source"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 5)
    r += 1
    par = {}
    ref_row = r + 1
    for name, b, c, m, src in [
            ("plan", 1, 1, "=x21_phase_months", "the register"),
            ("reference class", "=1-mckox_sw_benefit_shortfall_pct/100", "=1+mckox_sw_cost_overrun_pct/100",
             "=x21_phase_months*(1+mckox_sw_schedule_overrun_pct/100)", "McKinsey-Oxford, software projects"),
            ("stress, 25% of benefits", "=fb_stress_benefit_low_pct/100", "=1+fb_stress_cost_overrun_pct/100",
             f"=D{ref_row}", "Flyvbjerg-Budzier's stress test; phases as the reference class"),
            ("stress, 50% of benefits", "=fb_stress_benefit_high_pct/100", "=1+fb_stress_cost_overrun_pct/100",
             f"=D{ref_row}", "the same, its high end"),
            ("adverse ends", f"=B{ref_row}", f"=C{ref_row}", f"=D{ref_row}",
             "the reference class with every assumed rate at the end of its range that hurts the case, and the "
             "run cost at its high end")]:
        ws.cell(row=r, column=1, value=name)
        ws.cell(row=r, column=2, value=b).number_format = "0%"
        ws.cell(row=r, column=3, value=c).number_format = "0%"
        ws.cell(row=r, column=4, value=m).number_format = "0.0"
        ws.cell(row=r, column=5, value=src).font = NOTE
        par[name] = r
        r += 1
    r += 1

    # ---- cash by period, one block per scenario and case ----
    # X25: no single ask. Each build scenario's phase costs come from the Programme cost sheet (the work list priced
    # four ways); each is run through every case. None is chosen.
    last_col = get_column_letter(1 + len(PERIODS))
    BUILD = "build cost (the phase, at its overrun)"
    blocks = {}
    for sk, slabel in X25_SCENARIOS:
        for name, pr in par.items():
            b, c, m = f"$B${pr}", f"$C${pr}", f"$D${pr}"
            src_col = "G" if name == "adverse ends" else "D"
            run = (f"Assumptions!$E${row_of['run_cost_eur_m_year']}" if name == "adverse ends"
                   else "run_cost_eur_m_year")
            ws.cell(row=r, column=1, value=f"Cash by period: {slabel}, {name}").font = BOLD
            for j, t in enumerate(PERIODS):
                ws.cell(row=r, column=2 + j, value=t)
            style_header(ws, r, 1 + len(PERIODS))
            r += 1
            R = {}
            labels = ["start, month", "length, months"] + [BEN_ROWS[k][0] for k in COMMITTED] + [
                "benefit", BUILD, "run cost", "share inside the long horizon",
                "share inside the short horizon", "middle of the part inside the long horizon, month",
                "middle of the part inside the short horizon, month", "net cash within the long horizon", "cumulative",
                "payback month, if in this period"]
            for i, lab in enumerate(labels):
                ws.cell(row=r + i, column=1, value=lab)
                R[lab] = r + i
            for j in range(len(PERIODS)):
                col = get_column_letter(2 + j)
                prev = get_column_letter(1 + j)
                phase = j + 1 if j < 4 else None

                def cell(lab):
                    return f"{col}{R[lab]}"
                st, ln = cell("start, month"), cell("length, months")
                ws[st] = 0 if j == 0 else f"={prev}{R['start, month']}+{prev}{R['length, months']}"
                ws[ln] = f"={m}" if phase else "=12"
                for k in COMMITTED:
                    on = phase is None or phase >= BEN_ROWS[k][2]
                    ws[cell(BEN_ROWS[k][0])] = (f"={b}*${src_col}${lev[k]}*{col}${cov}*{ln}/12" if on else 0)
                ws[cell("benefit")] = f"=SUM({col}{R[BEN_ROWS[COMMITTED[0]][0]]}:{col}{R[BEN_ROWS[COMMITTED[-1]][0]]})"
                ws[cell(BUILD)] = (f"={c}*'Programme cost'!${get_column_letter(1 + phase)}${phase_rows[sk]}"
                                   if phase else 0)
                ws[cell("run cost")] = 0 if phase else f"={run}*{ln}/12"
                f10, f5 = cell("share inside the long horizon"), cell("share inside the short horizon")
                ws[f10] = f"=MAX(0,MIN(1,($B${h10}-{st})/{ln}))"
                ws[f5] = f"=MAX(0,MIN(1,($B${h5}-{st})/{ln}))"
                ws[cell("middle of the part inside the long horizon, month")] = f"={st}+{ln}*{f10}/2"
                ws[cell("middle of the part inside the short horizon, month")] = f"={st}+{ln}*{f5}/2"
                ben, bld, rc = cell("benefit"), cell(BUILD), cell("run cost")
                net = cell("net cash within the long horizon")
                ws[net] = f"=({ben}-{rc})*{f10}-{bld}*SIGN({f10})"
                cum = cell("cumulative")
                before = f"(-{bld}*SIGN({f10}))" if j == 0 else f"({prev}{R['cumulative']}-{bld}*SIGN({f10}))"
                ws[cum] = f"={net}" if j == 0 else f"={prev}{R['cumulative']}+{net}"
                flow = f"(({ben}-{rc})*{f10})"
                ws[cell("payback month, if in this period")] = (
                    f'=IF(AND({before}<0,{before}+{flow}>=0,{flow}>0),{st}+{ln}*{f10}*(-{before})/{flow},"-")')
                for lab in labels[2:]:
                    if "share" not in lab:
                        ws[cell(lab)].number_format = EURM1
                for lab in ("share inside the long horizon", "share inside the short horizon"):
                    ws[cell(lab)].number_format = "0%"
                for lab in ("start, month", "length, months", "middle of the part inside the long horizon, month",
                            "middle of the part inside the short horizon, month", "payback month, if in this period"):
                    ws[cell(lab)].number_format = "0.0"
            r += len(labels)
            rng = lambda lab: f"$B${R[lab]}:${last_col}${R[lab]}"  # noqa: E731

            def npv(horizon, rate):
                f = rng(f"share inside the {horizon} horizon")
                mid = rng(f"middle of the part inside the {horizon} horizon, month")
                return (f"=SUMPRODUCT(({rng('benefit')}-{rng('run cost')})*{f}/(1+{rate}/100)^({mid}/12))"
                        f"-SUMPRODUCT({rng(BUILD)}*SIGN({f})/(1+{rate}/100)^({rng('start, month')}/12))")
            out = {"R": R}
            out["payback"] = r
            r = put(ws, r, "Payback month", f'=IF(COUNT({rng("payback month, if in this period")})=0,'
                    f'"none within ten years",MIN({rng("payback month, if in this period")}))', "0.0", bold=True)
            for p in range(1, 5):
                out[f"stop{p}"] = r
                r = put(ws, r, f"Loss if stopped at the Phase {p} gate (negative: a gain)",
                        f"=-{get_column_letter(1 + p)}{R['cumulative']}", EURM1)
            for h, hl in (("5y", "short"), ("10y", "long")):
                for w_, rate in (("high", "stla_wacc_pretax_high_pct"), ("low", "stla_wacc_pretax_low_pct")):
                    out[(h, w_)] = r
                    r = put(ws, r, f"Value over the {hl} horizon at the group's {'highest' if w_ == 'high' else 'lowest'} "
                            "pre-tax WACC", npv(hl, rate), EURM1)
            if name == "reference class":
                f5, mid5 = rng("share inside the short horizon"), rng("middle of the part inside the short horizon, month")
                disc = f"(1+stla_wacc_pretax_high_pct/100)^({mid5}/12)"
                for k in COMMITTED:
                    out[f"pv_{k}"] = r
                    r = put(ws, r, f"Present value, decision basis: {BEN_ROWS[k][0]}",
                            f"=SUMPRODUCT({rng(BEN_ROWS[k][0])}*{f5}/{disc})", EURM1)
                out["pv_build"] = r
                r = put(ws, r, "Present value, decision basis: build cost",
                        f"=SUMPRODUCT({rng(BUILD)}*SIGN({f5})/(1+stla_wacc_pretax_high_pct/100)^({rng('start, month')}/12))",
                        EURM1)
                out["pv_run"] = r
                r = put(ws, r, "Present value, decision basis: run cost",
                        f"=SUMPRODUCT({rng('run cost')}*{f5}/{disc})", EURM1)
            blocks[(sk, name)] = out
            r += 1

    # ---- payback and value, every scenario and case ----
    ws.cell(row=r, column=1, value="Payback by scenario, and value").font = BOLD
    r += 1
    heads = ["scenario, case", "payback month", "loss if stopped at the Phase 1 gate", "at Phase 2", "at Phase 3",
             "at Phase 4", "value, 5 years, highest WACC", "5 years, lowest", "10 years, highest", "10 years, lowest"]
    for j, t in enumerate(heads):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, len(heads))
    r += 1
    slab = dict(X25_SCENARIOS)
    for (sk, name), out in blocks.items():
        ws.cell(row=r, column=1, value=f"{slab[sk]}, {name}")
        ws.cell(row=r, column=2, value=f"=B{out['payback']}").number_format = "0.0"
        for p in range(1, 5):
            ws.cell(row=r, column=2 + p, value=f"=B{out[f'stop{p}']}").number_format = EURM1
        for j, key in enumerate([("5y", "high"), ("5y", "low"), ("10y", "high"), ("10y", "low")]):
            ws.cell(row=r, column=7 + j, value=f"=B{out[key]}").number_format = EURM1
        r += 1
    r += 1

    # ---- switching values and the gates that depend on build cost, one column per scenario ----
    ws.cell(row=r, column=1, value=(
        "Switching values: how far an input can move before the case stops paying (the reference class, the short "
        "horizon, the highest WACC), for each scenario")).font = BOLD
    r += 1
    ws.cell(row=r, column=1, value="input")
    for j, (sk, slabel) in enumerate(X25_SCENARIOS):
        ws.cell(row=r, column=2 + j, value=slabel)
    style_header(ws, r, 1 + len(X25_SCENARIOS))
    r += 1
    sw_rows = {}

    def per_scenario(label, fn, fmt, note=None, bold=False):
        nonlocal r
        ws.cell(row=r, column=1, value=label).font = BOLD if bold else Font()
        for j, (sk, _) in enumerate(X25_SCENARIOS):
            c = ws.cell(row=r, column=2 + j, value=fn(blocks[(sk, "reference class")], get_column_letter(2 + j)))
            c.number_format = fmt
        if note:
            ws.cell(row=r, column=2 + len(X25_SCENARIOS), value=note).font = NOTE
        sw_rows[label] = r
        r += 1

    pvb = lambda ref: "(" + "+".join(f"B{ref[f'pv_{k}']}" for k in COMMITTED) + ")"  # noqa: E731
    npv_ref = lambda ref: f"B{ref[('5y', 'high')]}"  # noqa: E731
    per_scenario("Share of benefits that can be lost", lambda ref, col: f"={npv_ref(ref)}/{pvb(ref)}", "0%", bold=True,
                 note="the Green Book sets no benefit shortfall and asks for switching values instead (4.1)")
    share_row = r - 1
    per_scenario("Build cost overrun absorbed, % of plan",
                 lambda ref, col: f"=($C${par['reference class']}*({pvb(ref)}-B{ref['pv_run']})/B{ref['pv_build']}-1)*100",
                 "0", note="against the Green Book's unmitigated +200% for ICT and Flyvbjerg-Budzier's +400%")
    per_scenario("Run cost at which it stops paying, EUR m a year",
                 lambda ref, col: f"=run_cost_eur_m_year*({pvb(ref)}-B{ref['pv_build']})/B{ref['pv_run']}", EURM1,
                 note="no reference class for operating cost (Green Book 4.1)")
    for a, k in [("process_leak_pct", "claims"), ("recoverable_share", "claims"),
                 ("upgrade_capture_uplift", "retention"), ("margin_per_repeat_sale", "retention"),
                 ("x17_days_cut", "exec_days"), ("x17_share_routed", "exec_route")]:
        per_scenario(f"{a}: the value at which it stops paying",
                     lambda ref, col, a=a, k=k: (f'=IF((1-{npv_ref(ref)}/B{ref[f"pv_{k}"]})>0,'
                                                 f'{a}*(1-{npv_ref(ref)}/B{ref[f"pv_{k}"]}),"survives at zero")'),
                     "0.00", note="all else as planned")
    r += 1

    # ---- the headline split ----
    ws.cell(row=r, column=1, value="The headline split").font = BOLD
    r += 1
    for j, t in enumerate(["", "expected a year", "one year in ten"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 3)
    r += 1
    reach_all = (f"{LEAK1_CLAIMS} + {LEAK1_TARGETING} * finance_penetration/100 + {LEAK2} + {LEAK3_EXEC} + "
                 f"{LEAK3_EXPECTED_RISK}")
    bref = f"$B${par['reference class']}"
    for label, e, t in [
            ("At risk (the headline)", "=" + total_expected(), "=" + total("base")),
            ("Addressable: what the levers can reach, every source", "=" + reach_all, "-"),
            ("Planned benefit, committed levers", f"=D{committed}", f"=D{committed}+D{lev['tail']}"),
            ("The same at the reference class", f"={bref}*D{committed}", f"={bref}*(D{committed}+D{lev['tail']})"),
            ("Upper bound beside it, never committed: income targeting", f"=D{lev['targeting']}",
             f"=D{lev['targeting']}"),
            ("Certified today", 0, 0)]:
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=e).number_format = EURM1
        ws.cell(row=r, column=3, value=t).number_format = EURM1
        r += 1
    r += 1

    # ---- the exit gate (benefits only), then the gates that depend on build cost ----
    ws.cell(row=r, column=1, value="The Phase 4 exit gate, derived: the run rate at month 24 (the same in every scenario)").font = BOLD
    r += 1
    gate_every = r
    for label, col in [("Gate, every source (the joint-venture arrangement agreed at Phase 1)", "D"),
                       ("Gate, on the named fallback (without the joint ventures' data)", "E"),
                       ("Gate, without dealers' VIN-level evidence", "F"),
                       ("On our own adverse ends", "G")]:
        r = put(ws, r, label, f"={bref}*{col}{committed}*x21_cov_core_2024/100", EURM1, bold=col == "D")
    r += 1
    ws.cell(row=r, column=1, value="The gates that depend on build cost, one per scenario (X22)").font = BOLD
    r += 1
    ws.cell(row=r, column=1, value="gate")
    for j, (sk, slabel) in enumerate(X25_SCENARIOS):
        ws.cell(row=r, column=2 + j, value=slabel)
    style_header(ws, r, 1 + len(X25_SCENARIOS))
    r += 1
    per_scenario("Floor: below this the decision basis is worth nothing, EUR m a year",
                 lambda ref, col: f"=$B${gate_every}*(1-{col}{share_row})", EURM1,
                 note="a certified run rate says where the rates landed, so the whole benefit profile scales with it")
    switch_row = r
    R_ = lambda ref: ref["R"]  # noqa: E731
    per_scenario("Phase 1 switch trigger: process_leak_pct below which claims controls do not repay the first two phases",
                 lambda ref, col: ("=process_leak_pct*(" + "+".join(
                     f"{c_}{R_(ref)[BUILD]}/(1+stla_wacc_pretax_high_pct/100)^({c_}{R_(ref)['start, month']}/12)"
                     for c_ in "BC") + f")/B{ref['pv_claims']}"), "0.00",
                 note="below it, start with residual value (X22); gate_leak_switch_s*_pct carry it, rounded")
    per_scenario("Phase 2 money gate: claims recoveries certified in the pilot market, annualised, EUR m",
                 lambda ref, col: f"=$D${lev['claims']}*{col}{switch_row}/process_leak_pct*x21_cov_pilot_2024/100", EURM1,
                 note="what claims controls earn at the switch trigger in the pilot; gate_claims_recovered_s*_eur_m (X22)")
    ws.cell(row=r, column=1, value=(
        "The register's TARGET rows carry these gates, rounded (gate_benefits_eur_m the first exit gate; "
        "gate_exit_floor_s*, gate_leak_switch_s* and gate_claims_recovered_s* one per scenario); the audit checks "
        "they agree. The exit gate replaces one set 'above' an older controls figure and 'about four times the ask' "
        "(skeptic B1), the single ask X25 retired.")).font = NOTE
    ws.column_dimensions["A"].width = 62
    for j in range(2, 2 + len(PERIODS)):
        ws.column_dimensions[get_column_letter(j)].width = 13
    return ws


def sheet_discounting(wb):
    """What the group's own discounting costs it when the car comes back.

    The case asks for "the impact of prior discounting decisions" and this is the only sheet that
    answers it. It is a **decomposition, not an addition**: the euros here are already inside
    leak 3's book and leak 1's spend, cut a different way. What makes the cut worth making is
    that this slice is the group's own decision, where the market level is not.

    Two estimates bracket it. The low end is ours (`analysis/discount_passthrough_report.md`),
    measured per car and an upper bound on its own terms because the data carries no trim. The
    high end is published (Holweg and Kattuman), specification-normalised but older, UK, and on
    auction prices. Neither is quoted alone.
    """
    ws = wb.create_sheet("Prior discounting")
    ws["A1"], ws["A1"].font = "What a discount at the new sale costs when the car comes back", TITLE

    r = 3
    ws.cell(row=r, column=1, value=(
        "Not a fourth leak. These euros are already counted - in leak 1 as spend and in leak 3 as "
        "residual exposure - and are cut here by cause instead of by business. The point of the "
        "cut is that this part is the group's own decision, and the market level is not.")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    r += 2

    ws.cell(row=r, column=1, value="The two estimates, and what they rest on").font = BOLD
    r += 1
    r = put(ws, r, "Share of a deeper deal still there at resale, measured", "=dpt_passthrough",
            fmt=PCT2, note="MEASURED - 35,552 resales of cars also seen at their own new sale. "
                           "An upper bound: no trim field", indent=1)
    r = put(ws, r, "Published: % of residual lost at 36 months, per 10% discount", "=hk_passthrough_36m",
            fmt=PCT1, note="SOURCED - Holweg and Kattuman, UK auction prices 1999-2004", indent=1)
    r = put(ws, r, "Published: the same in the same month, per 10% discount", "=hk_passthrough_now",
            fmt=PCT1, note="SOURCED - the smaller, substitution channel", indent=1)
    r = put(ws, r, "Discount assumed given, % of list", "=pl_incentive_pct_list",
            fmt=PCT1, note="ASSUMPTION - the Per car sheet's incentive, a share of list (pl_incentive_pct_list)", indent=1)
    r += 1

    ws.cell(row=r, column=1, value="One car, euros").font = BOLD
    r += 1
    r = put(ws, r, "List price when new", "=new_car_price_eur", indent=1)
    given = r
    r = put(ws, r, "Incentive given at the new sale",
            "=new_car_price_eur * pl_incentive_pct_list/100", indent=1)
    residual = r
    r = put(ws, r, "Residual value when it comes back",
            "=new_car_price_eur * retained_4y_uk/100",
            note="the contractual residual on a 48-month contract", indent=1)
    share_lo = r
    r = put(ws, r, "Share of that residual lost, measured (low)",
            "=1-(1-pl_incentive_pct_list/100)^dpt_passthrough", fmt=PCT2, indent=1)
    share_hi = r
    r = put(ws, r, "Share of that residual lost, published (high)",
            "=(hk_passthrough_36m + hk_passthrough_now)/100 * pl_incentive_pct_list/10",
            fmt=PCT2, indent=1)
    lost_lo = r
    r = put(ws, r, "Residual lost to the discount, low", f"=B{residual} * B{share_lo}", indent=1)
    lost_hi = r
    r = put(ws, r, "Residual lost to the discount, high", f"=B{residual} * B{share_hi}", indent=1)
    r += 1
    r = put(ws, r, "Cost at resale per euro of incentive given, low",
            f"=B{lost_lo} / B{given}", fmt=PCT2, bold=True,
            note="every euro handed over at the new sale costs this much again at resale")
    r = put(ws, r, "Cost at resale per euro of incentive given, high",
            f"=B{lost_hi} / B{given}", fmt=PCT2, bold=True)
    r += 2

    ws.cell(row=r, column=1, value="The book, EUR millions a year").font = BOLD
    r += 1
    book = r
    r = put(ws, r, "Buy-back residual falling due within a year",
            "=buyback_payables_current_eur_m",
            note="SOURCED - the current portion of the buy-back payables, the same base leak 3 uses",
            indent=1)
    r = put(ws, r, "Of that, traceable to our own prior discounting - low",
            f"=B{book} * B{share_lo}", bold=True, indent=1)
    r = put(ws, r, "Of that, traceable to our own prior discounting - high",
            f"=B{book} * B{share_hi}", bold=True, indent=1)
    r += 2

    for line in [
        "How to read this sheet",
        "- The headline on the Summary sheet does not change. Nothing here is added to it.",
        "- The low end is measured per car on US electric and plug-in vehicles and is an upper "
        "bound in its own terms, because the source has no trim field and part of a cheap new "
        "price is a cheaper car. The high end is published, specification-normalised, and from "
        "UK auctions in 1999-2004. Quote the range, never one end.",
        "- The published coefficient is for a 36-month residual and is applied here to a "
        "48-month contract.",
        "- A market-level pass-through could not be measured at all: see part 3 of "
        "analysis/discount_passthrough_report.md, where every European market in Eurostat's new-car and "
        "used-car indices gives nothing after the price move and more before it.",
        "- This is the line that joins leak 1 to leak 3. It is also the only line in the model "
        "the group can move by deciding to, which is why it belongs in the pitch.",
    ]:
        c = ws.cell(row=r, column=1, value=line)
        c.font = BOLD if not line.startswith("-") else NOTE
        c.alignment = Alignment(wrap_text=True)
        r += 1

    ws.column_dimensions["A"].width = 58
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 72
    return ws


def sheet_summary(wb, rows):
    ws = wb.create_sheet("Summary", 0)
    ws["A1"], ws["A1"].font = "Value at risk - summary", TITLE
    ws["A2"] = ("EUR millions a year, in two measures (X18): expected a year, what to budget, and in a "
                "one-in-ten-year market, what a bad year costs. They sit side by side and are never added. "
                "Every cell is a formula over the Assumptions sheet; change an input there and this moves.")
    ws["A2"].font = NOTE
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.row_dimensions[2].height = 32

    lows = {"process_leak_pct": "low",
            "upgrade_capture_uplift": "low", "margin_per_repeat_sale": "low",
            "thin_share_of_book": "low", "x17_days_cut": "low", "x17_share_routed": "low"}
    by_id = {r["id"]: r for r in rows}
    # Low and high point at the Assumptions sheet's low (D) and high (E) columns rather than copying
    # the numbers in, so changing a bound there moves these cells too.
    row_of = {r["id"]: i for i, r in enumerate(rows, start=2)}

    def cell(name, which):
        return f"Assumptions!${'D' if which == 'low' else 'E'}${row_of[name]}"

    def bound(expr, which):
        out = expr
        for name in lows:
            out = swap(out, name, cell(name, which))
        # A derived figure: its range is two checked rows of its own, not a low and a high on one row.
        out = swap(out, "x14_incentive_claims_central", f"x14_incentive_claims_{which}")
        out = swap(out, "x17_day_cost_central", f"x17_day_cost_{which}")
        if which == "high":   # the retail gain's range: after all costs (low and base) to before operating costs
            out = swap(out, "x17_channel_gain_after_costs", "x17_channel_gain_before_opex")
        return swap(out, "x5_targeting_gain_central", f"x5_targeting_gain_{which}")

    head = 4
    for j, t in enumerate(["", "expected a year", "in a one-in-ten-year market", "", "", "what drives it"]):
        ws.cell(row=head, column=1 + j, value=t)
    style_header(ws, head, 6)
    r = head + 1
    for label, expected, tail, driver in [
            ("Leak 1 - incentives paid wrongly or needlessly", LEAK1, LEAK1,
             "claims base disclosed (worldwide), leak rate assumed; targeting derived from published studies"),
            ("Leak 2 - upgrade moments missed", LEAK2, LEAK2,
             "timing is measured, the euro conversion is assumed"),
            ("Leak 3 - residual value", leak3_expected(), leak3("base"),
             "book due within a year disclosed. Expected: the level and curve count both ways and gained on the "
             "book's record, so zero, plus resale execution. One in ten: their joint p10, measured, plus execution")]:
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value="=" + expected).number_format = EURM
        ws.cell(row=r, column=3, value="=" + tail).number_format = EURM
        ws.cell(row=r, column=6, value=driver).font = NOTE
        r += 1
    for c in range(1, 4):
        ws.cell(row=r, column=c).font = BOLD
    ws.cell(row=r, column=1, value="Total value at risk a year")
    ws.cell(row=r, column=2, value="=" + total_expected()).number_format = EURM
    ws.cell(row=r, column=3, value="=" + total("base")).number_format = EURM
    ws.cell(row=r, column=6, value="the two columns answer different questions; never add or average them").font = NOTE
    r += 1
    ws.cell(row=r, column=1, value="Upper end, in no total")
    ws.cell(row=r, column=2, value=f"={total_expected()} + buyback_payables_current_eur_m * x18_exp_onesided_book/100"
            ).number_format = EURM
    ws.cell(row=r, column=3, value="=" + total_sum("base")).number_format = EURM
    ws.cell(row=r, column=6, value="expected: as if every buy-back were a customer's put at the residual; one in ten: "
                                   "the level and the curve at their p10s at once").font = NOTE
    r += 1
    ws.cell(row=r, column=1,
            value=f"Stress: the whole book in a core market's bad year ({by_id['level_1y_p10_core']['value']}%)")
    ws.cell(row=r, column=3, value="=" + total("stress")).number_format = EURM
    ws.cell(row=r, column=6, value="a Europe-wide bad year as deep as a core market's one-in-ten; the book's short "
                                   "history lacks one").font = NOTE
    r += 1
    ws.cell(row=r, column=1, value="Stress, upper end, in no total")
    ws.cell(row=r, column=3, value="=" + total_sum("stress")).number_format = EURM
    ws.cell(row=r, column=6, value="the same with the level and the curve at their p10s at once").font = NOTE
    r += 1
    ws.cell(row=r, column=1, value="Total without the targeting line")
    ws.cell(row=r, column=2, value=f"={total_expected()} - {LEAK1_TARGETING}").number_format = EURM
    ws.cell(row=r, column=3, value=f"={total('base')} - {LEAK1_TARGETING}").number_format = EURM
    ws.cell(row=r, column=6, value="paying buyers who would buy anyway is the cost of any incentive").font = NOTE

    # What the programme gets back (X21): the headline split into addressable, planned and certified. The Benefits
    # sheet holds the levers, the cases and the gate.
    r += 2
    ws.cell(row=r, column=1, value="What the programme gets back (the Benefits sheet, X21)").font = BOLD
    r += 1
    committed = " + ".join(f"({BEN[k]})" for k in COMMITTED)
    for label, e, t, note in [
            ("Addressable: what the levers can reach, every source",
             f"={LEAK1_CLAIMS} + {LEAK1_TARGETING} * finance_penetration/100 + {LEAK2} + {LEAK3_EXEC} + "
             f"{LEAK3_EXPECTED_RISK}", "-", "reach, not benefit (the Data reach sheet, X20)"),
            ("Planned benefit, committed levers", f"={committed}", f"={committed} + {BEN['tail']}",
             "claims controls, retention, resale execution; one year in ten adds the little-history cut"),
            ("The same at the reference class",
             f"=(1-mckox_sw_benefit_shortfall_pct/100) * ({committed})",
             f"=(1-mckox_sw_benefit_shortfall_pct/100) * ({committed} + {BEN['tail']})",
             "large software projects fall short of their benefits on average (McKinsey-Oxford)"),
            ("Certified today", 0, 0, "every committed rate is an assumption; Finance certifies from Phase 1")]:
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=e).number_format = EURM
        ws.cell(row=r, column=3, value=t).number_format = EURM
        ws.cell(row=r, column=6, value=note).font = NOTE
        r += 1

    r += 2
    ws.cell(row=r, column=1, value="Range from the assumed inputs").font = TITLE
    r += 1
    for j, t in enumerate(["", "low", "base", "high"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 4)
    r += 1
    for label, expr in [("Leak 1", LEAK1), ("Leak 2", LEAK2),
                        ("Leak 3, expected a year", leak3_expected()),
                        ("Leak 3, one year in ten", leak3("base")),
                        ("Total, expected a year", total_expected()),
                        ("Total, one year in ten", total("base"))]:
        ws.cell(row=r, column=1, value=label).font = BOLD if label.startswith("Total") else Font()
        ws.cell(row=r, column=2, value="=" + bound(expr, "low")).number_format = EURM
        ws.cell(row=r, column=3, value="=" + expr).number_format = EURM
        ws.cell(row=r, column=4, value="=" + bound(expr, "high")).number_format = EURM
        r += 1

    r += 2
    ws.cell(row=r, column=1, value="How much of this is evidence?").font = TITLE
    r += 1
    for j, t in enumerate(["", "expected, EUR m", "share", "one in ten, EUR m", "share", "meaning"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 6)
    r += 1
    parts = [
        ("Disclosed exposure, measured shocks (leak 3, the level and the curve)", LEAK3_EXPECTED_RISK,
         leak3_risk("base"), TIER_FILL["MEASURED"],
         "our own analysis, on a disclosed exposure: nothing expected, the largest line in a bad year"),
        ("Measured costs, assumed reach (leak 3, resale execution)", LEAK3_EXEC, LEAK3_EXEC, TIER_FILL["ASSUMPTION"],
         "a day in stock and the retail margin are measured; the days cut and the share routed are assumed"),
        ("Measured timing, assumed conversion (leak 2)", LEAK2, LEAK2, TIER_FILL["ASSUMPTION"],
         "the window is measured and the contracts disclosed; the euros are not"),
        ("Disclosed base, assumed leak rate (leak 1, claims)", LEAK1_CLAIMS, LEAK1_CLAIMS, TIER_FILL["ASSUMPTION"],
         "the group's own incentive claims (20-F, worldwide); the share paid wrongly is assumed"),
        ("Derived from published studies (leak 1, targeting)", LEAK1_TARGETING, LEAK1_TARGETING, TIER_FILL["SOURCED"],
         "Swiss price sensitivities by income, a European margin, one assumption"),
    ]
    for label, expected, tail, fill, meaning in parts:
        ws.cell(row=r, column=1, value=label).fill = PatternFill("solid", fgColor=fill)
        ws.cell(row=r, column=2, value="=" + expected).number_format = EURM
        ws.cell(row=r, column=3, value=f"=B{r}/({total_expected()})").number_format = "0%"
        ws.cell(row=r, column=4, value="=" + tail).number_format = EURM
        ws.cell(row=r, column=5, value=f"=D{r}/({total('base')})").number_format = "0%"
        ws.cell(row=r, column=6, value=meaning).font = NOTE
        r += 1
    ws.cell(row=r, column=1, value=(
        "Read the split before either total. What we measured best is a tail: leak 3's level and curve cost "
        "about nothing in an average year, because the group's buy-back contracts bring the cars back and a "
        "rising market pays for a falling one, and they are the largest measured line in a bad year. The "
        "expected column rests mostly on disclosed bases with assumed rates (leak 1's claims, leak 2, resale "
        "execution's reach), which a pilot should replace, and on leak 1's targeting line, derived from "
        "published studies and tested by the pilot's holdout.")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 60

    r += 3
    ws.cell(row=r, column=1, value="One input at a time").font = TITLE
    r += 1
    for j, t in enumerate(["input", "tier", "one in ten at its low", "one in ten at its high", "swing",
                           "swing, expected a year"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 6)
    r += 1
    sens = ["thin_share_of_book", "process_leak_pct",
            "upgrade_capture_uplift",
            "margin_per_repeat_sale", "x17_days_cut", "x17_share_routed"]
    def value_of(expr, override):
        """The formula's value in Python, to rank the inputs by the swing they cause, as the table claims."""
        names = {k: float(r["value"]) for k, r in by_id.items() if r["value"] not in ("", None)
                 and re.fullmatch(r"-?[\d.]+", r["value"].strip())}
        names.update(override)
        return eval(expr.replace("ABS(", "abs(").replace("MAX(", "max("),  # noqa: S307
                    {"__builtins__": {}, "abs": abs, "max": max}, names)

    def swing(n):
        lo = value_of(total("base"), {n: float(by_id[n]["low"])})
        hi = value_of(total("base"), {n: float(by_id[n]["high"])})
        return abs(hi - lo)

    for name in sorted(sens, key=lambda n: -swing(n)):
        ws.cell(row=r, column=1, value=by_id[name]["label"])
        ws.cell(row=r, column=2, value=by_id[name]["tier"]).fill = PatternFill(
            "solid", fgColor=TIER_FILL[by_id[name]["tier"]])
        ws.cell(row=r, column=3,
                value="=" + swap(total("base"), name, cell(name, "low"))).number_format = EURM
        ws.cell(row=r, column=4,
                value="=" + swap(total("base"), name, cell(name, "high"))).number_format = EURM
        ws.cell(row=r, column=5, value=f"=ABS(D{r}-C{r})").number_format = EURM
        ws.cell(row=r, column=6, value=(f"=ABS(({swap(total_expected(), name, cell(name, 'high'))}) - "
                                        f"({swap(total_expected(), name, cell(name, 'low'))}))")
                ).number_format = EURM
        r += 1
    ws.cell(row=r, column=1, value=(
        "Only assumed inputs are varied here, ranked by their swing on the one-in-ten total. The measured ones "
        "have ranges too - they are on the Assumptions sheet - but varying them would answer a different "
        "question: this table asks how much of the answer rests on judgement. The little-history share moves only the "
        "one-in-ten column, since the expected column's level and curve line is zero.")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 46

    ws.column_dimensions["A"].width = 52
    for c in "BCDE":
        ws.column_dimensions[c].width = 16
    ws.column_dimensions["F"].width = 52
    return ws


# ---- X25: the programme's build cost on four bases ----
# analysis/programme_cost.py holds the same arithmetic in Python and the audit checks these sheets against it.
X25_ROLES = {  # role: (pay group, sits in the markets from Phase 3, codes, the rate-card level if handed over)
    "engineer": ("oc2", False, True, "dl_gc14_dev_l4_gbp_day"),
    "data_scientist": ("oc2", False, True, "dl_gc14_dev_l5_gbp_day"),
    "architect": ("oc2", False, False, "dl_gc14_arch_l5_gbp_day"),
    "product_owner": ("oc2", False, False, "dl_gc14_arch_l4_gbp_day"),
    "model_validator": ("oc2", False, False, None),
    "legal_counsel": ("oc2", False, False, None),
    "change_lead": ("oc2", True, False, "dl_gc14_arch_l4_gbp_day"),
    "finance_analyst": ("oc2", False, False, None),
    "programme_manager": ("oc1", False, False, "dl_gc14_arch_l6_gbp_day"),
    "data_steward": ("oc3", True, False, "dl_gc14_dev_l3_gbp_day"),
}
X25_ALWAYS_BUILT = ("ws01", "ws04")
X25_SCENARIOS = [("b1", "1. In-house, no AI"), ("b2", "2. Buy and outsource"), ("b3", "3. In-house with AI"),
                 ("b4", "4. Cheapest route per workstream")]
X25_OH = "(1+x25_overhead_pct/100)"
X25_DAYS = "x25_days_per_fte_year/12"
X25_TOUCHED = "(ai_timewarp_coding_pct+ai_timewarp_debugging_pct+ai_timewarp_review_pct)/100"


def sheet_programme_cost(wb):
    """X25 parts 4-5: the rates block and the four bases ("Programme cost") over the work list ("Work list")."""
    work = list(csv.DictReader((HERE / "work_list.csv").open(newline="", encoding="utf-8")))
    ws = wb.create_sheet("Programme cost")
    ws["A1"], ws["A1"].font = "Programme cost: the build on four bases, from one work list (X25)", TITLE
    ws["A2"] = ("EUR millions over the 24-month build unless stated. One work list (the Work list sheet, "
                "work_list.csv: every FTE an ASSUMPTION with its basis) priced four ways: 1 in-house at Eurostat's "
                "loaded cost of an employee in manufacturing plus overhead; 2 an integrator at a public rate card "
                "(Deloitte, G-Cloud 14, UK: a ceiling), the group keeping legal, Finance and model validation; 3 in-house "
                "with AI, saving only what the studies measured on the share of the week they touch, plus the tools' "
                "seats; 4 each workstream's cheapest route, the per-car store and the value engine always built. "
                "Platform and change delivery are the same in every base. analysis/programme_cost_report.md.")
    ws["A2"].font, ws["A2"].alignment = NOTE, Alignment(wrap_text=True)
    ws.merge_cells("A2:J2")
    ws.row_dimensions[2].height = 72

    # ---- rates by role (EUR a person-month; savings as shares; seats EUR a month) ----
    r = 4
    heads = ["role", "pay group", "in-house, central team (EUR a month)", "in-house, the four markets",
             "in-house, the lower-cost hub", "integrator at the rate card", "AI saving, central", "AI saving, upper",
             "AI saving, adverse", "AI seats (EUR a month)"]
    for j, t in enumerate(heads):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, len(heads))
    r += 1
    rate_row = {}
    for role, (g, _, codes, level) in X25_ROLES.items():
        L = lambda cc, g=g: f"x25_loaded_{g}_{cc}_eur"
        cells = [role, g.upper(),
                 f"=(x25_loc_fr_pct/100*{L('fr')}+(1-x25_loc_fr_pct/100)*{L('it')})/12*{X25_OH}",
                 f"=({L('fr')}+{L('it')}+{L('de')}+{L('es')})/4/12*{X25_OH}",
                 f"={L('pl')}/12*{X25_OH}",
                 f"={level}/x25_gbp_per_eur*{X25_DAYS}" if level else "kept in-house"]
        if codes:
            cells += [f"={X25_TOUCHED}*(1-1/(1+ai_cui_tasks_pct/100))", f"={X25_TOUCHED}*ai_peng_faster_pct/100",
                      f"=-{X25_TOUCHED}*ai_metr25_time_pct/100",
                      "=(gh_copilot_enterprise_usd_user_month+claude_team_std_usd_seat_month)/x25_usd_per_eur"]
        else:
            cells += ["=hv_time_savings_pct/100", "=hv_time_savings_pct/100", "=0",
                      "=claude_team_std_usd_seat_month/x25_usd_per_eur"]
        for j, v in enumerate(cells):
            c = ws.cell(row=r, column=1 + j, value=v)
            c.number_format = "0.0%" if 7 <= j + 1 <= 9 else "#,##0.00" if j + 1 == 10 else "#,##0"
        rate_row[role] = r
        r += 1
    RC = lambda role, col: f"'Programme cost'!${col}${rate_row[role]}"

    # ---- the work list, each row priced every way ----
    wl = wb.create_sheet("Work list")
    wheads = ["workstream", "phase", "role", "FTE (ASSUMPTION)", "person-months", "sits in", "base 2 route",
              "base 1", "base 2", "base 3 people", "base 3 tools", "base 3 upper, people", "base 3 upper, tools",
              "base 3 adverse, people", "base 3 adverse, tools", "base 2 at Consip's team-day",
              "base 2, engineers offshore", "base 1, coders in the hub", "base 4", "basis"]
    wl.append(wheads)
    style_header(wl, 1, len(wheads))
    for i, w in enumerate(work, start=2):
        role, p = w["role"], int(w["phase"])
        g, market, codes, level = X25_ROLES[role]
        loc_col = "D" if market and p >= 3 else "C"
        rate = RC(role, loc_col)
        pmc = f"E{i}"
        vals = [w["workstream"], p, role, float(w["fte"]), f"=D{i}*x21_phase_months",
                "the four markets" if loc_col == "D" else "central team", "integrator" if level else "kept",
                f"={pmc}*{rate}/1000000",
                f"={pmc}*{RC(role, 'F')}/1000000" if level else f"=H{i}"]
        for save_col in ("G", "H", "I"):
            s = RC(role, save_col)
            vals += [f"={pmc}*(1-{s})*{rate}/1000000", f"={pmc}*(1-{s})*{RC(role, 'J')}/1000000"]
        vals += [f"={pmc}*consip_svi_eur_team_day*{X25_DAYS}/1000000" if level else f"=H{i}",
                 f"={pmc}*dl_gc14_off_dev_l4_gbp_day/x25_gbp_per_eur*{X25_DAYS}/1000000" if role == "engineer" else f"=I{i}",
                 f"={pmc}*{RC(role, 'E')}/1000000" if codes else f"=H{i}",
                 None,               # base 4: filled once the per-workstream block's rows are known
                 w["basis"]]
        for j, v in enumerate(vals, start=1):
            c = wl.cell(row=i, column=j, value=v)
            if 8 <= j <= 19:
                c.number_format = "0.000"
    last = len(work) + 1
    for width, col in zip([44, 7, 18, 10, 10, 15, 11] + [11] * 12 + [80], range(1, 21)):
        wl.column_dimensions[get_column_letter(col)].width = width
    wl.freeze_panes = "D2"
    COL = lambda c: f"'Work list'!${c}$2:${c}${last}"

    # ---- the four bases ----
    r += 1
    ws.cell(row=r, column=1, value="The four bases, EUR m over the build").font = BOLD
    r += 1
    for j, t in enumerate(["base", "people", "AI tools", "platform, data and licences", "change delivery", "total"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 6)
    r += 1
    ws_first = r + 11          # the per-workstream block starts after this block (9 rows) and its own header
    bases = [("b1", "1. In-house, no AI", f"=SUM({COL('H')})", "=0"),
             ("b2", "2. Buy and outsource (rate card)", f"=SUM({COL('I')})", "=0"),
             ("b3", "3. In-house with AI, central", f"=SUM({COL('J')})", f"=SUM({COL('K')})"),
             (None, "3. In-house with AI, upper gain", f"=SUM({COL('L')})", f"=SUM({COL('M')})"),
             (None, "3. In-house with AI, adverse", f"=SUM({COL('N')})", f"=SUM({COL('O')})"),
             ("b4", "4. Cheapest route per workstream", f"=SUM(G{ws_first}:G{ws_first + 10})", "=0"),
             (None, "2 at Consip's Italian public team-day (a floor)", f"=SUM({COL('P')})", "=0"),
             (None, "2 with the integrator's engineers offshore", f"=SUM({COL('Q')})", "=0"),
             (None, "1 with the coders in the lower-cost hub (no coordination cost)", f"=SUM({COL('R')})", "=0")]
    total_rows = {}
    for key, label, people, tools in bases:
        if key:
            total_rows[key] = r
        ws.cell(row=r, column=1, value=label)
        for j, v in enumerate([people, tools, "=inv_platform_eur_m", "=inv_change_eur_m", f"=SUM(B{r}:E{r})"]):
            ws.cell(row=r, column=2 + j, value=v).number_format = '#,##0.00'
        r += 1
    r += 1
    assert r + 1 == ws_first, (r, ws_first)

    # ---- base 4: each workstream's cheapest route ----
    for j, t in enumerate(["workstream", "base 1", "base 2", "base 3", "rule", "chosen", "base 4"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 7)
    r += 1
    ws_row = {}
    for name in sorted({w["workstream"] for w in work}):
        ws_row[name] = r
        sif = lambda col, name=name: f"SUMIF({COL('A')},\"{name}\",{COL(col)})"
        built = name.startswith(X25_ALWAYS_BUILT)
        vals = [name, f"={sif('H')}", f"={sif('I')}", f"={sif('J')}+{sif('K')}",
                "always built" if built else "cheapest",
                f"=IF(G{r}=B{r},\"in-house\",IF(G{r}=D{r},\"in-house with AI\",\"integrator\"))",
                f"=MIN(B{r},D{r})" if built else f"=MIN(B{r}:D{r})"]
        for j, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=j, value=v)
            if j in (2, 3, 4, 7):
                c.number_format = '#,##0.00'
        r += 1
    r += 1
    for i, w in enumerate(work, start=2):
        f = f"'Programme cost'!$F${ws_row[w['workstream']]}"
        wl.cell(row=i, column=19, value=f'=IF({f}="in-house",H{i},IF({f}="integrator",I{i},J{i}+K{i}))').number_format = "0.000"

    # ---- switching values and by phase ----
    ws.cell(row=r, column=1, value="Switching values").font = BOLD
    r += 1
    kept_b1 = f"SUMIF({COL('G')},\"kept\",{COL('H')})"
    int_b2 = f"SUMIF({COL('G')},\"integrator\",{COL('I')})"
    int_days = f"SUMIF({COL('G')},\"integrator\",{COL('E')})*{X25_DAYS}"
    b1 = f"SUM({COL('H')})"
    r = put(ws, r, "Overhead on in-house cost at which bases 1 and 2 cost the same (%)",
            f"=100*({int_b2}/(({b1}-{kept_b1})/{X25_OH})-1)", "#,##0.0",
            note="Base 2 is dearer at any overhead up to this; x25_overhead_pct is the assumed overhead")
    r = put(ws, r, "One integrator day rate for every handed-over role at which bases 1 and 2 cost the same (EUR)",
            f"=({b1}-{kept_b1})*1000000/({int_days})", "#,##0",
            note="Hand work over only below this blended day rate")
    r = put(ws, r, "Integrator days in base 2", f"={int_days}", "#,##0")
    r += 1
    ws.cell(row=r, column=1, value="By phase, EUR m (platform and change delivery spread evenly)").font = BOLD
    r += 1
    for j, t in enumerate(["base", "Phase 1", "Phase 2", "Phase 3", "Phase 4"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 5)
    r += 1
    ws.cell(row=r, column=1, value="phase")
    for p in range(1, 5):
        ws.cell(row=r, column=1 + p, value=p)
    phase_row = r
    r += 1
    phase_rows = {}
    for key, label, people_cols in [("b1", "1. In-house, no AI", ("H",)), ("b2", "2. Buy and outsource (rate card)", ("I",)),
                                    ("b3", "3. In-house with AI, central", ("J", "K")),
                                    ("b4", "4. Cheapest route per workstream", ("S",))]:
        phase_rows[key] = r
        ws.cell(row=r, column=1, value=label)
        for p in range(1, 5):
            pc = f"{get_column_letter(1 + p)}${phase_row}"
            parts = "+".join(f"SUMIF({COL('B')},{pc},{COL(c)})" for c in people_cols)
            ws.cell(row=r, column=1 + p, value=f"={parts}+(inv_platform_eur_m+inv_change_eur_m)/4").number_format = '#,##0.00'
        r += 1
    for width, col in zip([62, 12, 14, 14, 14, 14, 12, 12, 12, 12], range(1, 11)):
        ws.column_dimensions[get_column_letter(col)].width = width
    return {"phase": phase_rows, "total": total_rows}


def sheet_readme(wb, rows):
    by_id = {r["id"]: r for r in rows}
    ws = wb.create_sheet("Read me", 0)
    ws["A1"], ws["A1"].font = "Case 4 - value at risk", TITLE
    counts = {t: sum(1 for r in rows if r["tier"] == t)
              for t in ("MEASURED", "SOURCED", "ASSUMPTION", "TARGET", "SYNTHETIC")}
    rows_total, n_sources = collection_size()
    lines = [
        "",
        "What this is",
        "A value-at-risk model for the three leaks in Case 4, built so that every number can be "
        "traced to where it came from.",
        "",
        "How to use it",
        "Change any value in column C of the Assumptions sheet, or a low or high in columns D and "
        "E. Every other sheet is formulas, so the answer moves with it. No input is typed into a "
        "formula anywhere in this workbook; the only literals are unit conversions, the halving of "
        "a two-sided spread, the floor at zero on leak 3's expected level and curve line, and the month "
        "arithmetic on the upgrade-timing sheet.",
        "",
        "The five tiers",
        f"MEASURED ({counts['MEASURED']} inputs) - our own analysis of {rows_total / 1e6:.1f} "
        f"million used-car listings from {n_sources} sources. The source column names the report "
        "and `check_assumptions.py` re-reads the figure out of it.",
        f"SOURCED ({counts['SOURCED']} inputs) - published figures with a URL: Stellantis's FY2025 "
        "results and Form 20-F, Eurostat and ONS price indices, published studies.",
        f"ASSUMPTION ({counts['ASSUMPTION']} inputs) - our judgement, each with a low and a high "
        "and a caveat saying what it rests on. These are the rows a pilot should replace with "
        "evidence.",
        f"TARGET ({counts['TARGET']} inputs) - a level the team chose rather than found: a phase "
        "gate or a KPI threshold. These are commitments, not findings, so `check_assumptions.py` refuses to let "
        "one feed a value-at-risk formula, and the audit keeps every one out of every formula.",
        f"SYNTHETIC ({counts['SYNTHETIC']} inputs) - results of the leak-1 test harness, a world we or "
        "a blind red team built, and of the ledger prototype built on it. They measure the tool, not "
        "the group, so they are quoted only as "
        "rankings, failures and engineering facts, and both checkers refuse to let one feed a "
        "formula.",
        "",
        "Which of them move the answer",
        "Only the ASSUMPTION and SOURCED rows used by the three leaks reach the total. The "
        "per-car profit and loss, the programme cost and every gate and KPI sit on the Per car "
        "sheet and in the roadmap; they are registered so they can be argued with, and they change "
        "no headline. The Internal prices sheet (X19) holds the prices that put one business's cost "
        "into another's decision, one worked trade-off and the operating metric: transfers inside the "
        "group, so they change no headline either. The Data reach sheet (X20) shows what each lever can "
        "work on when a data source is missing: reach, not a benefit. The Benefits sheet (X21) turns reach "
        "into what the programme gets back, lever by lever, and tests it against a reference class, a stress "
        "and switching values, once for each build scenario; it derives the exit gate and, per scenario, the floor, "
        "the Phase 1 switch trigger and the Phase 2 money gate, and changes no headline. The Programme cost sheet "
        "(X25) prices one work list (the Work list sheet) four ways: in-house, bought from an integrator at a public "
        "rate card, in-house with AI on the share of the work the studies measured, and each workstream's cheapest "
        "route. None is chosen and there is no single ask; it changes no headline.",
        "",
        "What the colours mean",
        "Green MEASURED, blue SOURCED, orange ASSUMPTION, purple TARGET, grey SYNTHETIC. The "
        "Summary sheet splits "
        "the answer the same way.",
        "",
        "Read this before quoting either total",
        "The headline comes in two measures, side by side and never added (X18): expected a year, "
        "what to budget, and in a one-in-ten-year market, what a bad year costs. Leaks 1 and 2 and "
        "leak 3's resale execution are expected losses and appear in both. Leak 3's level and curve "
        "count both ways, because the group's buy-back contracts bring the cars back (a repurchase "
        "obligation, or a customer's put expected to be exercised: 20-F): on the book's own record "
        "they gained on average, so they add nothing to the expected column; one year in ten they "
        "take their joint p10, which is smaller than their two p10s added. Both upper ends are shown "
        "in no total: every buy-back a customer's put at the residual, and the level and curve "
        "failing at once.",
        "The three leaks are not equally well evidenced, and the split on the Summary sheet says "
        "so. Leak 3 rests on an exposure the group publishes and on shocks measured from official "
        "European price indices; its resale execution line prices measured costs (a day in stock, the "
        "group's own retail margin) over an assumed reach. Leak 1's claims line rests on the group's own incentive claims (the "
        "20-F's sales-incentive provision, worldwide; no regional total is disclosed) and an assumed "
        "share of claims paid wrongly. Its targeting line is derived from published studies (X5).",
        "All three leaks are yearly. In a one-in-ten-year market, leak 3 applies a one-year shock to the part of the "
        "buy-back book due within twelve months: the group's own book's one-in-ten-year fall, its markets "
        "weighted as it sells, and as a stress a Europe-wide bad year as deep as a core market's "
        "one-in-ten, which the book's short history lacks. The whole book over a three-year lease is on its sheet for "
        "context, beside what the group booked on these contracts in 2023-2025: scheduled "
        "depreciation to the expected residual, not a loss against it.",
        "",
        "The discount-to-resale pass-through, and where it sits",
        "The Prior discounting sheet is a decomposition of leaks 1 and 3, not a fourth leak: those "
        "euros are already counted, in leak 1 as spend and in leak 3 as residual exposure, and are "
        "cut there by cause instead of by business. Adding them to the total would be double "
        "counting, so the headline is unaffected by them.",
        "The first attempt to measure the pass-through failed and stays withdrawn "
        f"(analysis/tesla_event_report.md): {float(by_id['tesla_pre_announcement']['value']):.0f}% "
        "of the used-Tesla repricing had happened before the January 2023 US list-price cut, "
        "alongside earlier discounts and a price cut in China. The second attempt works because it "
        "compares a car with itself rather than a market with itself, and it passes a placebo the "
        "event study never had (analysis/discount_passthrough_report.md). The low end is ours and "
        "is an upper bound - the source carries no trim field; the high end is published. Quote "
        "the range, never one end.",
        "",
        "Currency and basis",
        "EUR millions a year unless stated. Group figures are Stellantis FY2025, used as a "
        "same-scale proxy for the anonymous group in the case. The upgrade-timing sheet works in "
        "shares of list price, so no exchange rate enters it.",
        "",
        "Rebuild",
        ".venv/bin/python check_assumptions.py   # every figure traces to its source",
        ".venv/bin/python build_var_model.py     # rebuilds this workbook",
    ]
    for i, text in enumerate(lines, start=2):
        c = ws.cell(row=i, column=1, value=text)
        if text and not text.startswith(" ") and text[-1] not in ".:" and len(text) < 60:
            c.font = BOLD
        else:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 112
    for i in range(2, len(lines) + 2):
        if len(str(ws.cell(row=i, column=1).value or "")) > 110:
            ws.row_dimensions[i].height = 46
    return ws


def sheet_provenance(wb, rows):
    ws = wb.create_sheet("Provenance")
    ws["A1"], ws["A1"].font = "Where every figure comes from", TITLE
    ws["A2"] = "One row per input, in the order the model uses them."
    ws["A2"].font = NOTE
    head = 4
    for j, t in enumerate(["used in", "input", "value", "tier", "source", "caveat"]):
        ws.cell(row=head, column=1 + j, value=t)
    style_header(ws, head, 6)
    r = head + 1
    order = {"Leak 1": 1, "Leak 2": 2, "Leak 3": 3, "Context": 4}
    for row in sorted(rows, key=lambda x: (order.get(x["used_in"].split(";")[0], 9), x["id"])):
        ws.cell(row=r, column=1, value=row["used_in"])
        ws.cell(row=r, column=2, value=row["label"])
        ws.cell(row=r, column=3,
                value=(float(row["value"]) if row["value"] else "") )
        ws.cell(row=r, column=4, value=row["tier"]).fill = PatternFill(
            "solid", fgColor=TIER_FILL.get(row["tier"], "FFFFFF"))
        ws.cell(row=r, column=5, value=row["source"] + (f"  {row['url']}" if row["url"] else ""))
        ws.cell(row=r, column=6, value=row["caveat"])
        for c in range(1, 7):
            ws.cell(row=r, column=c).alignment = Alignment(wrap_text=c in (2, 5, 6),
                                                           vertical="top")
            ws.cell(row=r, column=c).border = BOX
        r += 1
    for col, width in zip("ABCDEF", [14, 46, 12, 13, 62, 62]):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A5"
    return ws


def store_values(path):
    """Recalculate in LibreOffice and save, so every formula carries its result."""
    soffice = shutil.which("soffice")
    if not soffice:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([soffice, "--headless", "--calc", "--convert-to",
                        "xlsx:Calc MS Excel 2007 XML", "--outdir", tmp, str(path)],
                       check=True, capture_output=True)
        shutil.move(str(Path(tmp) / path.name), path)
    return True


def main():
    rows = read_rows()
    wb = Workbook()
    wb.remove(wb.active)
    named = sheet_assumptions(wb, rows)
    sheet_leak1(wb)
    by_id = {r["id"]: r for r in rows}
    sheet_leak2(wb, by_id)
    sheet_leak3(wb, by_id)
    sheet_summary(wb, rows)
    pc = sheet_programme_cost(wb)               # before Per car and Benefits, which read its totals and phase costs
    sheet_per_car(wb, pc)
    sheet_internal(wb, rows)
    sheet_reach(wb)
    sheet_benefits(wb, rows, pc["phase"])
    sheet_discounting(wb)
    for name in ("Programme cost", "Work list"):   # keep the X25 sheets after the X21 ones
        wb.move_sheet(name, len(wb.sheetnames) - 1 - wb.sheetnames.index(name))
    sheet_provenance(wb, rows)
    sheet_readme(wb, rows)
    wb.move_sheet("Read me", -(len(wb.sheetnames) - 1))
    wb.move_sheet("Summary", -(len(wb.sheetnames) - 2))
    wb.save(OUT)
    print(f"{len(rows)} inputs, {len(named)} named cells")
    print(f"sheets: {', '.join(wb.sheetnames)}")
    if store_values(OUT):
        print("recalculated in LibreOffice: results stored beside every formula")
    else:
        print("WARNING: LibreOffice (soffice) not found - formulas have no stored results, so "
              "open and save the file in Excel before sharing it")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
