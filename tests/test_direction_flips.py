import datetime

import pandas as pd

from fx_bn.direction_flips import find_direction_flips

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

    assert list(flips.columns) == ['date', 'pair_i', 'pair_j', 'previous_direction', 'new_direction']
    assert flips.to_dict('records') == [
        {'date': DAY2, 'pair_i': 'A', 'pair_j': 'B', 'previous_direction': 'undirected', 'new_direction': 'no_edge'},
        {'date': DAY2, 'pair_i': 'B', 'pair_j': 'C', 'previous_direction': 'no_edge', 'new_direction': 'B<->C'},
        {'date': DAY3, 'pair_i': 'A', 'pair_j': 'B', 'previous_direction': 'no_edge', 'new_direction': 'A->B'},
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
