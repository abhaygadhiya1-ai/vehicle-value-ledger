"""X1 part 10: the scorecard. Every world and every layer, scored by the same strict scorer (`score.py`).

Runs, one per world and code version:
  Ours           our world (data/synthetic), today's code
  RT1 post hoc   blind red-team round 1's world, today's code. There is no blind run: round 1's code was never
                 frozen, and the fixes that followed it changed three detector files.
  RT2 blind      round 2's world, the code as frozen before the round: the tag `redteam2-frozen` in this folder's
                 local git repo, checked against `frozen_detector_hashes.txt`
  RT2 post hoc   round 2's world, today's code (adds `wrong_amount`, and reads dealer and order date from the OEM)

Stages are cumulative, in the order a claim meets them:
  keys           layer 1: exact keys, credit-note netting, duplicates
  + matching     layer 2: Splink on the claims layer 1 could not link
  + hard rules   layer 3 without its statistical rule
  + gaming rule  layer 3's hard rules and its statistical timing rule
  + keeper check adds part 7b's register keeper check (today's code, worlds with a keeper file)
  + contract check adds part 9's fleet check against the JV's contracts, linked privately (today's code, worlds with
                 a contract file): `contract_contradicted` and `fleet_unverified`, both held for review
  + complete sources  layer 3 in full: adds the two review rules on the sources written after round 3 (`sources.py`),
                 `first_keeper_suspect` and `order_change_suspect`. Those sources also feed hard rules (the dealer at
                 the sale event, the trade-in's holding period), so from them on "+ hard rules" moves too.

Review load is also counted by unit (part 10b). The gaming rule holds every volume claim of a flagged dealer-quarter,
so its unit is the dealer-quarter; every other flag is one claim.

Matching under noise (part 10c): the part 6b stress test, run through `stress.py`'s own functions on our world, ranks
Splink against the plain rule at noise levels 0-2. Each run's final flags carry a content hash, so two byte-identical
reports mean identical flags. Timings vary by machine, so they live in `runtime.py` and its own report.

Each run happens in a child process with X1_DATA pointing at its world. Nothing is written into any world's folder:
the layer scripts save their flags, this does not.

Checks: the frozen code matches the recorded hashes; in every run, the gaming rule only adds `gaming_suspect` flags.
Every claim whose flag differs between round 2 blind and post hoc is tabulated by its two flags.

All figures are synthetic. They measure the tool, not the group, and the catch rates are unit tests of our own code,
not evidence of real performance (skeptic A14). The register takes only rankings, failures and engineering facts.

Output: leak1/x1_scorecard_report.md
Usage: .venv/bin/python leak1/scorecard.py
"""
import hashlib
import inspect
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
REPORT = HERE / "x1_scorecard_report.md"
FROZEN = {"redteam2-frozen": "synthetic_redteam2", "redteam3-frozen": "synthetic_redteam3",
          "redteam4-frozen": "synthetic_redteam4"}  # tag: its hash file
DETECTORS = ["spec", "generate", "layer1_keys", "layer2_splink", "layer3_rules", "score", "linkage"]
RUNS = [  # name, world, code tag (None means today's code)
    ("Ours", "synthetic", None),
    ("RT1 post hoc", "synthetic_redteam", None),
    ("RT2 blind", "synthetic_redteam2", "redteam2-frozen"),
    ("RT2 post hoc", "synthetic_redteam2", None),
]
if (DATA / "synthetic_redteam3" / "x1_master.parquet").exists():  # blind round 3, once the red team's world is in
    RUNS += [("RT3 blind", "synthetic_redteam3", "redteam3-frozen"), ("RT3 post hoc", "synthetic_redteam3", None)]
if (DATA / "synthetic_redteam4" / "x1_master.parquet").exists():  # blind round 4, the same way
    RUNS += [("RT4 blind", "synthetic_redteam4", "redteam4-frozen"), ("RT4 post hoc", "synthetic_redteam4", None)]
STAGES = ["keys", "+ matching", "+ hard rules", "+ gaming rule", "+ keeper check", "+ contract check",
          "+ complete sources"]
STAGE_RULES = {"+ keeper check": ["self_registration_suspect"],  # the review rules each later stage adds
               "+ contract check": ["contract_contradicted", "fleet_unverified"],
               "+ complete sources": ["first_keeper_suspect", "order_change_suspect"]}
