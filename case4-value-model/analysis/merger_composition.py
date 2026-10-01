"""X2 part 3: is it what they sell? Composition checks on the month-end registration pattern.

Parts 1 and 2 found that the group's brand families register two to three times more of their new cars in a month's
last 3 days than other brands, every year since 2014, and that Opel's share rose after PSA bought it. A family that
sells more of a body type which is registered at month ends anyway would show the same pattern without any tactical
registration. Two checks:

  1. Body type. The gap between each family and other brands is split, year by year, into a *mix* part (the family
     sells different body types) and a *within* part (the family registers more at month ends than other brands do
     within the same body type). Kitagawa decomposition, with other brands' month-end rate per body type as the
     reference: gap = sum_b w_f(b) (r_f(b) - r_o(b)) + sum_b (w_f(b) - w_o(b)) r_o(b).
  2. Opel's models. Opel's month-end share by model origin: models GM developed, which were on sale before and after
     PSA bought Opel, against the PSA-based models that followed. If the rise after 2017 shows in the GM models too,
     it is not a product change.

Body type is RDW's `inrichting` (hatchback, estate, MPV, sedan; the rest pooled). Fuel type, buyer type and price are
not in this dataset, so the within part can still hide a mix of those.
Registrations are real; nothing here is synthetic.

Source: RDW open data, Gekentekende voertuigen (public domain), https://opendata.rdw.nl/resource/m9d7-ebf2.json,
aggregated server-side and cached in data/ (private).
Usage: .venv/bin/python analysis/merger_composition.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from build_unified import MAKE_ALIASES, md_table, norm_name  # noqa: E402
from merger_fingerprint import FAMILY, WHERE  # noqa: E402
from self_registration import END_DAYS, paged, position  # noqa: E402

OUT = HERE / "merger_composition_report.md"
BODY_CACHE = HERE.parent / "data" / "x2_rdw_brand_body.parquet"
OPEL_CACHE = HERE.parent / "data" / "x2_rdw_opel_models.parquet"
BODIES = ["hatchback", "stationwagen", "MPV", "sedan"]
# Opel's models by origin, counted only up to 2019: later generations of the same names are PSA-based (the Corsa F and
# electric Corsa-e from 2020, the second Mokka from 2021). Up to 2019 RDW's "CORSA-E" is GM's fifth-generation Corsa
# (the Corsa E), not the electric car. Opel's vans of that time were Renault- or Fiat-based and are kept apart.
GM_MODELS = ("CORSA", "KARL", "VIVA", "ASTRA", "ADAM", "MOKKA", "MERIVA", "ZAFIRA", "INSIGNIA", "AGILA", "CASCADA",
             "AMPERA", "ANTARA")
PSA_MODELS = ("CROSSLAND", "GRANDLAND", "COMBO LIFE")
GM_UNTIL = 2019


def body_panel():
    """New cars per brand, body type and month, and those first registered in the month's last END_DAYS days."""
    if BODY_CACHE.exists():
        return pd.read_parquet(BODY_CACHE)
    total = paged("merk, inrichting, date_trunc_ym(datum_eerste_toelating_dt) AS m, count(1) AS n", WHERE,
                  "m, merk, inrichting", "merk, inrichting, m")
    late = paged("merk, inrichting, date_trunc_ymd(datum_eerste_toelating_dt) AS d, count(1) AS n",
                 WHERE + " AND date_extract_d(datum_eerste_toelating_dt) >= 26", "d, merk, inrichting",
                 "merk, inrichting, d")
    total["m"], total["n"] = pd.to_datetime(total["m"]).dt.to_period("M"), pd.to_numeric(total["n"])
    late["d"], late["n"] = pd.to_datetime(late["d"]), pd.to_numeric(late["n"])
    late = late[position(late["d"], END_DAYS) != "other days"]
    end = late.assign(m=late["d"].dt.to_period("M")).groupby(["merk", "inrichting", "m"])["n"].sum().rename("end")
    p = total.set_index(["merk", "inrichting", "m"]).join(end, how="left").fillna({"end": 0}).reset_index()
    p["m"] = p["m"].astype(str)
    p.to_parquet(BODY_CACHE, index=False)
    return p


def opel_panel():
    """Opel's new cars per model name and day."""
    if OPEL_CACHE.exists():
        return pd.read_parquet(OPEL_CACHE)
    p = paged("handelsbenaming, date_trunc_ymd(datum_eerste_toelating_dt) AS d, count(1) AS n",
              WHERE + " AND merk='OPEL'", "d, handelsbenaming", "handelsbenaming, d")
    p["d"], p["n"] = pd.to_datetime(p["d"]), pd.to_numeric(p["n"])
    p.to_parquet(OPEL_CACHE, index=False)
    return p


def decompose(b, family, by="body", label="body type"):
    """Kitagawa split of the family's month-end gap to other brands into a within-group part and a mix part, with
    groups in column `by` (body type here; fuel type in `merger_fuel.py`)."""
    t = b.groupby(["family", by])[["n", "end"]].sum()
    bodies = t.loc[family].index.union(t.loc["other"].index)  # a group one side lacks counts with weight 0
    f, o = (t.loc[k].reindex(bodies, fill_value=0) for k in (family, "other"))
    wf, wo = f["n"] / f["n"].sum(), o["n"] / o["n"].sum()
    rf, ro = (f["end"] / f["n"]).fillna(0), (o["end"] / o["n"]).fillna(0)
    within = (wf * (rf - ro)).sum()
    mix = ((wf - wo) * ro).sum()
    actual_f, actual_o = f["end"].sum() / f["n"].sum(), o["end"].sum() / o["n"].sum()
    assert abs((actual_f - actual_o) - (within + mix)) < 1e-9
    return {"family": family, "cars": int(f["n"].sum()), "family (%)": 100 * actual_f, "other brands (%)": 100 * actual_o,
            "gap (points)": 100 * (actual_f - actual_o), f"within {label} (points)": 100 * within,
            f"{by} mix (points)": 100 * mix}


