"""Would one flexible model for every moment beat a model per moment?

`field_sets_report.md` settled the fork for linear models: one set of coefficients cannot drop a
stand-in effect - diesel for mileage - once the real field arrives, so it loses on the richest
moment. A gradient-boosted tree does not have that limit. Given a blank where a field is absent, it
can learn different effects for cars with and without that field. This tests whether that closes
the gap.

Same set-up as `field_sets.py`, so the numbers sit side by side: the same qualifying datasets and
training halves, the same held-out cars, the held-out dataset always supplying its own price level.
Three models per test:

  linear, per moment    the per-moment pooled model from field_sets.py
  boosted, per moment   a gradient-boosted model per moment, on the same pooled rows
  boosted, one model    one gradient-boosted model over every moment's rows, absent fields blank

Training rows are capped at MAX_TRAIN per fit, drawn at random with a fixed seed.

Usage: .venv/bin/python analysis/one_model_gbm.py   (a minute or two)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).parent))
from field_sets import EUROPE, MIN_ROWS, MOMENTS, load, run_moment, same_market  # noqa: E402
from drivers import md_table  # noqa: E402

OUT = Path(__file__).parent / "one_model_gbm_report.md"
SEED = 0
MAX_TRAIN = 400_000


def boosted():
    return HistGradientBoostingRegressor(random_state=SEED)


def stack(blocks, names, rng):
    """Every block's training rows on the union of columns, absent fields blank, capped in size.

    Each block is sampled at the same rate before stacking, so the cap never needs the full stack
    in memory and every block keeps its share of the rows.
    """
    rate = min(1.0, MAX_TRAIN / sum(len(v["y_tr"]) for v in blocks))
    Xs, ys = [], []
    for v in blocks:
        pick = rng.random(len(v["y_tr"])) < rate
        Xs.append(pad(v["X_tr"][pick], v["cols"], names))
        ys.append(v["y_tr"][pick])
    return np.vstack(Xs), np.concatenate(ys)


def error(model, y, X):
    return float(np.sqrt(np.mean((y - model.predict(X)) ** 2)))


def pad(X, cols, names):
    out = np.full((len(X), len(names)), np.nan)
    for j, c in enumerate(cols):
        out[:, names.index(c)] = X[:, j]
    return out


def main():
    rng = np.random.default_rng(SEED)
    d = load()
    d = d[d["country"].isin(EUROPE) & d["price_eur"].notna()]
    by_source = {s: g for s, g in d.groupby("source", observed=True) if len(g) >= MIN_ROWS}
    siblings = same_market(by_source)
    fitted, tables = {}, {}
    for title, feats in MOMENTS:
        fitted[title], tables[title] = run_moment(by_source, feats, siblings)
        print(f"{title}: {len(fitted[title])} datasets")
    names = list(dict.fromkeys(c for ready in fitted.values() for v in ready.values()
                               for c in v["cols"]))

    one = {}
    rows = []
    for title, feats in MOMENTS:
        ready = fitted[title]
        for r in tables[title]:
            target = r["held-out dataset"]
            v = ready[target]
            others = [ready[s] for s in ready if s != target]
            e_per = error(boosted().fit(*stack(others, v["cols"], rng)), v["y_te"], v["X_te"])
            if target not in one:
                blocks = [b for rd in fitted.values() for s, b in rd.items() if s != target]
                one[target] = boosted().fit(*stack(blocks, names, rng))
            e_one = error(one[target], v["y_te"], pad(v["X_te"], v["cols"], names))
            e_lin = r["_all"]
            rows.append({"moment": title.split(" - ")[0], "held-out dataset": target,
                         "linear, per moment": f"{e_lin:.4f}",
                         "boosted, per moment": f"{e_per:.4f}",
                         "boosted, one model": f"{e_one:.4f}",
                         "boosted per moment vs linear": f"{(e_per - e_lin) / e_lin * 100:+.1f}%",
                         "one boosted vs boosted per moment": f"{(e_one - e_per) / e_per * 100:+.1f}%",
                         "_moment": title, "_per": (e_per - e_lin) / e_lin * 100,
                         "_one": (e_one - e_per) / e_per * 100,
                         "_one_lin": (e_one - e_lin) / e_lin * 100})
            print(f"  {target:16} linear {e_lin:.4f} | boosted per moment {e_per:.4f} | "
                  f"one boosted {e_one:.4f}")

    t = pd.DataFrame(rows)
    summary = []
    for title, _ in MOMENTS:
        part = t[t["_moment"] == title]
        if part.empty:
            continue
        summary.append({"moment": title,
                        "tests": len(part),
                        "boosted per moment vs linear": f"{part['_per'].mean():+.1f}%",
                        "one boosted vs boosted per moment": f"{part['_one'].mean():+.1f}%",
                        "where one boosted model was worse": f"{int((part['_one'] > 0).sum())} of "
                                                              f"{len(part)}",
                        "one boosted vs linear per moment": f"{part['_one_lin'].mean():+.1f}%"})
    s = pd.DataFrame(summary)
    odometer = t[t["_moment"] == MOMENTS[2][0]]
    report = [
        "# One flexible model, or a model per moment?", "",
        "Generated by `analysis/one_model_gbm.py`. No new data source. Same datasets, training halves "
        "and held-out cars as `field_sets_report.md`, scored the same way: root mean squared error "
        "of log price within make and model, with the held-out dataset supplying its own price "
        f"level. Training rows capped at {MAX_TRAIN:,} per fit; scikit-learn's "
        "HistGradientBoostingRegressor with default settings, which handles a blank field natively.",
        "", "## Summary", "", md_table(s), "",
        "*Negative is better.*", "",
        "## Every test", "",
        md_table(t.drop(columns=[c for c in t.columns if c.startswith("_")])), "",
        "## What this says", "",
        f"- **On the moment where the linear single model lost, the boosted single model scored "
        f"{odometer['_one'].mean():+.1f}% against boosted models per moment, worse in "
        f"{int((odometer['_one'] > 0).sum())} of {len(odometer)}.** "
        + ("A flexible single model closes most of the gap a linear one leaves, so the case for a "
           "model per moment rests on simplicity and auditability more than accuracy."
           if abs(odometer["_one"].mean()) < 1.0 else
           "A flexible single model does not close the gap either, so keeping a model per moment "
           "holds beyond linear models."),
        f"- **The bigger lever is the learner, not the architecture.** Boosted models per moment "
        f"changed the error by {t['_per'].mean():+.1f}% on average against the linear per-moment "
        f"models on the same rows, and even one boosted model for every moment scored "
        f"{t['_one_lin'].mean():+.1f}% against them. The value engine is linear today; moving its "
        "shape to a boosted model per moment is the larger accuracy gain on offer, at the cost of "
        "the simple per-coefficient blend and explanation the linear design gives.",
        "", "## Limits", "",
        "- **Default settings, no tuning**, and a cap on training rows. A tuned model could do better; "
        "this answers whether the architecture closes the gap, not how far boosting can be pushed.",
        "- **Scored within make and model**, as everywhere in this project, so a boosted model's "
        "ability to learn price levels is deliberately not used. The boosted models see the same "
        "within-model deviations as the linear ones; given raw fields and a model identifier they "
        "might do better still.",
        "- **Advertised prices throughout.**", ""]
    OUT.write_text("\n".join(report))
    print(s.to_string(index=False))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
