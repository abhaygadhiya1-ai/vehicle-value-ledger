"""X11 part 2: two snapshots of Finland's open vehicle file, and whether one car can be followed from one to the next.

The UK result "mileage predicts disposal, not sale" (`readiness_mileage_report.md`) rests on one register. Finland's
open vehicle file (Traficom, CC BY 4.0) lists every vehicle in traffic use with the odometer reading found at its
last inspection. A car in one snapshot and absent a year later has left traffic use: scrapped, exported or laid up,
the same proxy as the UK's "not tested again". Before that can be measured (part 3), four things must hold:

1. **Can a car be followed?** `jarnro` ("running numbering") may be an id or just a row number. If it is an id, the
   fixed attributes of the row carrying it must agree across snapshots.
2. **If not, how unique is a key of fixed attributes?** Exact first-registration date, the first 10 VIN characters,
   make, model, variant, version, type approval, mass, power, engine size, fuel, body, doors, seats, colour. Only keys
   unique in both files are used. Its failures are bounded without ground truth: a matched car's reading should not
   fall; young cars rarely leave traffic use, so their apparent exits cap the key's misses; and cars registered
   before the first snapshot that appear only in the second are either re-entries or misses.
3. **What share of cars carry a reading, by age.**
4. **When are readings taken.** The inspection interval by age, stated by Traficom and checked in the data: the
   share of matched cars whose reading changed between the snapshots.

Sources: Traficom, Ajoneuvojen avoin data (open vehicle data), https://opendata.traficom.fi/Content/Ajoneuvorekisteri.zip
(the current file), and the Internet Archive's capture of the same URL of 7 September 2025
(https://web.archive.org/web/20250907204015id_/https://opendata.traficom.fi/Content/Ajoneuvorekisteri.zip), checked
against the Archive's SHA-1. The zips and the passenger-car extracts are kept in data/raw/traficom/ (private).
Usage: .venv/bin/python analysis/fi_register.py
"""
import base64
import codecs
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pcsv
import pyarrow.parquet as pq

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
RAW = HERE.parent / "data" / "raw" / "traficom"
OUT = HERE / "fi_register_report.md"

URL = "https://opendata.traficom.fi/Content/Ajoneuvorekisteri.zip"
# name: (url, sha1 in base32 as the Internet Archive prints it; None = the live file, hashed and reported)
SNAPSHOTS = {
    "2024-10": ("https://web.archive.org/web/20241001114320id_/" + URL, "NVNQP6V2NGPLWRMBRTWBSS3LVFS7XDBI"),
    "2025-09": ("https://web.archive.org/web/20250907204015id_/" + URL, "6BNXLGVRXNT5EL7YTEWECWJGS62B7N2T"),
    "2026-07": (URL, None),
}
CARS = ["M1", "M1G"]  # passenger cars, and off-road passenger cars


def sha1_b32(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return base64.b32encode(h.digest()).decode()


def download(name):
    url, sha = SNAPSHOTS[name]
    path = RAW / f"Ajoneuvorekisteri_{name}.zip"
    if not path.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, path)
    got = sha1_b32(path)
    if sha and got != sha:
        raise SystemExit(f"{path.name}: sha1 {got}, expected {sha}")
    return path, got


def extract(name):
    """Stream one zip; keep passenger cars in a typed parquet; count every row by class."""
    path, sha = download(name)
    out = RAW / f"fi_{name}_cars.parquet"
    z = zipfile.ZipFile(path)
    (member,) = z.infolist()
    stats = {"zip": path.name, "sha1": sha, "member": member.filename, "zipped": "%04d-%02d-%02d" % member.date_time[:3]}
    if out.exists():
        return out, pq.read_metadata(out).metadata, stats
    with z.open(member) as f:
        columns = f.readline().decode().strip().split(";")
    # Arrow reads a temporary unpacked copy, not the zip stream: its I/O threads, blocked on a Python file object,
    # stop Python exiting after any error (seen twice in part 2). The copy is written as UTF-8 whatever the release's
    # encoding, so make and model strings compare exactly across snapshots.
    csv = RAW / member.filename
    stats["encoding"] = unpack_utf8(z, member, csv)
    try:
        return _stream(csv, columns, out, stats)
    finally:
        csv.unlink()


