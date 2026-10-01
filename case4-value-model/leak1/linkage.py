"""X1 part 9: privacy-preserving linkage across the finance joint-venture boundary.

Fleet status is the one money field X1 still reads from what the dealer reports (round 2's fleet upcoding went
through). Its independent source is the fleet or lease contract, which sits with the group's captive finance joint
venture: another company, under GDPR, which cannot hand the OEM its customers' VINs in clear. This links the OEM's
vehicle record to the JV's contracts (`x1_finance_contracts`) four ways and measures what privacy costs:

  M0  clear, exact VIN              the reference; not allowed across the boundary
  M1  keyed hash of the VIN, exact  private (both sides hash with a shared secret key), but one typo loses the link
  M2  Bloom-filter encoding (CLK)   private and typo-tolerant: each VIN's bigrams are hashed into a 1024-bit filter
                                    with 20 keyed hash functions (Schnell et al., 2009, double hashing with HMAC keys),
                                    compared by Dice similarity
  M3  clear bigram Dice             the same comparison on the exact bigram sets, with no hashing: the ceiling M2 is
                                    measured against, so M3 - M2 isolates what the encoding costs

The JV keys its own VINs, so some carry typos, and a contract starts near, not on, registration. All four methods
compare a contract only with cars registered within 31 days of its start (blocking). A contract links to its best car
above the threshold, one to one, best scores first. The threshold, 0.8, was fixed before any result; a sensitivity
table follows. Truth (`car_id_truth`) is read only to score.

Then the check it enables: a fleet claim needs its car to be linked to a JV fleet lease. A car linked to a private
contract contradicts the claim; a car linked to nothing leaves it unverified. Scored on our world (false alarms on
legitimate fleet claims) and on round 2's world, post hoc (fleet upcoding).

**Limits.** CLKs are open to frequency and pattern-mining attacks when an attacker holds the filters and knows the
encoding scheme; keyed hashing, one filter per record and a secret key held apart reduce that but do not remove it
(Christen, Ranbaduge & Schnell). Synthetic worlds: the figures measure the tool. Every fleet sale is assumed to go
through the captive JV (`finance_fleet_share`); in reality independent lessors would need their own agreement.
Output: leak1/x1_linkage_report.md, and x1_finance_links.parquet (M2's links) in each world.
Usage: .venv/bin/python leak1/linkage.py
"""
import hashlib
import hmac
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from population import ALPHABET  # noqa: E402

DATA = HERE.parent / "data"
OUT = HERE / "x1_linkage_report.md"
BITS, K, WINDOW = 1024, 20, 31
THRESHOLD = 0.8
SENSITIVITY = [0.7, 0.75, 0.8, 0.85, 0.9]
KEY_A, KEY_B = b"x1-demo-secret-a", b"x1-demo-secret-b"  # a real deployment keeps the key with a trusted third party
BIGRAMS = {a + b: i for i, (a, b) in enumerate((a, b) for a in ALPHABET for b in ALPHABET)}
WORLDS = [("ours", "synthetic"), ("RT2 (post hoc)", "synthetic_redteam2"), ("RT3 (post hoc)", "synthetic_redteam3")]


def grams(vin):
    return [vin[i:i + 2] for i in range(len(vin) - 1)]


def positions(g):
    """The K filter positions of one bigram, from two keyed hashes (double hashing)."""
    h1 = int.from_bytes(hmac.new(KEY_A, g.encode(), hashlib.sha256).digest()[:8], "big")
    h2 = int.from_bytes(hmac.new(KEY_B, g.encode(), hashlib.sha256).digest()[:8], "big")
    return [(h1 + i * h2) % BITS for i in range(K)]


POSITIONS = {g: positions(g) for g in BIGRAMS}


def clk(vin):
    """A 1024-bit Bloom filter of the VIN's bigrams (a CLK)."""
    bits = np.zeros(BITS, bool)
    for g in grams(vin):
        bits[POSITIONS[g] if g in POSITIONS else positions(g)] = True
    return np.packbits(bits).view(np.uint64)


