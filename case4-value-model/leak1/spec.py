"""X1 part 2: the two legacy incentive systems, written down before any claim exists.

The case says dealer incentives "run on separate inherited systems with different rules, processes, and definitions
of an eligible sale", and that "many dealers interact with both systems simultaneously". No legacy PSA or FCA claim
format is public (the X1 deep research found none), so everything below that the case does not state is our own
choice for a synthetic world. It measures the tool, not the group.

**Frozen before the detectors.** The spec is fixed before any detector is built. Detectors may read this rulebook,
because a real team knows its own programmes, but they read the truth table only to be scored. This answers the
known trap of one team writing both the generator and the detector.

Every setting carries its provenance:
  CASE        the case text says it
  SOURCED     a public source, URL given, opened by us
  MEASURED    our own measurement on real data, read from the project register (`assumptions.csv`) by its id
  ASSUMPTION  our choice for the synthetic world

Usage: .venv/bin/python leak1/spec.py   (runs the checks against the part 1 cars)
"""
import csv
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
CARS = HERE.parent / "data" / "synthetic" / "x1_cars.parquet"
REGISTER = HERE.parent / "assumptions.csv"


def register_value(rid):
    """A figure we measured on real data, read from the register rather than typed."""
    rows = {r["id"]: r for r in csv.DictReader(REGISTER.open())}
    return float(rows[rid]["value"])


# ---------- which system a car's claims go to ----------
# CASE: "separate inherited systems". The split follows each brand's owner before the merger (Opel was PSA's).
SYSTEM_OF_BRAND = {"peugeot": "A", "citroen": "A", "ds": "A", "opel": "A",
                   "fiat": "B", "abarth": "B", "alfa romeo": "B", "lancia": "B", "jeep": "B",
                   "maserati": "B", "chrysler": "B", "dodge": "B", "ram": "B"}

