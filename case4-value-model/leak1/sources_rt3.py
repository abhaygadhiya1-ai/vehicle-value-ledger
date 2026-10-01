"""The four sources of `sources.py`, written post hoc into blind round 3's world (data/synthetic_redteam3).

Round 3's red team simulated real events the new sources would have recorded: cars registered in the dealer's name
and handed over 32 or more days later, documented transfers of already-sold cars, B orders signed in an affiliate's
name and taken over by the real customer later, and straw trade-ins held for days. This rebuilds each source from the
clean world (the same functions and seeds as ours) and then records the red team's events in it, read from the red
team's own change log and truth table. It confirms the rules work as built on a world someone else made; it is not
evidence, because the sources were designed after seeing round 3.

Where the red team did not date an event, this picks a date its description allows (noted inline); any such date
gives the same rule outcome.
Usage: .venv/bin/python leak1/sources_rt3.py
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from sources import first_keeper, oem_order_log, oem_transfers, register_tradein_keepers  # noqa: E402

W = HERE.parent / "data" / "synthetic_redteam3"
DAY = pd.Timedelta(days=1)
STRAW_HOLDING_DAYS = 3  # "a few days" in the red team's description


def main():
    sales = pd.read_parquet(W / "inputs" / "x1_sales.parquet")  # the clean world the red team started from
    dealers = pd.read_parquet(W / "x1_dealers.parquet")
    master = pd.read_parquet(W / "x1_master.parquet")
    keepers = pd.read_parquet(W / "x1_register_keepers.parquet")
    truth = pd.read_parquet(W / "x1_truth.parquet")
    truth_cars = pd.read_parquet(W / "x1_truth_cars.parquet")
    changes = pd.read_parquet(W / "x1_truth_master_changes.parquet")
    tradeins = pd.read_parquet(W / "x1_register_tradeins.parquet")
    oem = pd.read_parquet(W / "x1_oem_record.parquet").set_index("car_id")

    # first keeper: the clean world's keeper events (no gaming in it), then the slow handovers, registered in the
    # dealer's name and passed to the buyer on the day the red team's keeper file shows
    no_gaming = pd.DataFrame({"car_id": pd.Series(dtype="int64"), "true_registration_date": pd.Series(dtype="datetime64[ns]")})
    fk = first_keeper(sales, no_gaming).set_index("car_id")
    slow = truth_cars.loc[truth_cars["recorded_registration_date"].ne(truth_cars["true_registration_date"]), "car_id"]
    fk.loc[slow, "first_keeper"] = "dealer"
    fk.loc[slow, "customer_date"] = keepers.set_index("car_id").loc[slow, "keeper_date_prompt"].to_numpy()

    # transfers: the clean world's legitimate trades, plus the red team's documented transfers of sold cars, dated the
    # day after the car's sale event (its description: already sold, and not in the quarter's last week)
    moved = changes[changes["field"].eq("dealer_id")]
    car = master.set_index("car_id")
    event = car["registration_date"].where(car["system"].eq("A"), car["order_date"])
    red = pd.DataFrame({"car_id": moved["car_id"].to_numpy(), "from_dealer": moved["true_value"].astype(int).to_numpy(),
                        "to_dealer": moved["recorded_value"].astype(int).to_numpy(),
                        "transfer_date": (event.loc[moved["car_id"]] + DAY).to_numpy()})
    tr = pd.concat([oem_transfers(sales, dealers), red], ignore_index=True)

    # the B order log: the clean world's, with each placeholder order signed on the date the OEM record shows (in the
    # affiliate's name) and a change of customer on the real customer's own order date
    ol = oem_order_log(sales)
    ph = changes[changes["field"].eq("order_date")]
    for car_id, o0, o1 in zip(ph["car_id"], pd.to_datetime(ph["true_value"]), pd.to_datetime(ph["recorded_value"])):
        signed = ol["car_id"].eq(car_id) & ol["event"].eq("signed")
        ol.loc[signed, "date"] = o1
        ol = pd.concat([ol, pd.DataFrame({"car_id": [car_id], "event": ["customer changed"], "date": [o0],
                                          "dealer_id": [ol.loc[signed, "dealer_id"].iloc[0]]})], ignore_index=True)
    assert ol.loc[ol["event"].eq("signed")].set_index("car_id")["date"].eq(
        oem.loc[ol.loc[ol["event"].eq("signed"), "car_id"], "order_date"].to_numpy()).all(), "order log vs OEM record"
    ol = ol.sort_values(["car_id", "date"], ignore_index=True)

    # trade-in keepers: every trade-in on the red team's register file; the straw trade-ins held for days
    tk = register_tradein_keepers(sales, tradeins).set_index("car_id")
    straw = truth.loc[truth["label"].eq("straw_tradein_conquest"), "car_id"].astype(int)
    tk.loc[straw, "tradein_keeper_since"] = (event.loc[straw] - STRAW_HOLDING_DAYS * DAY).to_numpy()

    fk.reset_index().to_parquet(W / "x1_register_first_keeper.parquet", index=False)
    tr.to_parquet(W / "x1_oem_transfers.parquet", index=False)
    ol.to_parquet(W / "x1_oem_order_log.parquet", index=False)
    tk.reset_index().to_parquet(W / "x1_register_tradein_keepers.parquet", index=False)
    print(f"round 3, post hoc: {len(slow)} slow handovers, {len(red)} transfers of sold cars, {len(ph)} placeholder "
          f"orders and {len(straw)} straw trade-ins recorded in the four sources")


if __name__ == "__main__":
    main()
