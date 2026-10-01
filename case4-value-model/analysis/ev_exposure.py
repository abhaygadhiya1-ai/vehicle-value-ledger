"""X9 part 4: how much of the group's book is electric? The group's powertrain mix from the EU CO2 register.

The EU CO2 monitoring register (EEA DISCODATA) records every new car registered in the EU, Norway and Iceland by
Member State, manufacturer, make, fuel type (Ft) and fuel mode (Fm). Fuel mode E is a battery-electric car, P a
plug-in hybrid (petrol or diesel), H a hybrid that does not plug in; the rest burn fuel. The group is its legacy makes
as in X8 (`merger_diversification.family`: Peugeot, Citroen, DS, Opel, Vauxhall; Fiat, Abarth, Lancia, Alfa Romeo,
Jeep, Maserati, Dodge, Chrysler, RAM). Final data for 2019 to 2024 (2019-21 from the `latest` table, then one table
per year), provisional for 2025. Duplicate records and rows with no Member State are dropped, as in X8.

What it gives: the group's battery-electric and plug-in shares of its registrations each year, beside the whole
market's; the same by market for the latest final year; and the share on the two books the case's leak 3 and X6
price. Leak 3's book is the buy-back payables due within a year: cars sold with a buy-back commitment in the last year
or so, so the latest years' mix. A registrations mix is a proxy: the book's buyers and mix are not published (the
20-F names only the group's own leasing and rental joint ventures; most of the book is due within a year, a rental
fleet's term).

Check: the group's 2019 registrations by market reproduce X8's pull exactly (the same register, without the fuel split).

Usage: .venv/bin/python analysis/ev_exposure.py [--pull]   (writes analysis/ev_exposure_report.md)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
from merger_diversification import EEA_TO_PANEL, family, registrations as x8_registrations  # noqa: E402

OUT = HERE / "ev_exposure_report.md"
CACHE = HERE.parent / "data" / "reference" / "x9_eea_registrations_fuel.parquet"
EEA = "https://discodata.eea.europa.eu/sql"
# year: (table, status). Table names from the EEA datahub item for Regulation (EU) 2019/631, probed 26 September 2026.
TABLES = {2019: ("[CO2Emission].[latest].[co2cars]", "F"), 2020: ("[CO2Emission].[latest].[co2cars]", "F"),
          2021: ("[CO2Emission].[latest].[co2cars]", "F"), 2022: ("[CO2Emission].[latest].[co2cars_2022Fv26]", "F"),
          2023: ("[CO2Emission].[latest].[co2cars_2023Fv28]", "F"), 2024: ("[CO2Emission].[latest].[co2cars_2024Fv30]", "F"),
          2025: ("[CO2Emission].[latest].[co2cars_2025Pv31]", "P")}
QUERY = ("SELECT Year, MS, Mh, Mk, Ft, Fm, SUM(R) AS n FROM {table} WHERE Year = {year} AND Status = '{status}' "
         "GROUP BY Year, MS, Mh, Mk, Ft, Fm")
LATEST_FINAL = 2024
CORE = ("FR", "IT", "DE", "ES", "PL", "NL", "PT", "BE", "AT")


def pull():
    frames = []
    for year, (table, status) in TABLES.items():
        page = 1
        while True:
            r = requests.get(EEA, params={"query": QUERY.format(table=table, year=year, status=status), "p": page,
                                          "nrOfHits": 10000}, timeout=600)
            r.raise_for_status()
            rows = r.json()["results"]
            frames.append(pd.DataFrame(rows).assign(Status=status))
            if len(rows) < 10000:
                break
            page += 1
        print(f"  {year}: pulled")
    d = pd.concat(frames, ignore_index=True)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    d.to_parquet(CACHE, index=False)
    return d


def powertrain(fm):
    return {"E": "battery EV", "P": "plug-in hybrid", "H": "hybrid"}.get(str(fm).strip().upper(), "combustion")


def clean(d):
    d = d[(d["Mh"] != "DUPLICATE") & d["MS"].fillna("").ne("")].copy()
    d["market"] = d["MS"].replace(EEA_TO_PANEL)
    d["group"] = d["Mk"].map(family)
    d["powertrain"] = d["Fm"].map(powertrain)
    return d


def shares(d, by):
    t = d.pivot_table(index=by, columns="powertrain", values="n", aggfunc="sum", fill_value=0)
    total = t.sum(axis=1)
    return pd.DataFrame({"registrations": total,
                         "battery EV (%)": 100 * t.get("battery EV", 0) / total,
                         "plug-in hybrid (%)": 100 * t.get("plug-in hybrid", 0) / total})


def main():
    d = clean(pull() if "--pull" in sys.argv or not CACHE.exists() else pd.read_parquet(CACHE))
    grp = d[d["group"].isin(("PSA", "FCA"))]
    by_year = shares(grp, "Year").join(shares(d, "Year"), rsuffix=", whole market")
    by_market = shares(grp[grp["Year"] == LATEST_FINAL], "market").join(
        shares(d[d["Year"] == LATEST_FINAL], "market"), rsuffix=", whole market")
    by_market = by_market.sort_values("registrations", ascending=False)
    legacy = shares(grp[grp["Year"] == LATEST_FINAL], "group")

    # the check: 2019 by market equals X8's pull
    x8 = x8_registrations()
    x8 = x8[(x8["Mh"] != "DUPLICATE") & x8["MS"].fillna("").ne("") & (x8["Year"] == 2019)].copy()
    x8["group"] = x8["Mk"].map(family)
    a = x8[x8["group"].isin(("PSA", "FCA"))].groupby("MS")["n"].sum()
    b = grp[grp["Year"] == 2019].groupby("MS")["n"].sum()
    gap = (a.reindex(b.index.union(a.index), fill_value=0) - b.reindex(b.index.union(a.index), fill_value=0)).abs().max()
    ck = pd.DataFrame([{"check": "the group's 2019 registrations by Member State equal X8's pull (the same register)",
                        "got": f"largest difference {gap:,.0f} cars", "passes": bool(gap == 0)}])

    def fmt(t):
        t = t.copy()
        for c in t.columns:
            t[c] = t[c].map(lambda v: f"{v:,.0f}" if c.startswith("registrations") else f"{v:.1f}")
        return t

    yt = fmt(by_year).reset_index().rename(columns={"Year": "year"})
    yt["year"] = [f"{y}{' (provisional)' if TABLES[y][1] == 'P' else ''}" for y in by_year.index]
    mt = fmt(by_market.head(12)).reset_index()
    lt = fmt(legacy).reset_index().rename(columns={"group": "legacy book"})
    last = by_year.loc[LATEST_FINAL]
    heads = pd.DataFrame([
        {"figure": f"the group's battery-EV share of its registrations, {LATEST_FINAL} (%)",
         "value": f"{last['battery EV (%)']:.1f}"},
        {"figure": f"the group's plug-in hybrid share, {LATEST_FINAL} (%)", "value": f"{last['plug-in hybrid (%)']:.1f}"},
        {"figure": f"the group's battery-EV and plug-in share together, {LATEST_FINAL} (%)",
         "value": f"{last['battery EV (%)'] + last['plug-in hybrid (%)']:.1f}"},
        {"figure": f"the whole market's battery-EV share, {LATEST_FINAL} (%)",
         "value": f"{last['battery EV (%), whole market']:.1f}"},
        {"figure": f"the group's battery-EV share, {min(TABLES)} (%)", "value": f"{by_year.iloc[0]['battery EV (%)']:.1f}"},
    ])
    print(yt.to_string(index=False)); print(mt.to_string(index=False)); print(ck.to_string(index=False))
    lines = [
        "# X9 part 4: how much of the group's book is electric?",
        "",
        "Generated by `analysis/ev_exposure.py`; the method is in its docstring. New-car registrations in the EU, Norway "
        "and Iceland, EU CO2 monitoring register (EEA). The group is its legacy makes (X8).",
        "",
        "## Headline",
        "",
        md_table(heads),
        "",
        "## The group against the whole market, by year",
        "",
        md_table(yt),
        "",
        f"## By market, {LATEST_FINAL} (the group's largest twelve)",
        "",
        md_table(mt),
        "",
        f"## By legacy book, {LATEST_FINAL}",
        "",
        md_table(lt),
        "",
        "## Check",
        "",
        md_table(ck),
        "",
        "## Limits",
        "",
        "- **Registrations stand in for the books.** The buy-back book's buyers are not published beyond the group's own "
        "leasing and rental joint ventures (most of it is due within a year, a rental fleet's term), and lease cars go "
        "to companies; neither mix is published. A registration year is the car's first year; a book holds several.",
        "- **Makes, not the group's legal perimeter.** Leapmotor's European cars (a Stellantis-led joint venture) are "
        "not counted; neither are cars the group builds for others.",
        f"- **{max(TABLES)} is provisional.** The register's final data come a year later.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
