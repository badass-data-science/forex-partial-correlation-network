import datetime

import pandas as pd
import pytest
from rdflib import RDF, XSD, Literal
from rdflib.namespace import PROV

from fx_pcn.macro_vocabulary import _currency_uri
from fx_pcn.rdf_export import (
    FXPCN,
    _activity_uri,
    _network_uri,
    _pair_uri,
    _slugify,
    build_graph,
    build_summary_graph,
)

_RUN_PARAMS = {
    'window_days': 5,
    'step_days': 1,
    'min_observations': 60,
    'max_lag': 4,
    'fdr_alpha': 0.05,
    'granularity': 'H1',
    'network_name': 'forex-network-seven-majors',
}

_TEST_PAIRS = 'EUR/USD,GBP/USD,USD/JPY,USD/CHF,USD/CAD,AUD/USD,NZD/USD'


def _edges_row(**overrides):
    row = {
        'date': datetime.date(2026, 7, 8),
        'pair_i': 'EUR/USD',
        'pair_j': 'USD/CAD',
        'partial_corr': -0.23,
        'granger_p_i_to_j': 0.01,
        'granger_p_j_to_i': 0.8,
        'direction': 'EUR/USD->USD/CAD',
        'pairs': _TEST_PAIRS,
        **_RUN_PARAMS,
    }
    row.update(overrides)
    return row


def test_directed_edge_gets_source_and_target():
    edges = pd.DataFrame([_edges_row()])

    graph = build_graph(edges)

    obs = next(graph.subjects(RDF.type, FXPCN.EdgeObservation))
    assert (obs, FXPCN.source, _pair_uri('EUR/USD')) in graph
    assert (obs, FXPCN.target, _pair_uri('USD/CAD')) in graph
    assert (obs, FXPCN.pairA, _pair_uri('EUR/USD')) in graph
    assert (obs, FXPCN.pairB, _pair_uri('USD/CAD')) in graph
    assert (obs, FXPCN.partialCorrelation, Literal(-0.23, datatype=XSD.double)) in graph
    assert (obs, FXPCN.direction, Literal('EUR/USD->USD/CAD')) in graph


def test_currency_pair_links_to_base_and_quote_currency():
    edges = pd.DataFrame([_edges_row()])

    graph = build_graph(edges)

    pair = _pair_uri('EUR/USD')
    assert (pair, FXPCN.baseCurrency, _currency_uri('EUR')) in graph
    assert (pair, FXPCN.quoteCurrency, _currency_uri('USD')) in graph


def test_bidirected_edge_has_no_source_or_target():
    edges = pd.DataFrame([_edges_row(direction='EUR/USD<->USD/CAD')])

    graph = build_graph(edges)

    obs = next(graph.subjects(RDF.type, FXPCN.EdgeObservation))
    assert (obs, FXPCN.source, None) not in graph
    assert (obs, FXPCN.target, None) not in graph
    # still identifiable as involving both pairs, just unordered
    assert (obs, FXPCN.pairA, _pair_uri('EUR/USD')) in graph
    assert (obs, FXPCN.pairB, _pair_uri('USD/CAD')) in graph


def test_undirected_edge_has_no_source_or_target():
    edges = pd.DataFrame([_edges_row(direction='undirected')])

    graph = build_graph(edges)

    obs = next(graph.subjects(RDF.type, FXPCN.EdgeObservation))
    assert (obs, FXPCN.source, None) not in graph
    assert (obs, FXPCN.target, None) not in graph


def test_shared_activity_node_across_rows_with_identical_params():
    edges = pd.DataFrame([_edges_row(), _edges_row(pair_i='GBP/USD', pair_j='USD/JPY')])

    graph = build_graph(edges)

    activities = set(graph.subjects(RDF.type, PROV.Activity))
    assert len(activities) == 1
    observations = list(graph.subjects(RDF.type, FXPCN.EdgeObservation))
    assert len(observations) == 2
    for obs in observations:
        assert (obs, PROV.wasGeneratedBy, next(iter(activities))) in graph


def test_currency_pairs_are_typed_and_labeled():
    edges = pd.DataFrame([_edges_row()])

    graph = build_graph(edges)

    eur_usd = _pair_uri('EUR/USD')
    assert (eur_usd, RDF.type, FXPCN.CurrencyPair) in graph
    assert (eur_usd, FXPCN.label, Literal('EUR/USD')) in graph


def test_density_table_becomes_network_snapshots():
    edges = pd.DataFrame([_edges_row()])
    density = pd.DataFrame(
        [
            {
                'date': datetime.date(2026, 7, 8),
                'edge_count': 17,
                'density': 17 / 21,
                'mean_abs_partial_corr': 0.22,
                'directed_edge_count': 4,
                'bidirected_edge_count': 3,
                'undirected_edge_count': 10,
            }
        ]
    )

    graph = build_graph(edges, density=density)

    snapshots = list(graph.subjects(RDF.type, FXPCN.NetworkSnapshot))
    assert len(snapshots) == 1
    (snap,) = snapshots
    assert (snap, FXPCN.edgeCount, Literal(17, datatype=XSD.integer)) in graph
    assert (snap, FXPCN.bidirectedEdgeCount, Literal(3, datatype=XSD.integer)) in graph


