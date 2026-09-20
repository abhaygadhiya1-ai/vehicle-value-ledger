"""Helpers shared by the source loaders."""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import requests

# some hosts (Harvard Dataverse, the ONS) reject the default requests user agent
HEADERS = {"User-Agent": "case4-value-model"}

HP_TO_KW = 0.7355     # metric horsepower (PS, KM, hk, ch, CV)
BHP_TO_KW = 0.7457    # imperial brake horsepower
MILES_TO_KM = 1.609344


def leading_number(s):
    """'1 598 cm3' -> 1598, '150 KM' -> 150, '6.8L' -> 6.8."""
    txt = s.astype("string").str.extract(r"^\s*(\d[\d\s]*(?:\.\d+)?)")[0]
    return pd.to_numeric(txt.str.replace(r"\s", "", regex=True), errors="coerce")


def kaggle_download(slug, raw_dir):
    """Download and unzip a Kaggle dataset (needs the Kaggle CLI signed in)."""
    kaggle = Path(sys.executable).parent / "kaggle"
    subprocess.run([str(kaggle), "datasets", "download", slug, "-p", str(raw_dir), "--unzip", "-q"],
                   check=True)


def mendeley_files(dataset):
    """List the files of a Mendeley Data record's latest version as (filename, download url)."""
    meta = requests.get(f"https://data.mendeley.com/public-api/datasets/{dataset}", timeout=120).json()
    files = requests.get(f"https://data.mendeley.com/public-api/datasets/{dataset}/files",
                         params={"folder_id": "root", "version": meta["version"]}, timeout=120).json()
    return [(f["filename"], f["content_details"]["download_url"]) for f in files]


def http_download(url, path, params=None):
    """Stream a file from an open URL to path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, params=params, headers=HEADERS, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
