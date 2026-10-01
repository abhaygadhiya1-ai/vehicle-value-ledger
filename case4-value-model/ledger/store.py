"""X4 part 1: the vehicle value ledger's event store, and the facts it starts from.

The ledger is one table of events, one row per thing that happened to a car, and it only ever grows. A correction is
a new event, never an edit, so the store can always say what the group knew on any past date.

**Two dates per event.** `valid_date` is when it happened; `recorded_date` is when the group's systems learned it.
Where a source gives no separate date, the group learns a fact the day it happens. Two sources carry a real lag:
  - a claim is for a sale (`valid_date`, its system's sale event) and is learned when it is filed (`claim_date`);
  - the register's current-keeper date, read within a quarter of registration (X1's `inject.py`), is learned at the
    end of that window: registration plus 90 days. X1's second read, years later, is a test device for censoring,
    not something the group holds at the time, so it is left out.

**What it reads.** Only what X1 lets a detector read (`leak1/inject.py`): the two systems' claims as stored, the OEM's
vehicle record as recorded (gamed dates included), the independent sources X1 added (OEM record, prices, transfers and
order log; the register's first keeper, keeper and trade-ins; the finance contracts), and the resolver's links: each
claim's car from X1's layer 3, each finance contract's from part 9. Never the truth tables, the clean sales or
`x1_cars`, whose registration date is the true one.

**No personal data in events** (CJEU C-319/22: a VIN is personal data for whoever can link it to its owner). X1's
world holds none beyond the VIN and a buyer type. A production ledger keeps the customer link outside the log, so
erasing a customer destroys that link and leaves history alone.

**Append-only by construction.** `append()` is the only write to `events`, and it only inserts. An event id is derived
from its source key, so loading a source twice adds nothing, and a late-arriving event is simply a new row. Monthly
estimates (part 3's marks, part 4's readiness scores) are millions of rows, so each sits in its own typed table,
written only by `append_estimates()`, which also only inserts. The `ledger` view shows everything as one stream of
events; `as_of()` and `timeline()` read it. The schema is created if missing on every open, so a later part adds its
table without a rebuild. No SQL here edits or removes a row; `check()` searches this file for such statements.
`--rebuild` starts a fresh store from the sources, the prototype's reset.

Output: data/ledger/<world>.duckdb (not published: data/ is outside the allowlist) and ledger/x4_store_report.md.
Usage: .venv/bin/python ledger/store.py [--rebuild]   (X1_DATA picks the world, as for every X1 script)
"""
import hashlib
import re
import sys
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "leak1"))
from generate import SYN  # noqa: E402
from layer1_keys import load as load_claims  # noqa: E402
from spec import SETTINGS  # noqa: E402

STORE = HERE.parent / "data" / "ledger" / f"{SYN.name}.duckdb"
REPORT = HERE / "x4_store_report.md"
KEEPER_READ_DAYS = 90  # X1's prompt register read falls within a quarter of registration (inject.py)
FACTS = "x1_world"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq           BIGINT  NOT NULL,          -- append order
    event_id      VARCHAR PRIMARY KEY,       -- from the source key, so a reload adds nothing
    car_id        BIGINT,                    -- the resolved car; NULL when the resolver found none
    event_type    VARCHAR NOT NULL,
    valid_date    DATE    NOT NULL,          -- when it happened
    recorded_date DATE    NOT NULL,          -- when the group's systems learned it
    source        VARCHAR NOT NULL,
    source_ref    VARCHAR NOT NULL,
    amount_eur    DOUBLE,
    kind          VARCHAR NOT NULL,          -- fact, a model's estimate, a decision, or synthetic
    batch         VARCHAR NOT NULL,
    attrs         VARCHAR                    -- JSON: the source's other fields
);
CREATE TABLE IF NOT EXISTS marks (           -- part 3's estimates, typed so millions of rows stay small
    model         VARCHAR NOT NULL,          -- the valuation model and version
    car_id        BIGINT  NOT NULL,
    month_end     DATE    NOT NULL,          -- when the value holds
    recorded_date DATE    NOT NULL,          -- when the group could know it
    mark_eur      DOUBLE  NOT NULL,
    low_eur       DOUBLE  NOT NULL,          -- 80% band
    high_eur      DOUBLE  NOT NULL,
    age_years     DOUBLE  NOT NULL,
    level         DOUBLE  NOT NULL           -- the market level, as a ratio to the curve's month
);
CREATE TABLE IF NOT EXISTS readiness (       -- part 4: the chance a car comes to market, and the upgrade queue
    model         VARCHAR NOT NULL,
    car_id        BIGINT  NOT NULL,
    month_end     DATE    NOT NULL,
    recorded_date DATE    NOT NULL,
    age_months    INTEGER NOT NULL,
    p3            DOUBLE  NOT NULL,          -- within 3 months, with its 80% band
    p3_low        DOUBLE  NOT NULL,
    p3_high       DOUBLE  NOT NULL,
    p12           DOUBLE  NOT NULL,          -- within 12 months
    p12_low       DOUBLE  NOT NULL,
    p12_high      DOUBLE  NOT NULL,
    retail        BOOLEAN NOT NULL,          -- a private or conquest customer: the upgrade queue's population
    flag          BOOLEAN NOT NULL           -- in the queue's top band that month
);
CREATE OR REPLACE VIEW ledger AS
SELECT * FROM events
UNION ALL
SELECT NULL, model || '|' || car_id || '|' || strftime(month_end, '%Y-%m'), car_id, 'mark', month_end, recorded_date,
       model, car_id || '|' || strftime(month_end, '%Y-%m'), mark_eur, 'estimate', model,
       json_object('age', age_years, 'level', level, 'low', low_eur, 'high', high_eur)::VARCHAR
