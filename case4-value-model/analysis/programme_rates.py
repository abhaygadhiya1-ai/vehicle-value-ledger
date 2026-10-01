"""X25 part 3: what an in-house person costs, from official statistics, and the exchange rates for vendor prices.

Base 1 prices the work list at in-house pay. No public source gives pay for "a data engineer at a carmaker", so this
reads the nearest official cut and says so:

1. Pay: Eurostat's Structure of Earnings Survey 2022 (`earn_ses22_49`), mean annual gross earnings by one-digit
   occupation group (ISCO-08: managers OC1, professionals OC2, technicians OC3) in manufacturing (NACE C, the group's
   own sector), enterprises with 10 or more employees, in the core markets and one lower-cost hub (Poland).
2. To 2025: the growth of hourly wages and salaries in manufacturing, 2022 to 2025, from Eurostat's labour cost
   levels (`lc_lci_lev`, D11).
3. Employer costs on top of pay: labour costs other than wages and salaries against wages and salaries, manufacturing,
   2025 (`lc_lci_lev`, D12_D4_MD5 over D11): social contributions, taxes less subsidies, training and other employer
   costs. Office, equipment and management overhead are not in it.
4. Context: paid annual holidays (`earn_ses22_51`), for the working-days assumption; the share of enterprises that
   recruited ICT specialists and found vacancies hard to fill, 2024 (`isoc_ske_itrcrn2`).
5. Exchange rates: the ECB's monthly reference rates, the latest twelve months' average, for USD and GBP prices.

Run from case4-value-model/: .venv/bin/python analysis/programme_rates.py [--pull]. Downloads are cached in
data/raw/x25_rates/ (private, like all of data/); --pull re-reads them. Writes analysis/programme_rates_report.md.
"""
import json
import ssl
import sys
import urllib.request
from pathlib import Path

import certifi

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = ROOT / "data" / "raw" / "x25_rates"
COUNTRIES = {"FR": "France", "DE": "Germany", "IT": "Italy", "ES": "Spain", "PL": "Poland"}
GROUPS = {"OC1": "managers (OC1)", "OC2": "professionals (OC2)", "OC3": "technicians (OC3)"}
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
GEO = "".join(f"&geo={g}" for g in COUNTRIES)
QUERIES = {
    "ses_earnings": f"earn_ses22_49?format=JSON&lang=en&sex=T&nace_r2=C&sizeclas=GE10&unit=EUR&indic_se=ERN{GEO}",
    "ses_holidays": f"earn_ses22_51?format=JSON&lang=en&sex=T&nace_r2=C&sizeclas=GE10{GEO}",
    "labour_cost": f"lc_lci_lev?format=JSON&lang=en&nace_r2=C&unit=EUR&time=2022&time=2025{GEO}",
    "vacancies": f"isoc_ske_itrcrn2?format=JSON&lang=en&nace_r2=C&size_emp=GE10&indic_is=E_ITSPVAC2"
                 f"&unit=PC_ENT_ITSPRCR2&time=2024{GEO}",
}
ECB = "https://data-api.ecb.europa.eu/service/data/EXR/M.USD+GBP.EUR.SP00.A?format=jsondata&lastNObservations=12"


def fetch(name, url, pull):
    path = CACHE / f"{name}.json"
    if pull or not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        ctx = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(url, headers={"User-Agent": "case4-value-model"})
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            path.write_bytes(r.read())
    return json.loads(path.read_text())


def cells(d):
    """A Eurostat JSON-stat dataset as {tuple of category codes: value}, in the dataset's dimension order."""
    dims, size = d["id"], d["size"]
    inv = {k: {v: c for c, v in d["dimension"][k]["category"]["index"].items()} for k in dims}
    out = {}
    for pos, v in d["value"].items():
        p, codes = int(pos), []
        for k, n in reversed(list(zip(dims, size))):
            codes.append(inv[k][p % n])
            p //= n
        out[tuple(reversed(codes))] = v
    return dims, out


def pick(d, **want):
    dims, vals = cells(d)
    hits = [v for codes, v in vals.items() if all(codes[dims.index(k)] == w for k, w in want.items())]
    if len(hits) != 1:
        raise SystemExit(f"expected one value for {want}, found {len(hits)}")
    return hits[0]


def fmt(x, d=0):
    return f"{x:,.{d}f}"


