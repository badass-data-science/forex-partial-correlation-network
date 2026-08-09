import numpy as np
import pandas as pd
import pytest

from fx_pcn.network import (
    build_edge_table,
    fit_skeleton,
    infer_direction,
    pairs_from_edges,
    rolling_windows,
)


def test_rolling_windows_one_day_windows_match_calendar_days():
    index = pd.date_range('2024-01-01', periods=72, freq='h', tz='UTC')  # 3 full days
    returns_df = pd.DataFrame({'A': np.random.default_rng(0).normal(size=72)}, index=index)

    windows = list(rolling_windows(returns_df, window_days=1, step_days=1, min_observations=1))

    assert len(windows) == 3
    for date, window in windows:
        assert len(window) == 24
        assert window.index.min() >= date
        assert window.index.max() < date + pd.Timedelta(days=1)


def test_rolling_windows_skips_all_nan_window():
    index = pd.date_range('2024-01-01', periods=48, freq='h', tz='UTC')  # 2 days
    values = np.random.default_rng(0).normal(size=48)
    values[24:48] = np.nan  # second day entirely missing
    returns_df = pd.DataFrame({'A': values}, index=index)

    windows = list(rolling_windows(returns_df, window_days=1, step_days=1, min_observations=1))

    assert len(windows) == 1  # only day 0 survives


def test_fit_skeleton_recovers_a_strong_direct_relationship():
    rng = np.random.default_rng(42)
    n = 300
    a = rng.normal(size=n)
    b = 0.9 * a + 0.1 * rng.normal(size=n)  # tightly linked to a
    c = rng.normal(size=n)  # independent of both

    window_returns = pd.DataFrame({'A': a, 'B': b, 'C': c})

    skeleton = fit_skeleton(window_returns)

    assert ('A', 'B') in skeleton
    assert skeleton[('A', 'B')] > 0.5


def test_infer_direction_detects_lead_lag():
    rng = np.random.default_rng(7)
    n = 300
    x = rng.normal(size=n)
    y = np.empty(n)
    y[0] = rng.normal()
    for t in range(1, n):
        y[t] = 0.8 * x[t - 1] + 0.1 * rng.normal()  # y lags x, not the reverse

    window_returns = pd.DataFrame({'X': x, 'Y': y})
    skeleton_edges = {('X', 'Y'): 0.5}  # value unused by infer_direction, only the key pair matters

    records = infer_direction(window_returns, skeleton_edges, max_lag=2, fdr_alpha=0.05)

    assert len(records) == 1
    assert records[0]['direction'] == 'X->Y'


def _strongly_related_returns(pairs: list[str], n: int = 300, seed: int = 0) -> pd.DataFrame:
    """A datetime-indexed frame (hourly, like real bars) where every pair
    after the first is 90% driven by the first -- same recipe as
    `test_fit_skeleton_recovers_a_strong_direct_relationship`, so
    `build_edge_table` reliably produces at least one edge to check the
    network_name/pairs stamping against."""
    rng = np.random.default_rng(seed)
    base = rng.normal(size=n)
    index = pd.date_range('2024-01-01', periods=n, freq='h', tz='UTC')
    data = {pairs[0]: base}
    for pair in pairs[1:]:
        data[pair] = 0.9 * base + 0.1 * rng.normal(size=n)
    return pd.DataFrame(data, index=index)[pairs]


def test_build_edge_table_stamps_network_name_and_ordered_pairs_on_every_row():
    returns = _strongly_related_returns(['C/D', 'A/B', 'E/F'])

    edges = build_edge_table(
        returns, window_days=13, step_days=1, min_observations=100, network_name='custom-network'
    )

    assert not edges.empty
    assert (edges['network_name'] == 'custom-network').all()
    # the column order of `returns`, not alphabetical
    assert (edges['pairs'] == 'C/D,A/B,E/F').all()


def test_build_edge_table_defaults_to_config_network_name():
    from fx_pcn import config

    returns = _strongly_related_returns(['A/B', 'C/D'])

    edges = build_edge_table(returns, window_days=13, step_days=1, min_observations=100)

    assert not edges.empty
    assert (edges['network_name'] == config.DEFAULT_NETWORK_NAME).all()


def test_pairs_from_edges_recovers_the_ordered_pair_list():
    edges = pd.DataFrame({'pairs': ['C/D,A/B,E/F', 'C/D,A/B,E/F']})

    assert pairs_from_edges(edges) == ['C/D', 'A/B', 'E/F']


def test_pairs_from_edges_returns_empty_list_for_empty_edges():
    edges = pd.DataFrame({'pairs': pd.Series([], dtype=str)})

    assert pairs_from_edges(edges) == []


def test_pairs_from_edges_rejects_ambiguous_multi_network_tables():
    edges = pd.DataFrame({'pairs': ['A/B,C/D', 'A/B,C/D,E/F']})

    with pytest.raises(ValueError, match='distinct pair sets'):
        pairs_from_edges(edges)
