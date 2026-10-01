"""X4 part 4: readiness scores and the upgrade queue.

Each month end, every car a year old or more gets the readiness engine's chance of coming to market within 3 and within
12 months, with its 80% band, and the retail customers are ranked into a queue. That is leak 2 as the case states it:
customers ready to upgrade but not contacted in time.

**The engine is the project's own** (`readiness_engine.py`): the group's brands (`brands="stellantis"`, the Dutch
register's keeper-change rates for the group's cars), the `to_market` event, and layer 3 (the lease-end waves at 48
and 60 months) on, as by default. X1's world holds no odometer, so layer 2 is off: the engine's answer for a car whose
reading is unknown.

**What the score is not.** The engine predicts that a car comes to market, not that its customer is ready to replace;
the gap between the two is an assumption (the engine's own docstring). And with nothing but age to go on, every car of
one age scores the same, so the queue is an age schedule with the lease-end waves in it. That is the measured result,
not a shortcut: nothing public predicts coming to market beyond age (`notes/STATE.md`, Decided). The group's own
signals (contract end dates, service visits, connected-car mileage) would separate two cars of one age; the ledger is
where they would land.

**Scored from age one.** The engine's first measured age is one year; a younger car would only repeat it, and the
group's first-year rate carries dealer self-registrations passing to customers (`analysis/self_registration_report.md`).
Age is counted in whole months at the month end.

**The queue** holds the retail customers (a private or conquest buyer on the registration record) whose car is past
the equity window. Fleet cars come back through lease ends, which is remarketing (leak 3), not an upgrade call. A
customer is flagged when their 3-month chance is in the top tenth of the queue that month (`TOP_SHARE`, an ASSUMPTION
standing for contact capacity; every car tied at the cut is flagged, so the share can run above it). Ranked by
readiness, not uplift: the uplift model returned a negative, and a randomised pilot decides (STATE, Decided).

**The equity window (X16, 27 September).** A customer enters the queue at the month the car's equity first covers the
next deposit, read from the register (`window_nl_measured_m`: the Dutch curve with its first year measured, the Leak 2
sheet's contract). Leak 2 is customers ready to upgrade, and a financed customer can't upgrade before then; before it,
the group's keeper changes are mostly not upgrades (the young-car section of the report), and the age-only queue
flagged returning customers below chance while it sat on young cars (`x4_pnl_report.md`). One rule for every retail
customer; the group's contract data would set each car's own window. The scores are the same; only the queue changed.
The age-only queue, from age one, stays in the store as model `x4_ready_v1` beside this one (`x4_ready_v2`), so the
two can be compared: an append-only store keeps the rule it replaced.

**Dates.** A score is valid at the month end and recorded then, since it needs only the car's age. It is back-scored
with today's engine, so earlier months carry hindsight about the engine, never about the car.

Output: rows in the store's typed `readiness` table (model `x4_ready_v2`; the `ledger` view shows them as `readiness`
estimate events), and ledger/x4_readiness_report.md. Readers of the table filter on `MODEL`.
Usage: .venv/bin/python ledger/readiness.py   (after parts 1-3; running it again adds nothing)
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from readiness_engine import ReadinessEngine  # noqa: E402
from store import STORE, append_estimates, content_hash, open_store, read, timeline  # noqa: E402

REPORT = HERE / "x4_readiness_report.md"
MODEL = "x4_ready_v2"     # the queue from the equity window
AGE_ONLY = "x4_ready_v1"  # the same scores, queued from age one: the rule the window replaced
BRANDS = "stellantis"     # the engine's group-brand rates
FIRST_AGE = 12            # months: the engine's first measured age
TOP_SHARE = 0.10          # ASSUMPTION: contact capacity, the top tenth of the queue each month
MONTH_DAYS = 365.25 / 12
WAVES = (48, 60)          # the lease-end waves X3 found in the Dutch register (analysis/lease_end_report.md)
WINDOW = int(float(pd.read_csv(ROOT / "assumptions.csv").set_index("id").loc["window_nl_measured_m", "value"]))


def age_months(registration, end):
    return ((pd.Timestamp(end) - pd.to_datetime(registration)).dt.days // MONTH_DAYS).astype(int)


def scores(engine, oldest):
    """The engine's answer at every age in whole months: it depends on nothing else here."""
    rows = []
    for m in range(FIRST_AGE, oldest + 1):
        r3, r12 = (engine.readiness(m / 12, None, h) for h in (3, 12))
        rows.append({"age_months": m, "p3": r3["probability"], "p3_low": r3["low"], "p3_high": r3["high"],
                     "p12": r12["probability"], "p12_low": r12["low"], "p12_high": r12["high"]})
    return pd.DataFrame(rows).set_index("age_months")


