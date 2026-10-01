"""X1 part 4: the six leaks, injected into the clean world, with a truth table.

Starts from part 3's clean world and adds, at the rates set in `spec.py` (all ASSUMPTION, each a share of its own
pool; no public benchmark exists, so part 10 sweeps them):

  quarter_end_gaming      an A dealer that missed its quarterly target by a few cars pulls cars due early next
                          quarter into the last days of this one. The target is then met, and every car in the
                          quarter earns the volume bonus. The vehicle record shows the pulled-forward dates.
  late_claim              a claim filed after its deadline and paid anyway
  illegal_stack           a retail claim added to a fleet car; for a dealer on both systems sometimes in the other one
  cross_system_duplicate  the group programme claimed again in the other system, by a dealer on both
  vin_typo                a claim filed again under a mistyped VIN (look-alike swap, random character, or
                          transposition), paid as if a separate car
  pre_vin_claim           an order-only claim in B for an order that never became a registered car

and three legitimate look-alikes that must not be flagged:
  - a claim cancelled by a credit note and filed again with the right amount;
  - a B claim whose VIN was left empty though its order did become a car;
  - a claim that is not a duplicate, entered with a mistyped VIN or order number. Without it, "unknown key" would
    mean "leak" for free.
Cars pulled forward keep their own claims, labelled legit_gamed_car; the money in gaming is the volume bonus. A
mistyped VIN may land on another real VIN, as real typos do.

**No tell in the ids.** Every claim is renumbered in claim-date order with a random tie-break, so an injected row
cannot be spotted by being numbered last.

Outputs (data/synthetic/, not published). What a detector may read:
  x1_system_a.parquet, x1_system_b.parquet   the claims as each system stores them
  x1_master.parquet                          the OEM's vehicle record as recorded (gamed dates included)
  x1_dealers.parquet                         from part 3
What only the scorer may read:
  x1_truth.parquet        one row per claim: label, euros overpaid, the claim it duplicates, detail
  x1_truth_cars.parquet   cars whose recorded registration was pulled forward, with the true date
A source the dealer does not control (part 7b), written from its own random stream:
  x1_register_keepers.parquet  each car's current-keeper date as the national register would show it, read within
                               a quarter (`keeper_date_prompt`) and years later (`keeper_date_late`)
Usage: .venv/bin/python leak1/inject.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from generate import SEED_OFFSET, SYN, quarter_counts_targets, quarter_end, setting  # noqa: E402
from population import ALPHABET  # noqa: E402
from spec import (CLAIM_DEADLINE_DAYS, CONFUSABLE, CROSSWALK, EXCLUDES, LEAKS, PROGRAMMES,  # noqa: E402
                  claim_window, system_table)

SEED = 4 + SEED_OFFSET  # part 4
KEEPER_SEED = 44 + SEED_OFFSET  # its own stream, so adding the keeper source changed no existing file
LEGIT_LABELS = ["legit_reversal", "legit_vin_blank", "legit_key_typo", "legit_gamed_car"]
PROG = PROGRAMMES.set_index(["system", "family"])
OTHER = {"A": "B", "B": "A"}
DAY = pd.Timedelta(days=1)


def amount_for(system, family, list_price):
    p = PROG.loc[(system, family)]
    return round(p["amount"] * list_price, 2) if p["basis"] == "pct_list" else float(p["amount"])


def new_claim(car, system, family, dealer, claim_date, amount, label, leak, dup_of, detail=pd.NA):
    return {"system": system, "car_id": car.car_id, "dealer": dealer, "vin": car.vin,
            "order_no": car.order_no if system == "B" else pd.NA, "programme": PROG.loc[(system, family), "code"],
            "family": family, "event_date": car.registration_date if system == "A" else car.order_date,
            "claim_date": claim_date, "amount_net": amount, "label": label, "leak_eur": leak, "dup_of": dup_of,
            "detail": detail}


def draw_in(rng, opens, closes):
    return opens + int(rng.integers(0, (closes - opens).days + 1)) * DAY


def windows(c, master):
    """Each claim's filing window, from the vehicle record as recorded."""
    m = master.set_index("car_id")
    opens = pd.Series(pd.NaT, index=c.index, dtype="datetime64[ns]")
    closes = opens.copy()
    for (system, family), g in c.groupby(["system", "family"]):
        o, cl = claim_window(system, family, g["car_id"].map(m["order_date"]),
                             g["car_id"].map(m["registration_date"]), quarter_end(g["event_date"]))
        opens[g.index], closes[g.index] = o, cl
    return opens, closes


