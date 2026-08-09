import datetime

import pandas as pd
import pytest

from fx_pcn import config
from fx_pcn.density import compute_density_table

_SEVEN_MAJORS_CSV = ','.join(config.PAIRS)
_MAX_POSSIBLE_EDGES = len(config.PAIRS) * (len(config.PAIRS) - 1) // 2


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
            'pairs': [_SEVEN_MAJORS_CSV] * 4,
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


def test_compute_density_table_scales_by_the_edge_tables_own_pair_universe():
    # A 3-pair custom network: max possible edges is C(3,2) = 3, not the
    # 7-major default's 21 -- density must reflect the network it was
    # actually built from, not a fixed constant.
    edges = pd.DataFrame(
        {
            'date': [datetime.date(2026, 1, 1)],
            'partial_corr': [0.5],
            'direction': ['A->B'],
            'pairs': ['EUR/USD,USD/CHF,GBP/USD'],
        }
    )

    density = compute_density_table(edges)

    assert density.iloc[0]['density'] == pytest.approx(1 / 3)
