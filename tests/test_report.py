import datetime
import json

import pandas as pd
import pytest

from fx_pcn import density as density_mod
from fx_pcn import report
from fx_pcn.render_graph import LABEL_THRESHOLD
from fx_pcn.report import _d3_graph_data, _latest_edge_rows, generate_report
from fx_pcn.summary import Summary, recent_density_rows, recent_flip_rows, run_params

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
    assert run_params(edges) == _RUN_PARAMS


def test_recent_density_rows_sorts_ascending_by_date():
    edges = _synthetic_edges()
    density = density_mod.compute_density_table(edges)

    rows = recent_density_rows(density, n=2)

    assert [r['date'] for r in rows] == [DAY2, DAY3]
    assert rows[-1]['edge_count'] == 1
    assert rows[-1]['bidirected_edge_count'] == 1


def test_recent_flip_rows_sorts_ascending_by_date_then_pair():
    rows = recent_flip_rows(_synthetic_flips(), n=10)

    assert [r['date'] for r in rows] == [DAY2, DAY3]
    assert rows[-1]['new_direction'] == 'EUR/USD<->USD/CAD'


def test_recent_flip_rows_handles_empty_table():
    assert recent_flip_rows(pd.DataFrame(columns=['date', 'pair_i', 'pair_j'])) == []


def test_latest_edge_rows_includes_edges_below_the_graph_label_threshold():
    # A second, weak edge on the same (most recent) date whose |partial_corr|
    # sits below render_graph.LABEL_THRESHOLD -- it gets no printed label on
    # the graph image, but must still appear in the table.
    weak_partial_corr = LABEL_THRESHOLD - 0.1
    assert weak_partial_corr > 0  # sanity: still a real, non-trivial edge
    edges = pd.DataFrame(
        [
            _edges_row(date=DAY1),
            _edges_row(
                date=DAY1,
                pair_i='GBP/USD',
                pair_j='USD/JPY',
                partial_corr=weak_partial_corr,
                direction='undirected',
            ),
        ]
    )

    rows = _latest_edge_rows(edges)

    assert [(r['pair_i'], r['pair_j']) for r in rows] == [
        ('EUR/USD', 'USD/CAD'),
        ('GBP/USD', 'USD/JPY'),
    ]
    weak_row = rows[1]
    assert weak_row['partial_corr'] == pytest.approx(weak_partial_corr)
    assert weak_row['direction'] == 'undirected'


def test_d3_graph_data_mirrors_render_graphs_arrow_logic():
    edges = pd.DataFrame(
        [
            _edges_row(date=DAY1, direction='undirected'),
            _edges_row(
                date=DAY1,
                pair_i='GBP/USD',
                pair_j='USD/JPY',
                direction='USD/JPY->GBP/USD',
                partial_corr=0.5,
            ),
        ]
    )

    data = json.loads(_d3_graph_data(edges))

    assert {n['id'] for n in data['nodes']} == {'EUR/USD', 'USD/CAD', 'GBP/USD', 'USD/JPY'}
    links_by_pair = {(link['source'], link['target']): link for link in data['links']}
    assert links_by_pair[('EUR/USD', 'USD/CAD')]['arrow'] == 'none'  # undirected
    forward = links_by_pair[('USD/JPY', 'GBP/USD')]  # direction split on '->' gives source/target
    assert forward['arrow'] == 'forward'
    assert forward['label'] is True  # |0.5| >= LABEL_THRESHOLD


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
    assert 'All edges' in html
    assert 'Most recent density data' in html
    # boxplots + time series; D3 replaces the graph PNG
    assert html.count('data:image/png;base64,') == 2
    assert 'id="d3-graph"' in html
    assert 'd3js.org' in html  # vendored D3 bundle is inlined, not CDN-linked
    # caption used to be baked into the Graphviz PNG; now it's plain HTML text
    assert 'Blue = positive, red = negative partial correlation' in html
    assert 'About this report' in html
    for term in (
        'Partial correlation',
        'Granger causality',
        'Density',
        'Mean absolute partial correlation',
        'Direction',
    ):
        assert term in html
    assert 'Table of Contents' in html
    # ToC comes before the "About this report" *div* (id="about"), not just its own link text
    assert html.index('Table of Contents') < html.index('id="about"')
    for anchor in (
        'about',
        'network-graph',
        'recent-data',
        'recent-direction-changes',
        'distributions',
        'trends',
        'summary',
    ):
        assert f'href="#{anchor}"' in html
        assert f'id="{anchor}"' in html
    blog_url = 'https://badassdatascience.substack.com/p/our-heroine-wiretaps-seven-currency'
    repo_url = 'https://github.com/badass-data-science/forex-partial-correlation-network'
    assert f'href="{blog_url}"' in html
    assert f'href="{repo_url}"' in html
    assert 'LLM summary skipped' in html


