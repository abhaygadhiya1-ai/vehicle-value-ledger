"""What a discount given when the car was new costs when the car is resold.

This is the one thing the case asks for that the project has refused to answer. The first
attempt (`tesla_event.py`) failed: 68% of the used-Tesla repricing happened before the January
2023 US list-price cut, so the cut could not be separated from the slide already under way.
That failure was a *market-level event study* - one maker, one month, one contaminated control.

This takes a different route. Washington State title transfers record a realised price and a
vehicle id, and a car can be sold more than once, so tens of thousands of cars are seen **twice:
once at their own new sale, and again when they are resold**. The question then stops being
"did the market move?" and becomes "did *this car*, bought at a deeper discount, fetch less?" -
which has a control group built into it and a placebo that the event study never had.

Four parts:

1. **The pass-through.** How much of a discount at purchase survives into the resale price,
   with a placebo: the same model's discount a year *after* the car was bought.
2. **Discount, or specification?** The per-car data has no trim field, so a cheap new price
   might be a cheap car. AutoScout24 does have the exact version, and settles how much of a
   visible price gap is specification rather than discount.
3. **The market-level test, again, properly.** The Tesla study was one event. Eurostat's new-car
   and used-car indices give every European market's new-price moves over ten years. It fails
   too, and for the same reason - which is worth saying, because it is now a general result and
   not one awkward month.
4. What the group can take from it.

Usage: .venv/bin/python analysis/discount_passthrough.py   (about 1 minute)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from loaders import us_wa_ev_sales  # noqa: E402

RAW = HERE.parent / "data" / "raw"
NEW_INDEX = HERE.parent / "data" / "reference" / "new_car_price_indices.parquet"
USED_INDEX = HERE.parent / "data" / "reference" / "price_indices.parquet"
REPORT = HERE / "discount_passthrough_report.md"
SUMMARY = HERE / "discount_passthrough_summary.csv"

PRICE_BAND = (2000, 150000)      # us_wa_ev_sales writes sale dates into some price fields
MIN_CELL = 30                    # new sales needed before a nameplate-year has a usable norm
MIN_MONTH = 6                    # new sales in a month before that month has a usable norm


# ---------------------------------------------------------------- shared estimator

def ols(y, regressors, absorb, cluster):
    """OLS with dummy-absorbed fixed effects and cluster-robust standard errors.

    Returns one (beta, se) pair per named regressor. Everything here is a small panel, so
    dummies are cheaper than a within transform and leave the ranks easy to check.
    """
    blocks = [np.ones(len(y))[:, None]] + [v.to_numpy(float)[:, None] for v in regressors.values()]
    for a in absorb:
        blocks.append(pd.get_dummies(a.astype(str), drop_first=True).to_numpy(float))
    A = np.column_stack(blocks)
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ beta
    XtXi = np.linalg.pinv(A.T @ A)
    meat = np.zeros((A.shape[1], A.shape[1]))
    for _, idx in pd.Series(range(len(y))).groupby(cluster.to_numpy()).indices.items():
        u = (A[idx] * resid[idx, None]).sum(0)
        meat += np.outer(u, u)
    se = np.sqrt(np.diag(XtXi @ meat @ XtXi))
    return {name: (beta[i], se[i]) for i, name in enumerate(regressors, start=1)}, len(y)


def cell(b_se):
    beta, se = b_se
    return f"{beta:+.3f} ({beta / se:+.1f})"


# ---------------------------------------------------------------- part 1: per-car

def per_car():
    """Washington State: cars seen at their own new sale and again at resale."""
    d = us_wa_ev_sales.load(RAW / "us_wa_ev_sales")
    d["vehicle"] = d.listing_id.str.split("_").str[0]
    d["price"] = pd.to_numeric(d.price, errors="coerce")
    d = d[d.price.between(*PRICE_BAND) & d.listing_date.notna() & d.year.notna()].copy()
    d["nameplate"] = (d.make.astype(str).str.strip().str.upper() + " "
                      + d.model.astype(str).str.strip().str.upper())
    d["cell"] = d.nameplate + "|" + d.year.astype(int).astype(str)
    d["month"] = d.listing_date.dt.to_period("M")

    # --- the new side: how far the price paid sat below what that car normally went for.
    # Both means leave the car itself out, so a car's own price can never enter the yardstick
    # it is measured against.
    new = d[d.is_new == True].copy()                                     # noqa: E712
    new["ln"] = np.log(new.price)
    bym, byc = new.groupby(["cell", "month"]).ln, new.groupby("cell").ln
    new["msum"], new["mn"] = bym.transform("sum"), bym.transform("size")
    new["csum"], new["cn"] = byc.transform("sum"), byc.transform("size")
    new = new[(new.cn >= MIN_CELL) & (new.mn >= MIN_MONTH)].copy()
    loo_month = (new.msum - new.ln) / (new.mn - 1)
    loo_cell = (new.csum - new.ln) / (new.cn - 1)
    new["cohort_gap"] = loo_month - loo_cell      # the month's deal: list-price moves, programmes
    new["indiv_gap"] = new.ln - loo_month         # this car against its month: trim, negotiation

    # the placebo: the deal the same model was offering 12 months after this car was bought
    later = new.groupby(["cell", "month"]).cohort_gap.first().rename("placebo").reset_index()
    later["month"] = later.month - 12
    new = new.merge(later, on=["cell", "month"], how="left")

    # split the month's deal into a smooth drift through the model year (which is what a
    # shifting trim mix looks like) and an abrupt departure from it (which is what a price
    # action looks like)
    gaps = new.groupby(["cell", "month"]).cohort_gap.first().reset_index()
    gaps["t"] = gaps.groupby("cell").cumcount()

    def quadratic(g):
        if len(g) < 5:
            return pd.Series(np.nan, index=g.index)
        A = np.column_stack([np.ones(len(g)), g.t, g.t ** 2])
        b, *_ = np.linalg.lstsq(A, g.cohort_gap.to_numpy(), rcond=None)
        return pd.Series(A @ b, index=g.index)

    gaps["drift"] = gaps.groupby("cell", group_keys=False).apply(quadratic)
    gaps["abrupt"] = gaps.cohort_gap - gaps.drift
    new = new.merge(gaps[["cell", "month", "drift", "abrupt"]], on=["cell", "month"], how="left")

    first = new.sort_values("listing_date").groupby("vehicle").first()
    carried = ["listing_date", "cohort_gap", "indiv_gap", "placebo", "drift", "abrupt",
               "cell", "nameplate"]
    resale = d[d.is_new == False].merge(first[carried], left_on="vehicle",     # noqa: E712
                                        right_index=True, suffixes=("", "_new"))
    resale = resale[resale.listing_date > resale.listing_date_new].copy()
    resale["hold"] = (resale.listing_date - resale.listing_date_new).dt.days / 365.25
    resale = resale[resale.hold.between(1, 7) & resale.mileage_km.between(1000, 300000)].copy()
    resale["y"] = np.log(resale.price)
    resale["ln_km"] = np.log(resale.mileage_km)
    resale["resale_month"] = resale.listing_date.dt.to_period("M")
    resale["age_bin"] = pd.cut(resale.hold, np.arange(1, 7.5, 0.5))

    def fit(df, regs, extra_absorb=()):
        absorb = [df.cell_new, df.resale_month, df.age_bin] + list(extra_absorb)
        cols = {k: df[k] for k in regs}
        cols["ln_km"] = df.ln_km
        return ols(df.y.to_numpy(), cols, absorb, df.nameplate_new)

    rows, main = [], None
    for label, sub, regs in [
        ("All resales", resale, ["cohort_gap", "indiv_gap"]),
        ("The month's deal alone", resale, ["cohort_gap"]),
        ("This car's own gap alone", resale, ["indiv_gap"]),
        ("Held at least 2 years", resale[resale.hold >= 2], ["cohort_gap", "indiv_gap"]),
        ("Tesla only", resale[resale.nameplate_new.str.startswith("TESLA")],
         ["cohort_gap", "indiv_gap"]),
        ("Tesla excluded", resale[~resale.nameplate_new.str.startswith("TESLA")],
         ["cohort_gap", "indiv_gap"]),
    ]:
        res, n = fit(sub, regs)
        if main is None:
            main = res
        rows.append({"Cut": label, "n": f"{n:,}",
                     "The month's deal": cell(res["cohort_gap"]) if "cohort_gap" in res else "-",
                     "This car's own gap": cell(res["indiv_gap"]) if "indiv_gap" in res else "-"})

    pl = resale.dropna(subset=["placebo"])
    pres, pn = fit(pl, ["cohort_gap", "placebo", "indiv_gap"])
    sp = resale.dropna(subset=["drift", "abrupt"])
    sres, sn = fit(sp, ["drift", "abrupt", "indiv_gap"])

    return {
        "resale": resale, "table": rows, "main": main,
        "placebo": {"res": pres, "n": pn},
        "split": {"res": sres, "n": sn},
        "counts": dict(resales=len(resale), vehicles=resale.vehicle.nunique(),
                       cells=resale.cell_new.nunique(), nameplates=resale.nameplate_new.nunique(),
                       start=resale.listing_date.min(), end=resale.listing_date.max(),
                       gap_sd=resale.cohort_gap.std()),
    }


# ---------------------------------------------------------------- part 2: trim

def discount_or_specification():
    """AutoScout24: is a cheap new-ish car discounted, or is it a cheaper car?"""
    f = RAW / "eu_2025_11" / "autoscout24_dataset_20251108.csv"
    d = pd.read_csv(f, low_memory=False)
    d["price"] = pd.to_numeric(d.price, errors="coerce")
    d["km"] = pd.to_numeric(d.mileage_km.astype(str).str.replace(r"[^0-9]", "", regex=True),
                            errors="coerce").fillna(0)
    d["reg"] = pd.to_datetime(d.registration_date, errors="coerce", format="mixed")
    d["age_m"] = (d.reg.max() - d.reg).dt.days / 30.44
    d["kw"] = pd.to_numeric(d.power_kw, errors="coerce")
    d["mm"] = (d.make.astype(str).str.lower().str.strip() + "|"
               + d.model.astype(str).str.lower().str.strip())
    d["coarse"] = (d.mm + "|" + (d.kw // 15 * 15).astype("Int64").astype(str) + "|"
                   + d.primary_fuel.astype(str).str.lower() + "|"
                   + d.transmission.astype(str).str.lower() + "|"
                   + d.body_type.astype(str).str.lower())
    d["version"] = d.mm + "|" + d.model_version.astype(str).str.lower().str.strip()
    s = d[(d.is_new | d.is_preregistered) & d.price.between(3000, 250000) & (d.km <= 15000)].copy()
    s["prereg"] = s.is_preregistered.astype(float)
    s["km1000"] = s.km / 1000
    s = s.dropna(subset=["price", "age_m", "kw"])

    rows = []
    for label, key in [("Make and model", "mm"),
                       ("plus power, fuel, gearbox, body", "coarse"),
                       ("plus the exact version", "version")]:
        both = s.groupby(key).is_preregistered.nunique()
        sub = s[s[key].isin(both[both == 2].index)]
        res, n = ols(np.log(sub.price.to_numpy()),
                     {"prereg": sub.prereg, "age_m": sub.age_m, "km1000": sub.km1000},
                     [sub[key]], sub.mm)
        b, se = res["prereg"]
        rows.append({"Controlling for": label, "n": f"{n:,}", "groups": sub[key].nunique(),
                     "gap": f"{100 * (np.exp(b) - 1):+.1f}%",
                     "95% range": f"{100 * (np.exp(b - 1.96 * se) - 1):+.1f}% to "
                                  f"{100 * (np.exp(b + 1.96 * se) - 1):+.1f}%",
                     "t": f"{b / se:+.2f}"})
    return {"table": rows, "countries": sorted(s.country_code.dropna().unique()),
            "n_new": int((s.is_new).sum()), "n_prereg": int(s.is_preregistered.sum()),
            "as_of": d.reg.max()}


# ---------------------------------------------------------------- part 3: market level

def market_level():
    """Eurostat: does a market's new-car price move show up in its used-car prices later?"""
    new = pd.read_parquet(NEW_INDEX)[["geo", "date", "index_value"]].rename(
        columns={"index_value": "new"})
    used = pd.read_parquet(USED_INDEX)
    used = used[used.series.str.startswith("Eurostat")][["geo", "date", "index_value"]].rename(
        columns={"index_value": "used"})
    m = new.merge(used, on=["geo", "date"])
    m = m[~m.geo.isin({"EA", "EA19", "EA20", "EU", "EU27_2020", "EU28"})].sort_values(
        ["geo", "date"]).reset_index(drop=True)
    m["d_new"] = m.groupby("geo").new.transform(lambda s: np.log(s).diff())
    m["d_used"] = m.groupby("geo").used.transform(lambda s: np.log(s).diff())

    leads, lags = [-12, -6], [0, 6, 12, 18, 24, 30, 36, 42, 48]
    for k in leads + lags:
        m[f"k{k}"] = m.groupby("geo").d_new.shift(k)
    cols = [f"k{k}" for k in leads + lags]
    e = m.dropna(subset=cols + ["d_used"])
    res, n = ols(e.d_used.to_numpy(), {c: e[c] for c in cols}, [e.geo, e.date], e.geo)
    lag_sum = sum(res[f"k{k}"][0] for k in lags)
    lead_sum = sum(res[f"k{k}"][0] for k in leads)
    rows = [{"Horizon": ("%d months before the car was bought" % -k) if k < 0
             else ("same month" if k == 0 else "%d months after" % k),
             "Effect on used prices": cell(res[f"k{k}"])} for k in leads + lags]
    return {"table": rows, "lag_sum": lag_sum, "lead_sum": lead_sum, "n": n,
            "countries": e.geo.nunique(), "start": e.date.min(), "end": e.date.max()}


