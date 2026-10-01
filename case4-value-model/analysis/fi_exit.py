"""X11 part 3: does mileage predict leaving the fleet in Finland, as it does in the UK?

The UK result (`readiness_mileage_report.md`, part 1): among cars tested in March 2024, a car on twice its age
cohort's mileage was about half as likely again to never be tested again. This repeats the test on Finland's open
vehicle file (`fi_register.py`), with the UK script's own functions, so the two numbers are made the same way:

    deciles of mileage within each whole-year age cohort (year of the snapshot minus year of first use), the exit
    rate in each, and log(rate) = age effect + b * log(mileage / the cohort's median), weighted by cars per cell.

**The Finnish design.** Baseline: the snapshot of 30 June 2025. Exit: the car is absent from the snapshot of 30 June
2026, so it has left traffic use (scrapped, exported or laid up). Mileage: the 2025 reading. A reading is dated by the
last inspection, which can be two years back at ages 4-10 (`fi_register_report.md`). So the main sample keeps only cars
whose reading changed between the 2024 and 2025 snapshots: inspected in the year before the baseline, as the UK's
baseline cars were. Cars are followed on key K3 (fixed attributes plus colour), unique in each snapshot used.

**The checks.**
- Ages 4-9 and 10-20 apart. From 10, both countries inspect every year, so that band is the like-for-like comparison.
  The UK's band figures are refitted from its saved cell table.
- All readings, fresh or not: what the staleness does.
- Domestic cars only: imports are inspected at registration, and their readings are dated by that.
- Laid-up cars: baseline 2024, absent in 2025, and whether each car is back in 2026. The mileage gradient is fitted
  on all exits, on those still absent in 2026 (permanent), and on returns alone.

Needs the three extracts `fi_register.py` writes to data/raw/traficom/ (private).
Usage: .venv/bin/python analysis/fi_exit.py
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from build_unified import md_table  # noqa: E402
from fi_register import load, meta, pairs  # noqa: E402
from readiness_mileage import CURVE, ELAST, FACTS, MAX_KM, MIN_KM, by_decile, elasticity, pooled  # noqa: E402

OUT = HERE / "fi_exit_report.md"
S24, S25, S26 = "2024-10", "2025-09", "2026-07"
AGE_MIN = 4  # a domestic car has no reading before its first inspection (fi_register_report.md)


def snapshot(name):
    d = load(name, extra=["kayttoonottopvm"])
    year = int(meta(name)["max_reg_date"][:4])
    d["age_y"] = year - pd.to_numeric(d["kayttoonottopvm"].astype(object).str[:4], errors="coerce")
    return d[["K3", "odo", "age_y", "imported"]]


def unique(d):
    return d[~d.K3.duplicated(keep=False)]


def fit(df, flag, ages=(AGE_MIN, 20)):
    """The UK method on one sample: elasticity, its standard error, and the decile profile."""
    s = df[df.age_y.between(*ages) & df.odo.between(MIN_KM, MAX_KM)]
    tab = by_decile(s.age_y.to_numpy(), s.odo.to_numpy(float), s[flag].to_numpy(float))
    tab = tab[tab.age.between(*ages)]
    b, se = elasticity(tab)
    prof = pooled(tab)
    top, bottom = prof.set_index("decile").relative.loc[[10, 1]]
    return {"cars": len(s), "rate": s[flag].mean(), "b": b, "se": se, "d10_d1": top / bottom, "prof": prof,
            "ages": f"{tab.age.min()}-{tab.age.max()}"}


def row(label, r):
    return {"sample": label, "ages": r["ages"], "cars": f"{r['cars']:,}", "exit rate": f"{100 * r['rate']:.1f}%",
            "elasticity": f"{r['b']:.3f}", "se": f"{r['se']:.3f}", "twice the mileage": f"{2 ** r['b']:.2f}x",
            "decile 10 / decile 1": f"{r['d10_d1']:.1f}x"}


FI_MONTHS = ["tammikuuta", "helmikuuta", "maaliskuuta", "huhtikuuta", "toukokuuta", "kesäkuuta", "heinäkuuta",
             "elokuuta", "syyskuuta", "lokakuuta", "marraskuuta", "joulukuuta"]


def van_adverts():
    """Part 4: could the Finnish van adverts in `eu_commercial_2023` test coming to market?"""
    import json
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = pd.read_excel(HERE.parent / "data" / "raw" / "eu_commercial_2023" / "FI.xlsx")
    month = d.LocationAndTime.astype(str).str.extract("(" + "|".join(FI_MONTHS) + ")")[0]
    month = month.map({m: i + 1 for i, m in enumerate(FI_MONTHS)})
    age = 2023 - d.Year
    ok = d.Mileage.between(MIN_KM, MAX_KM) & month.notna()
    yearly = ok & age.between(10, 20)
    per_age = age[yearly].value_counts()
    return {"n": len(d), "dated": month.notna().mean(), "dec_jan": month.isin([12, 1]).sum() / month.notna().sum(),
            "yearly": int(yearly.sum()), "per_age_lo": int(per_age.min()), "per_age_hi": int(per_age.max()),
            "uk_ads": json.loads(FACTS.read_text())["n_ads"]}


def main():
    s24, s25, s26 = snapshot(S24), snapshot(S25), snapshot(S26)
    u24 = unique(s24)[["K3", "odo"]].rename(columns={"odo": "odo_24"})

    # baseline 2025, followed to 2026; the 2024 reading dates the 2025 one
    p = pairs(s25, s26)
    p = p[~p.K3.isin(s24.K3[s24.K3.duplicated(keep=False)])]
    p = p.merge(u24, on="K3", how="left", indicator=True)
    p["in_2024"] = p.pop("_merge").eq("both")
    p["fresh"] = p.in_2024 & p.odo.notna() & (p.odo_24.isna() | (p.odo != p.odo_24))
    p["gone"] = ~p.found
    fresh = p[p.fresh]
    main_, fi_10, dom = fit(fresh, "gone"), fit(fresh, "gone", (10, 20)), fit(fresh[~fresh.imported], "gone")
    every = fit(p, "gone")
    rows = [row("Main: inspected in the year before the baseline", main_),
            row("Main, ages 4-9", fit(fresh, "gone", (4, 9))),
            row("Main, ages 10-20 (yearly inspections)", fi_10),
            row("Main, domestic cars only", dom),
            row("All readings, fresh or not", every),
            row("All readings, ages 10-20", fit(p, "gone", (10, 20)))]
    stale_rate = p.loc[p.age_y.between(4, 9) & p.odo.notna() & ~p.fresh, "gone"].mean()
    fresh_rate = p.loc[p.age_y.between(4, 9) & p.fresh, "gone"].mean()

    # laid-up cars: baseline 2024, gone in 2025, back in 2026?
    q = pairs(s24, s25)
    q = q[~q.K3.isin(s26.K3[s26.K3.duplicated(keep=False)])]
    q["gone"] = ~q.found
    q["back"] = q.gone & q.K3.isin(s26.K3)
    q["permanent"] = q.gone & ~q.back
    g24, perm, back = (fit(q, f, (10, 20)) for f in ("gone", "permanent", "back"))
    g25 = fit(p, "gone", (10, 20))
    lay = [row("Baseline 2024: gone in 2025", g24), row("Baseline 2024: still gone in 2026 (permanent)", perm),
           row("Baseline 2024: back in 2026 (laid up)", back), row("Baseline 2025: gone in 2026 (a year later)", g25)]
    back_share = back["rate"] / g24["rate"]  # the same sample: ages 10-20, readings in the band

    # the UK, from its saved cells
    uk = pd.read_csv(CURVE)
    uk = uk[uk.event.eq("fleet_exit")]
    uk_b_saved = float(pd.read_csv(ELAST).set_index("event").loc["fleet_exit", "elasticity"])
    uk_rows = []
    for lab, ages in [("UK, all ages", (3, 20)), ("UK, ages 4-9", (4, 9)), ("UK, ages 10-20", (10, 20))]:
        t = uk[uk.age.between(*ages)]
        b, se = elasticity(t)
        pr = pooled(t).set_index("decile").relative
        uk_rows.append({"UK sample": lab, "ages": f"{t.age.min()}-{t.age.max()}", "elasticity": f"{b:.3f}",
                        "se": f"{se:.3f}", "twice the mileage": f"{2 ** b:.2f}x",
                        "decile 10 / decile 1": f"{pr.loc[10] / pr.loc[1]:.1f}x"})
    uk_b_refit = elasticity(uk)[0]
    assert abs(uk_b_refit - uk_b_saved) < 1e-9, (uk_b_refit, uk_b_saved)
    uk_prof = pooled(uk)

    prof = main_["prof"].merge(uk_prof, on="decile", suffixes=("_fi", "_uk"))
    profile = pd.DataFrame({"mileage decile": prof.decile,
                            "Finland: mileage vs cohort median": prof.ratio_fi.map("{:.2f}x".format),
                            "Finland: exit vs cohort average": prof.relative_fi.map("{:.2f}x".format),
                            "UK: mileage vs cohort median": prof.ratio_uk.map("{:.2f}x".format),
                            "UK: exit vs cohort average": prof.relative_uk.map("{:.2f}x".format)})
    uk_10 = elasticity(uk[uk.age.between(10, 20)])
    vans = van_adverts()
    z_10 = (fi_10["b"] - uk_10[0]) / (fi_10["se"] ** 2 + uk_10[1] ** 2) ** 0.5
    like = pd.DataFrame([
        {"ages 10-20, cars inspected in the year before": "elasticity", "Finland": f"{fi_10['b']:.3f}",
         "UK": f"{uk_10[0]:.3f}"},
        {"ages 10-20, cars inspected in the year before": "standard error", "Finland": f"{fi_10['se']:.3f}",
         "UK": f"{uk_10[1]:.3f}"},
        {"ages 10-20, cars inspected in the year before": "twice the mileage", "Finland": f"{2 ** fi_10['b']:.2f}x",
         "UK": f"{2 ** uk_10[0]:.2f}x"},
        {"ages 10-20, cars inspected in the year before": "difference, in standard errors",
         "Finland": f"{abs(z_10):.1f}", "UK": ""}])

    OUT.write_text(f"""# X11 part 3: mileage and leaving the fleet, Finland beside the UK

