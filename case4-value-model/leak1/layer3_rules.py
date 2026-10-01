"""X1 part 7, layer 3: the rules engine. The leaks that keys cannot see: eligibility, deadlines, stacking and gaming.

Reads only what a detector may read: the claims, the vehicle record as recorded, the rulebook in `spec.py`, and the
car each claim was linked to by layers 1 and 2 (`x1_flags_layer2`). Every rule is checked against the vehicle
record, the trusted source, not against the dates keyed on the claim.

Rules run on live claims: linked to a car, positive, not cancelled by a credit note, and not already flagged as a
duplicate. A claim takes the first rule it breaks, in this order:
  wrong_system        filed in a different system from the one that serves the car's brand
  ineligible_buyer    the car's buyer does not qualify for the programme (retail on a fleet car, for example)
  conquest_unverified a conquest claim whose car has no register-verified non-group trade-in
  outside_years       the car's sale event (registration in A, order in B) falls outside the programme's years
  early_claim         filed before its window opens (`spec.claim_window`)
  late_claim          filed after its window closes
  wrong_amount        the amount differs from the rulebook's: a share of the car's list price, or the flat amount
  volume_not_earned   a volume bonus for a dealer-quarter that did not reach its published target
  forbidden_stack     two families that exclude each other on one car, across both systems (the later claim)
  gaming_suspect      a statistical flag, not a hard rule: a dealer-quarter that met its target only thanks to an
                      unusual bump in last-week sale events (registrations in A, signed orders in B). All its volume
                      claims are held for review.
  self_registration_suspect  part 7b, also held for review: an A dealer-quarter that met its target only on
                      registration dates, and misses it once each car counts in the quarter the national register
                      shows its keeper took it on (a change within 30 days). Read from `x1_register_keepers`, when the
                      world has it.
  contract_contradicted  part 9, held for review: the captive finance JV's contract linked to the car contradicts the
                      programme's buyer (a private finance contract under a fleet claim, a fleet lease under a retail
                      or conquest claim). The contracts are linked with part 9's keyed Bloom-filter encodings (M2), so
                      no clear VIN crosses the JV boundary. Strong evidence, but a wrong link can cause it, so a
                      reviewer confirms the link before payment is withheld.
  fleet_unverified    part 9, held for review: a fleet claim whose car no JV fleet lease links to. A review queue, never
                      grounds to withhold payment automatically: independent lessors and failed links land here too.
  first_keeper_suspect  after round 3, held for review: an A dealer-quarter that meets its target on registration dates
                      but not once each car first registered in the dealer's own name counts when a customer took it,
                      however long after (the register's first keeper, `x1_register_first_keeper`). The complete version
                      of the keeper check: no 30-day window to wait out, and no later change to hide the first.
  order_change_suspect  after round 3, held for review: a B dealer-quarter that meets its target on signed orders but not
                      once each order counts when its final customer took it over (the order system's log of customer
                      changes, `x1_oem_order_log`).

The gaming rule was fixed before any result. "Last week" means the last 7 days of the quarter. "Unusual" means above
the dealer's own average last week. The generator pulls cars into the last 3 days; the detector deliberately uses
7, so it is not tuned to the generator.

Self-check: the clean world obeys the rulebook by construction, so no hard rule may flag a legitimate claim. Only
the gaming rule may raise false alarms.

**Changed after the blind red team (25 September), as post-hoc fixes.** The red-team world confirms they work as
built, but it cannot test them fairly; a second, fresh blind round can.
  - Targets are read from the OEM's published table (`x1_targets`). They were recomputed from the vehicle record, so
    a dealer who moved cars in the record also moved the targets.
  - The gaming rule also runs on B, on B's own sale event (signed orders), with the same 7-day window.
  - New hard rule `conquest_unverified`: a conquest claim needs a trade-in whose make, per the national register
    (`x1_register_tradeins`), is outside the group. The dealer-reported buyer type is no longer enough.
**Added after the second red-team round, also post hoc:** `wrong_amount` recomputes every live claim's amount from
the rulebook. Credit notes and the claims they cancel are netted out first, so honest corrections pass. A tolerance
of EUR 0.02 covers rounding in B's gross-to-net conversion. In reality, percentage programmes are paid on the
invoice price, so this rule needs the invoice as its independent source; this world's rulebook uses list price.
**The design gaps, closed after both rounds (post hoc):** the rules no longer read the selling dealer or the order
date from the vehicle record the dealer reports. `trusted_record` takes both from the OEM's own record
(`x1_oem_record`: the wholesale invoice after documented transfers, and the order system's timestamp). Volume counts,
targets met, gaming checks, B's sale event and claim windows all follow. Conquest is checked against the register.
**The fleet check, wired in on 25 September (second session):** buyer type is checked against the JV's contracts
(`x1_finance_contracts`, linked privately by `linkage.py`'s M2) as two review rules, so the dealer-reported buyer type
is no longer the only source. Both are review rules, not hard rules: part 9 found one legitimate fleet claim in our
world contradicted by a wrong link, and a few hundred left unverified by links that failed.
**After round 3 (post hoc, before round 4):** four sources the dealer does not control (`sources.py`) close the gaps
round 3 used. `trusted_record` gives A's volume credit to the dealer that held the car at registration (a dated
transfer after it is unwound) and B's to the dealer that signed the order. `conquest_unverified` also needs the
trade-in in the buyer's name for the rulebook's minimum, by the register's keeper date. Two review rules count cars
when the real customer took them. Each runs only when its source file exists.

Output: data/synthetic/x1_flags_layer3.parquet (the combined flags of layers 1, 2 and 3)
Usage: .venv/bin/python leak1/layer3_rules.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from generate import SYN, quarter_end, setting  # noqa: E402
from layer1_keys import credit_pairs, load, with_family  # noqa: E402
from linkage import THRESHOLD as LINK_THRESHOLD, best_links, clk, encode  # noqa: E402
from score import score, show  # noqa: E402
from spec import BUYERS_OF, EXCLUDES, GROUP_MAKES, LEAKS, PROGRAMMES, SALE_EVENT, claim_window  # noqa: E402

HARD = ["wrong_system", "ineligible_buyer", "conquest_unverified", "outside_years", "early_claim", "late_claim",
        "wrong_amount", "volume_not_earned", "forbidden_stack"]
AMOUNT_TOLERANCE = 0.02  # euros: covers rounding in B's gross-to-net conversion
LAST_WEEK_DAYS = 7
KEEPER_READ = "keeper_date_prompt"  # part 7b: the ledger reads the register within a quarter of the event
REVIEW = ["gaming_suspect", "self_registration_suspect",  # held for a reviewer, not hard rules
          "contract_contradicted", "fleet_unverified", "first_keeper_suspect", "order_change_suspect"]
PROG = PROGRAMMES.set_index(["system", "code"])


def trusted_record(master, oem, prices=None, transfers=None, orders=None):
    """The vehicle record with the fields the OEM holds taken from the OEM, not from what the dealer reported: the
    selling dealer (wholesale invoice after documented transfers), the order date (the order system's timestamp) and,
    when the world has the OEM price list (added after round 3, post hoc), the list price amounts are computed on.
    With the dated transfer log, an A car's dealer is the one that held it at registration: transfers after that are
    unwound. With the order log, a B car's dealer is the one that signed the order."""
    o = oem.set_index("car_id")
    assert master["car_id"].isin(o.index).all(), "a car without an OEM record"
    t = master.copy()
    t["dealer_id"] = t["car_id"].map(o["dealer_id"]).astype(master["dealer_id"].dtype)
    t["order_date"] = t["car_id"].map(o["order_date"])
    if prices is not None:
        t["list_price_eur"] = t["car_id"].map(prices.set_index("car_id")["list_price_eur"])
        assert t["list_price_eur"].notna().all(), "a car without an OEM price"
    if transfers is not None:
        late = transfers.merge(t[["car_id", "system", "registration_date"]], on="car_id")
        late = late[late["system"].eq("A") & (late["transfer_date"] > late["registration_date"])]
        first = late.sort_values(["car_id", "transfer_date"]).drop_duplicates("car_id").set_index("car_id")
        hit = t["car_id"].isin(first.index)
        t.loc[hit, "dealer_id"] = t.loc[hit, "car_id"].map(first["from_dealer"]).astype(t["dealer_id"].dtype)
    if orders is not None:
        signed = orders[orders["event"].eq("signed")].set_index("car_id")["dealer_id"]
        b = t["system"].eq("B") & t["car_id"].isin(signed.index)
        t.loc[b, "dealer_id"] = t.loc[b, "car_id"].map(signed).astype(t["dealer_id"].dtype)
    return t


def contract_types(master, contracts):
    """Part 9's private linkage (M2: keyed Bloom-filter encodings compared by Dice, one to one, threshold fixed in
    advance): the type of the JV contract linked to each car, for the cars a contract links to."""
    cars = master[["car_id", "vin", "registration_date"]]
    linked, _, _ = best_links(cars, contracts, encode(cars["vin"], clk), encode(contracts["vin"], clk),
                              LINK_THRESHOLD)
    types = pd.Series(contracts["contract_type"].to_numpy(), index=linked)
    return types[types.index >= 0]


def live_claims(claims, links, master):
    """Linked, positive, not netted by a credit note, not a flagged duplicate; with the car's record attached."""
    c = with_family(claims).merge(links[["claim_id", "reason", "car_id"]], on="claim_id", validate="one_to_one")
    linked = c[c["car_id"].notna()]
    pair, _ = credit_pairs(linked)
    live = linked[(linked["amount_net"] > 0) & ~linked.index.isin(pair["index_pos"])
                  & linked["reason"].fillna("").ne("duplicate")].copy()
    car = master.set_index("car_id")[["system", "buyer", "dealer_id", "registration_date", "order_date"]]
    live = live.join(car.rename(columns={"system": "car_system"}), on=live["car_id"].astype("int64"))
    live["car_event"] = np.where(live["system"].eq("A"), live["registration_date"], live["order_date"])
    return live


def volume_counts(master, system):
    """Cars per dealer and quarter of the system's own sale event, inside its volume programme's years, as recorded."""
    s = master[master["system"] == system]
    event = s[SALE_EVENT[system]]
    inside = event.dt.year.isin(PROGRAMMES.loc[PROGRAMMES["system"].eq(system) & PROGRAMMES["family"].eq("volume"),
                                               "years"].iloc[0])
    return s[inside].groupby([s.loc[inside, "dealer_id"], event[inside].dt.to_period("Q")]).size()


def gaming_suspects(master, targets, system):
    """Dealer-quarters that met their published target only thanks to an unusual bump in last-week sale events:
    without the events above the dealer's own average last week, the quarter would have missed."""
    s = master[master["system"] == system]
    event = s[SALE_EVENT[system]]
    counts = volume_counts(master, system)
    target = targets[targets["system"] == system].set_index("dealer_id")["target"]
    q = event.dt.to_period("Q")
    in_last_week = (q.dt.end_time.dt.normalize() - event).dt.days < LAST_WEEK_DAYS
    last = s[in_last_week].groupby([s.loc[in_last_week, "dealer_id"], q[in_last_week]]).size()
    last = last.reindex(counts.index, fill_value=0)
    excess = last - last.groupby(level=0).transform("mean")
    margin = counts - target.reindex(counts.index.get_level_values(0)).to_numpy()
    suspect = (margin >= 0) & (excess > 0) & (margin < excess)
    return set(suspect.index[suspect])


def self_registration_suspects(master, targets, keepers, column=KEEPER_READ):
    """Part 7b, a check built on the mechanism rather than on timing statistics. A dealer that registers cars in its
    own name to reach a target leaves a trace in the national register: the car's keeper changes within weeks, when
    it reaches its real buyer. So each A car counts toward its dealer's volume in the quarter its keeper took it on
    when that came within `keeper_quick_days` of registration, and in its registration quarter otherwise. A
    dealer-quarter that meets its published target on registration dates but not on those dates is a suspect."""
    a = master[master["system"] == "A"]
    keeper = a["car_id"].map(keepers.set_index("car_id")[column])
    gap = (keeper - a["registration_date"]).dt.days
    effective = a["registration_date"].where(~gap.between(1, setting("keeper_quick_days")), keeper)
    years = PROGRAMMES.loc[PROGRAMMES["system"].eq("A") & PROGRAMMES["family"].eq("volume"), "years"].iloc[0]
    target = targets[targets["system"] == "A"].set_index("dealer_id")["target"]
    by_reg = volume_counts(master, "A")
    inside = effective.dt.year.isin(years)
    by_keeper = a[inside].groupby([a.loc[inside, "dealer_id"], effective[inside].dt.to_period("Q")]).size()
    by_keeper = by_keeper.reindex(by_reg.index, fill_value=0)
    t = target.reindex(by_reg.index.get_level_values(0)).to_numpy()
    suspect = (by_reg >= t) & (by_keeper < t)
    return set(suspect.index[suspect])


def customer_date_suspects(master, targets, system, effective):
    """Dealer-quarters that meet their published target on the recorded sale events but not when each car counts on
    `effective`, the day its real customer took it (aligned with `master`)."""
    s = master[master["system"] == system]
    eff = pd.to_datetime(effective[s.index])
    years = PROGRAMMES.loc[PROGRAMMES["system"].eq(system) & PROGRAMMES["family"].eq("volume"), "years"].iloc[0]
    target = targets[targets["system"] == system].set_index("dealer_id")["target"]
    by_event = volume_counts(master, system)
    inside = eff.dt.year.isin(years)
    by_customer = s[inside].groupby([s.loc[inside, "dealer_id"], eff[inside].dt.to_period("Q")]).size()
    by_customer = by_customer.reindex(by_event.index, fill_value=0)
    t = target.reindex(by_event.index.get_level_values(0)).to_numpy()
    suspect = (by_event >= t) & (by_customer < t)
    return set(suspect.index[suspect])


def rules(live, master, targets, tradeins, keepers=None, contracts=None, first_keepers=None, orders=None,
          tradein_keepers=None):
    p = PROG.loc[list(zip(live["system"], live["programme"]))]
    broken = pd.DataFrame(False, index=live.index, columns=HARD + REVIEW)
    broken["wrong_system"] = live["system"].ne(live["car_system"])
    broken["ineligible_buyer"] = [b not in BUYERS_OF[pb] for b, pb in zip(live["buyer"], p["buyer"])]
    tradein = live["car_id"].astype("int64").map(tradeins.set_index("car_id")["tradein_make"])
    unverified = tradein.isna() | tradein.isin(GROUP_MAKES)
    if tradein_keepers is not None:  # after round 3: held long enough, by the register's keeper date
        since = live["car_id"].astype("int64").map(tradein_keepers.set_index("car_id")["tradein_keeper_since"])
        held = (pd.to_datetime(live["car_event"]) - since).dt.days
        unverified |= ~held.ge(setting("conquest_min_holding_days"))
    broken["conquest_unverified"] = (live["family"].eq("conquest") & unverified).to_numpy()
    broken["outside_years"] = [e.year not in y for e, y in zip(live["car_event"], p["years"])]
    for (system, family), g in live.groupby(["system", "family"]):
        opens, closes = claim_window(system, family, g["order_date"], g["registration_date"],
                                     quarter_end(g["car_event"]))
        broken.loc[g.index, "early_claim"] = g["claim_date"] < opens
        broken.loc[g.index, "late_claim"] = g["claim_date"] > closes
    price = live["car_id"].astype("int64").map(master.set_index("car_id")["list_price_eur"]).to_numpy()
    expected = np.where(p["basis"].eq("pct_list").to_numpy(), np.round(p["amount"].to_numpy() * price, 2),
                        p["amount"].to_numpy())
    broken["wrong_amount"] = np.abs(live["amount_net"].to_numpy() - expected) > AMOUNT_TOLERANCE

    # volume bonus earned, and gaming suspects: the car's dealer and the quarter of its sale event, as recorded,
    # against the published target
    suspects = {}
    for system in "AB":
        counts = volume_counts(master, system)
        target = targets[targets["system"] == system].set_index("dealer_id")["target"]
        hit = counts >= target.reindex(counts.index.get_level_values(0)).to_numpy()
        suspects[system] = gaming_suspects(master, targets, system)
        v = live["system"].eq(system) & live["family"].eq("volume")
        key = list(zip(live.loc[v, "dealer_id"], pd.to_datetime(live.loc[v, "car_event"]).dt.to_period("Q")))
        broken.loc[v, "volume_not_earned"] = [not hit.get(k, False) for k in key]
        broken.loc[v, "gaming_suspect"] = [k in suspects[system] for k in key]
        if system == "A" and keepers is not None:
            suspects["keeper"] = self_registration_suspects(master, targets, keepers)
            broken.loc[v, "self_registration_suspect"] = [k in suspects["keeper"] for k in key]

    # after round 3: count each car when its real customer took it (the register's first keeper; B's order log)
    if first_keepers is not None:
        fk = master["car_id"].map(first_keepers.set_index("car_id")[["first_keeper", "customer_date"]].to_dict("series")
                                  ["customer_date"].where(first_keepers.set_index("car_id")["first_keeper"].eq("dealer")))
        suspects["first_keeper"] = customer_date_suspects(master, targets, "A",
                                                          fk.fillna(master["registration_date"]))
        v = live["system"].eq("A") & live["family"].eq("volume")
        key = list(zip(live.loc[v, "dealer_id"], pd.to_datetime(live.loc[v, "car_event"]).dt.to_period("Q")))
        broken.loc[v, "first_keeper_suspect"] = [k in suspects["first_keeper"] for k in key]
    if orders is not None:
        final = orders[orders["event"].eq("customer changed")].groupby("car_id")["date"].max()
        suspects["order_change"] = customer_date_suspects(master, targets, "B",
                                                          master["car_id"].map(final).fillna(master["order_date"]))
        v = live["system"].eq("B") & live["family"].eq("volume")
        key = list(zip(live.loc[v, "dealer_id"], pd.to_datetime(live.loc[v, "car_event"]).dt.to_period("Q")))
        broken.loc[v, "order_change_suspect"] = [k in suspects["order_change"] for k in key]

    # the fleet check (part 9): the buyer type the programme needs against the type of the JV contract on the car
    if contracts is not None:
        ctype = live["car_id"].astype("int64").map(contract_types(master, contracts)).to_numpy()
        need = p["buyer"].to_numpy()
        broken["contract_contradicted"] = (((need == "fleet") & (ctype == "private finance"))
                                           | (np.isin(need, ["private", "conquest"]) & (ctype == "fleet lease")))
        broken["fleet_unverified"] = (need == "fleet") & pd.isna(ctype)

    # forbidden stacks among the claims no earlier rule has flagged: flag the later claim of an excluded pair
    ok = ~broken[HARD[:-1]].any(axis=1)
    rest = live[ok].sort_values(["car_id", "claim_date", "claim_id"])
    seen = {}
    for i, car, family in zip(rest.index, rest["car_id"], rest["family"]):
        fams = seen.setdefault(car, set())
        if any((family, f) in EXCLUDES or (f, family) in EXCLUDES for f in fams):
            broken.at[i, "forbidden_stack"] = True
        else:
            fams.add(family)
    return broken, suspects


def layer3(claims, master, links, targets, tradeins, keepers=None, contracts=None, first_keepers=None, orders=None,
           tradein_keepers=None):
    live = live_claims(claims, links, master)
    broken, suspects = rules(live, master, targets, tradeins, keepers, contracts, first_keepers, orders,
                             tradein_keepers)
    first = broken.idxmax(axis=1).where(broken.any(axis=1))
    reason = links["reason"].copy()
    idx = links.index[links["claim_id"].isin(live["claim_id"])]
    by_id = pd.Series(first.to_numpy(), index=live["claim_id"].to_numpy())
    new = links.loc[idx, "claim_id"].map(by_id)
    reason[idx] = reason[idx].fillna(new)
    return pd.DataFrame({"claim_id": links["claim_id"], "reason": reason, "car_id": links["car_id"]}), \
        broken.assign(claim_id=live["claim_id"].to_numpy()), suspects


def main():
    claims, master = load()
    links = pd.read_parquet(SYN / "x1_flags_layer2.parquet").astype({"reason": "object"})
    truth = pd.read_parquet(SYN / "x1_truth.parquet")
    targets = pd.read_parquet(SYN / "x1_targets.parquet")
    tradeins = pd.read_parquet(SYN / "x1_register_tradeins.parquet")
    price_file = SYN / "x1_oem_prices.parquet"
    extra = {n: pd.read_parquet(SYN / f"x1_{f}.parquet") if (SYN / f"x1_{f}.parquet").exists() else None
             for n, f in [("transfers", "oem_transfers"), ("orders", "oem_order_log"),
                          ("first_keepers", "register_first_keeper"), ("tradein_keepers", "register_tradein_keepers")]}
    master = trusted_record(master, pd.read_parquet(SYN / "x1_oem_record.parquet"),
                            pd.read_parquet(price_file) if price_file.exists() else None,
                            extra["transfers"], extra["orders"])
    keeper_file = SYN / "x1_register_keepers.parquet"
    keepers = pd.read_parquet(keeper_file) if keeper_file.exists() else None
    contract_file = SYN / "x1_finance_contracts.parquet"
    contracts = pd.read_parquet(contract_file) if contract_file.exists() else None
    kw = {n: extra[n] for n in ("first_keepers", "orders", "tradein_keepers")}
    flags, broken, suspects = layer3(claims, master, links, targets, tradeins, keepers, contracts, **kw)
    again, _, _ = layer3(claims, master, links, targets, tradeins, keepers, contracts, **kw)
    assert flags.equals(again)

    # self-check: no hard rule flags a legitimate claim
    is_leak = truth["is_leak"] if "is_leak" in truth else truth["label"].isin(LEAKS)
    legit = ~broken["claim_id"].map(pd.Series(is_leak.to_numpy(), index=truth["claim_id"])).astype(bool)
    hard_on_legit = broken.loc[legit, HARD].sum()
    if "is_leak" in truth:  # another author's world (the red team): report, since breaking us is the point
        print(f"hard rules on the {legit.sum():,} legitimate live claims: {hard_on_legit[hard_on_legit > 0].to_dict()}\n")
    else:
        assert hard_on_legit.sum() == 0, hard_on_legit[hard_on_legit > 0].to_dict()
        print(f"self-check: no hard rule flags any of the {legit.sum():,} legitimate live claims\n")

    gamed = pd.read_parquet(SYN / "x1_truth_cars.parquet")
    gamed_q = set(zip(gamed["dealer_id"], gamed["gamed_quarter"]))
    flagged_q = {(d, str(q)) for d, q in suspects["A"]}
    print(f"gaming rule, A dealer-quarters: flagged {len(flagged_q)}, of which gamed {len(flagged_q & gamed_q)}; "
          f"gamed quarters caught {len(flagged_q & gamed_q)} of {len(gamed_q)}; B dealer-quarters flagged "
          f"{len(suspects['B'])}\n")

    if contracts is not None:  # the fleet check's two review rules, on leak and legitimate live claims
        leak_claim = broken["claim_id"].map(pd.Series(is_leak.to_numpy(), index=truth["claim_id"])).astype(bool)
        for rule in ("contract_contradicted", "fleet_unverified"):
            print(f"{rule}: {int(broken.loc[leak_claim, rule].sum())} leak claims, "
                  f"{int(broken.loc[~leak_claim, rule].sum())} legitimate")
        print()

    show(flags, "layers 1+2+3")

    # which layer catches which euros
    t = truth.merge(links[["claim_id", "reason"]].rename(columns={"reason": "r12"}), on="claim_id") \
             .merge(flags[["claim_id", "reason"]], on="claim_id")
    leak = t[t["is_leak"].astype(bool)] if "is_leak" in t else t[t["label"].isin(LEAKS)]
    by = leak.groupby("label").agg(leak_eur=("leak_eur", "sum"))
    by["keys_and_matching"] = leak[leak["r12"].notna()].groupby("label")["leak_eur"].sum()
    by["rules"] = leak[leak["r12"].isna() & leak["reason"].notna()].groupby("label")["leak_eur"].sum()
    by = by.fillna(0.0)
    by["missed"] = by["leak_eur"] - by["keys_and_matching"] - by["rules"]
    by.loc["total"] = by.sum()
    share = (by.div(by["leak_eur"], axis=0) * 100).round(1)
    print("\nleak euros by the layer that catches them (% of each type's leak euros; synthetic):")
    print(share.drop(columns="leak_eur").assign(leak_eur_k=(by["leak_eur"] / 1e3).round(0)).to_string())
    flags.to_parquet(SYN / "x1_flags_layer3.parquet", index=False)


if __name__ == "__main__":
    main()