def unpack_utf8(z, member, csv):
    """Write the member as UTF-8. The encoding changed between releases: the 2025 file is UTF-8, the 2026 file
    Latin-1 (every non-ASCII line invalid UTF-8). Latin-1 is accepted only without bytes 0x80-0x9F, where
    cp1252 would read differently."""
    for enc in ("utf-8", "latin-1"):
        dec = codecs.getincrementaldecoder(enc)()
        try:
            with z.open(member) as f, open(csv, "w", encoding="utf-8", newline="") as g:
                for block in iter(lambda: f.read(16 << 20), b""):
                    if enc == "latin-1" and any(0x80 <= c <= 0x9F for c in set(block)):
                        raise SystemExit(f"{member.filename}: bytes 0x80-0x9F, neither UTF-8 nor Latin-1")
                    g.write(dec.decode(block))
                g.write(dec.decode(b"", final=True))
            return enc
        except UnicodeDecodeError:
            continue


def _stream(csv, columns, out, stats):
    # every column as text: inferred types would turn codes such as "01" into 1. Some model names are quoted and
    # hold a ";".
    reader = pcsv.open_csv(
        csv,
        read_options=pcsv.ReadOptions(block_size=16 << 20),
        parse_options=pcsv.ParseOptions(delimiter=";"),
        convert_options=pcsv.ConvertOptions(column_types={c: pa.string() for c in columns}, strings_can_be_null=True),
    )
    part = out.with_suffix(".part")
    writer, n, n_by_class, prev, gaps, max_reg = None, 0, {}, 0, 0, None
    for batch in reader:
        batch = pa.Table.from_batches([batch])
        n += batch.num_rows
        for d in pc.value_counts(batch["ajoneuvoluokka"]).to_pylist():
            n_by_class[d["values"]] = n_by_class.get(d["values"], 0) + d["counts"]
        j = pc.cast(batch["jarnro"], pa.int64())
        steps = pc.subtract(j.slice(1), j.slice(0, len(j) - 1))
        gaps += (j[0].as_py() != prev + 1) + (len(j) - 1 - pc.sum(pc.equal(steps, 1)).as_py())
        prev = j[-1].as_py()
        # the 2024 release writes this date as 2003-06-10, later ones as 10.06.2003
        reg = pc.cast(pc.coalesce(*(pc.strptime(batch["ensirekisterointipvm"], format=fmt, unit="s", error_is_null=True)
                                    for fmt in ("%d.%m.%Y", "%Y-%m-%d"))), pa.date32())
        m = pc.max(reg).as_py()
        max_reg = m if max_reg is None or (m and m > max_reg) else max_reg
        keep = pc.is_in(batch["ajoneuvoluokka"], pa.array(CARS))
        t = batch.filter(keep)
        t = t.append_column("reg_date", reg.filter(keep))
        t = t.set_column(t.schema.get_field_index("jarnro"), "jarnro", pc.cast(t["jarnro"], pa.int64()))
        t = t.append_column("odo", pc.cast(t["matkamittarilukema"], pa.int64()))
        if writer is None:
            writer = pq.ParquetWriter(part, t.schema, compression="zstd")
        writer.write_table(t)
    meta = {"rows": n, "jarnro_gaps": gaps, "jarnro_last": prev, "max_reg_date": str(max_reg),
            "encoding": stats["encoding"],
            "columns": ",".join(columns), **{f"class_{k}": v for k, v in n_by_class.items()}}
    # the whole-file counts go in the parquet footer, so a rerun needs no second pass over the zip
    writer.add_key_value_metadata({k: str(v) for k, v in meta.items()})
    writer.close()
    part.rename(out)
    return out, pq.read_metadata(out).metadata, stats



# The key: fixed attributes of one car. Part 2 measured each on pairs matched by the first four; colour changes on
# under 0.1% of pairs and makes a key unique for far more cars, so it is in. Municipality and use change and are out.
K0 = ["reg_date", "valmistenumero2", "merkkiSelvakielinen", "mallimerkinta"]
K1 = K0 + ["kayttoonottopvm", "variantti", "versio", "tyyppihyvaksyntanro", "kaupallinenNimi"]
K2 = K1 + ["omamassa", "teknSuurSallKokmassa", "ajonKokPituus", "ajonLeveys", "ajonKorkeus", "iskutilavuus",
           "suurinNettoteho", "sylintereidenLkm", "korityyppi", "ovienLukumaara", "istumapaikkojenLkm", "vaihteisto",
           "kayttovoima"]
