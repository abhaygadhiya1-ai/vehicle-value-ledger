"""X1 part 3: the clean world. Dealers, buyers, orders and claims, with no leaks yet.

Every claim here is one the rulebook in `spec.py` allows: the right buyer, the right system, filed inside its window,
for the right amount, with no forbidden stack. Part 4 injects the leaks into a copy of this world and keeps the truth
table. So anything a detector later flags in the clean claims is a false alarm by construction.

Everything drawn here uses the ASSUMPTION settings in `spec.py`. It is a synthetic world that measures the tool,
not the group.

Outputs (data/synthetic/, not published):
  x1_dealers.parquet          one row per dealer: its code in each system it is on, and its size
  x1_sales.parquet            the sales record: every car with its system, dealer, buyer, order number and date
  x1_claims_clean.parquet     canonical claims, with car_id, the truth link a real claims table does not carry
  x1_system_a_clean.parquet   the same claims as system A stores them (its columns, net amounts)
  x1_system_b_clean.parquet   ... and as system B stores them (its columns, gross amounts)
  x1_finance_contracts.parquet  the finance joint venture's contracts (part 9): a source across the JV boundary, keyed
                              by the JV's own staff, so its VINs carry typos and its start dates differ from
                              registration. `car_id_truth` is for the scorer only; a detector may not read it.
  x1_oem_prices.parquet       the OEM's price list per car (after round 3, post hoc): the list price amounts are
                              computed on, from the OEM's configurator rather than the dealer-reported record
  x1_oem_record.parquet       the OEM's own record of each car (the design-gap fix after the red teams): the dealer it
                              invoiced, after documented dealer-to-dealer transfers, and the order system's timestamp
                              of the signed order. Sources the dealer does not control. In reality this is the wholesale
                              invoice, the transfer log and the order system; X1 holds their result.
Usage: .venv/bin/python leak1/generate.py
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from spec import (BUYERS_OF, EXCLUDES, NONGROUP_MAKES, PROGRAMMES, SALE_EVENT, SETTINGS,  # noqa: E402
                  SYSTEM_OF_BRAND, claim_window, system_table)

# X1_DATA points every X1 script at another world (the red-team world) without touching a detector
SYN = Path(os.environ.get("X1_DATA", HERE.parent / "data" / "synthetic"))
# X1_SEED_OFFSET builds a fresh-seed world (the part 7b holdout) from the same cars; 0 is our world
SEED_OFFSET = int(os.environ.get("X1_SEED_OFFSET", 0))
SEED = 3 + SEED_OFFSET  # part 3
TRADEIN_SEED = 33 + SEED_OFFSET  # its own stream, so adding the register source changed no existing file
FINANCE_SEED = 55 + SEED_OFFSET  # part 9, its own stream too


def setting(name):
    return SETTINGS[name][0]


def quarter_end(dates):
    return dates.dt.to_period("Q").dt.end_time.dt.normalize()


def make_dealers(rng):
    systems = (["A"] * setting("dealers_a_only") + ["B"] * setting("dealers_b_only")
               + ["AB"] * setting("dealers_both"))
    d = pd.DataFrame({"dealer_id": np.arange(1, len(systems) + 1), "systems": systems})
    d["weight"] = rng.lognormal(0, setting("dealer_size_sigma"), len(d))
    on_a, on_b = d["systems"].str.contains("A"), d["systems"].str.contains("B")
    d["code_a"] = pd.Series(dtype="string")
    d["code_b"] = pd.Series(dtype="string")
    d.loc[on_a, "code_a"] = [f"NL{x:05d}" for x in rng.choice(10**5, on_a.sum(), replace=False)]
    d.loc[on_b, "code_b"] = [f"{x:06d}" for x in rng.choice(10**6, on_b.sum(), replace=False)]
    return d


def make_sales(cars, dealers, rng):
    s = cars.rename(columns={"first_reg_date": "registration_date"})
    s.insert(2, "system", s["make"].map(SYSTEM_OF_BRAND))
    s["dealer_id"] = 0
    for system in "AB":
        pool = dealers[dealers["systems"].str.contains(system)]
        idx = s.index[s["system"] == system]
        p = (pool["weight"] / pool["weight"].sum()).to_numpy()
        s.loc[idx, "dealer_id"] = rng.choice(pool["dealer_id"].to_numpy(), len(idx), p=p)
    fleet = rng.random(len(s)) < setting("fleet_share")
    conquest = ~fleet & (rng.random(len(s)) < setting("conquest_share"))
    s["buyer"] = np.where(fleet, "fleet", np.where(conquest, "conquest", "private"))
    lo, hi = setting("order_lead_days")
    s["order_date"] = s["registration_date"] - pd.to_timedelta(rng.integers(lo, hi + 1, len(s)), unit="D")
    s["order_no"] = [f"OR{x:08d}" for x in rng.choice(10**8, len(s), replace=False)]
    return s


def quarter_counts_targets(s, event, years):
    """Cars per dealer and quarter, counted on the system's own sale event, and each dealer's quarterly target:
    a share of its average quarter over the programme's years."""
    inside = event.dt.year.isin(years)
    q = event.dt.to_period("Q")
    counts = s[inside].groupby([s.loc[inside, "dealer_id"], q[inside]]).size()
    per_dealer = counts.groupby(level=0).sum() / (4 * len(years))
    return counts, np.ceil(setting("volume_target_share") * per_dealer)