**The UK result holds in Finland.** For cars of 10-20 years, which both countries inspect every year, a car on twice
its age cohort's mileage is **{2 ** fi_10['b']:.2f} times** as likely to leave the fleet within a year in Finland
(elasticity {fi_10['b']:.3f}, standard error {fi_10['se']:.3f}), and **{2 ** uk_10[0]:.2f} times** in the UK
({uk_10[0]:.3f}, {uk_10[1]:.3f}). The difference is {abs(z_10):.1f} standard errors. Both figures come from the same
method and the same functions, on two registers.

{md_table(like)}

Across ages 4-20 the Finnish figure is {2 ** main_['b']:.2f} times (elasticity {main_['b']:.3f}, standard error
{main_['se']:.3f}); the UK's published figure, for ages 3-20, is {2 ** uk_b_saved:.2f} times ({uk_b_saved:.3f}). At
4-9 the two designs differ. A Finnish car inspected in the year before the baseline is not due again in the
follow-up year, because it is on a two-year cycle, while a UK car is due every year. So the whole-range figures are
not like for like; the 10-20 band is.

In the main sample (cars inspected in the year to 30 June 2025, ages 4-20), {main_['rate'] * 100:.1f}% had left
traffic use by 30 June 2026. That means scrapped, exported or laid up: Finland's open file lists only vehicles in
traffic use, and gives no reason.

