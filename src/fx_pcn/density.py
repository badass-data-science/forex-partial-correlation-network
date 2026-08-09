from __future__ import annotations

from pathlib import Path

import pandas as pd

from fx_pcn.incremental import merge_incremental
from fx_pcn.network import pairs_from_edges


def compute_density_table(edges: pd.DataFrame) -> pd.DataFrame:
    """One row per date summarizing that day's graph: edge count and density
    (as a fraction of the max possible over `edges`'s own pair universe --
    see network.pairs_from_edges, not a fixed constant, since `edges` may
    have been built from any --pairs set, not just the default majors), mean
    |partial_corr| among the edges the lasso penalty kept, and how many of
    those edges came out directed vs bidirected vs undirected.

    A date with zero edges (the lasso penalty zeroed every pair that window)
    has no rows in `edges` at all -- see network.build_edge_table -- so it's
    silently absent here too rather than appearing as a `edge_count == 0` row;
    that's an existing property of the edge-table schema, not something this
    function can recover.

    Meant as a compact time series for spotting regime shifts (a densifying,
    strengthening graph) without inspecting every edge by hand.
    """
    direction = edges['direction']
    bidirected = direction.str.contains('<->', regex=False)
    directed = direction.str.contains('->', regex=False) & ~bidirected
    undirected = direction == 'undirected'

    per_edge = pd.DataFrame(
        {
            'date': edges['date'],
            'abs_partial_corr': edges['partial_corr'].abs(),
            'directed': directed,
            'bidirected': bidirected,
            'undirected': undirected,
        }
    )

    density = (
        per_edge.groupby('date', sort=True)
        .agg(
            edge_count=('abs_partial_corr', 'size'),
            mean_abs_partial_corr=('abs_partial_corr', 'mean'),
            directed_edge_count=('directed', 'sum'),
            bidirected_edge_count=('bidirected', 'sum'),
            undirected_edge_count=('undirected', 'sum'),
        )
        .reset_index()
    )
    pairs = pairs_from_edges(edges)
    max_possible_edges = len(pairs) * (len(pairs) - 1) // 2
    density['density'] = density['edge_count'] / max_possible_edges

    columns = [
        'date',
        'edge_count',
        'density',
        'mean_abs_partial_corr',
        'directed_edge_count',
        'bidirected_edge_count',
        'undirected_edge_count',
    ]
    return density[columns]


def run(input_path: Path, output_path: Path, append: bool = False) -> pd.DataFrame:
    edges = pd.read_parquet(input_path)

    existing: pd.DataFrame | None = None
    if append and output_path.exists():
        existing = pd.read_parquet(output_path)

    density = compute_density_table(edges)

    if existing is not None:
        density = merge_incremental(existing, density, last_date=existing['date'].max())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    density.to_parquet(output_path, index=False)
    return density
