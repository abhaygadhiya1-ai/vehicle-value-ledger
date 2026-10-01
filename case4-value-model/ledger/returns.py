"""X4 part 5: life after sale. When each car came back to market, from the real register, and the price it changed
hands at, which is synthetic.

**The dates are real.** X1's cars are real Dutch registrations (RDW), so the register's current-keeper date
(`datum_tenaamstelling`) of the very same cars says when each last changed keeper. X1 read the plates only to fix the
row order and never stored them; this pull reads them again the same way (the same filter, sorted by first registration
date and plate) and pins each `car_id` to its plate date by date, by a sequence match on all seven fields X1 kept (make,
model, date, catalogue price, body, variant, trim). Where a car left the register or a new one arrived, the cars sharing
its seven fields that day cannot be told apart (fleet batches are identical), so they are left out rather than guessed;
every other car keeps its unique place in plate order. The plates stay in memory and are never written. A car with no
current keeper in the register (exported, or off the road) gets no keeper event; its export flag is counted.

**What a date means.** Only the current keeper is visible, so a later change hides an earlier one: every count here is
a lower bound (`analysis/keeper_history_report.md`). A change within 3 months of first registration is a handover
(a dealer registration passing to its first customer: the same 3-month window as the keeper-history analysis), not a
car coming back. A later change is `came_to_market`. Both are facts, recorded on the day the register was read: that is
when this ledger learned them. A live ledger reading the register monthly would learn each within a month, and would
also see the changes now hidden.

**The price is synthetic.** The register holds no prices. Each car that came back gets a `resale` event (kind
`synthetic`): the part-3 mark at that date (catalogue × the Dutch curve at the car's age × the level, held at the last
published index month for dates after it), times a draw from the adverts' spread at that age (a split normal in logs
whose 10th and 90th percentiles are the band's). It exercises the ledger; it measures nothing.

**This is a demo, not evidence** (decision B): layer 1 of the readiness engine was built on the same register, so the
engine-against-register table in the report is partly in-sample. And X1's buyer types are synthetic, so the real
dates say nothing about retail against fleet.

Decision B (`notes/Case4_Extensions.md`, X4): the user's, 25 September.
Output: data/ledger/rdw_keepers.parquet (car_id, dates, export flag, read date; no plates), events in the store, and
ledger/x4_returns_report.md.
Usage: .venv/bin/python ledger/returns.py [--pull]   (--pull reads the register again; otherwise the cached read)
"""
import difflib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "leak1"))
from build_reference import RDW_URL, align_names, rdw_group  # noqa: E402
from build_unified import MAKE_ALIASES, STELLANTIS, norm_name  # noqa: E402
from population import OUT as CARS, START, STOP  # noqa: E402
from readiness import MODEL as READY  # noqa: E402
from remark import curve, level, share  # noqa: E402
from store import STORE, append, content_hash, events, open_store, timeline  # noqa: E402

KEEPERS = ROOT / "data" / "ledger" / "rdw_keepers.parquet"
MATCH = KEEPERS.with_name("rdw_keepers_match.json")   # how the re-read matched X1's cars
REPORT = HERE / "x4_returns_report.md"
PAGE = 50_000
HANDOVER_DAYS = 91        # 3 months: the keeper-history analysis's early-change window
SEED = 20250925
FIELDS = ["make", "model", "first_reg_date", "list_price_eur", "body", "variant", "trim"]
Z90 = 1.2815515655446004  # the standard normal's 90th percentile


def where():
    """X1's population filter (`leak1/population.py`), rebuilt the same way."""
    window = (f"voertuigsoort='Personenauto' AND datum_eerste_toelating_dt >= '{START}T00:00:00.000' "
              f"AND datum_eerste_toelating_dt < '{STOP}T00:00:00.000' "
              "AND datum_eerste_tenaamstelling_in_nederland_dt = datum_eerste_toelating_dt")
    makes = rdw_group("merk,count(1) AS n", window, "merk", limit=50_000)
    group = sorted(makes.loc[norm_name(makes["merk"]).replace(MAKE_ALIASES).isin(STELLANTIS), "merk"])
    return (window + " AND merk IN (" + ",".join("'" + m.replace("'", "''") + "'" for m in group) + ")"
            + " AND catalogusprijs IS NOT NULL")


