"""One module per data source.

Each module defines:
- INFO: dict with "country" (ISO code, or None if the data has a country column),
  "price_type" ("asking", "sale" or "auction"), "license" and "url"
- download(raw_dir): fetch the raw files into raw_dir (a Path under data/raw/)
- load(raw_dir): return a DataFrame using the shared column names in build_unified.py

Modules are discovered automatically, so adding a source means adding one file.
"""
import importlib
import pkgutil
from pathlib import Path

SOURCES = {
    m.name: importlib.import_module(f"{__name__}.{m.name}")
    for m in sorted(pkgutil.iter_modules([str(Path(__file__).parent)]), key=lambda m: m.name)
    if m.name != "common"
}
