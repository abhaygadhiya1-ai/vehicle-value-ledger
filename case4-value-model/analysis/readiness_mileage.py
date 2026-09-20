"""Layer 2: what a car's mileage, measured against its own age cohort, does to its hazard.

Layer 1 says how likely a five-year-old car is to come to market. It cannot say which five-year-
old car. The answer the handoff specifies is a density-ratio estimator,

    hazard(age, mileage)  is proportional to  f(mileage | age, event) / f(mileage | age, parc)

which needs no per-car outcome: two mileage distributions at the same age are enough. The parc
side is the UK MOT register, the only European source that records an odometer for a whole fleet.

Two events, because the public data can measure two and they are not the same thing:

  **Part 1, leaving the fleet.** Every car tested in the baseline months of 2024 is looked for
  again in the following year. A car that never comes back has been scrapped, exported or laid
  up. Here the outcome *is* observed per car, so the hazard is a straight conditional probability
  and the density ratio is not needed - which makes this the part that can check the other.

  **Part 2, coming to market.** UK adverts of October 2022 against the same month's parc from the
  MOT register. This is the estimator as specified, and the one that matches the ledger's event.
  It cannot be checked per car, because an advert and a test record are different files.

**They do not agree, and that is the result.** Mileage predicts leaving the fleet strongly and
predicts reaching a forecourt not at all - the hardest-driven cars are disposed of rather than
advertised. An engine that ranks customers by mileage would surface cars about to be scrapped.

Both sides use whole years of age, computed the same way on each: test year (or advert year)
minus year of first use. That is not an age-at-listing analysis, so the whole-year trap in the
handoff does not bite; what would bite is comparing a month-precision age on one side with a
whole-year age on the other, and nothing here does.

Needs `mot_stream.py`. Streams about 5 GB over the network and writes none of it to disk.

Usage: .venv/bin/python analysis/readiness_mileage.py
"""
import json
import sys
from array import array
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import mot_stream as mot  # noqa: E402
from build_unified import md_table  # noqa: E402

HERE = Path(__file__).parent
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
OUT = HERE / "readiness_mileage_report.md"
CURVE = HERE / "readiness_mileage_effect.csv"
ELAST = HERE / "readiness_mileage_elasticity.csv"
FACTS = HERE / "readiness_mileage_facts.json"

MILES_TO_KM = 1.609344
MIN_KM, MAX_KM = 1_000, 400_000     # the same believable band the listings sample uses
AGES = (3, 20)                      # an MOT starts at three; past twenty the cohorts thin out
DECILES = 10

# A car tested in March is due again in March a year later. The follow-up runs from December 2024
# to July 2025 so that a test taken a month early, or a few months late, still counts as a return.
# `window_check` in part 1 measures whether that is wide enough instead of assuming it.
BASELINE = [(2024, 3)]
FOLLOWUP = [(2024, 12)] + [(2025, m) for m in range(1, 8)]

# The 2022 release is one file sorted by test date, so a prefix would be a January parc and a
# January odometer is three quarters of a year short of an October one. The whole year is read and
# then cut to the months around the advert date, which removes the drift instead of assuming it
# away.
PARC_MONTHS_2022 = ("2022-09", "2022-10", "2022-11")


def collect_baseline():
    """Cars tested in the baseline months, with an age and a believable odometer."""
    # C arrays, not lists: a few million Python ints would be a gigabyte of objects
    vid, age, km = array("q"), array("b"), array("f")
    for year, month in BASELINE:
        zf, names = mot.members(year, month=month)
        for name in names:
            for p in mot.rows(zf, name):
                fu = mot.reg_year(p)
                m = mot.mileage(p)
                if fu is None or m is None:
                    continue
                a = year - fu
                if not AGES[0] <= a <= AGES[1]:
                    continue
                k = m * MILES_TO_KM
                if not MIN_KM <= k <= MAX_KM:
                    continue
                vid.append(int(p[1]))
                age.append(a)
                km.append(k)
        print(f"  baseline {year}-{month:02d}: {len(vid):,} cars so far", flush=True)
    return (np.frombuffer(vid, dtype=np.int64), np.frombuffer(age, dtype=np.int8),
            np.frombuffer(km, dtype=np.float32))


