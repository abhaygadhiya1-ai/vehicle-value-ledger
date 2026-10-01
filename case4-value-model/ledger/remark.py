"""X4 part 3: the monthly re-mark. Every car in the book gets a value at every month end, as an estimate event.

**A mark is the curve times the level**, the split the programme is built on (`notes/STATE.md`, "The answer"):
  mark = catalogue price × share kept at the car's age × (Dutch used-car index that month ÷ in the curve's month)
  - Catalogue price: the OEM's price list (part 1's `list_price` event), the independent source rather than the
    dealer-reported record. It is RDW's catalogue price, VAT and BPM included: the same basis as the curve.
  - The curve: the Dutch share of the catalogue price that used cars keep, by age, from `value_retained.py`'s matched
    adverts (NL rows), filtered and binned as that script does (age rounded to the year, at least 30 adverts). Between
    whole years it is interpolated in logs; in the first year it runs from 1 at registration (the price paid) to the
    one-year share. The adverts are one premium dealer's scrape of all makes, and BPM deflates the share
    (`value_retained_report.md`). The curve's month is the scrape's, read from the listings.
  - The level: Eurostat HICP, second-hand motor cars (CP07112), Netherlands, monthly, as a ratio to its value in the
    curve's month. A consumer price index, not advert prices.
  - The band (80%): the adverts' 10th and 90th percentile share at that age, as ratios to the median. It says how far
    one car can sit off the curve in that scrape, not how sure we are about a group car.

**Dates.** A mark is valid at the month end and recorded at the end of the next month, since a month's index is
published after the month ends (Eurostat's release timing ~, not checked; a month's lag is the cautious reading). Marks
run from each car's registration month to the index's last month. No car leaves the book yet; part 5 adds returns.

Decision A (`notes/Case4_Extensions.md`, X4) was taken as recommended while the user was away; it is reversible.
Output: rows in the store's typed `marks` table (model `x4_mark_v1`; the `ledger` view shows them as `mark` estimate
events), and ledger/x4_remark_report.md.
Usage: .venv/bin/python ledger/remark.py   (after parts 1 and 2; running it again adds nothing)
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from store import STORE, append_estimates, content_hash, open_store, read, timeline  # noqa: E402
sys.path.insert(0, str(ROOT / "analysis"))
from value_retained import AGES, MATCHED  # noqa: E402

REPORT = HERE / "x4_remark_report.md"
INDEX = ROOT / "data" / "reference" / "price_indices.parquet"
LISTINGS = ROOT / "data" / "unified" / "listings.parquet"
MODEL = "x4_mark_v1"
MIN_ADS = 30              # value_retained.py prints a year's share only with at least 30 adverts
KEEP = (0.02, 1.5)        # value_retained.curve's filter on the share
SHOWCASE = 51500          # part 1's showcase car


def curve():
    """The Dutch share kept at each whole year of age (median, 10th and 90th percentile), and the curve's month."""
    v = pd.read_parquet(MATCHED, columns=["source", "country", "age_years", "retained"])
    v = v[v["country"].eq("NL") & v["age_years"].between(0.5, 15) & v["retained"].between(*KEEP)].copy()
    v["age"] = v["age_years"].round().astype(int)
    g = v[v["age"].isin(AGES)].groupby("age")["retained"]
    t = pd.DataFrame({"adverts": g.size(), "median": g.median(), "p10": g.quantile(0.1), "p90": g.quantile(0.9)})
    t = t[t["adverts"] >= MIN_ADS]
    ads = pd.read_parquet(LISTINGS, columns=["source", "country", "listing_date"], filters=[("country", "==", "NL")])
    ads = ads[ads["source"].isin(v["source"].unique()) & ads["country"].eq("NL")]
    month = pd.to_datetime(ads["listing_date"]).median().strftime("%Y-%m")
    return t, month


def share(age, t, col="median"):
    """The curve at any age in years: log-linear between whole years, from 1 at age 0. For the band, the ratio of a
    percentile to the median, held at the first year's ratio before it."""
    ages = np.r_[0.0, t.index.to_numpy(float)]
    if col == "median":
        vals = np.r_[0.0, np.log(t["median"].to_numpy())]
    else:
        r = np.log((t[col] / t["median"]).to_numpy())
        vals = np.r_[r[0], r]
    return np.exp(np.interp(age, ages, vals))


def level():
    i = pd.read_parquet(INDEX)
    i = i[i["geo"].eq("NL") & i["series"].str.contains("CP07112")]
    return i.set_index("month")["index_value"].sort_index()


