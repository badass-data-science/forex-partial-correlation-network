from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fx_pcn import config, density, direction_flips, rdf_export, render_graph, report, summary
from fx_pcn.influx_client import DEFAULT_START
from fx_pcn.pipeline import run as run_pipeline


def _run_pipeline(args: argparse.Namespace) -> None:
    start = DEFAULT_START
    if args.days is not None:
        start = (datetime.now(UTC) - timedelta(days=args.days)).strftime('%Y-%m-%dT%H:%M:%SZ')

    logging.basicConfig(level=logging.INFO)
    if args.append and args.days is not None and args.output.exists():
        logging.getLogger(__name__).warning(
            "--days is ignored: --append fetches from the existing table's latest date instead"
        )

    edges = run_pipeline(
        output_path=args.output,
        pairs=args.pairs or config.PAIRS,
        start=start,
        window_days=args.window_days,
        step_days=args.step_days,
        min_observations=args.min_observations,
        max_lag=args.max_lag,
        fdr_alpha=args.fdr_alpha,
        granularity=args.granularity,
        network_name=args.network_name or config.DEFAULT_NETWORK_NAME,
        append=args.append,
    )
    print(edges.tail(20))


def _render_graph(args: argparse.Namespace) -> None:
    render_graph.render(args.input, args.output)
    print(f'Wrote {args.output}')


def _compute_density(args: argparse.Namespace) -> None:
    result = density.run(args.input, args.output, append=args.append)
    print(result.tail(20))


def _find_direction_flips(args: argparse.Namespace) -> None:
    result = direction_flips.run(args.input, args.output, append=args.append)
    print(result.tail(20))


def _export_rdf(args: argparse.Namespace) -> None:
    graph = rdf_export.run(
        edges_path=args.edges,
        output_path=args.output,
        density_path=args.density,
        flips_path=args.flips,
    )
    print(f'Wrote {len(graph)} triples to {args.output}')


def _generate_report(args: argparse.Namespace) -> None:
    report.run(
        edges_path=args.edges,
        output_path=args.output,
        density_path=args.density,
        flips_path=args.flips,
        model=args.model,
        include_llm_summary=not args.no_llm_summary,
        bullets_output_path=args.bullets_output,
        append_bullets=args.append_bullets,
    )
    print(f'Wrote {args.output}')


def _generate_summary(args: argparse.Namespace) -> None:
    bullets = summary.run(
        edges_path=args.edges,
        density_path=args.density,
        flips_path=args.flips,
        output_path=args.output,
        model=args.model,
        append=args.append,
    )
    print(bullets.tail(20))


def _export_summary_rdf(args: argparse.Namespace) -> None:
    graph = rdf_export.run_summary_export(bullets_path=args.bullets, output_path=args.output)
    print(f'Wrote {len(graph)} triples to {args.output}')


def _add_run_pipeline_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        'run-pipeline', help='Fetch FX data from InfluxDB and build the time-varying edge table'
    )
    parser.add_argument(
        '--output', type=Path, required=True, help='Output path for the edge table (parquet)'
    )
    parser.add_argument(
        '--pairs',
        type=str,
        nargs='+',
        default=None,
        metavar='PAIR',
        help='Currency pairs to build the network from, e.g. --pairs EUR/USD USD/CHF GBP/USD '
        f'(default: the {len(config.PAIRS)} major pairs, {", ".join(config.PAIRS)}). Requires '
        '--network-name whenever given, so the resulting network stays distinguishable from '
        'other pair sets in the output tables and RDF export.',
    )
    parser.add_argument(
        '--network-name',
        type=str,
        default=None,
        help='Name for the resulting network, e.g. forex-network-european-majors -- recorded on '
        f'every output row and folded into RDF URIs (default: {config.DEFAULT_NETWORK_NAME!r}). '
        'Required whenever --pairs is given.',
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
        help=(
            'Minimum complete-case bars required per window '
            f'(default: {config.MIN_OBSERVATIONS_PER_WINDOW})'
        ),
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
    parser.add_argument(
        '--append',
        action='store_true',
        help=(
            'Append new dates to an existing --output file instead of recomputing its full history '
            "(fetches only enough trailing data to fit windows after the existing table's latest "
            'date; has no effect if --output does not exist yet)'
        ),
    )
    parser.set_defaults(handler=_run_pipeline)


def _add_render_graph_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        'render-graph', help='Render the most recent graph in an edge-table parquet as a PNG'
    )
    parser.add_argument(
        '--input', type=Path, required=True, help='Edge-table parquet produced by run-pipeline'
    )
    parser.add_argument('--output', type=Path, required=True, help='PNG output path')
    parser.set_defaults(handler=_render_graph)


def _add_derived_table_args(
    parser: argparse.ArgumentParser, input_help: str, output_help: str
) -> None:
    parser.add_argument('--input', type=Path, required=True, help=input_help)
    parser.add_argument('--output', type=Path, required=True, help=output_help)
    parser.add_argument(
        '--append',
        action='store_true',
        help='Append new dates to an existing --output file instead of recomputing it from scratch '
        '(has no effect if --output does not exist yet)',
    )