K3 = K2 + ["vari"]
KEYS = {"K0": K0, "K1": K1, "K2": K2, "K3": K3}
CHANGING = ["kunta", "ajoneuvonkaytto"]


def meta(name):
    return {k.decode(): v.decode() for k, v in pq.read_metadata(RAW / f"fi_{name}_cars.parquet").metadata.items()
            if k != b"ARROW:schema"}


def load(name, extra=()):
    """One snapshot's cars: hashed keys K0-K3, the reading, and age at the file's data date.

    The data date is the latest first-registration date in the whole file. Age is exact years since first use
    (`kayttoonottopvm`, the date inspections count from) where its day is known, else the difference in years.
    `imported` marks a car first registered in Finland more than 180 days after its first use: a used import. (Of
    cars first used since 2015, about three-quarters are registered on the day of first use, a sixth more than 180
    days later, and a few per cent in between, which are left unflagged.)"""
    cols = list(dict.fromkeys(K3 + ["odo", *extra]))
    t = pq.read_table(RAW / f"fi_{name}_cars.parquet", columns=cols,
                      read_dictionary=[c for c in cols if c not in ("reg_date", "odo")])
    d = t.to_pandas()
    asof = pd.Timestamp(meta(name)["max_reg_date"])
    use = d["kayttoonottopvm"].astype(object)
    full = pd.to_datetime(use, format="%Y%m%d", errors="coerce")
    year = pd.to_numeric(use.str[:4], errors="coerce")
    d["age"] = ((asof - full).dt.days / 365.25).where(full.notna(), asof.year - year)
    d["first_use"] = full
    d["imported"] = (pd.to_datetime(d["reg_date"]) - full).dt.days > 180
    d["reg_date"] = d["reg_date"].astype("category")
    for k, c in KEYS.items():
        d[k] = pd.util.hash_pandas_object(d[c], index=False).to_numpy()
    return d.drop(columns=[c for c in K3 if c not in extra])


def pairs(a, b, key="K3"):
    """The first snapshot's key-unique cars; `found` marks those present, once, in the second. A car whose key the
    second snapshot holds twice can't be followed and is left out, not counted as gone."""
    ua, ub = ~a[key].duplicated(keep=False), ~b[key].duplicated(keep=False)
    left = a[ua & ~a[key].isin(b.loc[~ub, key])]
    right = b.loc[ub].drop(columns=[c for c in b.columns if c in left.columns and c != key])
    right = right.assign(odo_b=b.loc[ub, "odo"], found=True)
    m = left.merge(right, on=key, how="left")
    m["found"] = m["found"].fillna(False).astype(bool)
    return m


