import numpy as np
import pandas as pd

from fx_bn.network import fit_skeleton, infer_direction, rolling_windows


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