# ---------- scalar settings: (value, provenance, note) ----------
SETTINGS = {
    "vat_nl": (0.21, "SOURCED", "https://business.gov.nl/finance-and-taxes/vat/vat-rates-and-exemptions/"),
    "dealers_a_only": (90, "ASSUMPTION", "dealers on system A only"),
    "dealers_b_only": (20, "ASSUMPTION", "dealers on system B only"),
    "dealers_both": (40, "ASSUMPTION", "CASE says 'many dealers' sit on both; the count is ours"),
    "fleet_share": (0.40, "ASSUMPTION", "share of sales to fleet buyers"),
    "conquest_share": (0.20, "ASSUMPTION", "share of private buyers coming from a non-group brand"),
    "b_registration_within_days": (180, "ASSUMPTION",
                                   "borrowed from the Italian Ecobonus rule (~, snippet); the booking-before-"
                                   "registration mechanism itself is SOURCED: "
                                   "https://ecobonus.mimit.gov.it/iter-di-prenotazione"),
    "volume_target_share": (0.95, "ASSUMPTION",
                            "a dealer's quarterly target, as a share of its expected quarterly volume"),
    "dealer_size_sigma": (0.8, "ASSUMPTION", "dealer sizes are lognormal; the spread of log size"),
    "order_lead_days": ((7, 150), "ASSUMPTION",
                        "days from signed order to registration, uniform; inside B's 180-day limit"),
    # leak rates, each a share of its own pool. No public benchmark exists (X1 research), so part 10 sweeps them.
    "rate_cross_system_duplicate": (0.10, "ASSUMPTION",
                                    "of group-programme claims by a dealer on both systems: claimed again in the other"),
    "rate_vin_typo": (0.005, "ASSUMPTION", "of all claims: filed again under a mistyped VIN"),
    "rate_pre_vin_claim": (0.02, "ASSUMPTION",
                           "of B retail, fleet and conquest claims: a phantom order-only claim beside it"),
    "rate_illegal_stack": (0.02, "ASSUMPTION", "of fleet claims: a retail claim added on the same car"),
    "rate_late_claim": (0.01, "ASSUMPTION", "of all claims: filed after the deadline"),
    "rate_quarter_end_gaming": (0.30, "ASSUMPTION",
                                "of A dealer-quarters that could reach target by pulling cars forward"),
    "gaming_max_shortfall": (3, "ASSUMPTION", "the most cars a dealer pulls forward"),
    "gaming_pull_days": (15, "ASSUMPTION", "a pulled car was due in the first days of the next quarter"),
    "stack_other_system_share": (0.30, "ASSUMPTION",
                                 "of illegal stacks by a dealer on both systems: filed in the other system"),
    "typo_two_chars_share": (0.20, "ASSUMPTION", "of VIN typos: two characters wrong rather than one"),
    "typo_mix": ((0.5, 0.3, 0.2), "ASSUMPTION", "look-alike swap, random character, adjacent transposition"),
    # legitimate look-alikes, each a share of its own pool
    "rate_legit_reversal": (0.01, "ASSUMPTION", "of claims: cancelled by a credit note and filed again"),
    "rate_legit_vin_blank": (0.10, "ASSUMPTION", "of B claims: VIN left empty though the order became a car"),
    "rate_legit_key_typo": (0.01, "ASSUMPTION",
                            "of claims: the key mistyped on entry (the VIN, or the order number of a B claim with "
                            "no VIN) on a claim that is not a duplicate"),
    # stress test (part 6b): noise in what detectors read, each a share of its own pool; the stress level multiplies
    "stress_fleet_batches": (True, "ASSUMPTION",
                             "fleet cars of one make, model, trim and registration day go through one dealer"),
    "stress_invoice_price": (0.30, "ASSUMPTION",
                             "of cars: programme amounts computed on the invoice price, catalogue x U(0.95, 1.10)"),
    "stress_date_offset": (0.10, "ASSUMPTION", "of claims: the sale-event date keyed 1-7 days off"),
    "stress_date_swap": (0.005, "ASSUMPTION", "of claims: day and month swapped on entry"),
    "stress_dealer_code": (0.02, "ASSUMPTION", "of claims: filed under another dealer's code in the same system"),
    "stress_heavy_typo": (0.30, "ASSUMPTION", "of mistyped keys: one or two more characters wrong"),
    # the register trade-in source (added after the blind red team)
    "tradein_private_share": (0.60, "ASSUMPTION",
                              "of loyal private buyers: trade in a car of the same make; the rest trade in nothing"),
    # the register keeper source (part 7b): each car's current-keeper date, anchored on the real RDW register
    "keeper_quick_base": (register_value("selfreg_group_base") / 100, "MEASURED",
                          "selfreg_group_base: legitimate keeper changes 1-30 days after registration, ordinary days"),
    "keeper_quick_qend_lift": (register_value("selfreg_group_qend_lift") / 100, "MEASURED",
                               "selfreg_group_qend_lift: the real quarter-end lift in quick changes, all of it "
                               "treated here as legitimate, the hard case for a detector"),
    "keeper_hidden_prompt": (register_value("keeper_early_change_3m_group") / 100, "MEASURED",
                             "keeper_early_change_3m_group: a later change hides an early one, register read within "
                             "a quarter (an upper bound)"),
    "keeper_hidden_late": (register_value("keeper_hidden_2021_group") / 100, "MEASURED",
                           "keeper_hidden_2021_group: a later change hides an early one, register read years later"),
    "keeper_quick_days": (30, "ASSUMPTION", "a keeper change within this many days of registration is quick; the "
                                            "same cut as the real-data measurement"),
    # the finance joint venture's contract table (part 9): across the JV boundary, so linked privately
    "finance_fleet_share": (1.0, "ASSUMPTION", "of fleet sales: leased or financed through the group's captive JV "
                                              "(in reality a share; independent lessors would need their own source)"),
    "finance_private_share": (0.30, "ASSUMPTION", "of private and conquest sales: financed through the captive JV"),
    "finance_vin_typo": (0.03, "ASSUMPTION", "of JV contracts: the VIN keyed with one or two characters wrong"),
    "finance_start_days": (30, "ASSUMPTION", "a contract starts up to this many days either side of registration"),
    # after round 3 (`sources.py`): the legitimate events behind the four sources that close its gaps
    "transfer_legit_share": (0.03, "ASSUMPTION", "of cars: sourced from another dealer's stock by a documented dealer "
                                                 "trade before registration"),
    "order_customer_change_share": (0.01, "ASSUMPTION", "of B orders: the customer changes before delivery (a company "
                                                        "car reassigned, a partner taking over the contract)"),
    "conquest_min_holding_days": (180, "ASSUMPTION",
                                  "a conquest bonus needs the trade-in in the buyer's name at least this long. Real "
                                  "terms run from 3 to 12 months: France's prime a la conversion 1 year (Citroen's page, "
                                  "opened: https://www.reprise.citroen.fr/lp/prime-conversion), Opel's conquest bonus 6 "
                                  "months (~, a dealer portal)"),
    "tradein_holding_days": ((30, 3650), "ASSUMPTION", "days a buyer held the trade-in, uniform; a conquest buyer at "
                                                       "least conquest_min_holding_days"),
}
# Look-alike characters people mistype (ASSUMPTION). I and O may not appear in a VIN, so a swap into them gives a
# VIN a format check can reject; the other swaps need matching to catch.
CONFUSABLE = {"0": "OD", "1": "I7", "2": "Z", "5": "S", "6": "G", "8": "B", "B": "8", "D": "0", "G": "6",
              "S": "5", "Z": "2", "U": "V", "V": "U", "M": "N", "N": "M"}