def pick(rng, pool, rate, step, log):
    chosen = pool[rng.random(len(pool)) < rate]
    log.append({"step": step, "pool": len(pool), "selected": len(chosen), "rate": rate})
    return chosen


def append(c, rows):
    new = pd.DataFrame(rows)
    start = c["row"].max() + 1
    new["row"] = np.arange(start, start + len(new))
    c = pd.concat([c, new], ignore_index=True)
    return c.astype({"car_id": "Int64", "dup_of": "Int64"})


def gaming_candidates(a):
    """A dealer-quarters that missed target by a few cars and could pull enough cars from early next quarter,
    without changing whether next quarter meets its own target. Excludes a quarter whose next quarter is also a
    candidate, so no two games touch the same cars."""
    years = PROG.loc[("A", "volume"), "years"]
    counts, target = quarter_counts_targets(a, a["registration_date"], years)
    q = counts.rename("n").reset_index()
    q.columns = ["dealer_id", "quarter", "n"]
    q["target"] = q["dealer_id"].map(target)
    n_of = counts.to_dict()
    q["n_next"] = [n_of.get((d, p + 1), 0) for d, p in zip(q["dealer_id"], q["quarter"])]
    # a car can be pulled if it was due early next quarter, was ordered before the new date, and is not a conquest
    # sale (the 2022-only conquest programme would lose its eligibility if a car moved into 2021)
    period = a["registration_date"].dt.to_period("Q")
    start = period.dt.start_time
    pullable = a[((a["registration_date"] - start).dt.days < setting("gaming_pull_days"))
                 & (a["order_date"] < start - 3 * DAY) & a["buyer"].ne("conquest")]
    early = pullable.groupby([pullable["dealer_id"], period[pullable.index]]).size().to_dict()
    q["early_next"] = [early.get((d, p + 1), 0) for d, p in zip(q["dealer_id"], q["quarter"])]
    q["short"] = q["target"] - q["n"]
    cand = q[q["short"].between(1, setting("gaming_max_shortfall")) & q["quarter"].lt(pd.Period(f"{max(years)}Q4"))
             & q["early_next"].ge(q["short"])
             & ((q["n_next"] - q["short"] >= q["target"]) | (q["n_next"] < q["target"]))]
    keys = set(zip(cand["dealer_id"], cand["quarter"]))
    cand = cand[[(d, p + 1) not in keys for d, p in zip(cand["dealer_id"], cand["quarter"])]]
    return cand.reset_index(drop=True), pullable, period


