"""X1 part 8, layer 4: an LLM reviews the middle band, with "select" prompts. Does it beat the plain rule (A9)?

Layer 2 (Splink) links most claims whose key is broken, and leaves a middle band it cannot decide: claims with at
least one candidate car, none of which passes the decision rule. Today those go to a person. This layer asks an LLM
to pick the claim's car from its candidates, or none, the "select" strategy that beat plain match/no-match prompting
across 10 LLMs and 8 datasets (Wang et al., COLING 2025, https://aclanthology.org/2025.coling-main.8/).

**Fixed before any LLM answer existed:**
  - the band: layer 1's unknown-key claims that Splink's decision rule does not accept, with at least one candidate
    at match probability 0.01 or more (Splink's own prediction floor). Claims with no candidate stay unmatched for
    every method;
  - the candidates: Splink's five most likely cars per claim, shown under letters in random order, so the letter
    says nothing about Splink's ranking;
  - the prompt (`INSTRUCTIONS`): the error types a claims team knows about, no rates, and both costs of a mistake;
  - the decision: a claim is linked to the car the LLM names; "none" leaves it for a person. Confidence is recorded
    and shown as a sensitivity, never used to choose;
  - the worlds: part 6b's stress levels 1 and 2 (level 0 has almost no middle band);
  - the comparator on the same band: the plain rule (same dealer, key within two edits, closest car wins).
The LLM sees only the batch files: no car ids, no labels, no truth. The letter key sits in a separate file the LLM
never reads. Truth is read only by `score`.

**Who answers.** No API key was available, so the LLM under test is Claude Sonnet run as agents in a Claude Code
workflow, each reading one batch file and nothing else (their tool calls are audited). Answers are cached in
`x1_llm/answers.json`, so scoring re-runs without the LLM. In production the same prompt would go through the API
one claim at a time; here a batch holds up to 40 claims, which, if anything, handicaps the LLM.

Usage: .venv/bin/python leak1/layer4_llm.py prepare   (writes the batches, the letter key and the band)
       .venv/bin/python leak1/layer4_llm.py score     (reads the answers; writes leak1/x1_llm_report.md)
All figures are synthetic. They measure the tool, not the group.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import stress  # noqa: E402
from generate import SYN  # noqa: E402
from layer1_keys import layer1, load  # noqa: E402
from layer2_splink import (BAND, accepted, anchor_m, records, resolve, rule_candidates,  # noqa: E402
                           train)
from score import score as score_flags  # noqa: E402
from spec import PROGRAMMES  # noqa: E402

OUT = SYN / "x1_llm"
REPORT = HERE / "x1_llm_report.md"
LEVELS = [1, 2]
TOP_K = 5
FLOOR = 0.01
BATCH = 40
SEED = 88  # part 8: the letter order
INSTRUCTIONS = """You are checking dealer incentive claims for a car maker. Each claim was filed by a dealer for one
specific new car, but its key (the VIN, or in system B the order number) did not match any car exactly, so a
matching model proposed up to five candidate cars. For each item, decide which candidate is the car the claim was
filed for, or answer "none".

What you should know:
- System A counts a sale when the car is registered, so its sale-event date is the registration date. System B
  counts a sale when the order is signed, so its sale-event date is the order date. B claims may have no VIN.
- Keys are sometimes mistyped: one or more characters wrong in the VIN or the order number.
- Sale-event dates are sometimes keyed a few days off, or with day and month swapped.
- Percentage programmes are sometimes paid on an invoice price that differs from the list price, so the implied
  price can be a little off the car's list price.
- A claim is occasionally filed under another dealer's code.
- Some claims are for orders that never became a registered car. For those, no candidate is right: answer "none".
- Linking a claim to the wrong car can pay money that is not owed. Answering "none" for a genuine claim sends it
  to a person for review. Both are mistakes; choose the answer you believe is correct.

