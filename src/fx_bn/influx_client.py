"""Minimal read-only InfluxDB client for pulling forward-filled candlestick data.

Deliberately independent of the ETL repo's `forex.util.influxdb_tool.InfluxDbTool` --
this project talks to the same InfluxDB instance over the network but stays decoupled
from that repo's codebase.
"""

from __future__ import annotations

import os

import pandas as pd
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

load_dotenv()

DEFAULT_START = '2015-01-01T00:00:00Z'


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f'environment variable {name!r} is not set (see .env.example)')
    return value


def _client() -> InfluxDBClient:
    return InfluxDBClient(url=_env('INFLUXDB_URL'), token=_env('INFLUXDB_TOKEN'), org=_env('INFLUXDB_ORG'))


def query_pair_frame(
    pair: str,
    granularity: str,
    measurement: str,
    start: str = DEFAULT_START,
) -> pd.DataFrame:
    """Pull one instrument's field columns from InfluxDB, pivoted into wide form.

    Mirrors the Flux query pattern used by the ETL repo's ForwardFillInator
    (pivot on _time so each field becomes its own column, one row per bar).
    """
    bucket = _env('INFLUXDB_BUCKET')
    query = f'''
        from(bucket: "{bucket}")
          |> range(start: {start})
          |> filter(fn: (r) => r._measurement == "{measurement}")
          |> filter(fn: (r) => r.granularity == "{granularity}")
          |> filter(fn: (r) => r.instrument == "{pair}")
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> drop(columns: ["_start", "_stop", "_measurement"])
    '''
    with _client() as client:
        df = client.query_api().query_data_frame(query, org=_env('INFLUXDB_ORG'))

    if isinstance(df, list):
        df = pd.concat(df, ignore_index=True) if df else pd.DataFrame()

    for column_name in ('result', 'table'):
        if column_name in df.columns:
            df = df.drop(columns=[column_name])

    if '_time' in df.columns:
        df['unix_epoch_s'] = (
            pd.to_datetime(df['_time'], utc=True).astype('datetime64[ns, UTC]').astype('int64') // 10**9
        )
        df = df.drop(columns=['_time'])

    return df.sort_values('unix_epoch_s').reset_index(drop=True)
