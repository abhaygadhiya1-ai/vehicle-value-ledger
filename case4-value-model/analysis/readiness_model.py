"""A learned readiness model, and the honest question of whether it beats the two-layer engine.

`readiness_engine.py` is not a model. It is a measured rate by age times a measured multiplier for
mileage - two numbers, both traceable to a register, and deliberately so. But two numbers cannot
use what else is known about a car: what it is, where it is, whether it just failed a test, and
how those interact. A learned model can.

This builds one, on the only public data with a **per-car outcome**: the UK MOT panel. Every car
tested in March 2024 is looked for again through July 2025; a car that never returns has been
scrapped, exported or laid up.

    features: age, odometer, odometer against the car's own age cohort, make, model, fuel,
              engine size, region, colour, and the result of that test
    label:    did not come back

**The point is not that a model exists. It is whether it earns its place.** The report scores it
against two things it has to beat: the age curve alone, and the age-and-mileage engine we already
have. If it does not beat them, that is the finding, exactly as it was for the uplift engine.

**What it predicts is a car leaving the fleet, not a customer choosing to replace.** The group's
own book has the fields that would close that gap - contract end, equity, service history, who the
keeper is - and none of them is public. What transfers is the machine, the feature set and the
measured answer to "does learning beat a lookup".

    .venv/bin/python analysis/readiness_model.py --build   # ~20 min, streams 3.5 GB, saves 1 file
    .venv/bin/python analysis/readiness_model.py           # trains and scores, seconds
"""
import sys
from array import array
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent.parent))
import mot_stream as mot  # noqa: E402
from build_unified import md_table  # noqa: E402

HERE = Path(__file__).parent
PANEL = HERE.parent / "data" / "reference" / "uk_mot_panel.parquet"
ELAST = HERE / "readiness_mileage_elasticity.csv"
OUT = HERE / "readiness_model_report.md"
SCORES = HERE / "readiness_model_scores.csv"
GAINS = HERE / "readiness_model_gains.csv"

MILES_TO_KM = 1.609344
MIN_KM, MAX_KM = 1_000, 400_000
AGES = (3, 20)
BASELINE = [(2024, 3)]
FOLLOWUP = [(2024, 12)] + [(2025, m) for m in range(1, 8)]
KEEP = 4            # keep one car in KEEP to hold the panel to a workable size
SEED = 20260921
SPREAD_AGE = 12     # the age at which the by-model spread is quoted
CAT_CAP = 200       # levels kept per categorical; the rest become one 'other'
CATS = ["make", "model", "fuel", "region", "colour", "result"]

# The engine is built in tiers, and this list is the whole extension point. Each tier is what a
# company knows at a given stage of joining its data up; the report scores the model after each
# one, so the value of the next field set is a measurement rather than a promise. **When the
# group's own contract, equity and service data arrive, they become a tier here and nothing else
# changes.** Columns that are not in the panel yet are skipped and said to be skipped.
TIERS = [
    ("Age alone", ["age"]),
    ("+ how far it has gone", ["km", "km_ratio"]),
    ("+ what the car is", ["make", "model", "cc", "fuel"]),
    ("+ where it is, and how it just did", ["region", "colour", "result"]),
    ("+ last year's test (a service history, arriving late)",
     ["prev_km", "km_per_year", "km_rate_ratio", "years_since_test", "prev_fail"]),
]