Answer every item with its item id, your choice (a candidate letter, or "none") and your confidence (high, medium
or low)."""


def fmt_date(d):
    return "none" if pd.isna(d) else pd.Timestamp(d).strftime("%Y-%m-%d")


def top_candidates(linker):
    """Every claim's candidate cars at match probability FLOOR or more, most likely first."""
    p = linker.inference.predict(threshold_match_probability=FLOOR).as_pandas_dataframe()
    left_is_claim = p["source_dataset_l"].eq("claims")
    p["claim_id"] = p["unique_id_l"].where(left_is_claim, p["unique_id_r"])
    p["car_id"] = p["unique_id_r"].where(left_is_claim, p["unique_id_l"]).astype("int64")
    p = p.sort_values(["claim_id", "match_weight", "car_id"], ascending=[True, False, True])
    return p.groupby("claim_id").head(TOP_K)[["claim_id", "car_id", "match_probability"]]


def world(level):
    """The stressed world at a level, layer 1, Splink's decisions and candidates, and the rule's decisions."""
    claims, master = load()
    truth, dealers = (pd.read_parquet(SYN / f"x1_{n}.parquet") for n in ["truth", "dealers"])
    c, m, t, _, _ = stress.stressed(level, claims, master, truth, dealers)
    l1, _ = layer1(c, m)
    band_ids = l1.loc[l1["reason"].isin(BAND), "claim_id"]
    left, right = records(c[c["claim_id"].isin(band_ids)], m, dealers)
    mm, _ = anchor_m(c, m, dealers, l1)
    linker = train(left, right, mm)
    cand = top_candidates(linker)
    best = cand.drop_duplicates("claim_id").set_index("claim_id")
    # Splink's decision rule needs the evidence share over all candidates: layer 2's own function computes it
    from layer2_splink import best_candidates
    splink = accepted(best_candidates(linker))
    rule = rule_candidates(left, right)
    middle = sorted(set(best.index) - set(splink.index))
    return c, m, t, dealers, l1, band_ids, cand, splink, rule, middle


def item_text(item, claim, cands, letters, master, dealers):
    """One claim and its candidates, as the LLM sees them."""
    prog = PROGRAMMES.set_index(["system", "code"]).loc[(claim["system"], claim["programme"])]
    code_col = "code_a" if claim["system"] == "A" else "code_b"
    code = dealers.set_index("dealer_id")[code_col]
    if prog["basis"] == "pct_list":
        rule = f"{prog['amount']:.1%} of the car's list price"
        price = f"; implied list price EUR {claim['amount_net'] / prog['amount']:,.0f}"
    else:
        rule, price = f"a flat EUR {prog['amount']:,.0f}", ""
    event = "registration" if claim["system"] == "A" else "order signed"
    lines = [f"Item {item}",
             f"Claim, system {claim['system']}: dealer {claim['dealer']}; VIN {claim['vin'] if pd.notna(claim['vin']) else 'none'}; "
             f"order number {claim['order_no'] if pd.notna(claim['order_no']) else 'none'}; sale event ({event}) "
             f"{fmt_date(claim['event_date'])}; filed {fmt_date(claim['claim_date'])}; programme {claim['programme']} "
             f"({rule}); amount EUR {claim['amount_net']:,.2f} net{price}"]
    car = master.set_index("car_id")
    for letter, car_id in zip(letters, cands):
        r = car.loc[car_id]
        d = code.get(r["dealer_id"])
        dealer = d if pd.notna(d) else f"not on system {claim['system']}"
        lines.append(f"  {letter}: VIN {r['vin']}; order number {r['order_no'] if pd.notna(r['order_no']) else 'none'}; "
                     f"dealer {dealer}; brand system {r['system']}; registered {fmt_date(r['registration_date'])}; "
                     f"ordered {fmt_date(r['order_date'])}; list price EUR {r['list_price_eur']:,.0f}")
    return "\n".join(lines)


