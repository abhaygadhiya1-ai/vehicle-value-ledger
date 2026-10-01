"""X2 part 4: the cross-check outside the Netherlands. German short-term registrations by brand, 2007-2023.

Germany's KBA publishes, every year and by brand, how many new passenger cars were deregistered within 30 days of
first registration (Kurzzulassungen). A car a dealer registers to reach a target and then deregisters to sell on,
often abroad, shows up here. It is a different measure from part 1's month-end share, in a different country, so if
it tells the same story, the story is not an artefact of Dutch taxes or of our date field.

Two questions, as in part 2:
  1. Level: do the group's families (PSA: Peugeot, Citroen, DS; Opel; FCA: Fiat, Alfa Romeo, Jeep, Lancia) have more
     short-term registrations than the rest of the market, before and after the merger?
  2. Change: did a family's gap to the rest of the market move when it met a new owner (Opel from 2018, the first
     full year after PSA's takeover on 1 August 2017; everyone from 2021, Stellantis)? The estimate is a
     difference-in-differences of annual shares over W years either side, and the placebo p is the share of all other
     break years whose estimate is at least as large in absolute size. With annual data the placebo set is small, so
     the p-values are coarse.

"Rest of the market" is KBA's own total minus every brand of the group, including Maserati. Abarth is not listed
separately by KBA and sits in its "other" line. Figures are KBA's, read from its annual Kurzbericht pages; nothing is
synthetic. Data licence Germany, attribution, version 2.0 (dl-de/by-2-0).

Source: https://www.kba.de/DE/Statistik/Fahrzeuge/Neuzulassungen/Kurzzulassungen/kurzzulassungen_node.html
Usage: .venv/bin/python analysis/merger_kba.py   (parsed tables are cached in data/, private)
"""
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_unified import MAKE_ALIASES, md_table, norm_name  # noqa: E402

OUT = HERE / "merger_kba_report.md"
CACHE = HERE.parent / "data" / "x2_kba_kurzzulassungen.csv"
URL = ("https://www.kba.de/DE/Statistik/Fahrzeuge/Neuzulassungen/Kurzzulassungen/{y}/"
       "{y}_n_kurzzulassungen_kurzbericht.html?nn=838512")
YEARS = range(2007, 2024)
FAMILY = {"peugeot": "PSA", "citroen": "PSA", "ds": "PSA", "opel": "Opel",
          "fiat": "FCA", "alfa romeo": "FCA", "jeep": "FCA", "lancia": "FCA", "maserati": "FCA niche"}
EVENTS = [("Opel joins PSA", 2018, "Opel"), ("Stellantis formed", 2021, "FCA"), ("Stellantis formed", 2021, "PSA"),
          ("Stellantis formed", 2021, "Opel")]
WINDOWS = (3, 2)


