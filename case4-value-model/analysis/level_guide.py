"""X7 part 3b: a residual guide's own forecast errors, against no change.

Skeptic B5 says residual guides forecast the level, so their error is the right comparison. Part 3 used ALD's
disposal margin, which is partly a forecast error. cap hpi, the UK's main residual guide, publishes a clean one: every
monthly "Future car market overview" for new cars has a "Historic forecast accuracy" section, in which its gold book
forecasts are compared with its own black book values when they fall due. Each edition gives, for 12- and 36-month
forecasts, the average since measurement began and the most recent result ("the most recent results show August 2018
36/60 gold book forecasts being -36.2% less than August 2021 36/60 black book").

Sources: the new-car editions of March, June, September and December each year, from March 2021 (the first edition
listed in cap hpi's sitemap) to September 2026, read from cap-hpi.com (links below). The PDFs are copyrighted and
stay in data/caphpi/ (private); only figures read from them are published.

No change on the same windows: the ONS second-hand car index (D7E9, UK) at the forecast month against the month the
forecast fell due. A forecast of "no change" misses by (index then / index at maturity) - 1, which is cap hpi's own
reading of its result (forecast over value, less 1). The index holds age constant, so its move is the level;
cap hpi's result is a car's forecast value at 12 or 36 months (and 20,000 or 60,000 miles), so it includes the curve
as well. The comparison is descriptive: the 36-month windows overlap, and part 5 showed that a few years of windows
cannot carry a test. Scores: RMSE, mean miss and the windows where each was closer, overall and split by whether
the level rose or fell; and a straight line of cap hpi's miss on no change's (intercept: its miss when the level
is flat; slope: how its miss scales with the level's move).

Checks: every edition yields both horizons and both averages; wherever cap hpi prints a sign it agrees with its word
(less or lower, more or higher); each result's months are the horizon apart and fall due a month or two before the
edition; the September 2021 figures read by hand with a different extractor (poppler's pdftotext) are reproduced.

Usage: .venv/bin/python analysis/level_guide.py [--pull]   (writes analysis/level_guide_report.md; --pull fetches the
       PDFs again)
"""
import logging
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from pypdf import PdfReader

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
from level_risk import load  # noqa: E402

OUT = HERE / "level_guide_report.md"
CACHE = HERE.parent / "data" / "caphpi"
ONS = "ONS CPI 07.1.1B, second-hand cars (D7E9)"
HORIZONS = (12, 36)
UPLOADS = "https://www.cap-hpi.com/wp-content/uploads/"
EDITIONS = {  # edition month -> PDF, from each edition's page at cap-hpi.com/editorials/ (26 September 2026)
    "2021-03": "2024/06/20210223082747_CarNew_March2021.pdf",
    "2021-06": "2024/06/20210524143839_CarNew_June2021.pdf",
    "2021-09": "2024/06/20210825161947_CarNew_September2021.pdf",
    "2021-12": "2024/06/20211125142009_CarNew_December2021.pdf",
    "2022-03": "2024/06/20220223142326_Car_New_March2022.pdf",
    "2022-06": "2024/06/20220526101405_Car_New_June2022.pdf",
    "2022-09": "2024/06/20220824083528_Car_New_September2022.pdf",
    "2022-12": "2024/06/20221125145307_Car_New_December2022.pdf",
    "2023-03": "2024/07/20230223103736_Future-Car-Market-Overview-New-Cars-Mar2023.pdf",
    "2023-06": "2024/07/20230525112614_Future-Car-Market-Overview-New-Cars-Jun2023.pdf",
    "2023-09": "2024/07/20230824142239_Future-Car-Market-Overview-New-Cars-Sep2023.pdf",
    "2023-12": "2024/07/20231127073702_Future-Car-Market-Overview-New-Cars-Dec2023.pdf",
    "2024-03": "2024/07/20240226135725_Future-Car-Market-Overview-New-Cars-Mar2024.pdf",
    "2024-06": "2024/06/20240606154155_Future-Car-Market-Overview-New-Cars-Jun2024.pdf",
    "2024-09": "2024/10/Future-Car-Market-Overview-New-Cars-Sep2024.pdf",
    "2024-12": "2024/11/Future-Car-Market-Overview-New-Cars-Dec2024.pdf",
    "2025-03": "2025/02/Future-Car-Market-Overview-New-Cars-Mar25.pdf",
    "2025-06": "2025/05/Future-Car-Market-Overview-New-Cars-Jun25.pdf",
    "2025-09": "2025/08/Future-Car-Market-Overview-New-Cars-Sep25.pdf",
    "2025-12": "2025/11/Future-Car-Market-Overview-New-Cars-Dec25.pdf",
    "2026-03": "2026/02/Future-Car-Market-Overview-New-Cars-Mar26.pdf",
    "2026-06": "2026/05/Future-Car-Market-Overview-New-Cars-Jun26.pdf",
    "2026-09": "2026/08/Future-Car-Market-Overview-New-Cars-Sep26.pdf",
}


