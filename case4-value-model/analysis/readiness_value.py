"""Readiness times value: what comes back, and what it is worth, in one table.

`readiness_engine.py` says how likely a car of a given age is to come to market.
`value_engine.py` says what a car is worth. The ledger's claim is that those two belong on the
same record, and this is the smallest honest demonstration of it: for the Dutch fleet, the value
of the cars that will change hands in the next twelve months, by age.

    cars of that age  x  share that change keeper in a year  x  what one is worth

Three measured numbers, multiplied. The first two come from RDW's register
(`analysis/readiness_base.py`); the third is the median asking price of Dutch adverts of that age
in the collection.

**This is not the value-at-risk model and must not be confused with it.** The workbook prices what
the group loses when a residual is wrong. This prices the flow of metal across the market, which
is a different quantity with a different purpose: it says *where in the age range the money moves*,
which is what a contact list has to be sorted by.

Usage: .venv/bin/python analysis/readiness_value.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import md_table  # noqa: E402

HERE = Path(__file__).parent
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
HAZARD = HERE / "readiness_base_hazard.csv"
RETAINED = HERE.parent / "data" / "unified" / "value_retained.parquet"
OUT = HERE / "readiness_value_report.md"
TABLE = HERE / "readiness_value_by_age.csv"

MIN_ADS = 60        # below this an age's median price is not worth quoting
AGES = (1, 20)


def retention():
    """What a Dutch car is still worth, as a share of its official new price, by age.

    `value_retained.parquet` divides an advert price by the RDW catalogue price of the same make,
    model and year. **A ratio is the right thing to take from a scrape that over-represents
    expensive cars**, because the bias sits in the numerator and the denominator alike and divides
    out. The level of those adverts does not survive scrutiny; their retention does.
    """
    v = pd.read_parquet(RETAINED)
    nl = v[(v["country"] == "NL") & v["retained"].between(0.02, 1.5)].copy()
    nl["age"] = nl["age_years"].round().astype(int)
    g = nl.groupby("age")["retained"].agg(retained="median", n_retained="size").reset_index()
    return g[g["n_retained"] >= 30]


def prices():
    """Median Dutch asking price by age, from the collection's Dutch adverts."""
    d = pd.read_parquet(LISTINGS, columns=["source", "country", "age_years", "price_eur",
                                           "is_new", "price_type", "is_stellantis"])
    d = d[(d["country"] == "NL") & d["price_type"].eq("asking")
          & ~d["is_new"].fillna(False).astype(bool)]
    d = d[d["price_eur"].between(500, 200_000) & d["age_years"].between(0.5, 30)]
    d["age"] = d["age_years"].round().astype(int)
    g = d.groupby("age")
    return pd.DataFrame({
        "ads": g.size(),
        "median_eur": g["price_eur"].median(),
        "group_ads": g["is_stellantis"].sum(),
    }).reset_index()


