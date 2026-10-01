# X1 runtime and determinism

**Machine-dependent.** Measured on 2026-09-25 on an Apple M1
with 8 cores and 8 GB of memory, macOS
26.5.1; Python 3.12.13, pandas 3.0.5, Splink 4.0.17,
DuckDB 1.5.5. On another machine the seconds change; the determinism check should not.

Written by `leak1/runtime.py`; re-run it rather than editing this file.

## Runtime

Our world (171,999 claims), today's code, 3 repeats, each in a fresh process. In-process seconds per layer:
Python start-up, imports and data loading are excluded. Layer 2 includes training Splink.

| layer | median seconds | fastest | slowest |
|---|---|---|---|
| layer 1 | 1.3 | 1.3 | 1.3 |
| layer 2 | 63.7 | 62.8 | 66.1 |
| layer 3 | 3.4 | 3.4 | 3.4 |
| total | 68.3 | 67.6 | 70.8 |

## Determinism

All 3 repeats give identical flags at every stage. Final flags hash: 12e76d31f0f5.
