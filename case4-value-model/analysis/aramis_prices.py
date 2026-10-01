"""X10 part 3a: the group's own realised used-car prices, from Aramis Group's public releases.

Aramis Group (France) is 60.54% owned by Stellantis (Stellantis 20-F FY2025, Exhibit 8.1). It sells used cars online
to consumers in six countries (B2C: refurbished used cars and pre-registered cars) and sells other cars to the trade
(B2B). Every quarterly release since its June 2021 IPO gives units and revenue by segment, and revenue by country.
Revenue over units is a realised average price per car: what the group's own used-car business was paid. This is
unlike every other European price we hold, which is an advert's asking price.

The question for the solution: do the group's own realised prices move with the official used-car indices that leak
3 and X6 measure the market level on? For each fiscal quarter (Aramis's year ends 30 September), the year-on-year
change of Aramis's realised price per refurbished car is set against the year-on-year change of those indices,
weighted by Aramis's revenue by country in that quarter.

**What the average price is and is not.** It moves with the market, and with Aramis's own mix: country, age, segment
and the price ranges it chooses to sell. No release gives units by country, so the country mix can't be taken out of
the price itself; it is taken into the index side through the weights. Aramis's own "price effect" statements, where a
release gives one, are listed beside it.

**How the quarters are built.** Q1 (October-December) and Q3 (April-June) come from their own releases. Q2 is H1 less
Q1, and Q4 is the full year less the nine months. Each figure is taken from the first release that reports it, on the
reported basis. The 2025 first-half release prints its tables as images, so its figures come from the next year's
release, as its prior-year column. That release's text confirms the figures it states. Each release's prior-year
column is checked against the figure first reported.

Sources: Aramis Group financial press releases (https://aramis.group/investors/press-releases/c/financial-results/),
PDFs cached in data/raw/aramis/ (private). Eurostat HICP CP07112 (prc_hicp_minr, COICOP 2018, index 2025=100) for
France, Belgium, Spain, Austria and Italy, cached in data/reference/x10_hicp_used_cars.parquet. ONS D7E9 for the UK,
from data/reference/price_indices.parquet.
Usage: .venv/bin/python analysis/aramis_prices.py
"""
import json
import logging
import re
import ssl
import sys
import urllib.request
from pathlib import Path

import certifi
import numpy as np
import pandas as pd
from pypdf import PdfReader

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_unified import md_table  # noqa: E402

