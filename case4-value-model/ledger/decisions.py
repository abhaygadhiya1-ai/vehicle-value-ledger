"""X4 part 2: the detector's decision on every claim, as events in the ledger.

X1's layer 3 (with layers 1 and 2 inside it) marks each claim it would not pay as filed, with a reason. Part 2 writes
that answer into the ledger as one `claim_decision` event per claim:
  hold    a key, matching or hard-rule failure (X1's layer-1 and layer-2 reasons, and `layer3_rules.HARD`)
  review  held for a person to decide (`layer3_rules.REVIEW`)
  clear   no flag
The decision carries no euros: the claim event holds them, so a view that sums `amount_eur` cannot count a claim twice.

**When the ledger learns a decision.** X1's detector runs once over the whole history, so every decision is dated the
day after the last fact the world holds: an audit run, after the money went out. That is leak 1 as the case puts it,
"checked too late". As of the day before, every claim is simply filed; from the run date, the holds are in. A live
ledger would decide each claim as its evidence arrives; dating each rule's evidence is not done here.

**Truth is read only by the check, through X1's own scorer** (`leak1/score.py`). The check compares the result with the
scorecard's full-pipeline row for our world. Synthetic: it measures the tool, not the group.

Output: new events in data/ledger/<world>.duckdb, and ledger/x4_decisions_report.md.
Usage: .venv/bin/python ledger/decisions.py   (after ledger/store.py; running it again adds nothing)
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from store import STORE, append, content_hash, events, open_store, read, timeline  # noqa: E402
sys.path.insert(0, str(HERE.parent / "leak1"))
from layer3_rules import REVIEW  # noqa: E402
from score import score  # noqa: E402

REPORT = HERE / "x4_decisions_report.md"
SCORECARD = HERE.parent / "leak1" / "x1_scorecard_report.md"
SCORECARD_ROW = "Ours · + complete sources"
BATCH = "x1_layer3_run"


def run_date(con):
    """The detector's run: the day after the last fact the world holds."""
    last = con.execute("SELECT max(recorded_date) FROM events WHERE kind = 'fact'").fetchone()[0]
    return pd.Timestamp(last) + pd.Timedelta(days=1)


def decisions(con):
    claims = con.execute("SELECT source_ref AS claim_id, car_id, event_id AS claim_event FROM events "
                         "WHERE event_type = 'claim'").df()
    reason = read("flags_layer3").set_index("claim_id")["reason"]
    d = claims.assign(reason=claims["claim_id"].map(reason))
    d["decision"] = "clear"
    d.loc[d["reason"].notna(), "decision"] = "hold"
    d.loc[d["reason"].isin(REVIEW), "decision"] = "review"
    d["run_date"] = run_date(con)
    return events(d, "claim_decision", "x1_layer3", "claim_id", "run_date",
                  attrs=["decision", "reason", "claim_event"], kind="decision")


def scorecard_row():
    """The scorecard's full-pipeline row for our world, as printed: flagged, then five rates."""
    for line in SCORECARD.read_text().splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] == SCORECARD_ROW:
            return cells[1:]
    raise ValueError(f"no '{SCORECARD_ROW}' row in {SCORECARD}")


def check(con, last_fact, before):
    got = con.execute("SELECT source_ref AS claim_id, json_extract_string(attrs, '$.decision') AS decision, "
                      "json_extract_string(attrs, '$.reason') AS reason FROM events "
                      "WHERE event_type = 'claim_decision'").df()
    flags = read("flags_layer3")
    n_claims = con.execute("SELECT count(*) FROM events WHERE event_type = 'claim'").fetchone()[0]
    results = [("one decision per claim", len(got) == n_claims == got["claim_id"].nunique()),
               ("reasons match layer 3's flags",
                got["reason"].value_counts().to_dict() == flags["reason"].value_counts().to_dict()),
               ("review exactly where layer 3 names a review rule",
                got["decision"].eq("review").equals(got["reason"].isin(REVIEW)))]

    head, by_label, _ = score(got.assign(reason=got["reason"].where(got["decision"] != "clear")))
    row = scorecard_row()
    ours = [str(head["flagged"]), f"{100 * head['precision']:.1f}", f"{100 * head['recall']:.1f}",
            f"{100 * head['euro_recall']:.1f}", f"{head['false_alarms_per_1000_legit']:.2f}",
            f"{head['review_load_per_1000']:.1f}"]
    results.append((f"X1's scorer on the ledger's decisions reproduces the scorecard row '{SCORECARD_ROW}'",
                    ours == row))

    run = run_date(con)
    results.append(("appending the decisions left every fact unchanged", content_hash(con, upto=last_fact) == before))
    results.append(("running again adds nothing", append(con, decisions(con), BATCH) == 0))

    shown = {}
    for reason, both_systems in (("duplicate", True), ("late_claim", False)):
        q = ("SELECT e.car_id FROM events d JOIN events e ON e.event_id = json_extract_string(d.attrs, '$.claim_event') "
             "WHERE d.event_type = 'claim_decision' AND json_extract_string(d.attrs, '$.reason') = ? "
             "AND e.car_id IS NOT NULL GROUP BY e.car_id ")
        if both_systems:  # the other claim sits in the other system: a cross-system duplicate, seen without truth
            q += ("HAVING (SELECT count(DISTINCT source) FROM events c WHERE c.car_id = e.car_id "
                  "AND c.event_type = 'claim') = 2 ")
        car = int(con.execute(q + "ORDER BY e.car_id LIMIT 1", [reason]).fetchone()[0])
        seen = [set(timeline(con, car, d)["event_type"]) for d in (run - pd.Timedelta(days=1), run)]
        results.append((f"a {reason} hold is invisible the day before the run and visible on it (car {car})",
                        "claim_decision" not in seen[0] and "claim_decision" in seen[1] and "claim" in seen[0]))
        shown[reason] = car
    return got, results, head, by_label, shown, run


