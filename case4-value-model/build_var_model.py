"""Build the value-at-risk workbook from `assumptions.csv`.

Every number in the model is a live formula pointing at a named cell on the Assumptions sheet.
No constant is typed into a formula, so a reader can change one input and watch the answer move,
and "nothing is invented" can be checked by inspection rather than taken on trust.

Each input carries a tier - MEASURED, SOURCED or ASSUMPTION - and the Summary sheet splits the
answer by tier, so the committee can see how much of the number is evidence and how much is
judgement.

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
             "TARGET": "EAE0F0"}
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
LEAK1 = ("eu_revenue_eur_m * incentive_pct_revenue/100 "
         "* (process_leak_pct/100 + targeting_leak_pct/100)")
LEAK2 = ("eu_shipments * finance_penetration/100 * upgrade_capture_uplift/100 "
         "* margin_per_repeat_sale / 1000000")
# Leak 3 is a yearly figure like the other two. The part of the buy-back book that comes back within
# twelve months - disclosed as the current portion of the payables - meets at most a year of market
# movement, so it takes the one-year level shock and the one-year curve error; the rest is counted
# in the year it falls due. The level shock is a one-sided downside at p10. The curve spreads are
# p10-p90 bands, so half of one is the distance from the centre to p10: the same one-in-ten. The two
# downsides are added, so this is a scenario in which both happen at once - a joint one-in-ten
# outcome would be smaller, because they are independent.
CURVE = ("(curve_1y_p80_known/2/retained_1y_pooled * (1 - thin_share_of_book/100) "
         "+ curve_1y_p80_unknown/2/retained_1y_pooled * thin_share_of_book/100)")
LEAK3 = f"buyback_payables_current_eur_m * (ABS({{level}})/100 + {CURVE})"
LEVELS = {"base": "level_1y_p10_core", "wide": "level_1y_p10", "stress": "level_1y_worst"}
# The whole book over a three-year lease, shown on the leak 3 sheet for context. Not a yearly figure.
CURVE_3Y = ("(curve_p80_known/2/retained_3y_pooled * (1 - thin_share_of_book/100) "
            "+ curve_p80_unknown/2/retained_3y_pooled * thin_share_of_book/100)")
BOOK_3Y = f"buyback_payables_eur_m * (ABS({{level}})/100 + {CURVE_3Y})"

def leak3(level="base"):
    return LEAK3.format(level=LEVELS[level])


def total(level="base"):
    return f"{LEAK1} + {LEAK2} + {leak3(level)}"


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
        "Every figure on this sheet is an ASSUMPTION or a SOURCED benchmark. There is no measured "
        "input here, because the group does not disclose a total incentive spend - its own 20-F "
        "records sales incentives as a critical estimate reviewed monthly, with no total given. "
        "Say this out loud rather than hiding it: it is the reason the ledger has to be built."
    )).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 46
    r += 2
    ws.cell(row=r, column=1, value="EUR millions a year, Enlarged Europe").font = BOLD
    r += 1
    r = put(ws, r, "Incentive spend (assumed share of European revenue)",
            "=eu_revenue_eur_m * incentive_pct_revenue/100",
            note="eu_revenue_eur_m x incentive_pct_revenue")
    r = put(ws, r, "Claims paid twice, wrongly or too late",
            "=eu_revenue_eur_m * incentive_pct_revenue/100 * process_leak_pct/100",
            indent=1, note="process_leak_pct")
    r = put(ws, r, "Incentives paid on sales that would have happened anyway",
            "=eu_revenue_eur_m * incentive_pct_revenue/100 * targeting_leak_pct/100",
            indent=1, note="targeting_leak_pct")
    r = put(ws, r, "Value at risk, leak 1", "=" + LEAK1, bold=True)
    r += 1
    r = put(ws, r, "Of which a controls layer actually recovers",
            "=eu_revenue_eur_m * incentive_pct_revenue/100 * process_leak_pct/100 "
            "* recoverable_share/100",
            note="leakage that exists is not leakage you can recover")
    r += 1
    ws.cell(row=r, column=1, value="Not sized here, on purpose").font = BOLD
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
            value="Equity covers the next deposit from month (searched from month 12)").font = BOLD
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

    r += 3
    ws.cell(row=r, column=1, value=(
        "A fall in the market level pushes the upgrade window months later, and a rise pulls it "
        "forward. That shift is the measured part of this leak: it comes from the value curve and "
        "the level moves, not from judgement. Turning it into euros needs the three assumptions "
        "below, and those should be replaced by a randomised pilot rather than defended. The window is "
        "searched from month 12 because the value curve is measured from one year onward; the first "
        "twelve months are drawn toward the list price by definition, which would put equity equal "
        "to the deposit at month 0.")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 32
    r += 2
    ws.cell(row=r, column=1, value="EUR millions a year").font = BOLD
    r += 1
    r = put(ws, r, "Contracts financed or leased through the group",
            "=eu_shipments * finance_penetration/100", fmt='#,##0',
            note="eu_shipments x finance_penetration")
    r = put(ws, r, "Extra customers retained by contacting them at the right moment",
            "=eu_shipments * finance_penetration/100 * upgrade_capture_uplift/100", fmt='#,##0',
            indent=1, note="upgrade_capture_uplift")
    r = put(ws, r, "Value at risk, leak 2", "=" + LEAK2, bold=True,
            note="x margin_per_repeat_sale")
    ws.column_dimensions["A"].width = 52
    for c in "BCDEFGH":
        ws.column_dimensions[c].width = 17
    return ws


def sheet_leak3(wb, by_id):
    v = {k: by_id[k]["value"] for k in ("level_1y_p10_core", "level_1y_p10", "level_1y_worst",
                                        "level_3y_p10_core", "level_3y_worst",
                                        "curve_1y_p80_known", "curve_1y_p80_unknown",
                                        "retained_1y_pooled", "pooling_gain_100",
                                        "pooling_gain_250", "buyback_payables_eur_m")}
    ws = wb.create_sheet("Leak 3 - Residual value")
    ws["A1"], ws["A1"].font = "Leak 3: the value nobody recovers", TITLE
    ws["A3"] = ("This is the leak the evidence actually reaches, and it is a yearly figure like the "
                "other two. The exposure is the part of the group's disclosed buy-back book that "
                "comes back within twelve months; the shocks are measured, not assumed.")
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
    r = put(ws, r, f"Base: a bad year in the group's largest EU markets "
                   f"(p10, {v['level_1y_p10_core']}%)",
            "=buyback_payables_current_eur_m * ABS(level_1y_p10_core)/100", indent=1)
    r = put(ws, r, f"Wider: p10 across all 26 EU markets ({v['level_1y_p10']}%)",
            "=buyback_payables_current_eur_m * ABS(level_1y_p10)/100", indent=1)
    r = put(ws, r, f"Stress: the worst twelve-month move observed ({v['level_1y_worst']}%)",
            "=buyback_payables_current_eur_m * ABS(level_1y_worst)/100", indent=1)
    r += 1
    ws.cell(row=r, column=1,
            value="The car itself over one year - what a value model can fix").font = BOLD
    r += 1
    r = put(ws, r, "Curve error on the part of the book with its own history",
            "=buyback_payables_current_eur_m * curve_1y_p80_known/2/retained_1y_pooled "
            "* (1 - thin_share_of_book/100)", indent=1,
            note=f"half of a {v['curve_1y_p80_known']}-point p10-p90 spread, on "
                 f"{v['retained_1y_pooled']} retained: centre to p10")
    r = put(ws, r, "Curve error on the thin slice (new brands, new markets, electrified lines)",
            "=buyback_payables_current_eur_m * curve_1y_p80_unknown/2/retained_1y_pooled "
            "* thin_share_of_book/100", indent=1,
            note=f"half of a {v['curve_1y_p80_unknown']}-point 80% interval; thin_share_of_book is "
                 "the one assumption here")
    r = put(ws, r, "Value at risk, leak 3 a year (base level shock)", "=" + leak3("base"), bold=True,
            note="level and curve downsides added: both going wrong at once, not a joint p10")
    r = put(ws, r, "Value at risk, leak 3 a year (stress level shock)", "=" + leak3("stress"))
    r += 1
    ws.cell(row=r, column=1, value="Reality check: what the group actually booked").font = BOLD
    r += 1
    for year in (2023, 2024, 2025):
        r = put(ws, r, f"Decrease in value on assets sold with a buy-back commitment, {year}",
                f"=buyback_value_decrease_{year}_eur_m", indent=1,
                note=("contracts of 12 months or less only" if year == 2025 else None))
    ws.cell(row=r, column=1, value=(
        "Compare these with the yearly rows above. The booked charge covers only the short contracts "
        "and has been rising fast; where it sits above the index-based base, that is the limit "
        "level_risk_report.md already states - official price indices may understate the moves, "
        "and the 20-F says electrified residuals carry extra uncertainty. Read the base as a floor.")
    ).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 46
    r += 2
    ws.cell(row=r, column=1, value="For context: the whole book over a three-year lease "
                                   "(not a yearly figure)").font = BOLD
    r += 1
    r = put(ws, r, f"Base: a bad three years in the largest EU markets "
                   f"(p10, {v['level_3y_p10_core']}%)",
            "=" + BOOK_3Y.format(level="level_3y_p10_core"), indent=1,
            note=f"level plus curve over 36 months, on all {float(v['buyback_payables_eur_m']):,.0f}m")
    r = put(ws, r, f"Stress: the worst three-year move observed ({v['level_3y_worst']}%)",
            "=" + BOOK_3Y.format(level="level_3y_worst"), indent=1)
    r += 1
    ws.cell(row=r, column=1, value="What the programme actually buys").font = BOLD
    r += 1
    r = put(ws, r, "Pooling the group's markets, on the thin slice only, a year",
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
        "the programme does remove is a share of the curve error, and it does that exactly where "
        "the book is thin - which is the part of the book the group's own 20-F says is growing.")
    ).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 60
    ws.column_dimensions["A"].width = 66
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 62
    return ws


def sheet_per_car(wb):
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
            note="the same rate leak 1 uses, on a different base", indent=1)
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
                        ("Leak 3 at risk per vehicle", leak3("base"))):
        r = put(ws, r, label, f"=({expr})*1000000/eu_shipments", indent=1)
    tot = r
    r = put(ws, r, "Total at risk per vehicle", f"=({total('base')})*1000000/eu_shipments",
            bold=True)
    r = put(ws, r, "In the worst year on record", f"=({total('stress')})*1000000/eu_shipments")
    r = put(ws, r, "Leakage against the 2025 result per vehicle", f"=-B{tot}/B{y25}",
            "0.0", note="the leakage is this many times the loss the group reported per vehicle")
    r += 2

    ws.cell(row=r, column=1, value="What the programme has to capture to pay for itself").font = BOLD
    r += 2
    cost = r
    r = put(ws, r, "Programme cost over 24 months, EUR m",
            "=inv_people_eur_m + inv_platform_eur_m + inv_change_eur_m",
            note="people, platform and data, change and training - all ASSUMPTION")
    var = r
    r = put(ws, r, "Value at risk a year, EUR m", f"={total('base')}")
    r = put(ws, r, "Share of it the programme must capture to break even", f"=B{cost}/B{var}",
            "0.0%", bold=True)
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
            fmt=PCT1, note="ASSUMPTION - the rate leak 1 uses, on list price", indent=1)
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
        "analysis/discount_passthrough_report.md, where 27 European markets over ten years give "
        "nothing after the price move and more before it.",
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
    ws["A2"] = ("EUR millions a year. Every cell is a formula over the Assumptions sheet; change an "
                "input there and this moves.")
    ws["A2"].font = NOTE

    head = 4
    for j, t in enumerate(["", "low", "base", "high", "what drives it"]):
        ws.cell(row=head, column=1 + j, value=t)
    style_header(ws, head, 5)

    lows = {"incentive_pct_revenue": "low", "process_leak_pct": "low",
            "targeting_leak_pct": "low", "finance_penetration": "low",
            "upgrade_capture_uplift": "low", "margin_per_repeat_sale": "low",
            "thin_share_of_book": "low"}
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
        return out

    r = head + 1
    for label, expr, driver in [
            ("Leak 1 - incentives paid wrongly or needlessly", LEAK1,
             "all assumed; no total spend is disclosed"),
            ("Leak 2 - upgrade moments missed", LEAK2,
             "timing is measured, the euro conversion is assumed"),
            ("Leak 3 - residual value", leak3("base"),
             "book due within a year disclosed, shocks measured")]:
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value="=" + bound(expr, "low")).number_format = EURM
        ws.cell(row=r, column=3, value="=" + expr).number_format = EURM
        ws.cell(row=r, column=4, value="=" + bound(expr, "high")).number_format = EURM
        ws.cell(row=r, column=5, value=driver).font = NOTE
        r += 1
    for c in range(1, 5):
        ws.cell(row=r, column=c).font = BOLD
    ws.cell(row=r, column=1, value="Total value at risk a year")
    for j, which in enumerate(["low", None, "high"]):
        expr = total("base")
        ws.cell(row=r, column=2 + j,
                value="=" + (bound(expr, which) if which else expr)).number_format = EURM
    r += 1
    ws.cell(row=r, column=1,
            value=f"Total under the stress level shock ({by_id['level_1y_worst']['value']}%)")
    ws.cell(row=r, column=3, value="=" + total("stress")).number_format = EURM
    ws.cell(row=r, column=5, value="worst twelve-month move in 26 EU markets since 2016").font = NOTE

    r += 3
    ws.cell(row=r, column=1, value="How much of this is evidence?").font = TITLE
    r += 1
    for j, t in enumerate(["", "EUR m", "share", "meaning"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 4)
    r += 1
    parts = [
        ("Disclosed exposure, measured shocks (leak 3)", leak3("base"), TIER_FILL["MEASURED"],
         "our own analysis, on a disclosed exposure"),
        ("Measured timing, assumed conversion (leak 2)", LEAK2, TIER_FILL["ASSUMPTION"],
         "the window is measured; the euros are not"),
        ("Assumed throughout (leak 1)", LEAK1, TIER_FILL["ASSUMPTION"],
         "no disclosed spend to anchor on"),
    ]
    first = r
    for label, expr, fill, meaning in parts:
        ws.cell(row=r, column=1, value=label).fill = PatternFill("solid", fgColor=fill)
        ws.cell(row=r, column=2, value="=" + expr).number_format = EURM
        ws.cell(row=r, column=3, value=f"=B{r}/({total('base')})").number_format = "0%"
        ws.cell(row=r, column=4, value=meaning).font = NOTE
        r += 1
    ws.cell(row=r, column=1, value=(
        "Read the split before the total. The residual-value figure rests on a number the group "
        "itself publishes and on shocks measured from official European price indices. The other "
        "two rest on assumptions that a pilot should replace.")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 46

    r += 3
    ws.cell(row=r, column=1, value="One input at a time").font = TITLE
    r += 1
    for j, t in enumerate(["input", "tier", "at its low", "at its high", "swing"]):
        ws.cell(row=r, column=1 + j, value=t)
    style_header(ws, r, 5)
    r += 1
    sens = ["thin_share_of_book", "incentive_pct_revenue", "process_leak_pct",
            "targeting_leak_pct", "finance_penetration", "upgrade_capture_uplift",
            "margin_per_repeat_sale"]
    for name in sorted(sens, key=lambda n: -(abs(float(by_id[n]["high"]) - float(by_id[n]["low"])))):
        ws.cell(row=r, column=1, value=by_id[name]["label"])
        ws.cell(row=r, column=2, value=by_id[name]["tier"]).fill = PatternFill(
            "solid", fgColor=TIER_FILL[by_id[name]["tier"]])
        ws.cell(row=r, column=3,
                value="=" + swap(total("base"), name, cell(name, "low"))).number_format = EURM
        ws.cell(row=r, column=4,
                value="=" + swap(total("base"), name, cell(name, "high"))).number_format = EURM
        ws.cell(row=r, column=5, value=f"=ABS(D{r}-C{r})").number_format = EURM
        r += 1
    ws.cell(row=r, column=1, value=(
        "Only assumed inputs are varied here. The measured ones have ranges too - they are on the "
        "Assumptions sheet - but varying them would answer a different question: this table asks "
        "how much of the answer rests on judgement.")).font = NOTE
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[r].height = 32

    ws.column_dimensions["A"].width = 52
    for c in "BCDE":
        ws.column_dimensions[c].width = 16
    ws.column_dimensions["E"].width = 46
    return ws


def sheet_readme(wb, rows):
    by_id = {r["id"]: r for r in rows}
    ws = wb.create_sheet("Read me", 0)
    ws["A1"], ws["A1"].font = "Case 4 - value at risk", TITLE
    counts = {t: sum(1 for r in rows if r["tier"] == t)
              for t in ("MEASURED", "SOURCED", "ASSUMPTION", "TARGET")}
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
        "a two-sided spread and the month arithmetic on the upgrade-timing sheet.",
        "",
        "The four tiers",
        f"MEASURED ({counts['MEASURED']} inputs) - our own analysis of {rows_total / 1e6:.1f} "
        f"million used-car listings from {n_sources} sources. The source column names the report "
        "and `check_assumptions.py` re-reads the figure out of it.",
        f"SOURCED ({counts['SOURCED']} inputs) - published figures with a URL: Stellantis's FY2025 "
        "results and Form 20-F, Eurostat and ONS price indices, one academic paper.",
        f"ASSUMPTION ({counts['ASSUMPTION']} inputs) - our judgement, each with a low and a high "
        "and a caveat saying what it rests on. These are the rows a pilot should replace with "
        "evidence.",
        f"TARGET ({counts['TARGET']} inputs) - a level the team chose rather than found: a phase "
        "gate, a KPI threshold, an investment tranche. These are commitments, not findings, so "
        "`check_assumptions.py` refuses to let one feed a value-at-risk formula.",
        "",
        "Which of them move the answer",
        "Only the ASSUMPTION and SOURCED rows used by the three leaks reach the total. The "
        "per-car profit and loss, the programme cost and every gate and KPI sit on the Per car "
        "sheet and in the roadmap; they are registered so they can be argued with, and they change "
        "no headline.",
        "",
        "What the colours mean",
        "Green MEASURED, blue SOURCED, orange ASSUMPTION, purple TARGET. The Summary sheet splits "
        "the answer the same way.",
        "",
        "Read this before quoting the total",
        "The three leaks are not equally well evidenced, and the split on the Summary sheet says "
        "so. Leak 3 rests on an exposure the group publishes and on shocks measured from official "
        "European price indices. Leak 1 has no measured input at all, because no total incentive "
        "spend is disclosed - the group's own 20-F records it as a critical estimate with no total "
        "given.",
        "All three leaks are yearly. Leak 3 applies a one-year shock to the part of the buy-back "
        "book due within twelve months; the whole book over a three-year lease is on its sheet for "
        "context, beside what the group actually booked on these contracts in 2023-2025.",
        "",
        "What this model deliberately does not contain",
        "A discount-to-resale pass-through factor. Every baseline answer to this case assumes one. "
        "We tried to measure it (analysis/tesla_event_report.md) and could not: "
        f"{float(by_id['tesla_pre_announcement']['value']):.0f}% of the used-Tesla repricing had "
        "happened before the January 2023 US list-price cut, alongside earlier discounts and a "
        "price cut in China. Quoting a number we could not measure would undo the point of the rest "
        "of the workbook.",
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
    sheet_per_car(wb)
    sheet_discounting(wb)
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