def exact_bigrams(vin):
    """The exact bigram set as a bit vector: no hashing, so no collisions."""
    bits = np.zeros(len(BIGRAMS) + (-len(BIGRAMS)) % 64, bool)
    for g in grams(vin):
        if g in BIGRAMS:
            bits[BIGRAMS[g]] = True
    return np.packbits(bits).view(np.uint64)


def encode(vins, f):
    return np.stack([f(v) for v in vins])


def best_links(cars, contracts, enc_cars, enc_con, threshold):
    """For each contract, its best car registered within WINDOW days of its start, by Dice; one to one, best first."""
    ones_car = np.bitwise_count(enc_cars).sum(axis=1)
    ones_con = np.bitwise_count(enc_con).sum(axis=1)
    reg = cars["registration_date"].to_numpy("datetime64[D]")
    order = np.argsort(reg)
    reg_sorted = reg[order]
    start = contracts["start_date"].to_numpy("datetime64[D]")
    best_car, best_score = np.full(len(contracts), -1), np.zeros(len(contracts))
    for day in np.unique(start):
        ci = np.flatnonzero(start == day)
        lo, hi = np.searchsorted(reg_sorted, [day - np.timedelta64(WINDOW, "D"), day + np.timedelta64(WINDOW + 1, "D")])
        cand = order[lo:hi]
        if not len(cand):
            continue
        inter = np.bitwise_count(enc_con[ci][:, None, :] & enc_cars[cand][None, :, :]).sum(axis=2)
        dice = 2 * inter / (ones_con[ci][:, None] + ones_car[cand][None, :])
        j = dice.argmax(axis=1)
        best_car[ci], best_score[ci] = cand[j], dice[np.arange(len(ci)), j]
    links = pd.DataFrame({"contract": np.arange(len(contracts)), "car": best_car, "score": best_score})
    links = links[(links["car"] >= 0) & (links["score"] >= threshold)].sort_values("score", ascending=False)
    links = links.drop_duplicates("car")  # one to one: a car keeps its best contract
    out = pd.Series(-1, index=np.arange(len(contracts)))
    out[links["contract"].to_numpy()] = cars["car_id"].to_numpy()[links["car"].to_numpy()]
    return out.to_numpy(), best_car, best_score


def accuracy(linked, truth):
    real = truth.notna().to_numpy()
    got = linked >= 0
    right = got & (linked == truth.fillna(-2).to_numpy())
    return {"contracts": len(truth), "linked": int(got.sum()), "right car": int(right.sum()),
            "wrong car": int((got & ~right).sum()), "missed": int((real & ~got).sum()),
            "precision (%)": round(100 * right.sum() / max(got.sum(), 1), 2),
            "recall (%)": round(100 * right.sum() / real.sum(), 2)}