def target_hit(s, event, years):
    """Did the car's dealer reach its quarterly target in this system?"""
    counts, target = quarter_counts_targets(s, event, years)
    hit = counts >= target.reindex(counts.index.get_level_values(0)).to_numpy()
    key = pd.MultiIndex.from_arrays([s["dealer_id"], event.dt.to_period("Q")])
    return pd.Series(hit.reindex(key).fillna(False).astype(bool).to_numpy(), index=s.index)


def make_claims(sales, dealers, rng):
    parts = []
    for system, code, family, buyer, basis, amount, years in PROGRAMMES.itertuples(index=False):
        s = sales[sales["system"] == system]
        event = s[SALE_EVENT[system]]
        ok = s["buyer"].isin(BUYERS_OF[buyer]) & event.dt.year.isin(years)
        if family == "volume":
            ok &= target_hit(s, event, years)
        e = s[ok]
        opens, closes = claim_window(system, family, e["order_date"], e["registration_date"],
                                     quarter_end(e[SALE_EVENT[system]]))
        span = (closes - opens).dt.days.to_numpy()
        parts.append(pd.DataFrame({
            "system": system, "car_id": e["car_id"], "dealer_id": e["dealer_id"], "vin": e["vin"],
            "order_no": e["order_no"] if system == "B" else pd.NA,  # A leaves its optional order field empty
            "programme": code, "family": family, "event_date": e[SALE_EVENT[system]],
            "claim_date": opens + pd.to_timedelta(rng.integers(0, span + 1), unit="D"),
            "amount_net": (amount * e["list_price_eur"] if basis == "pct_list"
                           else pd.Series(float(amount), index=e.index)).round(2),
        }))
    c = pd.concat(parts, ignore_index=True).sort_values(["system", "claim_date", "car_id", "programme"],
                                                        ignore_index=True)
    n = c.groupby("system").cumcount() + 1
    c.insert(0, "claim_id", np.where(c["system"] == "A", "A" + n.map("{:08d}".format), n.map("{:07d}".format)))
    codes = dealers.set_index("dealer_id")
    c.insert(3, "dealer", np.where(c["system"] == "A", c["dealer_id"].map(codes["code_a"]),
                                   c["dealer_id"].map(codes["code_b"])))
    return c.drop(columns="dealer_id")


def published_targets(sales):
    """Each dealer's quarterly volume target per system, as the OEM publishes it before the quarter: the rule the
    world was generated with. Detectors read this and never recompute a target from the vehicle record."""
    rows = []
    for system in "AB":
        s = sales[sales["system"] == system]
        years = PROGRAMMES.loc[PROGRAMMES["system"].eq(system) & PROGRAMMES["family"].eq("volume"), "years"].iloc[0]
        _, target = quarter_counts_targets(s, s[SALE_EVENT[system]], years)
        rows.append(pd.DataFrame({"system": system, "dealer_id": target.index, "target": target.to_numpy()}))
    return pd.concat(rows, ignore_index=True)


