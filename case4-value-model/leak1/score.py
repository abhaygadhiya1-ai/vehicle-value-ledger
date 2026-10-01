"""X1 scorer: how well a layer's flags match the truth table. Shared by every layer (parts 5-8) and part 10.

A flag says "do not pay this claim as filed". Scoring is per claim, and strict: flagging the original of a duplicate
instead of the copy counts as one false alarm and one miss, even though the euros are the same.

  precision     leak claims among flagged claims
  recall        flagged leak claims among leak claims, per leak type
  euro recall   leak euros on flagged claims among all leak euros
  false alarms  flagged claims that are clean or legitimate, per 1,000 such claims, by label
  review load   flagged claims per 1,000 claims: the work someone must check

All figures are synthetic. They measure the tool, not the group.
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from generate import SYN  # noqa: E402
from spec import LEAKS  # noqa: E402


def score(flags, truth=None):
    """`flags`: claim_id and reason (NA when the claim passes). Returns (headline, by_label, by_reason)."""
    truth = pd.read_parquet(SYN / "x1_truth.parquet") if truth is None else truth
    t = truth.merge(flags[["claim_id", "reason"]], on="claim_id", how="left", validate="one_to_one")
    assert len(t) == len(truth) == len(flags), "flags must cover every claim exactly once"
    t["flagged"] = t["reason"].notna()
    # a truth table from another author (the red team) marks its own leak labels in `is_leak`
    t["leak"] = t["is_leak"].astype(bool) if "is_leak" in t else t["label"].isin(LEAKS)
    t["caught_eur"] = t["leak_eur"].where(t["flagged"], 0.0)

    flagged, leaks = t["flagged"].sum(), t["leak"].sum()
    tp = (t["flagged"] & t["leak"]).sum()
    headline = {
        "claims": len(t), "flagged": int(flagged),
        "precision": tp / flagged if flagged else float("nan"),
        "recall": tp / leaks,
        "euro_recall": t["caught_eur"].sum() / t["leak_eur"].sum(),
        "false_alarms_per_1000_legit": 1000 * (t["flagged"] & ~t["leak"]).sum() / (~t["leak"]).sum(),
        "review_load_per_1000": 1000 * flagged / len(t),
    }
    by_label = t.groupby("label").agg(claims=("claim_id", "size"), flagged=("flagged", "sum"),
                                      leak_eur=("leak_eur", "sum"), caught_eur=("caught_eur", "sum"))
    by_label["flag_rate"] = by_label["flagged"] / by_label["claims"]
    by_label["euro_recall"] = by_label["caught_eur"] / by_label["leak_eur"]
    by_label["is_leak"] = t.groupby("label")["leak"].any()
    f = t[t["flagged"]]
    by_reason = f.groupby("reason").agg(flagged=("claim_id", "size"), leaks=("leak", "sum"))
    by_reason["precision"] = by_reason["leaks"] / by_reason["flagged"]
    by_reason["labels"] = f.groupby("reason")["label"].agg(lambda s: s.value_counts().head(3).to_dict())
    return headline, by_label, by_reason


def show(flags, title):
    headline, by_label, by_reason = score(flags)
    h = headline
    print(f"{title}: flagged {h['flagged']:,} of {h['claims']:,} claims | precision {h['precision']:.1%} | "
          f"recall {h['recall']:.1%} | euro recall {h['euro_recall']:.1%} | false alarms "
          f"{h['false_alarms_per_1000_legit']:.2f} per 1,000 legitimate claims | review load "
          f"{h['review_load_per_1000']:.1f} per 1,000 claims")
    leak_rows = by_label["is_leak"].to_numpy()
    print("\nleaks, by type:")
    print(by_label[leak_rows][["claims", "flagged", "flag_rate", "euro_recall"]]
          .sort_values("claims", ascending=False).round(3).to_string())
    print("\nfalse alarms, by legitimate label:")
    print(by_label[~leak_rows][["claims", "flagged", "flag_rate"]].round(4).to_string())
    print("\nflags, by reason:")
    print(by_reason.round(3).to_string())
    return headline