def fetch():
    """KBA's brand table for every year it publishes, as one long table; cached."""
    if CACHE.exists():
        return pd.read_csv(CACHE)
    rows = []
    for y in YEARS:
        r = requests.get(URL.format(y=y), headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
        if r.status_code != 200:
            print(f"{y}: HTTP {r.status_code}, skipped")
            continue
        t = pd.concat(pd.read_html(io.StringIO(r.text), decimal=",", thousands="."), ignore_index=True)
        t = t.iloc[:, [0, 5, 6]]
        t.columns = ["brand", "short", "new"]
        rows.append(t.assign(year=y))
    out = pd.concat(rows, ignore_index=True)
    out.to_csv(CACHE, index=False)
    return out


def shares(k):
    """Per year and family: short-term registrations, new registrations, and the short-term share (%)."""
    total = k[k["brand"].str.lower().eq("insgesamt")].set_index("year")[["short", "new"]]
    brands = k[~k["brand"].str.lower().eq("insgesamt")].copy()
    sums = brands.groupby("year")[["short", "new"]].sum()
    assert (sums == total.loc[sums.index]).all().all(), "brand rows do not add up to KBA's total"
    brands["family"] = norm_name(brands["brand"]).replace(MAKE_ALIASES).map(FAMILY)
    fam = brands.dropna(subset=["family"]).groupby(["year", "family"])[["short", "new"]].sum()
    group = fam.groupby("year").sum()
    other = (total - group.reindex(total.index, fill_value=0)).assign(family="other").set_index("family", append=True)
    t = pd.concat([fam, other]).sort_index()
    t["share (%)"] = 100 * t["short"] / t["new"]
    return t


def did(t, family, year, w):
    """Change in the family's share minus the change in the rest of the market's, w years either side of `year`."""
    s = t["share (%)"].unstack("family")
    if family not in s:
        return None
    before, after = s.loc[year - w:year - 1], s.loc[year:year + w - 1]
    if len(before.dropna(subset=[family])) < w or len(after.dropna(subset=[family])) < w:
        return None
    pooled = t.unstack("family")

    def share(years, f):
        p = pooled.loc[years]
        return 100 * p[("short", f)].sum() / p[("new", f)].sum()

    b, a = list(before.index), list(after.index)
    return (share(a, family) - share(b, family)) - (share(a, "other") - share(b, "other"))


def main():
    k = fetch()
    t = shares(k)
    years = sorted(t.index.get_level_values("year").unique())
    wide = t["share (%)"].unstack("family")[["PSA", "Opel", "FCA", "other"]].round(2).reset_index()
    wide.columns = ["year"] + [f"{c} (%)" for c in wide.columns[1:]]
    cars = t["new"].unstack("family")[["PSA", "Opel", "FCA", "other"]].fillna(0).astype(int)
    cars.columns = [f"{c}: new cars" for c in cars.columns]
    wide = wide.merge(cars.reset_index(), on="year")

    rows = []
    for name, year, family in EVENTS:
        row = {"test": f"{name}: {family}", "event": name, "first year after": year, "family": family}
        for w in WINDOWS:
            est = did(t, family, year, w)
            placebo = [did(t, family, y, w) for y in years if y != year]
            placebo = np.array([x for x in placebo if x is not None])
            row[f"{w} years: estimate (points)"] = round(est, 2) if est is not None else None
            row[f"{w} years: placebo p"] = round(float(np.mean(np.abs(placebo) >= abs(est))), 2) \
                if est is not None and len(placebo) else None
            row[f"{w} years: placebo breaks"] = len(placebo)
        rows.append(row)
    events = pd.DataFrame(rows)
    eras = [("2007 to 2020, before the merger", 2007, 2020), ("2021 to 2022, merged", 2021, 2022),
            ("2023, contracts ended", 2023, 2023)]
    p = t.unstack("family")
    pooled = pd.DataFrame([{"era": label, **{f"{f} (%)": round(100 * p.loc[a:b, ("short", f)].sum()
                                                             / p.loc[a:b, ("new", f)].sum(), 2)
                                              for f in ["PSA", "Opel", "FCA", "other"]}}
                           for label, a, b in eras])

    OUT.write_text(f"""# X2 part 4: German short-term registrations by brand, {years[0]}-{years[-1]}

_Generated by `analysis/merger_kba.py` from KBA's annual Kurzzulassungen tables (dl-de/by-2-0). Real data, not
synthetic._

A short-term registration is a new car deregistered within 30 days of first registration: the German footprint of a
dealer registering a car to reach a target and selling it on. **Check passed:** in every year the brand rows add up to
KBA's own total. "Other" is KBA's total minus every group brand. Years without a KBA page are absent.

## Short-term registrations as a share of new cars, by family (%)

{md_table(wide)}

## Pooled by era (%)

Short-term registrations over new cars, pooled over each era's years. The dealer contracts ended in June 2023.

{md_table(pooled)}

## Did a family's gap to the rest of the market move?

Difference-in-differences of annual shares, W years either side of the first year after the event. The placebo p is
the share of all other break years whose estimate is at least as large in absolute size; with annual data it is
coarse.

{md_table(events)}
""")
    print(md_table(wide[["year", "PSA (%)", "Opel (%)", "FCA (%)", "other (%)"]]))
    print(md_table(events))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