FROM marks
UNION ALL
SELECT NULL, model || '|' || car_id || '|' || strftime(month_end, '%Y-%m'), car_id, 'readiness', month_end,
       recorded_date, model, car_id || '|' || strftime(month_end, '%Y-%m'), NULL, 'estimate', model,
       json_object('age_months', age_months, 'p3', p3, 'p3_low', p3_low, 'p3_high', p3_high, 'p12', p12,
                   'p12_low', p12_low, 'p12_high', p12_high, 'retail', retail, 'flag', flag)::VARCHAR
FROM readiness"""
COLUMNS = ["event_id", "car_id", "event_type", "valid_date", "recorded_date", "source", "source_ref", "amount_eur",
           "kind", "attrs"]


def read(name):
    return pd.read_parquet(SYN / f"x1_{name}.parquet")


def events(d, event_type, source, ref, valid, recorded=None, amount=None, attrs=(), kind="fact"):
    """One event per row of `d`. `ref` is the column holding the source key; dates and amount are column names."""
    out = pd.DataFrame({
        "car_id": d["car_id"].astype("Int64"),
        "event_type": event_type,
        "valid_date": pd.to_datetime(d[valid]).dt.normalize(),
        "recorded_date": pd.to_datetime(d[recorded or valid]).dt.normalize(),
        "source": source,
        "source_ref": d[ref].astype(str),
        "amount_eur": d[amount].astype(float) if amount else np.nan,
        "kind": kind,
    })
    out["attrs"] = (d[list(attrs)].to_json(orient="records", lines=True, date_format="iso").splitlines()
                    if attrs else None)
    key = source + "|" + event_type + "|" + out["source_ref"]
    out["event_id"] = [hashlib.sha1(k.encode()).hexdigest()[:16] for k in key]
    return out[COLUMNS]


def facts():
    """Every fact event in the world, from the sources a detector may read."""
    master = read("master")
    reg = master.set_index("car_id")["registration_date"]
    out = [
        events(master.assign(ref=master["car_id"]), "order", "vehicle_master", "ref", "order_date",
               attrs=["dealer_id", "order_no"]),
        events(master.assign(ref=master["car_id"]), "registration", "vehicle_master", "ref", "registration_date",
               amount="list_price_eur",
               attrs=["vin", "system", "make", "model", "body", "variant", "trim", "dealer_id", "buyer", "order_no"]),
    ]

    rec = read("oem_record")
    out.append(events(rec.assign(ref=rec["car_id"]), "order", "oem_record", "ref", "order_date", attrs=["dealer_id"]))
    prices = read("oem_prices").assign(registration_date=lambda d: d["car_id"].map(reg))
    out.append(events(prices.assign(ref=prices["car_id"]), "list_price", "oem_prices", "ref", "registration_date",
                      amount="list_price_eur"))
    log = read("oem_order_log")
    log["ref"] = log["car_id"].astype(str) + "|" + log["event"] + "|" + log["date"].astype(str)
    out.append(events(log, "order_log", "oem_order_log", "ref", "date", attrs=["event", "dealer_id"]))
    tr = read("oem_transfers")
    tr["ref"] = (tr["car_id"].astype(str) + "|" + tr["transfer_date"].astype(str) + "|" + tr["from_dealer"].astype(str)
                 + "|" + tr["to_dealer"].astype(str))
    out.append(events(tr, "dealer_transfer", "oem_transfers", "ref", "transfer_date",
                      attrs=["from_dealer", "to_dealer"]))

    fk = read("register_first_keeper")
    out.append(events(fk.assign(ref=fk["car_id"]), "first_keeper", "register", "ref", "customer_date",
                      attrs=["first_keeper"]))
    kp = read("register_keepers")
    kp["read_date"] = np.maximum(kp["car_id"].map(reg) + pd.Timedelta(days=KEEPER_READ_DAYS),
                                 kp["keeper_date_prompt"])
    out.append(events(kp.assign(ref=kp["car_id"]), "keeper_read", "register", "ref", "keeper_date_prompt",
                      recorded="read_date"))
    ti = read("register_tradeins").dropna(subset=["tradein_make"])
    ti = ti.merge(read("register_tradein_keepers"), on="car_id", how="left")
    ti["registration_date"] = ti["car_id"].map(reg)
    out.append(events(ti.assign(ref=ti["car_id"]), "tradein", "register", "ref", "registration_date",
                      attrs=["tradein_make", "tradein_keeper_since"]))

    fc = read("finance_contracts").drop(columns="car_id_truth")  # the scorer's column, never the ledger's
    fc = fc.merge(read("finance_links")[["contract_id", "car_id", "score"]], on="contract_id", how="left")
    fc["car_id"] = fc["car_id"].where(fc["car_id"] > 0)  # the linkage writes -1 for "no car found": unresolved
    out.append(events(fc.rename(columns={"score": "link_score"}), "finance_start", "finance_jv", "contract_id",
                      "start_date", attrs=["contract_type", "vin", "link_score"]))

    claims, _ = load_claims()  # both systems in X1's canonical columns, amounts net of VAT
    link = read("flags_layer3").set_index("claim_id")["car_id"]
    claims["car_id"] = claims["claim_id"].map(link)
    for s, g in claims.groupby("system"):
        out.append(events(g, "claim", f"system_{s.lower()}", "claim_id", "event_date", recorded="claim_date",
                          amount="amount_net", attrs=["dealer", "programme", "order_no", "vin"]))
    return pd.concat(out, ignore_index=True)


def open_store(path):
    """Opens the store, creating any table or view it lacks."""
    con = duckdb.connect(str(path))
    con.execute(SCHEMA)
    return con


def append(con, new, batch):
    """The only write: inserts the events whose id is not in the store yet, in a fixed order, and returns how many."""
    assert new["event_id"].is_unique, "an event id repeats within the batch"
    start = con.execute("SELECT coalesce(max(seq), 0) FROM events").fetchone()[0]
    con.register("incoming", new[COLUMNS])
    n = con.execute("""
        INSERT INTO events
        SELECT ? + row_number() OVER (ORDER BY recorded_date, valid_date, event_id), event_id, car_id, event_type,
               valid_date, recorded_date, source, source_ref, amount_eur, kind, ?, attrs
        FROM incoming WHERE event_id NOT IN (SELECT event_id FROM events)""", [start, batch]).fetchone()[0]
    con.unregister("incoming")
    return n


def append_estimates(con, table, new):
    """The only write to an estimate table (`marks`, `readiness`): inserts the rows whose (model, car, month) is not
    in it yet."""
    cols = [c[0] for c in con.execute(f"SELECT * FROM {table} LIMIT 0").description]
    con.register("incoming", new[cols])
    n = con.execute(f"""
        INSERT INTO {table} SELECT * FROM incoming i WHERE NOT EXISTS (
            SELECT 1 FROM {table} m WHERE m.model = i.model AND m.car_id = i.car_id AND m.month_end = i.month_end)"""
                    ).fetchone()[0]
    con.unregister("incoming")
    return n


def content_hash(con, upto=None):
    """A fingerprint of the store in append order, up to `seq` = `upto` if given."""
    d = con.execute("SELECT * FROM events WHERE seq <= ? ORDER BY seq",
                    [upto if upto is not None else 2**62]).df()
    return hashlib.sha256(pd.util.hash_pandas_object(d, index=False).to_numpy().tobytes()).hexdigest()[:12]


def as_of(con, date):
    """What the group knew on `date`: every event recorded by then."""
    return con.execute("SELECT * FROM ledger WHERE recorded_date <= ? ORDER BY seq", [pd.Timestamp(date)]).df()


def timeline(con, car_id, date=None):
    """One car's history, in the order things happened, as known on `date` (default: everything)."""
    q = "SELECT * FROM ledger WHERE car_id = ? AND recorded_date <= ? ORDER BY valid_date, seq"
    return con.execute(q, [car_id, pd.Timestamp(date or "2100-01-01")]).df()