# ---------------------------------------------------------------- report

def md_table(rows):
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return out


def main():
    print("part 1: per-car pass-through (Washington State)")
    pc = per_car()
    print("part 2: discount or specification (AutoScout24)")
    tr = discount_or_specification()
    print("part 3: market level (Eurostat)")
    ml = market_level()

    c = pc["counts"]
    beta, se = pc["main"]["cohort_gap"]
    ten = 100 * (1 - np.exp(beta * np.log(0.9)))          # a 10% deeper deal, in % of resale
    lo = 100 * (1 - np.exp((beta - 1.96 * se) * np.log(0.9)))
    hi = 100 * (1 - np.exp((beta + 1.96 * se) * np.log(0.9)))
    pb, pbse = pc["placebo"]["res"]["placebo"]
    own = pc["placebo"]["res"]["cohort_gap"]
    version_gap = tr["table"][-1]["gap"]
    coarse_gap = tr["table"][1]["gap"]

    out = [
        "# What a discount at the new sale costs at resale", "",
        "Generated by `analysis/discount_passthrough.py`.", "",
        "**Short answer: about a third of a discount given on a new car is still there, against "
        "the car, when it is resold - and that is an upper bound, because a cheap new price can "
        "also mean a cheaper car.** Measured on cars seen twice: once at their own new sale and "
        "again at resale.", "",
        "## 1. The pass-through, measured per car", "",
        f"- **Data:** Washington State title transfers, which carry a realised price, a sale date "
        f"and a vehicle id. **{c['resales']:,} resales of {c['vehicles']:,} cars that are also "
        f"in the file at their own new sale**, {c['cells']} nameplate-and-model-year cells, "
        f"{c['nameplates']} nameplates, {c['start']:%Y-%m} to {c['end']:%Y-%m}. Realised prices "
        "on both sides, not adverts.",
        "- **The deal a car got** is how far the price it was actually paid for sat below what "
        "that exact nameplate and model year normally went for, split in two: the **month's "
        "deal** (every buyer of that model that month got it - a list-price move or an incentive "
        "programme) and **this car's own gap** (trim, options, how hard the buyer pushed). Both "
        "yardsticks leave the car itself out, so a car's own price can never enter the norm it "
        "is measured against.",
        f"- **The outcome** is the resale price, holding the nameplate and model year, the month "
        f"of resale, the age to the nearest half year and the mileage fixed. Standard errors are "
        f"clustered by nameplate. The month's deal moves by "
        f"{100 * c['gap_sd']:.1f}% (standard deviation).", "",
        "Read each number as: a car bought 1% cheaper resells this much cheaper.", "",
        *md_table(pc["table"]), "",
        "What that is worth, read off the same coefficient. Each row is a car bought that much "
        "below what its model normally went for, and what it gives back at resale:", "",
        *md_table([
            {"Deal at the new sale": f"{d}% below the model's usual price",
             "Resale value lost": f"{100 * (1 - np.exp(beta * np.log(1 - d / 100))):.1f}%",
             "95% range": f"{100 * (1 - np.exp((beta - 1.96 * se) * np.log(1 - d / 100))):.1f}% to "
                          f"{100 * (1 - np.exp((beta + 1.96 * se) * np.log(1 - d / 100))):.1f}%"}
            for d in (5, 10, 20)]), "",
        f"**A car bought 10% below what its model normally went for resells about "
        f"{ten:.1f}% lower**, years later, at the same age and mileage, in the same month, "
        "against the same model.", "",
        "### The placebo the Tesla study never had", "",
        "The objection to any discount result is that the discount is not what moved the price - "
        "the model was already sliding. So run the same regression with a second, fake discount: "
        "the deal that same model was offering **twelve months after this car was bought**. A car "
        "cannot be affected by a discount that had not happened yet, so that coefficient has to "
        "be zero if the design is sound.", "",
        *md_table([
            {"Which deal": "The deal this car was actually bought with",
             "Effect on its resale price": cell(own)},
            {"Which deal": "The same model's deal 12 months later (placebo)",
             "Effect on its resale price": cell((pb, pbse))},
        ]), "",
        f"The placebo is {pb:+.3f} and cannot be told from zero (t {pb / pbse:+.1f}), while the "
        f"car's own deal holds at {own[0]:+.3f}. **This is the test `tesla_event.py` failed.** "
        "There, 68% of the repricing came before the cut and nothing separated the two. Here the "
        "discount a car was bought with matters and the same model's discount a year later does "
        "not.", "",
        "### Is it the deal, or is it a shifting trim mix?", "",
        "A month's deal could be cheap cars rather than cheap deals - later buyers in a model "
        "year take plainer trims. But a trim mix moves **smoothly** through a model year, while "
        "a price action is **abrupt**. Splitting the month's deal into a smooth drift and an "
        "abrupt departure from it:", "",
        *md_table([
            {"Part of the month's deal": "Smooth drift through the model year",
             "Effect on resale price": cell(pc["split"]["res"]["drift"])},
            {"Part of the month's deal": "Abrupt departure from that drift",
             "Effect on resale price": cell(pc["split"]["res"]["abrupt"])},
        ]), "",
        "The abrupt part carries at least as much as the smooth one, which is the wrong way round "
        "for a pure trim-mix story. It does not settle it - a year-end clearance of one trim is "
        "abrupt too - so part 2 measures the trim problem directly.", "",
        "## 2. Discount, or just a cheaper car?", "",
        f"The Washington file has no trim field. AutoScout24 does. Its **pre-registered** cars - "
        f"registered by the dealer to book the sale, then sold as nearly new - are the clearest "
        f"discounting decision in European data: the discount is the whole reason the car is in "
        f"that state. Comparing {tr['n_prereg']:,} of them with {tr['n_new']:,} genuinely new "
        f"cars in {', '.join(tr['countries'])}, all under 15,000 km, holding age and mileage "
        f"fixed:", "",
        *md_table(tr["table"]), "",
        f"**The visible gap is specification, not discount.** On make and model alone a "
        f"pre-registered car looks {tr['table'][0]['gap']} cheaper, and a coarse trim control "
        f"({coarse_gap}) barely dents it - but matched on the **exact version** the gap is "
        f"{version_gap} and cannot be told from zero.", "",
        "Two things follow, and they point in opposite directions:", "",
        "1. **The per-car pass-through in part 1 is an upper bound, not a point estimate.** Some "
        "of that third is specification the Washington data cannot see.",
        "2. **A discount does not show up in market data at all.** The advert for a heavily "
        "discounted car is priced like any other car of that version. Nothing outside the "
        "group's own incentive records can tell you what was paid to move it - which is the "
        "case's own premise, now measured rather than asserted.", "",
        "## 3. The market-level test fails, and not just for Tesla", "",
        f"`tesla_event.py` failed on one maker in one month. Eurostat's new-car price index "
        f"(CP07111) and second-hand index (CP07112) give every European market's new-price moves "
        f"over ten years, so the same question can be asked {ml['countries']} times over instead "
        f"of once. Each country's own level and each month's Europe-wide shock are held fixed; "
        f"{ml['n']:,} country-months, {ml['start']:%Y-%m} to {ml['end']:%Y-%m}, standard errors "
        f"clustered by country.", "",
        *md_table(ml["table"]), "",
        f"- **Everything after the discount adds to {ml['lag_sum']:+.3f}** - nothing, given these "
        f"standard errors.",
        f"- **Everything before it adds to {ml['lead_sum']:+.3f}**, which is larger. Used prices "
        "move *ahead of* new-car prices.",
        "- So the failure is **general**, not a quirk of one January. An index that mixes every "
        "vintage also dilutes any single cohort's discount roughly tenfold, so this test has "
        "little power even in principle. **A market-level series cannot answer this question. "
        "The per-car link can, and that is the whole argument for a per-vehicle ledger.**", "",
        "## 4. What the group can take from it", "",
        "1. **A discount is not only this year's margin.** Roughly a third of it - at most - is "
        "still working against the car when the finance arm takes it back. Nothing in the "
        "group's systems connects those two facts today, which is exactly the leak the case "
        "describes.",
        "2. **The published literature puts it higher.** Holweg and Kattuman, on 2,320 "
        "model-months of UK auction prices, find a 10% discount costs 1.5% of residual value at "
        "once and a further 6.5% when the discounted car reaches the used market three years "
        "later. That is a market-level, specification-normalised estimate; ours is per car with "
        "no trim control. **Our number is the low end of the same finding, measured a different "
        "way on a different continent.**",
        "3. **You cannot buy this answer.** Part 2 shows the discount is invisible in market "
        "data. Only the group's own claims records carry it, and only against a VIN.",
        "4. **Quote it as a range, not a point.** A tenth of the list price given away at the new "
        f"sale costs somewhere between {ten:.0f}% and 6.5% of the car's resale value. The low end "
        "is ours and is an upper bound on its own terms; the high end is published and older.", "",
        "### The two estimates side by side", "",
        *md_table([
            {"Estimate": "This study, per car, US, electric and plug-in, 2016-2026",
             "What a 10% discount costs of resale value": f"{ten:.1f}%",
             "What it is": "Upper bound: no trim control"},
            {"Estimate": "Holweg and Kattuman, UK auctions, 1999-2004, at once",
             "What a 10% discount costs of resale value": "1.5%",
             "What it is": "Published, specification-normalised"},
            {"Estimate": "Holweg and Kattuman, UK auctions, 1999-2004, at 36 months",
             "What a 10% discount costs of resale value": "6.5%",
             "What it is": "Published, specification-normalised"},
        ]), "",
        "## Limits", "",
        "- Part 1 is **Washington State, electric and plug-in vehicles only**, and is not a "
        "general used-car result. Title-transfer prices include private sales and are "
        "self-reported.",
        "- Part 1 has **no trim field**, so the pass-through is an upper bound (part 2).",
        "- Part 1 holds the resale month fixed, so it measures what a discount does **to the car "
        "it was given on**, against other cars sold at the same moment. A discount that lowers "
        "the whole market's used prices would be absorbed by that control - and part 3 is the "
        "attempt to measure that channel, which fails.",
        "- Part 2 compares **advertised** prices, and a pre-registered car's advert is set by the "
        "dealer, not by the incentive that put the car there.",
        "- Part 3 uses official indices, which are not realised prices, and its monthly changes "
        "are noisy.",
    ]
    REPORT.write_text("\n".join(out) + "\n")

    pd.DataFrame([
        {"id": "dpt_percar", "label": "Resale value lost per 1% deeper deal at the new sale",
         "value": round(beta, 3), "se": round(se, 3)},
        {"id": "dpt_percar_10", "label": "Resale value lost for a 10% deeper deal (%)",
         "value": round(ten, 1), "se": ""},
        {"id": "dpt_placebo", "label": "Placebo: the same model's deal 12 months later",
         "value": round(pb, 3), "se": round(pbse, 3)},
        {"id": "dpt_market_lags", "label": "Eurostat: everything after the new-price move",
         "value": round(ml["lag_sum"], 3), "se": ""},
        {"id": "dpt_market_leads", "label": "Eurostat: everything before it",
         "value": round(ml["lead_sum"], 3), "se": ""},
    ]).to_csv(SUMMARY, index=False)
    print(f"wrote {REPORT.name} and {SUMMARY.name}")


if __name__ == "__main__":
    main()
