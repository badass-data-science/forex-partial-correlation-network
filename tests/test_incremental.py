import datetime

import pandas as pd

from fx_bn.incremental import merge_incremental


def test_merge_incremental_keeps_existing_and_appends_only_new_dates():
    existing = pd.DataFrame(
        {
            'date': [datetime.date(2026, 8, 1), datetime.date(2026, 8, 2)],
            'partial_corr': [0.1, 0.2],
        }
    )
    # A fresh fit necessarily recomputes windows spanning the trailing overlap
    # too -- 8/2 here -- with a different value, to prove the existing row for
    # that date is kept as-is rather than overwritten by the recompute.
    freshly_computed = pd.DataFrame(
        {
            'date': [datetime.date(2026, 8, 2), datetime.date(2026, 8, 3)],
            'partial_corr': [0.999, 0.3],
        }
    )

    merged = merge_incremental(existing, freshly_computed, last_date=datetime.date(2026, 8, 2))

    assert list(merged['date']) == [datetime.date(2026, 8, 1), datetime.date(2026, 8, 2), datetime.date(2026, 8, 3)]
    assert list(merged['partial_corr']) == [0.1, 0.2, 0.3]


def test_merge_incremental_with_no_new_dates_returns_existing_unchanged():
    existing = pd.DataFrame({'date': [datetime.date(2026, 8, 1)], 'partial_corr': [0.1]})
    freshly_computed = pd.DataFrame({'date': [datetime.date(2026, 8, 1)], 'partial_corr': [0.999]})

    merged = merge_incremental(existing, freshly_computed, last_date=datetime.date(2026, 8, 1))

    assert list(merged['date']) == [datetime.date(2026, 8, 1)]
    assert list(merged['partial_corr']) == [0.1]