def pull():
    """The same cars as X1's pull, with their keeper dates. Paged by plate, not offset (STATE, RDW trap)."""
    cols = ["kenteken", "merk", "handelsbenaming", "datum_eerste_toelating_dt", "catalogusprijs", "inrichting",
            "variant", "uitvoering", "datum_tenaamstelling_dt", "export_indicator"]
    w, pages, last = where(), [], ""
    while True:
        r = requests.get(RDW_URL, params={"$select": ",".join(cols), "$where": f"({w}) AND kenteken > '{last}'",
                                          "$order": "kenteken", "$limit": PAGE}, timeout=900)
        r.raise_for_status()
        pages.append(pd.DataFrame(r.json()).reindex(columns=cols))
        print(f"  pulled {sum(map(len, pages)):,}", flush=True)
        if len(pages[-1]) < PAGE:
            break
        last = pages[-1]["kenteken"].iloc[-1]
    raw = pd.concat(pages, ignore_index=True)
    make, model = align_names(raw["merk"], raw["handelsbenaming"])
    return pd.DataFrame({
        "make": make, "model": model, "first_reg_date": pd.to_datetime(raw["datum_eerste_toelating_dt"]),
        "list_price_eur": pd.to_numeric(raw["catalogusprijs"]).astype("int64"), "body": raw["inrichting"],
        "variant": raw["variant"], "trim": raw["uitvoering"], "plate": raw["kenteken"],
        "keeper_date": pd.to_datetime(raw["datum_tenaamstelling_dt"]), "export": raw["export_indicator"],
    }).sort_values(["first_reg_date", "plate"], ignore_index=True)


def key(d):
    return list(zip(*(d[c].astype("string").fillna("") for c in FIELDS)))


def align(cars, now):
    """car_id for each row of `now`, date by date. Where both lists hold the same cars they match row for row. Around a
    gap, a sequence match keeps every pair except the cars whose seven fields equal a car that left or arrived that day:
    which of those identical cars left is unknowable."""
    out, removed, ambiguous = [], 0, 0
    now_by_date = dict(tuple(now.groupby("first_reg_date")))
    for date, x in cars.groupby("first_reg_date"):
        y = now_by_date.get(date, now.iloc[0:0])
        kx, ky = key(x), key(y)
        if kx == ky:
            out.append(y.assign(car_id=x["car_id"].to_numpy()))
            continue
        sm = difflib.SequenceMatcher(None, kx, ky, autojunk=False)
        changed = set()
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                changed |= set(kx[i1:i2]) | set(ky[j1:j2])
        pairs = [(a + i, b + i) for a, b, n in sm.get_matching_blocks() for i in range(n) if kx[a + i] not in changed]
        out.append(y.iloc[[b for _, b in pairs]].assign(car_id=x["car_id"].iloc[[a for a, _ in pairs]].to_numpy()))
        present = set(ky)
        gone = sum(1 for k in kx if k not in present)
        removed += gone
        ambiguous += len(x) - len(pairs) - gone
    return pd.concat(out, ignore_index=True), removed, ambiguous


def keepers(refresh):
    if KEEPERS.exists() and not refresh:
        return pd.read_parquet(KEEPERS), json.loads(MATCH.read_text())
    cars = pd.read_parquet(CARS)
    now = pull()
    matched, removed, ambiguous = align(cars, now)
    same = matched.merge(cars, on="car_id", suffixes=("", "_x1"))
    agree = all((same[c].astype("string").fillna("") == same[f"{c}_x1"].astype("string").fillna("")).all()
                for c in FIELDS)
    k = matched[["car_id", "first_reg_date", "keeper_date", "export"]].sort_values("car_id", ignore_index=True)
    k["read_on"] = pd.Timestamp.today().normalize()
    KEEPERS.parent.mkdir(parents=True, exist_ok=True)
    k.to_parquet(KEEPERS, index=False)
    stats = {"x1 cars": len(cars), "register now": len(now), "matched": len(k),
             "fields no longer in the register": removed,
             "left out: identical to a car that left or arrived that day": ambiguous,
             "register rows not matched": len(now) - len(k),
             "all seven fields agree on every matched car": bool(agree)}
    MATCH.write_text(json.dumps(stats, indent=1))
    return k, stats


def value_at(con, when):
    """The part-3 mark on any date: the curve at the car's age then, times the level of the last published month."""
    t, ref = curve()
    idx = level()
    b = con.execute("SELECT p.car_id, p.amount_eur AS catalogue, r.valid_date AS registration_date FROM events p "
                    "JOIN events r ON r.car_id = p.car_id AND r.event_type = 'registration' "
                    "WHERE p.event_type = 'list_price' AND p.source = 'oem_prices'").df().set_index("car_id")
    w = when.join(b, on="car_id")
    age = (pd.to_datetime(w["date"]) - pd.to_datetime(w["registration_date"])).dt.days / 365.25
    month = pd.to_datetime(w["date"]).dt.strftime("%Y-%m").clip(upper=idx.index.max())
    w["level_month"] = month
    w["basis"] = (w["catalogue"] * share(age, t) * (idx.reindex(month).to_numpy() / idx[ref])).round(2)
    w["s_low"] = -np.log(share(age, t, "p10")) / Z90
    w["s_high"] = np.log(share(age, t, "p90")) / Z90
    w["age"] = age.round(3)
    return w


