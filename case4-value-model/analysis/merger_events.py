"""X2 part 2: did a brand's month-end registrations move when it met a new owner's incentive regime?

Event studies on the Dutch register panel of part 1 (`merger_fingerprint.py`). A brand's month-end share is the share
of its new cars first registered in the last 3 days of a month: a proxy for tactical registrations at target
deadlines (see part 1's report and `self_registration_report.md`).

The estimate is a difference-in-differences: the change in the treated family's month-end share (after minus before)
minus the same change for the comparison group, over W months either side of the event. Shares pool the cars of
every month in a window. Windows of 12 and 24 months never cross another event.

Inference is a placebo-in-time test. The same estimate is computed at every other month the data allow, as if the
event had happened then. The p-value is the share of those placebo breaks whose estimate is at least as large, in
absolute size, as the event's. It asks whether the event moved the gap more than the gap moves anyway. A first
version resampled months as if they were independent; its intervals were far too narrow, because a family's share
drifts, and fake dates halfway through each before-window came out "significant". This test replaces it.

Robustness: without December and January, when Dutch tax changes move registrations; also without August 2018 (the
WLTP switch) and June 2020 (before BPM moved to WLTP on 1 July 2020); and the quarter-end share instead of the
month-end share.

What it cannot show: a change at an event date is consistent with a new incentive regime, but a product change, a
distribution change or a fleet deal at the same time would look the same. Part 3 holds the model mix fixed.
Registrations are real; nothing here is synthetic.

Usage: .venv/bin/python analysis/merger_events.py   (after merger_fingerprint.py has cached the panel)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from build_unified import md_table  # noqa: E402
from merger_fingerprint import classified  # noqa: E402

OUT = HERE / "merger_events_report.md"
WINDOWS = (24, 12)
# (name, first month after, treated family, comparison family). Sources for each date are in SOURCES and the report.
EVENTS = [
    ("Opel joins PSA", "2017-08", "Opel", "other"),
    ("Opel joins PSA", "2017-08", "Opel", "PSA"),
    ("Stellantis formed", "2021-01", "FCA", "PSA"),
    ("Stellantis formed", "2021-01", "FCA", "other"),
    ("Stellantis formed", "2021-01", "PSA", "other"),
    ("Stellantis formed", "2021-01", "Opel", "other"),
    ("agency model (NL)", "2023-09", "PSA", "other"),
    ("agency model (NL)", "2023-09", "Opel", "other"),
    ("agency model (NL)", "2023-09", "FCA", "other"),
]
SOURCES = [
    ("Opel joins PSA", "1 August 2017", "WardsAuto, 1 August 2017: PSA has formally taken over Opel/Vauxhall",
     "https://www.wardsauto.com/opel/psa-group-completes-opel-vauxhall-purchase-from-gm"),
    ("Stellantis formed", "16 January 2021", "Stellantis press release, 16 January 2021: the merger has been completed",
     "https://www.stellantis.com/en/news/press-releases/2021/january/the-merger-of-fca-and-groupe-psa-has-been-completed"),
    ("agency model (NL)", "4 September 2023", "planned 1 July 2023, postponed; Automotive Online, 25 September 2023: "
     "introduced early that month", "https://www.automotive-online.nl/management/2023/09/25/"
     "stellantis-retailers-verenigen-zich-in-strened/"),
]
TAX_MONTHS = {pd.Period("2018-08", "M"), pd.Period("2020-06", "M")}  # WLTP switch; month before BPM moved to WLTP


def monthly(p, measure):
    """Per month and family: all new cars, and those first registered in the period-end days of the measure."""
    end = p["position"].ne("other days") if measure == "month end" else p["position"].eq("quarter end")
    m = p.assign(month=p["d"].dt.to_period("M"), end=np.where(end, p["n"], 0))
    return m.groupby(["month", "family"])[["n", "end"]].sum()


def series(m, treated, comparison, drop_months=()):
    """Month-by-month cars and period-end cars for the two families, on the months both have."""
    t, c = (m.xs(f, level="family") for f in (treated, comparison))
    months = t.index.intersection(c.index)
    months = months[~months.month.isin(drop_months) & ~months.isin(TAX_MONTHS if drop_months else set())]
    return months, [x.loc[months].to_numpy(float) for x in (t["n"], t["end"], c["n"], c["end"])]


def did_at(months, arrays, month, w):
    """The difference-in-differences with w months either side of `month`; None if a window is short."""
    tn, te, cn, ce = arrays
    b = (months >= month - w) & (months < month)
    a = (months >= month) & (months < month + w)
    if b.sum() < w * 0.75 or a.sum() < w * 0.75:
        return None

    def share(e, n, k):
        return 100 * e[k].sum() / n[k].sum()

    return (share(te, tn, a) - share(te, tn, b)) - (share(ce, cn, a) - share(ce, cn, b))


def test(m, treated, comparison, month, w, drop_months=()):
    """The event's estimate, and the share of placebo breaks at least as large in absolute size."""
    months, arrays = series(m, treated, comparison, drop_months)
    month = pd.Period(month, "M")
    est = did_at(months, arrays, month, w)
    placebo = [did_at(months, arrays, b, w) for b in months if b != month]
    placebo = np.array([x for x in placebo if x is not None])
    return est, float(np.mean(np.abs(placebo) >= abs(est))), len(placebo)