OUT = HERE / "aramis_prices_report.md"
RAW = HERE.parent / "data" / "raw" / "aramis"
HICP = HERE.parent / "data" / "reference" / "x10_hicp_used_cars.parquet"
INDICES = HERE.parent / "data" / "reference" / "price_indices.parquet"
U = "https://aramis.group/wp-content/uploads/"
# release date, kind, PDF. The 9 December 2021 results release repeats the 9 November one's tables and is left out.
RELEASES = [
    ("2021-07-29", "q3", "2025/04/5d02711e-f90d-47fd-a1f6-b2777d9c25ca.pdf"),
    ("2021-11-09", "fy", "2025/04/a14cbcff-1c56-4e56-9f40-24fe3af892dd.pdf"),
    ("2022-01-27", "q1", "2025/04/53e91ad3-326e-4180-990f-e0fd01c55661-1.pdf"),
    ("2022-05-16", "h1", "2025/04/ed74ffc4-0dc3-4bdc-8e6d-b092b7a9c0b0.pdf"),
    ("2022-07-26", "q3", "2025/04/ee883c44-d3cc-4d1f-96ff-627e25912382.pdf"),
    ("2022-12-01", "fy", "2025/04/44478870-47b6-469f-80aa-f4048d90e39a.pdf"),
    ("2023-01-25", "q1", "2025/04/20bdd520-2588-4419-99fa-cfec4b841f8a.pdf"),
    ("2023-05-24", "h1", "2025/04/30da2f26-d9ee-4159-81f7-8a2439c90ed4.pdf"),
    ("2023-07-17", "q3", "2025/04/4a74e7b3-ca2f-4fc7-be44-b6078f229d37.pdf"),
    ("2023-11-28", "fy", "2025/04/51da2e9c-e7e6-4320-b07c-7f7fed7645f7.pdf"),
    ("2024-01-24", "q1", "2025/04/92299ddf-77d3-430f-99bd-875ae0519493.pdf"),
    ("2024-05-27", "h1", "2025/04/91d445a1-870a-4553-b9eb-c8ae39197206.pdf"),
    ("2024-07-23", "q3", "2025/04/7728e56a-ada5-4a80-89db-f589124d5126.pdf"),
    ("2024-11-26", "fy", "2025/04/2ec89af7-796e-4232-8034-7e73dc2e354d.pdf"),
    ("2025-01-28", "q1", "2025/04/ad768879-2c37-44a8-b90b-baf2cdb5b749.pdf"),
    ("2025-05-19", "h1", "2025/08/faacc0f2-a03f-4891-bf11-ae4941b9bbef.pdf"),
    ("2025-07-24", "q3", "2025/08/b0ec686d-af6f-4a68-a5f6-3a7575720a46.pdf"),
    ("2025-11-26", "fy", "2025/11/press-release-aramis-group-2025-annual-results.pdf"),
    ("2026-01-27", "q1", "2026/01/f107d0c2-ef86-419a-80bc-f699907a4df4.pdf"),
    ("2026-05-19", "h1", "2026/08/6b69251a-0919-4bf9-ba20-cf56f0b59b05.pdf"),
    ("2026-07-23", "q3", "2026/08/6451275b-fa9d-4945-905d-bf35dcdeda4e.pdf"),
]
ROWS = {"refurb": r"Refurbished(?: cars| vehicles)?", "prereg": r"Pre-registered(?: cars| vehicles)?",
        "b2b": r"(?:Total )?B2B", "b2b_units": r"Total B2B volumes"}
COUNTRIES = {"FR": r"France", "BE": r"Belgium", "ES": r"Spain", "UK": r"(?:United[ -]Kingdom|UK)", "AT": r"Austria",
             "IT": r"Italy"}
NUM = r"([+-]?[\d,]+\.?\d*)"
TLS = ssl.create_default_context(cafile=certifi.where())


def text(date, kind):
    path = RAW / f"{date}_{kind}.pdf"
    if not path.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        url = U + dict((d, u) for d, _, u in RELEASES)[date]
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        path.write_bytes(urllib.request.urlopen(req, context=TLS).read())
    logging.disable(logging.CRITICAL)  # pypdf's font warnings
    lines = "\n".join(p.extract_text() or "" for p in PdfReader(path).pages).split("\n")
    return [re.sub(r"\s+", " ", x).strip() for x in lines]


def numbers(line, label):
    m = re.match(rf"^{label} ((?:{NUM}%? ?)+)$", line)
    if not m:
        return None
    vals = [v for v in m.group(1).split() if not v.endswith("%")]
    return [float(v.replace(",", "")) for v in vals]


