# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Graphviz-based PNG rendering of the most recent graph in an edge-table
  parquet (`fx_bn.render_graph`), force-directed `neato` layout with curved
  splines, edges colored by partial-correlation sign and weighted by magnitude.
- Pipeline parameters (window/step/min-observations/max-lag/FDR-alpha/granularity)
  are now CLI-overridable and recorded as columns in the edge table, so runs
  with differing settings stay distinguishable.

### Changed
- Replaced `scripts/run_pipeline.py` and `scripts/render_graph.py` with a
  single `fx-bn` CLI (`src/fx_bn/cli.py`, subcommands `run-pipeline` and
  `render-graph`).

## [0.1.0] - 2026-08-03

### Added
- Initial pipeline: InfluxDB client and wide-frame fetch for the 7 major FX pairs.
- Log-return computation that masks returns spanning forward-filled bars.
- Rolling-window partial-correlation skeleton via graphical lasso (`GraphicalLassoCV`).
- Edge direction inference via pairwise Granger causality with BH-FDR correction.
- `scripts/run_pipeline.py` CLI, with `--days` for a quick recent-history smoke test.
- Test suite covering rolling windows, skeleton recovery, and direction inference on synthetic data.
