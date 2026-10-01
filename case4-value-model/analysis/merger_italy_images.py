"""X2 part 7, step 1: find and download Dataforce's monthly Italian "last 3 days" charts and tables.

Dataforce Italy publishes a press release on each month's car market. Most carry an image of the share of each
brand's registrations made in the month's last 3 working days: a table of the brands making 80% of the market up to
2020 (passenger cars and light vans together), and from 2021 a chart of passenger cars ("Winners & Losers"), in
some months a table split by sales channel, dealer and maker self-registrations included. The images are read
(transcribed) in step 2; this finds them.

Source: Dataforce Italia press releases, https://www.dataforce.de/it/tutte-le-notizie/ (the data are Dataforce's
processing of Ministry of Transport registrations). The images are copyrighted; they are kept in data/ (private) and
never published. Only the figures read from them are used.
Usage: .venv/bin/python analysis/merger_italy_images.py
"""
import json
import re
from pathlib import Path

import requests

HERE = Path(__file__).parent
OUT = HERE.parent / "data" / "x2_italy_png"
INDEX = HERE.parent / "data" / "x2_italy_images.json"
NEWS = "https://www.dataforce.de/it/tutte-le-notizie/"
HEADERS = {"User-Agent": "Mozilla/5.0 (research; case competition)"}
MONTHS = {m: i + 1 for i, m in enumerate(["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
                                          "agosto", "settembre", "ottobre", "novembre", "dicembre"])}
# the passenger-car last-3-days image, in the names Dataforce has used; light-van (LCV) versions are excluded
WANTED = re.compile(r"(wl-3gg-pc|3gg-pc|pc-3gg|wl-pc|ultimi-3-giorni)", re.I)
SIZED = re.compile(r"-\d+x\d+\.(png|jpe?g)$", re.I)


def releases():
    """Every monthly market release in Dataforce Italy's news list."""
    urls, page = set(), 1
    while True:
        r = requests.get(NEWS + (f"page/{page}/" if page > 1 else ""), headers=HEADERS, timeout=60)
        if r.status_code != 200:
            return sorted(urls)
        found = set(re.findall(r'href="(https://www\.dataforce\.de/it/tutte-le-notizie/comunicato-stampa-dataforce-'
                               r'mercato-(?:auto|autovetture)[^"]+)"', r.text))
        if not found and page > 3:
            return sorted(urls)
        urls |= found
        page += 1


def month_of(url):
    """The release's month from its address, e.g. ...-agosto-2021/ or ...-maggio2022/."""
    m = re.search(r"(" + "|".join(MONTHS) + r")-?(20\d\d)/?$", url)
    return f"{m.group(2)}-{MONTHS[m.group(1)]:02d}" if m else None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    for url in releases():
        month = month_of(url)
        if month is None or "veicoli-commerciali-leggeri" in url and "autovetture" not in url:
            continue
        html = requests.get(url, headers=HEADERS, timeout=60).text
        imgs = sorted(set(re.findall(r'(https://www\.dataforce\.de/wp-content/uploads/[^"\s]+\.(?:png|jpe?g))',
                                     html, re.I)))
        imgs = [i for i in imgs if WANTED.search(i) and not SIZED.search(i) and "lcv" not in i.lower()]
        if not imgs:
            continue
        files = []
        for n, img in enumerate(imgs):
            name = f"{month}_{n}{Path(img).suffix.lower()}"
            if not (OUT / name).exists():
                (OUT / name).write_bytes(requests.get(img, headers=HEADERS, timeout=60).content)
            files.append({"file": name, "image": img})
        index[month] = {"release": url, "images": files}
    INDEX.write_text(json.dumps(dict(sorted(index.items())), indent=1))
    print(f"{len(index)} months with a last-3-days image, {sum(len(v['images']) for v in index.values())} images, "
          f"{min(index)} to {max(index)}")


if __name__ == "__main__":
    main()