def book(con):
    """Each car's catalogue price (OEM price list) and registration date, read from the ledger itself."""
    return con.execute(
        "SELECT p.car_id, p.amount_eur AS catalogue, r.valid_date AS registration_date FROM events p "
        "JOIN events r ON r.car_id = p.car_id AND r.event_type = 'registration' "
        "WHERE p.event_type = 'list_price' AND p.source = 'oem_prices' ORDER BY p.car_id").df()


def marks(cars, year, t, idx, ref):
    out = []
    for end in pd.date_range(f"{year}-01-31", f"{year}-12-31", freq="ME"):
        month = end.strftime("%Y-%m")
        if month not in idx.index:
            continue
        c = cars[pd.to_datetime(cars["registration_date"]) <= end].copy()
        c["age"] = ((end - pd.to_datetime(c["registration_date"])).dt.days / 365.25).round(3)
        c["level"] = round(idx[month] / idx[ref], 4)
        c["mark_eur"] = (c["catalogue"] * share(c["age"], t) * c["level"]).round(2)
        c["low_eur"] = (c["mark_eur"] * share(c["age"], t, "p10")).round(2)
        c["high_eur"] = (c["mark_eur"] * share(c["age"], t, "p90")).round(2)
        c["month_end"] = end
        c["recorded_date"] = end + pd.offsets.MonthEnd(1)
        out.append(c)
    d = pd.concat(out, ignore_index=True).rename(columns={"age": "age_years"})
    return d.assign(model=MODEL)


def report_row():
    """The NL row of value_retained_report.md, as printed: '82%' ... per whole year."""
    for line in (ROOT / "analysis" / "value_retained_report.md").read_text().splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] == "NL" and len(cells) == 3 + len(AGES):
            return dict(zip([f"{a}y" for a in AGES], cells[3:]))
    raise ValueError("no NL row in value_retained_report.md")


def check(con, t, idx, ref, last, before):
    results = []
    printed = report_row()
    ours = {f"{a}y": f"{t.loc[a, 'median'] * 100:.0f}%" for a in t.index}
    results.append(("the curve reproduces value_retained_report.md's NL row",
                    all(printed[k] == v for k, v in ours.items()) and len(ours) == sum(v != "-" for v in printed.values())))
    reg = pd.read_csv(ROOT / "assumptions.csv").set_index("id")
    results.append(("the curve at 36 months matches register row retained_3y_nl",
                    round(100 * float(share(3.0, t))) == float(reg.loc["retained_3y_nl", "value"])))

    master = read("master")
    first = pd.to_datetime(master["registration_date"]).dt.to_period("M")
    last_month = pd.Period(idx.index.max(), "M")
    expect = (last_month - first).apply(lambda p: p.n) + 1
    got = con.execute("SELECT car_id, count(*) n FROM marks WHERE model = ? GROUP BY car_id", [MODEL]).df()
    got = got.set_index("car_id")["n"].reindex(master["car_id"]).fillna(0).astype(int).to_numpy()
    results.append(("one mark per car per month, registration month to the index's last", (got == expect.to_numpy()).all()))

    # five cars recomputed by a plain loop from the source files, not from the ledger
    prices = read("oem_prices").set_index("car_id")["list_price_eur"]
    regd = master.set_index("car_id")["registration_date"]
    ids = master["car_id"].sort_values().iloc[np.linspace(0, len(master) - 1, 5).astype(int)].tolist()
    stored = con.execute("SELECT car_id, month_end AS valid_date, mark_eur AS amount_eur FROM marks WHERE model = ? "
                         f"AND car_id IN ({','.join(map(str, ids))})", [MODEL]).df()
    worst = 0.0
    for r in stored.itertuples():
        end = pd.Timestamp(r.valid_date)
        age = round((end - pd.Timestamp(regd[r.car_id])).days / 365.25, 3)
        want = prices[r.car_id] * float(share(age, t)) * round(idx[end.strftime("%Y-%m")] / idx[ref], 4)
        worst = max(worst, abs(want - r.amount_eur))
    results.append((f"five cars' {len(stored)} marks recomputed from the source files (worst gap €{worst:.2f})",
                    worst < 0.01 and len(stored) > 0))

    dup = con.execute("SELECT count(*) - count(DISTINCT (model, car_id, month_end)) FROM marks").fetchone()[0]
    results.append(("no car has two marks for one month", dup == 0))
    results.append(("facts and decisions unchanged by the marks", content_hash(con, upto=last) == before))
    y = int(idx.index.max()[:4])
    results.append((f"running {y}'s marks again adds nothing", append_estimates(con, "marks", marks(book(con), y, t, idx, ref)) == 0))

    tl = timeline(con, SHOWCASE)
    mk = tl[tl["event_type"].eq("mark")].iloc[-1]
    day = pd.Timestamp(mk["recorded_date"])
    seen = [mk["event_id"] in set(timeline(con, SHOWCASE, d)["event_id"]) for d in (day - pd.Timedelta(days=1), day)]
    results.append(("the last month's mark is unknown until its index month is published", seen == [False, True]))
    free = shutil.disk_usage(STORE).free / 2**30
    results.append((f"disk: store {STORE.stat().st_size / 2**20:,.0f} MB, {free:.1f} GB free", free > 1))
    return results