def rows(m, drop_months=()):
    out = []
    for name, month, treated, comparison in EVENTS:
        row = {"test": f"{name}: {treated} vs {comparison}", "event": name, "month": month, "treated": treated,
               "comparison": comparison}
        for w in WINDOWS:
            est, pval, n = test(m, treated, comparison, month, w, drop_months)
            row[f"{w} months: estimate (points)"] = est
            row[f"{w} months: placebo p"] = pval
            row[f"{w} months: placebo breaks"] = n
        out.append(row)
    return pd.DataFrame(out)


def levels(m):
    """Each event pair's pooled month-end shares in the 24 months before and after."""
    out = []
    for name, month, treated, comparison in EVENTS:
        months, (tn, te, cn, ce) = series(m, treated, comparison)
        e, w = pd.Period(month, "M"), WINDOWS[0]
        b, a = (months >= e - w) & (months < e), (months >= e) & (months < e + w)
        out.append({"test": f"{name}: {treated} vs {comparison}", "event": name, "treated": treated,
                    "comparison": comparison,
                    "before: treated (%)": 100 * te[b].sum() / tn[b].sum(),
                    "before: comparison (%)": 100 * ce[b].sum() / cn[b].sum(),
                    "after: treated (%)": 100 * te[a].sum() / tn[a].sum(),
                    "after: comparison (%)": 100 * ce[a].sum() / cn[a].sum()})
    return pd.DataFrame(out)


def fmt(df):
    df = df.copy()
    for c in df.columns:
        if df[c].dtype.kind == "f":
            df[c] = df[c].round(2)
    return df


def main():
    p = classified()
    m_month, m_quarter = monthly(p, "month end"), monthly(p, "quarter end")
    main_rows = rows(m_month)
    keys = ["test", "event", "treated", "comparison"]
    w = WINDOWS[0]
    pick = [f"{w} months: estimate (points)", f"{w} months: placebo p"]
    robust = main_rows[keys + pick]
    for label, df in (("without tax months", rows(m_month, drop_months=(12, 1))),
                      ("quarter end", rows(m_quarter))):
        robust = robust.merge(df[keys + pick].rename(columns={c: f"{label}: {c}" for c in pick}), on=keys)

    OUT.write_text(f"""# X2 part 2: did month-end registrations move when a brand met a new owner's regime?

_Generated by `analysis/merger_events.py`. Real RDW register data (public domain), not synthetic._

Each estimate is a difference-in-differences: the change in the treated family's month-end share (the share of its
new cars first registered in a month's last 3 days) minus the same change for the comparison group, over W months
either side of the event. The placebo p is the share of all other break months whose estimate is at least as large in
absolute size: it asks whether the event moved the gap more than the gap moves anyway. A change at an event date is
consistent with a new incentive regime but does not prove it; a product, distribution or fleet change at the same
time would look the same.

## Main estimates

{md_table(fmt(main_rows))}

## Event dates

{md_table(pd.DataFrame(SOURCES, columns=["event", "date", "source", "url"]))}

"Without tax months" drops every December and January, August 2018 (the WLTP switch) and June 2020 (the month before
BPM moved to WLTP), when Dutch tax deadlines pull registrations forward.

## The shares behind the {w}-month estimates (%)

{md_table(fmt(levels(m_month)))}

## Robustness ({w}-month windows)

{md_table(fmt(robust))}
""")
    print(md_table(fmt(main_rows[keys + [c for c in main_rows.columns if "estimate" in c or "p" == c[-1]]])))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