def build(path, rows):
    con = open_store(path)
    n = append(con, rows, FACTS)
    return con, n


def check(con, rows):
    """Each check reads the sources itself, so a builder bug cannot pass by agreeing with itself. `rows` are the fact
    events the store was built from, reused for the rebuild and reload checks."""
    got = con.execute("SELECT source, event_type, count(*) n, sum(amount_eur) eur FROM events "
                      "GROUP BY ALL ORDER BY ALL").df()
    n = got.set_index(["source", "event_type"])["n"]
    raw = {s: read(f"system_{s}") for s in "ab"}
    expect = {("vehicle_master", "order"): len(read("master")), ("vehicle_master", "registration"): len(read("master")),
              ("oem_record", "order"): len(read("oem_record")), ("oem_prices", "list_price"): len(read("oem_prices")),
              ("oem_order_log", "order_log"): len(read("oem_order_log")),
              ("oem_transfers", "dealer_transfer"): len(read("oem_transfers")),
              ("register", "first_keeper"): len(read("register_first_keeper")),
              ("register", "keeper_read"): len(read("register_keepers")),
              ("register", "tradein"): int(read("register_tradeins")["tradein_make"].notna().sum()),
              ("finance_jv", "finance_start"): len(read("finance_contracts")),
              ("system_a", "claim"): len(raw["a"]), ("system_b", "claim"): len(raw["b"])}
    results = [("every source row is one event", all(n.get(k, 0) == v for k, v in expect.items())
                and len(n) == len(expect))]

    eur = got.set_index(["source", "event_type"])["eur"]
    vat = SETTINGS["vat_nl"][0]
    want_a = raw["a"]["amount_net_eur"].sum()
    want_b = (raw["b"]["importo_lordo_eur"] / (1 + vat)).round(2).sum()  # B stores gross; X1's VAT setting
    results.append(("claim euros match both systems, net of VAT",
                    abs(eur[("system_a", "claim")] - want_a) < 0.01 and abs(eur[("system_b", "claim")] - want_b) < 0.01))
    unlinked = con.execute("SELECT count(*) FROM events WHERE event_type = 'claim' AND car_id IS NULL").fetchone()[0]
    results.append(("unlinked claims = the resolver's", unlinked == int(read("flags_layer3")["car_id"].isna().sum())))
    one_reg = con.execute("SELECT count(DISTINCT car_id) = count(*) FROM events WHERE event_type = 'registration'")
    results.append(("one registration per car", bool(one_reg.fetchone()[0])))
    stray = con.execute("SELECT count(*) FROM events e WHERE car_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM events r "
                        "WHERE r.event_type = 'registration' AND r.car_id = e.car_id)").fetchone()[0]
    unlinked_fc = int((read("finance_links")["car_id"] <= 0).sum())
    results.append(("every car in the ledger is on the registration record; unlinked contracts stay unresolved",
                    stray == 0 and con.execute("SELECT count(*) FROM events WHERE event_type = 'finance_start' "
                                               "AND car_id IS NULL").fetchone()[0] == unlinked_fc))

    with tempfile.TemporaryDirectory() as tmp:
        other, _ = build(Path(tmp) / "again.duckdb", facts())
        results.append(("two builds give the same content hash", content_hash(other) == content_hash(con)))
        results.append(("loading the sources again adds nothing", append(other, rows, "reload") == 0))
        last = other.execute("SELECT max(seq) FROM events").fetchone()[0]
        before = content_hash(other)
        late = rows.iloc[[0]].assign(event_id="late-arrival-test", source_ref="test", event_type="note")
        added = append(other, late, "test")
        results.append(("a new batch leaves every earlier row unchanged",
                        added == 1 and content_hash(other, upto=last) == before))
        other.close()

    code = re.sub(r'""".*?"""', "", Path(__file__).read_text(), flags=re.S)
    edits = re.findall(r"\b(" + "UPD" + "ATE|" + "DEL" + "ETE|" + "TRUN" + "CATE|" + "DR" + "OP" + r")\b", code)
    results.append(("no statement in the code edits or removes a row", not edits))

    lag = con.execute("SELECT event_id, recorded_date, valid_date FROM events WHERE event_type = 'claim' "
                      "ORDER BY recorded_date - valid_date DESC, event_id LIMIT 1").df().iloc[0]
    day = pd.Timestamp(lag["recorded_date"])
    seen = [lag["event_id"] in set(as_of(con, d)["event_id"]) for d in (day - pd.Timedelta(days=1), day)]
    results.append(("the latest-filed claim is unknown the day before it is filed, known on the day",
                    seen == [False, True]))
    return got, results, lag


