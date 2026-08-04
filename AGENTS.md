# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this is

`fx-bn` builds a time-varying, Bayesian-network-style graph over the 7 major
FX pairs (`EUR/USD`, `GBP/USD`, `USD/JPY`, `USD/CHF`, `USD/CAD`, `AUD/USD`,
`NZD/USD`). For each rolling window of H1 bars it:

1. Fetches wide-form price data from InfluxDB (`src/fx_bn/influx_client.py`, `data.py`).
2. Computes log returns, masking any return that spans a forward-filled bar (`returns.py`).
3. Fits an undirected partial-correlation skeleton via graphical lasso (`network.fit_skeleton`).
4. Orients each skeleton edge with pairwise Granger causality, BH-FDR corrected
   across the window's tests (`network.infer_direction`).
5. Writes one row per `(date, pair_i, pair_j)` edge to `output/edges.parquet` (`pipeline.py`).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in INFLUXDB_URL / INFLUXDB_TOKEN / INFLUXDB_ORG / INFLUXDB_BUCKET
```

InfluxDB credentials are required to run the pipeline against real data, but
are **not** required to run the test suite — tests build DataFrames in memory
and never touch `influx_client`.

## Common commands

```bash
pytest                              # run the test suite
python scripts/run_pipeline.py      # full pipeline, full history since 2015
python scripts/run_pipeline.py --days 30   # quick smoke test, last 30 days only
```

## Conventions to preserve

- `from __future__ import annotations` at the top of every module.
- Single quotes for strings, double quotes only when the string itself contains a `'`.
- Type-hinted function signatures; config defaults are pulled from `fx_bn.config`
  rather than hardcoded, so window/lag/alpha parameters stay overridable.
- Docstrings explain the *why* behind a non-obvious choice (e.g. why a window is
  skipped, why FDR correction is batched per-window) — not a restatement of the signature.
- `fx_bn.influx_client` is deliberately independent of the separate ETL repo's
  `InfluxDbTool` — don't reintroduce that coupling.
- New pipeline stages should stay pure/testable: take DataFrames in, return
  DataFrames out, with I/O (InfluxDB, parquet) isolated at the edges
  (`influx_client.py`, `pipeline.py`) the way `network.py` and `returns.py` already are.

## Tests

Tests favor synthetic data with a known ground truth over fixtures pulled from
InfluxDB — e.g. `test_fit_skeleton_recovers_a_strong_direct_relationship`
constructs a series where `B` is 90% driven by `A` and asserts the skeleton
recovers that edge. Follow this pattern for new statistical logic: construct
data where the correct answer is known analytically, don't just snapshot
output.

## Secrets

Never commit `.env` (already gitignored). `.env.example` documents the required
variable names with empty values only.
