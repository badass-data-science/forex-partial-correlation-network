import datetime

import pandas as pd
from rdflib import RDF, XSD, Literal
from rdflib.namespace import PROV

from fx_pcn.rdf_export import FXPCN, _pair_uri, build_graph

_RUN_PARAMS = {
    'window_days': 5,
    'step_days': 1,
    'min_observations': 60,
    'max_lag': 4,
    'fdr_alpha': 0.05,
    'granularity': 'H1',
}


def _edges_row(**overrides):
    row = {
        'date': datetime.date(2026, 7, 8),
        'pair_i': 'EUR/USD',
        'pair_j': 'USD/CAD',
        'partial_corr': -0.23,
        'granger_p_i_to_j': 0.01,
        'granger_p_j_to_i': 0.8,
        'direction': 'EUR/USD->USD/CAD',
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