def collect_followup():
    """Every vehicle id in the follow-up window, with which month of the window it was seen in.

    The month is kept so that part 1 can show where returns actually fall, and therefore whether
    the window is wide enough. Sorted by id and then month, so a lookup finds the earliest.
    """
    ids, months = [], []
    for i, (year, month) in enumerate(FOLLOWUP):
        zf, names = mot.members(year, month=month)
        for name in names:
            got = np.fromiter(mot.vehicle_ids(zf, name), dtype=np.int64)
            ids.append(got)
            months.append(np.full(len(got), i, dtype=np.int8))
        print(f"  follow-up {year}-{month:02d}: {sum(len(s) for s in ids):,} tests so far",
              flush=True)
    ids = np.concatenate(ids)
    months = np.concatenate(months)
    order = np.lexsort((months, ids))
    return ids[order], months[order]


def by_decile(age, km, flag):
    """Split each age cohort into mileage deciles and measure the event rate in each.

    The deciles are cut on the cohort's own mileage, so decile 1 is the least-driven tenth of
    five-year-olds and decile 10 the most-driven tenth. That is what "against its own cohort"
    means, and it removes the fact that older cars have simply driven further.
    """
    rows = []
    for a in range(AGES[0], AGES[1] + 1):
        sel = age == a
        if sel.sum() < 5_000:
            continue
        k, f = km[sel], flag[sel]
        edges = np.quantile(k, np.linspace(0, 1, DECILES + 1))
        edges[0], edges[-1] = -np.inf, np.inf
        which = np.clip(np.searchsorted(edges, k, side="right") - 1, 0, DECILES - 1)
        med = np.median(k)
        for d in range(DECILES):
            m = which == d
            if m.sum() < 200:
                continue
            rows.append({"age": a, "decile": d + 1, "n": int(m.sum()),
                         "median_km": float(np.median(k[m])),
                         "ratio": float(np.median(k[m]) / med),
                         "rate": float(f[m].mean())})
    return pd.DataFrame(rows)


def elasticity(tab):
    """How much the hazard moves with mileage, holding age fixed.

    log(rate) = age effect + b * log(mileage / the cohort's median mileage), weighted by how many
    cars sit in each cell. b is an elasticity: a car on twice its cohort's mileage has its hazard
    multiplied by 2**b. Fitting in logs keeps the result a multiplier, which is what layer 1 needs
    - a multiplier cannot push a probability below zero, and it composes with a level.
    """
    t = tab[(tab["rate"] > 0) & (tab["ratio"] > 0)]
    ages = sorted(t["age"].unique())
    X = np.zeros((len(t), len(ages) + 1))
    for i, a in enumerate(ages):
        X[:, i] = (t["age"] == a).to_numpy(float)
    X[:, -1] = np.log(t["ratio"].to_numpy(float))
    y = np.log(t["rate"].to_numpy(float))
    w = t["n"].to_numpy(float)
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    resid = y - X @ beta
    dof = max(len(t) - X.shape[1], 1)
    s2 = float((w * resid ** 2).sum() / dof)
    cov = s2 * np.linalg.pinv((X * w[:, None]).T @ X)
    return float(beta[-1]), float(np.sqrt(cov[-1, -1]))


def pooled(tab):
    """One decile profile across ages: the event rate in each decile relative to its own cohort."""
    t = tab.copy()
    base = t.groupby("age")["rate"].transform(lambda s: np.average(s, weights=t.loc[s.index, "n"]))
    t["relative"] = t["rate"] / base
    g = t.groupby("decile")
    return pd.DataFrame({
        "decile": g.size().index,
        "n": g["n"].sum().to_numpy(),
        "ratio": [np.average(x["ratio"], weights=x["n"]) for _, x in g],
        "relative": [np.average(x["relative"], weights=x["n"]) for _, x in g],
    })


