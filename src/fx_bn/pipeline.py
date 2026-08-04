from __future__ import annotations

import datetime
import logging
from pathlib import Path

import pandas as pd

from fx_bn import config
from fx_bn.data import fetch_wide_frame
from fx_bn.influx_client import DEFAULT_START
from fx_bn.network import build_edge_table
from fx_bn.returns import log_returns

logger = logging.getLogger(__name__)


def _merge_incremental(existing: pd.DataFrame, freshly_computed: pd.DataFrame, last_date: datetime.date) -> pd.DataFrame:
    """Every window ending on or before `last_date` was already fit and written
    on a previous run -- keep those rows as-is and only append the newly
    computed rows for dates after it, rather than re-fitting history that
    can't have changed."""
    new_rows = freshly_computed[freshly_computed['date'] > last_date]
    return pd.concat([existing, new_rows], ignore_index=True)


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
    append: bool = False,
) -> pd.DataFrame:
    """`start` is an RFC3339 timestamp (e.g. '2026-07-04T00:00:00Z'); defaults to
    the full history. Pass a recent date for a quick smoke test.

    If `append` is set and `output_path` already exists, only the windows
    after the existing table's most recent date are fetched and fit; `start`
    is overridden to fetch just enough trailing history (`window_days` back
    from that date) to compute them, and the new rows are appended to the
    existing table rather than replacing it. If `output_path` doesn't exist
    yet, `append` has no effect -- this is a normal full run.
    """
    existing: pd.DataFrame | None = None
    last_date: datetime.date | None = None
    if append and output_path.exists():
        existing = pd.read_parquet(output_path)
        last_date = existing['date'].max()
        start = (pd.Timestamp(last_date) - pd.Timedelta(days=window_days)).strftime('%Y-%m-%dT%H:%M:%SZ')
        logger.info('Appending to %s (existing data ends %s); fetching from %s', output_path, last_date, start)

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

    if existing is not None:
        edges = _merge_incremental(existing, edges, last_date)

    logger.info('Built %d edges across %d distinct dates', len(edges), edges['date'].nunique())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    edges.to_parquet(output_path, index=False)
    logger.info('Wrote edge table to %s', output_path)

    return edges