NEW_SOURCES = {"transfers": "oem_transfers", "orders": "oem_order_log", "first_keepers": "register_first_keeper",
               "tradein_keepers": "register_tradein_keepers"}  # after round 3: argument name -> file


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def worker(code, out):
    """In a child process: layers 1-3 on the world X1_DATA names, with the code in `code`. Saves scores and flags."""
    sys.path.insert(0, str(code))
    # last, so detectors still come from `code`: frozen code runs from a temp folder, and from round 4 on it imports
    # linkage -> population -> build_reference, which lives in the project root
    sys.path.append(str(HERE.parent))
    import layer1_keys as k1
    import layer2_splink as k2
    import layer3_rules as k3
    from generate import SYN
    from score import score
    from spec import LEAKS
    for mod in (k1, k2, k3):
        assert Path(mod.__file__).parent == Path(code), f"{mod.__name__} imported from the wrong folder"

    claims, master = k1.load()
    dealers, truth, targets, tradeins = (pd.read_parquet(SYN / f"x1_{n}.parquet")
                                         for n in ["dealers", "truth", "targets", "register_tradeins"])
    t0 = time.perf_counter()
    f1, _ = k1.layer1(claims, master)
    t1 = time.perf_counter()
    band = f1.loc[f1["reason"].isin(k2.BAND), "claim_id"]
    left, right = k2.records(claims[claims["claim_id"].isin(band)], master, dealers)
    suggested = pd.Series(dtype="int64")
    if len(left):
        m, _ = k2.anchor_m(claims, master, dealers, f1)
        suggested = k2.accepted(k2.best_candidates(k2.train(left, right, m)))
    f2 = k2.resolve(claims, master, f1, suggested)
    t2 = time.perf_counter()
    sources = {n: pd.read_parquet(SYN / f"x1_{f}.parquet") for n, f in NEW_SOURCES.items()
               if (SYN / f"x1_{f}.parquet").exists()}
    if hasattr(k3, "trusted_record"):  # today's code reads dealer and order date from the OEM; frozen code cannot
        extra = {}
        params = inspect.signature(k3.trusted_record).parameters
        if "prices" in params and (SYN / "x1_oem_prices.parquet").exists():
            extra["prices"] = pd.read_parquet(SYN / "x1_oem_prices.parquet")  # after round 3, post hoc
        extra.update({n: sources[n] for n in ("transfers", "orders") if n in params and n in sources})
        master = k3.trusted_record(master, pd.read_parquet(SYN / "x1_oem_record.parquet"), **extra)
    kw = {}
    if hasattr(k3, "self_registration_suspects") and (SYN / "x1_register_keepers.parquet").exists():
        kw["keepers"] = pd.read_parquet(SYN / "x1_register_keepers.parquet")
    if hasattr(k3, "contract_types") and (SYN / "x1_finance_contracts.parquet").exists():
        kw["contracts"] = pd.read_parquet(SYN / "x1_finance_contracts.parquet")
    kw.update({n: sources[n] for n in ("first_keepers", "orders", "tradein_keepers")
               if n in inspect.signature(k3.layer3).parameters and n in sources})
    f3, broken, suspects = k3.layer3(claims, master, f2, targets, tradeins, **kw)
    seconds = {"layer 1": t1 - t0, "layer 2": t2 - t1, "layer 3": time.perf_counter() - t2}

    def upto(cols):
        """Layer 3 with only these rule columns: each live claim's first broken rule, as layer3() assigns it."""
        b = broken[[c for c in cols if c in broken]]
        first = pd.Series(b.idxmax(axis=1).where(b.any(axis=1)).to_numpy(), index=broken["claim_id"].to_numpy())
        return f2.assign(reason=f2["reason"].fillna(f2["claim_id"].map(first)))

    hard = broken[k3.HARD]
    cols = k3.HARD + ["gaming_suspect"]
    fh, fg = upto(k3.HARD), upto(cols)
    fk = upto(cols + STAGE_RULES["+ keeper check"])
    fc = upto(cols + STAGE_RULES["+ keeper check"] + STAGE_RULES["+ contract check"])
    assert upto([c for c in broken.columns if c != "claim_id"])["reason"].fillna("").equals(f3["reason"].fillna(""))
    for before, after, added_rules in ((fh, fg, ["gaming_suspect"]), (fg, fk, STAGE_RULES["+ keeper check"]),
                                       (fk, fc, STAGE_RULES["+ contract check"]),
                                       (fc, f3, STAGE_RULES["+ complete sources"])):
        added = before["reason"].fillna("").ne(after["reason"].fillna(""))
        assert after.loc[added, "reason"].isin(added_rules).all() and before.loc[added, "reason"].isna().all()

    is_leak = truth["is_leak"].astype(bool) if "is_leak" in truth else truth["label"].isin(LEAKS)
    legit = ~broken["claim_id"].map(pd.Series(is_leak.to_numpy(), index=truth["claim_id"])).astype(bool)
    hit = broken.loc[legit.to_numpy() & hard.any(axis=1).to_numpy(), "claim_id"]
    res = {"code": {d: sha(Path(code) / f"{d}.py") if (Path(code) / f"{d}.py").exists() else "absent"
                    for d in DETECTORS}, "hard_on_legit": len(hit),
           "hard_on_legit_originals": int(hit.isin(set(truth.loc[is_leak, "dup_of"].dropna())).sum()), "stages": {},
           "hard_on_legit_changed": int(hit.map(truth.set_index("claim_id")["car_id"]).isin(
               pd.read_parquet(SYN / "x1_truth_master_changes.parquet")["car_id"]).sum())
           if (SYN / "x1_truth_master_changes.parquet").exists() else 0,
           "flags_sha": {}, "seconds": seconds}  # seconds vary by machine: runtime.py reports them, not this

    # the gaming rule holds all the volume claims of a flagged dealer-quarter, so its review unit is the
    # dealer-quarter: the car's recorded dealer and the quarter of its sale event, as layer 3 keys it
    live = k3.live_claims(claims, f2, master)
    held = live[live["claim_id"].isin(fg.loc[fg["reason"].eq("gaming_suspect"), "claim_id"])]
    dq = held.groupby([held["system"], held["dealer_id"], pd.to_datetime(held["car_event"]).dt.to_period("Q")])
    with_leak = dq["claim_id"].agg(lambda s: s.isin(set(truth.loc[is_leak, "claim_id"])).any())
    res["review"] = {"rule_dq": {s: len(suspects[s]) for s in "AB"},
                     "held_dq": {s: int((with_leak.index.get_level_values(0) == s).sum()) for s in "AB"},
                     "held_dq_with_leak": int(with_leak.sum()), "held_claims": len(held),
                     "flagged_before_gaming": int(fh["reason"].notna().sum())}
    assert res["review"]["flagged_before_gaming"] + len(held) == fg["reason"].notna().sum()

    # the full pipeline's review load: the two dealer-quarter rules (gaming, keeper check) are reviewed once per
    # dealer-quarter, whichever rule holds it; every other flag, the contract check's included, once per claim
    dq_rules = ["gaming_suspect", "self_registration_suspect"] + STAGE_RULES["+ complete sources"]
    held_all = live[live["claim_id"].isin(f3.loc[f3["reason"].isin(dq_rules), "claim_id"])]
    dq_all = held_all.groupby([held_all["system"], held_all["dealer_id"],
                               pd.to_datetime(held_all["car_event"]).dt.to_period("Q")])
    dq_all_leak = dq_all["claim_id"].agg(lambda s: s.isin(set(truth.loc[is_leak, "claim_id"])).any())
    per_claim = f3["reason"].notna() & ~f3["reason"].isin(dq_rules)
    res["review_full"] = {"claim_units": int(per_claim.sum()), "dq_units": len(dq_all_leak),
                          "dq_with_leak": int(dq_all_leak.sum()),
                          "contract_claims": int(f3["reason"].isin(STAGE_RULES["+ contract check"]).sum())}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for i, (stage, flags) in enumerate(zip(STAGES, [f1, f2, fh, fg, fk, fc, f3])):
        headline, by_label, _ = score(flags, truth)
        res["stages"][stage] = {"headline": headline, "by_label": by_label.reset_index().to_dict("records")}
        res["flags_sha"][stage] = hashlib.sha256(flags[["claim_id", "reason"]].to_csv(index=False).encode()
                                                 ).hexdigest()[:12]
        flags[["claim_id", "reason"]].to_parquet(out / f"flags_{i}.parquet", index=False)
    (out / "scores.json").write_text(json.dumps(res, default=lambda o: o.item()))