def test_generate_report_replaces_underscores_with_spaces_in_direction_columns(tmp_path):
    edges = _synthetic_edges()
    density = density_mod.compute_density_table(edges)
    flips = pd.DataFrame(
        [
            {
                'date': DAY3,
                'pair_i': 'EUR/USD',
                'pair_j': 'USD/CAD',
                'previous_direction': 'undirected',
                'new_direction': 'no_edge',
            }
        ]
    )
    output_path = tmp_path / 'report.html'

    generate_report(edges, density, flips, output_path, include_llm_summary=False)

    html = output_path.read_text(encoding='utf-8')

    assert 'no_edge' not in html
    assert 'no edge' in html


def test_generate_report_renders_narrative_and_bullets(tmp_path, monkeypatch):
    fake_summary = Summary(
        report_date=DAY3,
        narrative='First paragraph.\n\nSecond paragraph.',
        bullets=['Watch EUR/USD.', 'Density is elevated.'],
        model='fake-model',
        params=_RUN_PARAMS,
        pairs=_TEST_PAIRS_LIST,
    )
    monkeypatch.setattr(report.summary_mod, 'generate_summary', lambda *a, **k: fake_summary)
    edges = _synthetic_edges()
    density = density_mod.compute_density_table(edges)
    flips = _synthetic_flips()
    output_path = tmp_path / 'report.html'

    generate_report(edges, density, flips, output_path, include_llm_summary=True)

    html = output_path.read_text(encoding='utf-8')
    assert 'First paragraph.' in html
    assert 'Second paragraph.' in html
    assert 'Strategic takeaways' in html
    assert '<li>Watch EUR/USD.</li>' in html
    assert '<li>Density is elevated.</li>' in html


def test_generate_report_writes_bullets_sidecar(tmp_path, monkeypatch):
    fake_summary = Summary(
        report_date=DAY3,
        narrative='Narrative.',
        bullets=['A bullet.'],
        model='fake-model',
        params=_RUN_PARAMS,
        pairs=_TEST_PAIRS_LIST,
    )
    monkeypatch.setattr(report.summary_mod, 'generate_summary', lambda *a, **k: fake_summary)
    edges = _synthetic_edges()
    density = density_mod.compute_density_table(edges)
    flips = _synthetic_flips()
    output_path = tmp_path / 'report.html'
    bullets_path = tmp_path / 'bullets.parquet'

    generate_report(
        edges,
        density,
        flips,
        output_path,
        include_llm_summary=True,
        bullets_output_path=bullets_path,
    )

    bullets = pd.read_parquet(bullets_path)
    assert bullets['bullet_text'].tolist() == ['A bullet.']
    assert (bullets['date'] == DAY3).all()


def test_generate_report_skips_bullets_sidecar_when_no_path_given(tmp_path, monkeypatch):
    monkeypatch.setattr(report.summary_mod, 'generate_summary', lambda *a, **k: None)
    edges = _synthetic_edges()
    density = density_mod.compute_density_table(edges)
    flips = _synthetic_flips()
    output_path = tmp_path / 'report.html'

    generate_report(edges, density, flips, output_path, include_llm_summary=False)

    assert list(tmp_path.iterdir()) == [output_path]
