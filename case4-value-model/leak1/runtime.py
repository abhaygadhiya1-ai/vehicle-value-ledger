"""X1 part 10c: runtime and determinism, on this machine.

Kept apart from the scorecard because timings vary by machine and by run, while the scorecard must be byte-identical
across runs. It runs our world's pipeline (layers 1-3, today's code) through the scorecard's own worker REPEATS times,
each in a fresh process. It reports each layer's in-process seconds (Python start-up, imports and data loading
excluded), and checks that every repeat gives identical flags at every stage.

These are engineering facts about the tool, not about the group (skeptic A14).
Output: leak1/x1_runtime_report.md
Usage: .venv/bin/python leak1/runtime.py
"""
import datetime
import platform
import statistics
import subprocess
import tempfile

import duckdb
import pandas as pd
import splink

from scorecard import HERE, RUNS, STAGES, run

REPEATS = 3
REPORT = HERE / "x1_runtime_report.md"
LAYERS = ["layer 1", "layer 2", "layer 3"]


def sysctl(key):
    return subprocess.run(["sysctl", "-n", key], capture_output=True, text=True).stdout.strip()


def main():
    name, world, _ = RUNS[0]
    with tempfile.TemporaryDirectory() as tmp:
        reps = [run(f"{name} {i}", world, HERE, tmp)[0] for i in range(REPEATS)]
    hashes = {tuple(r["flags_sha"][s] for s in STAGES) for r in reps}
    assert len(hashes) == 1, f"repeats disagree: {hashes}"
    seconds = {layer: [r["seconds"][layer] for r in reps] for layer in LAYERS}
    seconds["total"] = [sum(r["seconds"][layer] for layer in LAYERS) for r in reps]
    rows = "\n".join(f"| {k} | {statistics.median(v):.1f} | {min(v):.1f} | {max(v):.1f} |" for k, v in seconds.items())
    claims = reps[0]["stages"][STAGES[0]]["headline"]["claims"]

    REPORT.write_text(f"""# X1 runtime and determinism

**Machine-dependent.** Measured on {datetime.date.today().isoformat()} on an {sysctl("machdep.cpu.brand_string")}
with {sysctl("hw.ncpu")} cores and {int(sysctl("hw.memsize")) / 2**30:.0f} GB of memory, macOS
{platform.mac_ver()[0]}; Python {platform.python_version()}, pandas {pd.__version__}, Splink {splink.__version__},
DuckDB {duckdb.__version__}. On another machine the seconds change; the determinism check should not.

Written by `leak1/runtime.py`; re-run it rather than editing this file.

## Runtime

Our world ({claims:,} claims), today's code, {REPEATS} repeats, each in a fresh process. In-process seconds per layer:
Python start-up, imports and data loading are excluded. Layer 2 includes training Splink.

| layer | median seconds | fastest | slowest |
|---|---|---|---|
{rows}

## Determinism

All {REPEATS} repeats give identical flags at every stage. Final flags hash: {reps[0]["flags_sha"][STAGES[-1]]}.
""")
    print(rows)
    print(f"wrote {REPORT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
