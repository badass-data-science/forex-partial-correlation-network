from __future__ import annotations

from rdflib import RDF, Graph, Literal, URIRef
from rdflib.namespace import SKOS

from fx_pcn.ontology import FXPCN, KG

# Static, hand-authored -- not a matching problem. Every FX pair decomposes
# into two currencies, and each currency has exactly one issuer; there's no
# ambiguity to resolve here, unlike linking a currency to a news topic.
#
# `region` is populated for all 8 currencies (checked against a real
# strategic-report-generator concept vocabulary: 'australia', 'canada',
# 'japan', 'new zealand', 'switzerland', 'united kingdom', 'united states',
# and 'european union' for EUR all exist as exact-string concept labels).
#
# `institution` is left `None` for CHF/CAD/AUD/NZD: 'swiss national bank',
# 'bank of canada', 'reserve bank of australia', and 'reserve bank of new
# zealand' don't exist as concepts in that same vocabulary check -- and for
# CAD specifically, 'royal bank of canada' (a commercial bank, not the
# central bank) *does* exist, which is a real false-friend risk for a
# label-similarity linker. Better to mint nothing than mint something that
# could get matched to the wrong entity.
_CURRENCY_META: dict[str, dict[str, str | None]] = {
    'EUR': {'region': 'European Union', 'institution': 'European Central Bank'},
    'USD': {'region': 'United States', 'institution': 'Federal Reserve'},
    'GBP': {'region': 'United Kingdom', 'institution': 'Bank of England'},
    'JPY': {'region': 'Japan', 'institution': 'Bank of Japan'},
    'CHF': {'region': 'Switzerland', 'institution': None},
    'CAD': {'region': 'Canada', 'institution': None},
    'AUD': {'region': 'Australia', 'institution': None},
    'NZD': {'region': 'New Zealand', 'institution': None},
}


def _currency_uri(code: str) -> URIRef:
    return KG[f'currency/{code}']


def _concept_uri(kind: str, label: str) -> URIRef:
    slug = label.replace(' ', '')
    return KG[f'{kind}/{slug}']


def add_currencies(graph: Graph, currency_codes: set[str]) -> dict[str, URIRef]:
    """Mints `fxpcn:Currency` nodes for the given currency codes, each linked
    to a `skos:Concept` region node (always) and institution node (only
    where `_CURRENCY_META` has one) via `fxpcn:region`/`fxpcn:institution`.

    Region/institution nodes are typed `skos:Concept` with `skos:prefLabel`
    -- matching strategic-report-generator's own vocabulary conventions
    directly (see graph-nexus's hub/sources.yaml: `concept_type: skos:Concept`,
    `label_property: skos:prefLabel`) -- rather than a custom fxpcn type, so
    a future graph-nexus registration against these nodes needs no
    conversion step, and so graph-nexus's LIMES matching only ever sees
    these nodes, never fxpcn:CurrencyPair/EdgeObservation/etc. (a different
    rdf:type entirely).

    Deliberately takes plain currency-code strings rather than fx-pcn's
    pair-string format or a DataFrame -- pair-string parsing and the
    CurrencyPair linkage are fx-pcn-specific and stay in rdf_export.py, so
    this module has no dependency on anything fx-pcn-specific beyond the
    shared FXPCN/KG namespaces, in case it's ever split into its own repo.

    Unknown currency codes (not in `_CURRENCY_META`) are silently skipped --
    still minted as a bare `fxpcn:Currency` node, just without region/
    institution links, rather than raising, so this stays usable if the
    pair universe ever grows beyond the 8 currencies checked against the
    vocabulary so far.

    Returns a `{code: Currency URIRef}` mapping for the caller to link
    CurrencyPair nodes against.
    """
    currencies: dict[str, URIRef] = {}
    for code in currency_codes:
        currency_uri = _currency_uri(code)
        currencies[code] = currency_uri
        graph.add((currency_uri, RDF.type, FXPCN.Currency))
        graph.add((currency_uri, FXPCN.label, Literal(code)))

        meta = _CURRENCY_META.get(code)
        if meta is None:
            continue

        region_label = meta['region']
        if region_label is not None:
            region_uri = _concept_uri('region', region_label)
            graph.add((region_uri, RDF.type, SKOS.Concept))
            graph.add((region_uri, SKOS.prefLabel, Literal(region_label)))
            graph.add((currency_uri, FXPCN.region, region_uri))

        institution_label = meta['institution']
        if institution_label is not None:
            institution_uri = _concept_uri('institution', institution_label)
            graph.add((institution_uri, RDF.type, SKOS.Concept))
            graph.add((institution_uri, SKOS.prefLabel, Literal(institution_label)))
            graph.add((currency_uri, FXPCN.institution, institution_uri))

    return currencies
