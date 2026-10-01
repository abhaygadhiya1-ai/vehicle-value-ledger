"""X3 part 1: the lease-end spike, tested in the register at monthly resolution.

Layer 3 of the readiness engine (`readiness_events_report.md`) looked for a bulge of cars coming to market at the
end of a lease contract (24, 36, 48 or 60 months) in adverts, and found none at 36 months. Adverts smear the timing:
a returned car is remarketed weeks to months later and may never be advertised. The Dutch register records the date
the current keeper took each car on, so it can be asked directly.

    hazard(a) = cars of age a months whose keeper changed in the calendar month
                ------------------------------------------------------------------
                          cars of that registration month on the road

computed for each of the last 12 full calendar months and pooled, so that every age mixes 12 registration months and
the calendar's seasons cancel. The same test on the 12 months before that, and the 12 before those, asks whether a
spike follows age (it reappears in older cohorts) or one cohort (it moves with the cars): the cars now at 60 months
were registered in 2020-21, when low company-car tax on electric cars was locked in for 60 months. Those older
windows are more censored, which can hide a spike but not create one. The population is `build_reference.py
nlhazard`'s "domestic" one: passenger cars on the road, not exported, first put on Dutch plates when new. A first
registration is not a keeper change.

**The spike test.** For a contract length k, the excess is the pooled hazard over the ages k to k+2 (a returned car
changes keeper in the weeks after the contract ends) against the local trend: the ages k-6 to k-3 and k+4 to k+7.
The placebo p is the share of all other ages from 12 to 108 months whose excess is at least as large, so a contract
age must stand out from the curve's ordinary ups and downs, not only from zero.

**Censoring.** RDW shows only the current keeper, so a car that changed keeper in a window and again before the
snapshot is counted at its later change. The latest window is the least affected; it is reported apart. A lessor that
hands a car to a trader, who sells it on within weeks, shows as the later change, which is when the car reached its
next user. Registrations are real; nothing here is synthetic.

Source: RDW open data, Gekentekende voertuigen (public domain), https://opendata.rdw.nl/resource/m9d7-ebf2.json,
aggregated server-side; the monthly table is cached in data/ (private).
Usage: .venv/bin/python analysis/lease_end.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_reference import rdw_group  # noqa: E402
from build_unified import MAKE_ALIASES, STELLANTIS, md_table, norm_name  # noqa: E402

OUT = HERE / "lease_end_report.md"
CACHE = HERE.parent / "data" / "x3_rdw_monthly_hazard.parquet"
WINDOWS = 12       # pooled for the main test
HISTORY = 36       # all-brand windows fetched: three years, to tell an age effect from a cohort effect
MAX_AGE = 120
CONTRACTS = (24, 36, 48, 60)
LIVE = ("voertuigsoort='Personenauto' AND export_indicator='Nee' AND tenaamstellen_mogelijk='Ja' "
        "AND datum_eerste_toelating_dt IS NOT NULL")
BORN_HERE = ("date_extract_y(datum_eerste_tenaamstelling_in_nederland_dt) = date_extract_y(datum_eerste_toelating_dt)")
COHORT = "date_trunc_ym(datum_eerste_toelating_dt)"


def monthly():
    """Movers per window month and registration month, and the parc per registration month; for all brands and for
    the group's brands. Cached."""
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    where = f"{LIVE} AND {BORN_HERE}"
    latest = pd.Timestamp(rdw_group("max(datum_tenaamstelling_dt) AS m", LIVE, "")["m"].iloc[0])
    end = latest.normalize().replace(day=1)
    makes = rdw_group("merk, count(1) AS n", LIVE, "merk", limit=50_000)
    group = sorted(makes.loc[norm_name(makes["merk"]).replace(MAKE_ALIASES).isin(STELLANTIS), "merk"].unique())
    quoted = ",".join("'" + m.replace("'", "''") + "'" for m in group)
    rows = []
    for brands, bw in (("all", where), ("group", f"{where} AND merk IN ({quoted})")):
        parc = rdw_group(f"{COHORT} AS c, count(1) AS n", bw, "c", limit=50_000)
        rows.append(parc.assign(brands=brands, kind="parc", window=pd.NaT))
        for i in range(1, (HISTORY if brands == "all" else WINDOWS) + 1):
            w0, w1 = end - pd.DateOffset(months=i), end - pd.DateOffset(months=i - 1)
            moved = (f"{bw} AND datum_tenaamstelling_dt >= '{w0:%Y-%m-%d}T00:00:00.000' "
                     f"AND datum_tenaamstelling_dt < '{w1:%Y-%m-%d}T00:00:00.000' "
                     "AND datum_tenaamstelling_dt > datum_eerste_tenaamstelling_in_nederland_dt")
            m = rdw_group(f"{COHORT} AS c, count(1) AS n", moved, "c", limit=50_000)
            rows.append(m.assign(brands=brands, kind="moved", window=w0))
            print(f"  {brands} {w0:%Y-%m}: {pd.to_numeric(m['n']).sum():,} movers", flush=True)
    d = pd.concat(rows, ignore_index=True)
    d["c"], d["n"] = pd.to_datetime(d["c"]), pd.to_numeric(d["n"])
    d.to_parquet(CACHE, index=False)
    return d


