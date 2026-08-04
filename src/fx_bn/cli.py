from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fx_bn import config, render_graph
from fx_bn.influx_client import DEFAULT_START
from fx_bn.pipeline import run as run_pipeline


def _run_pipeline(args: argparse.Namespace) -> None:
    start = DEFAULT_START
    if args.days is not None:
        start = (datetime.now(UTC) - timedelta(days=args.days)).strftime('%Y-%m-%dT%H:%M:%SZ')

    logging.basicConfig(level=logging.INFO)
    edges = run_pipeline(
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


def _render_graph(args: argparse.Namespace) -> None:
    render_graph.render(args.input, args.output)
    print(f'Wrote {args.output}')


def _add_run_pipeline_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser('run-pipeline', help='Fetch FX data from InfluxDB and build the time-varying edge table')
    parser.add_argument('--output', type=Path, required=True, help='Output path for the edge table (parquet)')
    parser.add_argument('--days', type=int, default=None, help='Only pull the last N days (default: full history since 2015)')
    parser.add_argument(
        '--window-days', type=int, default=config.WINDOW_DAYS, help=f'Trailing window size in days (default: {config.WINDOW_DAYS})'
    )
    parser.add_argument(
        '--step-days', type=int, default=config.STEP_DAYS, help=f'Days between successive windows (default: {config.STEP_DAYS})'
    )
    parser.add_argument(
        '--min-observations',
        type=int,
        default=config.MIN_OBSERVATIONS_PER_WINDOW,
        help=f'Minimum complete-case bars required per window (default: {config.MIN_OBSERVATIONS_PER_WINDOW})',
    )
    parser.add_argument(
        '--max-lag', type=int, default=config.MAX_LAG, help=f'Max lag for pairwise Granger causality tests (default: {config.MAX_LAG})'
    )
    parser.add_argument(
        '--fdr-alpha', type=float, default=config.FDR_ALPHA, help=f'BH-FDR alpha for direction significance (default: {config.FDR_ALPHA})'
    )
    parser.add_argument(
        '--granularity', type=str, default=config.GRANULARITY, help=f'Bar granularity to fetch from InfluxDB (default: {config.GRANULARITY})'
    )
    parser.set_defaults(handler=_run_pipeline)


def _add_render_graph_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser('render-graph', help='Render the most recent graph in an edge-table parquet as a PNG')
    parser.add_argument('--input', type=Path, required=True, help='Edge-table parquet produced by run-pipeline')
    parser.add_argument('--output', type=Path, required=True, help='PNG output path')
    parser.set_defaults(handler=_render_graph)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='fx-bn')
    subparsers = parser.add_subparsers(dest='command', required=True)
    _add_run_pipeline_parser(subparsers)
    _add_render_graph_parser(subparsers)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == '__main__':
    main()