def game(sales, c, D, rng, log):
    master = sales.copy()
    a = master[master["system"] == "A"]
    cand, pullable, period = gaming_candidates(a)
    chosen = cand.loc[pick(rng, cand.index, setting("rate_quarter_end_gaming"), "quarter_end_gaming", log)]
    moved = []
    for r in chosen.itertuples():
        ids = pullable.loc[pullable["dealer_id"].eq(r.dealer_id) & period[pullable.index].eq(r.quarter + 1),
                           "car_id"].to_numpy()
        qend = r.quarter.end_time.normalize()
        for car_id in sorted(rng.choice(ids, int(r.short), replace=False)):
            moved.append((car_id, r.dealer_id, str(r.quarter), qend - int(rng.integers(0, 3)) * DAY))
    gamed = pd.DataFrame(moved, columns=["car_id", "dealer_id", "gamed_quarter", "recorded_registration_date"])
    gamed["true_registration_date"] = gamed["car_id"].map(sales.set_index("car_id")["registration_date"])
    new_reg = master["car_id"].map(gamed.set_index("car_id")["recorded_registration_date"])
    master["registration_date"] = new_reg.fillna(master["registration_date"])

    # the pulled cars: their volume claims next quarter go (the gamed quarter's claims replace them); their other
    # claims follow the new registration date and stay inside the window
    mv = c["car_id"].isin(gamed["car_id"]) & c["system"].eq("A")
    c = c[~(mv & c["family"].eq("volume"))].copy()
    mv = c["car_id"].isin(gamed["car_id"]) & c["system"].eq("A")
    reg = c.loc[mv, "car_id"].map(master.set_index("car_id")["registration_date"])
    c.loc[mv, "event_date"] = reg
    c.loc[mv, "claim_date"] = np.minimum(c.loc[mv, "claim_date"], reg + CLAIM_DEADLINE_DAYS["A"] * DAY)
    c.loc[mv, "label"] = "legit_gamed_car"

    rows = []
    a_rec = master[master["system"] == "A"]
    a_period = a_rec["registration_date"].dt.to_period("Q")
    for r in chosen.itertuples():
        qend = r.quarter.end_time.normalize()
        for car in a_rec[a_rec["dealer_id"].eq(r.dealer_id) & a_period.eq(r.quarter)].itertuples():
            amount = amount_for("A", "volume", car.list_price_eur)
            rows.append(new_claim(car, "A", "volume", D.at[r.dealer_id, "code_a"],
                                  draw_in(rng, qend, qend + CLAIM_DEADLINE_DAYS["A"] * DAY), amount,
                                  "quarter_end_gaming", amount, pd.NA, str(r.quarter)))
    return master, append(c, rows), gamed, chosen


def keeper_events(master, gamed, seed=KEEPER_SEED):
    """The keeper changes behind the register (part 7b). A car pulled forward by gaming was registered at quarter end
    in the dealer's name and passed to its buyer on the date it was really due. Other cars change keeper within
    `keeper_quick_days` of registration at the real base rate, plus the real quarter-end lift, all of it legitimate.
    Returns the random stream (for `register_keepers` to go on drawing), each car's first keeper change and whether it
    was a quick one. `sources.py` reads the same events for the first-keeper source."""
    rng = np.random.default_rng(seed)
    reg, n, days = master["registration_date"], len(master), setting("keeper_quick_days")
    last3 = (quarter_end(reg) - reg).dt.days < 3
    rate = np.where(last3, setting("keeper_quick_base") + setting("keeper_quick_qend_lift"), setting("keeper_quick_base"))
    quick = rng.random(n) < rate
    keeper = reg + pd.to_timedelta(np.where(quick, rng.integers(1, days + 1, n), 0), unit="D")
    true = pd.to_datetime(master["car_id"].map(dict(zip(gamed["car_id"], gamed["true_registration_date"]))))
    return rng, keeper.where(true.isna(), true), quick


def register_keepers(master, gamed, seed=KEEPER_SEED):
    """Each car's current-keeper date as the national register would show it (part 7b), from `keeper_events`. A later
    keeper change hides an early one: the register read within a quarter hides a measured share, and read years later
    a much larger measured share."""
    rng, keeper, _ = keeper_events(master, gamed, seed)
    reg, n, days = master["registration_date"], len(master), setting("keeper_quick_days")
    out = {"car_id": master["car_id"].to_numpy()}
    for col, hidden, latest in (("keeper_date_prompt", "keeper_hidden_prompt", 90),
                                ("keeper_date_late", "keeper_hidden_late", 1800)):
        later = rng.random(n) < setting(hidden)
        moved = reg + pd.to_timedelta(rng.integers(days + 1, latest + 1, n), unit="D")
        out[col] = keeper.where(~later, moved).to_numpy()
    return pd.DataFrame(out)


