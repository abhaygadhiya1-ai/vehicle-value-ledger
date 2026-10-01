"""X2 part 6: is it fuel? The month-end pattern within fuel types.

Part 3 found that body mix explains almost none of the group's month-end gap, but fuel type was not in that dataset.
Fuel could matter in the Netherlands: electric cars were pulled forward by subsidy windows and company-car tax
changes, and some electric brands deliver in waves. A family selling a different fuel mix would show a different
month-end share without registering any differently. So each new car is joined to its fuel type by plate, and part
3's Kitagawa split is repeated with fuel classes in place of body types.

Fuel classes, from RDW's fuel table (one row per plate and fuel): plug-in hybrid (any row OVC-HEV), hybrid (NOVC-HEV),
electric (electricity with no hybrid class), diesel, and petrol and other (the rest: petrol, and a few LPG, CNG and
hydrogen cars). Checked: the fuel panel adds up to part 1's brand-by-day panel, within the cars that left the register
between the two downloads.

Registrations are real; nothing here is synthetic.

Source: RDW open data (public domain): Gekentekende voertuigen, https://opendata.rdw.nl/resource/m9d7-ebf2.json, for
plate, make and first-registration day (part 1's population), and Gekentekende voertuigen brandstof,
https://opendata.rdw.nl/resource/8ys7-d773.json, for fuel. Plates are streamed and joined in memory; only the brand x
fuel x month panel is cached, in data/ (private).
Usage: .venv/bin/python analysis/merger_fuel.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from build_unified import MAKE_ALIASES, md_table, norm_name  # noqa: E402
from merger_composition import decompose  # noqa: E402
from merger_fingerprint import FAMILY, WHERE  # noqa: E402
from self_registration import END_DAYS, PAGE, RDW_URL, position  # noqa: E402

OUT = HERE / "merger_fuel_report.md"
CACHE = HERE.parent / "data" / "x2_rdw_brand_fuel.parquet"
FUEL_URL = "https://opendata.rdw.nl/resource/8ys7-d773.json"
FUELS = ["petrol and other", "diesel", "hybrid", "plug-in hybrid", "electric"]


def pages(url, select, where):
    """Every row of a query, paged by plate (keyset paging: each page starts after the last plate seen, which stays
    fast where large offsets do not)."""
    out, last = [], ""
    while True:
        r = requests.get(url, params={"$select": select, "$where": f"({where}) AND kenteken > '{last}'",
                                      "$order": "kenteken", "$limit": PAGE}, timeout=900)
        r.raise_for_status()
        out.append(pd.DataFrame(r.json()))
        if len(out[-1]) < PAGE:
            return pd.concat(out, ignore_index=True)
        last = out[-1]["kenteken"].iloc[-1]


def fuel_of_plate():
    """Each plate with an electricity or diesel row, and its fuel class. Plates absent here are petrol and other."""
    f = pages(FUEL_URL, "kenteken, brandstof_omschrijving, klasse_hybride_elektrisch_voertuig",
              "brandstof_omschrijving in ('Elektriciteit', 'Diesel')")
    cls = f.get("klasse_hybride_elektrisch_voertuig", pd.Series(index=f.index, dtype=object))
    g = pd.DataFrame({"kenteken": f["kenteken"], "phev": cls.eq("OVC-HEV"), "hev": cls.eq("NOVC-HEV"),
                      "bev": f["brandstof_omschrijving"].eq("Elektriciteit") & cls.isna(),
                      "diesel": f["brandstof_omschrijving"].eq("Diesel")}).groupby("kenteken").any()
    return pd.Series(np.select([g["phev"], g["hev"], g["bev"], g["diesel"]],
                               ["plug-in hybrid", "hybrid", "electric", "diesel"], "petrol and other"), index=g.index)


def fuel_panel():
    """New cars per brand, fuel class and month, and those first registered in the month's last END_DAYS days."""
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    cars = pages(RDW_URL, "kenteken, merk, datum_eerste_toelating_dt", WHERE)
    fuel = fuel_of_plate()
    cars["fuel"] = cars["kenteken"].map(fuel).fillna("petrol and other")
    day = pd.to_datetime(cars["datum_eerste_toelating_dt"])
    cars["m"] = day.dt.to_period("M").astype(str)
    cars["end"] = position(day, END_DAYS) != "other days"
    p = cars.groupby(["merk", "fuel", "m"]).agg(n=("kenteken", "size"), end=("end", "sum")).reset_index()
    p.to_parquet(CACHE, index=False)
    return p


