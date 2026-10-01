"""Dealer self-registrations in the real Dutch register: do quick keeper changes spike at period ends?

X1's synthetic world showed that quarter-end gaming (a dealer registering cars in its own name to reach a volume
target, then selling them on) cannot be seen from registration dates alone. The public RDW register holds one more
date: when the car's *current* keeper was registered. A new car whose keeper changes within weeks of first
registration was probably registered by someone other than its real buyer, most often the dealer. If that is tactical,
it should pile up at the end of quarters, when volume targets close.

Population: every passenger car first registered new in the Netherlands (first admission = first Dutch
registration), 2022-2025. A car is a *quick change* when its current keeper was registered 1 to 30 days after first
registration.

**What this measures and what it cannot.**
  - The register shows only the current keeper. A car sold on again later hides its early change, so every rate is a
    lower bound, and older cohorts are more censored. Rates are reported by cohort; 2025 is the least censored.
  - A quick change is not proof of a self-registration. A car may pass quickly to a lease company, a corrected
    registration or a family member. That is why the test compares quarter-end days with other days *in the same
    data*, not with zero.
  - Exports soon after registration (another tactical pattern) are counted separately; exported cars leave the keeper
    history.
  - Registrations are the real ones; nothing here is synthetic.

Source: RDW open data, Gekentekende voertuigen (public domain), https://opendata.rdw.nl/resource/m9d7-ebf2.json,
queried server-side. Nothing is stored except this report.
Usage: .venv/bin/python analysis/self_registration.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_reference import RDW_URL  # noqa: E402
from build_unified import MAKE_ALIASES, STELLANTIS, md_table, norm_name  # noqa: E402

OUT = HERE / "self_registration_report.md"
PAGE = 50_000
QUICK_DAYS = 30
END_DAYS = 3  # "quarter end" and "month end": the last 3 calendar days
SEED = 7
# The group's agency model in the Netherlands: a pilot market, live during 2023 and kept after the Europe-wide rollout
# was paused. Opened: https://www.automotive-online.nl/management/merkkanaal/2023/12/11/stellantis-stelt-europese-invoering-agentuur-model-uit-zint-op-aanpassingen/
# Planned for 1 July 2023, postponed in May 2023, and started on 4 September 2023 in the Netherlands, Belgium,
# Luxembourg and Austria: Stellantis Nederland's release of 1 September 2023 ("start op 4 september", blocked to
# scripted access; found by the X2 research), confirmed by Automotive Online, 25 September 2023 (opened): the agency
# model was introduced "begin deze maand",
# https://www.automotive-online.nl/management/2023/09/25/stellantis-retailers-verenigen-zich-in-strened/
AGENCY_START = pd.Timestamp("2023-09-04")
NEW = ("voertuigsoort='Personenauto' AND datum_eerste_toelating_dt >= '2022-01-01T00:00:00.000' "
       "AND datum_eerste_toelating_dt < '2026-01-01T00:00:00.000' "
       "AND datum_eerste_tenaamstelling_in_nederland_dt = datum_eerste_toelating_dt")


def paged(select, where, order, group=None):
    pages, offset = [], 0
    while True:
        params = {"$select": select, "$where": where, "$order": order, "$limit": PAGE, "$offset": offset}
        if group:
            params["$group"] = group
        r = requests.get(RDW_URL, params=params, timeout=900)
        r.raise_for_status()
        pages.append(pd.DataFrame(r.json()))
        if len(pages[-1]) < PAGE:
            return pd.concat(pages, ignore_index=True)
        offset += PAGE


def is_group(merk):
    return norm_name(merk).replace(MAKE_ALIASES).isin(STELLANTIS)


def position(dates, end_days=END_DAYS):
    """Where a day sits: the last `end_days` days of a quarter, of another month, or neither."""
    month_end = dates + pd.offsets.MonthEnd(0)
    last = (month_end - dates).dt.days < end_days
    quarter_month = dates.dt.month.isin([3, 6, 9, 12])
    return np.where(last & quarter_month, "quarter end", np.where(last, "other month end", "other days"))


def diff_ci(daily, a, b, reps=2000):
    """Bootstrap over days (days are the clusters) for the quick-change share of `a` minus that of `b`."""
    rng = np.random.default_rng(SEED)
    da, db = daily[daily["position"] == a], daily[daily["position"] == b]
    out = []
    for _ in range(reps):
        sa, sb = da.sample(len(da), replace=True, random_state=rng), db.sample(len(db), replace=True, random_state=rng)
        out.append(sa["quick"].sum() / sa["new"].sum() - sb["quick"].sum() / sb["new"].sum())
    return np.percentile(out, [2.5, 97.5])


def did(daily, stat, reps=2000):
    """Difference-in-differences: (group brands after - before) - (other brands after - before), with a bootstrap
    that resamples days within each of the four cells."""
    rng = np.random.default_rng(SEED)
    cells = {(g, e): daily[(daily["group"] == g) & (daily["era"] == e)]
             for g in ("group brands", "other brands") for e in ("before", "after")}

    def value(c):
        return ((stat(c[("group brands", "after")]) - stat(c[("group brands", "before")]))
                - (stat(c[("other brands", "after")]) - stat(c[("other brands", "before")])))

    boot = [value({k: v.sample(len(v), replace=True, random_state=rng) for k, v in cells.items()})
            for _ in range(reps)]
    return value(cells), *np.percentile(boot, [2.5, 97.5])


def period_end_share(c):
    return c.loc[c["position"] != "other days", "new"].sum() / c["new"].sum()


def period_end_lift(c):
    end = c["position"] != "other days"
    return c.loc[end, "quick"].sum() / c.loc[end, "new"].sum() - c.loc[~end, "quick"].sum() / c.loc[~end, "new"].sum()


def main():
    new = paged("merk, date_trunc_ymd(datum_eerste_toelating_dt) AS d, count(1) AS n", NEW, "d, merk", "merk, d")
    new["d"], new["n"] = pd.to_datetime(new["d"]), pd.to_numeric(new["n"])
    changed = paged("merk, datum_eerste_toelating_dt AS first, datum_tenaamstelling_dt AS keeper",
                    NEW + " AND datum_tenaamstelling_dt > datum_eerste_toelating_dt", "kenteken")
    exported = paged("merk, date_trunc_ymd(datum_eerste_toelating_dt) AS d, count(1) AS n",
                     NEW + " AND export_indicator='Ja'", "d, merk", "merk, d")
    exported["d"], exported["n"] = pd.to_datetime(exported["d"]), pd.to_numeric(exported["n"])
    changed["first"], changed["keeper"] = pd.to_datetime(changed["first"]), pd.to_datetime(changed["keeper"])
    changed["gap"] = (changed["keeper"] - changed["first"]).dt.days
    changed["d"] = changed["first"].dt.normalize()
    for df in (new, changed, exported):
        df["group"] = np.where(is_group(df["merk"]), "group brands", "other brands")

    def build_daily(quick_days, end_days):
        """One row per day and brand group: new cars, quick keeper changes, exports, and the day's position."""
        quick = changed[changed["gap"].between(1, quick_days)]
        d = (new.groupby(["d", "group"])["n"].sum().rename("new").to_frame()
             .join(quick.groupby(["d", "group"]).size().rename("quick"), how="left")
             .join(exported.groupby(["d", "group"])["n"].sum().rename("exported"), how="left")
             .fillna(0).reset_index())
        d["position"] = position(d["d"], end_days)
        d["cohort"] = d["d"].dt.year
        return d

    daily = build_daily(QUICK_DAYS, END_DAYS)
    print(f"new cars {new['n'].sum():,}; later keeper change {len(changed):,}; quick (1-{QUICK_DAYS} days) "
          f"{int(daily['quick'].sum()):,}; exported {exported['n'].sum():,}")

    def table(by):
        t = daily.groupby(by)[["new", "quick", "exported"]].sum()
        t["quick share"] = t["quick"] / t["new"]
        t["export share"] = t["exported"] / t["new"]
        return t

    by_pos = table(["group", "position"])
    by_cohort = table(["cohort", "group", "position"])

    # the lift at period ends against ordinary days, with a day-level bootstrap interval, and the excess it implies
    def lift_rows(d, keys):
        rows = []
        for key, g in d.groupby(keys):
            s = g.groupby("position")[["new", "quick"]].sum()
            share = s["quick"] / s["new"]
            row = dict(zip(keys, key if isinstance(key, tuple) else (key,)))
            for end in ["quarter end", "other month end"]:
                lo, hi = diff_ci(g, end, "other days")
                row[f"{end}: difference"] = share[end] - share["other days"]
                row[f"{end}: 95% interval"] = f"{100 * lo:+.2f} to {100 * hi:+.2f} pts"
                row[f"{end}: low"], row[f"{end}: high"] = lo, hi
                row[f"{end}: excess cars"] = round((share[end] - share["other days"]) * s.loc[end, "new"])
            row["quick share, other days"] = share["other days"]
            rows.append(row)
        return pd.DataFrame(rows)

    lift = lift_rows(daily, ["cohort", "group"])
    pooled = lift_rows(daily, ["group"]).set_index("group")
    head = pd.DataFrame({g: {
        "share registered in a month's last days, before the agency model (%)":
            100 * period_end_share(daily[(daily["group"] == g) & (daily["d"] < AGENCY_START)]),
        "quick share on ordinary days (%)": 100 * pooled.at[g, "quick share, other days"],
        "quarter-end lift (points)": 100 * pooled.at[g, "quarter end: difference"],
        "quarter-end lift, 95% low (points)": 100 * pooled.at[g, "quarter end: low"],
        "quarter-end lift, 95% high (points)": 100 * pooled.at[g, "quarter end: high"],
        "month-end lift (points)": 100 * pooled.at[g, "other month end: difference"],
        "month-end lift, 95% low (points)": 100 * pooled.at[g, "other month end: low"],
        "month-end lift, 95% high (points)": 100 * pooled.at[g, "other month end: high"],
        "quarter-end excess cars, 2022-2025": pooled.at[g, "quarter end: excess cars"],
        "month-end excess cars, 2022-2025": pooled.at[g, "other month end: excess cars"],
    } for g in pooled.index})
    head = head.map(lambda v: f"{v:,.0f}" if abs(v) >= 100 else f"{v:.2f}").rename_axis("measure").reset_index()
    sens = []
    for end_days in (3, 7):
        for quick_days in (30, 90):
            t = lift_rows(build_daily(quick_days, end_days), ["group"])
            sens.append(t.assign(**{"end days": end_days, "quick days": quick_days}))
    sens = pd.concat(sens, ignore_index=True)
    sens = sens[["end days", "quick days"] + [c for c in sens.columns if c not in ("end days", "quick days")]]

    # before and after the agency model: half-year series and a difference-in-differences against other brands
    daily["half"] = daily["d"].dt.year.astype(str) + np.where(daily["d"].dt.month <= 6, " H1", " H2")
    daily["era"] = np.where(daily["d"] >= AGENCY_START, "after", "before")
    halves = []
    for (half, grp), c in daily.groupby(["half", "group"]):
        halves.append({"half-year": half, "brands": grp, "cars": c["new"].sum(),
                       "share registered at period ends": period_end_share(c),
                       "period-end lift in quick changes": period_end_lift(c)})
    halves = pd.DataFrame(halves).pivot(index="half-year", columns="brands")
    halves.columns = [f"{b}: {m}" for m, b in halves.columns]
    halves = halves.reset_index()
    agency = pd.DataFrame([
        {"measure": name, **dict(zip(["difference-in-differences", "95% low", "95% high"],
                                     [100 * x for x in did(daily, stat)]))}
        for name, stat in [("share registered at period ends (points)", period_end_share),
                           ("period-end lift in quick changes (points)", period_end_lift)]]).round(2)

    # volume spike, for context: cars per day at quarter ends against other days
    per_day = daily.groupby(["d", "position"])["new"].sum().reset_index().groupby("position")["new"].mean()

    def fmt(t):
        t = t.drop(columns=[c for c in t.columns if c.endswith(": low") or c.endswith(": high")]).copy()
        for c in t.columns:
            if c in ("cohort", "end days", "quick days"):
                continue
            if "share" in c or "difference" in c or "lift" in c:
                t[c] = (100 * t[c]).map("{:.2f}%".format)
            elif t[c].dtype.kind in "fi":
                t[c] = t[c].map("{:,.0f}".format)
        return t

    lines = [
        "# Dealer self-registrations in the Dutch register: quick keeper changes at quarter ends",
        "",
        "_Generated by `analysis/self_registration.py`. Real RDW register data (public domain), not synthetic._",
        "",
        f"**Population:** {new['n'].sum():,} passenger cars first registered new in the Netherlands, 2022-2025. "
        f"A quick change is a current keeper registered 1-{QUICK_DAYS} days after first registration "
        f"({int(daily['quick'].sum()):,} cars). Quarter end and month end mean the last {END_DAYS} calendar days.",
        "",
        "**Read with the limits in the script's docstring:** only the current keeper is visible (a lower bound, more "
        "censored for older cohorts), and a quick change is not proof of a self-registration.",
        "",
        f"## Headline (last {END_DAYS} days of the period, quick = within {QUICK_DAYS} days, 2022-2025 pooled)",
        "",
        "Lift = the extra share of cars whose keeper changed quickly, in percentage points, against ordinary days. "
        "The 95% bounds resample days. Excess cars = the lift times the period-end cars.",
        "",
        md_table(head),
        "",
        "## Before and after the group's agency model (Netherlands, 2023)",
        "",
        f"Split at {AGENCY_START:%d %B %Y}. Period ends = the last {END_DAYS} days of any month. Difference-in-"
        "differences = the change for group brands minus the change for other brands, so that market-wide shifts and "
        "the censoring that differs by cohort cancel out. The interval resamples days. The agency model is the "
        "obvious candidate for any group-specific change, but this cannot prove it was the cause. **Read the half-year "
        "table before the difference-in-differences:** the quick-change result is driven mostly by other brands' "
        "period-end lift rising after 2023, not by a fall for group brands, so the parallel-trends assumption is "
        "doubtful and the estimate is not a causal effect. The descriptive facts stand: group brands register a far "
        "larger share of their cars in a month's last days than other brands, and that share fell from late 2024.",
        "",
        md_table(agency),
        "",
        md_table(fmt(halves)),
        "",
        "## Cars registered per day",
        "",
        md_table(per_day.rename("cars per day").map("{:,.0f}".format).reset_index()),
        "",
        "## Quick keeper changes by position in the quarter",
        "",
        md_table(fmt(by_pos).reset_index()),
        "",
        "## Period-end differences, by cohort",
        "",
        "Difference = the quick share on quarter-end (or other month-end) days minus the share on ordinary days. "
        "The interval resamples days. Excess = the difference times the period-end cars: quick changes above the "
        "ordinary-day rate.",
        "",
        md_table(fmt(lift)),
        "",
        "## Sensitivity: the window at the period end, and what counts as quick (all cohorts pooled)",
        "",
        md_table(fmt(sens)),
        "",
        "## By cohort and position (detail)",
        "",
        md_table(fmt(by_cohort).reset_index()),
        "",
    ]
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT.relative_to(HERE.parent)}")
    cols = ["group", "end days", "quick days", "quarter end: difference", "quarter end: 95% interval",
            "other month end: difference", "other month end: 95% interval", "quick share, other days"]
    print(fmt(sens)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