def test_edge_observation_uris_differ_across_regimes_for_same_date_and_pair():
    """Regression test: two regimes' `.ttl` exports get loaded into the same
    Neo4j graph via n10s (see load-ttl-files-into-Neo4j.cypher), so an
    EdgeObservation URI keyed only by (date, pair_i, pair_j) would collide
    across regimes and silently overwrite one regime's properties with the
    other's."""
    default_edge = _edges_row()
    other_regime_edge = _edges_row(granularity='D', window_days=60, step_days=7)

    default_graph = build_graph(pd.DataFrame([default_edge]))
    other_graph = build_graph(pd.DataFrame([other_regime_edge]))

    default_obs = next(default_graph.subjects(RDF.type, FXPCN.EdgeObservation))
    other_obs = next(other_graph.subjects(RDF.type, FXPCN.EdgeObservation))
    assert default_obs != other_obs


def test_edge_observation_uris_differ_across_networks_for_same_regime_and_date():
    """Same regression as above, but for two --pairs/--network-name networks
    sharing an otherwise identical regime -- network_name must also be part
    of the disambiguating regime slug, not just window/step/lag/etc."""
    seven_majors_edge = _edges_row()
    european_majors_edge = _edges_row(
        network_name='forex-network-european-majors', pairs='EUR/USD,USD/CHF,GBP/USD'
    )

    seven_majors_graph = build_graph(pd.DataFrame([seven_majors_edge]))
    european_majors_graph = build_graph(pd.DataFrame([european_majors_edge]))

    seven_majors_obs = next(seven_majors_graph.subjects(RDF.type, FXPCN.EdgeObservation))
    european_majors_obs = next(european_majors_graph.subjects(RDF.type, FXPCN.EdgeObservation))
    assert seven_majors_obs != european_majors_obs


def test_networks_are_typed_labeled_and_linked_to_their_pairs():
    edges = pd.DataFrame(
        [_edges_row(network_name='forex-network-european-majors', pairs='EUR/USD,USD/CHF,GBP/USD')]
    )

    graph = build_graph(edges)

    uri = _network_uri('forex-network-european-majors')
    assert (uri, RDF.type, FXPCN.Network) in graph
    assert (uri, FXPCN.label, Literal('forex-network-european-majors')) in graph
    assert (uri, FXPCN.hasPair, _pair_uri('EUR/USD')) in graph
    assert (uri, FXPCN.hasPair, _pair_uri('USD/CHF')) in graph
    assert (uri, FXPCN.hasPair, _pair_uri('GBP/USD')) in graph
    # GBP/USD never appears as pair_i/pair_j (only EUR/USD-USD/CAD does), but
    # it's still declared a member of the network's pair universe -- and
    # still gets its own CurrencyPair node -- via the 'pairs' column.
    assert (_pair_uri('GBP/USD'), RDF.type, FXPCN.CurrencyPair) in graph


def test_activity_links_to_its_network():
    edges = pd.DataFrame([_edges_row()])

    graph = build_graph(edges)

    activity = next(graph.subjects(RDF.type, PROV.Activity))
    assert (activity, FXPCN.network, _network_uri('forex-network-seven-majors')) in graph
    assert (activity, FXPCN.networkName, Literal('forex-network-seven-majors')) in graph


def test_slugify_collapses_non_alphanumerics():
    assert _slugify('forex network / european majors') == 'forex-network-european-majors'


def test_density_and_flips_uris_differ_across_regimes_for_same_date():
    density = pd.DataFrame(
        [
            {
                'date': datetime.date(2026, 7, 8),
                'edge_count': 17,
                'density': 17 / 21,
                'mean_abs_partial_corr': 0.22,
                'directed_edge_count': 4,
                'bidirected_edge_count': 3,
                'undirected_edge_count': 10,
            }
        ]
    )

    default_graph = build_graph(pd.DataFrame([_edges_row()]), density=density)
    other_graph = build_graph(
        pd.DataFrame([_edges_row(granularity='D', window_days=60, step_days=7)]), density=density
    )

    default_snap = next(default_graph.subjects(RDF.type, FXPCN.NetworkSnapshot))
    other_snap = next(other_graph.subjects(RDF.type, FXPCN.NetworkSnapshot))
    assert default_snap != other_snap


def test_build_graph_rejects_ambiguous_multi_regime_density():
    edges = pd.DataFrame([_edges_row(), _edges_row(granularity='D', window_days=60, step_days=7)])
    density = pd.DataFrame(
        [
            {
                'date': datetime.date(2026, 7, 8),
                'edge_count': 17,
                'density': 17 / 21,
                'mean_abs_partial_corr': 0.22,
                'directed_edge_count': 4,
                'bidirected_edge_count': 3,
                'undirected_edge_count': 10,
            }
        ]
    )

    with pytest.raises(ValueError, match='distinct regimes'):
        build_graph(edges, density=density)


