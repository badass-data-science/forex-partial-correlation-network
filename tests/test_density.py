import datetime

import pandas as pd
import pytest

from fx_bn.density import _MAX_POSSIBLE_EDGES, compute_density_table


def test_compute_density_table_summarizes_each_date():
    edges = pd.DataFrame(
        {
            'date': [
                datetime.date(2026, 1, 1),
                datetime.date(2026, 1, 1),
                datetime.date(2026, 1, 1),
                datetime.date(2026, 1, 2),
            ],
            'partial_corr': [0.5, -0.3, 0.1, 0.9],
            'direction': ['A->B', 'undirected', 'B<->C', 'undirected'],
        }
    )

    density = compute_density_table(edges)

    day1 = density[density['date'] == datetime.date(2026, 1, 1)].iloc[0]
    assert day1['edge_count'] == 3
    assert day1['mean_abs_partial_corr'] == pytest.approx(0.3)
    assert day1['directed_edge_count'] == 1
    assert day1['bidirected_edge_count'] == 1
    assert day1['undirected_edge_count'] == 1
    assert day1['density'] == pytest.approx(3 / _MAX_POSSIBLE_EDGES)

    day2 = density[density['date'] == datetime.date(2026, 1, 2)].iloc[0]
    assert day2['edge_count'] == 1
    assert day2['mean_abs_partial_corr'] == pytest.approx(0.9)
    assert day2['directed_edge_count'] == 0
    assert day2['bidirected_edge_count'] == 0
    assert day2['undirected_edge_count'] == 1
    assert day2['density'] == pytest.approx(1 / _MAX_POSSIBLE_EDGES)