def main():
    b = fuel_panel()
    b["family"] = norm_name(b["merk"]).replace(MAKE_ALIASES).map(FAMILY).fillna("other")
    b["year"] = pd.PeriodIndex(b["m"], freq="M").year

    # the fuel panel is part 1's population, downloaded later: cars that left the register since may be missing
    part1 = pd.read_parquet(HERE.parent / "data" / "x2_rdw_brand_day.parquet")
    n1, n6 = int(part1["n"].sum()), int(b["n"].sum())
    assert 0 <= n1 - n6 < 0.005 * n1, (n1, n6)

    pooled = pd.DataFrame([decompose(b, f, "fuel", "fuel type") for f in ["PSA", "Opel", "FCA"]])
    by_year = pd.DataFrame([{"year": y, **decompose(b[b["year"] == y], f, "fuel", "fuel type")}
                            for y in sorted(b["year"].unique()) for f in ["PSA", "Opel", "FCA"]])
    year_rows = pd.DataFrame({"year": sorted(b["year"].unique())})
    for f in ["PSA", "Opel", "FCA"]:
        w = by_year[by_year["family"] == f].set_index("year")
        year_rows[f"{f}: gap (points)"] = year_rows["year"].map(w["gap (points)"]).round(2)
        year_rows[f"{f}: within (points)"] = year_rows["year"].map(w["within fuel type (points)"]).round(2)
        year_rows[f"{f}: mix (points)"] = year_rows["year"].map(w["fuel mix (points)"]).round(2)

    t = b.groupby(["fuel", "family"])[["n", "end"]].sum()
    rates = (100 * t["end"] / t["n"]).unstack("family")[["PSA", "Opel", "FCA", "other"]].reindex(FUELS)
    fuel_rows = rates.round(2).reset_index()
    fuel_rows.insert(1, "cars", fuel_rows["fuel"].map(b.groupby("fuel")["n"].sum()).map("{:,}".format))

    mix = b.groupby(["family", "fuel"])["n"].sum().unstack("fuel").reindex(columns=FUELS).fillna(0)
    mix = (100 * mix.div(mix.sum(axis=1), axis=0)).round(1).reindex(["PSA", "Opel", "FCA", "FCA niche", "other"])
    mix_rows = mix.reset_index()

    fmt = {c: 2 for c in pooled.columns if pooled[c].dtype.kind == "f"}
    OUT.write_text(f"""# X2 part 6: is it fuel? The month-end pattern within fuel types

_Generated by `analysis/merger_fuel.py`. Real RDW register data (public domain), not synthetic._

**Check passed:** the fuel panel holds {n6:,} cars against part 1's {n1:,}: the same population, downloaded later,
short only by cars that left the register in between. Month end means the last {END_DAYS} calendar days. Fuel
classes come from RDW's fuel table, joined by plate.

## Fuel type: how much of each family's month-end gap is mix, and how much is within the same fuel type (2014-2025)

The gap to other brands is split into the part that comes from registering more at month ends *within the same fuel
type* and the part that comes from selling a different *mix* of fuel types (Kitagawa, with other brands' rates as the
reference). Buyer type and price are still not in the data, so the within part can hide those mixes.

{md_table(pooled.round(fmt))}

## By year (points)

{md_table(year_rows)}

## Month-end share by fuel type and family (%, 2014-2025)

{md_table(fuel_rows)}

## Fuel mix by family (% of each family's new cars, 2014-2025)

{md_table(mix_rows)}
""")
    print(md_table(pooled.round(fmt)))
    print(md_table(fuel_rows))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
