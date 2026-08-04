from __future__ import annotations

import pandas as pd

from fx_bn import config
from fx_bn.influx_client import DEFAULT_START, query_pair_frame


def pair_to_colname(pair: str) -> str:
    """Column-safe form of a pair, e.g. 'EUR/USD' -> 'EUR_USD'. Distinct from the
    slash-form tag value InfluxDB stores (see influx_client.query_pair_frame)."""
    return pair.replace('/', '_')


def fetch_wide_frame(
    pairs: list[str] = config.PAIRS,
    granularity: str = config.GRANULARITY,
    measurement: str = config.MEASUREMENT,
    start: str = DEFAULT_START,
) -> pd.DataFrame:
    """One row per H1 bar timestamp, with `{pair}_mid_close` and
    `{pair}_is_forward_filled` columns for every requested pair. Outer-joined on
    unix_epoch_s -- forward-filled data should already share a grid, but a pair
    missing a bar shouldn't drop that timestamp for the others.

    `start` is an RFC3339 timestamp (e.g. '2026-07-04T00:00:00Z'); defaults to
    the full history."""
    wide: pd.DataFrame | None = None

    for pair in pairs:
        col = pair_to_colname(pair)
        df = query_pair_frame(pair, granularity, measurement, start)
        df = df[['unix_epoch_s', 'mid_close', 'is_forward_filled']].rename(
            columns={
                'mid_close': f'{col}_mid_close',
                'is_forward_filled': f'{col}_is_forward_filled',
            }
        )
        wide = df if wide is None else wide.merge(df, on='unix_epoch_s', how='outer')

    assert wide is not None, 'fetch_wide_frame() requires at least one pair'
    wide = wide.sort_values('unix_epoch_s').reset_index(drop=True)
    wide['datetime'] = pd.to_datetime(wide['unix_epoch_s'], unit='s', utc=True)
    return wide.set_index('datetime').drop(columns=['unix_epoch_s'])
