import datetime

import pandas as pd

from fx_pcn import density as density_mod
from fx_pcn.report import _recent_density_rows, _recent_flip_rows, _run_params, generate_report

DAY1 = datetime.date(2026, 1, 1)
DAY2 = datetime.date(2026, 1, 2)
DAY3 = datetime.date(2026, 1, 3)

_RUN_PARAMS = {
    'window_days': 5,
    'step_days': 1,
    'min_observations': 60,
    'max_lag': 4,
    'fdr_alpha': 0.05,
    'granularity': 'H1',
}


def _edges_row(**overrides: object) -> dict:
    row = {
        'pair_i': 'EUR/USD',
        'pair_j': 'USD/CAD',
        'partial_corr': -0.23,
        'granger_p_i_to_j': 0.01,
        'granger_p_j_to_i': 0.8,
        'direction': 'EUR/USD->USD/CAD',
        **_RUN_PARAMS,
    }
    row.update(overrides)
    return row


def _synthetic_edges() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _edges_row(date=DAY1, direction='undirected'),
            _edges_row(date=DAY2, direction='EUR/USD->USD/CAD'),
            _edges_row(date=DAY3, direction='EUR/USD<->USD/CAD', partial_corr=0.4),
        ]
    )


def _synthetic_flips() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                'date': DAY2,
                'pair_i': 'EUR/USD',
                'pair_j': 'USD/CAD',
                'previous_direction': 'undirected',
                'new_direction': 'EUR/USD->USD/CAD',
            },
            {
                'date': DAY3,
                'pair_i': 'EUR/USD',
                'pair_j': 'USD/CAD',
                'previous_direction': 'EUR/USD->USD/CAD',
                'new_direction': 'EUR/USD<->USD/CAD',
            },
        ]
    )


def test_run_params_reads_most_recent_dates_regime_settings():
    edges = _synthetic_edges()
    assert _run_params(edges) == _RUN_PARAMS


def test_recent_density_rows_sorts_ascending_by_date():
    edges = _synthetic_edges()
    density = density_mod.compute_density_table(edges)

    rows = _recent_density_rows(density, n=2)

    assert [r['date'] for r in rows] == [DAY2, DAY3]
    assert rows[-1]['edge_count'] == 1
    assert rows[-1]['bidirected_edge_count'] == 1


def test_recent_flip_rows_sorts_ascending_by_date_then_pair():
    rows = _recent_flip_rows(_synthetic_flips(), n=10)

    assert [r['date'] for r in rows] == [DAY2, DAY3]
    assert rows[-1]['new_direction'] == 'EUR/USD<->USD/CAD'


def test_recent_flip_rows_handles_empty_table():
    assert _recent_flip_rows(pd.DataFrame(columns=['date', 'pair_i', 'pair_j'])) == []


def test_generate_report_writes_self_contained_html(tmp_path):
    edges = _synthetic_edges()
    density = density_mod.compute_density_table(edges)
    flips = _synthetic_flips()
    output_path = tmp_path / 'report.html'

    generate_report(edges, density, flips, output_path, include_llm_summary=False)

    html = output_path.read_text(encoding='utf-8')

    assert html.startswith('<!DOCTYPE html>')
    assert '<meta charset="UTF-8">' in html
    assert str(DAY3) in html  # report date == most recent density date
    for value in _RUN_PARAMS.values():
        assert str(value) in html
    assert 'EUR/USD' in html and 'USD/CAD' in html
    assert html.count('data:image/png;base64,') == 3  # graph + boxplots + time series
    assert 'LLM summary skipped' in html