def parse(date, kind):
    """The current-period figures (first number of each row) and the prior-year column where the layout is simple.

    Q3 releases carry a 9M block after the quarter; the first full-year release carries a Q4 block. The current
    period's value is the first number and the second block's the third (percentages dropped). From FY2022 on, pro
    forma and reported current values are equal. In the FY2021 release they are not, so its full-year figure is pro
    forma; it is never used, because that year's Q4 is read directly (pro forma equals reported for Q4)."""
    lines = text(date, kind)
    found = {}
    for key, label in {**ROWS, **{f"rev_{c}": p for c, p in COUNTRIES.items()}}.items():
        hits = [n for n in (numbers(x, label) for x in lines) if n and len(n) >= 2]
        if key == "b2b":
            hits = [n for n in (numbers(x, label) for x in lines if not x.startswith("Total B2B volumes"))
                    if n and len(n) >= 2]
        found[key] = hits
    out = {}
    first = kind.upper()
    second = {"q3": "9M", "fy": "Q4"}.get(kind)
    blocks = [(first, 0)] + ([(second, 2)] if second else [])
    for period, i in blocks:
        rec = {}
        for key in ["refurb", "prereg"]:
            if len(found[key]) >= 2:  # units table, then revenue table
                u, r = found[key][0], found[key][1]
                if len(u) > i and len(r) > i:
                    rec[f"units_{key}"], rec[f"rev_{key}"] = u[i], r[i]
        if found["b2b"] and len(found["b2b"][0]) > i:
            rec["rev_b2b"] = found["b2b"][0][i]
        if found["b2b_units"] and len(found["b2b_units"][0]) > i:
            rec["units_b2b"] = found["b2b_units"][0][i]
        for c in COUNTRIES:
            if found[f"rev_{c}"] and len(found[f"rev_{c}"][0]) > i:
                rec[f"rev_{c}"] = found[f"rev_{c}"][0][i]
        if period == "Q4" and date != "2021-11-09":
            continue  # only the first full-year release has a Q4 block
        out[period] = rec
    # the prior-year column (second number), for the simple layouts from 2023 on
    prev = {}
    if date >= "2023":
        for key in ["refurb", "prereg"]:
            if len(found[key]) >= 2:
                prev[f"units_{key}"], prev[f"rev_{key}"] = found[key][0][1], found[key][1][1]
        if found["b2b"]:
            prev["rev_b2b"] = found["b2b"][0][1]
        if found["b2b_units"]:
            prev["units_b2b"] = found["b2b_units"][0][1]
        for c in COUNTRIES:
            if found[f"rev_{c}"]:
                prev[f"rev_{c}"] = found[f"rev_{c}"][0][1]
    return out, {first: prev}


def reported():
    """{(fiscal year, period): figures} as first reported, with the prior-year columns for the check and fallback."""
    first, later = {}, {}
    for date, kind, _ in RELEASES:
        fy = int(date[:4])
        cur, prev = parse(date, kind)
        for period, rec in cur.items():
            if rec:
                first.setdefault((fy, period), rec)
        for period, rec in prev.items():
            if rec:
                later[(fy - 1, period)] = rec
    missing = [k for k in later if k not in first]
    for k in missing:
        first[k] = later[k]
    return first, later, missing


def quarters(first):
    rows = []
    for fy in sorted({k[0] for k in first}):
        g = {p: first.get((fy, p)) for p in ["Q1", "H1", "Q3", "9M", "FY", "Q4"]}
        q = {}
        if g["Q1"]:
            q["Q1"] = g["Q1"]
        if g["H1"] and g["Q1"]:
            q["Q2"] = {k: g["H1"][k] - g["Q1"].get(k, np.nan) for k in g["H1"]}
        if g["Q3"]:
            q["Q3"] = g["Q3"]
        if g["Q4"]:
            q["Q4"] = g["Q4"]
        elif g["FY"] and g["9M"]:
            q["Q4"] = {k: g["FY"][k] - g["9M"].get(k, np.nan) for k in g["FY"]}
        for p, rec in q.items():
            rows.append({"fy": fy, "q": int(p[1]), **rec})
    d = pd.DataFrame(rows).sort_values(["fy", "q"]).reset_index(drop=True)
    # fiscal quarter -> calendar months: FY Q1 = October-December of the year before
    d["end"] = [pd.Period(f"{fy - 1}-12" if q == 1 else f"{fy}-{3 * (q - 1):02d}", "M") for fy, q in zip(d.fy, d.q)]
    d["label"] = [f"FY{fy % 100:02d} Q{q}" for fy, q in zip(d.fy, d.q)]
    return d


def hicp():
    if not HICP.exists():
        rows = []
        for geo in ["FR", "BE", "ES", "AT", "IT"]:
            url = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr?format=JSON"
                   f"&lang=EN&geo={geo}&coicop18=CP07112&unit=I25")
            d = json.load(urllib.request.urlopen(url, context=TLS))
            t, v = d["dimension"]["time"]["category"]["index"], d["value"]
            rows += [{"geo": geo, "month": m, "index": v[str(i)]} for m, i in t.items() if str(i) in v]
        pd.DataFrame(rows).to_parquet(HICP)
    h = pd.read_parquet(HICP)
    uk = pd.read_parquet(INDICES)
    uk = uk[uk.series.str.startswith("ONS CPI 07.1.1B")][["geo", "month", "index_value"]]
    uk = uk.rename(columns={"index_value": "index"})
    h = pd.concat([h, uk])
    h["month"] = pd.PeriodIndex(h.month, freq="M")
    return h.pivot_table(index="month", columns="geo", values="index")