def hazard(d, brands, windows=None):
    """Pooled monthly hazard by age in months: movers over the parc of their registration month, summed over the
    windows."""
    parc = d[(d["brands"] == brands) & (d["kind"] == "parc")].set_index("c")["n"]
    m = d[(d["brands"] == brands) & (d["kind"] == "moved")].copy()
    if windows is not None:
        m = m[m["window"].isin(windows)]
    m["age"] = (m["window"].dt.year - m["c"].dt.year) * 12 + (m["window"].dt.month - m["c"].dt.month)
    m["parc"] = m["c"].map(parc)
    m = m[m["age"].between(1, MAX_AGE)]
    h = m.groupby("age")[["n", "parc"]].sum()
    h["hazard (%)"] = 100 * h["n"] / h["parc"]
    return h


def excess(h, k):
    """The hazard over ages k..k+2 against the local trend (k-6..k-3 and k+4..k+7), as a relative excess."""
    at = h.loc[k:k + 2]
    near = pd.concat([h.loc[k - 6:k - 3], h.loc[k + 4:k + 7]])
    if len(at) < 3 or len(near) < 8:
        return None
    return at["n"].sum() / at["parc"].sum() / (near["n"].sum() / near["parc"].sum()) - 1


def spike_rows(h, label):
    out = []
    base = {a: excess(h, a) for a in range(12, 109)}
    for k in CONTRACTS:
        e = base[k]
        others = np.array([v for a, v in base.items() if a != k and v is not None])
        out.append({"population": label, "contract (months)": k, "excess (%)": round(100 * e, 1),
                    "placebo p": round(float(np.mean(others >= e)), 3), "ages tested": len(others) + 1})
    top = sorted(((v, a) for a, v in base.items() if v is not None), reverse=True)[:5]
    return out, top


def main():
    d = monthly()
    windows = sorted(d["window"].dropna().unique())
    recent = windows[-WINDOWS:]
    rows, tops = [], {}
    for brands, label in (("all", "all domestic cars"), ("group", "the group's brands")):
        r, top = spike_rows(hazard(d, brands, recent), label)
        rows += r
        tops[label] = top
    latest_rows, _ = spike_rows(hazard(d, "all", windows[-1:]), "all domestic cars, latest window only")
    rows += latest_rows
    older = []
    for i, label in ((1, "13 to 24 months before"), (2, "25 to 36 months before")):
        ws = windows[-WINDOWS * (i + 1):-WINDOWS * i]
        r, _ = spike_rows(hazard(d, "all", ws), f"all domestic cars, {label}")
        older += [{**x, "windows": f"{pd.Timestamp(ws[0]):%b %Y} to {pd.Timestamp(ws[-1]):%b %Y}"} for x in r]
    older = pd.DataFrame(older)
    older.insert(0, "test", older["population"] + ": " + older["contract (months)"].astype(str) + " months")
    spikes = pd.DataFrame(rows)
    spikes.insert(0, "test", spikes["population"] + ": " + spikes["contract (months)"].astype(str) + " months")

    h = hazard(d, "all", recent)
    g = hazard(d, "group", recent)
    curve = pd.DataFrame({"age (months)": h.index, "all: hazard (%)": h["hazard (%)"].round(3).to_numpy(),
                          "group: hazard (%)": g["hazard (%)"].reindex(h.index).round(3).to_numpy()})
    curve = curve[curve["age (months)"].between(12, 72)]
    top_rows = pd.DataFrame([{"population": lab, "rank": i + 1, "age (months)": a, "excess (%)": round(100 * v, 1)}
                             for lab, t in tops.items() for i, (v, a) in enumerate(t)])
    movers = int(d[(d["brands"] == "all") & (d["kind"] == "moved") & d["window"].isin(recent)]["n"].sum())

    OUT.write_text(f"""# X3 part 1: is there a lease-end spike in the register?

_Generated by `analysis/lease_end.py`. Real RDW register data (public domain), not synthetic._

**Population:** passenger cars on the road that were first put on Dutch plates when new. **Windows:** the
{len(recent)} full calendar months {pd.Timestamp(recent[0]):%B %Y} to {pd.Timestamp(recent[-1]):%B %Y}, pooled
({movers:,} keeper changes in all). The hazard at age a is the share of cars of that registration month whose keeper
changed in a window when they were a months old. The excess at a contract length k compares ages k to k+2 with the
local trend (k-6 to k-3 and k+4 to k+7); the placebo p is the share of all other ages from 12 to 108 months with an
excess at least as large.

## The spike test

{md_table(spikes)}

## Age or cohort? The same test in the two earlier years

Each row pools 12 earlier calendar months. A car at 60 months in these windows was registered in an earlier year,
before electric company cars were common. More censored than the main test, so a spike can shrink here but cannot be
created.

{md_table(older)}

## The five largest excesses at any age, 12 to 108 months

If contract ends drive the curve, contract ages should be among these.

{md_table(top_rows)}

## The monthly hazard, 12 to 72 months (%)

{md_table(curve)}
""")
    print(md_table(spikes))
    print(md_table(top_rows))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