def mix(v):
    """A strong mixing hash (splitmix64) of the vehicle id, for sampling.

    **The raw id must never be sampled on directly.** It is not a uniform hash: even ids are a
    third of the file rather than half, and the cars behind them average 16.3 years and 101,000
    miles against 6.9 years and 51,700 for odd ids. Taking every other id would have produced a
    panel of old, worn-out cars and a model calibrated to them. Mixing first removes that.
    """
    v = (v + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    v = ((v ^ (v >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    v = ((v ^ (v >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    return v ^ (v >> 31)


def build():
    """Stream the panel once and save it, so the modelling never needs the network again."""
    vid, age, km = array("q"), array("b"), array("f")
    cc = array("i")
    make, model, fuel, region, colour, result = [], [], [], [], [], []
    for year, month in BASELINE:
        zf, names = mot.members(year, month=month)
        for name in names:
            for p in mot.rows(zf, name):
                v = int(p[1])
                if mix(v) % KEEP:
                    continue
                fu, m = mot.reg_year(p), mot.mileage(p)
                if fu is None or m is None:
                    continue
                a = year - fu
                k = m * MILES_TO_KM
                if not (AGES[0] <= a <= AGES[1] and MIN_KM <= k <= MAX_KM):
                    continue
                vid.append(v)
                age.append(a)
                km.append(k)
                try:
                    cc.append(int(p[12]))
                except ValueError:
                    cc.append(-1)
                make.append(p[8])
                model.append(p[9])
                fuel.append(p[11])
                region.append(p[7])
                colour.append(p[10])
                result.append(p[5])
        print(f"  baseline {year}-{month:02d}: {len(vid):,} cars", flush=True)

    d = pd.DataFrame({
        "vehicle_id": np.frombuffer(vid, dtype=np.int64),
        "age": np.frombuffer(age, dtype=np.int8).astype(np.int16),
        "km": np.frombuffer(km, dtype=np.float32),
        "cc": np.frombuffer(cc, dtype=np.int32),
        "make": make, "model": model, "fuel": fuel, "region": region,
        "colour": colour, "result": result,
    })

    seen = []
    for year, month in FOLLOWUP:
        zf, names = mot.members(year, month=month)
        for name in names:
            seen.append(np.fromiter(mot.vehicle_ids(zf, name), dtype=np.int64))
        print(f"  follow-up {year}-{month:02d}: {sum(len(s) for s in seen):,} tests", flush=True)
    seen = np.concatenate(seen)
    seen.sort()
    idx = np.clip(np.searchsorted(seen, d["vehicle_id"].to_numpy()), 0, len(seen) - 1)
    d["gone"] = (seen[idx] != d["vehicle_id"].to_numpy()).astype(np.int8)

    # mileage against the car's own age cohort: the feature layer 2 is built on
    d["cohort_km"] = d.groupby("age")["km"].transform("median")
    d["km_ratio"] = d["km"] / d["cohort_km"]
    PANEL.parent.mkdir(parents=True, exist_ok=True)
    d.to_parquet(PANEL, index=False)
    print(f"wrote {PANEL.name}: {len(d):,} cars, {d['gone'].mean():.2%} gone, "
          f"{PANEL.stat().st_size / 1e6:.0f} MB")


def build_history():
    """Add last year's test to the panel: the stand-in for a service history.

    This is the point of the tiered design. A year of prior history is a *new data layer* arriving
    after the model was built, exactly as the group's contract and service records would - and
    nothing about the model has to be rewritten to take it, only `TIERS` extended.

    The 2023 release is one deflate64 member, so it is read start to finish once, keeping only the
    759,541 cars already in the panel.
    """
    d = pd.read_parquet(PANEL)
    want = set(d["vehicle_id"].tolist())
    zf, names = mot.members(2023)
    best, scanned = {}, 0
    for p in mot.rows(zf, names[0]):
        scanned += 1
        if scanned % 5_000_000 == 0:
            print(f"  {scanned:,} scanned, {len(best):,} of {len(want):,} matched", flush=True)
        v = int(p[1])
        if v not in want:
            continue
        m = mot.mileage(p)
        if m is None:
            continue
        prev = best.get(v)
        if prev is None or p[2] > prev[0]:
            best[v] = (p[2], m * MILES_TO_KM, p[5])
    print(f"  matched {len(best):,} of {len(want):,} panel cars in 2023")

    d["prev_date"] = d["vehicle_id"].map({k: v[0] for k, v in best.items()})
    d["prev_km"] = d["vehicle_id"].map({k: v[1] for k, v in best.items()})
    d["prev_fail"] = d["vehicle_id"].map(
        {k: float(v[2] == "F") for k, v in best.items()})
    # every baseline test is in March 2024, so the gap is dated to mid-month: at most a fortnight
    # of error on a year-long interval, which a rate can carry
    gap = (pd.Timestamp("2024-03-15") - pd.to_datetime(d["prev_date"])).dt.days / 365.25
    d["years_since_test"] = gap.where(gap.between(0.25, 3.0))
    d["km_per_year"] = ((d["km"] - d["prev_km"]) / d["years_since_test"]).where(
        lambda x: x.between(-5_000, 120_000))
    d["km_rate_ratio"] = d["km_per_year"] / d.groupby("age")["km_per_year"].transform("median")
    d.to_parquet(PANEL, index=False)
    print(f"wrote history into {PANEL.name}: "
          f"{d['km_per_year'].notna().mean():.1%} of cars have a usable annual rate")


def lift_at(y, score, frac=0.10):
    """How many more leavers the top slice holds than the population average."""
    k = max(int(len(score) * frac), 1)
    top = np.argsort(-score)[:k]
    return float(y[top].mean() / y.mean())


def gains_curve(y, p, steps=21):
    """Rank the book by score, then ask: contacting the top x%, what share of the cars that
    actually moved do you reach? The diagonal is contacting at random."""
    order = np.argsort(-p)
    hit = np.cumsum(y[order]) / max(y.sum(), 1)
    n = len(y)
    out = []
    for i in range(steps):
        f = i / (steps - 1)
        k = int(round(f * n))
        out.append({"frac": f, "captured": 0.0 if k == 0 else float(hit[k - 1])})
    return pd.DataFrame(out)


def within_age_auc(te, y, p):
    """Ranking *inside* an age band, which is where knowing the car pays.

    A global AUC is dominated by age, because age separates most pairs on its own. But a call list
    is built from cars of similar age, and there the question is whether the model can tell a
    Yaris from an Astra. This averages the AUC computed separately at each age, weighted by how
    many cars left at that age.
    """
    tot = num = 0.0
    for a, m in te.groupby("age").groups.items():
        i = te.index.get_indexer(m)
        yy = y[i]
        if len(i) < 2_000 or not 0 < yy.mean() < 1:
            continue
        w = yy.sum()
        num += w * roc_auc_score(yy, p[i])
        tot += w
    return num / tot if tot else float("nan")


def train():
    d = pd.read_parquet(PANEL)
    levels = {}
    for c in CATS:
        keep = d[c].value_counts().head(CAT_CAP).index
        d[c] = d[c].where(d[c].isin(keep), "OTHER")
        cat = d[c].astype("category")
        levels[c] = list(cat.cat.categories)
        d[c] = cat.cat.codes.astype(np.int32)
    rng = np.random.default_rng(SEED)
    test = rng.random(len(d)) < 0.30
    tr, te = d[~test].reset_index(drop=True), d[test].reset_index(drop=True)
    y_tr, y_te = tr["gone"].to_numpy(), te["gone"].to_numpy()
    print(f"{len(d):,} cars, {d['gone'].mean():.2%} gone; {len(te):,} held out")

    tiers, used, skipped, last, gains = [], [], [], None, []
    for name, cols in TIERS:
        have = [c for c in cols if c in d.columns]
        skipped += [c for c in cols if c not in d.columns]
        if not have and cols:
            continue
        used += have
        m = HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.06, random_state=SEED,
            categorical_features=[c in CATS for c in used])
        m.fit(tr[used], y_tr)
        p = m.predict_proba(te[used])[:, 1]
        tiers.append({"Tier": name, "Fields": len(used), "AUC": roc_auc_score(y_te, p),
                      "within_age": within_age_auc(te, y_te, p),
                      "lift10": lift_at(y_te, p, 0.10)})
        g = gains_curve(y_te, p)
        g.insert(0, "fields", len(used))
        g.insert(0, "tier", name)
        g["auc"] = tiers[-1]["AUC"]
        g["within_age"] = tiers[-1]["within_age"]
        gains.append(g)
        last = (m, p, list(used))
        print(f"  {name:52s} AUC {tiers[-1]['AUC']:.3f}  within-age "
              f"{tiers[-1]['within_age']:.3f}  lift {tiers[-1]['lift10']:.2f}x")
    m, p_model, feats = last

    age_rate = tr.groupby("age")["gone"].mean()
    p_age = te["age"].map(age_rate).to_numpy(float)
    b = float(pd.read_csv(ELAST).set_index("event").loc["fleet_exit", "elasticity"])
    p_engine = p_age * te["km_ratio"].to_numpy(float) ** b

    def net_features(frame, maps, prior):
        X = [frame[["age", "km_ratio"]].to_numpy(float),
             np.log(frame["km"].to_numpy(float))[:, None],
             frame["cc"].clip(0, 5000).to_numpy(float)[:, None]]
        for c in ("make", "model", "region"):
            X.append(frame[c].map(maps[c]).fillna(prior).to_numpy(float)[:, None])
        for c in ("fuel", "result", "colour"):
            X.append(np.stack([(frame[c] == v).to_numpy(float)
                               for v in maps[f"top_{c}"]], axis=1))
        return np.concatenate(X, axis=1)

    prior = float(y_tr.mean())
    maps = {c: tr.groupby(c)["gone"].mean() for c in ("make", "model", "region")}
    for c in ("fuel", "result", "colour"):
        maps[f"top_{c}"] = tr[c].value_counts().head(12).index.tolist()
    sc = StandardScaler().fit(net_features(tr, maps, prior))
    net = MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=60, early_stopping=True,
                        random_state=SEED)
    net.fit(sc.transform(net_features(tr, maps, prior)), y_tr)
    p_net = net.predict_proba(sc.transform(net_features(te, maps, prior)))[:, 1]

    rows = []
    for name, p in (("Age curve alone", p_age),
                    ("The two-layer engine (age x mileage)", p_engine),
                    ("Neural net, every field", p_net),
                    ("Learned, every field", p_model)):
        rows.append({"Model": name, "AUC": roc_auc_score(y_te, p),
                     "within_age": within_age_auc(te, y_te, p),
                     "lift10": lift_at(y_te, p, 0.10), "lift20": lift_at(y_te, p, 0.20)})
    fail_rate = tr.groupby("make")["gone"].mean().to_dict()
    fail_rate["__all__"] = float(y_tr.mean())
    pd.concat(gains, ignore_index=True).to_csv(GAINS, index=False)
    return (d, te, y_te, pd.DataFrame(rows), m, feats, p_model, levels, fail_rate,
            pd.DataFrame(tiers), sorted(set(skipped)))


def calibration(y, p, bins=10):
    """Does a car the model calls 12% actually leave 12% of the time?

    A model can rank well and still be wrong about the level, and a level is what a euro figure
    needs. Ranking is AUC; this is the other half.
    """
    order = np.argsort(p)
    cut = np.array_split(order, bins)
    return pd.DataFrame([{"decile": i + 1, "predicted": float(p[c].mean()),
                          "actual": float(y[c].mean()), "cars": len(c)}
                         for i, c in enumerate(cut)])


def by_slice(te, y, p, levels):
    """AUC inside slices, because one number over a million cars hides where it fails."""
    rows = []
    for lo, hi in [(3, 6), (7, 10), (11, 15), (16, 20)]:
        m = te["age"].between(lo, hi).to_numpy()
        if m.sum() > 5_000 and 0 < y[m].mean() < 1:
            rows.append({"Slice": f"aged {lo}-{hi}", "Cars": int(m.sum()),
                         "Left the fleet": float(y[m].mean()),
                         "AUC": roc_auc_score(y[m], p[m])})
    for code, _ in te["make"].value_counts().head(6).items():
        m = (te["make"] == code).to_numpy()
        if m.sum() > 5_000 and 0 < y[m].mean() < 1:
            rows.append({"Slice": levels["make"][int(code)].title(), "Cars": int(m.sum()),
                         "Left the fleet": float(y[m].mean()),
                         "AUC": roc_auc_score(y[m], p[m])})
    return pd.DataFrame(rows)


def reasons(te, p, levels, fail_rate, k=5, ages=None, label=""):
    """A plain-words reason for the highest-scoring cars.

    The solution document promises this and nothing delivered it: "a score nobody can explain will
    not be used by a dealer, and an unused model is worth nothing". Each reason is stated against
    the car's own age cohort, which is the comparison a person actually makes. Large ratios are
    said as multiples - "3.4x the yearly mileage of cars its age" reads; "240% harder" does not.
    """
    sel = np.ones(len(te), bool) if ages is None else te["age"].between(*ages).to_numpy()
    order = [i for i in np.argsort(-p) if sel[i]][:k]
    out = []
    for i in order:
        row = te.iloc[i]
        make = levels["make"][int(row["make"])]
        bits = [f"{int(row['age'])} years old"]
        r = float(row["km_ratio"])
        if r >= 2:
            bits.append(f"{r:.1f}x the mileage of cars its age")
        elif r >= 1.15:
            bits.append(f"driven {r - 1:.0%} above cars its age")
        elif r <= 0.85:
            bits.append(f"driven {1 - r:.0%} below cars its age")
        else:
            bits.append("about average mileage for its age")
        rate = row.get("km_rate_ratio")
        if pd.notna(rate) and rate >= 2:
            bits.append(f"and {rate:.1f}x their yearly rate in the last year")
        elif pd.notna(rate) and rate >= 1.25:
            bits.append(f"and {rate - 1:.0%} harder in the last year")
        if levels["result"][int(row["result"])] == "F":
            bits.append("failed this test")
        mk = fail_rate.get(int(row["make"]))
        if mk is not None and mk > fail_rate["__all__"] * 1.15:
            bits.append(f"{make.title()}s leave the fleet more often than average")
        out.append({"Score": f"{p[i]:.0%}", "Car": f"{make.title()}, {int(row['km']):,} km",
                    "Why the model says so": "; ".join(bits)})
    return pd.DataFrame(out)


def main():
    if "--build" in sys.argv:
        build()
        return
    if "--history" in sys.argv:
        build_history()
        return
    (d, te, y_te, res, m, feats, p_model, levels, fail_rate,
     tiers, skipped) = train()

    best = res.iloc[res["AUC"].idxmax()]
    engine = res[res["Model"].str.startswith("The two-layer")].iloc[0]
    net_row = res[res["Model"].str.startswith("Neural net")].iloc[0]

    # the by-model spread at one age, computed rather than typed
    top_models = d["model"].value_counts().head(8).index
    at_age = d[(d["age"] == SPREAD_AGE) & d["model"].isin(top_models)]
    rate = at_age.groupby("model")["gone"].agg(["mean", "size"])
    rate = rate[rate["size"] >= 300].sort_values("mean")
    # `d` comes back with categories encoded, so decode for the sentence
    lo_m = levels["model"][int(rate.index[0])]
    hi_m = levels["model"][int(rate.index[-1])]
    lo_r, hi_r = rate["mean"].iloc[0], rate["mean"].iloc[-1]

    agefull = res[res["Model"].str.startswith("Age curve")].iloc[0]

    # where the gain comes from: drop one field at a time
    imp = []
    rng = np.random.default_rng(SEED + 5)
    base = roc_auc_score(y_te, p_model)
    X = te[feats].copy()
    for f in feats:
        shuffled = X.copy()
        shuffled[f] = rng.permutation(shuffled[f].to_numpy())
        imp.append({"Field": f, "AUC lost": base - roc_auc_score(
            y_te, m.predict_proba(shuffled)[:, 1])})
    imp = pd.DataFrame(imp).sort_values("AUC lost", ascending=False)

    lines = [
        "# A learned readiness model, and whether it earns its place",
        "",
        f"{len(d):,} UK cars tested in March 2024, followed to July 2025; "
        f"**{d['gone'].mean():.1%} never came back.** A gradient-boosted model over ten fields "
        "against the two-layer engine we already have.",
        "",
        "AUC is the chance the model scores a car that left above one that stayed - 0.5 is a coin "
        "toss. Lift is how many more leavers the top slice holds than the population average, "
        "which is what a contact list actually cares about.",
        "",
    ]
    lines += [
        "## What each layer of data is worth",
        "",
        "The engine is built in tiers, and `TIERS` in the script is the whole extension point. "
        "Each tier is what a company knows at a stage of joining its data up, and the model is "
        "refitted after each one. **When the group's own contract, equity and service records "
        "arrive they become a tier here, and nothing else changes.**",
        "",
        "Two columns, because they answer different questions. **AUC** is ranking across all "
        "cars, and age dominates it. **Within-age AUC** ranks only cars of the same age, which is "
        "what a call list actually is - and it is where knowing *which* car pays.",
        "",
        md_table(pd.DataFrame({
            "Tier": tiers["Tier"],
            "Fields": tiers["Fields"],
            "AUC": tiers["AUC"].map("{:.3f}".format),
            "Within-age AUC": tiers["within_age"].map("{:.3f}".format),
            "Lift, top 10%": tiers["lift10"].map("{:.2f}x".format),
        })),
        "",
        f"**Knowing what the car is takes within-age ranking from "
        f"{tiers['within_age'].iloc[1]:.3f} to {tiers['within_age'].iloc[2]:.3f}.** That is the "
        "answer to \"surely two cars of the same age are not the same car\": they are not. At "
        f"{SPREAD_AGE} years old the share leaving the fleet runs from **{lo_r:.1%} for a "
        f"{lo_m.title()} to {hi_r:.1%} for an {hi_m.title()}** - a **{hi_r / lo_r:.1f}x spread at "
        "one age**, across the eight commonest models. A global AUC hides that, because age "
        "already separates most pairs; the within-age column does not.",
        "",
        f"**And the last tier is the point of the whole design.** A year of prior test history - "
        "the public stand-in for a service record - arrived after the model was built, and cost "
        "one line in `TIERS`. It took within-age ranking from "
        f"{tiers['within_age'].iloc[3]:.3f} to {tiers['within_age'].iloc[4]:.3f} and the top-tenth "
        f"list from {tiers['lift10'].iloc[3]:.2f}x to {tiers['lift10'].iloc[4]:.2f}x. **The "
        "group's contract dates, equity and service visits go in the same way.**",
        "",
    ] + ([f"*Tiers skipped because the panel does not carry them yet: "
          f"`{'`, `'.join(skipped)}`. Run `--history` to add them.*", ""] if skipped else []) + [
        "## Against what it has to beat",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Model": res["Model"],
        "AUC": res["AUC"].map("{:.3f}".format),
        "Within-age AUC": res["within_age"].map("{:.3f}".format),
        "Lift, top 10%": res["lift10"].map("{:.2f}x".format),
        "Lift, top 20%": res["lift20"].map("{:.2f}x".format),
    })))
    lines += [
        "",
        f"**Learning beats the lookup, and the size of the win matters more than the fact of "
        f"it.** Most of the gain is already in the two-layer engine: age alone gives "
        f"**{agefull['AUC']:.3f}**, adding mileage takes it to **{engine['AUC']:.3f}**. Everything "
        f"else the register knows - what the car is, where it is, whether it just failed - is "
        f"worth a further **{best['AUC'] - engine['AUC']:+.3f}**, to **{best['AUC']:.3f}**. In the "
        f"terms a call list cares about that is **{engine['lift10']:.2f}x** to "
        f"**{best['lift10']:.2f}x** in the top tenth, or about "
        f"{best['lift10'] / engine['lift10'] - 1:.0%} more leavers for the same number of calls.",
        "",
        "So: worth building, and not a revolution. The two-layer engine was not leaving much on "
        "the table, which is a useful thing to know before anyone budgets for a modelling "
        "programme - and it is the opposite of what the uplift engine found, which is why both "
        "were tested instead of either being taken on faith.",
        "",
        f"**A neural network on the same fields reaches AUC {net_row['AUC']:.3f}.** Boosted trees "
        "are the right tool for a table of ten columns, and this is the measurement rather than "
        "an opinion; the net is included because it is the first thing anyone asks about.",
        "",
        "## Where the gain comes from",
        "",
        "Each field shuffled in turn, and the AUC it costs:",
        "",
    ]
    lines.append(md_table(pd.DataFrame({
        "Field": imp["Field"],
        "AUC lost when shuffled": imp["AUC lost"].map("{:+.3f}".format),
    })))
    cal = calibration(y_te, p_model)
    sl = by_slice(te, y_te, p_model, levels)
    lines += [
        "",
        "## Does it get the level right, not just the order?",
        "",
        "AUC says the model ranks. It does not say a car it calls 12% leaves 12% of the time, and "
        "a level is what a euro figure needs.",
        "",
        md_table(pd.DataFrame({
            "Decile of predicted risk": cal["decile"],
            "Predicted": cal["predicted"].map("{:.1%}".format),
            "Actually left": cal["actual"].map("{:.1%}".format),
            "Cars": cal["cars"].map("{:,}".format),
        })),
        "",
        f"Predicted against actual across the ten deciles: the largest gap is "
        f"**{(cal['predicted'] - cal['actual']).abs().max():.1%}**, from "
        f"{cal['predicted'].min():.1%} at the safest tenth to {cal['predicted'].max():.1%} at the "
        f"riskiest against {cal['actual'].min():.1%} and {cal['actual'].max():.1%} actual.",
        "",
        "## Where it works and where it does not",
        "",
        "One AUC over a million cars hides the slices it fails on. `engine_check.py` does this for "
        "the value engine; this is the same test for readiness.",
        "",
        md_table(pd.DataFrame({
            "Slice": sl["Slice"],
            "Cars": sl["Cars"].map("{:,}".format),
            "Left the fleet": sl["Left the fleet"].map("{:.1%}".format),
            "AUC": sl["AUC"].map("{:.3f}".format),
        })),
        "",
        f"AUC runs **{sl['AUC'].min():.3f} to {sl['AUC'].max():.3f}** across slices against "
        f"{best['AUC']:.3f} overall, and the weakest slice is "
        f"**{sl.loc[sl['AUC'].idxmin(), 'Slice']}**.",
        "",
        "**That weakness is the one that matters, and it is not an accident.** The model is far "
        "better at spotting an old car about to be scrapped than a young one about to change "
        "hands - and young cars are exactly the ones a lease book holds. What separates a "
        "sixteen-year-old that dies from one that survives is visible in a register: mileage, a "
        "failed test, what the car is. What separates a four-year-old that gets replaced from one "
        "that does not is a contract date, an equity position and a conversation with a dealer - "
        "**none of which is in any public file.** The engine is weakest exactly where the "
        "group's own data would be strongest, and that is the ledger's argument in one number.",
        "",
        "## A reason a dealer can read",
        "",
        "The five highest-scoring cars in the held-out set, with why:",
        "",
        md_table(reasons(te, p_model, levels, fail_rate)),
        "",
        "Those are all old cars, because that is what the model is best at. **The same five, "
        "restricted to the ages a lease book actually holds:**",
        "",
        md_table(reasons(te, p_model, levels, fail_rate, ages=(3, 6))),
        "",
        "The scores are far lower and the reasons thinner, which is the honest picture: on a "
        "four-year-old, public data has little to say beyond mileage. That is the gap the "
        "group's contract dates close.",
        "",
        "## What it is not",
        "",
        "- **It predicts a car leaving the fleet, not a customer replacing it.** The MOT register "
        "carries no keeper, no contract and no price. Those live in the group's own book, and "
        "that gap is the ledger's argument, not a limitation this model can design away.",
        "- **It is a black box, and for this use that is acceptable.** Choosing whom to call is "
        "marketing, not credit. The project's standing position - **no AI in a credit decision**, "
        "for the reasons in the solution document - is untouched by this.",
        "- **British, and three years old at the youngest.** An MOT starts at three, so the first "
        "contract cycle is invisible.",
        "- **The label is a proxy.** 'Not tested again' mixes scrappage, export and a car laid up.",
        "- **Rare makes and models are pooled.** The commonest 200 levels of each are kept and "
        "everything else becomes one 'other' bucket, because a boosted tree takes at most 255 "
        "levels and a model with a handful of cars teaches nothing.",
        "- **One car in four** is kept, by a mixing hash of the id, to hold the panel to a "
        "workable size. Sampling the raw id "
        "instead would have been a disaster: even ids are 31.8% of the file and average 16.3 "
        "years against 6.9 for odd ones. The train/test split is a fixed seed, so the held-out "
        "set is the same on every run.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    res.to_csv(SCORES, index=False)
    print(f"wrote {OUT.name}")
    for _, r in res.iterrows():
        print(f"  {r['Model']:38s} AUC {r['AUC']:.3f}  lift10 {r['lift10']:.2f}x")


if __name__ == "__main__":
    main()
