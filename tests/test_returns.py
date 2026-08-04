import numpy as np
import pandas as pd
import pytest

from fx_pcn.returns import log_returns


def _wide_frame(closes: list[float], filled: list[bool]) -> pd.DataFrame:
    index = pd.date_range('2024-01-01', periods=len(closes), freq='h', tz='UTC')
    return pd.DataFrame(
        {
            'EUR_USD_mid_close': closes,
            'EUR_USD_is_forward_filled': filled,
        },
        index=index,
    )


def test_log_returns_basic_math():
    closes = [1.10, 1.11, 1.09]
    wide = _wide_frame(closes, [False, False, False])

    result = log_returns(wide, pairs=['EUR/USD'])

    assert np.isnan(result['EUR/USD'].iloc[0])
    assert result['EUR/USD'].iloc[1] == pytest.approx(np.log(1.11) - np.log(1.10))
    assert result['EUR/USD'].iloc[2] == pytest.approx(np.log(1.09) - np.log(1.11))


def test_log_returns_masks_forward_filled_bars():
    # Bar 1 is forward-filled -- both the return *into* bar 1 and *out of* bar 1
    # (into bar 2) should be NaN, since both span a fabricated price.
    closes = [1.10, 1.10, 1.10, 1.12]
    filled = [False, True, False, False]
    wide = _wide_frame(closes, filled)

    result = log_returns(wide, pairs=['EUR/USD'])

    assert np.isnan(result['EUR/USD'].iloc[0])  # no prior bar
    assert np.isnan(result['EUR/USD'].iloc[1])  # bar 1 itself forward-filled
    assert np.isnan(result['EUR/USD'].iloc[2])  # spans forward-filled bar 1
    assert not np.isnan(result['EUR/USD'].iloc[3])  # bars 2->3 both real