def panel(extra=()):
    """The first snapshot's key-unique cars, each marked found or not in the second: part 3's input."""
    a, b = load("2025-09", extra), load("2026-07")
    return pairs(a, b)


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def main():
    from build_unified import md_table
    rows = []
    for name in SNAPSHOTS:
        _, m, st = extract(name)
        md = meta(name)
        rows.append({"snapshot": name, "file": st["member"], "sha1": st["sha1"], "data date": md["max_reg_date"], "encoding": md["encoding"],
                     "rows": f"{int(md['rows']):,}", "jarnro gaps": md["jarnro_gaps"],
                     "cars (M1, M1G)": f"{int(md['class_M1']) + int(md['class_M1G']):,}"})
    files = pd.DataFrame(rows)

    # 1. jarnro across snapshots
    cols = ["jarnro", "reg_date", "mallimerkinta"]
    ja, jb = (pq.read_table(RAW / f"fi_{n}_cars.parquet", columns=cols).to_pandas() for n in ("2025-09", "2026-07"))
    jm = ja.merge(jb, on="jarnro", suffixes=("_a", "_b"))
    same = (jm.reg_date_a == jm.reg_date_b) & (jm.mallimerkinta_a == jm.mallimerkinta_b)
    first_bad = int(jm.loc[~same, "jarnro"].min())
    del ja, jb, jm

    a = load("2025-09", extra=K3 + CHANGING)
    b = load("2026-07", extra=K3 + CHANGING)

    # 2. which attributes change on pairs matched by K0 alone
    m0 = a[~a.K0.duplicated(keep=False)].merge(b[~b.K0.duplicated(keep=False)], on="K0", suffixes=("_a", "_b"))
    ch = []
    for c in [x for x in K3 if x not in K0] + CHANGING:
        x, y = m0[c + "_a"].astype(object), m0[c + "_b"].astype(object)
        ch.append({"attribute": c, "in key": "no" if c in CHANGING else ("K3 only" if c == "vari" else "yes"),
                   "differs on K0 pairs": pct((~((x == y) | (x.isna() & y.isna()))).mean(), 3)})
    changes = pd.DataFrame(ch)
    n_m0 = len(m0)
    del m0
    young4 = a[a.age < 4]
    imports = pd.DataFrame([{"age": int(k), "imported": pct(g.imported.mean()),
                             "reading if imported": pct(g.odo[g.imported].notna().mean()),
                             "reading if not": pct(g.odo[~g.imported].notna().mean())}
                            for k, g in young4.groupby(young4.age.astype(int))])
    a = a.drop(columns=[c for c in K3 + CHANGING if c != "reg_date"])
    b = b.drop(columns=[c for c in K3 + CHANGING if c != "reg_date"])
    b_before = pd.to_datetime(b["reg_date"].astype(object)) < pd.Timestamp(meta("2025-09")["max_reg_date"])

    # 3. the keys, scored without ground truth
    kr = []
    for k in KEYS:
        m = pairs(a, b, k)
        ub = ~b[k].duplicated(keep=False)
        back = b.loc[ub & b_before, k].isin(m.loc[m.found, k])
        both = m.odo.notna() & m.odo_b.notna()
        kr.append({"key": k, "attributes": len(KEYS[k]), "unique in 2025": pct((~a[k].duplicated(keep=False)).mean()),
                   "unique in 2026": pct(ub.mean()), "found a year later": pct(m.found.mean()),
                   "1-3-year-olds not found": pct(1 - m.loc[m.age.between(1, 4, inclusive="left"), "found"].mean(), 2),
                   "readings that fell": pct((m.odo_b[both] < m.odo[both]).mean(), 2),
                   "2026 cars first registered before 1 Jul 2025, not in 2025": pct(1 - back.mean(), 2)})
    keys = pd.DataFrame(kr)

    # 4. how many K3 misses are the same car with a changed attribute: an unfound 2025 car and an unmatched 2026
    # car that agree on K1 (or K0), each unique on it in its whole file
    m = pairs(a, b)
    gone = m[~m.found]
    new = b[~b.K3.duplicated(keep=False) & ~b.K3.isin(m.loc[m.found, "K3"]) & b_before]
    near = {}
    for k in ["K1", "K0"]:
        ga = gone[gone[k].isin(a.loc[~a[k].duplicated(keep=False), k])]
        nb = new[new[k].isin(b.loc[~b[k].duplicated(keep=False), k])]
        near[k] = gone[k].isin(ga[k][ga[k].isin(nb[k])]).mean()
    gy = gone[gone.age.between(1, 4, inclusive="left")]
    ny = new[new.K0.isin(b.loc[~b.K0.duplicated(keep=False), "K0"])]
    young_near = gy.K0.isin(ny.K0).mean()

    # 5. readings by age, and 6. did the reading change over the year (the inspection rule, tested)
    bins = list(range(0, 16)) + [20, 30, 200]
    lab = [str(x) for x in range(0, 15)] + ["15-19", "20-29", "30+"]
    cut = lambda s: pd.cut(s, bins=bins, right=False, labels=lab)  # noqa: E731
    ra = a.groupby(cut(a.age), observed=False).odo.apply(lambda s: s.notna().mean())
    rb = b.groupby(cut(b.age), observed=False).odo.apply(lambda s: s.notna().mean())
    mf = m[m.found].copy()
    mf["changed"] = mf.odo_b.notna() & (mf.odo_b != mf.odo)
    g = mf.groupby(cut(mf.age), observed=False)
    rule = {**{str(x): "none due before 4" for x in range(0, 3)}, "3": "first, by 4", "4": "not due (4, 6, 8)",
            "5": "due (4, 6, 8)", "6": "not due (4, 6, 8)", "7": "not due (mostly before the reform: 3, 5, 7, 9)",
            "8": "due (before the reform: 3, 5, 7, 9)", "9": "due by 10 y 0 m", **{x: "yearly" for x in lab[10:]}}
    ages = pd.DataFrame({"age (years since first use)": lab,
                         "reading, 2025": [pct(ra[x]) for x in lab], "reading, 2026": [pct(rb[x]) for x in lab],
                         "found cars": [f"{len(g.get_group(x)):,}" if x in g.groups else "0" for x in lab],
                         "reading changed in the year": [pct(g.changed.mean()[x]) for x in lab],
                         "the rule over that year": [rule[x] for x in lab]})
    # 7. which cycle: cars first used before the 2018 reform kept their old next date, then took 2-year steps
    reform = pd.Timestamp("2018-05-20")
    dom = mf[~mf.imported & mf.first_use.between("2015-07-01", "2019-06-30")].copy()
    dom["half"] = dom.first_use.dt.year.astype(str) + "H" + ((dom.first_use.dt.month > 6) + 1).astype(str)
    asof_a, asof_b = pd.Timestamp(meta("2025-09")["max_reg_date"]), pd.Timestamp(meta("2026-07")["max_reg_date"])

    def due(first_use, ages):
        """Does an inspection age fall in the year between the snapshots, for a car first used on this date?"""
        return any(asof_a < first_use + pd.DateOffset(years=x) <= asof_b for x in ages)
    ODD, EVEN = (3, 5, 7, 9, 10), (4, 6, 8, 10)
    coh = []
    for h, g in dom.groupby("half"):
        mid = g.first_use.median()
        rule = ODD if mid < reform else EVEN
        coh.append({"first used": h, "cars": f"{len(g):,}", "reading changed in the year": pct(g.changed.mean()),
                    "odd cycle (3, 5, 7, 9) predicts": "due" if due(mid, ODD) else "not due",
                    "even cycle (4, 6, 8) predicts": "due" if due(mid, EVEN) else "not due",
                    "the rule for this cohort": "odd" if rule is ODD else "even"})
    cohorts = pd.DataFrame(coh)
    uq = m.assign(u=True).groupby(cut(m.age), observed=False).size() / a.groupby(cut(a.age), observed=False).size()
    uq_lo, uq_hi = uq.min(), uq.max()
    chosen = keys.set_index("key").loc["K3"]

    OUT.write_text(f"""# X11 part 2: can one Finnish car be followed from one snapshot to the next?

Snapshots of Traficom's open vehicle file, a year apart. Every vehicle in traffic use is a row; passenger cars (M1
and M1G) are kept. A car present in one and absent a year later has left traffic use, which part 3 relates to its
mileage. This part checks, on 2025 against 2026, that the follow-up can be done and what the odometer field means.
Part 3 adds 2024 (`fi_exit_report.md`).

{md_table(files)}

The data date is the latest first-registration date in the file: 30 June of each year, exactly a year apart. The 2026
file is named for it. Its `jarnro` skips a few numbers (the gaps are in Traficom's file; the raw lines match the
parsed rows). The releases differ in encoding; each is read as the same text.

## `jarnro` is a row number, not an id

For cars carrying the same `jarnro` in both files, first-registration date and model agree from row 1 to row
{first_bad - 1} and almost never after (from row {first_bad} on). The number counts rows in each release; it cannot follow a car.

## A key of fixed attributes

On the {n_m0:,} cars that the first four attributes (exact first-registration date, first 10 VIN characters, make,
model) match one to one, how often does each other attribute differ a year later?

{md_table(changes)}

The fixed attributes almost never change, and many differences are a blank on one side. Colour changes rarely
and separates many identical cars registered on the same day. Municipality and use change, so they are left out.

{md_table(keys)}

Each key uses only cars unique on it in both files. **K3 is chosen:** all fixed attributes plus colour. It is
unique for the most cars, and it does best on every check that needs no ground truth. Three checks follow.

- **Readings that fell.** A car's odometer reading should not fall. On K3 pairs it falls for
  {chosen['readings that fell']}, which bounds wrong matches plus clocked or replaced odometers.
- **Young cars not found.** Cars of 1-3 years seldom leave traffic use, so their rate caps how often the key loses a car.
- **Unmatched 2026 cars.** A 2026 car first registered before July 2025 and not found in 2025 is a re-entry from lay-up,
  a car whose key twin left (so it became unique), or a key failure.

**How many losses are key failures?** There are two bounds.

- **Lower bound.** A lost 2025 car and an unmatched 2026 car that agree on a shorter key, unique in each whole file,
  are probably one car with a changed attribute. That describes {pct(near['K1'])} of lost cars on K1, and
  {pct(near['K0'])} on K0 ({pct(young_near)} of lost 1-3-year-olds). This misses a change in the first four
  attributes, which the table shows the file almost never makes.
- **Upper bound.** Suppose every lost 1-3-year-old were a key failure. Then the key would lose
  {chosen['1-3-year-olds not found']} of cars at any age. Part 3 compares cars within one age cohort, so an
  error that doesn't depend on mileage dilutes the contrast; it doesn't create one.

The cars K3 cannot separate are mostly pairs of identical cars registered on the same day in the same colour;
missing fields explain few. The key-unique share by age runs from {pct(uq_lo)} to {pct(uq_hi)}. Part 3 measures
within age cohorts, so this changes the weights between ages, not the comparison within one.

## The odometer reading, and when it is taken

Traficom's rule for passenger cars (verified 26 September 2026 at
https://traficom.fi/fi/autoilijat/katsastus/katsastusajankohdat-ajoneuvoluokittain):

- the first inspection is due at the latest 4 years after the car's date of first use (*käyttöönottopäivä*);
- after that, at the latest 2 years after the previous one;
- once more than 10 years have passed since first use, yearly;
- a car inspected at 8-9 years is still due by 10 years 0 months;
- privately used cars 40 years past their year of first use are inspected every 2 years (since 14 May 2020).

`matkamittarilukema` is "the last odometer reading found during the inspection". It is dated by the inspection, not
by the snapshot.

{md_table(ages)}

**Readings under 4 years are imports.** A used import is inspected when it is first registered in Finland, so
it carries a reading. A domestic car rarely does before its first periodic inspection:

{md_table(imports)}

**The reform of 20 May 2018 shows in the data.** Trafi's page on the new intervals (updated 18 May 2018, Internet
Archive capture of 27 May 2018:
https://web.archive.org/web/20180527194205/https://www.trafi.fi/tieliikenne/katsastus/uudet_katsastusajat)
says: "Seuraava katsastus määräytyy edellisen katsastuksen mukaan. Vasta kun ajoneuvo katsastetaan hyväksytysti uusien
säännösten voimassaoloaikana, seuraavan katsastuksen ajankohta määräytyy uusien säännösten mukaisesti." That is: the
next inspection follows from the previous one, and only after a pass under the new rules does the new schedule apply.
Its examples: a car first used on 20 May 2018 is first due by 20 May 2022. Since the reform, the date also rolls
from the last inspection, not from first use. So a car inspected early moves its whole cycle forward.

The data show two cycles. Cars first used before the reform keep the old first inspection at 3 years, then take
2-year steps: 3, 5, 7, 9. Later cars follow 4, 6, 8. For domestic cars (imports start their cycle at import), the
two cycles predict opposite years for the 2016-18 cohorts, and the data follow the one each cohort's first-use
date gives:

{md_table(cohorts)}

(The old first inspection at 3 years is from secondary sources, not opened at Traficom. The data show it as the
odd cycle. Predictions use each half-year's median first-use date, so a cohort crossing a deadline mixes.)

**What part 3 must do.** A reading is up to two years old for cars of 4-10 years, and up to one year old after 10.
Within an age cohort, a car just inspected and one due next month carry readings a year apart. Part 3 therefore
compares mileage within cohorts of the same age and first-use half-year, or uses cars whose reading changed in the
year before the baseline. Domestic cars under 4 carry almost no reading and are left out, as the UK's under-3s are.

## Limits

- **Leaving traffic use is a proxy.** It covers scrapping, export and temporary lay-up. Finland publishes no per-car
  reason in this file. A laid-up car can return, as the unmatched 2026 cars show.
- **K3 drops the non-unique cars:** identical cars registered on the same day. They are excluded, not guessed.
- **One pair of snapshots, one year.**
""")
    print(OUT.read_text()[:600])


if __name__ == "__main__":
    main()
