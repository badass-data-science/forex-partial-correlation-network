import datetime

import pandas as pd

from fx_pcn.direction_flips import find_direction_flips, run

DAY1 = datetime.date(2026, 1, 1)
DAY2 = datetime.date(2026, 1, 2)
DAY3 = datetime.date(2026, 1, 3)


def test_find_direction_flips_detects_edge_appearing_disappearing_and_reversing():
    # (A, B): undirected -> no edge (lasso zeroed it) -> a fresh directed edge
    # (A, C): unchanged the whole time -> no flips
    # (B, C): no edge -> a fresh bidirected edge -> unchanged
    edges = pd.DataFrame(
        {
            'date': [DAY1, DAY1, DAY2, DAY2, DAY3, DAY3, DAY3],
            'pair_i': ['A', 'A', 'A', 'B', 'A', 'A', 'B'],
            'pair_j': ['B', 'C', 'C', 'C', 'B', 'C', 'C'],
            'direction': ['undirected', 'A->C', 'A->C', 'B<->C', 'A->B', 'A->C', 'B<->C'],
        }
    )

    flips = find_direction_flips(edges, pairs=['A', 'B', 'C'])

    assert list(flips.columns) == [
        'date',
        'pair_i',
        'pair_j',
        'previous_direction',
        'new_direction',
    ]
    assert flips.to_dict('records') == [
        {
            'date': DAY2,
            'pair_i': 'A',
            'pair_j': 'B',
            'previous_direction': 'undirected',
            'new_direction': 'no_edge',
        },
        {
            'date': DAY2,
            'pair_i': 'B',
            'pair_j': 'C',
            'previous_direction': 'no_edge',
            'new_direction': 'B<->C',
        },
        {
            'date': DAY3,
            'pair_i': 'A',
            'pair_j': 'B',
            'previous_direction': 'no_edge',
            'new_direction': 'A->B',
        },
    ]


def test_find_direction_flips_first_date_never_flips():
    # Every pair is missing (implicitly no_edge) on the very first date --
    # that must not itself count as a flip, since there's no prior date to
    # compare against.
    edges = pd.DataFrame(
        {
            'date': [DAY1],
            'pair_i': ['A'],
            'pair_j': ['B'],
            'direction': ['A->B'],
        }
    )

    flips = find_direction_flips(edges, pairs=['A', 'B', 'C'])

    assert flips.empty


def test_run_derives_pairs_from_the_edges_tables_own_pairs_column(tmp_path):
    # (B, C) never has a surviving edge on either date -- run() must still
    # know it's part of the network (via the 'pairs' column) to flag it
    # going no_edge -> D3 on DAY2, rather than only recovering pairs that
    # happened to appear in pair_i/pair_j.
    edges = pd.DataFrame(
        {
            'date': [DAY1, DAY2],
            'pair_i': ['A', 'B'],
            'pair_j': ['B', 'C'],
            'direction': ['A->B', 'B<->C'],
            'pairs': ['A,B,C', 'A,B,C'],
        }
    )
    input_path = tmp_path / 'edges.parquet'
    output_path = tmp_path / 'flips.parquet'
    edges.to_parquet(input_path)

    flips = run(input_path, output_path)

    assert {(row['pair_i'], row['pair_j']) for _, row in flips.iterrows()} == {
        ('A', 'B'),
        ('B', 'C'),
    }