def stress_worker(out):
    """In a child process: the part 6b stress test on our world, through `stress.py`'s own functions."""
    sys.path.insert(0, str(HERE))
    import stress
    from generate import SYN
    from layer1_keys import load
    claims, master = load()
    truth, dealers = (pd.read_parquet(SYN / f"x1_{n}.parquet") for n in ["truth", "dealers"])
    rows, causes = [], []
    for level in stress.LEVELS:
        r, _, _, cz = stress.run_level(level, claims, master, truth, dealers)
        rows += r
        causes += cz
    Path(out).write_text(json.dumps({"rows": rows, "causes": causes}, default=lambda o: o.item()))


def frozen_code(tmp, tag):
    """The detector code as frozen before a blind round, from this folder's local git repo, checked against the
    hashes recorded before the round."""
    tar = subprocess.run(["git", "-C", str(HERE), "archive", tag], check=True, capture_output=True).stdout
    code = Path(tmp) / tag
    tarfile.open(fileobj=io.BytesIO(tar)).extractall(code, filter="data")
    if not (Path(tmp) / "assumptions.csv").exists():  # a rulebook from part 7b on reads the register one folder up
        shutil.copyfile(HERE.parent / "assumptions.csv", Path(tmp) / "assumptions.csv")
    recorded = (DATA / FROZEN[tag] / "frozen_detector_hashes.txt").read_text().split()
    recorded = dict(zip(recorded[1::2], recorded[0::2]))
    assert {f"{d}.py" for d in DETECTORS[:6]} <= set(recorded), "a hash file must cover the six base detectors"
    got = {name: sha(code / name) for name in recorded}  # each round records the detector files it froze
    assert got == recorded, f"frozen code does not match the recorded hashes: {got} vs {recorded}"
    return code


