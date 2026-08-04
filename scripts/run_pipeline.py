#!/usr/bin/env python
import argparse
import logging
from datetime import UTC, datetime, timedelta

from fx_bn.influx_client import DEFAULT_START
from fx_bn.pipeline import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--days',
        type=int,
        default=None,
        help='Only pull the last N days (default: full history since 2015)',
    )
    args = parser.parse_args()

    start = DEFAULT_START
    if args.days is not None:
        start = (datetime.now(UTC) - timedelta(days=args.days)).strftime('%Y-%m-%dT%H:%M:%SZ')

    logging.basicConfig(level=logging.INFO)
    edges = run(start=start)
    print(edges.tail(20))
