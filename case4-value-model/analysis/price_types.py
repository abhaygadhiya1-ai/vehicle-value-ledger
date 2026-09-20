"""Step 5: what is the gap between an advert price, a sale price and an auction price?

METHODOLOGY_multi_dataset.md step 5. The unified table holds three kinds of price and they are
not the same thing, so a model fitted on adverts cannot be read as a prediction of what a car
will actually fetch. This measures the gap where the data allows it, and says plainly where it
does not.

The honest finding is that only one of the three pairs is estimable:

  asking vs sale      NOT estimable. The only US advert source is a 1,000-row sample and the only
                      sale source is electric-vehicle registrations, so they share almost no cars.
  asking vs auction   NOT estimable, for the same reason.
  sale vs auction     estimable: Washington State sale records against Cars & Bids auctions, on
                      the make-models and the age and mileage range where both actually exist.

Usage: .venv/bin/python analysis/price_types.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from drivers import EUROPE, absorb, md_table, ols  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "price_types_report.md"
# where sale and auction cars actually overlap; outside this the comparison is extrapolation
AGE_MIN, AGE_MAX = 3, 12
KM_MIN, KM_MAX = 25_000, 200_000
MIN_ROWS = 30


def load():
    d = pd.read_parquet(HERE.parent / "data" / "unified" / "listings.parquet",
                        columns=["source", "country", "price_type", "is_new", "make", "model",
                                 "year", "age_years", "mileage_km", "price_eur", "listing_date"])
    d = d[d["country"].eq("US") & ~d["is_new"].fillna(False).astype(bool)]
    d = d[d["price_eur"].between(1_000, 300_000)]
    return d.assign(mm=d["make"].astype(str) + "|" + d["model"].astype(str))


def overlap_audit(d):
    rows = []
    for a, b in [("asking", "sale"), ("asking", "auction"), ("sale", "auction")]:
        A, B = d[d["price_type"].eq(a)], d[d["price_type"].eq(b)]
        shared = set(A["mm"]) & set(B["mm"])
        na, nb = int(A["mm"].isin(shared).sum()), int(B["mm"].isin(shared).sum())
        rows.append({"pair": f"{a} vs {b}", "shared make-models": len(shared),
                     f"rows on the thin side": f"{min(na, nb):,}",
                     "rows on the thick side": f"{max(na, nb):,}",
                     "estimable": "yes" if min(na, nb) >= 1_000 else "**no**"})
    return pd.DataFrame(rows)


def gap(d):
    """log price on an auction dummy, within make-model and calendar month."""
    shared = set(d[d["price_type"].eq("sale")]["mm"]) & set(d[d["price_type"].eq("auction")]["mm"])
    s = d[d["mm"].isin(shared) & d["price_type"].isin(["sale", "auction"])].copy()
    s = s[s["listing_date"].ge("2021-08-01")]                       # Cars & Bids starts here
    s = s[s["age_years"].between(AGE_MIN, AGE_MAX) & s["mileage_km"].between(KM_MIN, KM_MAX)]
    s["month"] = s["listing_date"].dt.to_period("M").astype(str)
    months = sorted(s["month"].unique())
    x = pd.DataFrame({
        "auction": s["price_type"].eq("auction").to_numpy(float),
        "age_years": s["age_years"].to_numpy(float),
        "log_mileage": np.log(s["mileage_km"].to_numpy(float)),
    }, index=s.index)
    for m in months[1:]:
        x[f"month_{m}"] = (s["month"] == m).to_numpy(float)
    y = np.log(s["price_eur"].to_numpy(float))
    keep = x.notna().all(axis=1).to_numpy() & np.isfinite(y)
    y, x, s = y[keep], x[keep], s[keep]
    yc, Xc, n_cells = absorb(y, x.to_numpy(float), s["mm"])
    beta, se = ols(yc, Xc, n_cells)
    i = list(x.columns).index("auction")
    return beta[i], se[i], s, n_cells


def by_bucket(s):
    """A plain median comparison inside narrow age and mileage bands, as a sense check."""
    s = s.copy()
    s["age band"] = pd.cut(s["age_years"], [3, 5, 7, 9, 12],
                           labels=["3-5y", "5-7y", "7-9y", "9-12y"], right=False)
    rows = []
    for band, part in s.groupby("age band", observed=True):
        sale = part[part["price_type"].eq("sale")]["price_eur"]
        auc = part[part["price_type"].eq("auction")]["price_eur"]
        if len(sale) < MIN_ROWS or len(auc) < MIN_ROWS:
            continue
        rows.append({"age band": band, "sale cars": f"{len(sale):,}", "auction cars": f"{len(auc):,}",
                     "median sale €": f"{sale.median():,.0f}",
                     "median auction €": f"{auc.median():,.0f}",
                     "auction vs sale": f"{(auc.median() / sale.median() - 1) * 100:+.0f}%"})
    return pd.DataFrame(rows)


def main():
    d = load()
    audit = overlap_audit(d)
    every = pd.read_parquet(HERE.parent / "data" / "unified" / "listings.parquet",
                            columns=["price_type", "country", "source"])
    asking = every[every["price_type"].eq("asking")]
    europe_share = float(asking["country"].isin(EUROPE).mean())
    us_asking = int(asking["country"].eq("US").sum())
    print(audit.to_string(index=False))

    beta, se, s, n_cells = gap(d)
    pct = lambda b: (np.exp(b) - 1) * 100
    lo, hi = beta - 1.96 * se, beta + 1.96 * se
    n_auc = int(s["price_type"].eq("auction").sum())
    n_sale = int(s["price_type"].eq("sale").sum())
    print(f"\nauction vs sale: {pct(beta):+.1f}% ({pct(lo):+.1f}% to {pct(hi):+.1f}%) "
          f"on {n_sale:,} sale and {n_auc:,} auction cars, {n_cells} make-models")
    buckets = by_bucket(s)
    sales = d[d["price_type"].eq("sale")]
    cnb = d[d["source"].eq("us_carsandbids")]
    low_share = float((sales["price_eur"] < 5_000).mean() * 100)
    p1 = float(sales["price_eur"].quantile(0.01))
    raw_gaps = [float(v.rstrip("%")) for v in buckets["auction vs sale"]]

    report = [
        "# Asking, sale and auction prices are not the same number", "",
        "Generated by `analysis/price_types.py`, step 5 of `METHODOLOGY_multi_dataset.md`.", "",
        "The unified table holds three kinds of price. An advert price is what a seller asks, a sale "
        "price is what was actually paid, an auction price is what a car fetched under the hammer. "
        "A model fitted on adverts - which is what almost all of this collection is - cannot be read "
        "as a prediction of what a car will fetch until that gap is known.", "",
        "## What the data can and cannot measure", "", md_table(audit), "",
        "**Two of the three pairs cannot be estimated, and that is the main finding of this step.** "
        f"The collection has {len(asking) / 1e6:.1f} million advert prices, {europe_share:.0%} of "
        "them European, while both sale and auction prices are North American. Inside the US the "
        f"only advert sources are {us_asking:,} Marketcheck rows and the only sale source is "
        "electric-vehicle registrations, so they overlap on "
        f"{audit.loc[0, 'rows on the thin side']} cars - far too few to separate a price-type gap "
        "from noise. **No asking-to-sale adjustment factor can be honestly quoted from this "
        "data.**", "",
        "## The one pair that works: auction against recorded sale", "",
        f"Comparing Washington State sale records with Cars & Bids auction results on the "
        f"{n_cells} make-models both cover, restricted to the age and mileage range where both "
        f"actually have cars ({AGE_MIN}-{AGE_MAX} years, {KM_MIN:,}-{KM_MAX:,} km), with a fixed "
        "effect per make-model and per calendar month:", "",
        f"- **A car sold at auction fetches {pct(beta):+.1f}% against an equivalent recorded sale** "
        f"(95% range {pct(lo):+.1f}% to {pct(hi):+.1f}%), on {n_sale:,} sale and {n_auc:,} auction "
        "cars.", "",
        "The same comparison without any model, as plain medians inside age bands:", "",
        md_table(buckets), "",
        f"Raw, the gap looks like {min(raw_gaps):+.0f}% to {max(raw_gaps):+.0f}%. Controlling for "
        "model, mileage and month cuts it to "
        f"{pct(beta):+.1f}%, so most of the raw difference is simply that Cars & Bids sells better "
        "cars than the registration file records.", "",
        "### Do not read this as \"auctions pay more\"", "",
        "The sign is the opposite of what anyone would expect - trade auctions normally clear below "
        "retail - and the two likely reasons are both about measurement rather than economics:", "",
        "1. **Cars & Bids is a curated enthusiast marketplace, not a trade auction.** Within the same "
        "make and model it lists cars people have chosen to present well: special trims, careful "
        "owners, documented history. Neither source records condition, so nothing in the regression "
        "can absorb that.",
        "2. **Washington sale prices are self-reported on a title transfer, and that transfer sets "
        "the excise tax due.** There is a standing incentive to report a low number on a private "
        f"sale. In this data {low_share:.1f}% of used sales are under EUR 5,000 and the bottom 1% "
        f"sit under EUR {p1:,.0f}, which is low even for an old electric car (prices between "
        "EUR 1,000 and EUR 300,000 kept).", "",
        "So the honest reading is not a channel-choice rule. **What this pair does establish is that "
        "price types differ by far more than noise even after controlling for the car**, which is "
        "the reason `build_unified.py` keeps `price_type` as a column and never pools them. The "
        "size of the gap here is specific to these two sources.", "",
        "## Limits", "",
        "- **The two sources are not the same kind of car.** Washington's records are electric "
        "vehicles; Cars & Bids is an enthusiast auction site. The overlap is the models that are "
        "both, which skews toward Teslas, Porsches and large SUVs rather than an ordinary fleet.",
        f"- **Common support is the real constraint.** Across the whole of both sources the median "
        f"Cars & Bids car is {cnb['age_years'].median():.0f} years old with "
        f"{cnb['mileage_km'].median():,.0f} km, while the median sale car is "
        f"{sales['age_years'].median():.0f} years old with {sales['mileage_km'].median():,.0f} km. "
        "Restricting to the band where both exist is what makes the comparison meaningful and is "
        "also what makes it narrow.",
        "- **An auction price and a sale price differ for more reasons than the channel.** Cars sent "
        "to auction may be harder to sell, or better kept, and neither source records condition.",
        "- **US only, and one US state for the sale side.** This gap should not be carried over to "
        "European resale without saying that it was measured somewhere else.", "",
        "## What would fix the gap in the collection", "",
        "One European source with realised transaction prices would unlock the pair that matters. "
        "Candidates already identified and rejected on cost or access in `DATASETS.md` include the "
        "dealer-auction datasets; a national registration file that records a sale price, in the way "
        "Washington State does, would be the equivalent European asset.", "",
    ]
    OUT.write_text("\n".join(report))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