def child(name, world, args):
    p = subprocess.run([sys.executable, __file__, *map(str, args)], capture_output=True, text=True,
                       env={**os.environ, "X1_DATA": str(DATA / world)})
    if p.returncode:
        sys.exit(f"{name} failed:\n{p.stderr[-3000:]}")


def run(name, world, code, tmp):
    out = Path(tmp) / name.replace(" ", "_")
    child(name, world, ["--worker", code, out])
    return json.loads((out / "scores.json").read_text()), out


def stress_run(tmp):
    out = Path(tmp) / "stress.json"
    child("stress", "synthetic", ["--stress", out])
    return json.loads(out.read_text())


def pct(x):
    return "" if x is None or x != x else f"{100 * x:.1f}"


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def report(res, moves, stress):
    leak_rows, legit_rows, head_rows, run_rows, review_rows, full_rows = [], [], [], [], [], []
    for (name, world, tag), (r, _) in zip(RUNS, res):
        v, claims = r["review"], r["stages"]["keys"]["headline"]["claims"]
        units = v["flagged_before_gaming"] + sum(v["held_dq"].values())
        review_rows.append([name, v["flagged_before_gaming"], v["held_claims"], v["held_dq"]["A"], v["held_dq"]["B"],
                            sum(v["held_dq"].values()), v["held_dq_with_leak"], units,
                            f"{1000 * units / claims:.1f}"])
        f = r["review_full"]
        full_units = f["claim_units"] + f["dq_units"]
        full_rows.append([name, f["claim_units"], f["contract_claims"], f["dq_units"], f["dq_with_leak"], full_units,
                          f"{1000 * full_units / claims:.1f}"])
        labels = {s: {b["label"]: b for b in r["stages"][s]["by_label"]} for s in STAGES}
        last = labels[STAGES[-1]]
        leaks = [b for b in last.values() if b["is_leak"]]
        run_rows.append([name, f"data/{world}", tag or "today's", r["stages"]["keys"]["headline"]["claims"],
                         sum(b["claims"] for b in leaks), f"{sum(b['leak_eur'] for b in leaks) / 1e3:,.0f}",
                         r["hard_on_legit"], r["hard_on_legit_originals"], r["hard_on_legit_changed"],
                         r["code"]["layer1_keys"],
                         r["code"]["layer2_splink"], r["code"]["layer3_rules"], r["flags_sha"][STAGES[-1]]])
        for s in STAGES:
            h = r["stages"][s]["headline"]
            head_rows.append([f"{name} · {s}", h["flagged"], pct(h["precision"]), pct(h["recall"]),
                              pct(h["euro_recall"]), f"{h['false_alarms_per_1000_legit']:.2f}",
                              f"{h['review_load_per_1000']:.1f}"])
        for b in sorted(last.values(), key=lambda b: -b["claims"]):
            if b["is_leak"]:
                leak_rows.append([f"{name} · {b['label']}", b["claims"], f"{b['leak_eur'] / 1e3:,.0f}"]
                                 + [pct(labels[s][b["label"]]["flag_rate"]) for s in STAGES] + [pct(b["euro_recall"])])
            else:
                legit_rows.append([f"{name} · {b['label']}", b["claims"]]
                                  + [pct(labels[s][b["label"]]["flag_rate"]) for s in STAGES])

    empty = {name: sum(r["review"]["rule_dq"].values()) - sum(r["review"]["held_dq"].values())
             for (name, _, _), (r, _) in zip(RUNS, res)}
    empty = ("In every run, each dealer-quarter the gaming rule flags holds at least one claim, so the table's counts "
             "are the rule's own." if not any(empty.values()) else
             "Some dealer-quarters the gaming rule flags hold no claim and need no review: " +
             ", ".join(f"{k} {n}" for k, n in empty.items()) + ".")
    stage_cols = [f"{s} (%)" for s in STAGES]
    method = {"layer 1 only": "layer 1 only", "splink": "Splink", "rule": "plain rule"}
    noise_rows = [[f"level {r['level']} · {method[r['method']]}", *(r.get(k, "") for k in
                   ["band", "right_car", "wrong_car", "no_car", "phantom_linked", "phantom_unlinked"]),
                   pct(r["precision"]), pct(r["recall"]), f"{r['false_alarms_per_1000_legit']:.2f}",
                   f"{r['review_load_per_1000']:.1f}"] for r in stress["rows"]]
    cause_rows = [[f"level {c['level']} · {c['noise']}", c["real band claims hit"], pct(c["unlinked, splink"]),
                   pct(c["unlinked, rule"])] for c in stress["causes"]]
    return f"""# X1 scorecard: every world, every layer

**Synthetic.** These figures measure our tool in worlds that we or a blind red team built. They say nothing about the
group's leak rate. The catch rates are unit tests of our own code, not evidence of real performance (skeptic A14).
What carries over is rankings, failures and engineering facts.

Written by `leak1/scorecard.py`; re-run it rather than editing this file.

## The runs

Round 1 has no blind run: its code was never frozen, and the fixes that followed it changed three detector files. Its
blind result survives only as the written record in the X1 notes. Each later round's blind run uses the code frozen
before the round (a tag in this folder's local repo); its detector files match the hashes recorded before the round.

"Hard rules on legitimate claims" counts legitimate live claims that break at least one hard rule. It must be zero in
our world (the self-check). In a red-team world, a non-zero count is a finding, with two exceptions that can be
rightly flagged: a claim labelled legitimate that is the original of a leak claim (the truth table's `dup_of`), and one
on a car whose vehicle record the red team falsified (its own change log), judged against the true record. The X1
notes discuss each case.

{table(["run", "world", "code", "claims", "leak claims", "leak EUR (k)", "hard rules on legitimate claims",
        "of which the original of a leak claim", "of which on a car whose record the red team changed",
        "layer1_keys", "layer2_splink", "layer3_rules",
        "final flags (hash)"], run_rows)}

## Headline, by stage

Stages are cumulative: keys (layer 1), + matching (layer 2), + hard rules (layer 3's hard rules), + gaming rule (its
statistical timing rule), + keeper check (part 7b's register keeper check), + contract check (part 9's fleet check
against the JV's contracts), + complete sources (the review rules on the sources written after round 3; layer 3 in
full). The last four are review rules: they hold a claim for a person to decide. A flag means "do not pay this claim as filed". Scoring is strict and per claim. Frozen code that predates a
rule leaves its stage unchanged.

{table(["run and stage", "flagged", "precision (%)", "recall (%)", "euro recall (%)",
        "false alarms per 1,000 legitimate", "review load per 1,000 claims"], head_rows)}

## Review load, by unit

The gaming rule holds every volume claim of a flagged dealer-quarter: the car's recorded dealer, in the quarter of its
sale event. A reviewer therefore checks the dealer-quarter once, not each held claim. Review units are the claims
flagged before the gaming rule, one each, plus the dealer-quarters holding claims, one each. "With a leak claim" means
at least one held claim is a leak: the dealer-quarter was worth reviewing.

{table(["run", "claims flagged before the gaming rule", "claims held by the gaming rule",
        "dealer-quarters held: A", "dealer-quarters held: B", "dealer-quarters held", "of which with a leak claim",
        "review units",
        "review units per 1,000 claims"], review_rows)}

The full pipeline, counted the same way. The gaming rule, the keeper check and the two complete-source rules hold
dealer-quarters, so a dealer-quarter any of them holds is one unit. Every other flag is one claim, the contract
check's included.

{table(["run", "full pipeline: claims flagged one by one", "full pipeline: of which by the contract check",
        "full pipeline: dealer-quarters held", "full pipeline: of which with a leak claim", "full pipeline: review units",
        "full pipeline: review units per 1,000 claims"], full_rows)}

## Matching under noise: Splink against the plain rule

Our world only, from the part 6b stress test (`stress.py`, run through its own functions). Noise touches only what a
detector reads. Level 0 is the clean world, level 1 uses the rates in `spec.py` (ASSUMPTION settings) and level 2
doubles them. The band is the claims layer 1 could not link: real claims with a broken key, and phantom orders with no
car. The plain rule links a claim to the car of the same dealer whose key is within two edits. The ranking is the
finding, not the levels (A14).

{table(["level and method", "band claims", "right car", "wrong car", "no car", "phantoms linked", "phantoms held",
        "precision (%)", "recall (%)", "false alarms per 1,000 legitimate", "review load per 1,000 claims"],
       noise_rows)}

Where each method fails: of the real band claims hit by each kind of noise, the share left without a car. A claim can
be hit by several kinds.

{table(["level and noise", "real band claims hit", "left without a car, Splink (%)",
        "left without a car, plain rule (%)"], cause_rows)}

## Leaks, by type

The share of each leak type's claims flagged by the end of each stage, and the share of its euros caught in the end.

{table(["run and leak", "claims", "leak EUR (k)"] + stage_cols + ["euro recall (%)"], leak_rows)}

## Legitimate claims, by type

The share of each legitimate label flagged by the end of each stage: the false alarms.

{table(["run and label", "claims"] + stage_cols, legit_rows)}

## Checks that passed

- The frozen code of each blind run matches every hash recorded before its round.
- In every run, adding the gaming rule only adds `gaming_suspect` flags to claims no hard rule flagged, adding the
  keeper check only adds `self_registration_suspect` flags, adding the contract check only adds
  `contract_contradicted` and `fleet_unverified` flags, and adding the complete sources only adds
  `first_keeper_suspect` and `order_change_suspect` flags, each to claims no earlier rule flagged.
- {empty}

## Round 2: what the post-hoc fixes changed

Every claim whose final flag differs between the blind run (frozen code) and the post-hoc run (today's code), by the
two flags. "passed" means no flag. The post-hoc code adds `wrong_amount` and reads each car's dealer and order date
from the OEM's record instead of the dealer-reported one; the red team corrupted both in the record.

{table(["change", "claims", "of which leak claims"], moves)}
"""