def main():
    pull = "--pull" in sys.argv
    ses, hol, lc, vac = (fetch(k, EUROSTAT + q, pull) for k, q in QUERIES.items())
    fx = fetch("ecb_fx", ECB, pull)

    out = ["# What an in-house person costs, and the exchange rates (X25 part 3)", "",
           "Official statistics for base 1's pay, and the ECB's rates for vendor prices quoted in USD and GBP. Built by",
           "`analysis/programme_rates.py` from Eurostat and ECB downloads (cached in `data/raw/x25_rates/`).", "",
           "## Loaded annual cost of an employee, manufacturing, 2025 terms", "",
           "Mean annual gross earnings from the Structure of Earnings Survey 2022 (`earn_ses22_49`; manufacturing, NACE C;",
           "enterprises with 10 or more employees), carried to 2025 with the growth of hourly wages and salaries in",
           "manufacturing (`lc_lci_lev`, D11, 2022 to 2025), plus employer labour costs other than wages and salaries",
           "(`lc_lci_lev`, D12_D4_MD5 over D11, 2025). No overhead for offices, equipment or management is included.", "",
           "| Country and group | Earnings 2022 (EUR a year) | Wage growth 2022-2025 | Employer costs on pay | "
           "Loaded cost 2025 (EUR a year) |", "|---|---:|---:|---:|---:|"]
    for cc, country in COUNTRIES.items():
        d11_22 = pick(lc, geo=cc, time="2022", lcstruct="D11")
        d11_25 = pick(lc, geo=cc, time="2025", lcstruct="D11")
        d12_25 = pick(lc, geo=cc, time="2025", lcstruct="D12_D4_MD5")
        growth, load = d11_25 / d11_22, d12_25 / d11_25
        for g, gname in GROUPS.items():
            e22 = pick(ses, geo=cc, isco08=g)
            loaded = e22 * growth * (1 + load)
            out.append(f"| {country}, {gname} | {fmt(e22)} | {growth:.3f} | {100 * load:.1f}% | {fmt(loaded)} |")
    out += ["", "The occupation groups are one-digit ISCO-08, the finest the survey publishes by activity: a data "
            "engineer and a finance analyst are both professionals (OC2). Data specialists may earn more than their "
            "group's mean; the model takes that as a sensitivity, not a figure.", "",
            "## Paid annual holidays, manufacturing, 2022", "",
            "Mean annual holidays in days (`earn_ses22_51`; manufacturing, 10 or more employees), for the working-days "
            "assumption (`x25_days_per_fte_year`).", "",
            "| Country and group | Holidays (days a year) |", "|---|---:|"]
    for cc, country in COUNTRIES.items():
        for g, gname in GROUPS.items():
            out.append(f"| {country}, {gname} | {fmt(pick(hol, geo=cc, isco08=g), 1)} |")
    out += ["", "## Hard-to-fill ICT vacancies, manufacturing, 2024", "",
            "Share of enterprises that recruited or tried to recruit ICT specialists and had vacancies that were hard to "
            "fill (`isoc_ske_itrcrn2`; 10 or more employees). It measures difficulty, not months to hire.", "",
            "| Country | Recruiting enterprises with hard-to-fill ICT vacancies |", "|---|---:|"]
    for cc, country in COUNTRIES.items():
        out.append(f"| {country} | {pick(vac, geo=cc):.1f}% |")

    # ECB monthly reference rates: units of currency per euro, the latest twelve months
    ser = fx["dataSets"][0]["series"]
    sdim = fx["structure"]["dimensions"]["series"]
    cur_pos = [d["id"] for d in sdim].index("CURRENCY")
    months = [o["id"] for o in fx["structure"]["dimensions"]["observation"][0]["values"]]
    out += ["", "## Exchange rates", "",
            "ECB euro reference rates, monthly averages, the latest twelve months (units of currency per euro).", "",
            "| Currency | Units per euro, twelve-month average | First month | Last month |", "|---|---:|---|---|"]
    for key, s in sorted(ser.items()):
        cur = sdim[cur_pos]["values"][int(key.split(":")[cur_pos])]["id"]
        obs = [(months[int(i)], v[0]) for i, v in s["observations"].items() if v[0] is not None]
        obs.sort()
        out.append(f"| {cur} | {sum(v for _, v in obs) / len(obs):.4f} | {obs[0][0]} | {obs[-1][0]} |")
    (HERE / "programme_rates_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(line for line in out if line.startswith("| ") and ("OC2" in line or "USD" in line or "GBP" in line)))


if __name__ == "__main__":
    main()
