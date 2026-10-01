"""The sealed inputs for a blind red-team round: the clean world, the rulebook and every independent source.

A red team starts from the clean world (no leaks of ours) and must record any real event it simulates truthfully in
the independent sources. So each source here is rebuilt from the clean sales by the same function and seed as in our
world, with no gaming in it. The rulebook (`spec.py`) is copied as it stands, with the four register rows it reads
beside the folder. No detector code, notes or results go in.

Usage: .venv/bin/python leak1/redteam_inputs.py data/synthetic_redteam4
"""
import csv
import shutil
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from generate import (SYN, finance_contracts, oem_prices, oem_record, published_targets,  # noqa: E402
                      register_tradeins)
from inject import register_keepers  # noqa: E402
from sources import first_keeper, oem_order_log, oem_transfers, register_tradein_keepers  # noqa: E402

REGISTER_ROWS = ["selfreg_group_base", "selfreg_group_qend_lift", "keeper_hidden_2021_group",
                 "keeper_early_change_3m_group"]  # the MEASURED settings `spec.py` reads


def main(folder):
    folder = Path(folder)
    inputs = folder / "inputs"
    inputs.mkdir(parents=True, exist_ok=False)  # a round's inputs are written once
    sales, claims, dealers = (pd.read_parquet(SYN / f"x1_{n}.parquet") for n in ["sales", "claims_clean", "dealers"])
    no_gaming = pd.DataFrame({"car_id": pd.Series(dtype="int64"),
                              "true_registration_date": pd.Series(dtype="datetime64[ns]")})
    tradeins = register_tradeins(sales)
    files = {"x1_sales": sales, "x1_claims_clean": claims, "x1_dealers": dealers,
             "x1_targets": published_targets(sales), "x1_register_tradeins": tradeins,
             "x1_oem_record": oem_record(sales), "x1_oem_prices": oem_prices(sales),
             "x1_finance_contracts": finance_contracts(sales),
             "x1_register_keepers": register_keepers(sales, no_gaming),
             "x1_register_first_keeper": first_keeper(sales, no_gaming),
             "x1_oem_transfers": oem_transfers(sales, dealers), "x1_oem_order_log": oem_order_log(sales),
             "x1_register_tradein_keepers": register_tradein_keepers(sales, tradeins)}
    for name, df in files.items():
        df.to_parquet(inputs / f"{name}.parquet", index=False)
    for name in ["x1_targets", "x1_register_tradeins", "x1_oem_record", "x1_oem_prices"]:  # as in our own world,
        # compared as read back, since text built in memory is object dtype and read back is pandas' string dtype
        assert pd.read_parquet(inputs / f"{name}.parquet").equals(pd.read_parquet(SYN / f"{name}.parquet")), name
    shutil.copyfile(HERE / "spec.py", inputs / "spec.py")
    rows = {r["id"]: r for r in csv.DictReader((HERE.parent / "assumptions.csv").open())}
    with (folder / "assumptions.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "value", "unit", "caveat"])
        for rid in REGISTER_ROWS:
            w.writerow([rid, rows[rid]["value"], rows[rid]["unit"], rows[rid]["caveat"]])
    print(f"wrote {len(files)} data files, the rulebook and {len(REGISTER_ROWS)} register rows to {folder}")


if __name__ == "__main__":
    main(sys.argv[1])