def text(edition, pull=False):
    """One edition's text, from the cached PDF (downloaded once)."""
    path = CACHE / Path(EDITIONS[edition]).name
    if pull or not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        r = requests.get(UPLOADS + EDITIONS[edition], timeout=120, headers={"User-Agent": "case4-value-model"})
        r.raise_for_status()
        path.write_bytes(r.content)
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


MONTH = r"([A-Z][a-z]+) ?(\d{4})"
NUMBER = r"([+-]?) ?(\d+)\. ?(\d+)% (less|more|higher|lower)"
RESULT = re.compile(r"most recent results? show " + MONTH + r" (12/20|36/60) (?:gold book )?forecasts [a-z ]*?"
                    + NUMBER + r" than " + MONTH)
AVERAGE = re.compile(r"our (12|36)[ -]month (?:new |used )?forecasts have averaged " + NUMBER)
HAND_READ = {("2021-09", 12): ("2020-08", "2021-08", -27.1, -2.4),   # pdftotext, 26 September 2026
             ("2021-09", 36): ("2018-08", "2021-08", -36.2, -11.1)}


def signed(sign, whole, tenths, word):
    """cap hpi's figure with the sign its word gives; None when a printed sign disagrees with the word."""
    value = float(f"{whole}.{tenths}") * (-1 if word in ("less", "lower") else 1)
    if sign and (sign == "-") != (value < 0) and value != 0:
        return None
    return value


def month(name, year):
    return pd.Period(f"{name} {year}", freq="M").strftime("%Y-%m")


def parse(edition, raw):
    """Both horizons' most recent result and running average from one edition."""
    t = re.sub(r"\s+", " ", raw)
    results = RESULT.findall(t)
    averages = {int(h): signed(*rest) for h, *rest in AVERAGE.findall(t)}
    rows = []
    for m1, y1, code, sign, whole, tenths, word, m2, y2 in results:
        h = int(code.split("/")[0])
        rows.append({"edition": edition, "h": h, "forecast made": month(m1, y1), "fell due": month(m2, y2),
                     "cap hpi": signed(sign, whole, tenths, word), "average so far": averages.get(h)})
    return rows