def main():
    haz = pd.read_csv(HAZARD)
    ret = retention()
    ads = prices()
    d = haz.merge(ret, left_on="age_years", right_on="age", how="inner")
    d = d.merge(ads[["age", "ads", "median_eur", "group_ads"]], on="age", how="left")
    d = d[d["age_years"].between(*AGES) & d["new_price_eur"].notna()].copy()

    d["moving"] = d["parc"] * d["rate"]
    d["moving_st"] = d["parc_st"] * d["rate_st"]
    # official new price of the cars of that vintage still on the road, times what a Dutch car of
    # that age is still worth
    d["used_eur"] = d["new_price_eur"] * d["retained"]
    d["value_eur"] = d["moving"] * d["used_eur"]
    d["value_st_eur"] = d["moving_st"] * d["used_eur"]

    total = d["value_eur"].sum()
    total_st = d["value_st_eur"].sum()
    peak = d.loc[d["value_eur"].idxmax()]
    top5 = d.nlargest(5, "value_eur")
    wave = d[d["age_years"].between(4, 6)]
    naive = float((d["moving"] * d["median_eur"]).sum(skipna=True))
    print(f"{len(d)} ages; EUR {total/1e9:.1f}bn total, EUR {total_st/1e9:.1f}bn group brands "
          f"(advert-priced would say EUR {naive/1e9:.1f}bn)")

    silly = d.loc[d["median_eur"].idxmax()] if d["median_eur"].notna().any() else None
    lines = [
        "# Readiness times value: where the money moves",
        "",
        "The ledger's claim is that how likely a car is to move and what it is worth belong on "
        "the same record. This is the smallest demonstration of it: for the Dutch fleet, the value "
        "of the cars that will change hands in the next twelve months, by age.",
        "",
        "    cars of that age  x  share that change keeper in a year  x  what one is worth",
        "",
        "The first two come from RDW's register (`readiness_base_report.md`). The third is RDW's "
        "**official catalogue price** for the cars of that vintage still on the road, multiplied "
        "by how much of it a Dutch car of that age still holds - measured in "
        "`value_retained_report.md` against that same official price.",
        "",
        f"**EUR {total/1e9:.1f} billion a year of metal crosses the Dutch market, "
        f"EUR {total_st/1e9:.1f} billion of it the group's own brands.** "
        f"{d['moving'].sum():,.0f} cars change keeper, {d['moving_st'].sum():,.0f} of them the "
        f"group's.",
        "",
        f"The biggest single age is **{int(peak['age_years'])}**, at "
        f"EUR {peak['value_eur']/1e9:.2f}bn, and it gets there on price rather than on hazard - "
        f"only {peak['rate']:.1%} of those cars move. **The replacement wave is ages four to six, "
        f"which carry EUR {wave['value_eur'].sum()/1e9:.2f}bn between them "
        f"({wave['value_eur'].sum()/total:.0%} of the total) on {wave['moving'].sum():,.0f} "
        f"cars.** That is where a high hazard meets a car still worth something, and it is the "
        "part of the age range a contact list has to be pointed at.",
        "",
    ]
    lines.append(md_table(pd.DataFrame([
        {"What": "Value crossing the Dutch market in a year",
         "Figure": f"{total/1e9:.1f}"},
        {"What": "...of which the group's own brands", "Figure": f"{total_st/1e9:.1f}"},
        {"What": "Cars changing keeper", "Figure": f"{d['moving'].sum():,.0f}"},
        {"What": "Value in the wave, ages four to six",
         "Figure": f"{wave['value_eur'].sum()/1e9:.2f}"},
        {"What": "What pricing it from our own adverts would have said",
         "Figure": f"{naive/1e9:.1f}"},
    ])))
    lines += ["", "*(EUR billions except the car count. In a table so each figure has its own "
              "cell for `check_assumptions.py`.)*", ""]
    lines.append(md_table(pd.DataFrame({
        "Age": d["age_years"].astype(int),
        "Cars on the road": d["parc"].map("{:,.0f}".format),
        "Change keeper in a year": d["rate"].map("{:.1%}".format),
        "Official new price": d["new_price_eur"].map("EUR {:,.0f}".format),
        "Still worth": d["retained"].map("{:.0%}".format),
        "Used value": d["used_eur"].map("EUR {:,.0f}".format),
        "Value crossing the market": (d["value_eur"] / 1e9).map("EUR {:.2f}bn".format),
    })))
    share5 = top5["value_eur"].sum() / total
    lines += [
        "",
        f"**The five biggest ages carry {share5:.0%} of it** "
        f"({', '.join(str(int(a)) for a in sorted(top5['age_years']))} years).",
        "",
        "## Why the price is not taken from our own adverts",
        "",
        "It was, first, and the answer was wrong. Our Dutch adverts give a median asking price of "
        f"**EUR {silly['median_eur']:,.0f} for a {int(silly['age_years'])}-year-old car** on "
        f"{int(silly['ads']):,} adverts, and the curve is not even monotone in age: that is one "
        "premium dealer scrape, not a market. Priced that way the total comes out at "
        f"**EUR {naive/1e9:.1f}bn against EUR {total/1e9:.1f}bn** here. **Do not price this from "
        "the listings.**",
        "",
        "It is the same failure `readiness_base_report.md` found in its third check, from the "
        "other side: our listings are good for shapes pooled across many sources and bad for a "
        "level in one country. **What survives from them is the retention ratio**, because a "
        "scrape that over-represents expensive cars biases the advert price and the catalogue "
        "price together, and the bias divides out. The level comes from the register instead.",
        "",
        "## What this is and is not",
        "",
        "- **It is not the value-at-risk model.** `../Case4_Value_at_Risk.xlsx` prices what the "
        "group loses when a residual is wrong, and its headline is unchanged at EUR 913m / "
        "EUR 1,460m. This prices the flow of metal across a market. They are different quantities: "
        "do not add them, and do not present one as the other.",
        "- **The retention curve is measured on advert prices**, so it inherits the project's "
        "standing caveat that an advert is not a sale (`price_types_report.md`). It reproduces "
        "the project's independently measured 62% at three years for the Netherlands.",
        "- **The group-brand figure carries no price assumption of its own beyond the market "
        "curve**: its cars and its rate are both measured for the group's brands specifically.",
        "- **Dutch.** The level is local; the project has measured three times that a shape "
        "travels between markets and a level does not.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    d.to_csv(TABLE, index=False)
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
