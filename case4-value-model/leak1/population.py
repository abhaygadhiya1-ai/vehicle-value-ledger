"""X1 part 1: the cars of the synthetic leak-1 world. Real cars, synthetic VINs.

Leak 1 is tested in a synthetic world with two legacy incentive systems and known answers. This
script builds the one table both systems will claim against: the sales record. Every other table
in X1 is generated from it, so it is the truth the leaks are scored against.

**The cars are real.** Every group-brand passenger car first put on Dutch plates new in 2021-2022,
the two years after the merger closed, from the RDW register (public domain, one row per car):
make, model, first registration date, catalogue price, body, variant and trim. "New" means the
first registration date equals the first Dutch registration date, which drops used imports. Cars
with no catalogue price are dropped, and the count is printed. Plates are read only to fix the row
order and are not stored.

**The VINs are synthetic.** 17 characters, no I, O or Q (ISO 3779):
  1-3    the brand's real WMI, one per brand (sources below). Real VINs vary by plant.
  4-8    a made-up model code, the same for every car of a model
  9      a North American check digit. Europe does not require one (~, not yet checked for PSA
         or FCA), so later parts must not rely on it to catch typos unless research confirms it.
  10     model-year code, taken from the registration year (an approximation)
  11     a made-up plant code, one per model
  12-17  serial number: a sparse random draw within each WMI, rising with registration date, the
         way one market's cars sit inside a plant's production run

Output: data/synthetic/x1_cars.parquet (not published: data/ is outside the allowlist).
Usage: .venv/bin/python leak1/population.py
"""
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build_reference import RDW_URL, align_names, rdw_group  # noqa: E402
from build_unified import MAKE_ALIASES, STELLANTIS, norm_name  # noqa: E402

OUT = HERE.parent / "data" / "synthetic" / "x1_cars.parquet"
REF = HERE.parent / "data" / "reference" / "rdw_new_prices.parquet"
SEED = 20210116  # the day the merger closed
PAGE = 50_000
START, STOP = "2021-01-01", "2023-01-01"

# One WMI per brand. vPIC = NHTSA's WMI register, https://vpic.nhtsa.dot.gov/api/ (DecodeWMI,
# GetWMIsForManufacturer); Wikibooks = https://en.wikibooks.org/wiki/Vehicle_Identification_Numbers_(VIN_codes)/World_Manufacturer_Identifier_(WMI)
WMI = {
    "peugeot": "VF3",     # vPIC: AUTOMOBILES PEUGEOT
    "citroen": "VF7",     # Wikibooks
    "ds": "VR1",          # Wikibooks
    "opel": "W0L",        # vPIC: ADAM OPEL AG
    "fiat": "ZFA",        # vPIC: STELLANTIS EUROPE S.P.A.
    "abarth": "ZFA",      # ASSUMPTION: no WMI of its own found; Abarths are built by Fiat
    "alfa romeo": "ZAR",  # vPIC: ALFA ROMEO S.P.A.
    "lancia": "ZLA",      # Wikibooks
    "jeep": "ZAC",        # vPIC: FCA ITALY S.P.A.; Wikibooks lists ZAC as Jeep
    "maserati": "ZAM",    # vPIC: MASERATI S.P.A.
    "chrysler": "1C4", "dodge": "1C4", "ram": "1C4",  # vPIC: FCA US LLC
}

ALPHABET = "0123456789ABCDEFGHJKLMNPRSTUVWXYZ"  # no I, O, Q
YEAR_CODES = "ABCDEFGHJKLMNPRSTVWXY123456789"    # position 10, a 30-year cycle from 1980
# check digit, 49 CFR 565: letters transliterate to numbers, positions carry weights
TRANSLIT = {**{str(d): d for d in range(10)}, **dict(zip("ABCDEFGH", range(1, 9))),
            **dict(zip("JKLMN", range(1, 6))), "P": 7, "R": 9,
            **dict(zip("STUVWXYZ", range(2, 10)))}
WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def check_digit(vin):
    r = sum(TRANSLIT[c] * w for c, w in zip(vin, WEIGHTS)) % 11
    return "X" if r == 10 else str(r)


def is_valid_vin(vin, with_check_digit=True):
    """Format check. `with_check_digit=False` is the European reading, where position 9 is free."""
    ok = len(vin) == 17 and set(vin) <= set(ALPHABET)
    return ok and (not with_check_digit or vin[8] == check_digit(vin))


def code(text, n):
    """n characters from the VIN alphabet, fixed by the text (sha256, so stable across runs)."""
    h = int(hashlib.sha256(text.encode()).hexdigest(), 16)
    out = ""
    for _ in range(n):
        h, i = divmod(h, len(ALPHABET))
        out += ALPHABET[i]
    return out


def assign_vins(cars, seed=SEED):
    """One synthetic VIN per car. `cars` must be in registration-date order."""
    rng = np.random.default_rng(seed)
    wmi = cars["make"].map(WMI)
    serial = pd.Series(0, index=cars.index)
    for w in sorted(wmi.unique()):
        idx = cars.index[wmi == w]
        serial[idx] = np.sort(rng.choice(10**6, size=len(idx), replace=False))
    model = cars["make"] + "|" + cars["model"]
    vds = model.map({m: code(m, 5) for m in model.unique()})
    plant = model.map({m: code("plant|" + m, 1) for m in model.unique()})
    year = cars["first_reg_date"].dt.year.map(lambda y: YEAR_CODES[(y - 1980) % 30])
    stem = wmi + vds + "0" + year + plant + serial.map("{:06d}".format)
    return pd.Series([s[:8] + check_digit(s) + s[9:] for s in stem], index=cars.index)