def customers(con):
    return con.execute("SELECT car_id, valid_date AS registration_date, "
                       "json_extract_string(attrs, '$.buyer') IN ('private', 'conquest') AS retail "
                       "FROM events WHERE event_type = 'registration' ORDER BY car_id").df()


def flag(month, window=WINDOW):
    """Flag every queued car (retail, at least `window` months old) scoring at least the car at the TOP_SHARE cut,
    ties included. The age-only queue is the same rule from age one (window 0)."""
    queued = month["retail"] & (month["age_months"] >= window)
    q = month.loc[queued, "p3"].sort_values(ascending=False).to_numpy()
    cut = q[math.ceil(TOP_SHARE * len(q)) - 1] if len(q) else np.inf
    return queued & (month["p3"] >= cut)


def month_rows(cars, ends, table, model=MODEL, window=WINDOW):
    out = []
    for end in ends:
        c = cars[pd.to_datetime(cars["registration_date"]) <= end].copy()
        c["age_months"] = age_months(c["registration_date"], end)
        c = c[c["age_months"] >= FIRST_AGE].join(table, on="age_months")
        c["flag"] = flag(c, window)
        c["month_end"] = end
        c["recorded_date"] = end
        out.append(c)
    return pd.concat(out, ignore_index=True).assign(model=model)


def month_ends(con):
    """The book's months: those the marks cover (part 3)."""
    first, last = con.execute("SELECT min(month_end), max(month_end) FROM marks").fetchone()
    return pd.date_range(first, last, freq="ME")


