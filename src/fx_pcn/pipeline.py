from __future__ import annotations

import datetime
import logging
from pathlib import Path

import pandas as pd

from fx_pcn import config
from fx_pcn.data import fetch_wide_frame
from fx_pcn.incremental import merge_incremental
from fx_pcn.influx_client import DEFAULT_START
from fx_pcn.network import build_edge_table
from fx_pcn.returns import log_returns

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
    network_name: str = config.DEFAULT_NETWORK_NAME,
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

    Raises if `append` targets a file already holding a *different*
    `network_name` -- appending rows built from a different `pairs` list into
    an existing table would silently conflate two distinct networks in one
    file, which every downstream consumer (density.py, direction_flips.py,
    rdf_export.py) assumes can't happen (see network.pairs_from_edges).

    A file written before `network_name`/`pairs` existed as columns (i.e.
    before --pairs/--network-name at all) is backfilled in memory as the
    default 7-majors network the first time `--append` touches it here --
    every edge table that predates this feature was always built from
    `config.PAIRS`, so this is a straight migration, not a guess -- and the
    full rewrite below (`edges.to_parquet`) persists it, so this only ever
    happens once per file.
    """
    existing: pd.DataFrame | None = None
    last_date: datetime.date | None = None
    if append and output_path.exists():
        existing = pd.read_parquet(output_path)
        if 'network_name' not in existing.columns:
            existing = existing.copy()
            existing['network_name'] = config.DEFAULT_NETWORK_NAME
            existing['pairs'] = ','.join(config.PAIRS)
        existing_network_name = str(existing['network_name'].iloc[0])
        if existing_network_name != network_name:
            raise ValueError(
                f'--append target {output_path} already holds network '
                f'{existing_network_name!r}; refusing to append {network_name!r} rows '
                'into it -- use a different --output path for a different network'
            )
        last_date = existing['date'].max()
        start = (pd.Timestamp(last_date) - pd.Timedelta(days=window_days)).strftime(
            '%Y-%m-%dT%H:%M:%SZ'
        )
        logger.info(
            'Appending to %s (existing data ends %s); fetching from %s',
            output_path,
            last_date,
            start,
        )

    logger.info(
        'Fetching %s bars for %d pairs from InfluxDB (since %s)', granularity, len(pairs), start
    )
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
        network_name=network_name,
    )

    if existing is not None:
        assert last_date is not None  # set alongside `existing`, above
        edges = merge_incremental(existing, edges, last_date)

    logger.info('Built %d edges across %d distinct dates', len(edges), edges['date'].nunique())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    edges.to_parquet(output_path, index=False)
    logger.info('Wrote edge table to %s', output_path)

    return edges