def part1():
    print("part 1: leaving the fleet (MOT panel 2024 -> 2025)")
    vid, age, km = collect_baseline()
    seen, seen_month = collect_followup()
    idx = np.clip(np.searchsorted(seen, vid), 0, len(seen) - 1)
    came_back = seen[idx] == vid
    gone = (~came_back).astype(float)
    print(f"  {len(vid):,} cars, {gone.mean():.2%} never tested again")

    # Where the returns fall in the window. If they pile up against either edge, the window is
    # too narrow and some of the "never came back" are really "came back just outside".
    months = seen_month[idx][came_back]
    counts = np.bincount(months, minlength=len(FOLLOWUP))
    window = pd.DataFrame({
        "month": [f"{y}-{m:02d}" for y, m in FOLLOWUP],
        "returns": counts,
        "share": counts / max(counts.sum(), 1),
    })
    tab = by_decile(age, km, gone)
    b, se = elasticity(tab)
    return {"table": tab, "profile": pooled(tab), "b": b, "se": se, "window": window,
            "n": int(len(vid)), "rate": float(gone.mean())}


def part2():
    print("part 2: coming to market (UK adverts, October 2022, against the 2022 parc)")
    buckets = {a: array("f") for a in range(AGES[0], AGES[1] + 1)}
    zf, names = mot.members(2022)
    scanned = 0
    for p in mot.rows(zf, names[0]):
        scanned += 1
        if p[2][:7] not in PARC_MONTHS_2022:
            continue
        fu = mot.reg_year(p)
        m = mot.mileage(p)
        if fu is None or m is None:
            continue
        a = 2022 - fu
        k = m * MILES_TO_KM
        if AGES[0] <= a <= AGES[1] and MIN_KM <= k <= MAX_KM:
            buckets[a].append(k)
    print(f"  parc: {scanned:,} car tests scanned, "
          f"{sum(len(v) for v in buckets.values()):,} in {PARC_MONTHS_2022[0]}"
          f" to {PARC_MONTHS_2022[-1]}")

    lst = pd.read_parquet(LISTINGS, columns=["source", "country", "year", "mileage_km", "is_new"])
    ad = lst[(lst["source"] == "uk_2022_10") & (lst["country"] == "GB")
             & ~lst["is_new"].fillna(False).astype(bool)].dropna(subset=["year", "mileage_km"])
    ad = ad.assign(age=2022 - ad["year"].astype(int))
    ad = ad[ad["age"].between(*AGES) & ad["mileage_km"].between(MIN_KM, MAX_KM)]
    print(f"  adverts: {len(ad):,}")

    rows = []
    for a in range(AGES[0], AGES[1] + 1):
        pk = np.frombuffer(buckets[a], dtype=np.float32)
        lk = ad.loc[ad["age"] == a, "mileage_km"].to_numpy(float)
        if len(pk) < 5_000 or len(lk) < 500:
            continue
        edges = np.quantile(pk, np.linspace(0, 1, DECILES + 1))
        edges[0], edges[-1] = -np.inf, np.inf
        which = np.clip(np.searchsorted(edges, lk, side="right") - 1, 0, DECILES - 1)
        med = float(np.median(pk))
        parc_band = np.clip(np.searchsorted(edges, pk, side="right") - 1, 0, DECILES - 1)
        for d in range(DECILES):
            hits = int((which == d).sum())
            share = hits / len(lk)
            inband = pk[parc_band == d]
            rows.append({"age": a, "decile": d + 1, "n": hits,
                         "median_km": float(np.median(inband)),
                         "ratio": float(np.median(inband) / med),
                         # the density ratio: how over- or under-represented this tenth of the
                         # parc is among the cars that came to market
                         "rate": share / (1 / DECILES)})
    tab = pd.DataFrame(rows)
    b, se = elasticity(tab)
    return {"table": tab, "profile": pooled(tab), "b": b, "se": se,
            "n_parc": int(sum(len(v) for v in buckets.values())), "n_ads": int(len(ad))}


