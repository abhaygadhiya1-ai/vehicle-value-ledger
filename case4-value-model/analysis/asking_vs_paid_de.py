"""X10 parts 2 and 3b: German asking prices against what German buyers say they paid, at one date and over time.

Every European price we hold is an advert's asking price. DAT's yearly survey of private car buyers publishes the
average price paid for a used car in Germany. This sets the June 2023 AutoScout24 Germany adverts (`de_2023`)
beside DAT's 2023 figure.

The two means describe different mixes of cars, and DAT publishes its mix (age, mileage, segment) only in its paid
report. So the adverts are reweighted to a range of mixes rather than one. An exponential tilt on age reaches a
chosen mean age with the least distortion. At the old end is the official mix of every passenger car that changed
owner in 2023 (KBA: its mean age and its ten largest brands), reached by raking on brand and age together. Each row
reports the weights' effective sample size, so a mix the adverts can reach only by leaning on a few cars shows.

What this can say: how far apart asking and paid sit under each mix, and how much the answer depends on the mix.
What it cannot say: how much of any gap is negotiation on the same car, and how much is the adverts' own composition
(dealer stock, slow sellers, trim). That needs per-car data (X10's Danish lead).

**Part 3b, over time.** Does the gap move with the market? Three German measures, year by year:
- AutoScout24's average asking price (AGPI);
- DAT's average price paid;
- Germany's official used-car index, which is hedonic, so it prices the same kind of car each year (Destatis; built
  on DAT's dealer transaction prices as of its 2003 method paper, current source unconfirmed).
The two averages are compared like for like; the official index shows what a like-for-like measure did meanwhile.

Inputs: `de_2023` from the unified table; DAT, AGPI and KBA figures from `assumptions.csv` (SOURCED rows, URLs
there); Eurostat HICP CP07112 for Germany from `data/reference/price_indices.parquet`.
Usage: .venv/bin/python analysis/asking_vs_paid_de.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.optimize import brentq

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_unified import md_table  # noqa: E402

OUT = HERE / "asking_vs_paid_de_report.md"
LISTINGS = HERE.parent / "data" / "unified" / "listings.parquet"
INDICES = HERE.parent / "data" / "reference" / "price_indices.parquet"
REGISTER = HERE.parent / "assumptions.csv"
BRANDS = {"audi": "audi", "bmw": "bmw", "mercedes benz": "mercedes", "opel": "opel", "volkswagen": "vw", "fiat": "fiat",
          "hyundai": "hyundai", "renault": "renault", "seat": "seat", "skoda": "skoda"}


def tilt(w, age, target):
    """Reweight w by exp(l * age) so the weighted mean age is `target`."""
    z = age - age.mean()
    lam = brentq(lambda x: np.average(age, weights=w * np.exp(x * z)) - target, -5, 5)
    return w * np.exp(lam * z)


def rake(age, brand, target_age, shares, rounds=500):
    """Weights matching the brand shares and the mean age at once (iterative proportional fitting)."""
    w = np.ones(len(age))
    for _ in range(rounds):
        for b, s in shares.items():
            m = brand == b
            w[m] *= s / (w[m].sum() / w.sum())
        w = tilt(w, age, target_age)
        cur = pd.Series(w).groupby(brand).sum() / w.sum()
        if max(abs(cur[b] - s) for b, s in shares.items()) < 1e-6:
            return w
    raise RuntimeError("raking did not converge")


def line(label, d, w, paid):
    ask = np.average(d.price_eur, weights=w)
    return {"mix the adverts are weighted to": label, "adverts": f"{len(d):,}",
            "effective adverts": f"{w.sum() ** 2 / (w ** 2).sum():,.0f}",
            "mean age": f"{np.average(d.age_years, weights=w):.1f}", "mean asking (EUR)": f"{ask:,.0f}",
            "DAT paid (EUR)": f"{paid:,.0f}", "asking / paid": f"{ask / paid:.2f}"}


def over_time(reg):
    """Part 3b: the three German measures year by year, and what the gap between asking and paid did at the turn."""
    idx = pd.read_parquet(INDICES)
    de = idx[(idx.geo == "DE") & idx.series.str.contains("CP07112")].set_index("month").index_value
    de.index = pd.PeriodIndex(de.index, freq="M")
    ann = de.groupby(de.index.year).mean()
    years = range(2022, 2026)
    off = {y: ann[y] / ann[y - 1] - 1 for y in years}
    off[2025] = de[pd.Period("2025-11", "M")] / de[pd.Period("2024-11", "M")] - 1  # November on November, as asking
    paid = {y: reg[f"dat_gw_paid_{y}"] / reg[f"dat_gw_paid_{y - 1}"] - 1 for y in years}
    ask = {2022: reg["agpi_change_2022"] / 100, 2023: reg["agpi_change_2023"] / 100,
           2024: reg["agpi_change_2024"] / 100, 2025: reg["agpi_nov_2025"] / reg["agpi_nov_2024"] - 1}

    def pct(x):
        return f"{100 * x:+.1f}%"

    def moved(x):
        return f"{'rose' if x > 0 else 'fell'} {abs(100 * x):.1f}%"
    tab = pd.DataFrame([{"year": str(y) + (" (November on November)" if y == 2025 else ""),
                         "asking, average (AutoScout24)": pct(ask[y]), "paid, average (DAT)": pct(paid[y]),
                         "asking less paid (points)": f"{100 * (ask[y] - paid[y]):+.1f}",
                         "official index, like for like": pct(off[y])} for y in years])
    two_ask = (1 + ask[2023]) * (1 + ask[2024]) - 1
    two_paid = reg["dat_gw_paid_2024"] / reg["dat_gw_paid_2022"] - 1
    two_off = ann[2024] / ann[2022] - 1
    peak = de.idxmax()
    top23 = de.loc["2023-01":"2023-12"].idxmax()
    dip = de.loc[str(top23):"2024-12"].min() / de[top23] - 1
    return f"""## Does the gap move with the market? (X10 part 3b)