# ---------- sources the dealer does not control (added after the blind red team, 25 September) ----------
# The red team showed that a dealer who falsifies the vehicle record itself passes every rule. So two checks now read
# sources outside the dealer's reach:
#   - volume targets are published by the OEM before the quarter (x1_targets.parquet). Detectors never recompute a
#     target from the record.
#   - a conquest claim needs a trade-in whose make, per the national register (make by plate is public in the RDW
#     register), is not a group brand (x1_register_tradeins.parquet). Buyer type reported by the dealer is not enough.
# After round 3 the rulebook states three things its first version left implicit, each checked against a source the
# dealer does not control (`sources.py` writes them):
#   - a conquest trade-in must have been in the buyer's name for `conquest_min_holding_days` before the sale event
#     (the register's keeper date for the trade-in, read by plate before it passes to the dealer);
#   - volume credit in A goes to the dealer that held the car when it was registered: a documented transfer after
#     registration does not move it. In B it goes to the dealer that signed the order;
#   - a car registered in the dealer's own name, and a B order whose customer changed, are sales when the real
#     customer takes them; a dealer-quarter that meets its target only otherwise is held for review.
GROUP_MAKES = set(SYSTEM_OF_BRAND)
# common makes on Dutch roads outside the group (ASSUMPTION: the list is ours, the makes are real)
NONGROUP_MAKES = ["volkswagen", "toyota", "kia", "renault", "hyundai", "skoda", "bmw", "volvo", "ford",
                  "mercedes benz"]

# ---------- the sale event each system counts: the heart of "different definitions of an eligible sale" ----------
# CASE: the definitions differ. Which way they differ is ours (ASSUMPTION).
#   A counts a sale when the car is registered. B counts it when the order is signed, and the car must then be
#   registered within `b_registration_within_days`. One car ordered in December and registered in January is a Q4
#   sale in B and a Q1 sale in A. That is legitimate, and naive cross-system checks trip over it.
SALE_EVENT = {"A": "registration_date", "B": "order_date"}
# claim deadline in days (ASSUMPTION); `claim_window` below says what it counts from
CLAIM_DEADLINE_DAYS = {"A": 60, "B": 90}


def claim_window(system, family, order_date, registration_date, quarter_end):
    """The dates a claim may be filed between (ASSUMPTION). Works on scalars or Series.
    Opens:  A at registration (A needs the VIN); B at the signed order (B books before registration, like the
            Ecobonus); a volume bonus in either system when the quarter closes and the target is known.
    Closes: the deadline, counted from registration, or for a volume bonus from the quarter's close."""
    days = pd.Timedelta(days=CLAIM_DEADLINE_DAYS[system])
    if family == "volume":
        return quarter_end, quarter_end + days
    return (registration_date if system == "A" else order_date), registration_date + days

