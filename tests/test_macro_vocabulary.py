from rdflib import RDF, Graph, Literal
from rdflib.namespace import SKOS

from fx_pcn.macro_vocabulary import add_currencies
from fx_pcn.ontology import FXPCN


def test_currency_node_typed_and_labeled():
    graph = Graph()

    currencies = add_currencies(graph, {'EUR'})

    eur = currencies['EUR']
    assert (eur, RDF.type, FXPCN.Currency) in graph
    assert (eur, FXPCN.label, Literal('EUR')) in graph


def test_region_always_present_and_typed_skos_concept():
    graph = Graph()

    add_currencies(graph, {'CHF'})

    regions = list(graph.objects(None, FXPCN.region))
    assert len(regions) == 1
    (region,) = regions
    assert (region, RDF.type, SKOS.Concept) in graph
    assert (region, SKOS.prefLabel, Literal('Switzerland')) in graph


def test_institution_present_for_covered_currencies():
    graph = Graph()

    currencies = add_currencies(graph, {'EUR', 'USD', 'GBP', 'JPY'})

    expected_labels = {
        'EUR': 'European Central Bank',
        'USD': 'Federal Reserve',
        'GBP': 'Bank of England',
        'JPY': 'Bank of Japan',
    }
    for code, label in expected_labels.items():
        institutions = list(graph.objects(currencies[code], FXPCN.institution))
        assert len(institutions) == 1
        (institution,) = institutions
        assert (institution, RDF.type, SKOS.Concept) in graph
        assert (institution, SKOS.prefLabel, Literal(label)) in graph


def test_institution_absent_for_uncovered_currencies():
    graph = Graph()

    currencies = add_currencies(graph, {'CHF', 'CAD', 'AUD', 'NZD'})

    for code in ('CHF', 'CAD', 'AUD', 'NZD'):
        assert (currencies[code], FXPCN.institution, None) not in graph


def test_unknown_currency_code_still_gets_a_bare_currency_node():
    graph = Graph()

    currencies = add_currencies(graph, {'XYZ'})

    xyz = currencies['XYZ']
    assert (xyz, RDF.type, FXPCN.Currency) in graph
    assert (xyz, FXPCN.region, None) not in graph
    assert (xyz, FXPCN.institution, None) not in graph