def write_report(p1, p2):
    """Build the report from the two results. Kept separate from the measurement so the wording
    can be fixed without streaming five gigabytes again; `--report-only` rebuilds it from the
    CSVs and the facts file the last run wrote."""
    def prof(p):
        return md_table(pd.DataFrame({
            "Mileage decile": p["profile"]["decile"].astype(int),
            "Mileage vs cohort median": p["profile"]["ratio"].map("{:.2f}x".format),
            "Hazard vs cohort average": p["profile"]["relative"].map("{:.2f}x".format),
        }))

    r1, r2 = p1["profile"]["relative"], p2["profile"]["relative"]
    top1 = r1.iloc[-1] / r1.iloc[0]
    mid2 = r2.iloc[4:6].mean()
    lines = [
        "# Layer 2: mileage against the cohort",
        "",
        "Layer 1 says how likely a car of a given age is to come to market. This says which car. "
        "Mileage is always measured against the car's own age cohort, so decile 1 is the least-"
        "driven tenth of five-year-olds and decile 10 the most-driven tenth - otherwise the "
        "result would only be saying that older cars have driven further.",
        "",
        "**The two events disagree, and the disagreement is the finding.**",
        "",
        f"- **Leaving the fleet rises steadily with mileage.** The most-driven tenth is "
        f"{top1:.1f} times as likely to go as the least-driven; a car on twice its cohort's "
        f"mileage is **{2 ** p1['b']:.2f} times** as likely to disappear.",
        f"- **Coming to market does not.** A car on twice its cohort's mileage is "
        f"**{2 ** p2['b']:.2f} times** as likely to be advertised - which is to say, no different. "
        f"The profile is not flat but arched: the middle of the mileage range is over-represented "
        f"among adverts at {mid2:.2f}x, and **both ends are under-represented**, the most-driven "
        f"tenth at {r2.iloc[-1]:.2f}x and the least-driven at {r2.iloc[0]:.2f}x.",
        "",
        "Read together they say something an engine has to respect: **mileage predicts disposal, "
        "not sale.** The hardest-driven cars do not reach a forecourt - they leave the fleet. A "
        "readiness model that ranks customers by mileage would surface cars about to be scrapped "
        "or exported, which is not the same list as customers about to buy.",
        "",
        "## Part 1: leaving the fleet, measured per car",
        "",
        f"{p1['n']:,} cars tested in March 2024, looked for again from December 2024 to July "
        f"2025. **{p1['rate']:.1%} never came back.** A car that is not tested again has been "
        "scrapped, exported or laid up; DVSA publishes no disposal flag, so this is the public "
        "proxy and it is a proxy.",
        "",
        prof(p1),
        "",
        f"Holding age fixed, **a car on twice its cohort's mileage is {2 ** p1['b']:.2f} times as "
        f"likely to leave the fleet** (elasticity {p1['b']:.3f}, standard error {p1['se']:.3f}).",
        "",
        "**Is the follow-up window wide enough?** A car that returned three months after the "
        "window closed would be counted as gone. This is where the returns actually landed:",
        "",
        md_table(pd.DataFrame({
            "Follow-up month": p1["window"]["month"],
            "Returns": p1["window"]["returns"].map("{:,}".format),
            "Share": p1["window"]["share"].map("{:.1%}".format),
        })),
        "",
        f"Returns peak in **{p1['window'].loc[p1['window']['returns'].idxmax(), 'month']}**, the "
        f"anniversary month. The two edge months hold {p1['window']['share'].iloc[0]:.1%} and "
        f"{p1['window']['share'].iloc[-1]:.1%} of them"
        + (", so the window is not clipping the tail."
           if max(p1["window"]["share"].iloc[0], p1["window"]["share"].iloc[-1]) < 0.06
           else ", which is enough at an edge that some returns fall outside the window and are "
                "counted as exits. Read the exit level as an upper bound."),
        "",
        "## Part 2: coming to market, the density-ratio estimator",
        "",
        f"{p2['n_ads']:,} UK adverts of October 2022 against {p2['n_parc']:,} MOT tests of the "
        "same September to November. No car is matched to itself: the estimator compares the "
        "mileage distribution of the cars that came to market with that of the fleet at the same "
        "age. A value of 1.00 means that tenth of the fleet is represented among the adverts "
        "exactly in proportion to its size.",
        "",
        prof(p2),
        "",
        f"Holding age fixed, **a car on twice its cohort's mileage is {2 ** p2['b']:.2f} times as "
        f"likely to be on the market** (elasticity {p2['b']:.3f}, standard error {p2['se']:.3f}) "
        "- and a single slope is the wrong summary of an arched profile. The deciles are the "
        "result; the elasticity is only there to be composed with layer 1.",
        "",
        "> **TRAP, and it cost a wrong answer once already.** The 2022 MOT file is one member "
        "> sorted by test date, so reading a prefix of it gives a **January** parc - and a January "
        "> odometer is three quarters of a year short of an October one. Priced that way the "
        "> estimator returned an elasticity of 0.194 and a confident story about high-mileage "
        "> cars flooding the market. Matching the parc to the advert month killed it. **Always "
        "> match the odometer month.**",
        "",
        "## The two events against each other",
        "",
        md_table(pd.DataFrame([
            {"Event": "Leaves the tested fleet", "Where": "MOT panel, 2024 to 2025",
             "Per car?": "yes", "Elasticity": f"{p1['b']:.3f}",
             "Twice the mileage": f"{2 ** p1['b']:.2f}x"},
            {"Event": "Comes to market", "Where": "UK adverts vs MOT parc, 2022",
             "Per car?": "no", "Elasticity": f"{p2['b']:.3f}",
             "Twice the mileage": f"{2 ** p2['b']:.2f}x"},
        ])),
        "",
        "## What this is not",
        "",
        "- **Two different events, and they answer differently.** Leaving the fleet is the end of "
        "a car's life; coming to market is a car changing hands. Neither is 'the customer is "
        "ready to replace'.",
        "- **Part 2 carries an assumption part 1 does not.** The adverts are a sample of the cars "
        "that came to market, and the estimator treats that sample as representative at each age. "
        "A site that carries more mid-mileage stock would produce exactly this arch.",
        "- **Advert mileage is what the seller typed; MOT mileage is what a tester read.** "
        "Different instruments, and part 2 compares one with the other.",
        "- **It is British.** The UK parc is the only European fleet with a public odometer. "
        "Layer 1 is Dutch. This layer is a shape, which the project has measured three times is "
        "the half that travels.",
        "- **Nothing here sees a car younger than three.** An MOT starts at three, so the first "
        "lease cycle is invisible in the parc.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.name}")


