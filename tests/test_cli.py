import sys

import pytest

from fx_pcn.cli import build_parser, main


def test_pairs_without_network_name_exits_with_usage_error(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        'argv',
        ['fx-pcn', 'run-pipeline', '--output', 'x.parquet', '--pairs', 'EUR/USD', 'USD/CHF'],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    assert '--network-name is required' in capsys.readouterr().err


def test_pairs_with_network_name_parses_cleanly():
    args = build_parser().parse_args(
        [
            'run-pipeline',
            '--output',
            'x.parquet',
            '--pairs',
            'EUR/USD',
            'USD/CHF',
            '--network-name',
            'forex-network-european-majors',
        ]
    )

    assert args.pairs == ['EUR/USD', 'USD/CHF']
    assert args.network_name == 'forex-network-european-majors'


def test_no_pairs_no_network_name_parses_cleanly_with_defaults():
    args = build_parser().parse_args(['run-pipeline', '--output', 'x.parquet'])

    assert args.pairs is None
    assert args.network_name is None


def test_network_name_alone_is_allowed_to_rename_the_default_network():
    args = build_parser().parse_args(
        ['run-pipeline', '--output', 'x.parquet', '--network-name', 'renamed-majors']
    )

    assert args.pairs is None
    assert args.network_name == 'renamed-majors'