## The decile profile

The main Finnish sample beside the UK's part 1. The UK columns are recomputed with the UK script's own `pooled()`
from its saved cells; refitting those cells reproduces its saved elasticity exactly.

{md_table(profile)}

## The checks

{md_table(pd.DataFrame(rows))}

- **Staleness.** At ages 4-9, cars not inspected in the year before the baseline left at
  {stale_rate * 100:.1f}%, and cars that were inspected at {fresh_rate * 100:.1f}%. The rates barely differ.
  What staleness changes is the mileage: a reading up to two years old ranks a car below its true place in the
  cohort. With every reading, fresh or not, the elasticity falls from {main_['b']:.3f} to {every['b']:.3f}. That
  is why the main sample keeps only fresh readings.
- **Imports.** Used imports enter the cycle at registration. On domestic cars alone the elasticity is
  {dom['b']:.3f}.
- **The UK the same way, by age band:**

{md_table(pd.DataFrame(uk_rows))}

## Laid-up cars: gone, or only resting?

The 2024 snapshot as a baseline, followed to 2025, with 2026 as a later look. Of the cars gone in 2025,
{back_share * 100:.1f}% were back in traffic use in 2026: laid up, not disposed of. Ages 10-20, all readings; at
those ages inspections are yearly, so almost every reading is under a year old.