def prepare():
    OUT.mkdir(exist_ok=True)
    rng = np.random.default_rng(SEED)
    key, band_rows, batches = [], [], []
    for level in LEVELS:
        c, m, t, dealers, l1, band_ids, cand, splink, rule, middle = world(level)
        byc = c.set_index("claim_id")
        texts = []
        for n, claim_id in enumerate(middle, 1):
            item = f"L{level}-{n:04d}"
            cars = cand.loc[cand["claim_id"].eq(claim_id), "car_id"].tolist()
            order = rng.permutation(len(cars))
            letters = "ABCDE"[:len(cars)]
            shown = [cars[i] for i in order]
            key += [{"item": item, "level": level, "claim_id": claim_id, "letter": ltr, "car_id": int(cid)}
                    for ltr, cid in zip(letters, shown)]
            band_rows.append({"item": item, "level": level, "claim_id": claim_id, "candidates": len(cars)})
            texts.append(item_text(item, byc.loc[claim_id], shown, letters, m, dealers))
        for b in range(0, len(texts), BATCH):
            name = f"batch_L{level}_{b // BATCH + 1:02d}.txt"
            (OUT / name).write_text(INSTRUCTIONS + "\n\n" + "\n\n".join(texts[b:b + BATCH]) + "\n")
            batches.append(name)
        print(f"level {level}: band {len(band_ids):,}, Splink accepts {len(splink):,}, middle band {len(middle):,}, "
              f"{len(texts) and -(-len(texts) // BATCH)} batches")
    pd.DataFrame(key).to_parquet(OUT / "letter_key.parquet", index=False)
    pd.DataFrame(band_rows).to_parquet(OUT / "middle_band.parquet", index=False)
    (OUT / "batches.json").write_text(json.dumps(batches))
    print(f"wrote {len(batches)} batches to {OUT}")


def link_table(ids, suggested, truth, cand):
    """Scorer-side: each method's decision on the middle band against the truth."""
    t = truth.set_index("claim_id").loc[ids]
    got = pd.Series(ids, index=ids).map(suggested)
    real = t["car_id"].notna()
    right = real & got.eq(t["car_id"]).fillna(False)
    ceiling = pd.Series([t.at[i, "car_id"] in set(cand.loc[cand["claim_id"].eq(i), "car_id"]) for i in ids], index=ids)
    return {"claims": len(ids), "real claims": int(real.sum()), "true car among candidates": int(ceiling.sum()),
            "right car": int(right.sum()), "wrong car": int((real & got.notna() & ~right).sum()),
            "no car": int((real & got.isna()).sum()), "phantoms linked": int((~real & got.notna()).sum()),
            "phantoms held": int((~real & got.isna()).sum())}


def answers():
    """The cached answers, first pass and repeat, keyed by item."""
    a = json.loads((OUT / "answers.json").read_text())
    first = {r["item"]: r for batch in a["first"] for r in batch}
    repeat = {r["item"]: r for batch in a["repeat"] for r in batch}
    return first, repeat