def write_report(con, t, idx, ref, results):
    ends = [f"{y}-12" for y in range(2021, int(idx.index.max()[:4]) + 1) if f"{y}-12" in idx.index]
    b = con.execute(
        "SELECT strftime(m.month_end, '%Y-%m') AS month, count(*) AS cars, sum(m.mark_eur) AS book, "
        "median(m.mark_eur / p.amount_eur) AS kept FROM marks m JOIN events p ON p.car_id = m.car_id "
        "AND p.event_type = 'list_price' WHERE m.model = ? GROUP BY ALL ORDER BY ALL", [MODEL]).df()
    b = b[b["month"].isin(ends)]
    lines = ["# X4 part 3: the monthly re-mark", "",
             "Generated by `ledger/remark.py`. The cars and catalogue prices are real (RDW); the world around them is "
             "synthetic (X1); the curve and the level are measured. The book totals are the prototype's output on "
             "that book, not a register figure.", "",
             f"mark = OEM catalogue price × Dutch share kept at the car's age × (NL HICP second-hand cars that month ÷ "
             f"in {ref}, the curve's month). Band: the adverts' p10 and p90 share at that age, over the median.", "",
             "## The curve (Dutch adverts matched to RDW catalogue prices)", "",
             "| age | adverts | median | p10 | p90 |", "|---:|---:|---:|---:|---:|"]
    lines += [f"| {a} | {r["adverts"]:,.0f} | {r["median"]:.1%} | {r["p10"]:.1%} | {r["p90"]:.1%} |" for a, r in t.iterrows()]
    lines += ["", "## The book at each year end", "",
              "| month | cars | book (€m) | level (index ÷ curve month) | median mark ÷ catalogue |", "|---|---:|---:|---:|---:|"]
    lines += [f"| {r.month} | {r.cars:,} | {r.book / 1e6:,.0f} | {idx[r.month] / idx[ref]:.3f} | {r.kept:.1%} |"
              for r in b.itertuples()]
    tl = timeline(con, SHOWCASE)
    mk = tl[tl["event_type"].eq("mark") & pd.to_datetime(tl["valid_date"]).dt.month.eq(12)]
    cat = tl.loc[tl["event_type"].eq("list_price"), "amount_eur"].iloc[0]
    lines += ["", f"## Car {SHOWCASE} (part 1's showcase), catalogue €{cat:,.0f}: each December's mark", "",
              "| month end | learned | mark | low | high |", "|---|---|---:|---:|---:|"]
    for r in mk.itertuples():
        a = json.loads(r.attrs)
        lines.append(f"| {r.valid_date:%Y-%m-%d} | {r.recorded_date:%Y-%m-%d} | {r.amount_eur:,.0f} | {a['low']:,.0f} "
                     f"| {a['high']:,.0f} |")
    lines += ["", "## Checks", ""] + [f"- {'pass' if ok else 'FAIL'}: {name}" for name, ok in results]
    REPORT.write_text("\n".join(lines) + "\n")


def main():
    con = open_store(STORE)
    last = con.execute("SELECT max(seq) FROM events").fetchone()[0]
    before = content_hash(con, upto=last)
    t, ref = curve()
    idx = level()
    cars = book(con)
    n = 0
    for year in range(pd.to_datetime(cars["registration_date"]).dt.year.min(), int(idx.index.max()[:4]) + 1):
        n += append_estimates(con, "marks", marks(cars, year, t, idx, ref))
    results = check(con, t, idx, ref, last, before)
    write_report(con, t, idx, ref, results)
    print(f"{n:,} marks appended (curve month {ref}); " + ", ".join("pass" if ok else "FAIL" for _, ok in results))
    con.close()
    if not all(ok for _, ok in results):
        sys.exit("a check failed; see " + str(REPORT))


if __name__ == "__main__":
    main()