def main():
    with tempfile.TemporaryDirectory() as tmp:
        frozen = {tag: frozen_code(tmp, tag) for tag in {t for _, _, t in RUNS if t}}
        res = []
        for name, world, tag in RUNS:
            res.append(run(name, world, frozen[tag] if tag else HERE, tmp))
            h = res[-1][0]["stages"][STAGES[-1]]["headline"]
            print(f"{name}: flagged {h['flagged']:,} of {h['claims']:,} | precision {h['precision']:.1%} | "
                  f"euro recall {h['euro_recall']:.1%}")
        outs = {name: out for (name, _, _), (_, out) in zip(RUNS, res)}
        last = f"flags_{len(STAGES) - 1}.parquet"
        blind, post = (pd.read_parquet(outs[n] / last) for n in ["RT2 blind", "RT2 post hoc"])
        assert blind["claim_id"].equals(post["claim_id"])
        truth = pd.read_parquet(DATA / "synthetic_redteam2" / "x1_truth.parquet").set_index("claim_id")
        changed = blind["reason"].fillna("").ne(post["reason"].fillna("")).to_numpy()
        moves = pd.DataFrame({"change": (blind["reason"].fillna("passed") + " → " + post["reason"].fillna("passed")),
                              "leak": post["claim_id"].map(truth["is_leak"].astype(bool))})[changed]
        moves = moves.groupby("change")["leak"].agg(["size", "sum"]).sort_values("size", ascending=False)
        moves = [[k, int(r["size"]), int(r["sum"])] for k, r in moves.iterrows()]
        stress = stress_run(tmp)
    REPORT.write_text(report(res, moves, stress))
    print(f"wrote {REPORT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--worker"]:
        worker(sys.argv[2], sys.argv[3])
    elif sys.argv[1:2] == ["--stress"]:
        stress_worker(sys.argv[2])
    else:
        main()
