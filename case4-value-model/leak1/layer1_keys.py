"""X1 part 5, layer 1: exact keys. What joins and exact-duplicate logic catch, before any matching or rules.

Reads only what a detector may read: the two systems' claims, the vehicle record (`x1_master`) and the rulebook.

  1. Link each claim to a car in the vehicle record by its VIN. A B claim whose VIN is empty or unknown is linked by
     its order number. A B claim whose VIN and order number name different cars is a key conflict, left unlinked.
  2. Net credit notes. A negative claim cancels one earlier positive claim with the same car, system, programme and
     amount.
  3. Find duplicates. After netting, a car may carry one live claim per programme family across BOTH systems (the
     crosswalk makes the group programme one family). Keep the claim in the car's own system, earliest first, and
     flag the rest.
  4. Flag what cannot be linked: an unknown VIN, an unknown order number, or a key conflict.

Flags: duplicate, unknown_vin, unknown_order, key_conflict. Anything not flagged passes to the later layers.
Stacking, eligibility, deadlines and gaming are rules, left to layer 3 on purpose, so this layer's score answers
skeptic A10 (VINs versus rules) on its own.

Output: data/synthetic/x1_flags_layer1.parquet (claim_id, reason, car_id as linked)
Usage: .venv/bin/python leak1/layer1_keys.py
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from generate import SYN  # noqa: E402
from score import show  # noqa: E402
from spec import PROGRAMMES, canonical_table  # noqa: E402


def load():
    claims = pd.concat([canonical_table(pd.read_parquet(SYN / f"x1_system_{s.lower()}.parquet"), s) for s in "AB"],
                       ignore_index=True)
    return claims, pd.read_parquet(SYN / "x1_master.parquet")


def link(claims, master):
    by_vin = claims["vin"].map(master.set_index("vin")["car_id"])
    by_order = claims["order_no"].map(master.set_index("order_no")["car_id"])
    conflict = by_vin.notna() & by_order.notna() & by_vin.ne(by_order)
    car = by_vin.fillna(by_order).mask(conflict).astype("Int64")
    how = pd.Series("unlinked", index=claims.index)
    how[by_vin.notna()] = "vin"
    how[by_vin.isna() & by_order.notna()] = "order"
    how[conflict] = "conflict"
    return car, how


def with_family(claims):
    family = PROGRAMMES.set_index(["system", "code"])["family"]
    return claims.assign(family=[family[k] for k in zip(claims["system"], claims["programme"])])


def credit_pairs(linked):
    """Step 2: each credit note paired with the latest earlier positive claim of the same car, system, programme and
    amount. Returns the pairs, with the row index of each side in `index_neg` and `index_pos`."""
    key = ["car_id", "system", "programme"]
    neg = linked[linked["amount_net"] < 0].reset_index()
    pos = linked[linked["amount_net"] > 0].reset_index()
    pair = neg.merge(pos, on=key, suffixes=("_neg", "_pos"))
    pair = pair[pair["amount_net_pos"].eq(-pair["amount_net_neg"]) & (pair["claim_date_pos"] <= pair["claim_date_neg"])]
    return (pair.sort_values("claim_date_pos", ascending=False).drop_duplicates("index_neg")
                .drop_duplicates("index_pos")), len(neg)


def duplicates(c, master):
    """Steps 2 and 3 on claims that carry a `car_id` (NA when unlinked). Returns the index of duplicate rows and
    the netting counts. Layer 2 reuses it after it has suggested cars for the unlinked claims."""
    linked = c[c["car_id"].notna()]
    pair, n_neg = credit_pairs(linked)

    # one live claim per car and family across both systems; the car's own system first, then the earliest
    live = linked[(linked["amount_net"] > 0) & ~linked.index.isin(pair["index_pos"])]
    own = live["car_id"].map(master.set_index("car_id")["system"]).eq(live["system"])
    live = live.assign(own=own).sort_values(["car_id", "family", "own", "claim_date", "claim_id"],
                                            ascending=[True, True, False, True, True])
    rank = live.groupby(["car_id", "family"]).cumcount()
    return rank.index[rank > 0], {"credit_notes": n_neg, "netted_pairs": len(pair)}


def layer1(claims, master):
    c = with_family(claims)
    c["car_id"], c["linked_by"] = link(c, master)
    reason = pd.Series(pd.NA, index=c.index, dtype="object")
    reason[c["linked_by"].eq("conflict")] = "key_conflict"
    unlinked = c["linked_by"].eq("unlinked")
    reason[unlinked & c["vin"].notna()] = "unknown_vin"
    reason[unlinked & c["vin"].isna()] = "unknown_order"
    dup, stats = duplicates(c, master)
    reason[dup] = "duplicate"
    stats["linked_by"] = c["linked_by"].value_counts().to_dict()
    return pd.DataFrame({"claim_id": c["claim_id"], "reason": reason, "car_id": c["car_id"]}), stats


def main():
    claims, master = load()
    flags, stats = layer1(claims, master)
    again, _ = layer1(claims, master)
    assert flags.equals(again)
    print(f"links: {stats['linked_by']}; credit notes {stats['credit_notes']}, netted {stats['netted_pairs']}\n")
    show(flags, "layer 1, exact keys")
    flags.to_parquet(SYN / "x1_flags_layer1.parquet", index=False)


if __name__ == "__main__":
    main()