Three German measures, year on year. Asking and paid are both plain averages over what was listed or bought. The
official index holds the kind of car fixed.

{md_table(tab)}

- **Asking turned a year after paid.** In 2023 the average asking price still {moved(ask[2023])}, while the average
  paid {moved(paid[2023])}; AutoScout24's record month was March 2023 (EUR {reg['agpi_peak_2023_03']:,.0f}). In 2024
  asking {moved(ask[2024])} and paid {moved(paid[2024])}. Over the two years together asking {moved(two_ask)} and paid
  {moved(two_paid)}. So the gap opened at the turn and closed within two years, with asking no higher against paid
  than before. In 2025 the two parted again: asking {moved(ask[2025])}, paid {moved(paid[2025])}.
- **Like for like, prices kept rising.** The official index {moved(off[2023])} in 2023 ({pct(two_off)} over
  2023-24). It fell {abs(100 * dip):.1f}% from its 2023 high ({top23.strftime('%B %Y')}) into 2024, and reached its highest
  level in {peak.strftime('%B %Y')}. Both averages can fall while like-for-like prices rise when the mix bought and
  listed shifts to cheaper cars. These figures can't say which cars shifted.
- **Asking lags realised prices, as in part 3a.** Aramis's realised price per car (about half of it France) stopped rising in
  early 2023. Germany's average paid turned in 2023 and its average asking price in 2024. The like-for-like indices
  (Germany's, and France's smoothed one) had not turned by then. They measure something else, and part 3a shows
  France's lagging.

**What it means for the solution.**
- **An advert-based mark is late at a turn.** A ledger marked only on asking prices would carry the book above what
  buyers pay for about a year after the market turns. The re-mark needs a realised signal beside the adverts: the
  group's own sales (Aramis, and the resale book itself once the ledger holds it).
- **No sign that asking-based falls understate paid falls over two years in Germany.** Over 2023-24 the asking
  average fell at least as far as the paid one. The risk shown is timing, not a lasting gap. 2025's renewed parting
  is one year and can't be read yet. X6's charge on percentage moves stands.
- **The engine is like for like, as the official index is.** It holds model, age and mileage fixed, so a mix shift
  doesn't move its values. An average-price series, asking or paid, would mislead the ledger.

**Limits.**
- **Annual averages, four years, one country.**
- **The two averages cover different populations:** AutoScout24's listings, largely dealers, against DAT's
  surveyed purchases, which include private sales.
- **AutoScout24's year figures come from its December reviews,** whose basis for the year isn't stated. The 2024
  stated change differs from the two year figures' ratio (`agpi_change_2024`'s caveat). The 2022 and 2023 figures
  are trade-press reprints of AutoScout24's reviews.
