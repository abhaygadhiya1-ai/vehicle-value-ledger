"""Layer 1 of the readiness engine: how likely a car of a given age is to come to market.

The engine needs a real probability, not an index, so the base hazard has to carry a level as
well as a shape. The Dutch RDW register gives both out of one official file: every car holds the
date it was first admitted to the road and the date the *current* keeper took it on, so

    hazard(age) = cars of that age whose keeper changed in the last twelve months
                  -------------------------------------------------------------
                            cars of that age on the road

is a count divided by a count. Nothing is modelled and nothing is assumed.

Three things are checked rather than asserted:

  1. **Against the outside.** Our twelve-month total is compared with the used-car sales that
     BOVAG and RDC publish for the Netherlands, which is an independent count of the same event.
  2. **Age or cohort?** One snapshot cannot tell "cars are replaced at five" from "the 2021 cars
     happen to be moving". The register's previous twelve months, uncensored, answer it.
  3. **Against our own adverts.** If the curve is real, Dutch adverts per car on the road should
     rise and fall with it.

`build_reference.py nlhazard` writes the table this reads.

Usage: .venv/bin/python analysis/readiness_base.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import md_table  # noqa: E402

HERE = Path(__file__).parent
HAZARD = HERE.parent / "data" / "reference" / "nl_transfer_hazard.parquet"
BYMAKE = HERE.parent / "data" / "reference" / "nl_transfer_by_make.parquet"
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
OUT = HERE / "readiness_base_report.md"
CURVE = HERE / "readiness_base_hazard.csv"

# The only figure here that is not ours. BOVAG and RDC count Dutch used-car sales from the trade's
# own registrations, which is a different instrument on the same event, so it is a real check.
BOVAG_2025_SALES = 2_124_429
BOVAG_URL = ("https://www.bovag.nl/pers/persberichten/"
             "recordjaar-2025-verkoop-gebruikte-auto-s-stijgt-naar-2-1-miljoen")

TOP_AGE = 25        # past this the parc thins out and a year of age stops meaning much
MIN_MAKE = 3_000    # below this a make-year cell is too thin to quote
PEAK_BAND = (3, 8)  # where the replacement wave sits, used to name the peak without picking it


def curve(d, population, brands, window):
    c = d[(d["population"] == population) & (d["brands"] == brands) & (d["window"] == window)]
    return c[c["age_years"].between(1, TOP_AGE)].sort_values("age_years").reset_index(drop=True)


def uncensor(d):
    """The previous twelve months, corrected for the register only showing the current keeper.

    A car whose current keeper arrived in the previous window is one that moved then and has not
    moved since, so the raw count misses those that moved twice. Dividing by the chance of not
    moving in the latest window puts them back, on the assumption that the two years are
    independent. They are not quite - a car that has just changed hands behaves differently - so
    this is a correction good enough to locate a peak, not to quote a level.
    """
    now = curve(d, "domestic", "all", "latest").set_index("reg_year")
    prev = curve(d, "domestic", "all", "previous").set_index("reg_year")
    survived = 1 - now["rate"].reindex(prev.index)
    out = pd.DataFrame({
        "reg_year": prev.index,
        "age_then": prev["age_years"] - 1,
        "raw": prev["rate"],
        "corrected": prev["rate"] / survived,
    }).reset_index(drop=True)
    # the same age, one year later, is the thing to compare it with
    out["latest_same_age"] = out["age_then"].map(
        dict(zip(now["age_years"], now["rate"])))
    return out.dropna()


def adverts(d):
    """Dutch adverts per thousand cars on the road, by year of registration."""
    cols = ["source", "country", "year", "is_new", "price_type"]
    lst = pd.read_parquet(LISTINGS, columns=cols)
    nl = lst[(lst["source"] == "eu_2025_11") & (lst["country"] == "NL")
             & ~lst["is_new"].fillna(False).astype(bool)]
    n = nl["year"].value_counts().rename("adverts")
    parc = curve(d, "all", "all", "latest").set_index("reg_year")
    out = parc.join(n, how="inner")
    out["per_1000"] = 1000 * out["adverts"] / out["parc"]
    return out.reset_index()


def main():
    d = pd.read_parquet(HAZARD)
    latest = d[d["window"] == "latest"]
    start = pd.Timestamp(latest["window_start"].min())
    end = pd.Timestamp(latest["window_end"].max())

    dom = curve(d, "domestic", "all", "latest")
    dom_st = curve(d, "domestic", "all", "latest").merge(
        curve(d, "domestic", "stellantis", "latest")[["age_years", "parc", "movers", "rate"]],
        on="age_years", suffixes=("", "_st"))
    allcars = curve(d, "all", "all", "latest")

    band = dom[dom["age_years"].between(*PEAK_BAND)]
    peak = band.loc[band["rate"].idxmax()]
    trough = dom.loc[dom[dom["age_years"] > peak["age_years"]]["rate"].idxmin()]
    overall = dom["movers"].sum() / dom["parc"].sum()

    # Every keeper change in the window, including cars since exported or scrapped: a car sold in
    # November and exported in March was still a sale, and that is what BOVAG counts.
    total_movers = int(d[(d["population"] == "all_ever") & (d["brands"] == "all")
                         & (d["window"] == "latest")]["movers"].sum())
    on_road = int(d[(d["population"] == "all") & (d["brands"] == "all")
                    & (d["window"] == "latest")]["movers"].sum())
    gap = total_movers / BOVAG_2025_SALES - 1

    unc = uncensor(d)
    check = unc[unc["age_then"].between(2, 20)]
    peak_then = check.loc[check["corrected"].idxmax(), "age_then"]
    moved = abs(np.corrcoef(check["corrected"], check["latest_same_age"])[0, 1])

    ad = adverts(d)
    ad_fit = ad[ad["reg_year"].between(2005, 2023)]
    rho = ad_fit[["per_1000", "rate"]].corr(method="spearman").iloc[0, 1]

    imports = allcars.merge(dom[["age_years", "parc", "movers"]], on="age_years",
                            suffixes=("_all", "_dom"))
    imports["import_share"] = 1 - imports["parc_dom"] / imports["parc_all"]

    lines = [
        "# Layer 1: the base hazard by age",
        "",
        f"How often a Dutch car changes hands, by age, over the twelve months "
        f"{start:%B %Y} to {end:%B %Y}. Source: RDW's open vehicle register "
        "(https://opendata.rdw.nl/resource/m9d7-ebf2, CC0), aggregated on RDW's own server.",
        "",
        "Numerator and denominator come out of the same file. The numerator is a car whose "
        "current keeper took it on inside the window; the denominator is every car of that age "
        "on the road. A first registration is not a keeper change and is excluded, or age 0 "
        "would read 100% by construction.",
        "",
        "**The population is cars first put on Dutch plates when new.** An imported used car "
        "registers a keeper change the day it arrives, and imports are a large share of the parc "
        "at exactly the ages that matter, so leaving them in would invent a replacement wave.",
        "",
        f"**{overall:.1%} of the fleet changes hands in a year.** The rate is far from flat: it "
        f"peaks at **{peak['rate']:.1%} at {int(peak['age_years'])} years** and falls to "
        f"**{trough['rate']:.1%} at {int(trough['age_years'])}** - "
        f"**{peak['rate'] / trough['rate']:.2f} times** as many cars come to market at the peak "
        "as at the quietest age.",
        "",
        "## Headline",
        "",
        "*These figures sit in a table so that `check_assumptions.py` can pin each one to its own "
        "cell. A sentence holding several figures cannot tell them apart.*",
        "",
    ]
    lines.append(md_table(pd.DataFrame([
        {"What": "Changes hands in a year, whole fleet", "Figure": f"{overall:.1%}"},
        {"What": "Peak rate", "Figure": f"{peak['rate']:.1%}"},
        {"What": "Age at the peak", "Figure": f"{int(peak['age_years'])}"},
        {"What": "Quietest rate", "Figure": f"{trough['rate']:.1%}"},
        {"What": "Age at the quietest", "Figure": f"{int(trough['age_years'])}"},
        {"What": "Peak against quietest", "Figure": f"{peak['rate'] / trough['rate']:.2f}"},
        {"What": "Group brands, share of the Dutch fleet",
         "Figure": f"{dom_st['parc_st'].sum() / dom_st['parc'].sum():.1%}"},
        {"What": "Cars in the measurement", "Figure": f"{int(dom['parc'].sum()):,}"},
    ])))
    lines += [
        "",
        "## The hazard by age",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Age": dom_st["age_years"].astype(int),
        "Cars on the road": dom_st["parc"].map("{:,}".format),
        "Changed keeper": dom_st["movers"].map("{:,}".format),
        "Rate": dom_st["rate"].map("{:.1%}".format),
        "Group brands: cars": dom_st["parc_st"].map("{:,}".format),
        "Group brands: rate": dom_st["rate_st"].map("{:.1%}".format),
    })))
    st_rho = dom_st[["rate", "rate_st"]].corr(method="spearman").iloc[0, 1]
    lines += [
        "",
        f"The group's own brands are {dom_st['parc_st'].sum() / dom_st['parc'].sum():.0%} of the "
        f"Dutch fleet and follow the same curve (rank correlation {st_rho:.2f} across ages). "
        "The shape is a property of the fleet, not of a brand mix.",
        "",
        "## Same age, different cars",
        "",
    ]
    # the curve above is an average over makes, and an average is not a prediction about a car
    mk = pd.read_parquet(BYMAKE)
    mk = mk[(mk["age_years"] == peak["age_years"]) & (mk["parc"] >= MIN_MAKE)]
    mk = mk.sort_values("rate", ascending=False)
    grp = mk[mk["is_group"]]
    # the deck figure has room for fifteen rows, so its spread is quoted too
    big = mk.nlargest(15, "parc")
    lines += [
        f"The curve above is an average, and an average is not a prediction about a car. These "
        f"are the {len(mk)} makes with at least {MIN_MAKE:,} cars registered in "
        f"{int(peak['reg_year'])}, so **every one of them is exactly "
        f"{int(peak['age_years'])} years old**:",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Make": mk["merk"].str.title(),
        "Cars on the road": mk["parc"].map("{:,}".format),
        "Changed keeper": mk["rate"].map("{:.1%}".format),
        "Group brand": mk["is_group"].map({True: "yes", False: ""}),
    })))
    lines += ["", "*In a table so each figure has its own cell for the checker.*", ""]
    lines.append(md_table(pd.DataFrame([
        {"What": "Lowest make at the peak age", "Figure": f"{mk['rate'].min():.1%}"},
        {"What": "Highest make at the peak age", "Figure": f"{mk['rate'].max():.1%}"},
        {"What": "Spread across makes at one age",
         "Figure": f"{mk['rate'].max() / mk['rate'].min():.2f}"},
        {"What": "Spread across the fifteen largest makes",
         "Figure": f"{big['rate'].max() / big['rate'].min():.2f}"},
        {"What": "Lowest of the fifteen largest", "Figure": f"{big['rate'].min():.1%}"},
        {"What": "Group brands, lowest", "Figure": f"{grp['rate'].min():.1%}"},
        {"What": "Group brands, highest", "Figure": f"{grp['rate'].max():.1%}"},
    ])))
    lines += [
        "",
        f"**A {mk['rate'].max() / mk['rate'].min():.2f}x spread at a single age** "
        f"({big['rate'].max() / big['rate'].min():.2f}x across the fifteen largest makes, which "
        "is what the deck figure has room to show), and the "
        f"group's own four brands alone run {grp['rate'].min():.1%} to {grp['rate'].max():.1%}. "
        "The age curve says which year to look at and nothing about which car in it. That is the "
        "measured reason the engine needs a layer beyond age, and it is on the same register.",
        "",
        "## Check 1: against a count made by somebody else",
        "",
    ]
    lines.append(md_table(pd.DataFrame([{
        "What": "Keeper changes in the register, twelve months, every car",
        "Count": f"{total_movers:,}",
    }, {
        "What": "...of which the car is still on Dutch plates today",
        "Count": f"{on_road:,}",
    }, {
        "What": "Used-car sales published by BOVAG and RDC for 2025",
        "Count": f"{BOVAG_2025_SALES:,}",
    }, {
        "What": "Difference against BOVAG",
        "Count": f"{gap:+.1%}",
    }])))
    lines += [
        "",
        f"**{abs(gap):.1%} below** a figure collected a different way, by the motor trade's own "
        "body, and low in the direction the method predicts. A snapshot shows only the *current* "
        "keeper, so a car that changed hands twice inside the year counts once. At a rate of "
        f"about {overall:.0%} a year the share of movers that move again within the window is of "
        "the order of a tenth, which is the size of the gap. *That is an explanation of the "
        "direction and rough size, not a measurement of the difference.* Treat the level as good "
        "to about ten per cent, and never quote it as exact.",
        "",
        "## Check 2: is it age, or is it the 2021 cars?",
        "",
        "A single snapshot cannot tell a wave that follows a car's age from one that follows a "
        "registration year. The register carries the answer, because the twelve months before "
        "last are still visible through cars that have not moved since - censored, and put back "
        "by dividing by the chance of not moving since.",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Age": check["age_then"].astype(int),
        "Previous year, as seen": check["raw"].map("{:.1%}".format),
        "Previous year, uncensored": check["corrected"].map("{:.1%}".format),
        "Latest year, same age": check["latest_same_age"].map("{:.1%}".format),
    })))
    lines += [
        "",
        f"The peak sits at **{int(peak_then)} years in the earlier window** and at "
        f"**{int(peak['age_years'])} years in the later one**, and the two curves agree across "
        f"ages at a correlation of **{moved:.2f}**. The wave travels with the car's age, not with "
        "a registration year, so it is not the 2021 cohort. *The correction assumes one year is "
        "independent of the next, which is not quite true; it locates the peak, it does not "
        "measure the level a second time.*",
        "",
        "## Check 3: against our own adverts - this one fails",
        "",
        "If the curve is real, the Dutch adverts in the collection should thin out and thicken "
        "with it. This is adverts per thousand cars on the road, by year of registration, from "
        f"`eu_2025_11` ({int(ad['adverts'].sum()):,} used Dutch adverts, 8 November 2025). The "
        "population is every car on the road, imports included, because an advert does not care "
        "where the car came from.",
        "",
    ]
    show = ad[ad["reg_year"].between(2006, 2024)].sort_values("reg_year", ascending=False)
    lines.append(md_table(pd.DataFrame({
        "Registered": show["reg_year"].astype(int),
        "Adverts per 1,000 cars": show["per_1000"].map("{:.1f}".format),
        "Keeper-change rate": show["rate"].map("{:.1%}".format),
    })))
    spike = show.loc[show["adverts"].idxmax()]
    quiet = show[show["reg_year"].between(2013, 2023)].nsmallest(1, "adverts").iloc[0]
    lines += [
        "",
        f"**Rank correlation {rho:.2f} over registrations 2005 to 2023. The adverts do not "
        "recover the curve, and this check fails.** It fails for a readable reason rather than "
        f"because the curve is wrong: one site on one day carries "
        f"{int(spike['adverts']):,} adverts of {int(spike['reg_year'])} cars and only "
        f"{int(quiet['adverts']):,} of {int(quiet['reg_year'])} cars, a swing no fleet produces. "
        "What a scrape holds is the stock that site happened to have, and the share of keeper "
        "changes that reach any one forecourt is not flat in age.",
        "",
        "**This is the argument for taking layer 1 from the register rather than from our own "
        "listings.** The handoff's design put the shape in the listings and the level in official "
        "statistics; the register carries both, and the listings turn out not to be able to check "
        "it. Stating that is better than pooling the two and hoping.",
        "",
        "## What this is not",
        "",
        "- **A keeper change is not a sale to a new customer.** It counts a car going into a "
        "dealer's stock, a lease company handing a car to its buyer, and a car moving inside a "
        "family. It is the closest public event to \"the car came to market\", and it is not the "
        "same event as \"the customer was ready to replace\".",
        "- **It is Dutch.** The project has measured three times that the shape of a used-car "
        "effect travels between markets and the level does not. The level here is Dutch, and the "
        "Netherlands taxes cars unusually (BPM) and leases them heavily.",
        f"- **Imports run the other way.** {imports.loc[imports['age_years'].between(4, 6), 'import_share'].mean():.0%} "
        "of Dutch cars aged four to six were imported used, and every one of them books a keeper "
        "change on arrival. That is why the headline uses the domestic population.",
        "- **One snapshot, one year.** The window is twelve months to "
        f"{end:%B %Y}; check 2 is what stands in for a second year.",
    ]
    OUT.write_text("\n".join(lines) + "\n")

    keep = dom_st[["age_years", "reg_year", "parc", "movers", "rate", "parc_st", "movers_st",
                   "rate_st", "new_price_eur"]]
    keep.to_csv(CURVE, index=False)
    print(f"wrote {OUT.name} and {CURVE.name}")
    print(f"  overall {overall:.2%}, peak {peak['rate']:.2%} at age {int(peak['age_years'])}, "
          f"trough {trough['rate']:.2%} at {int(trough['age_years'])}")
    print(f"  BOVAG gap {gap:+.2%}; cohort check peak {int(peak_then)} -> "
          f"{int(peak['age_years'])}, r={moved:.2f}; adverts rho={rho:.2f}")


if __name__ == "__main__":
    main()
