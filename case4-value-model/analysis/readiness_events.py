"""Layer 3: is there a spike in cars coming to market when a contract ends? No.

This is the layer the readiness engine cannot have, and the measurement that says so. It was run
once before and written into `HANDOFF.md` as prose. That is not good enough for a figure that goes
on a slide - the project's own trap list says typed figures go stale - so it is a script now, with
a report `check_assumptions.py` can pin a number to.

A three-year contract ending should show up as a bulge of cars advertised at 36 months old. The
test is whether the number of adverts at 36 months is above what the ages either side lead you to
expect.

Two things have to be handled or the answer is nonsense:

  1. **Whole-year ages.** Most sources record a registration *year*, so every car in them lands on
     an exact multiple of twelve months and the test reads a spike of thousands of per cent at 24,
     36, 48 and 60. It is an artefact of the calendar, not a lease. Only sources that record a
     registration month can answer the question, and part 2 shows what happens if you forget.
  2. **Registration seasonality.** A snapshot taken in one month maps age-in-months onto calendar
     month of registration one for one, so a country that registers heavily in January puts a bump
     at 12, 24, 36 and 48 months for reasons that have nothing to do with a contract. This is not
     in the handoff's account of the result and it matters: it is the confounder most likely to
     manufacture the spike we are looking for. It is absorbed with a calendar-month effect.

Usage: .venv/bin/python analysis/readiness_events.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import md_table  # noqa: E402

HERE = Path(__file__).parent
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
OUT = HERE / "readiness_events_report.md"
TABLE = HERE / "readiness_events_excess.csv"

AGE_MIN, AGE_MAX = 12, 96      # a year old to eight years old
EVENTS = (24, 36, 48, 60)      # the contract lengths a lease book actually uses
HALF = 1                       # an event is the month itself and one either side: remarketing
DEGREE = 5                     # how flexible the underlying age trend is allowed to be
MONTH_PRECISE = 0.5            # a source counts as month-precise if over half its ages are not whole


def load():
    cols = ["source", "country", "year", "age_years", "price_type", "is_new", "price_eur",
            "mileage_km", "listing_date"]
    d = pd.read_parquet(LISTINGS, columns=cols)
    d = d[d["price_type"].eq("asking") & ~d["is_new"].fillna(False).astype(bool)]
    d = d[d["age_years"].between(0.5, 30) & d["price_eur"].between(500, 200_000)]
    d = d.dropna(subset=["age_years", "listing_date"])
    d["age_months"] = (d["age_years"] * 12).round().astype(int)
    return d


def month_precise(d):
    """Which sources record a registration month rather than only a year."""
    share = d.groupby("source")["age_years"].apply(
        lambda s: float((s.round(4) % 1 != 0).mean()))
    return sorted(share[share > MONTH_PRECISE].index)


def excess(d, label, seasonal=True):
    """Adverts by age in months against a smooth trend, with the event months dummied out.

    log(count) = a flexible curve in age + which source + which calendar month the car was
    registered in + one term per contract length. The contract terms are what we are after; the
    calendar term is there so that a country's registration peak cannot be mistaken for one.
    """
    d = d[d["age_months"].between(AGE_MIN, AGE_MAX)]
    g = (d.groupby(["source", "age_months"]).size().rename("n").reset_index())
    g = g[g["n"] > 0]
    if len(g) < 60:
        return None

    # the calendar month a car of this age at this snapshot was registered in
    snap = d.groupby("source")["listing_date"].max()
    g["reg_month"] = [
        ((pd.Timestamp(snap[s]).month - 1 - m) % 12) + 1
        for s, m in zip(g["source"], g["age_months"])]

    a = g["age_months"].to_numpy(float)
    a = (a - a.mean()) / a.std()
    parts = [np.ones(len(g))] + [a ** k for k in range(1, DEGREE + 1)]
    names = ["const"] + [f"age^{k}" for k in range(1, DEGREE + 1)]
    for s in sorted(g["source"].unique())[1:]:
        parts.append((g["source"] == s).to_numpy(float))
        names.append(f"source={s}")
    if seasonal:
        for m in range(2, 13):
            parts.append((g["reg_month"] == m).to_numpy(float))
            names.append(f"regmonth={m}")
    for e in EVENTS:
        parts.append(g["age_months"].between(e - HALF, e + HALF).to_numpy(float))
        names.append(f"event={e}")

    X = np.column_stack(parts)
    y = np.log(g["n"].to_numpy(float))
    w = g["n"].to_numpy(float)
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    resid = y - X @ beta
    dof = max(len(g) - X.shape[1], 1)
    cov = float((w * resid ** 2).sum() / dof) * np.linalg.pinv((X * w[:, None]).T @ X)
    se = np.sqrt(np.diag(cov))
    out = []
    for e in EVENTS:
        i = names.index(f"event={e}")
        out.append({"which": label, "event_months": e,
                    "excess": float(np.exp(beta[i]) - 1),
                    "lo": float(np.exp(beta[i] - 1.96 * se[i]) - 1),
                    "hi": float(np.exp(beta[i] + 1.96 * se[i]) - 1)})
    return pd.DataFrame(out), int(d.shape[0]), sorted(d["source"].unique())


def main():
    d = load()
    precise = month_precise(d)
    print(f"month-precise sources: {precise}")

    good, n_good, _ = excess(d[d["source"].isin(precise)], "month-precise sources")
    # no calendar control here on purpose: for a whole-year source the calendar month is the
    # age modulo twelve, so the control would absorb the very artefact this is meant to show
    bad, n_bad, _ = excess(d[~d["source"].isin(precise)], "whole-year sources",
                           seasonal=False)
    noseas, _, _ = excess(d[d["source"].isin(precise)], "month-precise, no calendar control",
                          seasonal=False)

    fmt = lambda x: f"{x:+.1%}"
    lines = [
        "# Layer 3: the contract-end spike that is not there",
        "",
        "A three-year lease ending should put a bulge of cars on the market at 36 months old. "
        "This looks for it, and does not find it. **That is the result, and it is the reason the "
        "readiness engine has three layers rather than four.**",
        "",
        "The test fits the number of adverts at each age in months to a smooth curve in age, plus "
        "which source the advert came from, plus the calendar month the car was registered in, "
        "plus one term for each contract length. The contract term is the excess over what the "
        "ages either side lead you to expect.",
        "",
        "## The answer",
        "",
        f"{n_good:,} European adverts from the {len(precise)} sources that record a registration "
        f"month: `{'`, `'.join(precise)}`.",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Contract length": good["event_months"].map("{} months".format),
        "Excess adverts": good["excess"].map(fmt),
        "Low": good["lo"].map(fmt),
        "High": good["hi"].map(fmt),
    })))
    # the one apparent positive has to survive being taken apart before it is believed
    per_source = []
    for src in precise:
        g, n, _ = excess(d[d["source"] == src], src)
        if g is not None:
            per_source.append({"source": src, "n": n,
                               **{int(r.event_months): r.excess for r in g.itertuples()}})
    per_source = pd.DataFrame(per_source)

    specs = []
    global DEGREE, HALF
    keep = (DEGREE, HALF)
    for deg in (3, 4, 5, 6):
        for half in (0, 1, 2):
            DEGREE, HALF = deg, half
            g, _, _ = excess(d[d["source"].isin(precise)], "spec")
            specs.append({"trend": deg, "window": half,
                          **{int(r.event_months): r.excess for r in g.itertuples()}})
    DEGREE, HALF = keep
    specs = pd.DataFrame(specs)

    at36 = good.loc[good["event_months"] == 36].iloc[0]
    at60 = good.loc[good["event_months"] == 60].iloc[0]
    lines += [
        "",
        f"**At 36 months, the contract length a lease book is built on, there is no bulge: "
        f"{fmt(at36['excess'])} ({fmt(at36['lo'])} to {fmt(at36['hi'])}).** A car coming off a "
        "three-year lease is remarketed weeks to months later, at a spread of ages, and the event "
        "smears away.",
        "",
        f"The one positive reading is {fmt(at60['excess'])} at 60 months, and the next two tables "
        "are what happens when it is taken apart.",
        "",
        "## Taking the 60-month reading apart",
        "",
        "**One source produces all of it.**",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Source": per_source["source"],
        "Adverts": per_source["n"].map("{:,}".format),
        "24 months": per_source[24].map(fmt),
        "36 months": per_source[36].map(fmt),
        "48 months": per_source[48].map(fmt),
        "60 months": per_source[60].map(fmt),
    })))
    worst = per_source.loc[per_source[60].idxmax()]
    others = per_source[per_source["source"] != worst["source"]]
    lines += [
        "",
        f"`{worst['source']}` reads {fmt(worst[60])} at 60 months; the other two read "
        + " and ".join(fmt(v) for v in others[60]) + ". That source is a single day's scrape "
        "whose registration years are lumpy - it carries several times as many cars of one "
        "registration year as of its neighbours - and in a November 2025 snapshot that lump sits "
        "at about sixty months old. **It is the composition of one scrape, not a contract.**",
        "",
        "**And the specification moves it.** The trend column is how flexible the underlying age "
        "curve is; the window column is how many months either side of the contract date count as "
        "the event.",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Trend": specs["trend"], "Window": specs["window"],
        "24 months": specs[24].map(fmt), "36 months": specs[36].map(fmt),
        "48 months": specs[48].map(fmt), "60 months": specs[60].map(fmt),
    })))
    lines += [
        "",
        f"Across twelve specifications the 36-month reading is negative in every one "
        f"({fmt(specs[36].min())} to {fmt(specs[36].max())}), and the 60-month reading swings from "
        f"{fmt(specs[60].min())} to {fmt(specs[60].max())}. **A result that needs one source and "
        "one specification is not a result.**",
        "",
        "## The trap, shown rather than described",
        "",
        f"The same test on the sources that record only a registration *year* ({n_bad:,} "
        "adverts), without the calendar control - which for those sources would absorb the very "
        "thing being shown, because their calendar month *is* their age. Every car in them lands "
        "on a whole number of years:",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Contract length": bad["event_months"].map("{} months".format),
        "Apparent excess": bad["excess"].map(fmt),
    })))
    lines += [
        "",
        "**Any analysis of age at listing has to filter to month-precision sources first.** This "
        "is the trap already in `HANDOFF.md`, measured here so it cannot be forgotten.",
        "",
        "## Does the calendar control matter?",
        "",
        "A snapshot maps age in months onto the calendar month a car was registered in, one for "
        "one. A market that registers heavily in one month therefore bumps every twelfth month of "
        "age for reasons that have nothing to do with a contract. With the control in, each "
        "contract length is measured against the *other* whole-year ages, which is the right "
        "question. Without it:",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Contract length": noseas["event_months"].map("{} months".format),
        "Excess, no calendar control": noseas["excess"].map(fmt),
        "Excess, with it": good["excess"].map(fmt),
    })))
    lines += [
        "",
        "## What this does and does not say",
        "",
        "- **It does not say contracts do not end.** It says the ending does not show up in a "
        "public advert. Cars come back, sit in a compound, get prepared, and reach a forecourt "
        "over the following weeks and months.",
        "- **It is the argument for the ledger.** The third layer of the engine exists only in "
        "the group's own contract dates. No amount of public data recovers it, and that is now a "
        "measurement rather than an assertion.",
        "- **These numbers supersede the prose in `HANDOFF.md`** (+0.0% at 36, -4.8% at 48, "
        "-8.6% at 24), which came from a different and looser specification with no calendar "
        "control and no robustness check. The conclusion is the same and the figures are not; "
        "quote these, because a script writes them.",
        "- **Adverts are not returns.** These are asking prices on public sites, and a lease "
        "return that goes straight to auction never appears in them at all.",
        "- **Three European snapshots of different dates.** Source and calendar-month effects are "
        "absorbed; a difference in how long adverts stay up is not.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    pd.concat([good, bad, noseas], ignore_index=True).to_csv(TABLE, index=False)
    per_source.to_csv(TABLE.with_name("readiness_events_by_source.csv"), index=False)
    print(f"wrote {OUT.name}")
    for _, r in good.iterrows():
        print(f"  {int(r['event_months'])} months: {r['excess']:+.1%} "
              f"({r['lo']:+.1%} to {r['hi']:+.1%})")
    print("  whole-year artefact: " + ", ".join(
        f"{int(r['event_months'])}m {r['excess']:+.0%}" for _, r in bad.iterrows()))


if __name__ == "__main__":
    main()