{md_table(pd.DataFrame(lay))}

**The gradient belongs to permanent exits.** For cars still gone a year later the elasticity is
{perm['b']:.3f}. For cars that came back it is {back['b']:.3f}: laid-up cars are only mildly more driven than their
cohort. So lay-ups dilute the all-exits figure, and high mileage marks disposal. The last row repeats the 2024 row's
definition a year later ({g25['b']:.3f} against {g24['b']:.3f}), so the result is not a fluke of one year.

## Limits

- **A proxy, like the UK's.** "Left traffic use" covers scrapping, export and lay-up. The UK's covers the same
  plus an MOT missed. Neither register gives a reason per car. The 2026 look splits off the lay-ups that
  returned within a year, not the ones that will return later.
- **The key drops cars it cannot follow:** identical cars registered on one day. An error independent of mileage
  would dilute the gradient, not create it (`fi_register_report.md`).
- **Three snapshots, one country.**

## Coming to market: not tested in Finland (part 4)

The UK's second result is that mileage does not predict a car being advertised. It needs adverts, and no Finnish
car-advert dataset is in hand. The one Finnish source is the van file in `eu_commercial_2023`: {vans['n']:,} adverts
("European Used Commercial Car On-line Market Monitoring in 2023", issued 22 December 2023:
https://doi.org/10.17632/kz6hh7832p). It cannot carry the test, for four reasons.

- **The listing month holds; the year is inferred.** {vans['dated'] * 100:.0f}% of adverts give a day and a Finnish month
  name, and {vans['dec_jan'] * 100:.0f}% of those fall in December or January. None gives a year. Since the dataset
  was issued in December 2023, the scrape is most likely around December 2022 to January 2023.
- **The parc would be out of step.** The matching register would be the Archive's March 2023 capture. Its
  readings date from each van's last inspection, up to a year earlier even at yearly-inspection ages, while an
  advert's mileage is current. That pushes adverts into higher parc deciles and makes a slope on its own. There is
  no earlier snapshot to keep only fresh readings, as part 3 does.
- **Too few.** At the yearly-inspection ages (10-20), {vans['yearly']:,} adverts carry a date and a believable
  mileage: {vans['per_age_lo']}-{vans['per_age_hi']} per age cohort. The UK test used {vans['uk_ads']:,} car adverts.
- **Vans, not cars.**

**Decided (26 September, on solution quality):** result 2 stays UK-only and says so. A Finnish van test would be
weaker than the result it checks, and a staleness correction would rest on an assumption. The disposal half, which
needs no adverts, is the half Finland replicates above.
""")
    print(OUT.read_text()[:1500])


if __name__ == "__main__":
    main()
