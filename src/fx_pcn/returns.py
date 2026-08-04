from __future__ import annotations

import numpy as np
import pandas as pd

from fx_pcn import config
from fx_pcn.data import pair_to_colname


def log_returns(wide_df: pd.DataFrame, pairs: list[str] = config.PAIRS) -> pd.DataFrame:
    """Per-pair log returns from a wide frame produced by data.fetch_wide_frame().

    A return r_t = log(close_t) - log(close_{t-1}) is set to NaN if either bar it
    spans was forward-filled -- a forward-filled bar is a carried-forward price
    with a zero return by construction, and simultaneous forward-fills across
    pairs would otherwise inject spurious co-movement into the skeleton fit.
    """
    out = pd.DataFrame(index=wide_df.index)

    for pair in pairs:
        col = pair_to_colname(pair)
        close = wide_df[f'{col}_mid_close']
        filled = wide_df[f'{col}_is_forward_filled'].astype(bool)

        r = np.log(close) - np.log(close.shift(1))
        r[filled | filled.shift(1).fillna(True)] = np.nan
        out[pair] = r

    return out
