#!/usr/bin/env python
import argparse
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fx_bn import config
from fx_bn.influx_client import DEFAULT_START
from fx_bn.pipeline import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output path for the edge table (parquet)',
    )
    parser.add_argument(
        '--days',
        type=int,
        default=None,
        help='Only pull the last N days (default: full history since 2015)',
    )
    parser.add_argument(
        '--window-days',
        type=int,
        default=config.WINDOW_DAYS,
        help=f'Trailing window size in days (default: {config.WINDOW_DAYS})',
    )
    parser.add_argument(
        '--step-days',
        type=int,
        default=config.STEP_DAYS,
        help=f'Days between successive windows (default: {config.STEP_DAYS})',
    )
    parser.add_argument(
        '--min-observations',
        type=int,
        default=config.MIN_OBSERVATIONS_PER_WINDOW,
        help=f'Minimum complete-case bars required per window (default: {config.MIN_OBSERVATIONS_PER_WINDOW})',
    )
    parser.add_argument(
        '--max-lag',
        type=int,
        default=config.MAX_LAG,
        help=f'Max lag for pairwise Granger causality tests (default: {config.MAX_LAG})',
    )
    parser.add_argument(
        '--fdr-alpha',
        type=float,
        default=config.FDR_ALPHA,
        help=f'BH-FDR alpha for direction significance (default: {config.FDR_ALPHA})',
    )
    parser.add_argument(
        '--granularity',
        type=str,
        default=config.GRANULARITY,
        help=f'Bar granularity to fetch from InfluxDB (default: {config.GRANULARITY})',
    )
    args = parser.parse_args()

    start = DEFAULT_START
    if args.days is not None:
        start = (datetime.now(UTC) - timedelta(days=args.days)).strftime('%Y-%m-%dT%H:%M:%SZ')

    logging.basicConfig(level=logging.INFO)
    edges = run(
        output_path=args.output,
        start=start,
        window_days=args.window_days,
        step_days=args.step_days,
        min_observations=args.min_observations,
        max_lag=args.max_lag,
        fdr_alpha=args.fdr_alpha,
        granularity=args.granularity,
    )
    print(edges.tail(20))