def score():
    key = pd.read_parquet(OUT / "letter_key.parquet")
    band = pd.read_parquet(OUT / "middle_band.parquet")
    first, repeat = answers()
    assert set(first) <= set(band["item"]), "an answer for an item that is not in the band"
    done = [lv for lv in LEVELS if set(band.loc[band["level"].eq(lv), "item"]) <= set(first)]
    partial = {lv: (int(band.loc[band["level"].eq(lv), "item"].isin(list(first)).sum()), int(band["level"].eq(lv).sum()))
               for lv in LEVELS if lv not in done}
    rows, links, pipes = [], [], []
    for level in done:
        c, m, t, dealers, l1, band_ids, cand, splink, rule, middle = world(level)
        b = band[band["level"].eq(level)]
        assert b["claim_id"].tolist() == middle, "the world must rebuild the same middle band"
        k = key[key["level"].eq(level)].set_index(["item", "letter"])["car_id"]
        items = list(zip(b["item"], b["claim_id"]))

        def pick(keep):  # the LLM's chosen car per claim, for the answers `keep` accepts
            return pd.Series({cid: k[(item, first[item]["choice"])] for item, cid in items
                              if first[item]["choice"] != "none" and keep(first[item])}, dtype="int64")

        llm, llm_high = pick(lambda a: True), pick(lambda a: a["confidence"] == "high")
        rule_mid = rule[rule.index.isin(middle)]
        for name, sug in [("Splink (holds the whole band)", pd.Series(dtype="int64")), ("plain rule", rule_mid),
                          ("LLM, select", llm), ("LLM, high confidence only", llm_high)]:
            links.append({"level": level, "method": name, **link_table(middle, sug, t, cand)})
        for name, sug in [("Splink", splink), ("Splink + plain rule on the band", pd.concat([splink, rule_mid])),
                          ("Splink + LLM on the band", pd.concat([splink, llm])),
                          ("Splink + LLM, high confidence only", pd.concat([splink, llm_high]))]:
            h, _, _ = score_flags(resolve(c, m, l1, sug), t)
            pipes.append({"level": level, "pipeline": name, "flagged": h["flagged"],
                          "precision (%)": round(100 * h["precision"], 1), "recall (%)": round(100 * h["recall"], 1),
                          "false alarms per 1,000 legitimate": round(h["false_alarms_per_1000_legit"], 2),
                          "review load per 1,000 claims": round(h["review_load_per_1000"], 1)})
        rows.append({"level": level, "band": len(band_ids), "Splink accepts": len(splink), "middle band": len(middle)})
    scored = band.loc[band["level"].isin(done), "item"]
    conf = pd.Series([first[i]["confidence"] for i in scored]).value_counts().reindex(["high", "medium", "low"],
                                                                                   fill_value=0)
    choice = pd.Series([first[i]["choice"] != "none" for i in scored]).value_counts().reindex([True, False],
                                                                                            fill_value=0)
    per_item = len(INSTRUCTIONS) / BATCH + np.mean([len(t) for t in "".join(
        (OUT / n).read_text()[len(INSTRUCTIONS):] for n in json.loads((OUT / "batches.json").read_text())
    ).split("\n\nItem ")[1:]])
    return rows, links, pipes, partial, conf, choice, per_item, len(repeat)


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def report():
    rows, links, pipes, partial, conf, choice, per_item, repeats = score()
    not_run = "; ".join(f"level {lv}: {a} of {n} items answered" for lv, (a, n) in partial.items())
    REPORT.write_text(f"""# X1 part 8: an LLM on the middle band, with "select" prompts (A9)

_Generated by `leak1/layer4_llm.py score`. **Synthetic.** It measures the tool in our world under part 6b's noise, not
the group; the ranking is the finding, not the levels (A14)._

The middle band is the claims whose key is broken and that Splink's decision rule leaves unlinked although it has at
least one candidate car. The LLM (Claude Sonnet, run as blind agents that read only the batch files) picks one of up to
five candidates, shown in random order, or none. The plain rule is the same-dealer, two-edit rule of part 6. Every
setting was fixed before any answer existed (see the script's docstring).

**Not run, and why:** the session's usage limit stopped the agents before {not_run}, and before the planned repeat of
four batches (the consistency check; {repeats} repeated answers exist). Only fully answered levels are scored.

## The band

{table(["level", "band (layer 1's broken keys)", "Splink accepts", "middle band"], [list(r.values()) for r in rows])}

## Decisions on the middle band

"True car among candidates" is the most any select method could get right. A phantom is an order that never became a
car: linking it pays a claim that is not owed.

{table(["level and method"] + list(links[0])[2:], [[f"level {r['level']} · {r['method']}"] + list(r.values())[2:]
                                                   for r in links])}

## The whole pipeline

Layers 1 and 2, with the middle band decided by each method. A flag means "do not pay as filed".

{table(["level and pipeline"] + list(pipes[0])[2:], [[f"level {r['level']} · {r['pipeline']}"] + list(r.values())[2:]
                                                     for r in pipes])}

## The LLM's answers (scored levels)

Chose a car: {int(choice[True])}; answered none: {int(choice[False])}. Confidence: high {int(conf['high'])}, medium
{int(conf['medium'])}, low {int(conf['low'])}.

**Cost:** an item averages about {per_item:,.0f} characters of prompt, the instructions shared across a batch
included. Tokens and euros need the API's own count, which this run did not have.
""")
    print(REPORT.read_text())


if __name__ == "__main__":
    {"prepare": prepare, "score": report}[sys.argv[1]]()
