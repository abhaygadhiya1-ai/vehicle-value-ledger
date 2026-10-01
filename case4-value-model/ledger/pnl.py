"""X4 part 6: a lifetime P&L per car, across the three businesses, from the ledger.

One row per car, recomputed from the ledger on every run and never written back into it: a derived view, so a late
event changes it by being in the ledger, never by an edit. Only lines with a source are filled. A line the group holds
and this prototype does not is named and left empty ("not held"), never zero.

  New cars
    catalogue_eur          fact: the OEM price list, VAT and BPM included; a reference, not revenue
    incentives_paid_eur    SYNTHETIC (X1's claims): every claim linked to the car, credit notes netted. X1's world paid
                           them all before the detector ran (part 2)
    incentives_held_eur    SYNTHETIC: of which on hold (part 2), money a live ledger would not have paid
    incentives_review_eur  SYNTHETIC: of which held for a person to decide
    new_car_margin         not held: the group's cost and transfer price
  Finance (the captive)
    contract, start        SYNTHETIC: X1's contract type and start date, linked by part 9's resolver
    finance_income         not held: rates, amounts and terms
    residual_set_eur       fleet leases that came back: the mark the car would have at its return age, at the market
                           level of the month the contract started. The term is taken as the car's real time to its
                           return (part 5); a live ledger reads the contract's own term, which is not held here
  Used cars
    value_at_return_eur    the mark on the return date (part 5's basis): the same curve, that month's level
    resale_eur             SYNTHETIC: part 5's price
    level_part_eur         value at return − residual set: the market level's move between contract start and return,
                           from the real index on real dates, applied to a modelled car
    car_part_eur           resale − value at return: this car against the market (synthetic here)
    remarketing_cost       not held
  Upgrades (leak 2)
    came_back              real: the register's latest keeper change after the first 3 months (part 5)
    flagged_before         retail cars that came back while the queue ran: flagged (part 4's queue, from the equity
                           window) at a month end in the 3 months before the return
    flagged_before_age_only  the same for the age-only queue it replaced (from age one), kept for the comparison
  Today
    mark_now_eur, band     the last month's mark (part 3)

The split of the residual result is the programme's thesis made per car: a residual value is two forecasts, the curve
and the level, and the level is the one no car-level model can forecast. Everything is in the synthetic world bar the
cars, their prices, their dates and the index; the totals describe the prototype, not the group.

Output: data/ledger/car_pnl.parquet (for X16) and ledger/x4_pnl_report.md. Nothing is written to the store.
Usage: .venv/bin/python ledger/pnl.py   (after parts 1-5)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "leak1"))
from layer1_keys import load as load_claims  # noqa: E402
from layer3_rules import REVIEW  # noqa: E402
from readiness import AGE_ONLY, MODEL as READY, WINDOW  # noqa: E402
from remark import curve, level, share  # noqa: E402
from returns import KEEPERS  # noqa: E402
from store import STORE, open_store, read  # noqa: E402

OUT = ROOT / "data" / "ledger" / "car_pnl.parquet"
REPORT = HERE / "x4_pnl_report.md"
NOT_HELD = ["new_car_margin", "finance_income", "remarketing_cost", "contract_term"]
FLAG_WINDOW = 3           # months: the queue's horizon (part 4's 3-month chance)
SHOWCASE = 51500          # part 1's showcase car


def pnl(con):
    q = lambda sql: con.execute(sql).df()  # noqa: E731
    cars = q("SELECT r.car_id, json_extract_string(r.attrs, '$.buyer') AS buyer, "
             "json_extract_string(r.attrs, '$.make') AS make, json_extract_string(r.attrs, '$.model') AS model, "
             "r.valid_date AS registration_date, p.amount_eur AS catalogue_eur FROM events r "
             "JOIN events p ON p.car_id = r.car_id AND p.event_type = 'list_price' "
             "WHERE r.event_type = 'registration' ORDER BY r.car_id").set_index("car_id")
    claims = q("SELECT c.car_id, c.amount_eur, json_extract_string(d.attrs, '$.decision') AS decision FROM events c "
               "JOIN events d ON d.event_type = 'claim_decision' AND json_extract_string(d.attrs, '$.claim_event') = "
               "c.event_id WHERE c.event_type = 'claim' AND c.car_id IS NOT NULL")
    by = claims.pivot_table(index="car_id", columns="decision", values="amount_eur", aggfunc="sum", fill_value=0.0)
    cars["incentives_paid_eur"] = by.sum(axis=1).reindex(cars.index).fillna(0.0)
    cars["incentives_held_eur"] = by.get("hold", pd.Series(dtype=float)).reindex(cars.index).fillna(0.0)
    cars["incentives_review_eur"] = by.get("review", pd.Series(dtype=float)).reindex(cars.index).fillna(0.0)

    fin = q("SELECT car_id, valid_date AS contract_start, json_extract_string(attrs, '$.contract_type') AS contract "
            "FROM events WHERE event_type = 'finance_start' AND car_id IS NOT NULL")
    assert fin["car_id"].is_unique, "a car with two contracts: choose one before summing"
    cars = cars.join(fin.set_index("car_id"))
    back = q("SELECT b.car_id, b.valid_date AS came_back, s.amount_eur AS resale_eur, "
             "CAST(json_extract_string(s.attrs, '$.basis') AS DOUBLE) AS value_at_return_eur, "
             "json_extract_string(s.attrs, '$.level_month') AS level_month FROM events b "
             "JOIN events s ON s.car_id = b.car_id AND s.event_type = 'resale' "
             "WHERE b.event_type = 'came_to_market'").set_index("car_id")
    cars = cars.join(back)

    idx = level()
    _, ref = curve()
    fleet_back = cars["contract"].eq("fleet lease") & cars["came_back"].notna() \
        & (pd.to_datetime(cars["came_back"]) > pd.to_datetime(cars["contract_start"]))
    start_month = pd.to_datetime(cars["contract_start"]).dt.strftime("%Y-%m")
    lv_start = idx.reindex(start_month).to_numpy() / idx[ref]
    lv_back = idx.reindex(cars["level_month"]).to_numpy() / idx[ref]
    cars["residual_set_eur"] = np.where(fleet_back, cars["value_at_return_eur"] * lv_start / lv_back, np.nan).round(2)
    cars["level_part_eur"] = (cars["value_at_return_eur"] - cars["residual_set_eur"]).where(fleet_back).round(2)
    cars["car_part_eur"] = (cars["resale_eur"] - cars["value_at_return_eur"]).where(fleet_back).round(2)
    cars["months_to_return"] = ((pd.to_datetime(cars["came_back"]) - pd.to_datetime(cars["contract_start"])).dt.days
                                / (365.25 / 12)).where(fleet_back).round(1)

    first, last = con.execute("SELECT min(month_end), max(month_end) FROM readiness WHERE model = ?", [READY]).fetchone()
    first, last = pd.Timestamp(first), pd.Timestamp(last)
    cars["retail"] = cars["buyer"].isin(["private", "conquest"])
    back_at = pd.to_datetime(cars["came_back"])
    judged = cars["retail"] & back_at.notna() & (back_at <= last) \
        & (back_at > first + pd.DateOffset(months=FLAG_WINDOW))
    for col, model in (("flagged_before", READY), ("flagged_before_age_only", AGE_ONLY)):
        flags = con.execute("SELECT car_id, month_end FROM readiness WHERE flag AND model = ?", [model]).df()
        f = flags.merge(back_at[judged].rename("came_back").reset_index(), on="car_id")
        f = f[(pd.to_datetime(f["month_end"]) < f["came_back"])
              & (pd.to_datetime(f["month_end"]) >= f["came_back"] - pd.DateOffset(months=FLAG_WINDOW))]
        cars[col] = pd.Series(np.where(judged, cars.index.isin(f["car_id"]), None), index=cars.index, dtype="object")

    now = q(f"SELECT car_id, mark_eur AS mark_now_eur, low_eur AS mark_now_low_eur, high_eur AS mark_now_high_eur "
            f"FROM marks WHERE month_end = (SELECT max(month_end) FROM marks)").set_index("car_id")
    cars = cars.join(now)
    for c in NOT_HELD:
        cars[c] = None
    return cars.reset_index()


def check(con, p, counts):
    results = [("one row per registered car",
                len(p) == p["car_id"].nunique() == con.execute(
                    "SELECT count(*) FROM events WHERE event_type = 'registration'").fetchone()[0])]

    # incentives against the claim files themselves, split by layer 3's reasons
    claims, _ = load_claims()
    flags = read("flags_layer3").set_index("claim_id")
    claims["car_id"] = claims["claim_id"].map(flags["car_id"])
    claims["reason"] = claims["claim_id"].map(flags["reason"])
    linked = claims[claims["car_id"].notna()]
    hold = linked["reason"].notna() & ~linked["reason"].isin(REVIEW)
    want = [linked["amount_net"].sum(), linked.loc[hold, "amount_net"].sum(),
            linked.loc[linked["reason"].isin(REVIEW), "amount_net"].sum()]
    got = [p["incentives_paid_eur"].sum(), p["incentives_held_eur"].sum(), p["incentives_review_eur"].sum()]
    results.append(("incentives paid, held and in review reconcile to the claim files (linked claims)",
                    all(abs(a - b) < 0.01 for a, b in zip(got, want))))
    total = con.execute("SELECT sum(amount_eur) FROM events WHERE event_type = 'claim'").fetchone()[0]
    unlinked = con.execute("SELECT sum(amount_eur) FROM events WHERE event_type = 'claim' AND car_id IS NULL"
                           ).fetchone()[0]
    results.append(("cars' incentives plus unlinked claims = every claim in the ledger",
                    abs(p["incentives_paid_eur"].sum() + unlinked - total) < 0.01))

    fb = p["residual_set_eur"].notna()
    results.append(("residual set + level part = value at return, and value at return + car part = resale",
                    np.allclose(p.loc[fb, "residual_set_eur"] + p.loc[fb, "level_part_eur"],
                                p.loc[fb, "value_at_return_eur"], atol=0.02)
                    and np.allclose(p.loc[fb, "value_at_return_eur"] + p.loc[fb, "car_part_eur"],
                                    p.loc[fb, "resale_eur"], atol=0.02)))
    results.append(("residual lines only on fleet leases that came back after their contract started",
                    bool((p.loc[fb, "contract"] == "fleet lease").all()
                         and (pd.to_datetime(p.loc[fb, "came_back"]) > pd.to_datetime(p.loc[fb, "contract_start"])).all()
                         and p.loc[~fb, ["level_part_eur", "car_part_eur"]].isna().all().all())))

    # five residuals recomputed by a plain loop from the source files
    t, ref = curve()
    idx = level()
    prices = read("oem_prices").set_index("car_id")["list_price_eur"]
    regd = read("master").set_index("car_id")["registration_date"]
    keep = pd.read_parquet(KEEPERS).set_index("car_id")["keeper_date"]
    fc = read("finance_contracts").drop(columns="car_id_truth").merge(read("finance_links")[["contract_id", "car_id"]])
    start = fc[fc["car_id"] > 0].set_index("car_id")["start_date"]
    worst = 0.0
    for r in p[fb].iloc[np.linspace(0, fb.sum() - 1, 5).astype(int)].itertuples():
        back = pd.Timestamp(keep[r.car_id])
        age = (back - pd.Timestamp(regd[r.car_id])).days / 365.25
        want = prices[r.car_id] * float(share(age, t)) * idx[pd.Timestamp(start[r.car_id]).strftime("%Y-%m")] / idx[ref]
        worst = max(worst, abs(want - r.residual_set_eur))
    results.append((f"five residuals set at start recomputed from the source files (worst gap €{worst:.2f})",
                    worst < 0.02))

    fl = p["flagged_before"].notna()
    results.append(("the upgrade check is judged only on retail cars that came back while the queue ran",
                    bool((p.loc[fl, "buyer"].isin(["private", "conquest"])).all())))
    results.append(("every line the group holds and we do not is empty, never zero",
                    bool(p[NOT_HELD].isna().all().all())))
    results.append(("nothing written to the store",
                    [con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("events", "marks", "readiness")]
                    == counts))
    return results


def baseline(con, model):
    """How often any retail car is flagged at one of three consecutive month ends, over the months the upgrade check
    judges: the share a return would show if flags had nothing to do with coming back."""
    w = con.execute(f"""
        WITH w AS (SELECT month_end, bool_or(flag) OVER (PARTITION BY car_id ORDER BY month_end
                                                         ROWS BETWEEN {FLAG_WINDOW - 1} PRECEDING AND CURRENT ROW) AS hit
                   FROM readiness WHERE retail AND model = $m)
        SELECT year(month_end) AS year, sum(hit::INT) AS hits, count(*) AS n FROM w
        WHERE month_end >= (SELECT min(month_end) FROM readiness WHERE model = $m) + INTERVAL {FLAG_WINDOW} MONTH
        GROUP BY 1 ORDER BY 1""", {"m": model}).df().set_index("year")
    return w["hits"].sum() / w["n"].sum(), w["hits"] / w["n"]


def write_report(p, results, bases):
    fb = p[p["residual_set_eur"].notna()]
    fleet = p[p["contract"].eq("fleet lease")]
    fl = p[p["flagged_before"].notna()]
    by_year = fb.assign(year=pd.to_datetime(fb["came_back"]).dt.year).groupby("year").agg(
        cars=("car_id", "size"), level=("level_part_eur", "sum"), car=("car_part_eur", "sum"),
        per_car=("level_part_eur", "mean"))
    eur = lambda v: f"€{v / 1e6:,.1f}m"  # noqa: E731
    lines = ["# X4 part 6: a lifetime P&L per car", "",
             "Generated by `ledger/pnl.py`. One row per car in `data/ledger/car_pnl.parquet`, recomputed from the ledger "
             "on every run. The cars, prices, return dates and index are real; the claims, contracts, buyer types and "
             "resale prices are synthetic (X1 and part 5). **The totals describe the prototype, not the group.**", "",
             "## New cars: incentives (SYNTHETIC)", "",
             f"- Paid on the {int((p['incentives_paid_eur'] != 0).sum()):,} cars with a claim: "
             f"{eur(p['incentives_paid_eur'].sum())}; of which on hold {eur(p['incentives_held_eur'].sum())}, in review "
             f"{eur(p['incentives_review_eur'].sum())} (part 2's decisions, dated after the money went out).", "",
             "## Fleet leases that came back: the residual result, split", "",
             f"- Fleet leases: {len(fleet):,}; came back after the contract started: {len(fb):,}; median months to "
             f"return {fb['months_to_return'].median():.0f}.",
             f"- Residual set at start {eur(fb['residual_set_eur'].sum())}; value at return "
             f"{eur(fb['value_at_return_eur'].sum())}; synthetic resale {eur(fb['resale_eur'].sum())}.",
             f"- **Level part {eur(fb['level_part_eur'].sum())}** (the market's move between start and return: real "
             f"index, real dates). Car part {eur(fb['car_part_eur'].sum())}: synthetic draws whose median is the mark; "
             "they sum above it only because the adverts' spread is skewed upward (the band's 90th percentile sits "
             "further above the median than the 10th sits below). **Not a finding.**",
             "- \"Came back\" is the latest keeper change: the lease return, or a trader's later resale that hides it. "
             "So months to return run long, and the level part is measured at that later date; a live ledger reads "
             "the contract's end.", "",
             "| returned in | cars | level part | per car | car part (synthetic) |", "|---|---:|---:|---:|---:|"]
    lines += [f"| {r.Index} | {r.cars:,} | {eur(r.level)} | €{r.per_car:,.0f} | {eur(r.car)} |"
              for r in by_year.itertuples()]
    lines.append(f"| all | {len(fb):,} | {eur(fb['level_part_eur'].sum())} | €{fb['level_part_eur'].mean():,.0f} | "
                 f"{eur(fb['car_part_eur'].sum())} |")
    lines += ["", "The level part is what the programme proposes to price and re-mark monthly: a gain or loss nobody "
                  "chose, set by where the whole market stood when the car came back. The index is held at its last "
                  "published month for returns after it.", "",
              "## Upgrades (leak 2): were the customers flagged before they came back?", "",
              f"- Retail cars that came back while the queue ran: {len(fl):,}. Each queue flags the top tenth of its "
              "population each month; the check asks how often a returning customer was flagged in the "
              f"{FLAG_WINDOW} months before, against how often any retail car was in any 3-month window.",
              "- Real dates, synthetic retail labels (a random share of real cars), and a score that is age alone: "
              "this measures the rule's reach, not the group's customers. Returns are latest keeper changes, a lower "
              "bound.", "",
              "### The age-only queue (from age one), the rule the window replaced", "",
              "| came back in | retail cars | flagged in the 3 months before | any retail car, any 3-month window |",
              "|---|---:|---:|---:|"]
    fa = fl["flagged_before_age_only"].astype(bool)
    base, base_by_year = bases["age_only"]
    fy = fa.groupby(pd.to_datetime(fl["came_back"]).dt.year)
    lines += [f"| {y} | {len(g):,} | {g.mean():.1%} | {base_by_year.get(y, float('nan')):.1%} |" for y, g in fy]
    lines.append(f"| all | {len(fl):,} | {fa.mean():.1%} | {base:.1%} |")
    lines += ["", "While the age-only queue's flags sat on young cars (part 4's caveat: the group's first-year rate fits "
                  "dealer registrations passing to customers), returning customers were flagged less often than any "
                  "car; once the book reached the lease-end waves, more often. An age-only queue earns its place only "
                  "on the waves; the group's own contract end dates are the exact version.", "",
              f"### The queue from the equity window (month {WINDOW}), as it runs now", "",
              "| came back in | retail cars | flagged in the 3 months before, from the window | "
              "any retail car, any 3-month window, from the window |", "|---|---:|---:|---:|"]
    fw = fl["flagged_before"].astype(bool)
    wbase, wbase_by_year = bases["window"]
    fy = fw.groupby(pd.to_datetime(fl["came_back"]).dt.year)
    rows = [(y, len(g), g.mean(), wbase_by_year.get(y, float("nan"))) for y, g in fy]
    lines += [f"| {y} | {n:,} | {a:.1%} | {b:.1%} |" for y, n, a, b in rows]
    lines.append(f"| all | {len(fl):,} | {fw.mean():.1%} | {wbase:.1%} |")
    above = [str(y) for y, _, a, b in rows if a > b]
    below = [str(y) for y, _, a, b in rows if a <= b]
    lines += ["", f"From the window, returning customers were flagged more often than any car in "
                  f"{', '.join(above) or 'no year'}, and no more often in {', '.join(below) or 'no year'}; over all "
                  f"returns, {fw.mean():.1%} against {wbase:.1%}.",
              ("The window keeps first-year cars out of the queue, but before the lease-end waves the queue sat on cars "
               "just past it, and returning customers were flagged there no more often than any car: the window is the "
               "upgrade rule (equity), not a fix for the score. " if below else "") +
              "An age-only score earns its place on the waves; the group's own contract end dates are the exact version.",
              "", "## Lines the group holds and this prototype does not", "",
              "- " + ", ".join(c.replace("_", " ") for c in NOT_HELD) + ": empty in every row, never zero.", ""]
    for car in (SHOWCASE, int(fb["car_id"].iloc[0])):
        r = p.set_index("car_id").loc[car]
        lines += [f"## Car {car}: {r['make']} {r['model']}, {r['buyer']} buyer", "", "| line | value |", "|---|---|"]
        for c in ["catalogue_eur", "incentives_paid_eur", "incentives_held_eur", "incentives_review_eur", "contract",
                  "contract_start", "came_back", "months_to_return", "residual_set_eur", "value_at_return_eur",
                  "resale_eur", "level_part_eur", "car_part_eur", "flagged_before", "mark_now_eur"] + NOT_HELD:
            v = r[c]
            shown = ("not held" if c in NOT_HELD else "" if v is None or pd.isna(v)
                     else f"€{v:,.0f}" if c.endswith("_eur") else f"{pd.Timestamp(v):%Y-%m-%d}"
                     if c in ("contract_start", "came_back") else str(v))
            lines.append(f"| {c.replace('_', ' ')} | {shown} |")
        lines.append("")
    lines += ["## Checks", ""] + [f"- {'pass' if ok else 'FAIL'}: {name}" for name, ok in results]
    REPORT.write_text("\n".join(lines) + "\n")


def main():
    con = open_store(STORE)
    counts = [con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("events", "marks", "readiness")]
    p = pnl(con)
    results = check(con, p, counts)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    p.to_parquet(OUT, index=False)
    write_report(p, results, {"window": baseline(con, READY), "age_only": baseline(con, AGE_ONLY)})
    print(f"{len(p):,} cars; " + ", ".join("pass" if ok else "FAIL" for _, ok in results))
    con.close()
    if not all(ok for _, ok in results):
        sys.exit("a check failed; see " + str(REPORT))


if __name__ == "__main__":
    main()
