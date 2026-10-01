"""X15 part 2: how big must a dealer-randomised pilot be to pass the programme's own Phase 2 gate?

Skeptic A8: uplift needs a random holdout of customers not contacted, but dealers own the conversation and contact
whom they like, so the holdout cannot be enforced customer by customer. The repair is to randomise dealers: every
customer of a treated dealer gets the timed contact, every customer of a control dealer does not. That makes the
pilot a cluster-randomised trial, and clustering costs power. Customers of one dealer resemble each other (the
dealer's staff, stock and habits), so each extra customer of the same dealer adds less information than a new one.

The inflation is the design effect, 1 + (m - 1) x ICC, for m customers per dealer and an intracluster correlation ICC
(CONSORT 2010 extension to cluster randomised trials, Campbell et al., BMJ 2012;345:e5661, which notes ICC is "often
<0.05"). No ICC is published for car retention; outcomes that depend on the provider run higher (0.15 to 0.31 for
documentation outcomes in Snavely et al., JNCI Monographs 2025, across ICCs of about 0 to 0.50). So the ICC is a grid,
0.01 to 0.20, not a number.

What the pilot must detect is the programme's own gate: a retention uplift of `gate_uplift_pp` points over a
randomised control, at `gate_uplift_significance_pct` confidence (TARGET rows), and leak 2's assumed uplift
`upgrade_capture_uplift` (ASSUMPTION). The base retention rate is not published; 50% is used because it maximises the
variance, so the sizes are upper bounds for any base rate (20% and 35% shown beside). Power 80%, the usual convention,
and 90%.

Two tables: dealers per arm needed, and, the other way round, the smallest uplift a pilot of a given size could detect.

**The design chosen (26 September): randomise the group's own flag within each dealer.** A8's objection holds for a
holdout of customers *never contacted*; it does not hold for what the group controls, its own flag (the lead to the
dealer, the finance arm's contact). Within each dealer, the customers reaching the upgrade moment are split at random;
half are flagged, half not. Dealers contact whom they like in both halves, so the comparison measures what the
programme adds over business as usual, which is the gate's own question. Each dealer is a block: its effect cancels.
With dealer rates beta with mean p0 and intracluster correlation ICC, each arm's within-dealer variance is its
Bernoulli variance less ICC x p0 (1 - p0), so customers per arm are z^2 [p0 (1 - p0) + p1 (1 - p1) - 2 ICC p0 (1 - p0)]
/ uplift^2: the ICC now shrinks the size a little instead of inflating it. **Spillover:** a flagged dealer may work its
unflagged customers harder too. If they catch a share c of the uplift, the measured uplift is (1 - c) of the true one,
and the size grows by about 1 / (1 - c)^2; the bias is toward zero, so it can fail a programme that works but not pass
one that does not. Keeping some dealers wholly unflagged measures it: a two-stage, randomised saturation design, which
trades power on the average effect for the spillover estimate (Baird, Bohren, McIntosh and Ozler, Review of Economics
and Statistics 100(5), 2018). The size is set beside one year's financed EU sales, on the register's shipments and its
assumed finance share.

Checks: the sample-size formula agrees with statsmodels' power solver; with an ICC of 0 or one customer per dealer the
design effect is 1; a simulated cluster trial (beta-binomial dealers with the stated ICC) shows the arm mean's variance
inflated by the design effect, and the computed number of dealers giving the stated power. For the chosen design: a
simulated within-dealer trial shows the difference's variance matching the blocked formula, the computed size giving
the stated power, and spillover shrinking the measured uplift to (1 - c) of the true one; with an ICC of 0 the blocked
size equals the unclustered one.

Usage: .venv/bin/python analysis/pilot_size.py   (writes analysis/pilot_size_report.md)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_unified import md_table  # noqa: E402

OUT = HERE / "pilot_size_report.md"
REGISTER = HERE.parent / "assumptions.csv"
ICCS = (0.01, 0.05, 0.10, 0.20)
CUSTOMERS_PER_DEALER = (20, 50, 100, 200)     # customers reaching the upgrade moment per dealer in the pilot window
BASE_RATES = (0.50, 0.35, 0.20)
POWERS = (0.80, 0.90)
PILOT_DEALERS = (25, 50, 100, 200)            # dealers per arm, for the detectable-uplift table
BLOCK_ICCS = (0.0, 0.01, 0.05, 0.10, 0.20)
SPILLOVERS = (0.0, 0.10, 0.25, 0.50)          # share of the uplift unflagged customers of a flagged dealer catch
SEED = 7


def n_individual(p0, delta, alpha, power):
    """Customers per arm for a two-sided test of two proportions, unpooled variance."""
    p1 = p0 + delta
    z = norm.ppf(1 - alpha / 2) + norm.ppf(power)
    return z ** 2 * (p0 * (1 - p0) + p1 * (1 - p1)) / delta ** 2


def design_effect(m, icc):
    return 1 + (m - 1) * icc


def dealers(p0, delta, alpha, power, m, icc):
    return int(np.ceil(n_individual(p0, delta, alpha, power) * design_effect(m, icc) / m))


def detectable(p0, alpha, power, m, icc, k):
    """The smallest uplift (points) k dealers per arm with m customers each detect: base-rate variance on both arms."""
    z = norm.ppf(1 - alpha / 2) + norm.ppf(power)
    return z * np.sqrt(2 * p0 * (1 - p0) * design_effect(m, icc) / (k * m))


def n_blocked(p0, delta, alpha, power, icc, spill=0.0):
    """Customers per arm when the flag is randomised within dealers: dealer effects cancel, spillover shrinks the gap.

    Unflagged customers of a flagged dealer catch a share `spill` of the uplift, so the control rate is p0 + spill x delta
    and the measured gap (1 - spill) x delta. Each arm's within-dealer variance is its Bernoulli variance less the
    between-dealer variance ICC x p0 (1 - p0).
    """
    pc, pt = p0 + spill * delta, p0 + delta
    z = norm.ppf(1 - alpha / 2) + norm.ppf(power)
    var = pc * (1 - pc) + pt * (1 - pt) - 2 * icc * p0 * (1 - p0)
    return z ** 2 * var / ((1 - spill) * delta) ** 2


def simulate_blocked(rng, k, m, p0, delta, icc, spill, trials):
    """Mean within-dealer gap: k dealers, m customers each, half flagged at random; dealer rates beta (mean p0, icc)."""
    s = 1 / icc - 1
    rates = rng.beta(p0 * s, (1 - p0) * s, size=(trials, k))
    h = m // 2
    flagged = rng.binomial(h, np.clip(rates + delta, 0, 1))
    unflagged = rng.binomial(h, np.clip(rates + spill * delta, 0, 1))
    return (flagged - unflagged).sum(axis=1) / (k * h)


def simulate_arm(rng, k, m, p, icc, trials):
    """Arm means of k dealers with m customers each; dealer rates beta with mean p and intracluster correlation icc."""
    if icc == 0:
        rates = np.full((trials, k), p)
    else:
        s = 1 / icc - 1                      # beta(a, b) with a + b = s gives ICC = 1 / (a + b + 1)
        rates = rng.beta(p * s, (1 - p) * s, size=(trials, k))
    return rng.binomial(m, rates).sum(axis=1) / (k * m)


def checks(alpha, gate):
    from statsmodels.stats.power import NormalIndPower
    rows = []

    def check(name, passes, got):
        rows.append({"check": name, "got": got, "passes": bool(passes)})

    p0 = 0.5
    mine = n_individual(p0, gate, alpha, 0.8)
    # statsmodels solves for a standardised difference; with the unpooled SD it is the same normal approximation
    sd = np.sqrt((p0 * (1 - p0) + (p0 + gate) * (1 - p0 - gate)) / 2)
    theirs = NormalIndPower().solve_power(effect_size=gate / sd, alpha=alpha, power=0.8, ratio=1.0)
    check("customers per arm: the formula agrees with statsmodels' NormalIndPower within 0.1%",
          abs(mine / theirs - 1) < 0.001, f"{mine:,.0f} against {theirs:,.0f}")
    check("the design effect is 1 with an ICC of 0 or one customer per dealer",
          design_effect(100, 0.0) == 1.0 and design_effect(1, 0.2) == 1.0, "1 and 1")

    rng = np.random.default_rng(SEED)
    k, m, icc, trials = 40, 50, 0.05, 20_000
    var = simulate_arm(rng, k, m, p0, icc, trials).var()
    expected = p0 * (1 - p0) / (k * m) * design_effect(m, icc)
    se = expected * np.sqrt(2 / (trials - 1))
    check(f"simulation ({trials:,} trials, {k} dealers of {m}, ICC {icc}): the arm mean's variance is the design "
          "effect times the unclustered variance, within three standard errors", abs(var - expected) <= 3 * se,
          f"{var / (p0 * (1 - p0) / (k * m)):.2f} against {design_effect(m, icc):.2f}")

    m, icc, trials = 50, 0.05, 4_000
    need = dealers(p0, 0.05, alpha, 0.8, m, icc)      # a larger uplift keeps the simulation fast
    a = simulate_arm(rng, need, m, p0, icc, trials)
    b = simulate_arm(rng, need, m, p0 + 0.05, icc, trials)
    se_diff = np.sqrt((p0 * (1 - p0) + (p0 + 0.05) * (1 - p0 - 0.05)) * design_effect(m, icc) / (need * m))
    power = np.mean(np.abs(b - a) / se_diff > norm.ppf(1 - alpha / 2))
    check(f"simulation ({trials:,} trials): {need} dealers per arm of {m} customers at ICC {icc} detect a 5-point "
          "uplift with about 80% power (0.77 to 0.85)", 0.77 <= power <= 0.85, f"{power:.1%}")

    # the chosen design: the flag randomised within dealers
    check("blocked: with an ICC of 0 and no spillover the size equals the unclustered one",
          abs(n_blocked(p0, gate, alpha, 0.8, 0.0) - n_individual(p0, gate, alpha, 0.8)) < 1e-9, "equal")
    k, m, icc, d, trials = 60, 50, 0.10, 0.05, 20_000
    gaps = simulate_blocked(rng, k, m, p0, d, icc, 0.0, trials)
    h = m // 2
    expected = ((p0 * (1 - p0) + (p0 + d) * (1 - p0 - d) - 2 * icc * p0 * (1 - p0)) / (k * h))
    se = expected * np.sqrt(2 / (trials - 1))
    check(f"blocked simulation ({trials:,} trials, {k} dealers of {m}, ICC {icc}): the gap's variance matches the "
          "blocked formula within three standard errors", abs(gaps.var() - expected) <= 3 * se,
          f"{gaps.var() * 1e5:.3f} against {expected * 1e5:.3f} (x 1e-5)")
    per_arm = n_blocked(p0, d, alpha, 0.8, icc)
    k_need = int(np.ceil(per_arm / h))
    gaps = simulate_blocked(rng, k_need, m, p0, d, icc, 0.0, 4_000)
    var_pair = expected * k * h                     # the two arms' within-dealer variances, summed
    power = np.mean(np.abs(gaps) / np.sqrt(var_pair / (k_need * h)) > norm.ppf(1 - alpha / 2))
    check(f"blocked simulation (4,000 trials): {k_need} dealers of {m} at ICC {icc} detect a 5-point uplift with "
          "about 80% power (0.77 to 0.85)", 0.77 <= power <= 0.85, f"{power:.1%}")
    gaps = simulate_blocked(rng, k, m, p0, d, icc, 0.25, trials)
    check(f"blocked simulation: with a quarter of the uplift spilling over, the measured gap is three quarters of "
          "the true one (within 0.2 points)", abs(gaps.mean() - 0.75 * d) < 0.002, f"{100 * gaps.mean():.2f} points")
    return pd.DataFrame(rows)


def main():
    reg = pd.read_csv(REGISTER).set_index("id")["value"]
    gate = reg["gate_uplift_pp"] / 100
    alpha = 1 - reg["gate_uplift_significance_pct"] / 100
    assumed = reg["upgrade_capture_uplift"] / 100

    rows = []
    for delta, label in ((gate, "the gate"), (assumed, "leak 2's assumed uplift")):
        for power in POWERS:
            for p0 in BASE_RATES:
                for m in CUSTOMERS_PER_DEALER:
                    rows.append({"case": f"{label} ({100 * delta:.0f} points), power {power:.0%}, base {p0:.0%}, "
                                         f"{m} customers per dealer",
                                 "customers per arm, unclustered": f"{n_individual(p0, delta, alpha, power):,.0f}",
                                 **{f"dealers per arm, ICC {icc}": f"{dealers(p0, delta, alpha, power, m, icc):,}"
                                    for icc in ICCS}})
    table = pd.DataFrame(rows)
    headline = table[table["case"].str.contains("power 80%, base 50%")]

    mde = pd.DataFrame([{"pilot": f"{k} dealers per arm, 100 customers each",
                         **{f"smallest uplift, ICC {icc} (points)": f"{100 * detectable(0.5, alpha, 0.8, 100, icc, k):.1f}"
                            for icc in ICCS}} for k in PILOT_DEALERS])
    ck = checks(alpha, gate)

    blocked = pd.DataFrame([{"case": f"the gate ({100 * gate:.0f} points), power {pw:.0%}, base {p0:.0%}",
                             **{f"customers per arm, ICC {icc}": f"{n_blocked(p0, gate, alpha, pw, icc):,.0f}"
                                for icc in BLOCK_ICCS}} for pw in POWERS for p0 in BASE_RATES])
    spill = pd.DataFrame([{"share of the uplift unflagged customers catch": f"{c:.0%}",
                           "measured uplift (points)": f"{100 * (1 - c) * gate:.1f}",
                           "customers per arm, ICC 0.1": f"{n_blocked(0.5, gate, alpha, 0.8, 0.10, c):,.0f}"}
                          for c in SPILLOVERS])
    financed = reg["sfse_eu_nv_contracts_2025"]
    per_arm, per_arm_spill = n_blocked(0.5, gate, alpha, 0.8, 0.10), n_blocked(0.5, gate, alpha, 0.8, 0.10, 0.25)
    chosen = pd.DataFrame([
        {"figure": "customers per arm, the flag randomised within dealers (the gate, power 80%, base 50%, ICC 0.1)",
         "value": f"{per_arm:,.0f}"},
        {"figure": "the same, with a quarter of the uplift spilling over to unflagged customers",
         "value": f"{per_arm_spill:,.0f}"},
        {"figure": "both arms, as a share of one year's financed EU sales (%)",
         "value": f"{100 * 2 * per_arm / financed:.1f}"},
        {"figure": "the same, with a quarter spilling over (%)", "value": f"{100 * 2 * per_arm_spill / financed:.1f}"}])

    lines = [
        "# X15 part 2: how big must a dealer-randomised pilot be?",
        "",
        "Generated by `analysis/pilot_size.py`; the method is in its docstring. The gate: a retention uplift of "
        f"{100 * gate:.0f} points over a randomised control at {100 * (1 - alpha):.0f}% confidence (two-sided), "
        f"from the register; leak 2's assumed uplift is {100 * assumed:.0f} points. The first tables randomise dealers "
        "(skeptic A8's first repair); the last section randomises the group's flag within each dealer, the design "
        "chosen.",
        "",
        "## Dealers per arm, power 80%, base retention 50% (the largest sizes any base rate needs)",
        "",
        md_table(headline),
        "",
        "## What a pilot of a given size can detect (power 80%, base 50%, 100 customers per dealer)",
        "",
        md_table(mde),
        "",
        "## Every case",
        "",
        md_table(table),
        "",
        "## The design chosen: the group's flag, randomised within each dealer",
        "",
        "The holdout is \"not flagged by the group\", not \"never contacted\". Dealers contact whom they like in both "
        "halves, so the comparison is what the programme adds over business as usual, the gate's own question. Each "
        "dealer is its own block, so its effect cancels, and the ICC shrinks the size a little instead of inflating it:",
        "",
        md_table(blocked),
        "",
        "A flagged dealer may work its unflagged customers harder too. Spillover shrinks the measured uplift toward zero, "
        "so it can fail a programme that works but cannot pass one that does not (power 80%, base 50%, ICC 0.1):",
        "",
        md_table(spill),
        "",
        "Keeping a few dealers wholly unflagged measures the spillover instead of guessing it: a two-stage, randomised "
        "saturation design, which trades some power on the average effect for the spillover estimate (Baird, Bohren, "
        "McIntosh and Ozler, Review of Economics and Statistics 100(5), 2018). On the register's figures the pilot is "
        "small against the book (`sfse_eu_nv_contracts_2025`, the new-car contracts the group's finance arm wrote in Europe "
        "in 2025, a disclosed count):",
        "",
        md_table(chosen),
        "",
        "## Checks",
        "",
        md_table(ck),
        "",
        "## Limits",
        "",
        "- **No automotive ICC exists.** The grid spans the general trial literature; the pilot's first months should "
        "estimate it, and the size be revised.",
        "- **Equal dealer sizes assumed.** Unequal sizes raise the design effect further (CONSORT's coefficient of "
        "variation adjustment).",
        "- **Covariates help.** Adjusting for each customer's and dealer's past retention can cut the variance further; "
        "these sizes are without it.",
        "- **The pilot markets must hold the customers.** The share above is of the whole EU book on an assumed finance "
        "share; the pilot's markets and window are a fraction of it, and whether they hold the customers is for the "
        "group's contract data (X14 sources the finance share).",
        "- **One average, over the pilot's dealers.** If the uplift differs by dealer, carrying the result to dealers "
        "outside the pilot adds that spread to the uncertainty; picking pilot dealers at random keeps it honest.",
        "- **The flag must stay the group's.** The holdout list is never shown to dealers, and dealers' own contacts "
        "are recorded in both halves.",
        "- **Retention takes time to observe.** An upgrade decision can come months after the flag; the outcome window "
        "is set before the pilot starts.",
        "- **The base rate is not published.** 50% gives the largest sizes; lower base rates need fewer.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(ck.to_string(index=False))
    print(headline.to_string(index=False))
    print(mde.to_string(index=False))
    print(chosen.to_string(index=False))
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
