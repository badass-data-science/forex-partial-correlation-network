import datetime

import pandas as pd

from fx_pcn import summary

DAY1 = datetime.date(2026, 1, 1)
DAY2 = datetime.date(2026, 1, 2)

_RUN_PARAMS = {
    'window_days': 5,
    'step_days': 1,
    'min_observations': 60,
    'max_lag': 4,
    'fdr_alpha': 0.05,
    'granularity': 'H1',
    'network_name': 'forex-network-seven-majors',
}

_TEST_PAIRS = 'EUR/USD,GBP/USD,USD/JPY,USD/CHF,USD/CAD,AUD/USD,NZD/USD'
_TEST_PAIRS_LIST = _TEST_PAIRS.split(',')


def _edges_row(**overrides: object) -> dict:
    row = {
        'pair_i': 'EUR/USD',
        'pair_j': 'USD/CAD',
        'partial_corr': -0.23,
        'granger_p_i_to_j': 0.01,
        'granger_p_j_to_i': 0.8,
        'direction': 'EUR/USD->USD/CAD',
        'pairs': _TEST_PAIRS,
        **_RUN_PARAMS,
    }
    row.update(overrides)
    return row


def _synthetic_edges() -> pd.DataFrame:
    return pd.DataFrame([_edges_row(date=DAY1), _edges_row(date=DAY2)])


def test_parse_response_splits_narrative_from_bullets():
    raw = (
        'Paragraph one.\n\nParagraph two.\n\n'
        f'{summary._TAKEAWAYS_HEADING}\n'
        '- First takeaway.\n'
        '- Second takeaway.\n'
    )

    narrative, bullets = summary._parse_response(raw)

    assert narrative == 'Paragraph one.\n\nParagraph two.'
    assert bullets == ['First takeaway.', 'Second takeaway.']


def test_parse_response_handles_missing_heading():
    raw = 'Just a narrative, no takeaways heading.'

    narrative, bullets = summary._parse_response(raw)

    assert narrative == raw
    assert bullets == []


def test_parse_response_ignores_non_bullet_lines_after_heading():
    raw = f'Narrative.\n\n{summary._TAKEAWAYS_HEADING}\nSome preamble.\n- Real bullet.\n'

    _, bullets = summary._parse_response(raw)

    assert bullets == ['Real bullet.']


def test_bullets_table_empty_when_summary_is_none():
    table = summary.bullets_table(None)

    assert table.empty
    assert list(table.columns) == summary._BULLETS_TABLE_COLUMNS


def test_bullets_table_empty_when_summary_has_no_bullets():
    result = summary.Summary(
        report_date=DAY1,
        narrative='text',
        bullets=[],
        model='m',
        params=_RUN_PARAMS,
        pairs=_TEST_PAIRS_LIST,
    )

    assert summary.bullets_table(result).empty


def test_bullets_table_one_row_per_bullet_in_order():
    result = summary.Summary(
        report_date=DAY1,
        narrative='text',
        bullets=['first', 'second'],
        model='fake-model',
        params=_RUN_PARAMS,
        pairs=_TEST_PAIRS_LIST,
    )

    table = summary.bullets_table(result)

    assert list(table.columns) == summary._BULLETS_TABLE_COLUMNS
    assert table['bullet_index'].tolist() == [0, 1]
    assert table['bullet_text'].tolist() == ['first', 'second']
    assert (table['date'] == DAY1).all()
    assert (table['model'] == 'fake-model').all()
    assert (table['window_days'] == _RUN_PARAMS['window_days']).all()
    assert (table['pairs'] == _TEST_PAIRS).all()


def test_generate_summary_returns_none_when_llm_call_fails(monkeypatch):
    monkeypatch.setattr(summary, '_call_llm', lambda prompt, model: None)
    edges = _synthetic_edges()
    density = pd.DataFrame(
        [
            {
                'date': DAY1,
                'density': 0.5,
                'mean_abs_partial_corr': 0.2,
                'edge_count': 1,
                'directed_edge_count': 1,
                'bidirected_edge_count': 0,
                'undirected_edge_count': 0,
            }
        ]
    )
    flips = pd.DataFrame(
        columns=['date', 'pair_i', 'pair_j', 'previous_direction', 'new_direction']
    )

    assert summary.generate_summary(edges, density, flips) is None