def pull(where):
    cols = ["kenteken", "merk", "handelsbenaming", "datum_eerste_toelating_dt", "catalogusprijs",
            "inrichting", "variant", "uitvoering"]
    pages, offset = [], 0
    while True:
        r = requests.get(RDW_URL, params={"$select": ",".join(cols), "$where": where,
                                          "$order": "kenteken", "$limit": PAGE,
                                          "$offset": offset}, timeout=900)
        r.raise_for_status()
        pages.append(pd.DataFrame(r.json()))
        print(f"  pulled {offset + len(pages[-1]):,}", flush=True)
        if len(pages[-1]) < PAGE:
            break
        offset += PAGE
    return pd.concat(pages, ignore_index=True).reindex(columns=cols)


def main():
    assert is_valid_vin("1M8GDM9AXKP042788")  # the textbook example, check digit X
    window = (f"voertuigsoort='Personenauto' "
              f"AND datum_eerste_toelating_dt >= '{START}T00:00:00.000' "
              f"AND datum_eerste_toelating_dt < '{STOP}T00:00:00.000' "
              "AND datum_eerste_tenaamstelling_in_nederland_dt = datum_eerste_toelating_dt")
    makes = rdw_group("merk,count(1) AS n", window, "merk", limit=50_000)
    group = sorted(makes.loc[norm_name(makes["merk"]).replace(MAKE_ALIASES).isin(STELLANTIS),
                             "merk"])
    print("group spellings in RDW:", group)
    where = window + " AND merk IN (" + ",".join("'" + m.replace("'", "''") + "'" for m in group) + ")"
    n_all = int(rdw_group("count(1) AS n", where, "")["n"].iloc[0])
    where += " AND catalogusprijs IS NOT NULL"
    n_priced = int(rdw_group("count(1) AS n", where, "")["n"].iloc[0])
    print(f"RDW count: {n_all:,} new group cars, {n_priced:,} with a catalogue price "
          f"({n_all - n_priced:,} dropped)")

    raw = pull(where)
    assert len(raw) == n_priced, (len(raw), n_priced)
    make, model = align_names(raw["merk"], raw["handelsbenaming"])
    cars = pd.DataFrame({
        "make": make, "model": model,
        "first_reg_date": pd.to_datetime(raw["datum_eerste_toelating_dt"]),
        "list_price_eur": pd.to_numeric(raw["catalogusprijs"]).astype("int64"),
        "body": raw["inrichting"], "variant": raw["variant"], "trim": raw["uitvoering"],
        "plate": raw["kenteken"],
    })
    unmapped = set(cars["make"]) - set(WMI)
    assert not unmapped, f"no WMI for {unmapped}"
    cars = (cars.sort_values(["first_reg_date", "plate"], ignore_index=True)
                .drop(columns="plate"))
    cars.insert(0, "car_id", np.arange(1, len(cars) + 1))
    vins = assign_vins(cars)
    assert vins.equals(assign_vins(cars)), "VIN assignment is not deterministic"
    cars.insert(1, "vin", vins)

    # checks
    valid = cars["vin"].map(is_valid_vin)
    wmi_ok = cars["vin"].str[:3] == cars["make"].map(WMI)
    print(f"VINs: {valid.mean():.2%} valid, {cars['vin'].duplicated().sum()} duplicates, "
          f"{wmi_ok.mean():.2%} carry their brand's WMI")
    assert valid.all() and not cars["vin"].duplicated().any() and wmi_ok.all()

    ours = (cars.assign(year=cars["first_reg_date"].dt.year)
                .groupby(["make", "model", "year"])["list_price_eur"]
                .agg(n="size", median="median").reset_index())
    # the reference can hold one key twice (two RDW spellings normalise to one name, e.g. two
    # rows for the 2022 Fiat 500): keep the most common spelling so each car is compared once
    ref = (pd.read_parquet(REF).sort_values("n", ascending=False)
             .drop_duplicates(["make", "model", "year"])[["make", "model", "year", "new_price_eur"]])
    m = ours.merge(ref, on=["make", "model", "year"], how="left")
    gap = (m["median"] / m["new_price_eur"] - 1).abs()
    w = m["n"] / m["n"].sum()
    print(f"price check vs rdw_new_prices (all first registrations, imports included): "
          f"{w[m['new_price_eur'].notna()].sum():.1%} of cars in a matched model-year; "
          f"gap within 5%: {w[gap <= 0.05].sum():.1%} of cars, within 10%: "
          f"{w[gap <= 0.10].sum():.1%}; median gap {gap.median():.1%}")

    print("\ncars by make and registration year:")
    print(cars.groupby([cars["make"], cars["first_reg_date"].dt.year]).size()
              .unstack(fill_value=0).to_string())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cars.to_parquet(OUT, index=False)
    print(f"\nwrote {OUT.relative_to(HERE.parent)}: {len(cars):,} cars, "
          f"{OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