def main():
    b = body_panel()
    b["family"] = norm_name(b["merk"]).replace(MAKE_ALIASES).map(FAMILY).fillna("other")
    b["body"] = b["inrichting"].where(b["inrichting"].isin(BODIES), "other body")
    b["year"] = pd.PeriodIndex(b["m"], freq="M").year

    # the body panel must add up to part 1's brand-by-day panel
    part1 = pd.read_parquet(HERE.parent / "data" / "x2_rdw_brand_day.parquet")
    assert b["n"].sum() == part1["n"].sum(), (b["n"].sum(), part1["n"].sum())

    pooled = pd.DataFrame([decompose(b, f) for f in ["PSA", "Opel", "FCA"]])
    by_year = pd.DataFrame([{"year": y, **decompose(b[b["year"] == y], f)}
                            for y in sorted(b["year"].unique()) for f in ["PSA", "Opel", "FCA"]])
    within_wide = by_year.pivot(index="year", columns="family", values="within body type (points)")
    mix_wide = by_year.pivot(index="year", columns="family", values="body mix (points)")
    year_rows = pd.DataFrame({"year": within_wide.index})
    for f in ["PSA", "Opel", "FCA"]:
        year_rows[f"{f}: within (points)"] = within_wide[f].round(2).to_numpy()
        year_rows[f"{f}: mix (points)"] = mix_wide[f].round(2).to_numpy()

    body_rates = b.groupby(["body", "family"])[["n", "end"]].sum()
    body_rates = (100 * body_rates["end"] / body_rates["n"]).unstack("family")[["PSA", "Opel", "FCA", "other"]]
    body_cars = b.groupby("body")["n"].sum()
    body_rows = body_rates.round(2).reset_index()
    body_rows.insert(1, "cars", body_rows["body"].map(body_cars).map("{:,}".format))

    o = opel_panel()
    name = o["handelsbenaming"].str.upper()
    o["origin"] = np.select([o["d"].dt.year > GM_UNTIL, name.str.startswith(GM_MODELS), name.str.startswith(PSA_MODELS)],
                            [f"after {GM_UNTIL}", "GM-developed", "PSA-based"], "vans (Renault- or Fiat-based)")
    o["end"] = np.where(position(o["d"], END_DAYS) != "other days", o["n"], 0)
    o["year"] = o["d"].dt.year
    t = o[o["year"] <= GM_UNTIL].groupby(["year", "origin"])[["n", "end"]].sum()
    opel_rows = pd.DataFrame({"cars": t["n"], "month end (%)": (100 * t["end"] / t["n"]).round(2)}).unstack("origin")
    opel_rows.columns = [f"{origin}: {c}" for c, origin in opel_rows.columns]
    opel_rows = opel_rows.astype({c: "Int64" for c in opel_rows.columns if c.endswith(": cars")})
    opel_rows = opel_rows.reset_index()
    other_year = b[b["family"] == "other"].groupby("year")[["n", "end"]].sum()
    opel_rows["other brands: month end (%)"] = opel_rows["year"].map(100 * other_year["end"] / other_year["n"]).round(2)
    assert o["n"].sum() == part1.loc[norm_name(part1["merk"]).eq("opel"), "n"].sum()

    fmt = {c: 2 for c in pooled.columns if pooled[c].dtype.kind == "f"}
    OUT.write_text(f"""# X2 part 3: is it what they sell? Composition checks

_Generated by `analysis/merger_composition.py`. Real RDW register data (public domain), not synthetic._

**Checks passed:** the body-type panel adds up to part 1's brand-by-day panel ({b['n'].sum():,} cars), and the Opel
model panel adds up to Opel's cars in it. Month end means the last {END_DAYS} calendar days.

## Body type: how much of each family's month-end gap is mix, and how much is within the same body type (2014-2025)

The gap to other brands is split into the part that comes from registering more at month ends *within the same body
type* and the part that comes from selling a different *mix* of body types (Kitagawa, with other brands' rates as the
reference). Fuel type, buyer type and price are not in this dataset, so the within part can still hide those mixes.

{md_table(pooled.round(fmt))}

## By year (points)

{md_table(year_rows)}

## Month-end share by body type and family (%, 2014-2025)

{md_table(body_rows)}

## Opel by model origin, up to {GM_UNTIL}

GM-developed models were on sale before and after PSA bought Opel in 2017. If Opel's rise after 2017 shows in them
too, it is not a product change. The PSA-based models (Crossland X, Grandland X, Combo Life) arrived from 2017.
Up to {GM_UNTIL}, RDW's "CORSA-E" is GM's fifth-generation Corsa, not the electric car.

{md_table(opel_rows)}
""")
    print(md_table(pooled.round(fmt)))
    print(md_table(opel_rows))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
