from __future__ import annotations

import itertools
from pathlib import Path

import pandas as pd

from fx_bn import config
from fx_bn.incremental import merge_incremental

# Distinct from 'undirected': 'undirected' means the edge existed that window
# but Granger causality found no significant direction; NO_EDGE means the
# lasso penalty zeroed the pair out entirely -- there was no edge to test.
NO_EDGE = 'no_edge'


def find_direction_flips(edges: pd.DataFrame, pairs: list[str] = config.PAIRS) -> pd.DataFrame:
    """Every date a given pair's relationship state changed from the date
    before it -- an edge appearing or disappearing entirely (to/from
    NO_EDGE), a direction reversing (`i->j` to `j->i`), gaining or losing a
    Granger-significant direction (to/from `undirected`), or becoming/ceasing
    to be bidirected.

    `pairs` must be in the same order `network.build_edge_table` used to
    generate `pair_i`/`pair_j` (config.PAIRS's declared order, not
    alphabetical -- `fit_skeleton` orders edges by each pair's position in
    that list, e.g. ('USD/CAD', 'AUD/USD') because USD/CAD precedes AUD/USD
    in config.PAIRS, not the reverse). Sorting `pairs` here would silently
    fail to match rows in `edges` for any pair whose alphabetical order
    differs from its config.PAIRS order.

    One row per flip: date, pair_i, pair_j, previous_direction, new_direction.
    """
    all_dates = sorted(edges['date'].unique())
    all_pairs = list(itertools.combinations(pairs, 2))

    grid = pd.DataFrame(
        [(date, pair_i, pair_j) for date in all_dates for pair_i, pair_j in all_pairs],
        columns=['date', 'pair_i', 'pair_j'],
    )

    states = grid.merge(edges[['date', 'pair_i', 'pair_j', 'direction']], on=['date', 'pair_i', 'pair_j'], how='left')
    states['direction'] = states['direction'].fillna(NO_EDGE)
    states = states.sort_values(['pair_i', 'pair_j', 'date'])

    states['previous_direction'] = states.groupby(['pair_i', 'pair_j'])['direction'].shift(1)
    flipped = states['previous_direction'].notna() & (states['direction'] != states['previous_direction'])

    flips = states[flipped].rename(columns={'direction': 'new_direction'})
    columns = ['date', 'pair_i', 'pair_j', 'previous_direction', 'new_direction']
    return flips[columns].sort_values(['date', 'pair_i', 'pair_j']).reset_index(drop=True)


def run(input_path: Path, output_path: Path, append: bool = False) -> pd.DataFrame:
    edges = pd.read_parquet(input_path)

    existing: pd.DataFrame | None = None
    if append and output_path.exists():
        existing = pd.read_parquet(output_path)

    flips = find_direction_flips(edges)

    if existing is not None:
        flips = merge_incremental(existing, flips, last_date=existing['date'].max())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    flips.to_parquet(output_path, index=False)
    return flips