def test_flips_table_becomes_direction_flips():
    edges = pd.DataFrame([_edges_row()])
    flips = pd.DataFrame(
        [
            {
                'date': datetime.date(2026, 7, 9),
                'pair_i': 'EUR/USD',
                'pair_j': 'USD/CAD',
                'previous_direction': 'EUR/USD->USD/CAD',
                'new_direction': 'no_edge',
            }
        ]
    )

    graph = build_graph(edges, flips=flips)

    flip_nodes = list(graph.subjects(RDF.type, FXPCN.DirectionFlip))
    assert len(flip_nodes) == 1
    (flip,) = flip_nodes
    assert (flip, FXPCN.previousDirection, Literal('EUR/USD->USD/CAD')) in graph
    assert (flip, FXPCN.newDirection, Literal('no_edge')) in graph
    assert (flip, FXPCN.pairA, _pair_uri('EUR/USD')) in graph


_BULLETS_COLUMNS = [
    'date',
    *_RUN_PARAMS.keys(),
    'model',
    'bullet_index',
    'bullet_text',
]


def _bullets_row(**overrides):
    row = {
        'date': datetime.date(2026, 7, 8),
        **_RUN_PARAMS,
        'model': 'fake-model',
        'bullet_index': 0,
        'bullet_text': 'Watch EUR/USD.',
    }
    row.update(overrides)
    return row


def test_build_summary_graph_is_empty_for_empty_bullets():
    graph = build_summary_graph(pd.DataFrame(columns=_BULLETS_COLUMNS))

    assert len(graph) == 0


def test_build_summary_graph_produces_one_run_node_per_date():
    bullets = pd.DataFrame(
        [
            _bullets_row(date=datetime.date(2026, 7, 8), bullet_index=0, bullet_text='First.'),
            _bullets_row(date=datetime.date(2026, 7, 8), bullet_index=1, bullet_text='Second.'),
            _bullets_row(date=datetime.date(2026, 7, 9), bullet_index=0, bullet_text='Third.'),
        ]
    )

    graph = build_summary_graph(bullets)

    runs = list(graph.subjects(RDF.type, FXPCN.QualitativeSummaryRun))
    assert len(runs) == 2


def test_build_summary_graph_bullets_are_ordered_and_typed():
    bullets = pd.DataFrame(
        [
            _bullets_row(bullet_index=1, bullet_text='Second.'),
            _bullets_row(bullet_index=0, bullet_text='First.'),
        ]
    )

    graph = build_summary_graph(bullets)

    (run,) = graph.subjects(RDF.type, FXPCN.QualitativeSummaryRun)
    assert (run, RDF.type, PROV.Activity) in graph
    assert (run, FXPCN.date, Literal(datetime.date(2026, 7, 8), datatype=XSD.date)) in graph
    assert (run, FXPCN.llmModel, Literal('fake-model')) in graph
    bullet_texts = {str(o) for o in graph.objects(run, FXPCN.takeawayBullet)}
    assert bullet_texts == {'First.', 'Second.'}


def test_build_summary_graph_links_to_same_activity_as_numeric_export():
    """The summary run's `prov:wasInformedBy` target must be the exact same
    URI `build_graph`'s numeric export mints for that regime's `prov:Activity`
    -- that's what lets the two independently-loaded `.ttl` files join once
    both are in the same Neo4j graph."""
    params = (
        _RUN_PARAMS['window_days'],
        _RUN_PARAMS['step_days'],
        _RUN_PARAMS['min_observations'],
        _RUN_PARAMS['max_lag'],
        _RUN_PARAMS['fdr_alpha'],
        _RUN_PARAMS['granularity'],
        _RUN_PARAMS['network_name'],
    )
    bullets = pd.DataFrame([_bullets_row()])

    graph = build_summary_graph(bullets)

    (run,) = graph.subjects(RDF.type, FXPCN.QualitativeSummaryRun)
    assert (run, PROV.wasInformedBy, _activity_uri(params)) in graph


def test_build_summary_graph_asserts_network_name_directly_on_each_run():
    """A consumer querying the summary graph on its own -- not merged with
    its numeric sibling .ttl in the same store -- must still be able to
    filter/identify runs by network name, so this can't only live on the
    Activity node `wasInformedBy` points at (that node's own properties are
    only asserted in build_graph's output, a separate file)."""
    bullets = pd.DataFrame([_bullets_row(network_name='forex-network-european-majors')])

    graph = build_summary_graph(bullets)

    (run,) = graph.subjects(RDF.type, FXPCN.QualitativeSummaryRun)
    assert (run, FXPCN.networkName, Literal('forex-network-european-majors')) in graph
    assert (run, FXPCN.network, _network_uri('forex-network-european-majors')) in graph


def test_build_summary_graph_rejects_ambiguous_multi_regime_bullets():
    bullets = pd.DataFrame(
        [_bullets_row(), _bullets_row(granularity='D', window_days=60, step_days=7)]
    )

    with pytest.raises(ValueError, match='distinct regimes'):
        build_summary_graph(bullets)
