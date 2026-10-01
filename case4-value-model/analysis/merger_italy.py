"""X2 part 7, step 2: Italy, from the two months Dataforce split by sales channel (August and September 2021).

For each brand, Dataforce's table gives the month's passenger-car registrations by channel (private, fleet, long-term
rental, short-term rental, dealers and makers) and the same for the month's last 3 working days. The dealer-and-maker
channel ("Concessionarie e Case Auto") is registrations in the dealer's or maker's own name: self-registrations,
directly, where the Dutch work (`merger_fingerprint.py`) could only use a quick keeper change as a proxy.

Input: `data/x2_italy_channels.csv`, transcribed by hand from `data/x2_italy_png/2021-08_0.png` and `2021-09_0.png`
(private: the images are Dataforce's, copyrighted). This script checks the transcription before using it: every
row's channels add to its total, each column adds to the table's own total row, and the two printed percentages
match the counts. August is also checked against the press release's own text (`x2_dataforce_italy_transcription`).

Usage: .venv/bin/python analysis/merger_italy.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from build_unified import STELLANTIS, md_table  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
OUT = HERE / "merger_italy_report.md"
CH = ["private", "fleet", "long_rent", "short_rent", "dealer_maker"]
L3, M = [f"l3_{c}" for c in CH], [f"m_{c}" for c in CH]
NAMES = {"month": "month", "who": "brands"}


def load():
    d = pd.read_csv(DATA / "x2_italy_channels.csv")
    rows = d[~d["brand"].isin(["TOTAL"])]
    assert (d[L3].sum(axis=1) == d["l3_total"]).all() and (d[M].sum(axis=1) == d["m_total"]).all()
    assert ((100 * d["l3_total"] / d["m_total"] - d["l3_share_of_month_pct"]).abs() <= 0.051).all()
    assert ((100 * d["l3_dealer_maker"] / d["l3_total"] - d["l3_dealer_maker_pct"]).abs() <= 0.051).all()
    for month, g in d.groupby("month"):
        total = g[g["brand"].eq("TOTAL")].iloc[0]
        body = rows[rows["month"].eq(month)]
        assert all(body[c].sum() == total[c] for c in L3 + M + ["l3_total", "m_total"]), month
    # the release's own text names the extremes; our reading of the image must agree
    text = {r["month"]: r for r in json.loads((DATA / "x2_dataforce_italy_transcription.json").read_text())}
    checked = 0
    for month, r in text.items():
        if month not in set(d["month"]):
            continue
        g = d[d["month"].eq(month)]
        ours = g.set_index(g["brand"].str.lower().str.replace("ë", "e"))["l3_share_of_month_pct"]
        assert abs(ours["total"] - r["market_pct"]) < 0.051, month
        for brand, pct in r["highest"] + r["lowest"]:
            assert abs(ours[brand.lower().replace("ë", "e")] - pct) < 0.051, (month, brand)
            checked += 1
    return d, checked


def rates(g):
    s = g[L3 + M + ["l3_total", "m_total"]].sum()
    return pd.Series({
        "cars in the month": int(s["m_total"]),
        "share in the last 3 days (%)": 100 * s["l3_total"] / s["m_total"],
        "self-registered, share of the month (%)": 100 * s["m_dealer_maker"] / s["m_total"],
        "self-registered, share of the last 3 days (%)": 100 * s["l3_dealer_maker"] / s["l3_total"],
        "self-registrations made in the last 3 days (%)": 100 * s["l3_dealer_maker"] / s["m_dealer_maker"],
        "share in the last 3 days, self-registrations left out (%)":
            100 * (s["l3_total"] - s["l3_dealer_maker"]) / (s["m_total"] - s["m_dealer_maker"]),
    })


def main():
    d, checked = load()
    brands = d[~d["brand"].isin(["TOTAL", "Other"])].copy()
    brands["group"] = brands["brand"].str.lower().isin(STELLANTIS)
    brands["who"] = brands["group"].map({True: "group brands", False: "other named brands"})
    pooled = brands.groupby(["month", "who"]).apply(rates, include_groups=False).reset_index()
    market = d[d["brand"].eq("TOTAL")].groupby("month").apply(rates, include_groups=False).reset_index()
    market["who"] = "whole market"
    both = pd.concat([pooled, market], ignore_index=True).sort_values(["month", "who"], ignore_index=True)
    both2 = brands.groupby("who").apply(rates, include_groups=False).reset_index()

    per = brands.assign(**{
        "share in the last 3 days (%)": brands["l3_share_of_month_pct"],
        "self-registered, share of the month (%)": 100 * brands["m_dealer_maker"] / brands["m_total"],
    })
    per = per.pivot_table(index=["brand", "group"], columns="month",
                          values=["share in the last 3 days (%)", "self-registered, share of the month (%)"])
    per.columns = [f"{a[:-4]}, {b} (%)" for a, b in per.columns]
    per = per.reset_index().sort_values(per.columns[-2], ascending=False)
    rank = brands.sort_values(["month", "l3_share_of_month_pct"], ascending=[True, False])
    rank["rank"] = rank.groupby("month").cumcount() + 1
    top = rank.groupby("month").apply(lambda g: g.head(10)["group"].sum(), include_groups=False)
    n_brands = rank.groupby("month").size()
    n_group = brands.groupby("month")["group"].sum()

    sums = brands.groupby("who")[L3 + M].sum()
    chan = pd.DataFrame({f"{w}: {k}": [100 * sums.loc[w, f"{p}{c}"] / (sums.loc[w, f"m_{c}"] if p == "l3_" else
                                                                         sums.loc[w, M].sum()) for c in CH]
                         for w in sums.index for k, p in (("share of the month's cars (%)", "m_"),
                                                          ("share in the last 3 days (%)", "l3_"))}, index=CH)
    chan = chan.rename_axis("channel").reset_index()
    gap = chan.set_index("channel")
    lr = gap.loc["long_rent"]
    lr_gm, lr_om = lr["group brands: share of the month's cars (%)"], lr["other named brands: share of the month's cars (%)"]
    fmt = lambda t: t.round(1).astype({c: int for c in t.columns if c == "cars in the month"})  # noqa: E731
    g2, o2 = both2.set_index("who").loc["group brands"], both2.set_index("who").loc["other named brands"]
    lines = [
        "# X2 part 7: Italy, the months split by sales channel", "",
        "Generated by `analysis/merger_italy.py` from `data/x2_italy_channels.csv`, transcribed from Dataforce Italia's "
        "press-release tables for August and September 2021 (Dataforce's processing of Ministry of Transport "
        "registrations; the images are copyrighted and stay private). Passenger cars only.", "",
        f"**Transcription checked:** every row's channels add to its total, every column adds to the table's own total "
        f"row, both printed percentages match the counts, and {checked} brand figures plus the market figure for "
        "August match the press release's own text.", "",
        "**Group brands** are the group's makes as `build_unified.STELLANTIS` lists them: here Fiat, Jeep, Peugeot, "
        "Opel, Citroën, Lancia, Alfa Romeo and DS. Abarth and Maserati sit in Dataforce's \"Other\", which is left out. "
        "\"Self-registered\" is Dataforce's channel \"Concessionarie e Case Auto\": registrations in a dealer's or "
        "maker's own name.", "",
        "## Group brands against the rest, both months pooled", "",
        md_table(fmt(both2.rename(columns=NAMES))), "",
        "## By month", "", md_table(fmt(both.rename(columns=NAMES))), "",
        "## By channel, both months pooled", "",
        "Each channel's share of the month's cars, and the share of that channel's month registered in the last 3 "
        "days.", "", md_table(fmt(chan)), "",
        "## By brand", "", md_table(fmt(per)), "",
        "## What it shows", "",
        f"- **The group's brands register more of their month at its very end, as in the Netherlands.** Pooled over "
        f"both months, {g2['share in the last 3 days (%)']:.1f}% of the group brands' cars were registered in the "
        f"month's last 3 working days, against {o2['share in the last 3 days (%)']:.1f}% for the other named brands. "
        + "".join(f"In {m}, {top[m]} of the top 10 brands by that share were group brands ({n_group[m]} of the "
                  f"{n_brands[m]} named brands are). " for m in top.index),
        f"- **Italy shows the channel the Dutch data could only infer.** The group brands registered "
        f"{g2['self-registered, share of the month (%)']:.1f}% of their month in their dealers' or makers' own name, "
        f"against {o2['self-registered, share of the month (%)']:.1f}% for the others; in the last 3 days the share "
        f"was {g2['self-registered, share of the last 3 days (%)']:.1f}% against "
        f"{o2['self-registered, share of the last 3 days (%)']:.1f}%.",
        f"- **Self-registration is not the whole story.** With self-registrations left out, the group brands still "
        f"registered {g2['share in the last 3 days, self-registrations left out (%)']:.1f}% of their other cars in the "
        f"last 3 days, against {o2['share in the last 3 days, self-registrations left out (%)']:.1f}%. Every channel is "
        f"more month-end-heavy for the group's brands; outside self-registration the widest gap is long-term rental "
        f"({lr['group brands: share in the last 3 days (%)']:.1f}% of its month in the last 3 days, against "
        f"{lr['other named brands: share in the last 3 days (%)']:.1f}%), a channel that is also a larger part of the "
        f"group's month ({lr_gm:.1f}% against {lr_om:.1f}%).", "",
        "## Limits", "",
        "- **Two months, both after the merger closed** (16 January 2021). This is a level, like X2's Dutch claim, "
        "not a before-and-after, and it says nothing about the merger's effect.",
        "- **Not the same measure as the Dutch one.** Italy counts the last 3 *working* days of a month; the Dutch "
        "panel the last 3 calendar days. Compare the direction, not the numbers.",
        "- **August is a holiday month in Italy** and small; September is the more ordinary of the two.",
        "- **Self-registration is a channel, not a verdict.** Dealer and maker registrations include demonstrators "
        "and cars pre-registered to hit a target; the table cannot tell them apart.",
        "- **Brand, not group, decides.** Other brands (DR, Nissan, Toyota) also register heavily at month end in "
        "one month or the other; the claim is the group's pooled level, not that every group brand leads.", "",
    ]
    OUT.write_text("\n".join(lines))
    print(fmt(both2).to_string(index=False))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