def market(d, idx):
    """Each country's year-on-year change over the quarter's three months, weighted by Aramis's revenue there."""
    out = []
    for _, r in d.iterrows():
        months = pd.period_range(r.end - 2, r.end, freq="M")
        before = months - 12
        if not set(months) | set(before) <= set(idx.index):
            out.append((np.nan, np.nan))
            continue
        yoy = idx.loc[months].mean() / idx.loc[before].mean() - 1
        w = pd.Series({c: r.get(f"rev_{c}", np.nan) for c in COUNTRIES}).dropna()
        w = w[w > 0]
        w = w / w.sum()
        cover = w[yoy.reindex(w.index).notna()].sum()
        out.append((float((yoy.reindex(w.index) * w).sum() / cover) if cover else np.nan, float(cover)))
    return out


def own_words(first, later):
    """Aramis's own price-effect statements, as printed, beside the change in revenue per car computed for the same
    segment and period from the tables (the prior year from its first report, else the later release's column)."""
    seg = {"refurbished": "refurb", "pre-registered": "prereg", "b2b": "b2b"}
    got = []
    pat = re.compile(r"(refurbished cars? segment|pre-registered cars? segment|B2B segment|B2C)(?:[^.]|\.(?=\d)){0,300}?"
                     r"(price(?:/mix)? effect(?: of)? ([+-]?\d+(?:\.\d)?)%|impact of ([+-]\d+(?:\.\d)?)%)", re.I)
    for date, kind, _ in RELEASES:
        t = " ".join(text(date, kind)).replace("- ", "-")
        for m in pat.finditer(t):
            val = m.group(3) or m.group(4)
            s = next((v for k, v in seg.items() if m.group(1).lower().startswith(k)), None)
            fy, per = int(date[:4]), kind.upper()
            cur, old = first.get((fy, per), {}), {**later.get((fy - 1, per), {}), **first.get((fy - 1, per), {})}
            calc = ""
            if s and all(x.get(f"{a}_{s}") for x in (cur, old) for a in ("rev", "units")):
                calc = f"{100 * ((cur[f'rev_{s}'] / cur[f'units_{s}']) / (old[f'rev_{s}'] / old[f'units_{s}']) - 1):+.1f}%"
            got.append({"release": date, "period": per, "segment": m.group(1).lower(), "stated by Aramis": f"{val}%",
                        "revenue per car, computed": calc})
    return pd.DataFrame(got).drop_duplicates()


