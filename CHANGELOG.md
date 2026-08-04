# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Graphviz-based PNG rendering of the most recent graph in an edge-table
  parquet (`fx_pcn.render_graph`), force-directed `neato` layout with curved
  splines, edges colored by partial-correlation sign and weighted by magnitude.
- Pipeline parameters (window/step/min-observations/max-lag/FDR-alpha/granularity)
  are now CLI-overridable and recorded as columns in the edge table, so runs
  with differing settings stay distinguishable.
- `run-pipeline --append`: incrementally adds new dates to an existing edge
  table instead of recomputing its full history, since already-fit windows
  never need to be refit.
- `compute-density`: derives a per-date network-density time series (edge
  count, density, mean |partial_corr|, directed/bidirected/undirected counts)
  from an edge-table parquet.
- `find-direction-flips`: derives every date a pair's edge relationship
  changed from the date before it, including transitions to/from having no
  edge at all (distinct from `undirected`). Both new subcommands support
  `--append`.

### Changed
- Replaced `scripts/run_pipeline.py` and `scripts/render_graph.py` with a
  single `fx-pcn` CLI (`src/fx_pcn/cli.py`, subcommands `run-pipeline` and
  `render-graph`).
- Extracted the `--append` merge logic (`run-pipeline` originally) into a
  shared `fx_pcn.incremental.merge_incremental`, reused by `compute-density`
  and `find-direction-flips`.
- Renamed the project from `fx-bn` to `fx-pcn` (package, `src/fx_bn` ->
  `src/fx_pcn`, CLI command, PyPI-style metadata) -- "Bayesian-network-style"
  turned out not to accurately describe the method (see the "Not actually a
  Bayesian network" note in README.md); `fx-pcn` ("partial-correlation
  network") names the actual graph object instead.

## [0.1.0] - 2026-08-03

### Added
- Initial pipeline: InfluxDB client and wide-frame fetch for the 7 major FX pairs.
- Log-return computation that masks returns spanning forward-filled bars.
- Rolling-window partial-correlation skeleton via graphical lasso (`GraphicalLassoCV`).
- Edge direction inference via pairwise Granger causality with BH-FDR correction.
- `scripts/run_pipeline.py` CLI, with `--days` for a quick recent-history smoke test.
- Test suite covering rolling windows, skeleton recovery, and direction inference on synthetic data.