def life_events(con, k):
    k = k.copy()
    days = (k["keeper_date"] - k["first_reg_date"]).dt.days
    k["days_after_registration"] = days
    k["ref"] = k["car_id"].astype(str)
    back = k[days >= HANDOVER_DAYS]
    hand = k[(days > 0) & (days < HANDOVER_DAYS)]
    out = [events(back, "came_to_market", "rdw_register", "ref", "keeper_date", recorded="read_on",
                  attrs=["days_after_registration", "export"]),
           events(hand, "keeper_handover", "rdw_register", "ref", "keeper_date", recorded="read_on",
                  attrs=["days_after_registration", "export"])]
    w = value_at(con, back.rename(columns={"keeper_date": "date"})[["car_id", "date", "read_on", "ref"]]
                 .sort_values("car_id", ignore_index=True))
    w["z"] = [round(float(np.random.default_rng([SEED, int(c)]).standard_normal()), 4) for c in w["car_id"]]
    w["price"] = (w["basis"] * np.exp(w["z"] * np.where(w["z"] < 0, w["s_low"], w["s_high"]))).round(2)
    out.append(events(w, "resale", "x4_synthetic_resale", "ref", "date", recorded="read_on", amount="price",
                      attrs=["basis", "z", "age", "level_month"], kind="synthetic"))
    return pd.concat(out, ignore_index=True), w


def check(con, k, w, last, before, counts, stats):
    results = [("the re-read matches X1's cars on all seven fields, and no plate is stored",
                stats["all seven fields agree on every matched car"] and "plate" not in k.columns)]
    ev = con.execute("SELECT event_type, count(*) n, count(DISTINCT car_id) cars FROM events WHERE source IN "
                     "('rdw_register', 'x4_synthetic_resale') GROUP BY 1").df().set_index("event_type")
    days = (k["keeper_date"] - k["first_reg_date"]).dt.days
    results.append(("one event per car and kind, each kind exactly where the dates put it",
                    (ev["n"] == ev["cars"]).all()
                    and ev.loc["came_to_market", "n"] == (days >= HANDOVER_DAYS).sum()
                    and ev.loc["keeper_handover", "n"] == ((days > 0) & (days < HANDOVER_DAYS)).sum()
                    and ev.loc["resale", "n"] == ev.loc["came_to_market", "n"]))
    has = k["keeper_date"].notna()
    results.append(("no keeper date before first registration or after the read",
                    bool((days[has] >= 0).all() and (k.loc[has, "keeper_date"] <= k.loc[has, "read_on"]).all())))

    # five resale bases recomputed by a plain loop from the source files
    t, ref = curve()
    idx = level()
    prices = pd.read_parquet(ROOT / "data" / "synthetic" / "x1_oem_prices.parquet").set_index("car_id")["list_price_eur"]
    regd = pd.read_parquet(ROOT / "data" / "synthetic" / "x1_master.parquet").set_index("car_id")["registration_date"]
    worst = 0.0
    for r in w.iloc[np.linspace(0, len(w) - 1, 5).astype(int)].itertuples():
        age = (pd.Timestamp(r.date) - pd.Timestamp(regd[r.car_id])).days / 365.25
        m = min(pd.Timestamp(r.date).strftime("%Y-%m"), idx.index.max())
        worst = max(worst, abs(prices[r.car_id] * float(share(age, t)) * idx[m] / idx[ref] - r.basis))
    results.append((f"five resale bases recomputed from the source files (worst gap €{worst:.2f})", worst < 0.01))
    below10 = (w["price"] < w["basis"] * share(w["age"], t, "p10")).mean()
    above90 = (w["price"] > w["basis"] * share(w["age"], t, "p90")).mean()
    results.append((f"the synthetic draws follow the band: {below10:.1%} below its 10th percentile, "
                    f"{above90:.1%} above its 90th", abs(below10 - 0.1) < 0.01 and abs(above90 - 0.1) < 0.01))

    results.append(("facts, decisions and estimates before this part unchanged",
                    content_hash(con, upto=last) == before
                    and [con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("marks", "readiness")]
                    == counts))
    results.append(("running again adds nothing", append(con, life_events(con, k)[0], "rdw_read") == 0))
    car = int(w["car_id"].iloc[0])
    day = pd.Timestamp(k["read_on"].iloc[0])
    seen = ["came_to_market" in set(timeline(con, car, d)["event_type"]) for d in (day - pd.Timedelta(days=1), day)]
    results.append(("a return is unknown until the day the register was read", seen == [False, True]))
    return results