- **The official index's source today is unconfirmed,** and in 2003 it covered cars up to ten years old.
"""


def main():
    reg = pd.read_csv(REGISTER).set_index("id")["value"].astype(float)
    paid, kba_age, total = reg["dat_gw_paid_2023"], reg["kba_pkw_transfer_age_2023"], reg["kba_pkw_transfers_2023"]
    shares = {b: reg[f"kba_pkw_transfers_2023_{b}"] / total for b in BRANDS.values()}
    shares["other"] = 1 - sum(shares.values())

    d = pq.read_table(LISTINGS, columns=["source", "age_years", "price_eur", "make"],
                      filters=[("source", "=", "de_2023")]).to_pandas()
    d = d[d.price_eur.notna() & d.age_years.notna()].reset_index(drop=True)
    d["brand"] = d.make.astype(str).map(BRANDS).fillna("other")
    age, brand = d.age_years.to_numpy(float), d.brand.to_numpy()
    one = np.ones(len(d))

    rows = [line("as listed (the adverts' own mix)", d, one, paid)]
    for t in (6, 7, 8, 9):
        rows.append(line(f"mean age {t}", d, tilt(one, age, t), paid))
    rows.append(line(f"mean age {kba_age:g} (KBA: all 2023 ownership changes)", d, tilt(one, age, kba_age), paid))
    w_kba = rake(age, brand, kba_age, shares)
    rows.append(line("KBA: mean age and the ten largest brands", d, w_kba, paid))
    old = d.age_years >= 1
    d1 = d[old].reset_index(drop=True)
    rows.append(line("KBA age and brands, cars 1 year and older", d1,
                     rake(d1.age_years.to_numpy(float), d1.brand.to_numpy(), kba_age, shares), paid))
    cap = d.price_eur <= d.price_eur.quantile(0.99)
    d2 = d[cap].reset_index(drop=True)
    rows.append(line("KBA age and brands, top 1% of asking prices dropped", d2,
                     rake(d2.age_years.to_numpy(float), d2.brand.to_numpy(), kba_age, shares), paid))
    tab = pd.DataFrame(rows)
    ratio = tab["asking / paid"].astype(float)
    lo, hi = ratio.min(), ratio.max()
    r_kba, r_used, r_trim = ratio.iloc[6], ratio.iloc[7], ratio.iloc[8]
    n_eff_min = tab["effective adverts"].str.replace(",", "").astype(int).min()

    brand_tab = pd.DataFrame({"brand": list(shares), "KBA share of 2023 ownership changes":
                              [f"{100 * s:.1f}%" for s in shares.values()],
                              "share of adverts": [f"{100 * (d.brand == b).mean():.1f}%" for b in shares]})

    OUT.write_text(f"""# X10 part 2: German asking prices against what German buyers paid

**The free German figures show no measurable gap, because the mix decides the answer.** DAT's survey puts the
average used car bought by a German private buyer in 2023 at EUR {paid:,.0f}. Depending on the mix they are
weighted to, the June 2023 AutoScout24 adverts ask {lo:.2f} to {hi:.2f} times that.
- **At the official mix** of every car that changed owner in 2023 (KBA: mean age and the ten largest brands),
  asking and paid nearly coincide: {r_kba:.2f}. Without near-new cars it is {r_used:.2f}, and with the top 1% of
  asking prices dropped, {r_trim:.2f}.
- **At younger mixes,** asking runs well above paid.

DAT publishes the mix of cars bought only in its paid report. The ratio moves by far more across mixes than a
negotiated discount plausibly could, so comparing an average advert with an average purchase says nothing about
the discount on one car.

{md_table(tab)}

- **Weights.** Effective adverts count how many equally weighted adverts the weights are worth. The official mix is
  older than the adverts' own, so reaching it leans on older cars. The lowest count is {n_eff_min:,}, so no row rests
  on a few cars.
- **Brands.** The adverts against the official mix of ownership changes (KBA's ten largest brands, the rest as
  other):

{md_table(brand_tab)}

## What the ratio contains

The advert mean and the paid mean differ for three reasons, and this comparison can't pull them apart.

- **Negotiation:** a buyer pays less than the asking price for the same car. This is the discount X10 is after.
- **Composition the weights can't reach:** mileage, trim and segment within a brand and age, and the mix DAT's
  buyers actually had.
- **Stock against flow:** adverts are a snapshot of stock, which overweights cars that sell slowly. It also
  overweights dealers: DAT's buyers bought {reg['dat_gw_private_share_2023']:.0f}% of their used cars privately,
  while `de_2023` does not record the seller.

Composition alone moves the ratio from {lo:.2f} to {hi:.2f}. A discount of a few per cent would be lost inside that
spread.

## What it means for the solution

- **No figure for "adverts overstate paid prices by X%" in Germany, from us or from any team using averages.** Such
  a figure reads composition, not a discount.
- **Every headline stays labelled as an advert price,** as before. A per-car value quoted in euros (the value engine,
  the sample car in 6.6) is an asking price.
- **The question that matters moves to time and to single cars.** Leak 3 and X6 use percentage moves of indices, and
  a steady gap cancels in a percentage move. What would matter is a gap that widens when the market falls. The
  next section tests that. The discount on one car needs per-car data; the Danish route is closed to us (X10 part 1).

## Limits

- **One snapshot of adverts.** `de_2023` is dated by its upload to Kaggle (24 June 2023), not by a scrape date,
  and has no listing dates. DAT's figure covers purchases across 2023.
- **DAT's figure is a survey.** Buyers report what they paid, possibly with extras or a trade-in folded in. DAT
  doesn't publish its sample size or questions in the free short report.
- **The official mix covers every ownership change,** commercial keepers included, not only DAT's private buyers.
- **Germany only, one year.**

""" + over_time(reg))
    print(OUT.read_text()[:1800])


if __name__ == "__main__":
    main()