def mistype(vin, rng):
    kinds = ["lookalike", "random", "transpose"]
    while True:
        v, kind = list(vin), kinds[rng.choice(3, p=setting("typo_mix"))]
        for _ in range(2 if rng.random() < setting("typo_two_chars_share") else 1):
            if kind == "transpose":
                i = int(rng.integers(0, 16))
                v[i], v[i + 1] = v[i + 1], v[i]
            else:
                i = int(rng.integers(0, 17))
                options = (CONFUSABLE.get(v[i], "") if kind == "lookalike" else "") or ALPHABET.replace(v[i], "")
                v[i] = options[int(rng.integers(0, len(options)))]
        out = "".join(v)
        if out != vin:  # it may land on another real VIN, as real typos do
            return out, kind


def mistype_order(order, rng):
    """One digit of an 'OR' + 8-digit order number replaced, or two adjacent digits swapped."""
    while True:
        d = list(order[2:])
        i = int(rng.integers(0, 7))
        if rng.random() < 0.3:
            d[i], d[i + 1] = d[i + 1], d[i]
        else:
            d[i] = str(int(rng.integers(0, 10)))
        out = "OR" + "".join(d)
        if out != order:
            return out


def inject(dealers, sales, clean, seed=SEED):
    rng = np.random.default_rng(seed)
    log = []
    D = dealers.set_index("dealer_id")
    c = clean.drop(columns="claim_id").astype({"car_id": "Int64"})
    c["label"], c["leak_eur"], c["detail"] = "clean", 0.0, pd.NA
    c["dup_of"] = pd.array([pd.NA] * len(c), dtype="Int64")
    c["row"] = np.arange(len(c))

    master, c, gamed, chosen = game(sales, c, D, rng, log)
    cars = {r.car_id: r for r in master.itertuples(index=False)}
    systems_of = master.set_index("car_id")["dealer_id"].map(D["systems"])

    # late claims
    sel = pick(rng, c.index[c["label"].eq("clean")], setting("rate_late_claim"), "late_claim", log)
    _, closes = windows(c.loc[sel], master)
    c.loc[sel, "claim_date"] = closes + pd.to_timedelta(rng.integers(1, 91, len(sel)), unit="D")
    c.loc[sel, "label"], c.loc[sel, "leak_eur"] = "late_claim", c.loc[sel, "amount_net"]

    # illegal stacks: retail on a fleet car (only cars ordered in the programme years, so B's rule allows it)
    pool = c.index[c["label"].eq("clean") & c["family"].eq("fleet")
                   & c["car_id"].map(master.set_index("car_id")["order_date"]).ge(pd.Timestamp("2021-01-01"))]
    rows = []
    for i in pick(rng, pool, setting("rate_illegal_stack"), "illegal_stack", log):
        car, system = cars[c.at[i, "car_id"]], c.at[i, "system"]
        split = systems_of[car.car_id] == "AB" and rng.random() < setting("stack_other_system_share")
        system = OTHER[system] if split else system
        o, cl = claim_window(system, "retail", car.order_date, car.registration_date, None)
        amount = amount_for(system, "retail", car.list_price_eur)
        rows.append(new_claim(car, system, "retail", D.at[car.dealer_id, "code_a" if system == "A" else "code_b"],
                              draw_in(rng, o, cl), amount, "illegal_stack", amount, c.at[i, "row"],
                              "other_system" if split else "same_system"))
    c = append(c, rows)

    # cross-system duplicates of the group programme, by a dealer on both systems
    years = PROG.loc[("A", "conquest"), "years"]
    pool = []
    for i in c.index[c["label"].eq("clean") & c["family"].eq("conquest")]:
        car, other = cars[c.at[i, "car_id"]], OTHER[c.at[i, "system"]]
        event = car.registration_date if other == "A" else car.order_date
        if systems_of[car.car_id] == "AB" and event.year in years:
            pool.append(i)
    rows = []
    for i in pick(rng, pd.Index(pool), setting("rate_cross_system_duplicate"), "cross_system_duplicate", log):
        car, system = cars[c.at[i, "car_id"]], OTHER[c.at[i, "system"]]
        o, cl = claim_window(system, "conquest", car.order_date, car.registration_date, None)
        rows.append(new_claim(car, system, "conquest", D.at[car.dealer_id, "code_a" if system == "A" else "code_b"],
                              draw_in(rng, o, cl), c.at[i, "amount_net"], "cross_system_duplicate",
                              c.at[i, "amount_net"], c.at[i, "row"]))
    c = append(c, rows)

    # VIN typos: the same claim filed again under a mistyped VIN, inside its window
    sel = pick(rng, c.index[c["label"].eq("clean")], setting("rate_vin_typo"), "vin_typo", log)
    _, closes = windows(c.loc[sel], master)
    rows = []
    for i in sel:
        r = c.loc[i].to_dict()
        vin, kind = mistype(r["vin"], rng)
        date = min(r["claim_date"] + int(rng.integers(1, 31)) * DAY, closes[i])
        r.update(vin=vin, claim_date=date, label="vin_typo", leak_eur=r["amount_net"], dup_of=r["row"], detail=kind)
        rows.append(r)
    c = append(c, rows)

    # phantom order-only claims in B: an order that was never delivered. It looks like a real order at that dealer
    # (the list price of a car the dealer did sell, a date inside the programme) but copies no existing claim.
    orders = set(master["order_no"])
    b_cars = master[master["system"].eq("B")].groupby("dealer_id")["car_id"].agg(list).to_dict()
    rows = []
    pool = c.index[c["label"].eq("clean") & c["system"].eq("B") & c["family"].ne("volume")]
    for i in pick(rng, pool, setting("rate_pre_vin_claim"), "pre_vin_claim", log):
        r = c.loc[i].to_dict()
        dealer_cars = b_cars[cars[r["car_id"]].dealer_id]
        donor = cars[dealer_cars[int(rng.integers(0, len(dealer_cars)))]]
        years = PROG.loc[("B", r["family"]), "years"]
        first, last = pd.Timestamp(f"{min(years)}-01-01"), pd.Timestamp(f"{max(years)}-12-31")
        event = first + int(rng.integers(0, (last - first).days + 1)) * DAY
        amount = amount_for("B", r["family"], donor.list_price_eur)
        while (order := f"OR{int(rng.integers(0, 10**8)):08d}") in orders:
            pass
        orders.add(order)
        r.update(car_id=pd.NA, vin=pd.NA, order_no=order, event_date=event, amount_net=amount,
                 claim_date=event + int(rng.integers(0, 31)) * DAY, label="pre_vin_claim", leak_eur=amount,
                 dup_of=pd.NA)
        rows.append(r)
    c = append(c, rows)

    # legitimate: filed with a wrong amount, cancelled by a credit note, filed again right, all inside the window
    clean_now = c[c["label"].eq("clean")]
    _, closes = windows(clean_now, master)
    pool = clean_now.index[(closes - clean_now["claim_date"]).dt.days >= 20]
    rows = []
    for i in pick(rng, pool, setting("rate_legit_reversal"), "legit_reversal", log):
        r = c.loc[i].to_dict()
        wrong = round(r["amount_net"] * rng.uniform(0.8, 1.2), 2)
        wrong = wrong if wrong != r["amount_net"] else wrong + 1.0
        credit = r["claim_date"] + int(rng.integers(1, 11)) * DAY
        rows.append({**r, "amount_net": -wrong, "claim_date": credit, "label": "legit_reversal", "dup_of": r["row"],
                     "detail": "credit_note"})
        rows.append({**r, "claim_date": credit + int(rng.integers(0, 10)) * DAY, "label": "legit_reversal",
                     "dup_of": r["row"], "detail": "refiled"})
        c.at[i, "amount_net"], c.at[i, "label"], c.at[i, "detail"] = wrong, "legit_reversal", "original"
    c = append(c, rows)

    # legitimate: a B claim with the VIN left empty, though its order became a car
    sel = pick(rng, c.index[c["label"].eq("clean") & c["system"].eq("B")], setting("rate_legit_vin_blank"),
               "legit_vin_blank", log)
    c.loc[sel, "vin"], c.loc[sel, "label"] = pd.NA, "legit_vin_blank"

    # legitimate: a claim that is not a duplicate, its key mistyped on entry. The VIN if it has one, else (a B
    # claim with no VIN) the order number. Without these, "unknown key" would mean "leak" for free.
    pool = c.index[c["label"].isin(["clean", "legit_vin_blank"])]
    for i in pick(rng, pool, setting("rate_legit_key_typo"), "legit_key_typo", log):
        if pd.notna(c.at[i, "vin"]):
            c.at[i, "vin"], kind = mistype(c.at[i, "vin"], rng)
            c.at[i, "detail"] = "vin_" + kind
        else:
            c.at[i, "order_no"], c.at[i, "detail"] = mistype_order(c.at[i, "order_no"], rng), "order"
        c.at[i, "label"] = "legit_key_typo"

    # renumber every claim in claim-date order, random tie-break
    c = (c.assign(tiebreak=rng.random(len(c))).sort_values(["system", "claim_date", "tiebreak"], ignore_index=True)
          .drop(columns="tiebreak"))
    n = c.groupby("system").cumcount() + 1
    c.insert(0, "claim_id", np.where(c["system"] == "A", "A" + n.map("{:08d}".format), n.map("{:07d}".format)))
    c["dup_of"] = c["dup_of"].map(c.set_index("row")["claim_id"])
    return master, c.drop(columns="row"), gamed, chosen, pd.DataFrame(log)


