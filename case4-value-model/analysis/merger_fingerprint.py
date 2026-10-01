"""X2 part 1: the merger's fingerprint in the Dutch register. When in the month did former-PSA and former-FCA brands
register their new cars, before and after the merger?

A dealer that registers cars in its own name to reach a volume target does it in the last days of the period. So a
brand's share of new cars first registered in a month's last days is a proxy for tactical registrations; the cars
registered then change keeper unusually fast (`self_registration_report.md`). This part builds the panel and
describes it. Part 2 tests whether the gap between the families moved when the two incentive regimes met.

Population: every passenger car first registered new in the Netherlands (first admission = first Dutch
registration), 2014-2025, counted per brand and day by RDW's own server. Brand families:
  PSA         Peugeot, Citroen, DS: PSA throughout
  Opel        GM until PSA bought it in 2017, so shown apart
  FCA         Fiat, Abarth, Alfa Romeo, Jeep, Lancia: FCA's mass-market brands with Dutch dealer networks
  FCA niche   Chrysler, Dodge, Ram, Maserati: mostly independent importers or a separate network, so shown apart
  other       every other brand: the comparison group
"Month end" and "quarter end" are the last 3 calendar days, as in `self_registration.py`. Calendar days are the same
for every brand, so families are always compared on the same days.

**Limits.**
  - The register holds the cars still in it, so older cohorts are survivors and their counts fall short of the sales
    published at the time. A share by registration day is biased only if a car's removal depends on the day it was
    registered.
  - Registration timing is a proxy. A month-end peak can also come from deliveries, tax deadlines or fleet orders,
    which is why families are compared with each other and with other brands, never with zero.
  - Registrations are real; nothing here is synthetic.

Source: RDW open data, Gekentekende voertuigen (public domain), https://opendata.rdw.nl/resource/m9d7-ebf2.json,
aggregated server-side. The brand-by-day panel is cached in data/ (private) for the later parts.
Usage: .venv/bin/python analysis/merger_fingerprint.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from build_unified import MAKE_ALIASES, md_table, norm_name  # noqa: E402
from check_assumptions import located  # noqa: E402
from self_registration import AGENCY_START, END_DAYS, is_group, paged, position  # noqa: E402

OUT = HERE / "merger_fingerprint_report.md"
CACHE = HERE.parent / "data" / "x2_rdw_brand_day.parquet"
FIRST, LAST = 2014, 2025
WHERE = (f"voertuigsoort='Personenauto' AND datum_eerste_toelating_dt >= '{FIRST}-01-01T00:00:00.000' "
         f"AND datum_eerste_toelating_dt < '{LAST + 1}-01-01T00:00:00.000' "
         "AND datum_eerste_tenaamstelling_in_nederland_dt = datum_eerste_toelating_dt")
FAMILY = {"peugeot": "PSA", "citroen": "PSA", "ds": "PSA", "opel": "Opel",
          "fiat": "FCA", "abarth": "FCA", "alfa romeo": "FCA", "jeep": "FCA", "lancia": "FCA",
          "chrysler": "FCA niche", "dodge": "FCA niche", "ram": "FCA niche", "maserati": "FCA niche"}
FAMILIES = ["PSA", "Opel", "FCA", "FCA niche", "other"]
# eras for the brand table; part 2 tests the dates themselves
ERAS = [("2014-2016", "2014-01-01"), ("2017-2020", "2017-01-01"), ("2021 to 3 September 2023", "2021-01-01"),
        ("4 September 2023 to 2025", str(AGENCY_START.date()))]


def panel():
    """New cars per brand and day. Cached, because the later parts reuse it."""
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    p = paged("merk, date_trunc_ymd(datum_eerste_toelating_dt) AS d, count(1) AS n", WHERE, "d, merk", "merk, d")
    p["d"], p["n"] = pd.to_datetime(p["d"]), pd.to_numeric(p["n"])
    p.to_parquet(CACHE, index=False)
    return p


def shares(p, keys):
    """Per group: cars, and the shares first registered at a month end and at a quarter end."""
    t = p.groupby(keys + ["position"])["n"].sum().unstack("position", fill_value=0)
    out = pd.DataFrame({"cars": t.sum(axis=1)})
    out["month end (%)"] = 100 * (t["quarter end"] + t["other month end"]) / out["cars"]
    out["quarter end (%)"] = 100 * t["quarter end"] / out["cars"]
    return out


def classified():
    """The panel with each row's brand, family, position in the month and year: shared with the later parts."""
    p = panel()
    brand = norm_name(p["merk"]).replace(MAKE_ALIASES)
    p["family"] = brand.map(FAMILY).fillna("other")
    p["brand"] = brand
    p["position"] = position(p["d"], END_DAYS)
    p["year"] = p["d"].dt.year
    return p