def _add_compute_density_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        'compute-density',
        help='Summarize each date in an edge-table parquet into a network-density time series',
    )
    _add_derived_table_args(
        parser,
        'Edge-table parquet produced by run-pipeline',
        'Output path for the density table (parquet)',
    )
    parser.set_defaults(handler=_compute_density)


def _add_find_direction_flips_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        'find-direction-flips',
        help="Find every date a pair's edge direction changed from the date before it",
    )
    _add_derived_table_args(
        parser,
        'Edge-table parquet produced by run-pipeline',
        'Output path for the direction-flips table (parquet)',
    )
    parser.set_defaults(handler=_find_direction_flips)


def _add_export_rdf_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        'export-rdf',
        help='Export an edge table (plus optional density/direction-flips tables) as RDF/Turtle',
    )
    parser.add_argument(
        '--edges', type=Path, required=True, help='Edge-table parquet produced by run-pipeline'
    )
    parser.add_argument(
        '--density',
        type=Path,
        default=None,
        help='Optional density-table parquet produced by compute-density',
    )
    parser.add_argument(
        '--flips',
        type=Path,
        default=None,
        help='Optional direction-flips-table parquet produced by find-direction-flips',
    )
    parser.add_argument('--output', type=Path, required=True, help='Turtle (.ttl) output path')
    parser.set_defaults(handler=_export_rdf)


def _add_generate_report_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        'generate-report',
        help='Render a self-contained HTML report (graph, plots, tables, LLM summary)',
    )
    parser.add_argument(
        '--edges', type=Path, required=True, help='Edge-table parquet produced by run-pipeline'
    )
    parser.add_argument(
        '--density',
        type=Path,
        default=None,
        help='Optional density-table parquet produced by compute-density '
        '(computed from --edges if omitted)',
    )
    parser.add_argument(
        '--flips',
        type=Path,
        default=None,
        help='Optional direction-flips-table parquet produced by find-direction-flips '
        '(computed from --edges if omitted)',
    )
    parser.add_argument('--output', type=Path, required=True, help='HTML output path')
    parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='litellm model string for the qualitative summary '
        '(default: env LLM_MODEL or ollama_chat/glm-5.2:cloud)',
    )
    parser.add_argument(
        '--no-llm-summary',
        action='store_true',
        help='Skip the LLM-generated qualitative summary (no network call)',
    )
    parser.add_argument(
        '--bullets-output',
        type=Path,
        default=None,
        help="Optional output path for the LLM summary's takeaway bullets (parquet), for "
        'export-summary-rdf to consume -- computed from the same LLM call as the HTML '
        'summary, not a second one',
    )
    parser.add_argument(
        '--append-bullets',
        action='store_true',
        help='Append new dates to an existing --bullets-output file instead of overwriting it '
        '(has no effect if --bullets-output is not given or the file does not exist yet)',
    )
    parser.set_defaults(handler=_generate_report)


def _add_generate_summary_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        'generate-summary',
        help='Standalone LLM qualitative-summary bullets (parquet) -- generate-report already '
        'produces these via --bullets-output as part of one shared LLM call; use this only to '
        'generate/inspect them without also rendering the HTML report',
    )
    parser.add_argument(
        '--edges', type=Path, required=True, help='Edge-table parquet produced by run-pipeline'
    )
    parser.add_argument(
        '--density',
        type=Path,
        required=True,
        help='Density-table parquet produced by compute-density',
    )
    parser.add_argument(
        '--flips',
        type=Path,
        required=True,
        help='Direction-flips-table parquet produced by find-direction-flips',
    )
    parser.add_argument('--output', type=Path, required=True, help='Bullets output path (parquet)')
    parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='litellm model string for the qualitative summary '
        '(default: env LLM_MODEL or ollama_chat/glm-5.2:cloud)',
    )
    parser.add_argument(
        '--append',
        action='store_true',
        help='Append new dates to an existing --output file instead of overwriting it',
    )
    parser.set_defaults(handler=_generate_summary)


def _add_export_summary_rdf_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        'export-summary-rdf',
        help='Export a summary-bullets table (from generate-report --bullets-output or '
        'generate-summary) as RDF/Turtle',
    )
    parser.add_argument(
        '--bullets', type=Path, required=True, help='Bullets-table parquet (see generate-summary)'
    )
    parser.add_argument('--output', type=Path, required=True, help='Turtle (.ttl) output path')
    parser.set_defaults(handler=_export_summary_rdf)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='fx-pcn')
    subparsers = parser.add_subparsers(dest='command', required=True)
    _add_run_pipeline_parser(subparsers)
    _add_render_graph_parser(subparsers)
    _add_compute_density_parser(subparsers)
    _add_find_direction_flips_parser(subparsers)
    _add_export_rdf_parser(subparsers)
    _add_generate_report_parser(subparsers)
    _add_generate_summary_parser(subparsers)
    _add_export_summary_rdf_parser(subparsers)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, 'pairs', None) is not None and args.network_name is None:
        parser.error('--network-name is required whenever --pairs is given')
    args.handler(args)


if __name__ == '__main__':
    main()