def test_generate_summary_parses_llm_response(monkeypatch):
    raw = f'Narrative here.\n\n{summary._TAKEAWAYS_HEADING}\n- Watch EUR/USD.\n'
    monkeypatch.setattr(summary, '_call_llm', lambda prompt, model: raw)
    edges = _synthetic_edges()
    density = pd.DataFrame(
        [
            {
                'date': DAY1,
                'density': 0.5,
                'mean_abs_partial_corr': 0.2,
                'edge_count': 1,
                'directed_edge_count': 1,
                'bidirected_edge_count': 0,
                'undirected_edge_count': 0,
            }
        ]
    )
    flips = pd.DataFrame(
        columns=['date', 'pair_i', 'pair_j', 'previous_direction', 'new_direction']
    )

    result = summary.generate_summary(edges, density, flips)

    assert result is not None
    assert result.narrative == 'Narrative here.'
    assert result.bullets == ['Watch EUR/USD.']
    assert result.params == _RUN_PARAMS
    assert result.pairs == _TEST_PAIRS_LIST


def test_run_append_accumulates_across_dates(tmp_path, monkeypatch):
    output_path = tmp_path / 'bullets.parquet'
    edges_path = tmp_path / 'edges.parquet'
    density_path = tmp_path / 'density.parquet'
    flips_path = tmp_path / 'flips.parquet'

    day1_edges = pd.DataFrame([_edges_row(date=DAY1)])
    day1_edges.to_parquet(edges_path)
    pd.DataFrame(
        [
            {
                'date': DAY1,
                'density': 0.5,
                'mean_abs_partial_corr': 0.2,
                'edge_count': 1,
                'directed_edge_count': 1,
                'bidirected_edge_count': 0,
                'undirected_edge_count': 0,
            }
        ]
    ).to_parquet(density_path)
    pd.DataFrame(
        columns=['date', 'pair_i', 'pair_j', 'previous_direction', 'new_direction']
    ).to_parquet(flips_path)

    monkeypatch.setattr(
        summary,
        '_call_llm',
        lambda prompt, model: f'Narrative.\n\n{summary._TAKEAWAYS_HEADING}\n- Day one bullet.\n',
    )
    summary.run(edges_path, density_path, flips_path, output_path, append=True)

    day2_edges = pd.DataFrame([_edges_row(date=DAY2)])
    day2_edges.to_parquet(edges_path)
    pd.DataFrame(
        [
            {
                'date': DAY2,
                'density': 0.6,
                'mean_abs_partial_corr': 0.3,
                'edge_count': 1,
                'directed_edge_count': 1,
                'bidirected_edge_count': 0,
                'undirected_edge_count': 0,
            }
        ]
    ).to_parquet(density_path)
    monkeypatch.setattr(
        summary,
        '_call_llm',
        lambda prompt, model: f'Narrative.\n\n{summary._TAKEAWAYS_HEADING}\n- Day two bullet.\n',
    )
    result = summary.run(edges_path, density_path, flips_path, output_path, append=True)

    assert sorted(result['date'].unique()) == [DAY1, DAY2]
    assert set(result['bullet_text']) == {'Day one bullet.', 'Day two bullet.'}


def test_run_append_skips_merge_when_existing_file_is_empty(tmp_path, monkeypatch):
    output_path = tmp_path / 'bullets.parquet'
    pd.DataFrame(columns=summary._BULLETS_TABLE_COLUMNS).to_parquet(output_path)

    edges_path = tmp_path / 'edges.parquet'
    density_path = tmp_path / 'density.parquet'
    flips_path = tmp_path / 'flips.parquet'
    pd.DataFrame([_edges_row(date=DAY1)]).to_parquet(edges_path)
    pd.DataFrame(
        [
            {
                'date': DAY1,
                'density': 0.5,
                'mean_abs_partial_corr': 0.2,
                'edge_count': 1,
                'directed_edge_count': 1,
                'bidirected_edge_count': 0,
                'undirected_edge_count': 0,
            }
        ]
    ).to_parquet(density_path)
    pd.DataFrame(
        columns=['date', 'pair_i', 'pair_j', 'previous_direction', 'new_direction']
    ).to_parquet(flips_path)

    monkeypatch.setattr(
        summary,
        '_call_llm',
        lambda prompt, model: f'Narrative.\n\n{summary._TAKEAWAYS_HEADING}\n- Bullet.\n',
    )
    result = summary.run(edges_path, density_path, flips_path, output_path, append=True)

    assert list(result['bullet_text']) == ['Bullet.']