def check(con, engine, last, before, n_marks, age_only):
    results = []
    ends = month_ends(con)
    master = read("master")
    reg = pd.to_datetime(master["registration_date"])
    expect = sum(int((((e - reg).dt.days // MONTH_DAYS) >= FIRST_AGE).sum()) for e in ends)
    got = con.execute("SELECT count(*) FROM readiness WHERE model = ?", [MODEL]).fetchone()[0]
    results.append(("one score per car per month from age one to the book's last month", got == expect))
    dup = con.execute("SELECT count(*) - count(DISTINCT (model, car_id, month_end)) FROM readiness").fetchone()[0]
    results.append(("no car has two scores for one month", dup == 0))

    # five cars, every month, asked of the engine directly from the source file's registration date
    ids = master["car_id"].sort_values().iloc[np.linspace(0, len(master) - 1, 5).astype(int)].tolist()
    regd = master.set_index("car_id")["registration_date"]
    stored = con.execute("SELECT * FROM readiness WHERE model = ? AND car_id IN "
                         f"({','.join(map(str, ids))})", [MODEL]).df()
    worst = 0.0
    for r in stored.itertuples():
        m = int((pd.Timestamp(r.month_end) - pd.Timestamp(regd[r.car_id])).days // MONTH_DAYS)
        a3, a12 = (engine.readiness(m / 12, None, h) for h in (3, 12))
        want = [a3["probability"], a3["low"], a3["high"], a12["probability"], a12["low"], a12["high"]]
        have = [r.p3, r.p3_low, r.p3_high, r.p12, r.p12_low, r.p12_high]
        worst = max(worst, max(abs(w - h) for w, h in zip(want, have)), abs(m - r.age_months))
    results.append((f"five cars' {len(stored)} scores asked of the engine directly (worst gap {worst:.1e})",
                    worst < 1e-12 and len(stored) > 0))

    rule = con.execute("""
        SELECT count(*) FILTER (WHERE bad) FROM (
            SELECT month_end,
                   bool_or(flag AND NOT (retail AND age_months >= $w)) OR
                   min(p3) FILTER (WHERE flag) <= max(p3) FILTER (WHERE retail AND age_months >= $w AND NOT flag) OR
                   avg(flag::INT) FILTER (WHERE retail AND age_months >= $w) < $s AS bad
            FROM readiness WHERE model = $m GROUP BY month_end)""", {"w": WINDOW, "s": TOP_SHARE, "m": MODEL}).fetchone()[0]
    results.append((f"every month: only retail cars past the equity window (month {WINDOW}) flagged, at least the "
                    "top tenth of that queue, every flagged car above every unflagged one", rule == 0))
    same = con.execute("""
        SELECT count(*), count(*) FILTER (WHERE a.age_months <> b.age_months OR a.retail <> b.retail OR a.p3 <> b.p3
                                           OR a.p3_low <> b.p3_low OR a.p3_high <> b.p3_high OR a.p12 <> b.p12
                                           OR a.p12_low <> b.p12_low OR a.p12_high <> b.p12_high)
        FROM readiness a JOIN readiness b USING (car_id, month_end) WHERE a.model = ? AND b.model = ?""",
                       [MODEL, AGE_ONLY]).fetchone()
    results.append(("the window queue and the age-only queue hold the same scores, row for row",
                    same[0] == got and same[1] == 0))
    results.append(("the age-only queue's rows are untouched",
                    con.execute("SELECT count(*), sum(flag::INT) FROM readiness WHERE model = ?",
                                [AGE_ONLY]).fetchone() == age_only))
    retail_now = int(master["buyer"].isin(["private", "conquest"])[
        ((ends[-1] - reg).dt.days // MONTH_DAYS) >= FIRST_AGE].sum())
    got_now = con.execute("SELECT count(*) FROM readiness WHERE model = ? AND retail AND month_end = ?",
                          [MODEL, ends[-1]]).fetchone()[0]
    results.append(("the queue's population is the registration record's private and conquest buyers",
                    got_now == retail_now))

    results.append(("facts and decisions unchanged", content_hash(con, upto=last) == before))
    results.append(("marks unchanged", con.execute("SELECT count(*) FROM marks").fetchone()[0] == n_marks))
    cars = customers(con)
    table = scores(engine, int(age_months(cars["registration_date"], ends[-1]).max()))
    results.append(("running the last month again adds nothing",
                    append_estimates(con, "readiness", month_rows(cars, ends[-1:], table)) == 0))
    car = int(stored["car_id"].iloc[0])
    day = ends[-1]
    seen = ["readiness" in set(timeline(con, car, d).query("valid_date == @day")["event_type"])
            for d in (day - pd.Timedelta(days=1), day)]
    results.append(("the last month's score is unknown the day before its month end", seen == [False, True]))
    return results


def write_report(con, table, results):
    last = con.execute("SELECT max(month_end) FROM readiness WHERE model = ?", [MODEL]).fetchone()[0]
    q = con.execute("""
        SELECT r.car_id, r.age_months, r.p3, r.p3_low, r.p3_high, r.p12, r.flag, m.mark_eur, m.low_eur, m.high_eur,
               json_extract_string(g.attrs, '$.make') AS make, json_extract_string(g.attrs, '$.model') AS model,
               EXISTS (SELECT 1 FROM events f WHERE f.car_id = r.car_id AND f.event_type = 'finance_start'
                       AND json_extract_string(f.attrs, '$.contract_type') = 'private finance') AS financed
        FROM readiness r
        JOIN marks m ON m.car_id = r.car_id AND m.month_end = r.month_end
        JOIN events g ON g.car_id = r.car_id AND g.event_type = 'registration'
        WHERE r.model = ? AND r.month_end = ? AND r.retail ORDER BY r.p3 DESC, m.mark_eur DESC, r.car_id""",
                    [MODEL, last]).df()
    book = con.execute("SELECT retail, count(*) n, sum(p3) e3, sum(p12) e12 FROM readiness WHERE model = ? AND "
                       "month_end = ? GROUP BY retail ORDER BY retail DESC", [MODEL, last]).df()
    flagged = q[q["flag"]]
    shown = sorted(set(range(FIRST_AGE, table.index.max() + 1, 6)) | {w - k for w in WAVES for k in (0, 1, 2)
                                                                        if w - k <= table.index.max()})
    lines = ["# X4 part 4: readiness scores and the upgrade queue", "",
             "Generated by `ledger/readiness.py`. The cars are real (RDW); the world around them is synthetic (X1); the "
             "engine is measured (`readiness_engine.py`, group brands, layers 1 and 3). The queue is the prototype's "
             "output on that book. A score is the chance a car comes to market, not that its customer is ready to "
             "replace.", "",
             "## The engine by age (group brands, no odometer)", "",
             "| age (months) | within 3 months | within 12 months |", "|---:|---:|---:|"]
    lines += [f"| {a} | {table.loc[a, 'p3']:.1%} | {table.loc[a, 'p12']:.1%} |" for a in shown]
    lines += ["", f"Every car of one age scores the same: with age the only input, the queue is an age schedule, "
                  f"highest just before the lease-end waves at {WAVES[0]} and {WAVES[1]} months.", "",
              f"## The queue on {last:%Y-%m-%d}", "",
              f"- Retail customers scored: {len(q):,}; past the equity window (month {WINDOW}): "
              f"{int((q['age_months'] >= WINDOW).sum()):,}. Flagged (top tenth by 3-month chance, ties included): "
              f"{len(flagged):,} ({len(flagged) / len(q):.1%}).",
              f"- Flagged by age in months: " + ", ".join(f"{a}: {n:,}" for a, n in
                                                         flagged["age_months"].value_counts().sort_index().items()) + ".",
              f"- Flagged customers the captive finances (SYNTHETIC share, set by X1's `finance_private_share`): "
              f"{flagged['financed'].mean():.1%}.", "",
              "| book | cars | expected to come to market within 3 months | within 12 months |", "|---|---:|---:|---:|"]
    lines += [f"| {'retail' if r.retail else 'fleet'} | {r.n:,} | {r.e3:,.0f} | {r.e12:,.0f} |" for r in book.itertuples()]
    lines += ["", "Fleet cars really come back at lease end; the group's contract dates would replace this curve for "
                  "them (X3).", "",
              "### The top of the queue (ranked by 3-month chance, then by the car's mark)", "",
              "| car | make | model | age | 3 months (80% band) | mark (80% band) | financed |",
              "|---:|---|---|---:|---|---|---|"]
    for r in q.head(10).itertuples():
        lines.append(f"| {r.car_id} | {r.make} | {r.model} | {r.age_months} | {r.p3:.1%} ({r.p3_low:.1%}–"
                     f"{r.p3_high:.1%}) | €{r.mark_eur:,.0f} (€{r.low_eur:,.0f}–€{r.high_eur:,.0f}) | "
                     f"{'yes' if r.financed else 'no'} |")
    lines += ["", "The band on a score is sampling error in the engine's measurements only (its docstring): not how "
                  "sure we are about this customer.", "",
              "## Young cars: read the early months with care", "",
              "The engine's layer 1 for the group's brands runs well above the whole market's at the youngest ages "
              "(`analysis/readiness_base_hazard.csv`), which fits dealer self-registrations passing to customers "
              "(`analysis/self_registration_report.md`), not customers replacing. So a young car's score overstates "
              f"customer readiness. The queue therefore starts at the equity window, month {WINDOW} "
              "(`window_nl_measured_m`); the age-only queue, from age one, stays in the store beside it. The latest "
              "queue holds only older cars, so the two agree on it.", "",
              "| age (years) | keeper changes in 12 months, group brands | all brands |", "|---:|---:|---:|"]
    base = pd.read_csv(ROOT / "analysis" / "readiness_base_hazard.csv").set_index("age_years")
    lines += [f"| {a} | {base.loc[a, 'rate_st']:.1%} | {base.loc[a, 'rate']:.1%} |" for a in (1, 2, 3, 4)]
    ages = con.execute("""SELECT month_end, model, count(*) n, min(age_months) lo, max(age_months) hi FROM readiness
                          WHERE flag AND month(month_end) = 12 GROUP BY 1, 2""").df().set_index(["month_end", "model"])
    lines += ["", "| year end | flagged, from the window | youngest (months) | oldest | flagged, age-only queue | "
                  "youngest (months) | oldest |", "|---|---:|---:|---:|---:|---:|---:|"]
    for end in sorted(ages.index.get_level_values(0).unique()):
        cells = [f"{end:%Y-%m}"]
        for m in (MODEL, AGE_ONLY):
            r = ages.loc[(end, m)] if (end, m) in ages.index else None
            cells += [f"{int(r.n):,}", str(int(r.lo)), str(int(r.hi))] if r is not None else ["0", "–", "–"]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "## Checks", ""]
    lines += [f"- {'pass' if ok else 'FAIL'}: {name}" for name, ok in results]
    REPORT.write_text("\n".join(lines) + "\n")


def main():
    con = open_store(STORE)
    last = con.execute("SELECT max(seq) FROM events").fetchone()[0]
    before = content_hash(con, upto=last)
    n_marks = con.execute("SELECT count(*) FROM marks").fetchone()[0]
    engine = ReadinessEngine(brands=BRANDS)
    cars = customers(con)
    ends = month_ends(con)
    table = scores(engine, int(age_months(cars["registration_date"], ends[-1]).max()))
    if not con.execute("SELECT count(*) FROM readiness WHERE model = ?", [AGE_ONLY]).fetchone()[0]:
        # a store rebuilt from scratch: write the age-only queue first, as the rule it was (retail from age one)
        for year in sorted(set(ends.year)):
            append_estimates(con, "readiness", month_rows(cars, ends[ends.year == year], table, AGE_ONLY, 0))
    age_only = con.execute("SELECT count(*), sum(flag::INT) FROM readiness WHERE model = ?", [AGE_ONLY]).fetchone()
    n = 0
    for year in sorted(set(ends.year)):
        n += append_estimates(con, "readiness", month_rows(cars, ends[ends.year == year], table))
    results = check(con, engine, last, before, n_marks, age_only)
    write_report(con, table, results)
    print(f"{n:,} scores appended; " + ", ".join("pass" if ok else "FAIL" for _, ok in results))
    con.close()
    if not all(ok for _, ok in results):
        sys.exit("a check failed; see " + str(REPORT))


if __name__ == "__main__":
    main()