def load_saved():
    """Rebuild both results from what the last full run wrote."""
    tab = pd.read_csv(CURVE)
    el = pd.read_csv(ELAST).set_index("event")
    facts = json.loads(FACTS.read_text())
    out = {}
    for key, event in (("p1", "fleet_exit"), ("p2", "to_market")):
        t = tab[tab["event"] == event]
        out[key] = {"table": t, "profile": pooled(t),
                    "b": float(el.loc[event, "elasticity"]), "se": float(el.loc[event, "se"])}
    out["p1"].update(n=facts["n_cars"], rate=facts["exit_rate"],
                     window=pd.DataFrame(facts["window"]))
    out["p2"].update(n_parc=facts["n_parc"], n_ads=facts["n_ads"])
    return out["p1"], out["p2"]


def main():
    if "--report-only" in sys.argv:
        write_report(*load_saved())
        return
    p1 = part1()
    p2 = part2()
    out = pd.concat([p1["table"].assign(event="fleet_exit"),
                     p2["table"].assign(event="to_market")], ignore_index=True)
    out.to_csv(CURVE, index=False)
    pd.DataFrame([{"event": "fleet_exit", "elasticity": p1["b"], "se": p1["se"]},
                  {"event": "to_market", "elasticity": p2["b"], "se": p2["se"]}]).to_csv(
        ELAST, index=False)
    FACTS.write_text(json.dumps({
        "n_cars": p1["n"], "exit_rate": p1["rate"],
        "n_parc": p2["n_parc"], "n_ads": p2["n_ads"],
        "window": p1["window"].to_dict("records")}, indent=1))
    write_report(p1, p2)
    print(f"  fleet exit b={p1['b']:.3f} ({p1['se']:.3f}); to market b={p2['b']:.3f} "
          f"({p2['se']:.3f})")


if __name__ == "__main__":
    main()