def main():
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    pull = "--pull" in sys.argv
    d = pd.DataFrame([r for e in EDITIONS for r in parse(e, text(e, pull))])
    ons = load()[(ONS, "UK")]
    d["no change"] = [(ons[f] / ons[m] - 1) * 100 for f, m in zip(d["forecast made"], d["fell due"])]
    d["level move"] = [(ons[m] / ons[f] - 1) * 100 for f, m in zip(d["forecast made"], d["fell due"])]
    d["closer"] = np.where(d["cap hpi"].abs() < d["no change"].abs(), "cap hpi", "no change")

    rows = []

    def check(name, passes, got):
        rows.append({"check": name, "got": got, "passes": bool(passes)})

    per = d.groupby("edition")["h"].apply(sorted)
    check("every edition yields a 12- and a 36-month result", (per.map(tuple) == HORIZONS).all() and
          len(per) == len(EDITIONS), f"{int((per.map(tuple) == HORIZONS).sum())} of {len(EDITIONS)} editions")
    check("every result and average has a sign consistent with its word, and every average was found",
          d["cap hpi"].notna().all() and d["average so far"].notna().all(), f"{len(d)} results")
    gap = [(pd.Period(m, "M") - pd.Period(f, "M")).n for f, m in zip(d["forecast made"], d["fell due"])]
    check("each result's months are the horizon apart", (np.array(gap) == d["h"].to_numpy()).all(),
          f"{sum(np.array(gap) == d['h'].to_numpy())} of {len(d)}")
    lag = [(pd.Period(e, "M") - pd.Period(m, "M")).n for e, m in zip(d["edition"], d["fell due"])]
    check("each result fell due one or two months before its edition", set(lag) <= {1, 2}, f"lags {sorted(set(lag))}")
    for (e, h), (f, m, value, avg) in HAND_READ.items():
        r = d[(d["edition"] == e) & (d["h"] == h)].iloc[0]
        check(f"{e} edition, {h} months: the figures read by hand ({f} to {m}, {value:+.1f}%, average {avg:+.1f}%)",
              (r["forecast made"], r["fell due"], r["cap hpi"], r["average so far"]) == (f, m, value, avg),
              f"{r['forecast made']} to {r['fell due']}, {r['cap hpi']:+.1f}%, average {r['average so far']:+.1f}%")
    ck = pd.DataFrame(rows)

    summary, fits = [], []
    for h in HORIZONS:
        s = d[d["h"] == h]
        slope, intercept = np.polyfit(s["no change"], s["cap hpi"], 1)
        fits.append({"fit": f"{h} months", "windows": len(s), "cap hpi miss with a flat level (intercept, pp)":
                     f"{intercept:+.1f}", "cap hpi miss per point of no change's miss (slope)": f"{slope:.2f}"})
        for label, part in (("all windows", s), ("level rose", s[s["level move"] > 0]),
                            ("level fell", s[s["level move"] <= 0])):
            if part.empty:
                continue
            summary.append({"horizon and windows": f"{h} months, {label}", "n": len(part),
                            "falling due": f"{part['fell due'].min()} to {part['fell due'].max()}",
                            "cap hpi RMSE (pp)": f"{np.sqrt((part['cap hpi'] ** 2).mean()):.1f}",
                            "no change RMSE (pp)": f"{np.sqrt((part['no change'] ** 2).mean()):.1f}",
                            "cap hpi mean (pp)": f"{part['cap hpi'].mean():+.1f}",
                            "no change mean (pp)": f"{part['no change'].mean():+.1f}",
                            "windows cap hpi was closer": int((part["closer"] == "cap hpi").sum())})
    summary = pd.DataFrame(summary)

    show = d.assign(**{c: d[c].map(lambda v: f"{v:+.1f}") for c in ("cap hpi", "average so far", "no change",
                                                                      "level move")})
    show = show[["edition", "h", "forecast made", "fell due", "cap hpi", "no change", "level move", "closer",
                 "average so far"]].rename(columns={"h": "months ahead", "cap hpi": "cap hpi miss (%)",
                                                   "no change": "no change miss (%)",
                                                   "level move": "ONS level move (%)",
                                                   "average so far": "cap hpi average so far (%)"})
    fell = d[(d["h"] == 36) & (d["level move"] <= 0)]
    after = int((fell["fell due"] >= "2024-02").sum())
    lines = [
        "# X7 part 3b: a residual guide's own forecast errors, against no change",
        "",
        "Generated by `analysis/level_guide.py`; the method is in its docstring. cap hpi's gold book forecasts for new "
        "cars against its own black book values when they fell due, as printed in the \"Historic forecast accuracy\" "
        f"section of {len(EDITIONS)} quarterly editions of its new-car \"Future car market overview\" "
        f"({min(EDITIONS)} to {max(EDITIONS)}), beside a no-change forecast on the ONS second-hand car index over the "
        "same months. UK data. A miss is forecast over value, less 1, as cap hpi reads its own: negative means the "
        "forecast was below the value.",
        "",
        "## Summary",
        "",
        "RMSE and mean in percentage points of value; closer counts the windows where cap hpi's miss was smaller than "
        "no change's. The 36-month windows overlap heavily, so this describes a record; it tests nothing (part 5).",
        "",
        md_table(summary),
        "",
        "A straight line through each horizon's windows, cap hpi's miss against no change's. The intercept is cap "
        "hpi's miss when the ONS level is flat: its standing discount, the curve included. A slope of 1 means its miss "
        "moved point for point with the level on the ONS scale; above 1, its own values moved more than the index or "
        "its forecasts leaned against the move; below 1, it partly foresaw the move. Descriptive, like the rest.",
        "",
        md_table(pd.DataFrame(fits)),
        "",
        "## Every edition",
        "",
        md_table(show),
        "",
        "## Checks",
        "",
        md_table(ck),
        "",
        "## Limits",
        "",
        "- **cap hpi scores itself against its own black book,** a guide value, not sale prices.",
        "- **Its result includes the curve.** It is a car's forecast value at 12 or 36 months, so an error in how cars "
        "age counts as well as the level. No change here forecasts the level only; it is the right yardstick for the "
        "level part of a residual, not for the whole.",
        "- **Mix.** Its figure averages across vehicle ids; the ONS index prices a fixed basket aged 1-3 years (to "
        "January 2024; Auto Trader listings from February 2024).",
        f"- **The windows where the level fell end after the ONS switch:** {after} of the {len(fell)} such 36-month "
        "windows fall due from February 2024, so cap hpi's wins are scored against the Auto Trader-based index.",
        "- **Few independent windows.** Four editions a year give overlapping windows; the 36-month record spans one "
        "cycle, the 2021-22 rise and the fall after it.",
        "- **Editions from March 2021 only.** Earlier ones are not listed on cap hpi's site; its averages cover "
        "everything since measurement began (12 months from January 2015, per the editions).",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(summary.to_string(index=False))
    print(pd.DataFrame(fits).to_string(index=False))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
