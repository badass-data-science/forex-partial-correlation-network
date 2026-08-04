# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.0] - 2026-08-03

### Added
- Initial pipeline: InfluxDB client and wide-frame fetch for the 7 major FX pairs.
- Log-return computation that masks returns spanning forward-filled bars.
- Rolling-window partial-correlation skeleton via graphical lasso (`GraphicalLassoCV`).
- Edge direction inference via pairwise Granger causality with BH-FDR correction.
- `scripts/run_pipeline.py` CLI, with `--days` for a quick recent-history smoke test.
- Test suite covering rolling windows, skeleton recovery, and direction inference on synthetic data.
