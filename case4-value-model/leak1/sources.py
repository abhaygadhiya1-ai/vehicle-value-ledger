"""X1 after round 3: four independent sources that close the gaps round 3 exploited.

Round 3's blind red team beat every check built on an incomplete source (see the X1 notes and
`notes/Case4_Field_Provenance.md`). The provenance map named the missing sources; this writes them. Each is built
from the true world, by its own random stream where it draws anything, so every existing world file stays
byte-identical. A red team that simulates a real event must record it here truthfully, as it must in the others.

  x1_register_first_keeper      the register's first keeper of each car (dealer or customer) and the day the car first
                                passed to a customer. RDW holds the history, but open data shows only the current
                                keeper (checked 25 September), so this needs a data agreement or proof from the dealer.
                                It closes round 3's slow handovers, which waited out the 30-day keeper window.
  x1_oem_transfers              the OEM's dated log of dealer-to-dealer transfers. A transfer after the car's retail
                                registration must not move volume credit; round 3 pooled volume that way.
  x1_oem_order_log              the B order system's audit trail: the dealer that signed each order and when, and each
                                later change of customer, dated. Round 3 signed placeholder orders in an affiliate's name
                                and handed them to the real customer later.
  x1_register_tradein_keepers   the day the buyer became keeper of the trade-in, as the register shows it by plate
                                (`datum_tenaamstelling`, public) when read before the trade-in passes to the dealer.
                                Round 3's straw trade-ins were in the buyer's name for days.

In our world, and in the holdout, the legitimate look-alikes are: dealer self-registrations that pass quickly to a
customer (the real-rate quick keeper changes of part 7b, all treated as dealer registrations, the hard case); dealer
trades that source a car from another dealer's stock before registration; B orders whose customer changes before
delivery; and conquest buyers who held their trade-in just past the minimum.

Usage: .venv/bin/python leak1/sources.py   (X1_DATA and X1_SEED_OFFSET pick the world, as for every X1 script)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from generate import SEED_OFFSET, SYN, setting  # noqa: E402
from inject import keeper_events  # noqa: E402

TRANSFER_SEED = 77 + SEED_OFFSET
ORDER_SEED = 78 + SEED_OFFSET
HOLDING_SEED = 79 + SEED_OFFSET
DAY = pd.Timedelta(days=1)


def first_keeper(master, gamed):
    """The first keeper and the day the car first passed to a customer, from the same keeper events as the register's
    current-keeper file (part 7b), without the later changes that hide them. A car pulled forward by gaming, and a car
    whose keeper changed within the quick window, was first registered in the dealer's name (for the legitimate ones
    that is the hard case: every quick change is taken to be a dealer registration)."""
    _, keeper, quick = keeper_events(master, gamed)
    dealer = quick | master["car_id"].isin(gamed["car_id"]).to_numpy()
    return pd.DataFrame({"car_id": master["car_id"].to_numpy(),
                         "first_keeper": np.where(dealer, "dealer", "customer"),
                         "customer_date": np.where(dealer, keeper, master["registration_date"]).astype("datetime64[ns]")})


def oem_transfers(sales, dealers, seed=TRANSFER_SEED):
    """Legitimate dealer trades: a share of cars are sourced from another dealer's stock (on the same system) before
    registration. The OEM record already names the selling dealer; this dates how the car got there."""
    rng = np.random.default_rng(seed)
    pick = rng.random(len(sales)) < setting("transfer_legit_share")
    s = sales[pick]
    rows = []
    for car, system, dealer, order, reg in zip(s["car_id"], s["system"], s["dealer_id"], s["order_date"],
                                               s["registration_date"]):
        pool = dealers.loc[dealers[f"code_{system.lower()}"].notna() & dealers["dealer_id"].ne(dealer), "dealer_id"]
        span = max((reg - order).days - 1, 0)
        rows.append((car, int(pool.iloc[int(rng.integers(len(pool)))]), dealer,
                     order + DAY * int(rng.integers(0, span + 1))))
    return pd.DataFrame(rows, columns=["car_id", "from_dealer", "to_dealer", "transfer_date"])


def oem_order_log(sales, seed=ORDER_SEED):
    """Every B order's signature (dealer and date), and for a share of orders a later change of customer before
    delivery (a company car reassigned, a buyer's partner taking the contract), dated by the order system."""
    rng = np.random.default_rng(seed)
    b = sales[sales["system"] == "B"]
    signed = pd.DataFrame({"car_id": b["car_id"].to_numpy(), "event": "signed", "date": b["order_date"].to_numpy(),
                           "dealer_id": b["dealer_id"].to_numpy()})
    change = rng.random(len(b)) < setting("order_customer_change_share")
    c = b[change]
    span = ((c["registration_date"] - c["order_date"]).dt.days - 1).clip(lower=1).to_numpy()
    when = c["order_date"] + pd.to_timedelta(rng.integers(1, span + 1), unit="D")
    changed = pd.DataFrame({"car_id": c["car_id"].to_numpy(), "event": "customer changed", "date": when.to_numpy(),
                            "dealer_id": c["dealer_id"].to_numpy()})
    return pd.concat([signed, changed], ignore_index=True).sort_values(["car_id", "date"], ignore_index=True)


def register_tradein_keepers(sales, tradeins, seed=HOLDING_SEED):
    """For each car sold with a trade-in, the day its buyer became the trade-in's keeper. A conquest buyer held it at
    least the programme's minimum (the rulebook's condition, so the clean world obeys it); any buyer at most the
    upper bound of `tradein_holding_days`."""
    rng = np.random.default_rng(seed)
    t = tradeins[tradeins["tradein_make"].notna()].merge(sales[["car_id", "system", "buyer", "registration_date",
                                                                "order_date"]], on="car_id")
    event = t["registration_date"].where(t["system"].eq("A"), t["order_date"])
    low, high = setting("tradein_holding_days")
    low = np.where(t["buyer"].eq("conquest"), setting("conquest_min_holding_days"), low)
    held = rng.integers(low, high + 1)
    return pd.DataFrame({"car_id": t["car_id"].to_numpy(),
                         "tradein_keeper_since": (event - pd.to_timedelta(held, unit="D")).to_numpy()})


def main():
    sales, master, dealers = (pd.read_parquet(SYN / f"x1_{n}.parquet") for n in ["sales", "master", "dealers"])
    gamed = pd.read_parquet(SYN / "x1_truth_cars.parquet")  # the world builder knows its own events
    tradeins = pd.read_parquet(SYN / "x1_register_tradeins.parquet")
    out = {"x1_register_first_keeper": first_keeper(master, gamed),
           "x1_oem_transfers": oem_transfers(sales, dealers),
           "x1_oem_order_log": oem_order_log(sales),
           "x1_register_tradein_keepers": register_tradein_keepers(sales, tradeins)}
    again = [first_keeper(master, gamed), oem_transfers(sales, dealers), oem_order_log(sales),
             register_tradein_keepers(sales, tradeins)]
    assert all(a.equals(b) for a, b in zip(out.values(), again)), "a source is not deterministic"

    # checks against the world they describe
    fk = out["x1_register_first_keeper"]
    assert fk["car_id"].equals(master["car_id"]) and (fk["customer_date"] >= master["registration_date"]).all()
    assert fk.set_index("car_id").loc[gamed["car_id"], "first_keeper"].eq("dealer").all()
    tr = out["x1_oem_transfers"].merge(sales[["car_id", "dealer_id", "registration_date", "order_date"]], on="car_id")
    assert tr["to_dealer"].eq(tr["dealer_id"]).all() and tr["from_dealer"].ne(tr["to_dealer"]).all()
    assert (tr["transfer_date"] < tr["registration_date"]).all() and (tr["transfer_date"] >= tr["order_date"]).all()
    ol = out["x1_oem_order_log"]
    b = sales[sales["system"] == "B"]
    assert ol.loc[ol["event"].eq("signed"), "car_id"].sort_values().tolist() == sorted(b["car_id"])
    ch = ol[ol["event"].eq("customer changed")].merge(b[["car_id", "order_date", "registration_date"]], on="car_id")
    assert ((ch["date"] > ch["order_date"]) & (ch["date"] <= ch["registration_date"])).all()
    tk = out["x1_register_tradein_keepers"].merge(sales[["car_id", "buyer", "system", "registration_date",
                                                         "order_date"]], on="car_id")
    held = (tk["registration_date"].where(tk["system"].eq("A"), tk["order_date"]) - tk["tradein_keeper_since"]).dt.days
    assert held[tk["buyer"].eq("conquest")].ge(setting("conquest_min_holding_days")).all()

    for name, df in out.items():
        df.to_parquet(SYN / f"{name}.parquet", index=False)
    print(f"first keeper a dealer: {fk['first_keeper'].eq('dealer').sum():,} of {len(fk):,} cars "
          f"({len(gamed)} of them gamed); legitimate dealer trades: {len(tr):,}; B orders: {len(b):,}, with a change of "
          f"customer: {len(ch):,}; trade-ins with a keeper date: {len(tk):,}")
    print(f"wrote {', '.join(out)} to {SYN}")


if __name__ == "__main__":
    main()
