"""Value retained: what share of a car's original new price is left, by age and market.

METHODOLOGY_multi_dataset.md step 6. Price levels are not comparable between countries, but the
share of the original list price a car still carries is. This attaches a new-car price to each
listing from an independent reference source and computes that share.

  UK      DVM-CAR entry prices           joined to the UK listings on make, model and year, and
                                         reported per snapshot: the DVM adverts (mostly 2018) and
                                         the October 2022 scrape sit either side of the shortage
  NL      RDW catalogue prices           joined to the Dutch listings the same way
  US      Marketcheck MSRP               already on the row, no join needed
  BR      FIPE official valuations       no Brazilian listings exist, so the ratio is computed
                                         inside FIPE itself: each model year's current value
                                         against that same model's 0 km price when it was new

Every borrowed price is written out with the source it came from, as the methodology requires.
The share is of the ORIGINAL list price of that model year, not of today's new price.

Usage: .venv/bin/python analysis/value_retained.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import md_table  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
OUT = HERE / "value_retained_report.md"
MATCHED = DATA / "unified" / "value_retained.parquet"
AGES = list(range(1, 11))
UK_2018, UK_2022 = "UK 2018", "UK Oct 2022"   # dvm adverts are mostly 2018; uk_2022_10 is one scrape


def listings():
    d = pd.read_parquet(DATA / "unified" / "listings.parquet",
                        columns=["source", "country", "price_type", "is_new", "make", "model",
                                 "year", "age_years", "mileage_km", "price", "currency",
                                 "price_eur", "new_price_eur", "listing_date"])
    d = d[d["price_type"].eq("asking") & ~d["is_new"].fillna(False).astype(bool)]
    return d[d["age_years"].between(0.5, 15)]


def curve(d, label, source):
    """Median value retained at each whole year of age, plus how many cars sit behind it."""
    d = d[d["retained"].between(0.02, 1.5)].copy()
    d["age"] = d["age_years"].round().astype(int)
    g = d[d["age"].isin(AGES)].groupby("age")["retained"]
    return {"market": label, "new price from": source, "cars": len(d),
            **{f"{a}y": (f"{g.median()[a] * 100:.0f}%" if a in g.median().index and g.size()[a] >= 30
                         else "-") for a in AGES}}


def main():
    L = listings()
    parts, rows, coverage = [], [], []

    # ---- UK: DVM entry prices ----
    dvm = pd.read_parquet(DATA / "reference" / "dvm_new_prices.parquet")
    uk = L[L["country"].eq("GB")].merge(
        dvm[["make", "model", "year", "entry_price_gbp"]], on=["make", "model", "year"], how="left")
    coverage.append({"market": "UK", "reference": "DVM-CAR entry price", "listings": f"{len(uk):,}",
                     "matched": f"{uk['entry_price_gbp'].notna().sum():,}",
                     "match rate": f"{uk['entry_price_gbp'].notna().mean():.1%}"})
    uk_m = uk[uk["entry_price_gbp"].notna() & uk["currency"].eq("GBP")].copy()
    uk_m["new_price"] = uk_m["entry_price_gbp"]
    uk_m["retained"] = uk_m["price"] / uk_m["new_price"]
    uk_m["new_price_source"] = "dvm_entry_price_gbp"
    # The two UK sources are years apart, either side of the 2021-22 shortage. Pooling them would
    # let the mix of eras change with age, so each gets its own row.
    for source, label in (("dvm", UK_2018), ("uk_2022_10", UK_2022)):
        rows.append(curve(uk_m[uk_m["source"].eq(source)], label, "DVM-CAR entry price"))
    parts.append(uk_m)

    # ---- NL: RDW catalogue prices ----
    rdw = pd.read_parquet(DATA / "reference" / "rdw_new_prices.parquet")
    nl = L[L["country"].eq("NL")].merge(
        rdw[["make", "model", "year", "new_price_eur", "n"]].rename(
            columns={"new_price_eur": "rdw_price"}), on=["make", "model", "year"], how="left")
    coverage.append({"market": "NL", "reference": "RDW catalogue price", "listings": f"{len(nl):,}",
                     "matched": f"{nl['rdw_price'].notna().sum():,}",
                     "match rate": f"{nl['rdw_price'].notna().mean():.1%}"})
    nl_m = nl[nl["rdw_price"].notna() & nl["n"].ge(3)].copy()
    nl_m["new_price"] = nl_m["rdw_price"]
    nl_m["retained"] = nl_m["price_eur"] / nl_m["new_price"]
    nl_m["new_price_source"] = "rdw_catalogusprijs_eur"
    rows.append(curve(nl_m, "NL", "RDW catalogue price"))
    parts.append(nl_m)

    # ---- US: Marketcheck MSRP, already on the row ----
    us = L[L["source"].eq("us_marketcheck_used") & L["new_price_eur"].notna()].copy()
    coverage.append({"market": "US", "reference": "Marketcheck MSRP",
                     "listings": f"{len(L[L['source'].eq('us_marketcheck_used')]):,}",
                     "matched": f"{len(us):,}", "match rate": "100.0%"})
    us["new_price"] = us["new_price_eur"]
    us["retained"] = us["price_eur"] / us["new_price"]
    us["new_price_source"] = "marketcheck_msrp"
    rows.append(curve(us, "US", "Marketcheck MSRP"))
    parts.append(us)

    # ---- BR: FIPE, computed inside the reference table ----
    fipe = pd.read_parquet(DATA / "reference" / "fipe_history.parquet",
                           columns=["make", "model", "model_year", "is_new", "ref_year",
                                    "ref_month", "price_brl"])
    # the 0 km price of that model in the year that model year was current
    new = (fipe[fipe["is_new"].astype("boolean").fillna(False)]
           .groupby(["make", "model", "ref_year"])["price_brl"].median()
           .rename("new_price").reset_index()
           .rename(columns={"ref_year": "model_year"}))
    used = fipe[~fipe["is_new"].astype("boolean").fillna(False)].merge(
        new, on=["make", "model", "model_year"], how="left")
    coverage.append({"market": "BR", "reference": "FIPE 0 km valuation",
                     "listings": f"{len(used):,}", "matched": f"{used['new_price'].notna().sum():,}",
                     "match rate": f"{used['new_price'].notna().mean():.1%}"})
    br = used[used["new_price"].notna()].copy()
    br["age_years"] = br["ref_year"] - br["model_year"]
    br["retained"] = br["price_brl"] / br["new_price"]
    br = br[br["age_years"].between(0.5, 15)]
    rows.append(curve(br, "BR", "FIPE 0 km valuation"))

    # FIPE's own 0 km series measures new-car price inflation in BRL, which is the obvious
    # suspect for Brazil's flat curve. Measure it rather than assume it.
    nk = new.sort_values(["make", "model", "model_year"]).copy()
    nk["prev"] = nk.groupby(["make", "model"])["new_price"].shift(1)
    nk["prev_year"] = nk.groupby(["make", "model"])["model_year"].shift(1)
    step = nk[(nk["model_year"] - nk["prev_year"]).eq(1) & nk["prev"].gt(0)]
    br_new_inflation = float((step["new_price"] / step["prev"] - 1).median() * 100)

    matched = pd.concat([p[["source", "country", "make", "model", "year", "age_years", "mileage_km",
                            "price", "currency", "price_eur", "new_price", "new_price_source",
                            "retained"]] for p in parts], ignore_index=True)
    matched = matched[matched["retained"].between(0.02, 1.5)]
    MATCHED.parent.mkdir(parents=True, exist_ok=True)
    matched.to_parquet(MATCHED, index=False)
    print(f"wrote {len(matched):,} listings with a borrowed new price to {MATCHED.name}")

    table = pd.DataFrame(rows)
    dvm_years = uk_m.loc[uk_m["source"].eq("dvm"), "listing_date"].dt.year.value_counts(normalize=True)
    pct_of = lambda v: float(v.rstrip("%")) if v and v != "-" else float("nan")  # noqa: E731
    three = {r["market"]: r.get("3y") for r in rows}
    five = {r["market"]: r.get("5y") for r in rows}
    # implied annual rate from the ten-year share, to compare with the driver models
    implied = {}
    for r in rows:
        v = r.get("10y")
        if v and v != "-":
            implied[r["market"]] = (float(v.rstrip("%")) / 100) ** (1 / 10) - 1

    report = [
        "# Value retained: how much of the new price is left", "",
        "Generated by `analysis/value_retained.py`. Matched listings with their borrowed new price "
        "are written to `data/unified/value_retained.parquet`, each row carrying the source the "
        "price came from.", "",
        "Price levels do not compare across countries, but the share of the original list price a "
        "car still carries does. Four markets, each with an **independent** new-price source:", "",
        "## Coverage", "", md_table(pd.DataFrame(coverage)), "",
        "Match rates matter more than the curve here. A listing only gets a new price if its make, "
        "model and year appear in the reference table, so the matched set leans toward mainstream "
        "models that a reference source bothers to list. Read the curves as being about ordinary "
        "cars, not the whole market.", "",
        "## Value retained by age (median)", "", md_table(table), "",
        "## What it shows", "",
        f"- **At three years old a car keeps roughly {three.get(UK_2018, '?')} (UK, 2018 adverts), "
        f"{three.get('NL', '?')} (NL), {three.get('US', '?')} (US) and {three.get('BR', '?')} (BR) "
        "of its original list price.** Four different countries, four different reference sources, "
        "four different currencies, and the same broad answer.",
        f"- By five years the figures are {five.get(UK_2018, '?')}, {five.get('NL', '?')}, "
        f"{five.get('US', '?')} and {five.get('BR', '?')}.",
        f"- **The UK's two snapshots show the level move directly.** The same three-year-old share "
        f"was {three.get(UK_2018, '?')} in the DVM adverts ({dvm_years.get(2018, 0):.0%} of them "
        f"from 2018) and {three.get(UK_2022, '?')} in October 2022, "
        f"{pct_of(three.get(UK_2022)) - pct_of(three.get(UK_2018)):+.0f} points, at the height of "
        "the shortage. That is the market-wide version of the Corsa in `one_car_report.md`, with "
        "the same caveat: two different scrapes, so part of the gap is a difference of source. "
        "Pooling the two would blend eras and bend the curve, because the older ages come mostly "
        "from 2022 and the younger mostly from 2018.",
        "- This is the same lesson as the rest of the analysis: **the shape travels, the level does "
        "not.** A Dutch car and a Brazilian car cost wildly different amounts and lose value at a "
        "broadly similar rate as a share of what they cost new.",
        "- **It is broadly consistent with the regressions, which are built quite differently.** "
        "Reading an annual rate off the ten-year share gives "
        + ", ".join(f"{m} {v * 100:.1f}%" for m, v in implied.items())
        + " a year. `analysis/drivers_report.md` never sees a new price and works from the slope of "
        "log price against age with mileage held fixed; these shares include the mileage cars "
        "actually accumulate and the gap from an entry-trim or tax-inclusive list price, so they "
        "need not match it exactly.", "",
        "## Limits worth stating before this goes on a slide", "",
        "- **The Dutch ratio is not comparable to the others in level.** RDW's `catalogusprijs` is "
        "the Dutch list price including VAT *and* BPM registration tax, while the used asking price "
        "carries no BPM for the buyer in the same way. That deflates the Dutch share against the "
        "others by construction.",
        "- **The UK new price is the cheapest trim.** DVM's entry price is the bottom of the range, "
        "so a listing of a higher trim is compared against a cheaper car and its retained share "
        "looks too high. Together with the shortage, that is why the October 2022 row passes 100% "
        "at one and two years.",
        "- **Brazil is not a like-for-like row.** FIPE is an official valuation table, not a market "
        "of adverts, and its ratio is one valuation divided by another from the same source, so it "
        "carries none of the noise the advert-based markets do.",
        f"- **The US sample is {len(us):,} listings.** It is the only source with an MSRP on every "
        "row, but it is tiny, and it is US data.",
        f"- **Brazil's curve is far flatter than the others, and new-car inflation does not explain "
        f"it.** That was the obvious suspect, so it was measured: FIPE's own 0 km series shows "
        f"Brazilian new-car prices rising a median **{br_new_inflation:.1f}% a year** over the "
        "period, which is nowhere near enough to account for the gap. The more likely explanations "
        "are that an official valuation table is smoothed by construction, and that Brazilian used "
        "cars genuinely hold nominal value well. Either way, do not present Brazil next to the "
        "others as if it were the same measurement.",
        "- **Nothing here is inflation-adjusted.** The new price is the nominal list price of that "
        "model year, so for older cars the share is flattered by general price inflation since.", "",
    ]
    OUT.write_text("\n".join(report))
    print(table.to_string(index=False))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
