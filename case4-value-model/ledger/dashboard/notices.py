"""The dashboard's third-party notices: every package the built page can contain, with its own licence text.

`index.html` is one file with its JavaScript and fonts inlined, so it carries other people's code. This writes
`THIRD_PARTY_NOTICES.txt` beside it from the packages themselves: every production dependency `npm ls` lists in
`app/` (a superset of what the bundle holds), each package's own licence and notice files verbatim, plus Vite's
licence (the build inlines its module-preload polyfill) and IBM Plex Sans's (the fonts). Nothing is downloaded.
It stops if a package ships no licence file, so a notice is never made up.

Re-run after any change to `app/package.json` (from case4-value-model/): .venv/bin/python ledger/dashboard/notices.py
"""
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
APP = HERE / "app"
FILES = re.compile(r"^(licen[cs]e|copying|notice)([.-].*)?$", re.I)
# A package that declares its licence but ships no file: the licence file from its own repository, read 1 October 2026.
UPSTREAM = {
    "react-remove-scroll-bar": ("https://github.com/theKashey/react-remove-scroll-bar/blob/master/LICENSE", """\
MIT License

Copyright (c) 2025 Anton Korzunov <thekashey@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""),
}


def packages():
    out = subprocess.run(["npm", "ls", "--omit=dev", "--all", "--parseable"], cwd=APP, check=True,
                         capture_output=True, text=True).stdout.splitlines()
    seen = {}
    for d in map(Path, out[1:]):  # the first line is the app itself
        meta = json.loads((d / "package.json").read_text())
        seen.setdefault((meta["name"], meta["version"]), (d, meta.get("license")))
    return [(name, ver, d, lic) for (name, ver), (d, lic) in sorted(seen.items())]


def section(title, lic, files):
    body = "\n\n".join(f.read_text(encoding="utf-8", errors="replace").strip() for f in files)
    return f"{'=' * 78}\n{title}\nLicence: {lic}\n{'=' * 78}\n\n{body}\n"


def main():
    parts, missing, pkgs = [], [], packages()
    for name, ver, d, lic in pkgs:
        files = sorted(f for f in d.iterdir() if f.is_file() and FILES.match(f.name))
        if files:
            parts.append(section(f"{name} {ver}", lic, files))
        elif name in UPSTREAM:
            url, text = UPSTREAM[name]
            parts.append(f"{'=' * 78}\n{name} {ver}\nLicence: {lic} (the package ships no licence file; this is its "
                         f"repository's, {url})\n{'=' * 78}\n\n{text}\n")
        else:
            missing.append(name)
    if missing:
        raise SystemExit(f"no licence file shipped by: {', '.join(missing)}")
    vite = APP / "node_modules" / "vite"
    vite_ver = json.loads((vite / "package.json").read_text())["version"]
    vite_mit = (vite / "LICENSE.md").read_text(encoding="utf-8").split("# Licenses of bundled dependencies")[0]
    parts.append(f"{'=' * 78}\nvite {vite_ver} (its module-preload polyfill, inlined by the build)\nLicence: MIT\n"
                 f"{'=' * 78}\n\n{vite_mit.strip()}\n")
    parts.append(section("IBM Plex Sans (fonts/, inlined in the page)", "OFL-1.1", [HERE / "fonts" / "OFL.txt"]))
    head = ("Third-party notices for the dashboard (index.html). Our own code is under the MIT licence in the\n"
            "repository's LICENSE. The page also carries the software and fonts below, each under its own licence,\n"
            "reproduced here from the package itself. The page's icons are listed separately in LICENSE-carbon.txt and\n"
            "LICENSE-mdi.txt. Written by notices.py; re-run it rather than editing this file.\n\n")
    (HERE / "THIRD_PARTY_NOTICES.txt").write_text(head + "\n".join(parts), encoding="utf-8")
    print(f"{len(parts)} sections, {len(pkgs)} npm packages")


if __name__ == "__main__":
    main()