def register_tradeins(sales):
    """What the national register says about each buyer's trade-in, a source the dealer does not control. A conquest
    buyer traded in a non-group make; a loyal private buyer a car of the same make, or nothing; a fleet buyer
    nothing (not applicable)."""
    rng = np.random.default_rng(TRADEIN_SEED)
    make = pd.Series(pd.NA, index=sales.index, dtype="object")
    conquest, private = sales["buyer"].eq("conquest"), sales["buyer"].eq("private")
    make[conquest] = rng.choice(NONGROUP_MAKES, conquest.sum())
    keeps = private & (rng.random(len(sales)) < setting("tradein_private_share"))
    make[keeps] = sales.loc[keeps, "make"]
    return pd.DataFrame({"car_id": sales["car_id"], "tradein_make": make})


def oem_record(sales):
    """The OEM's record of each car's selling dealer and order date, taken from the sales record: the truth, which the
    dealer-reported vehicle record may not match."""
    return sales[["car_id", "dealer_id", "order_date"]].reset_index(drop=True)


def oem_prices(sales):
    """The OEM's list price for each car, from its own price list: the truth, which the reported record may inflate."""
    return sales[["car_id", "list_price_eur"]].reset_index(drop=True)


def finance_contracts(sales, seed=FINANCE_SEED):
    """The captive finance JV's contracts, from the true sales record: a fleet lease for every fleet sale the JV
    carries, a private finance contract for a share of private and conquest sales. The JV keys its own VINs, so a
    share carry a typo, and a contract starts near, not on, the registration date."""
    from population import ALPHABET
    rng = np.random.default_rng(seed)
    fleet = sales["buyer"].eq("fleet")
    take = np.where(fleet, rng.random(len(sales)) < setting("finance_fleet_share"),
                    rng.random(len(sales)) < setting("finance_private_share"))
    s = sales[take]
    vin = s["vin"].to_numpy().copy()
    typo = rng.random(len(s)) < setting("finance_vin_typo")
    for i in np.flatnonzero(typo):
        v = list(vin[i])
        for _ in range(int(rng.integers(1, 3))):
            j = int(rng.integers(0, len(v)))
            v[j] = rng.choice([c for c in ALPHABET if c != v[j]])
        vin[i] = "".join(v)
    days = setting("finance_start_days")
    start = s["registration_date"] + pd.to_timedelta(rng.integers(-days, days + 1, len(s)), unit="D")
    return pd.DataFrame({"contract_id": [f"FC{x:07d}" for x in rng.choice(10**7, len(s), replace=False)],
                         "vin": vin, "start_date": start.to_numpy(),
                         "contract_type": np.where(s["buyer"].eq("fleet"), "fleet lease", "private finance"),
                         "car_id_truth": s["car_id"].to_numpy()})


def build(cars, seed=SEED):
    rng = np.random.default_rng(seed)
    dealers = make_dealers(rng)
    sales = make_sales(cars, dealers, rng)
    return dealers, sales, make_claims(sales, dealers, rng)


