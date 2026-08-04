from __future__ import annotations

import datetime

import pandas as pd


def merge_incremental(existing: pd.DataFrame, freshly_computed: pd.DataFrame, last_date: datetime.date) -> pd.DataFrame:
    """Keep every existing row and append only the freshly computed rows for
    dates after `last_date` -- shared by every derived table in this project
    that gets rebuilt incrementally (new dates appended) rather than from
    scratch on each run."""
    new_rows = freshly_computed[freshly_computed['date'] > last_date]
    return pd.concat([existing, new_rows], ignore_index=True)