# ---------- the two schemas ----------
# canonical field: (system A column, system B column). Names, amounts and dates differ; the meaning does not.
SCHEMA = {
    "claim_id":   ("claim_ref",         "id_pratica"),
    "dealer":     ("dealer_code",       "codice_dealer"),    # a dealer on both systems has one code in each
    "vin":        ("vin",               "telaio"),           # full 17 characters in both; B may leave it empty
    "order_no":   ("order_ref",         "numero_ordine"),    # optional in A, required in B
    "programme":  ("programme_code",    "codice_campagna"),
    "event_date": ("registration_date", "data_contratto"),   # the SALE_EVENT of each system
    "claim_date": ("claim_date",        "data_richiesta"),
    "amount_net": ("amount_net_eur",    "importo_lordo_eur"),  # A stores net of VAT, B stores gross
}
REQUIRED = {"A": {"claim_id", "dealer", "vin", "programme", "event_date", "claim_date", "amount_net"},
            "B": {"claim_id", "dealer", "order_no", "programme", "event_date", "claim_date", "amount_net"}}

# ---------- programme catalogues (all ASSUMPTION: no real catalogue is public) ----------
# family  the canonical kind of programme; codes differ between systems
# buyer   who qualifies: private, fleet, conquest (a private buyer from a non-group brand), any
# basis   pct_list = share of list price; flat = euros per car. Amounts are net of VAT in the spec; system B
#         stores them gross.
# years   calendar years the programme runs; windows are calendar quarters
PROGRAMMES = pd.DataFrame([
    ("A", "RC-CLI",  "retail",   "private",  "pct_list", 0.025, (2021, 2022)),
    ("A", "FL-SOC",  "fleet",    "fleet",    "pct_list", 0.060, (2021, 2022)),
    ("A", "VQ-TRIM", "volume",   "any",      "flat",     300,   (2021, 2022)),
    ("A", "GRP-CQ",  "conquest", "conquest", "flat",     500,   (2022,)),
    ("B", "BCL",     "retail",   "private",  "flat",     650,   (2021, 2022)),
    ("B", "FLOTTE",  "fleet",    "fleet",    "pct_list", 0.050, (2021, 2022)),
    ("B", "TGT-Q",   "volume",   "any",      "pct_list", 0.015, (2021, 2022)),
    ("B", "CQ22",    "conquest", "conquest", "flat",     500,   (2022,)),
], columns=["system", "code", "family", "buyer", "basis", "amount", "years"])
BUYERS_OF = {"private": {"private", "conquest"}, "fleet": {"fleet"}, "conquest": {"conquest"},
             "any": {"private", "conquest", "fleet"}}
# After the merger one group-wide programme runs in both systems, under a different code in each.
# CASE: "overlapping incentive programs operate across multiple systems". A dealer on both systems can claim one
# car in both: the cross-system duplicate.
CROSSWALK = [("A", "GRP-CQ", "B", "CQ22")]

# ---------- stacking (ASSUMPTION) ----------
# Per car, group-wide, across both systems: at most one programme per family, and these families exclude each
# other. Volume bonuses stack with anything.
EXCLUDES = {("fleet", "retail"), ("fleet", "conquest")}

# ---------- legitimate look-alikes: must NOT be flagged ----------
LEGIT = {
    "allowed_stack":    "retail or conquest plus the volume bonus on one car",
    "reversal_reclaim": "a claim cancelled by a credit note and filed again with the corrected amount",
    "cross_quarter":    "ordered in one quarter and registered in the next: B and A count different quarters",
    "vin_blank":        "a B claim with no VIN whose order did become a registered car",
    "booked_early":     "a B claim booked before its car was registered (the Ecobonus mechanism)",
    "key_typo":         "a claim that is not a duplicate, entered with a mistyped VIN or order number",
}

# ---------- the six leaks (definitions; rates are set in part 4) ----------
LEAKS = {
    "cross_system_duplicate": "one car's group programme claimed in both systems by a dealer on both",
    "vin_typo":               "a claim whose VIN has one or two characters wrong, paid as if a separate car",
    "pre_vin_claim":          "an order-only claim in B for an order that never became a registered car in time",
    "illegal_stack":          "a pair of excluded families on one car, possibly split across the two systems",
    "late_claim":             "filed after the system's claim deadline and paid anyway",
    "quarter_end_gaming":     "a registration pulled into the last days of a quarter to reach a volume target",
}


