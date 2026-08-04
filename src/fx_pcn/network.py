from __future__ import annotations

import contextlib
import io
import itertools
import warnings
from collections.abc import Iterator

import numpy as np
import pandas as pd
from sklearn.covariance import GraphicalLassoCV
from sklearn.exceptions import ConvergenceWarning
from statsmodels.stats.multitest import multipletests
from statsmodels.tsa.stattools import grangercausalitytests

from fx_pcn import config

Edge = tuple[str, str]

_PCORR_ZERO_TOL = 1e-10


def rolling_windows(
    returns_df: pd.DataFrame,
    window_days: int = config.WINDOW_DAYS,
    step_days: int = config.STEP_DAYS,
    min_observations: int = config.MIN_OBSERVATIONS_PER_WINDOW,
) -> Iterator[tuple[pd.Timestamp, pd.DataFrame]]:
    """Trailing `window_days`-day windows, stepped daily, complete-case only.

    Yields (window_end_date, window_df) where window_df has no NaNs (every pair
    has a real, non-forward-filled return at every timestamp) and at least
    `min_observations` rows -- too-sparse windows (early history, holiday-heavy
    weeks) are skipped rather than fit on unstable estimates.
    """
    dates = pd.date_range(returns_df.index.min().normalize(), returns_df.index.max().normalize(), freq=f'{step_days}D')

    for date in dates:
        window_end = date + pd.Timedelta(days=1)
        window_start = window_end - pd.Timedelta(days=window_days)
        window = returns_df[(returns_df.index >= window_start) & (returns_df.index < window_end)]
        complete = window.dropna()
        if len(complete) >= min_observations:
            yield date, complete


def fit_skeleton(window_returns: pd.DataFrame) -> dict[Edge, float]:
    """Undirected partial-correlation skeleton via graphical lasso.

    Standardizes each pair's returns within the window (graphical lasso is
    scale-sensitive), fits a sparse precision matrix, and converts it to partial
    correlations. Entries the L1 penalty zeroed out are simply absent as edges.
    """
    pairs = list(window_returns.columns)
    standardized = (window_returns - window_returns.mean()) / window_returns.std()

    model = GraphicalLassoCV(alphas=config.GRAPHICAL_LASSO_ALPHAS)
    with warnings.catch_warnings():
        # A rare residual ConvergenceWarning can still fire on an unusually
        # ill-conditioned window even with the constrained alpha grid above --
        # not worth surfacing per-window; the alpha grid is the real fix.
        warnings.simplefilter('ignore', ConvergenceWarning)
        model.fit(standardized.to_numpy())
    precision = model.precision_

    edges: dict[Edge, float] = {}
    for i, j in itertools.combinations(range(len(pairs)), 2):
        if abs(precision[i, j]) <= _PCORR_ZERO_TOL:
            continue
        pcorr = -precision[i, j] / np.sqrt(precision[i, i] * precision[j, j])
        edges[(pairs[i], pairs[j])] = float(pcorr)

    return edges


def _granger_pvalue(cause: pd.Series, effect: pd.Series, max_lag: int) -> float:
    """p-value (ssr F-test) that `cause` Granger-causes `effect`, jointly over lags 1..max_lag.

    Uses only the test at lag=max_lag rather than the min p-value across each
    lag 1..max_lag separately -- statsmodels' test at lag k already jointly
    tests all lags up to k, so taking a min across several k values would stack
    multiple non-independent tests and inflate the false-positive rate.
    """
    data = np.column_stack([effect.to_numpy(), cause.to_numpy()])
    with contextlib.redirect_stdout(io.StringIO()):
        results = grangercausalitytests(data, maxlag=max_lag)
    return results[max_lag][0]['ssr_ftest'][1]


def infer_direction(
    window_returns: pd.DataFrame,
    skeleton_edges: dict[Edge, float],
    max_lag: int = config.MAX_LAG,
    fdr_alpha: float = config.FDR_ALPHA,
) -> list[dict]:
    """Orient each skeleton edge via pairwise Granger causality.

    Runs both directions for every skeleton edge, then applies a Benjamini-Hochberg
    FDR correction across the whole batch of directional tests for this window
    (many pairwise tests per window -- needed to keep false positives from
    multiple comparisons in check). An edge is labeled 'i->j', 'j->i',
    'bidirected' (both directions survive), or 'undirected' (neither does).
    """
    if not skeleton_edges:
        return []

    edge_list = list(skeleton_edges.items())
    pvals_i_to_j = [
        _granger_pvalue(window_returns[i], window_returns[j], max_lag) for (i, j), _ in edge_list
    ]
    pvals_j_to_i = [
        _granger_pvalue(window_returns[j], window_returns[i], max_lag) for (i, j), _ in edge_list
    ]

    all_pvals = pvals_i_to_j + pvals_j_to_i
    reject, _, _, _ = multipletests(all_pvals, alpha=fdr_alpha, method='fdr_bh')
    n = len(edge_list)
    sig_i_to_j, sig_j_to_i = reject[:n], reject[n:]

    records = []
    for (edge, pcorr), p_ij, p_ji, sig_ij, sig_ji in zip(
        edge_list, pvals_i_to_j, pvals_j_to_i, sig_i_to_j, sig_j_to_i
    ):
        i, j = edge
        if sig_ij and sig_ji:
            direction = f'{i}<->{j}'
        elif sig_ij:
            direction = f'{i}->{j}'
        elif sig_ji:
            direction = f'{j}->{i}'
        else:
            direction = 'undirected'

        records.append(
            {
                'pair_i': i,
                'pair_j': j,
                'partial_corr': pcorr,
                'granger_p_i_to_j': p_ij,
                'granger_p_j_to_i': p_ji,
                'direction': direction,
            }
        )

    return records


def build_edge_table(
    returns_df: pd.DataFrame,
    window_days: int = config.WINDOW_DAYS,
    step_days: int = config.STEP_DAYS,
    min_observations: int = config.MIN_OBSERVATIONS_PER_WINDOW,
    max_lag: int = config.MAX_LAG,
    fdr_alpha: float = config.FDR_ALPHA,
    granularity: str = config.GRANULARITY,
) -> pd.DataFrame:
    """The full time-varying network: one row per (date, pair_i, pair_j) edge.

    Filtering to a single `date` gives that day's individual graph -- nodes are
    the 7 pairs, edges are the rows for that date.

    Every row also carries the window/step/lag/alpha/granularity settings it
    was built with, so edge tables from runs with different settings remain
    distinguishable (and filterable) even if later concatenated together.
    `granularity` isn't used by the fitting logic here -- it's threaded through
    purely to be recorded alongside the parameters that are.
    """
    rows: list[dict] = []
    for date, window in rolling_windows(returns_df, window_days, step_days, min_observations):
        skeleton = fit_skeleton(window)
        for record in infer_direction(window, skeleton, max_lag, fdr_alpha):
            record['date'] = date.date()
            record['window_days'] = window_days
            record['step_days'] = step_days
            record['min_observations'] = min_observations
            record['max_lag'] = max_lag
            record['fdr_alpha'] = fdr_alpha
            record['granularity'] = granularity
            rows.append(record)

    columns = [
        'date',
        'pair_i',
        'pair_j',
        'partial_corr',
        'granger_p_i_to_j',
        'granger_p_j_to_i',
        'direction',
        'window_days',
        'step_days',
        'min_observations',
        'max_lag',
        'fdr_alpha',
        'granularity',
    ]
    return pd.DataFrame(rows, columns=columns)
