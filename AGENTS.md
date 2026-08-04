# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this is

`fx-pcn` builds a time-varying partial-correlation network (an undirected
Gaussian graphical model, not a Bayesian network -- see the "Not actually a
Bayesian network" note in README.md if that distinction matters to you) with
Granger-causal edge direction, over the 7 major FX pairs (`EUR/USD`,
`GBP/USD`, `USD/JPY`, `USD/CHF`, `USD/CAD`, `AUD/USD`, `NZD/USD`). For each
rolling window of H1 bars it:

1. Fetches wide-form price data from InfluxDB (`src/fx_pcn/influx_client.py`, `data.py`).
2. Computes log returns, masking any return that spans a forward-filled bar (`returns.py`).
3. Fits an undirected partial-correlation skeleton via graphical lasso (`network.fit_skeleton`).
4. Orients each skeleton edge with pairwise Granger causality, BH-FDR corrected
   across the window's tests (`network.infer_direction`).
5. Writes one row per `(date, pair_i, pair_j)` edge to a parquet file (`pipeline.py`).
6. Optionally renders the most recent date's graph as a PNG via Graphviz (`render_graph.py`).

All of this is driven through a single CLI, `src/fx_pcn/cli.py` (entry point `fx-pcn`,
also runnable as `python -m fx_pcn.cli`) with one subcommand per stage.

This repo doesn't populate InfluxDB itself -- that's a separate repo,
[`ETL-forex-time-series-data`](https://github.com/badass-data-science/ETL-forex-time-series-data),
which must be run first to get real data into the bucket `fx-pcn` reads from.

## Setup

This project's `.venv` is `uv`-managed (`pyvenv.cfg` shows `uv = ...`) — there is no
`pip` inside it. Use `uv`, not `pip`, for all dependency work here:

```bash
uv sync --extra dev
export INFLUXDB_URL=... INFLUXDB_TOKEN=... INFLUXDB_ORG=... INFLUXDB_BUCKET=...
```

`uv sync` alone omits the `dev` extra (drops `pytest`) — always pass `--extra dev`
in this repo. `render-graph` also needs the system Graphviz binaries with the
neato-family layout plugin installed (`libgvplugin-neato-layout8` on Debian/Ubuntu;
`dot -v` should list `circo`/`neato` under `layout`, not just `dot`).

InfluxDB credentials are required to run the pipeline against real data, but
are **not** required to run the test suite — tests build DataFrames in memory
and never touch `influx_client`.

## Common commands

```bash
pytest                                                  # run the test suite
fx-pcn run-pipeline --output output/edges.parquet        # full pipeline, full history since 2015
fx-pcn run-pipeline --output output/edges.parquet --days 30   # quick smoke test, last 30 days only
fx-pcn render-graph --input output/edges.parquet --output output/graph.png   # PNG of the most recent graph
```

## Conventions to preserve

- `from __future__ import annotations` at the top of every module.
- Single quotes for strings, double quotes only when the string itself contains a `'`.
- Type-hinted function signatures; config defaults are pulled from `fx_pcn.config`
  rather than hardcoded, so window/lag/alpha parameters stay overridable.
- Docstrings explain the *why* behind a non-obvious choice (e.g. why a window is
  skipped, why FDR correction is batched per-window) — not a restatement of the signature.
- `fx_pcn.influx_client` is deliberately independent of the separate ETL repo's
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

No `.env` file, by design — `INFLUXDB_URL`/`INFLUXDB_TOKEN`/`INFLUXDB_ORG`/`INFLUXDB_BUCKET`
must already be set in the calling shell's environment (see README.md). Don't
reintroduce a `.env`/`python-dotenv` loading path.