def to_system(claim, system):
    """One canonical claim (dict) as a row of the given system: its column names, amount basis and event date."""
    i = 0 if system == "A" else 1
    row = {SCHEMA[k][i]: v for k, v in claim.items()}
    if system == "B":
        row[SCHEMA["amount_net"][1]] = round(claim["amount_net"] * (1 + SETTINGS["vat_nl"][0]), 2)
    return row


def from_system(row, system):
    """The inverse of `to_system`."""
    i = 0 if system == "A" else 1
    claim = {k: row[cols[i]] for k, cols in SCHEMA.items() if cols[i] in row}
    if system == "B":
        claim["amount_net"] = round(row[SCHEMA["amount_net"][1]] / (1 + SETTINGS["vat_nl"][0]), 2)
    return claim


def system_table(claims, system):
    """`to_system` for a whole DataFrame of canonical claims."""
    i = 0 if system == "A" else 1
    t = claims[list(SCHEMA)].rename(columns={k: v[i] for k, v in SCHEMA.items()})
    if system == "B":
        col = SCHEMA["amount_net"][1]
        t[col] = (t[col] * (1 + SETTINGS["vat_nl"][0])).round(2)
    return t


def canonical_table(t, system):
    """The inverse of `system_table`: a system's claims table back in canonical columns, amounts net."""
    i = 0 if system == "A" else 1
    c = t.rename(columns={v[i]: k for k, v in SCHEMA.items()})
    if system == "B":
        c["amount_net"] = (c["amount_net"] / (1 + SETTINGS["vat_nl"][0])).round(2)
    c.insert(1, "system", system)
    return c


def check():
    cars = pd.read_parquet(CARS, columns=["make"])
    system = cars["make"].map(SYSTEM_OF_BRAND)
    assert system.notna().all(), f"no system for {set(cars.loc[system.isna(), 'make'])}"
    print("cars per system:", system.value_counts().sort_index().to_dict())

    assert all(tag in {"CASE", "SOURCED", "MEASURED", "ASSUMPTION"} for _, tag, _ in SETTINGS.values())
    assert all(note.startswith("https://") for _, tag, note in SETTINGS.values() if tag == "SOURCED")

    p = PROGRAMMES
    assert not p.duplicated(["system", "code"]).any()
    for s in "AB":  # one programme per family in each system, so a family names one programme per system
        assert not p[p["system"].eq(s)].duplicated("family").any()
    fams = set(p["family"])
    assert all(a in fams and b in fams for a, b in EXCLUDES) and "volume" not in {f for e in EXCLUDES for f in e}
    for sa, ca, sb, cb in CROSSWALK:
        fa = p.loc[p["system"].eq(sa) & p["code"].eq(ca), "family"]
        fb = p.loc[p["system"].eq(sb) & p["code"].eq(cb), "family"]
        assert len(fa) == len(fb) == 1 and fa.iloc[0] == fb.iloc[0], (ca, cb)
    assert set(SALE_EVENT) == set(CLAIM_DEADLINE_DAYS) == set(REQUIRED) == {"A", "B"}
    assert all(r <= set(SCHEMA) for r in REQUIRED.values())

    claim = {"claim_id": "c1", "dealer": "d1", "vin": "VF3023U05MM333028", "order_no": "o1",
             "programme": "GRP-CQ", "event_date": pd.Timestamp("2022-03-30"),
             "claim_date": pd.Timestamp("2022-04-15"), "amount_net": 500.0}
    for s in "AB":
        assert from_system(to_system(claim, s), s) == claim, s
    print("gross amount of a EUR 500 net claim in system B:", to_system(claim, "B")["importo_lordo_eur"])
    print(f"programmes: {len(p)} ({(p['system'] == 'A').sum()} in A, {(p['system'] == 'B').sum()} in B), "
          f"{len(CROSSWALK)} run in both; {len(EXCLUDES)} exclusions; {len(LEGIT)} legitimate look-alikes; "
          f"{len(LEAKS)} leaks")
    tags = pd.Series([t for _, t, _ in SETTINGS.values()]).value_counts().to_dict()
    print("settings by provenance:", tags, "| every programme amount is ASSUMPTION")
    print("all spec checks pass")


if __name__ == "__main__":
    check()
