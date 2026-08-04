from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from fx_bn import config
from fx_bn.data import fetch_wide_frame
from fx_bn.influx_client import DEFAULT_START
from fx_bn.network import build_edge_table
from fx_bn.returns import log_returns

logger = logging.getLogger(__name__)


def run(
    output_path: Path,
    pairs: list[str] = config.PAIRS,
    start: str = DEFAULT_START,
    window_days: int = config.WINDOW_DAYS,
    step_days: int = config.STEP_DAYS,
    min_observations: int = config.MIN_OBSERVATIONS_PER_WINDOW,
    max_lag: int = config.MAX_LAG,
    fdr_alpha: float = config.FDR_ALPHA,
    granularity: str = config.GRANULARITY,
) -> pd.DataFrame:
    """`start` is an RFC3339 timestamp (e.g. '2026-07-04T00:00:00Z'); defaults to
    the full history. Pass a recent date for a quick smoke test."""
    logger.info('Fetching %s bars for %d pairs from InfluxDB (since %s)', granularity, len(pairs), start)
    wide = fetch_wide_frame(pairs, granularity=granularity, start=start)
    logger.info('Fetched %d bars spanning %s to %s', len(wide), wide.index.min(), wide.index.max())

    returns = log_returns(wide, pairs)
    edges = build_edge_table(
        returns,
        window_days=window_days,
        step_days=step_days,
        min_observations=min_observations,
        max_lag=max_lag,
        fdr_alpha=fdr_alpha,
        granularity=granularity,
    )
    logger.info('Built %d edges across %d distinct dates', len(edges), edges['date'].nunique())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    edges.to_parquet(output_path, index=False)
    logger.info('Wrote edge table to %s', output_path)

    return edges
