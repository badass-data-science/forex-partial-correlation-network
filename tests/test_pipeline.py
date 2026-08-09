import datetime

import pandas as pd
import pytest

from fx_pcn import config, pipeline

DAY1 = datetime.date(2024, 1, 1)
DAY2 = datetime.date(2024, 1, 2)


def _new_schema_edges_row(network_name: str, pairs_csv: str, date: datetime.date) -> dict:
    return {
        'date': date,
        'pair_i': 'A/B',
        'pair_j': 'C/D',
        'partial_corr': 0.5,
        'granger_p_i_to_j': 0.01,
        'granger_p_j_to_i': 0.8,
        'direction': 'A/B->C/D',
        'window_days': config.WINDOW_DAYS,
        'step_days': config.STEP_DAYS,
        'min_observations': config.MIN_OBSERVATIONS_PER_WINDOW,
        'max_lag': config.MAX_LAG,
        'fdr_alpha': config.FDR_ALPHA,
        'granularity': config.GRANULARITY,
        'network_name': network_name,
        'pairs': pairs_csv,
    }


def _stub_fetch_and_fit(
    monkeypatch, network_name: str, pairs_csv: str, date: datetime.date
) -> None:
    """Bypasses InfluxDB and graphical-lasso fitting entirely -- these tests
    are about pipeline.run's own --append/merge/schema-migration logic, not
    the statistics, which are already covered elsewhere (test_network.py)."""
    monkeypatch.setattr(
        pipeline, 'fetch_wide_frame', lambda pairs, granularity, start: pd.DataFrame()
    )
    monkeypatch.setattr(pipeline, 'log_returns', lambda wide, pairs: pd.DataFrame())
    monkeypatch.setattr(
        pipeline,
        'build_edge_table',
        lambda returns, **kwargs: pd.DataFrame(
            [_new_schema_edges_row(network_name, pairs_csv, date)]
        ),
    )


def test_run_append_backfills_a_pre_network_name_edge_table(tmp_path, monkeypatch):
    # Simulates a real edge-table parquet written before --pairs/--network-name
    # existed: no 'network_name'/'pairs' columns at all.
    output_path = tmp_path / 'edges.parquet'
    legacy = pd.DataFrame(
        [
            {
                'date': DAY1,
                'pair_i': 'A/B',
                'pair_j': 'C/D',
                'partial_corr': 0.4,
                'granger_p_i_to_j': 0.02,
                'granger_p_j_to_i': 0.9,
                'direction': 'undirected',
                'window_days': config.WINDOW_DAYS,
                'step_days': config.STEP_DAYS,
                'min_observations': config.MIN_OBSERVATIONS_PER_WINDOW,
                'max_lag': config.MAX_LAG,
                'fdr_alpha': config.FDR_ALPHA,
                'granularity': config.GRANULARITY,
            }
        ]
    )
    legacy.to_parquet(output_path, index=False)
    _stub_fetch_and_fit(monkeypatch, config.DEFAULT_NETWORK_NAME, ','.join(config.PAIRS), DAY2)

    edges = pipeline.run(output_path, append=True)

    assert sorted(edges['date'].unique()) == [DAY1, DAY2]
    assert (edges['network_name'] == config.DEFAULT_NETWORK_NAME).all()
    assert (edges['pairs'] == ','.join(config.PAIRS)).all()
    # persisted, not just the in-memory return value
    on_disk = pd.read_parquet(output_path)
    assert (on_disk['network_name'] == config.DEFAULT_NETWORK_NAME).all()


def test_run_append_rejects_mismatched_network_name(tmp_path, monkeypatch):
    output_path = tmp_path / 'edges.parquet'
    existing = pd.DataFrame(
        [_new_schema_edges_row('forex-network-european-majors', 'EUR/USD,USD/CHF', DAY1)]
    )
    existing.to_parquet(output_path, index=False)
    _stub_fetch_and_fit(monkeypatch, config.DEFAULT_NETWORK_NAME, ','.join(config.PAIRS), DAY2)

    with pytest.raises(ValueError, match='already holds network'):
        pipeline.run(output_path, append=True)