def write_report(con, k, w, stats, results):
    days = (k["keeper_date"] - k["first_reg_date"]).dt.days
    age_m = (days.dropna() // (365.25 / 12)).astype(int)
    back = age_m[days.dropna() >= HANDOVER_DAYS]
    lines = ["# X4 part 5: life after sale", "",
             "Generated by `ledger/returns.py`. **The dates are real** (RDW's current-keeper date of the same real cars); "
             "**the prices are synthetic**. Only the current keeper is visible, so every count is a lower bound.", "",
             f"Register read on {k['read_on'].iloc[0]:%Y-%m-%d}."]
    lines += ["", "## Matching the re-read to X1's cars", ""] + [f"- {n}: {v:,}" if not isinstance(v, bool)
                                                               else f"- {n}: {'yes' if v else 'NO'}"
                                                               for n, v in stats.items()]
    lines += ["", "## When the cars last changed keeper", "",
              f"- Cars matched: {len(k):,}. No current keeper in the register: {k['keeper_date'].isna().sum():,} (marked "
              f"for export: {(k['keeper_date'].isna() & (k['export'] == 'Ja')).sum():,}). No change since first "
              f"registration: {(days == 0).sum():,}. Handover within "
              f"3 months: {((days > 0) & (days < HANDOVER_DAYS)).sum():,}. **Came back to market (latest change after "
              f"3 months): {len(back):,}.** Marked for export: {(k['export'] == 'Ja').sum():,}.", "",
              "The latest change, by the car's age in months at that change (cars that came back):", "",
              "| age (months) | cars |", "|---:|---:|"]
    counts = back.value_counts().sort_index()
    lines += [f"| {a} | {n:,} |" for a, n in counts.items() if a >= 36 and a <= 66]
    lines += ["", "Ages 36-66 shown; the waves X3 found at 48 and 60 months, if present, show here in the group's own "
                  "cars. A later change hides an earlier one, so early ages are undercounted most; and only cars "
                  "registered early enough reach the oldest ages by the read date, so counts past about 57 months rest "
                  "on fewer cars.", ""]

    ev = con.execute("""
        WITH r AS (SELECT car_id, valid_date FROM events WHERE event_type = 'came_to_market')
        SELECT strftime(s.month_end, '%Y-%m') AS month, count(*) AS cars, sum(s.p12) AS expected,
               count(r.car_id) FILTER (WHERE r.valid_date > s.month_end
                                        AND r.valid_date <= s.month_end + INTERVAL 12 MONTH) AS observed
        FROM readiness s LEFT JOIN r ON r.car_id = s.car_id
        WHERE s.model = ? AND month(s.month_end) = 12 AND s.month_end + INTERVAL 12 MONTH <= ?
        GROUP BY 1 ORDER BY 1""", [READY, k["read_on"].iloc[0]]).df()
    lines += ["## The readiness engine against the register (a demo, not evidence)", "",
              "Each year end, the book's expected count of cars coming to market in the next 12 months (the sum of "
              "part 4's 12-month chances) against the cars whose latest keeper change falls in that window. The "
              "observed side is a lower bound, and the engine's layer 1 was built on the same register.", "",
              "| year end | cars scored | expected within 12 months | observed (lower bound) |", "|---|---:|---:|---:|"]
    lines += [f"| {r.month} | {r.cars:,} | {r.expected:,.0f} | {r.observed:,} |" for r in ev.itertuples()]
    lines += ["", "## Synthetic resale prices", "",
              f"- {len(w):,} prices, one per car that came back: the mark at that date times a draw from the adverts' "
              f"spread. Median price ÷ mark: {(w['price'] / w['basis']).median():.3f}. After the index's last month the "
              "level is held there.", "", "## Checks", ""]
    lines += [f"- {'pass' if ok else 'FAIL'}: {name}" for name, ok in results]
    REPORT.write_text("\n".join(lines) + "\n")


def main():
    k, stats = keepers("--pull" in sys.argv)
    con = open_store(STORE)
    last = con.execute("SELECT max(seq) FROM events").fetchone()[0]
    before = content_hash(con, upto=last)
    counts = [con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("marks", "readiness")]
    new, w = life_events(con, k)
    n = append(con, new, "rdw_read")
    results = check(con, k, w, last, before, counts, stats)
    write_report(con, k, w, stats, results)
    print(f"{n:,} events appended; " + ", ".join("pass" if ok else "FAIL" for _, ok in results))
    con.close()
    if not all(ok for _, ok in results):
        sys.exit("a check failed; see " + str(REPORT))


if __name__ == "__main__":
    main()