def showcase(con):
    """The car with the most kinds of event: the one a demo opens first (ties: the lowest id)."""
    return int(con.execute("SELECT car_id FROM events WHERE car_id IS NOT NULL GROUP BY car_id "
                           "ORDER BY count(DISTINCT event_type) DESC, count(*) DESC, car_id LIMIT 1").fetchone()[0])


def write_report(con, got, results, lag):
    car = showcase(con)
    t = timeline(con, car)
    lines = ["# X4 part 1: the ledger's event store", "",
             "Generated by `ledger/store.py`. Synthetic world (X1): every figure here describes the test world, not the "
             "group. Store: `data/ledger/" + STORE.name + "` (not published).", "",
             f"**{int(got['n'].sum()):,} events** from {got['source'].nunique()} sources; content hash "
             f"`{content_hash(con)}`.", "",
             "| source | event | events | euros |", "|---|---|---:|---:|"]
    lines += [f"| {r.source} | {r.event_type} | {r.n:,} | {'' if pd.isna(r.eur) else f'{r.eur:,.0f}'} |"
              for r in got.itertuples()]
    lines += ["", "## Checks", ""] + [f"- {'pass' if ok else 'FAIL'}: {name}" for name, ok in results]
    lines += ["", f"The as-of check uses the claim filed longest after its sale: sale {lag['valid_date']:%Y-%m-%d}, "
                  f"filed {lag['recorded_date']:%Y-%m-%d}.", "",
              f"## One car's timeline (car {car}, the car with the most kinds of event)", "",
              "| happened | learned | event | source | euros | detail |", "|---|---|---|---|---:|---|"]
    for r in t.itertuples():
        detail = "" if pd.isna(r.attrs) else r.attrs.replace("|", "/")[:90]
        eur = "" if pd.isna(r.amount_eur) else f"{r.amount_eur:,.2f}"
        lines.append(f"| {r.valid_date:%Y-%m-%d} | {r.recorded_date:%Y-%m-%d} | {r.event_type} | {r.source} | {eur} "
                     f"| {detail} |")
    REPORT.write_text("\n".join(lines) + "\n")


def main():
    if STORE.exists() and "--rebuild" not in sys.argv:
        sys.exit(f"{STORE} exists; the store only grows. Pass --rebuild to start a fresh one from the sources.")
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.unlink(missing_ok=True)
    rows = facts()
    con, n = build(STORE, rows)
    got, results, lag = check(con, rows)
    write_report(con, got, results, lag)
    print(f"{n:,} events, hash {content_hash(con)}; " + ", ".join("pass" if ok else "FAIL" for _, ok in results))
    con.close()
    if not all(ok for _, ok in results):
        sys.exit("a check failed; see " + str(REPORT))


if __name__ == "__main__":
    main()