def fleet_check(world, link_car, contracts):
    """Every fleet claim on a known car, by the type of contract M2 linked to that car. The claim's car is taken from
    the truth table here, because this scores the fleet source alone; in the pipeline it comes from layers 1 and 2."""
    from layer1_keys import with_family
    from spec import LEAKS, canonical_table
    claims = pd.concat([canonical_table(pd.read_parquet(world / f"x1_system_{s.lower()}.parquet"), s) for s in "AB"],
                       ignore_index=True)
    t = pd.read_parquet(world / "x1_truth.parquet")
    c = with_family(claims)[["claim_id", "family"]].merge(t, on="claim_id")
    fleet = c[c["family"].eq("fleet") & c["car_id"].notna()]
    ctype = pd.Series(contracts["contract_type"].to_numpy(), index=link_car)
    ctype = ctype[ctype.index >= 0]
    got = fleet["car_id"].astype("int64").map(ctype)
    outcome = np.where(got.eq("fleet lease"), "verified", np.where(got.eq("private finance"), "contradicted",
                                                                   "unverified"))
    leak = fleet["is_leak"].astype(bool) if "is_leak" in fleet else fleet["label"].isin(LEAKS)
    return pd.crosstab(pd.Series(outcome, name="outcome"), pd.Series(np.where(leak, "leak", "legitimate"),
                                                                        name="claim"))


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def main():
    method_rows, sens_rows, fleet_sections = [], [], []
    for name, folder in WORLDS:
        w = DATA / folder
        cars = pd.read_parquet(w / "x1_master.parquet")[["car_id", "vin", "registration_date"]]
        con = pd.read_parquet(w / "x1_finance_contracts.parquet")
        truth = con["car_id_truth"].astype("Float64")
        vin_car = dict(zip(cars["vin"], cars["car_id"]))
        m0 = con["vin"].map(vin_car).fillna(-1).astype(int).to_numpy()
        key = lambda v: hmac.new(KEY_A, v.encode(), hashlib.sha256).hexdigest()  # noqa: E731
        hashed = {key(v): c for v, c in zip(cars["vin"], cars["car_id"])}
        m1 = np.array([hashed.get(key(v), -1) for v in con["vin"]])
        e2c, e2k = encode(cars["vin"], clk), encode(con["vin"], clk)
        e3c, e3k = encode(cars["vin"], exact_bigrams), encode(con["vin"], exact_bigrams)
        m2, bc2, bs2 = best_links(cars, con, e2c, e2k, THRESHOLD)
        m3, _, _ = best_links(cars, con, e3c, e3k, THRESHOLD)
        for label, linked in (("M0 clear exact", m0), ("M1 keyed hash, exact", m1), ("M2 Bloom filter (CLK)", m2),
                              ("M3 clear bigram Dice", m3)):
            method_rows.append([f"{name} · {label}", *accuracy(linked, truth).values()])
        for t in SENSITIVITY:
            linked, _, _ = best_links(cars, con, e2c, e2k, t)
            a = accuracy(linked, truth)
            sens_rows.append([f"{name} · M2 at {t}", a["linked"], a["wrong car"], a["missed"], a["precision (%)"],
                              a["recall (%)"]])
        pd.DataFrame({"contract_id": con["contract_id"], "car_id": m2, "score": bs2,
                      "contract_type": con["contract_type"]}).to_parquet(w / "x1_finance_links.parquet", index=False)
        fc = fleet_check(w, m2, con)
        fleet_sections.append(table(["world and outcome"] + list(fc.columns),
                                    [[f"{name} · {i}", *r] for i, r in zip(fc.index, fc.to_numpy().tolist())]))

    OUT.write_text(f"""# X1 part 9: privacy-preserving linkage across the finance JV boundary

_Generated by `leak1/linkage.py`. Synthetic worlds; they measure the tool, not the group._

Each JV contract is linked to the OEM's car record four ways. M0 is the clear reference (not allowed across the
boundary), M1 a keyed hash of the VIN, M2 a keyed Bloom-filter encoding compared by Dice (1024 bits, 20 hashes per
bigram), M3 the same Dice on the exact bigrams with no hashing. A contract is compared with cars registered within
{WINDOW} days of its start, and links to its best car at Dice {THRESHOLD} or more, one to one.

## Linkage accuracy

{table(["world and method", "contracts", "linked", "right car", "wrong car", "missed", "precision (%)", "recall (%)"],
       method_rows)}

## M2's threshold ({THRESHOLD} fixed in advance)

{table(["world and threshold", "linked", "wrong car", "missed", "precision (%)", "recall (%)"], sens_rows)}

## The fleet check it enables

Every fleet claim, by what M2 linked to its car: a fleet lease verifies it, a private contract contradicts it, no
contract leaves it unverified.

{(chr(10) * 2).join(fleet_sections)}
""")
    print(OUT.read_text())


if __name__ == "__main__":
    main()