def write_report(con, got, results, head, by_label, shown, run):
    at_stake = con.execute(
        "SELECT json_extract_string(d.attrs, '$.decision') AS decision, count(*) AS n, sum(c.amount_eur) AS eur "
        "FROM events d JOIN events c ON c.event_id = json_extract_string(d.attrs, '$.claim_event') "
        "WHERE d.event_type = 'claim_decision' GROUP BY ALL ORDER BY ALL").df()
    lines = ["# X4 part 2: the detector's decisions, in the ledger", "",
             "Generated by `ledger/decisions.py`. Synthetic world (X1): every figure describes the test world, not the "
             "group.", "",
             f"One `claim_decision` event per claim, dated on the detector's run, {run:%Y-%m-%d}: the day after the "
             "last fact the world holds, so every hold arrives after the claim was paid (leak 1, \"checked too "
             "late\").", "",
             "| decision | claims | euros at stake (net) |", "|---|---:|---:|"]
    lines += [f"| {r.decision} | {r.n:,} | {r.eur:,.0f} |" for r in at_stake.itertuples()]
    lines += ["", "| reason | decision | claims |", "|---|---|---:|"]
    by = got[got["decision"] != "clear"].groupby(["reason", "decision"]).size().sort_values(ascending=False)
    lines += [f"| {r} | {d} | {n:,} |" for (r, d), n in by.items()]
    caught, total = by_label["caught_eur"].sum(), by_label["leak_eur"].sum()
    lines += ["", "## Against the truth (SYNTHETIC; X1's scorer)", "",
              f"- Flagged {head['flagged']:,}; precision {100 * head['precision']:.1f}%, recall "
              f"{100 * head['recall']:.1f}%, euro recall {100 * head['euro_recall']:.1f}%; false alarms "
              f"{head['false_alarms_per_1000_legit']:.2f} per 1,000 legitimate claims.",
              f"- Leak euros on held or reviewed claims: {caught:,.0f} of {total:,.0f}.", "",
              "## Checks", ""] + [f"- {'pass' if ok else 'FAIL'}: {name}" for name, ok in results]
    for reason, car in shown.items():
        t = timeline(con, car, run)
        t = t[t["event_type"].isin(["registration", "claim", "claim_decision"])]
        lines += ["", f"## Car {car}: a `{reason}` hold, as known on the run date", "",
                  "| happened | learned | event | source | euros | detail |", "|---|---|---|---|---:|---|"]
        for r in t.itertuples():
            detail = "" if pd.isna(r.attrs) else r.attrs.replace("|", "/")[:80]
            eur = "" if pd.isna(r.amount_eur) else f"{r.amount_eur:,.2f}"
            lines.append(f"| {r.valid_date:%Y-%m-%d} | {r.recorded_date:%Y-%m-%d} | {r.event_type} | {r.source} "
                         f"| {eur} | {detail} |")
    REPORT.write_text("\n".join(lines) + "\n")


def main():
    con = open_store(STORE)
    last_fact = con.execute("SELECT max(seq) FROM events WHERE kind = 'fact'").fetchone()[0]
    before = content_hash(con, upto=last_fact)
    n = append(con, decisions(con), BATCH)
    got, results, head, by_label, shown, run = check(con, last_fact, before)
    write_report(con, got, results, head, by_label, shown, run)
    print(f"{n:,} decisions appended, run date {run:%Y-%m-%d}; " + ", ".join("pass" if ok else "FAIL"
                                                                             for _, ok in results))
    con.close()
    if not all(ok for _, ok in results):
        sys.exit("a check failed; see " + str(REPORT))


if __name__ == "__main__":
    main()