def check(dealers, sales, claims):
    """Invariants of a clean world, re-derived from the sales record rather than trusted from the generator."""
    m = claims.merge(sales, on="car_id", how="left", suffixes=("", "_car"), validate="many_to_one")
    assert m["vin_car"].notna().all(), "a claim ties to no car"
    assert (m["vin"] == m["vin_car"]).all() and (m["system"] == m["system_car"]).all()
    b = m["system"] == "B"
    assert (m.loc[b, "order_no"] == m.loc[b, "order_no_car"]).all() and m.loc[~b, "order_no"].isna().all()
    codes = dealers.set_index("dealer_id")
    own = np.where(m["system"] == "A", m["dealer_id"].map(codes["code_a"]), m["dealer_id"].map(codes["code_b"]))
    assert (m["dealer"] == own).all(), "a claim filed under another dealer's code"

    p = m.merge(PROGRAMMES, left_on=["system", "programme"], right_on=["system", "code"], how="left",
                suffixes=("", "_p"))
    assert p["code"].notna().all(), "a programme not in its system's catalogue"
    assert (p["family"] == p["family_p"]).all()
    assert p.apply(lambda r: r["buyer"] in BUYERS_OF[r["buyer_p"]], axis=1).all(), "wrong buyer"
    event = np.where(p["system"] == "A", p["registration_date"], p["order_date"])
    assert (p["event_date"].to_numpy() == event).all()
    assert p.apply(lambda r: r["event_date"].year in r["years"], axis=1).all(), "outside the programme's years"
    amount = np.where(p["basis"] == "pct_list", p["amount"] * p["list_price_eur"], p["amount"])
    assert np.allclose(p["amount_net"], np.round(amount, 2)), "wrong amount"

    for (system, family), g in p.groupby(["system", "family"]):
        opens, closes = claim_window(system, family, g["order_date"], g["registration_date"],
                                     quarter_end(g["event_date"]))
        assert g["claim_date"].between(opens, closes).all(), f"{system} {family} claim outside its window"

    assert not claims.duplicated(["car_id", "family"]).any(), "two claims of one family on one car"
    sets = claims.groupby("car_id")["family"].agg(lambda x: set(x))
    assert not any(a in f and b in f for f in sets for a, b in EXCLUDES), "a forbidden stack"
    lead = (sales["registration_date"] - sales["order_date"]).dt.days
    assert lead.between(0, setting("b_registration_within_days")).all()
    assert sales["order_no"].is_unique and claims["claim_id"].is_unique


def main():
    cars = pd.read_parquet(SYN / "x1_cars.parquet")
    dealers, sales, claims = build(cars)
    again = build(cars)
    assert dealers.equals(again[0]) and sales.equals(again[1]) and claims.equals(again[2]), "not deterministic"
    check(dealers, sales, claims)
    print("all clean-world invariants hold; two builds are identical")

    print("\ndealers:", dealers["systems"].value_counts().sort_index().to_dict())
    print("buyers:", sales["buyer"].value_counts(normalize=True).round(3).to_dict())
    t = (claims.groupby(["system", "programme", "family"])
               .agg(claims=("claim_id", "size"), eur=("amount_net", "sum")).reset_index())
    t["eur"] = (t["eur"] / 1e6).round(2)
    print("\nclaims by programme (EUR m, net, synthetic amounts):")
    print(t.rename(columns={"eur": "eur_m"}).to_string(index=False))
    per_car = claims.groupby("car_id").size().reindex(sales["car_id"], fill_value=0)
    print(f"\ncars with at least one claim: {(per_car > 0).mean():.1%}; claims per car: "
          f"{per_car.value_counts().sort_index().to_dict()}")
    early = (sales["system"].eq("B") & (sales["order_date"] < "2021-01-01")).sum()
    print(f"B cars ordered before 2021, outside every B programme by B's own rule: {early:,}")
    pre = claims["system"].eq("B") & (claims["claim_date"] < claims["car_id"].map(
        sales.set_index("car_id")["registration_date"]))
    print(f"B claims booked before the car was registered: {pre.sum():,} of {claims['system'].eq('B').sum():,}")

    SYN.mkdir(parents=True, exist_ok=True)
    dealers.to_parquet(SYN / "x1_dealers.parquet", index=False)
    sales.to_parquet(SYN / "x1_sales.parquet", index=False)
    claims.to_parquet(SYN / "x1_claims_clean.parquet", index=False)
    for system in "AB":
        system_table(claims[claims["system"] == system], system).to_parquet(
            SYN / f"x1_system_{system.lower()}_clean.parquet", index=False)
    published_targets(sales).to_parquet(SYN / "x1_targets.parquet", index=False)
    register_tradeins(sales).to_parquet(SYN / "x1_register_tradeins.parquet", index=False)
    oem_record(sales).to_parquet(SYN / "x1_oem_record.parquet", index=False)
    finance_contracts(sales).to_parquet(SYN / "x1_finance_contracts.parquet", index=False)
    oem_prices(sales).to_parquet(SYN / "x1_oem_prices.parquet", index=False)
    size = sum((SYN / f).stat().st_size for f in ["x1_dealers.parquet", "x1_sales.parquet",
               "x1_claims_clean.parquet", "x1_system_a_clean.parquet", "x1_system_b_clean.parquet"])
    print(f"wrote 5 files to data/synthetic/, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
