from pathlib import Path

from fx_pcn.flows import REGIME_PARAMS, regime_output_path


def test_regime_output_path_matches_existing_naming_convention():
    path = regime_output_path(
        Path('/home/emily/output/forex-partial-correlation-network'),
        'parameters',
        network_name='forex-network-seven-majors',
        window_days=5,
        step_days=1,
        min_observations=60,
        max_lag=4,
        fdr_alpha=0.05,
        granularity='H1',
        ext='parquet',
    )

    assert path == Path(
        '/home/emily/output/forex-partial-correlation-network/'
        'parameters---network-name-forex-network-seven-majors'
        '---window-days-5---step-days-1---min-observations-60'
        '---max-lag-4---fdr-alpha-0.05---granularity-H1.parquet'
    )


def test_regime_output_path_varies_by_artifact_and_extension():
    kwargs = {
        'network_name': 'forex-network-seven-majors',
        'window_days': 60,
        'step_days': 7,
        'min_observations': 30,
        'max_lag': 3,
        'fdr_alpha': 0.05,
        'granularity': 'D',
    }
    density_path = regime_output_path(Path('/out'), 'density', ext='parquet', **kwargs)
    rdf_path = regime_output_path(Path('/out'), 'RDF', ext='ttl', **kwargs)

    assert density_path.name.startswith('density---')
    assert density_path.suffix == '.parquet'
    assert rdf_path.name.startswith('RDF---')
    assert rdf_path.suffix == '.ttl'
    assert density_path != rdf_path


def test_regime_output_path_distinguishes_networks_under_an_identical_regime():
    kwargs = {
        'window_days': 5,
        'step_days': 1,
        'min_observations': 60,
        'max_lag': 4,
        'fdr_alpha': 0.05,
        'granularity': 'H1',
    }
    seven_majors_path = regime_output_path(
        Path('/out'),
        'parameters',
        ext='parquet',
        network_name='forex-network-seven-majors',
        **kwargs,
    )
    european_majors_path = regime_output_path(
        Path('/out'),
        'parameters',
        ext='parquet',
        network_name='forex-network-european-majors',
        **kwargs,
    )

    assert seven_majors_path != european_majors_path


def test_default_regime_matches_existing_config_defaults():
    from fx_pcn import config

    default = REGIME_PARAMS['default']

    assert default['granularity'] == config.GRANULARITY
    assert default['window_days'] == config.WINDOW_DAYS
    assert default['step_days'] == config.STEP_DAYS
    assert default['max_lag'] == config.MAX_LAG
    assert default['min_observations'] == config.MIN_OBSERVATIONS_PER_WINDOW
    assert default['fdr_alpha'] == config.FDR_ALPHA
    assert default['network_name'] == config.DEFAULT_NETWORK_NAME


def test_all_regimes_use_the_default_network():
    from fx_pcn import config

    for params in REGIME_PARAMS.values():
        assert params['network_name'] == config.DEFAULT_NETWORK_NAME


def test_all_four_regimes_are_registered():
    assert set(REGIME_PARAMS) == {'default', 'intraday', 'macro', 'policy'}


def test_report_path_uses_html_extension():
    kwargs = {
        'network_name': 'forex-network-seven-majors',
        'window_days': 5,
        'step_days': 1,
        'min_observations': 60,
        'max_lag': 4,
        'fdr_alpha': 0.05,
        'granularity': 'H1',
    }
    report_path = regime_output_path(Path('/out'), 'report', ext='html', **kwargs)

    assert report_path.name.startswith('report---')
    assert report_path.suffix == '.html'
