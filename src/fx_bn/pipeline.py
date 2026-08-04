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

DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent / 'output' / 'edges.parquet'


def run(
    pairs: list[str] = config.PAIRS,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    start: str = DEFAULT_START,
) -> pd.DataFrame:
    """`start` is an RFC3339 timestamp (e.g. '2026-07-04T00:00:00Z'); defaults to
    the full history. Pass a recent date for a quick smoke test."""
    logger.info('Fetching %s bars for %d pairs from InfluxDB (since %s)', config.GRANULARITY, len(pairs), start)
    wide = fetch_wide_frame(pairs, start=start)
    logger.info('Fetched %d bars spanning %s to %s', len(wide), wide.index.min(), wide.index.max())

    returns = log_returns(wide, pairs)
    edges = build_edge_table(returns)
    logger.info('Built %d edges across %d distinct dates', len(edges), edges['date'].nunique())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    edges.to_parquet(output_path, index=False)
    logger.info('Wrote edge table to %s', output_path)

    return edges