def main():
    first, later, missing = reported()
    d = quarters(first)
    d["asp_refurb"] = d.rev_refurb * 1e6 / d.units_refurb
    d["asp_prereg"] = d.rev_prereg * 1e6 / d.units_prereg
    by = {(x.fy, x.q): x for x in d.itertuples()}  # the same quarter a year earlier
    d["yoy_refurb"] = [r.asp_refurb / by[(r.fy - 1, r.q)].asp_refurb - 1 if (r.fy - 1, r.q) in by else np.nan
                       for r in d.itertuples()]
    d["yoy_prereg"] = [r.asp_prereg / by[(r.fy - 1, r.q)].asp_prereg - 1 if (r.fy - 1, r.q) in by else np.nan
                       for r in d.itertuples()]
    idx = hicp()
    mk = market(d, idx)
    d["yoy_market"], d["market_cover"] = [m[0] for m in mk], [m[1] for m in mk]
    no_fr = d.copy()
    no_fr["rev_FR"] = 0  # France's index prices smoothed Argus guide values (X7): the same weights without it
    d["yoy_market_xfr"] = [m[0] for m in market(no_fr, idx)]

    # checks: sane prices, and each later release's prior-year column against the figure first reported
    assert d.asp_refurb.between(5_000, 40_000).all(), d[["label", "asp_refurb"]]
    diffs = []
    for (fy, p), rec in later.items():
        if (fy, p) in first and (fy, p) not in missing:
            for k, v in rec.items():
                f0 = first[(fy, p)].get(k)
                if f0:
                    diffs.append({"period": f"FY{fy % 100:02d} {p}", "item": k, "first": f0, "later": v,
                                  "diff %": 100 * (v / f0 - 1)})
    diffs = pd.DataFrame(diffs)
    big = diffs[diffs["diff %"].abs() > 0.5]
    # a figure filled from a later release must also appear in the original release's own text
    kinds = {date: kind for date, kind, _ in RELEASES}
    filled_seen = filled_total = 0
    for fy, period in missing:
        date = next(dt for dt, k in kinds.items() if int(dt[:4]) == fy and k.upper() == period)
        body = " ".join(text(date, kinds[date])).replace(",", "")
        for k, v in first[(fy, period)].items():
            if k.startswith("rev_"):
                filled_total += 1
                filled_seen += f"{v:.1f}" in body

    both = d.dropna(subset=["yoy_refurb", "yoy_market"])
    corr = both.yoy_refurb.corr(both.yoy_market)
    late = both[both.fy >= 2023]
    corr_late = late.yoy_refurb.corr(late.yoy_market)
    lags = pd.DataFrame([{"index taken k quarters later": k,
                          "all six countries": f"{d.yoy_refurb.corr(d.yoy_market.shift(-k)):.2f}",
                          "without France": f"{d.yoy_refurb.corr(d.yoy_market_xfr.shift(-k)):.2f}"}
                         for k in range(-1, 5)])
    best_all = max(range(-1, 5), key=lambda k: d.yoy_refurb.corr(d.yoy_market.shift(-k)))
    best_xfr = max(range(-1, 5), key=lambda k: d.yoy_refurb.corr(d.yoy_market_xfr.shift(-k)))
    r_best_all = d.yoy_refurb.corr(d.yoy_market.shift(-best_all))
    r_best_xfr = d.yoy_refurb.corr(d.yoy_market_xfr.shift(-best_xfr))
    boom = both[both.fy == 2022]
    recent = both[both.fy >= 2025]

    def pct(x, dp=1):
        return "" if pd.isna(x) else f"{100 * x:+.{dp}f}%"

    tab = pd.DataFrame({
        "fiscal quarter": d.label, "months": [f"{(e - 2).strftime('%b %Y')}-{e.strftime('%b %Y')}" for e in d.end],
        "refurbished cars sold": d.units_refurb.map("{:,.0f}".format),
        "realised price per refurbished car (EUR)": d.asp_refurb.map("{:,.0f}".format),
        "its change on a year": d.yoy_refurb.map(pct),
        "official indices, Aramis's country weights": d.yoy_market.map(pct),
        "the same without France": d.yoy_market_xfr.map(pct),
        "pre-registered: price change on a year": d.yoy_prereg.map(pct)})
    words = own_words(first, later)
    ok = words[words["revenue per car, computed"] != ""]
    agree = (ok["stated by Aramis"].str.rstrip("%").astype(float)
             - ok["revenue per car, computed"].str.rstrip("%").astype(float)).abs().max()

    OUT.write_text(f"""# X10 part 3a: the group's own realised used-car prices (Aramis Group)

Aramis Group is 60.54% owned by Stellantis (Stellantis 20-F FY2025, Exhibit 8.1:
https://www.sec.gov/Archives/edgar/data/1605484/000160548426000021/exhibit8120251231-subsidia.htm). Its releases give
what the group's own used-car retailer was paid per car, every quarter since its 2021 IPO: the only realised European
used-car prices we have. Here they are set against the official indices that leak 3 and X6 measure the level on.

**The group's own realised prices move with the official indices; France's index lags them.** Over {len(both)}
quarters the correlation of the two year-on-year changes is {corr:.2f} ({corr_late:.2f} without the 2022 boom).
With all six countries it is highest, {r_best_all:.2f}, against the indices {best_all} quarters later. Without France
it is highest, {r_best_xfr:.2f}, {'in the same quarter' if best_xfr == 0 else f'{best_xfr} quarters later'}. France's index prices smoothed Argus guide values (X7),
and it carries about half of Aramis's revenue.

**The realised price swings wider than the indices.** In the 2022 boom it rose {pct(boom.yoy_refurb.min())} to
{pct(boom.yoy_refurb.max())} on a year, while the indices rose {pct(boom.yoy_market.min())} to
{pct(boom.yoy_market.max())} ({pct(boom.yoy_market_xfr.min())} to {pct(boom.yoy_market_xfr.max())} without France).
It turned down while the indices were still rising. Since FY2025 it has slipped in every quarter
({pct(recent.yoy_refurb.min())} to {pct(recent.yoy_refurb.max())}), while the indices moved between
{pct(recent.yoy_market.min())} and {pct(recent.yoy_market.max())}. Part of that is Aramis's own mix: it says it
moved toward cheaper price ranges.

**The price change computed here is Aramis's own "price effect".** For all {len(ok)} statements that can be
recomputed from the tables, revenue per car reproduces the stated effect within {agree:.1f} points ("Aramis's own
words").

{md_table(tab)}

The indices are Eurostat's HICP for second-hand cars (France, Belgium, Spain, Austria, Italy; COICOP 2018, 2025=100)
and ONS's for the UK. Each is averaged over the quarter's three months and set against the same months a year
earlier, then weighted by Aramis's revenue by country that quarter. France's index prices Argus guide values and
barely moves; the UK's is built from Auto Trader adverts (X10 part 1).

{md_table(lags)}

A positive k means the realised price leads the index. With only {len(both)} quarters, the lag is a pattern, not a
precise estimate.

## Aramis's own words on price

Where a release separates a price effect from volume, it says so:

{md_table(words) if len(words) else "(none found)"}

These separate price from volume, not always from mix: some are labelled "price/mix", and the UK's 2026 fall came
with a move to cheaper price ranges.

## What it means for the solution

- **The level that leak 3 prices is the group's own.** Its own used-car business sees the same market level the
  official indices show, in sign and timing outside France.
- **The realised price moves more than the index, in both directions.** An index-based level shock can understate
  what the group realises, which fits X7's reading of X6's charge as a floor.
- **A re-mark on France's index would react late.** The group's own realised retail price, published every quarter,
  is an earlier signal for the French book. X6's re-mark can take it as a second input, with the mix caveat below.
- **The ledger can be checked against the group's own disclosures.** Before a ledger mark-to-market of the resale book
  is trusted, it should reproduce these quarterly realised prices. This is a Phase 1 reconciliation test that needs
  no new data.

## Checks

- **Prices are sane:** every quarter's realised price per refurbished car lies between EUR 5,000 and 40,000.
- **Figures don't drift between releases.** {len(diffs)} prior-year figures in later releases were checked against the
  figure first reported. {len(big)} differ by more than 0.5%{': ' + ', '.join(f"{r['period']} {r['item']} ({r['diff %']:+.1f}%)" for _, r in big.iterrows()) if len(big) else ''}.
- **Filled from a later release:** {', '.join(f'FY{k[0] % 100:02d} {k[1]}' for k in missing) or 'none'}. Its tables
  are printed as images, so its figures are the later release's prior-year column. {filled_seen} of its
  {filled_total} revenue figures also appear in the original release's text; the rest are stated only in its
  image tables.
- **Index coverage:** the countries with an index carry {d.market_cover.min() * 100:.0f}% of Aramis's revenue or more
  in every quarter.

## Limits

- **An average price, not a like-for-like one.** It moves with Aramis's mix of countries, ages and price ranges, as
  well as the market. Units by country aren't published, so the country mix stays inside the realised price.
- **A retailer's prices, not a lessor's.** Aramis sells refurbished used cars to consumers. The 20-F doesn't publish
  who buys the group's buy-back and lease returns. Aramis's own B2B units are published only from FY2026, too short
  for a series.
- **Quarters built from differences** (Q2 and Q4) carry any rounding in both terms.
- **About five years, one retailer.** The period holds one boom (2021-22) and one normalisation (2023-24), not a
  distribution of cycles.
""")
    print(OUT.read_text()[:2500])


if __name__ == "__main__":
    main()