def same(a, b):
    return ((a == b).fillna(False) | (a.isna() & b.isna())).all()


def check(sales, clean, master, c, gamed, chosen, log):
    labels = {"clean", *LEAKS, *LEGIT_LABELS}
    assert c["claim_id"].is_unique and set(c["label"]) <= labels, set(c["label"]) - labels
    leak = c["label"].isin(LEAKS)
    assert (c["leak_eur"] > 0).eq(leak).all(), "leak euros must be positive exactly on leak rows"
    assert c["dup_of"].dropna().isin(c["claim_id"]).all()
    for system, g in c.groupby("system"):
        assert g.sort_values("claim_id")["claim_date"].is_monotonic_increasing, "ids must follow claim dates"

    # realised rates within 3 standard errors of the set rates
    for r in log.itertuples():
        se = np.sqrt(r.rate * (1 - r.rate) / r.pool)
        assert abs(r.selected / r.pool - r.rate) <= 3 * se, r

    # clean rows are exactly the clean world's rows
    k = ["system", "car_id", "programme"]
    cl = c[c["label"].eq("clean")].merge(clean.astype({"car_id": "Int64"}), on=k, suffixes=("", "_0"),
                                         validate="one_to_one")
    assert len(cl) == c["label"].eq("clean").sum()
    for col in ["dealer", "vin", "order_no", "family", "event_date", "claim_date", "amount_net"]:
        assert same(cl[col], cl[col + "_0"]), col

    # each leak is what it says
    src = c.set_index("claim_id")
    t = c[c["label"].eq("vin_typo")]
    assert (t["vin"] != t["dup_of"].map(src["vin"])).all()
    p = c[c["label"].eq("pre_vin_claim")]
    assert p["vin"].isna().all() and p["car_id"].isna().all() and not p["order_no"].isin(master["order_no"]).any()
    lt = c[c["label"].eq("late_claim")]
    assert (lt["claim_date"] > windows(lt, master)[1]).all()
    st = c[c["label"].eq("illegal_stack")]
    pairs = set(zip(st["dup_of"].map(src["family"]), st["family"]))
    assert all(pr in EXCLUDES or pr[::-1] in EXCLUDES for pr in pairs), pairs
    x = c[c["label"].eq("cross_system_duplicate")]
    cw = {(a, ca): (b, cb) for a, ca, b, cb in CROSSWALK}
    cw.update({v: k for k, v in cw.items()})
    orig = list(zip(x["dup_of"].map(src["system"]), x["dup_of"].map(src["programme"])))
    assert [cw[o] for o in orig] == list(zip(x["system"], x["programme"]))
    assert (x["car_id"] == x["dup_of"].map(src["car_id"])).all()

    # gaming: each chosen quarter missed target before and meets it after; next quarter's status is unchanged
    years = PROG.loc[("A", "volume"), "years"]
    before, target = quarter_counts_targets(*(lambda a: (a, a["registration_date"], years))(
        sales[sales["system"] == "A"]))
    after, _ = quarter_counts_targets(*(lambda a: (a, a["registration_date"], years))(
        master[master["system"] == "A"]))
    for r in chosen.itertuples():
        t = target[r.dealer_id]
        assert before[(r.dealer_id, r.quarter)] < t <= after[(r.dealer_id, r.quarter)]
        nb, na = before.get((r.dealer_id, r.quarter + 1), 0), after.get((r.dealer_id, r.quarter + 1), 0)
        assert (nb >= t) == (na >= t)
    assert (gamed["recorded_registration_date"] < gamed["true_registration_date"]).all()