def main():
    p = classified()
    p["era"] = pd.cut(p["d"], [pd.Timestamp(s) for _, s in ERAS] + [pd.Timestamp(f"{LAST + 1}-01-01")],
                      right=False, labels=[e for e, _ in ERAS])

    # check: the pooled group-brand figure of self_registration.py, from its own report
    mine = p[(p["d"] >= "2022-01-01") & (p["d"] < AGENCY_START)]
    got = shares(mine.assign(g=np.where(is_group(mine["merk"]), "group brands", "other brands")), ["g"])
    report = (HERE / "self_registration_report.md").read_text()
    for g in ["group brands", "other brands"]:
        want = float(located(report, f"share registered in a month's last days, before the agency model (%) >> {g}")[0])
        assert abs(got.loc[g, "month end (%)"] - want) < 0.005, (g, got.loc[g, "month end (%)"], want)

    by_year = shares(p, ["year", "family"]).reset_index()
    wide = by_year.pivot(index="year", columns="family")
    year_rows = pd.DataFrame({"year": wide.index})
    for f in FAMILIES:
        year_rows[f"{f}: cars"] = wide[("cars", f)].fillna(0).astype(int).map("{:,}".format).to_numpy()
    for f in FAMILIES:
        year_rows[f"{f}: month end (%)"] = wide[("month end (%)", f)].round(2).to_numpy()
    quarter_rows = pd.DataFrame({"year": wide.index})
    for f in FAMILIES:
        quarter_rows[f"{f}: quarter end (%)"] = wide[("quarter end (%)", f)].round(2).to_numpy()

    group_brands = p[p["family"].isin(["PSA", "Opel", "FCA"])]
    by_brand = shares(group_brands, ["family", "brand", "era"]).reset_index()
    big = by_brand.groupby("brand")["cars"].transform("sum") >= 1000
    by_brand = by_brand[big]
    brand_rows = by_brand.pivot(index=["family", "brand"], columns="era", values="month end (%)").round(2)
    brand_cars = by_brand.pivot(index=["family", "brand"], columns="era", values="cars").fillna(0).astype(int)
    brand_rows.columns = [f"{c}: month end (%)" for c in brand_rows.columns]
    brand_cars.columns = [f"{c}: cars" for c in brand_cars.columns]
    brand_rows = brand_cars.join(brand_rows).reset_index()

    era_rows = shares(p, ["era", "family"]).reset_index()
    era_rows["era"] = era_rows["era"].astype(str)
    era_rows = era_rows.pivot(index="era", columns="family", values="month end (%)").round(2) \
        .reindex([e for e, _ in ERAS])[FAMILIES].reset_index()
    era_rows.columns = ["era"] + [f"{f}: month end (%)" for f in FAMILIES]

    OUT.write_text(f"""# X2 part 1: when in the month the group's brands register their cars, 2014-2025

_Generated by `analysis/merger_fingerprint.py`. Real RDW register data (public domain), not synthetic._

**Population:** {p['n'].sum():,} passenger cars first registered new in the Netherlands, {FIRST}-{LAST}, counted per
brand and day. Month end and quarter end mean the last {END_DAYS} calendar days. A high month-end share is a proxy for
tactical registrations at target deadlines, not proof of them. See the script's docstring for the limits: older
cohorts are survivors, and a peak can have other causes.

**Check passed:** for January 2022 to June 2023 this panel reproduces the group-brand and other-brand month-end
shares of `self_registration_report.md`, read from that report.

## Month-end share by family and era

Share of each family's new cars first registered in the last {END_DAYS} days of a month (%). The eras are
descriptive; part 2 tests the dates.

{md_table(era_rows)}

## By year: cars and month-end share

{md_table(year_rows)}

## By year: quarter-end share (%)

{md_table(quarter_rows)}

## By brand and era (brands with at least 1,000 cars)

{md_table(brand_rows)}
""")
    print(md_table(era_rows))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
