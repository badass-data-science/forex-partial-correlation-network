#!/usr/bin/env python
"""Render the most recent graph in a time-varying edge-table parquet as a PNG,
via Graphviz (circular layout, curved spline edges)."""

from __future__ import annotations

import argparse
from pathlib import Path

import graphviz
import pandas as pd

POS_COLOR = '#2a78d6'  # positive partial correlation
NEG_COLOR = '#e34948'  # negative partial correlation
MID_COLOR = '#b9b8b2'  # near-zero partial correlation
INK_COLOR = '#0b0b0b'
SURFACE_COLOR = '#fcfcfb'
MUTED_COLOR = '#6f6e6a'

# |partial_corr| at or above this magnitude is treated as fully saturated color/width.
SATURATION_CEILING = 0.6

# Only edges at or above this |partial_corr| get a printed label, to keep a
# near-complete 7-node graph from drowning in overlapping text.
LABEL_THRESHOLD = 0.2


def _mix_hex(hex_a: str, hex_b: str, t: float) -> str:
    a = tuple(int(hex_a[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(hex_b[i : i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return '#' + ''.join(f'{c:02x}' for c in mixed)


def _edge_color(pcorr: float) -> str:
    t = min(abs(pcorr) / SATURATION_CEILING, 1.0)
    pole = POS_COLOR if pcorr >= 0 else NEG_COLOR
    return _mix_hex(MID_COLOR, pole, t)


def _edge_width(pcorr: float) -> float:
    return 1.4 + min(abs(pcorr) / SATURATION_CEILING, 1.0) * 4.6


def _latest_edges(edge_table: pd.DataFrame) -> pd.DataFrame:
    latest_date = edge_table['date'].max()
    return edge_table[edge_table['date'] == latest_date]


def build_graph(edges: pd.DataFrame) -> graphviz.Digraph:
    """One row per (pair_i, pair_j) edge for a single date -- see
    fx_bn.network.build_edge_table for the schema."""
    row = edges.iloc[0]
    pairs = sorted(set(edges['pair_i']) | set(edges['pair_j']))

    dot = graphviz.Digraph(engine='circo')
    dot.attr(bgcolor=SURFACE_COLOR, splines='curved', overlap='false', mindist='1.1', pad='0.4', dpi='150')
    dot.attr(
        'node',
        shape='circle',
        style='filled',
        fillcolor=SURFACE_COLOR,
        color=INK_COLOR,
        fontname='Helvetica',
        fontsize='13',
        fixedsize='true',
        width='0.95',
    )
    dot.attr('edge', fontname='Helvetica', fontsize='10')

    for pair in pairs:
        dot.node(pair, pair)

    for _, edge in edges.iterrows():
        color = _edge_color(edge['partial_corr'])
        width = f"{_edge_width(edge['partial_corr']):.2f}"
        direction = edge['direction']

        if '<->' in direction:
            source, target, arrow_dir = edge['pair_i'], edge['pair_j'], 'both'
        elif '->' in direction:
            source, target = direction.split('->')
            arrow_dir = 'forward'
        else:
            source, target, arrow_dir = edge['pair_i'], edge['pair_j'], 'none'

        edge_kwargs = dict(color=color, penwidth=width, dir=arrow_dir)
        if abs(edge['partial_corr']) >= LABEL_THRESHOLD:
            # xlabel (not label) so Graphviz's collision-avoidance placement
            # kicks in -- several of these long chords cross near the same
            # spot, and a plain midpoint label would just stack on top.
            # fontcolor stays a fixed ink tone rather than matching the edge:
            # same-hue text sitting directly on a thick same-color stroke is
            # unreadable no matter where the label lands.
            edge_kwargs['xlabel'] = f"{edge['partial_corr']:+.2f}"
            edge_kwargs['fontcolor'] = INK_COLOR
        dot.edge(source, target, **edge_kwargs)

    dot.attr(
        label=(
            f"FX partial-correlation network -- {row['date']}\n"
            f"window {row['window_days']}d, step {row['step_days']}d, {row['granularity']} bars, "
            f"min obs {row['min_observations']}, max lag {row['max_lag']}, FDR alpha {row['fdr_alpha']}\n"
            'blue = positive, red = negative partial correlation; width scales with |partial correlation|; '
            'arrows mark Granger-significant direction'
        ),
        labelloc='b',
        fontname='Helvetica',
        fontsize='11',
        fontcolor=MUTED_COLOR,
    )
    return dot


def render(input_path: Path, output_path: Path) -> None:
    edge_table = pd.read_parquet(input_path)
    edges = _latest_edges(edge_table)
    dot = build_graph(edges)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = Path(dot.render(filename=output_path.stem, directory=str(output_path.parent), format='png', cleanup=True))
    rendered.replace(output_path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Edge-table parquet produced by scripts/run_pipeline.py')
    parser.add_argument('--output', type=Path, required=True, help='PNG output path')
    args = parser.parse_args()

    render(args.input, args.output)
    print(f'Wrote {args.output}')
