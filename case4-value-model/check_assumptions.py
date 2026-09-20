"""Check that every figure in `assumptions.csv` is what it claims to be.

The project's rule is that a number is either measured, sourced or an assumption, and never
invented. This makes that rule testable rather than a promise:

  * **MEASURED** - the report named in the `source` column must exist, and the value must appear at
    the place the `anchor` column names: `row >> column` for one cell of a markdown table (the row
    is the table's first cell), or plain text that must be on the same line as the figure. This
    catches a figure that was copied wrong, taken from the wrong row, or left behind when an
    analysis was re-run and the CSV was not updated.
  * **SOURCED** - a URL is required, and the source must name something specific.
  * **ASSUMPTION** - a low and a high are required, the value must sit between them, and the
    `caveat` column must say what the judgement rests on.
  * **TARGET** - a number the team chose rather than found: a phase gate, a KPI threshold, an
    investment tranche. It needs a `caveat` saying why that level, and it must not be used in a
    workbook formula, so that a commitment can never be quoted as evidence.

Most report figures appear more than once - a p90 of +25.3% is also Germany's best 12-month move -
so "appears somewhere in the report" would pass a figure taken from the wrong row. The anchor
closes that. A sentence anchor holding two figures still cannot tell them apart; that is why
tables are anchored to a cell.

Usage: .venv/bin/python check_assumptions.py
"""
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
CSV = HERE / "assumptions.csv"
NUMBER = re.compile(r"[-+]?\d[\d,]*\.?\d*")


def numbers_in(text):
    """Every number in a report, with thousands separators removed."""
    out = set()
    for m in NUMBER.finditer(text):
        try:
            out.add(float(m.group().replace(",", "")))
        except ValueError:
            pass
    return out


def located(text, anchor):
    """Where in a report a figure must be: one table cell for `row >> column`, else every line
    that contains the anchor text."""
    if " >> " not in anchor:
        return [line for line in text.split("\n") if anchor in line]
    row, column = anchor.split(" >> ")
    out, header = [], None
    for line in text.split("\n"):
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip().replace("**", "").replace("`", "")
                 for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
        elif cells[0] == row and column in header:
            out.append(cells[header.index(column)])
    return out


def tolerance(raw):
    """Half a unit in the last decimal place the CSV actually wrote."""
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    return 0.5 * 10 ** -decimals


def main():
    rows = list(csv.DictReader(CSV.open()))
    cache, problems, checked = {}, [], 0

    for r in rows:
        rid, tier, raw = r["id"], r["tier"], (r["value"] or "").strip()

        if tier == "MEASURED":
            if not raw:
                problems.append(f"{rid}: MEASURED with no value")
                continue
            path = re.match(r"(analysis/[\w.]+\.md)", r["source"])
            if not path:
                problems.append(f"{rid}: MEASURED but source names no report file")
                continue
            report = HERE / path.group(1)
            if not report.exists():
                problems.append(f"{rid}: report {path.group(1)} does not exist")
                continue
            anchor = r["anchor"].strip()
            if not anchor:
                problems.append(f"{rid}: MEASURED with no anchor saying where in the report it is")
                continue
            if report not in cache:
                cache[report] = report.read_text()
            places = located(cache[report], anchor)
            value, tol = float(raw), tolerance(raw)
            if not places:
                problems.append(f"{rid}: anchor {anchor!r} not found in {path.group(1)}")
            elif not any(abs(n - value) <= tol for place in places for n in numbers_in(place)):
                problems.append(f"{rid}: {raw} not at {anchor!r} in {path.group(1)}")
            checked += 1

        elif tier == "SOURCED":
            if not r["url"].startswith("http"):
                problems.append(f"{rid}: SOURCED with no URL")
            if not r["source"].strip():
                problems.append(f"{rid}: SOURCED with no source named")
            checked += 1

        elif tier == "ASSUMPTION":
            if not (r["low"] and r["high"] and raw):
                problems.append(f"{rid}: ASSUMPTION needs value, low and high")
                continue
            if not float(r["low"]) <= float(raw) <= float(r["high"]):
                problems.append(f"{rid}: value {raw} outside {r['low']}..{r['high']}")
            if not r["caveat"].strip():
                problems.append(f"{rid}: ASSUMPTION with no caveat saying what it rests on")
            checked += 1

        elif tier == "TARGET":
            if not raw:
                problems.append(f"{rid}: TARGET with no value")
            if not r["caveat"].strip():
                problems.append(f"{rid}: TARGET with no caveat saying why that level")
            if r["used_in"].strip().startswith("Leak"):
                problems.append(f"{rid}: TARGET used in {r['used_in']!r} - a target the team chose "
                                "must never feed the value-at-risk model")
            checked += 1

        else:
            problems.append(f"{rid}: unknown tier {tier!r}")

    counts = {t: sum(1 for r in rows if r["tier"] == t)
              for t in ("MEASURED", "SOURCED", "ASSUMPTION", "TARGET")}
    print(f"{len(rows)} rows: " + ", ".join(f"{v} {k.lower()}" for k, v in counts.items()))
    print(f"{checked} checked")
    for p in problems:
        print(f"  FAIL {p}")
    print("all figures trace to their stated source" if not problems
          else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