def main():
    dealers = pd.read_parquet(SYN / "x1_dealers.parquet")
    sales = pd.read_parquet(SYN / "x1_sales.parquet")
    clean = pd.read_parquet(SYN / "x1_claims_clean.parquet")
    out = inject(dealers, sales, clean)
    again = inject(dealers, sales, clean)
    assert all(a.equals(b) for a, b in zip(out, again)), "not deterministic"
    master, c, gamed, chosen, log = out
    check(sales, clean, master, c, gamed, chosen, log)
    print("all injection checks pass; two builds are identical\n")

    log["realised"] = (log["selected"] / log["pool"]).round(4)
    print("rates (each a share of its own pool):")
    print(log.to_string(index=False))
    paid = c.loc[c["amount_net"] > 0, "amount_net"].sum()
    t = c.groupby("label").agg(claims=("claim_id", "size"), leak_eur=("leak_eur", "sum"))
    t["leak_share_of_paid"] = (t["leak_eur"] / paid).round(4)
    t["leak_eur"] = t["leak_eur"].round(0)
    print(f"\nclaims by label (synthetic euros; {len(c):,} claims, EUR {paid / 1e6:.1f}m paid):")
    print(t.sort_values("claims", ascending=False).to_string())
    print(f"\ngamed dealer-quarters: {len(chosen)}; cars pulled forward: {len(gamed)}")
    typo = c["label"].isin(["vin_typo", "legit_key_typo"]) & c["vin"].notna()
    hit = typo & c["vin"].isin(master["vin"])
    print(f"mistyped VINs that landed on another real car: {hit.sum()} of {typo.sum()}")

    for system in "AB":
        system_table(c[c["system"] == system], system).to_parquet(SYN / f"x1_system_{system.lower()}.parquet",
                                                                  index=False)
    master.to_parquet(SYN / "x1_master.parquet", index=False)
    c[["claim_id", "system", "car_id", "label", "leak_eur", "dup_of", "detail"]].to_parquet(
        SYN / "x1_truth.parquet", index=False)
    gamed.to_parquet(SYN / "x1_truth_cars.parquet", index=False)
    keepers = register_keepers(master, gamed)
    assert keepers.equals(register_keepers(master, gamed)), "keeper source not deterministic"
    keepers.to_parquet(SYN / "x1_register_keepers.parquet", index=False)
    print("wrote x1_system_a, x1_system_b, x1_master, x1_truth, x1_truth_cars, x1_register_keepers")


if __name__ == "__main__":
    main()
