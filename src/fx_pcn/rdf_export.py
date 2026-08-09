from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from rdflib import RDF, XSD, Graph, Literal, URIRef
from rdflib.namespace import PROV

from fx_pcn import macro_vocabulary
from fx_pcn.ontology import FXPCN, KG

_RUN_PARAM_COLUMNS = [
    'window_days',
    'step_days',
    'min_observations',
    'max_lag',
    'fdr_alpha',
    'granularity',
    'network_name',
]


def _pair_uri(pair: str) -> URIRef:
    return KG[f'pair/{pair.replace("/", "")}']


def _slugify(value: str) -> str:
    """URI-safe form of an operator-chosen `network_name` -- collapses
    anything that isn't alphanumeric to a single `-`, so a name with spaces
    or slashes still produces a well-formed URI path segment."""
    return re.sub(r'[^A-Za-z0-9]+', '-', value).strip('-')


def _network_uri(network_name: str) -> URIRef:
    return KG[f'network/{_slugify(network_name)}']


def _regime_slug(params: tuple) -> str:
    window_days, step_days, min_observations, max_lag, fdr_alpha, granularity, network_name = params
    return (
        f'{_slugify(network_name)}-w{window_days}-s{step_days}-mo{min_observations}'
        f'-ml{max_lag}-fdr{fdr_alpha}-{granularity}'
    )


def _activity_uri(params: tuple) -> URIRef:
    return KG[f'run/{_regime_slug(params)}']


def _single_regime_params(table: pd.DataFrame) -> tuple:
    """The single regime `table` (any DataFrame carrying `_RUN_PARAM_COLUMNS`)
    represents -- used to attribute `NetworkSnapshot`/`DirectionFlip` URIs
    (built from density.py/direction_flips.py's output, which carries no
    run-param columns of its own, unlike `edges`) and `QualitativeSummaryRun`
    URIs (built from summary.py's bullets table) to the right regime. Raises
    if `table` spans more than one regime, since there's then no per-row
    regime to disambiguate against."""
    distinct = table[_RUN_PARAM_COLUMNS].drop_duplicates()
    if len(distinct) != 1:
        raise ValueError(
            f'can only be attributed to a single regime, but the table spans '
            f'{len(distinct)} distinct regimes'
        )
    row = distinct.iloc[0]
    return (
        int(row['window_days']),
        int(row['step_days']),
        int(row['min_observations']),
        int(row['max_lag']),
        float(row['fdr_alpha']),
        str(row['granularity']),
        str(row['network_name']),
    )


def _bind_namespaces(graph: Graph) -> None:
    graph.bind('fxpcn', FXPCN)
    graph.bind('kg', KG)
    graph.bind('prov', PROV)


def _add_pairs(graph: Graph, pairs: set[str]) -> None:
    currency_codes = {code for pair in pairs for code in pair.split('/')}
    currencies = macro_vocabulary.add_currencies(graph, currency_codes)

    for pair in pairs:
        uri = _pair_uri(pair)
        graph.add((uri, RDF.type, FXPCN.CurrencyPair))
        graph.add((uri, FXPCN.label, Literal(pair)))
        base, quote = pair.split('/')
        graph.add((uri, FXPCN.baseCurrency, currencies[base]))
        graph.add((uri, FXPCN.quoteCurrency, currencies[quote]))


def _add_networks(graph: Graph, edges: pd.DataFrame) -> None:
    """One `fxpcn:Network` per distinct `network_name` in `edges`, holding
    the ordered pair universe (`fxpcn:hasPair`) that name refers to -- lets a
    consumer resolve exactly which currency pairs a given regime's
    `prov:Activity` (linked here via `fxpcn:network`) was actually built
    from, not just how many edges it happened to produce."""
    distinct = edges[['network_name', 'pairs']].drop_duplicates()
    for _, row in distinct.iterrows():
        network_name = str(row['network_name'])
        uri = _network_uri(network_name)
        graph.add((uri, RDF.type, FXPCN.Network))
        graph.add((uri, FXPCN.label, Literal(network_name)))
        for pair in str(row['pairs']).split(','):
            graph.add((uri, FXPCN.hasPair, _pair_uri(pair)))


def _add_activities(graph: Graph, edges: pd.DataFrame) -> dict[tuple, URIRef]:
    distinct = edges[_RUN_PARAM_COLUMNS].drop_duplicates()
    activities: dict[tuple, URIRef] = {}
    for _, row in distinct.iterrows():
        window_days = int(row['window_days'])
        step_days = int(row['step_days'])
        min_observations = int(row['min_observations'])
        max_lag = int(row['max_lag'])
        fdr_alpha = float(row['fdr_alpha'])
        granularity = str(row['granularity'])
        network_name = str(row['network_name'])

        params = (
            window_days,
            step_days,
            min_observations,
            max_lag,
            fdr_alpha,
            granularity,
            network_name,
        )
        uri = _activity_uri(params)
        activities[params] = uri
        graph.add((uri, RDF.type, PROV.Activity))
        graph.add((uri, FXPCN.windowDays, Literal(window_days, datatype=XSD.integer)))
        graph.add((uri, FXPCN.stepDays, Literal(step_days, datatype=XSD.integer)))
        graph.add((uri, FXPCN.minObservations, Literal(min_observations, datatype=XSD.integer)))
        graph.add((uri, FXPCN.maxLag, Literal(max_lag, datatype=XSD.integer)))
        graph.add((uri, FXPCN.fdrAlpha, Literal(fdr_alpha, datatype=XSD.double)))
        graph.add((uri, FXPCN.granularity, Literal(granularity)))
        graph.add((uri, FXPCN.networkName, Literal(network_name)))
        graph.add((uri, FXPCN.network, _network_uri(network_name)))
    return activities


def _add_edges(graph: Graph, edges: pd.DataFrame) -> None:
    """One `fxpcn:EdgeObservation` per (date, pair_i, pair_j, regime) row.

    The regime slug (now including the network name -- see `_regime_slug`)
    is folded into the URI (not just reachable via `prov:wasGeneratedBy`)
    because different regimes' -- and, since `--pairs`/`--network-name`,
    different networks' -- `.ttl` exports get loaded into the same Neo4j
    graph via n10s (see
    operation-clusterfuck/scripts/.../load-ttl-files-into-Neo4j.cypher) --
    without it, two regimes (or two differently-scoped networks) observing
    the same (date, pair_i, pair_j) would collide on n10s's unique-URI
    constraint and silently overwrite each other's properties.

    `fxpcn:source`/`fxpcn:target` are only emitted when the row's `direction`
    names a single unambiguous leader (`i->j` or `j->i`) -- mirroring
    render_graph's own three-way arrow logic (dir='forward'/'both'/'none').
    A bidirected (`i<->j`) row has no single source/target to assert without
    inventing an ordering RDF can't actually preserve as two independent
    multi-valued properties on the same node, so it's left to
    `fxpcn:pairA`/`fxpcn:pairB` (always present, unordered) plus the
    `fxpcn:direction` literal itself.
    """
    all_pairs = {pair for pairs_csv in edges['pairs'].unique() for pair in pairs_csv.split(',')}
    _add_pairs(graph, all_pairs)
    _add_networks(graph, edges)
    activities = _add_activities(graph, edges)

    for _, row in edges.iterrows():
        pair_i = str(row['pair_i'])
        pair_j = str(row['pair_j'])
        direction = str(row['direction'])
        pair_a_slug = pair_i.replace('/', '')
        pair_b_slug = pair_j.replace('/', '')
        params = (
            int(row['window_days']),
            int(row['step_days']),
            int(row['min_observations']),
            int(row['max_lag']),
            float(row['fdr_alpha']),
            str(row['granularity']),
            str(row['network_name']),
        )
        regime_slug = _regime_slug(params)
        obs = KG[f'edge-observation/{row["date"]}/{pair_a_slug}-{pair_b_slug}/{regime_slug}']

        graph.add((obs, RDF.type, FXPCN.EdgeObservation))
        graph.add((obs, FXPCN.date, Literal(row['date'], datatype=XSD.date)))
        graph.add((obs, FXPCN.pairA, _pair_uri(pair_i)))
        graph.add((obs, FXPCN.pairB, _pair_uri(pair_j)))
        graph.add(
            (
                obs,
                FXPCN.partialCorrelation,
                Literal(float(row['partial_corr']), datatype=XSD.double),
            )
        )
        graph.add((obs, FXPCN.direction, Literal(direction)))
        graph.add(
            (
                obs,
                FXPCN.grangerPValuePairAToPairB,
                Literal(float(row['granger_p_i_to_j']), datatype=XSD.double),
            )
        )
        graph.add(
            (
                obs,
                FXPCN.grangerPValuePairBToPairA,
                Literal(float(row['granger_p_j_to_i']), datatype=XSD.double),
            )
        )

        if direction == f'{pair_i}->{pair_j}':
            graph.add((obs, FXPCN.source, _pair_uri(pair_i)))
            graph.add((obs, FXPCN.target, _pair_uri(pair_j)))
        elif direction == f'{pair_j}->{pair_i}':
            graph.add((obs, FXPCN.source, _pair_uri(pair_j)))
            graph.add((obs, FXPCN.target, _pair_uri(pair_i)))

        graph.add((obs, PROV.wasGeneratedBy, activities[params]))


def _add_density(graph: Graph, density: pd.DataFrame, params: tuple) -> None:
    """One `fxpcn:NetworkSnapshot` per date, from `compute_density_table`'s
    output. `params` (the regime `density` was computed under -- see
    `_single_regime_params`) is folded into the URI for the same reason
    `_add_edges` folds it into `EdgeObservation` URIs: distinct regimes'
    snapshots for the same date must not collide when loaded into one graph."""
    regime_slug = _regime_slug(params)
    for _, row in density.iterrows():
        snap = KG[f'network-snapshot/{row["date"]}/{regime_slug}']
        graph.add((snap, RDF.type, FXPCN.NetworkSnapshot))
        graph.add((snap, FXPCN.date, Literal(row['date'], datatype=XSD.date)))
        graph.add((snap, FXPCN.edgeCount, Literal(int(row['edge_count']), datatype=XSD.integer)))
        graph.add((snap, FXPCN.density, Literal(float(row['density']), datatype=XSD.double)))
        graph.add(
            (
                snap,
                FXPCN.meanAbsPartialCorrelation,
                Literal(float(row['mean_abs_partial_corr']), datatype=XSD.double),
            )
        )
        graph.add(
            (
                snap,
                FXPCN.directedEdgeCount,
                Literal(int(row['directed_edge_count']), datatype=XSD.integer),
            )
        )
        graph.add(
            (
                snap,
                FXPCN.bidirectedEdgeCount,
                Literal(int(row['bidirected_edge_count']), datatype=XSD.integer),
            )
        )
        graph.add(
            (
                snap,
                FXPCN.undirectedEdgeCount,
                Literal(int(row['undirected_edge_count']), datatype=XSD.integer),
            )
        )


def _add_flips(graph: Graph, flips: pd.DataFrame, params: tuple) -> None:
    """One `fxpcn:DirectionFlip` per row of `find_direction_flips`'s output.
    `params` (the regime `flips` was computed under -- see
    `_single_regime_params`) is folded into the URI for the same collision
    reason as `_add_edges`/`_add_density`."""
    _add_pairs(graph, set(flips['pair_i']) | set(flips['pair_j']))
    regime_slug = _regime_slug(params)

    for _, row in flips.iterrows():
        pair_i = str(row['pair_i'])
        pair_j = str(row['pair_j'])
        pair_a_slug = pair_i.replace('/', '')
        pair_b_slug = pair_j.replace('/', '')
        flip = KG[f'direction-flip/{row["date"]}/{pair_a_slug}-{pair_b_slug}/{regime_slug}']

        graph.add((flip, RDF.type, FXPCN.DirectionFlip))
        graph.add((flip, FXPCN.date, Literal(row['date'], datatype=XSD.date)))
        graph.add((flip, FXPCN.pairA, _pair_uri(pair_i)))
        graph.add((flip, FXPCN.pairB, _pair_uri(pair_j)))
        graph.add((flip, FXPCN.previousDirection, Literal(str(row['previous_direction']))))
        graph.add((flip, FXPCN.newDirection, Literal(str(row['new_direction']))))


def build_graph(
    edges: pd.DataFrame,
    density: pd.DataFrame | None = None,
    flips: pd.DataFrame | None = None,
) -> Graph:
    """The full edge table (required), plus `compute_density_table`'s and/or
    `find_direction_flips`'s output (optional), as one RDF graph.

    No links are drawn between a date's `NetworkSnapshot`/`DirectionFlip`s and
    that date's individual `EdgeObservation`s -- the shared `fxpcn:date`
    literal is enough for a consumer to join across them, and it keeps each
    table's export as independent as the pure functions that produced the
    tables themselves.

    `density`/`flips` must be attributable to a single regime (see
    `_single_regime_params`) -- `edges` may span more than one, but then only
    the edge table can be exported, since there'd be no way to tell which
    regime a given density/flips row belongs to.
    """
    graph = Graph()
    _bind_namespaces(graph)
    _add_edges(graph, edges)
    if density is not None:
        _add_density(graph, density, _single_regime_params(edges))
    if flips is not None:
        _add_flips(graph, flips, _single_regime_params(edges))
    return graph


def run(
    edges_path: Path,
    output_path: Path,
    density_path: Path | None = None,
    flips_path: Path | None = None,
) -> Graph:
    edges = pd.read_parquet(edges_path)
    density = pd.read_parquet(density_path) if density_path is not None else None
    flips = pd.read_parquet(flips_path) if flips_path is not None else None

    graph = build_graph(edges, density, flips)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(output_path), format='turtle')
    return graph


def build_summary_graph(bullets: pd.DataFrame) -> Graph:
    """One `fxpcn:QualitativeSummaryRun` per date in `bullets` (see
    `summary.bullets_table` -- accumulated across runs via `--append`, so
    this covers every historical report date, not just the latest), holding
    that date's LLM-derived takeaway bullets.

    Kept in its own Turtle export (`summary.run`, `fx-pcn export-summary-rdf`)
    rather than folded into `build_graph`'s output -- the numeric graph must
    stay exportable even when the LLM/Ollama is down (see `summary.py`'s
    `None`-on-failure contract), so it can't depend on this step succeeding.

    `prov:wasInformedBy` (not `wasGeneratedBy`) links each run to the
    regime's own `prov:Activity` (the same URI `build_graph` mints for that
    regime, via the shared `_activity_uri`) -- correct PROV-O usage for
    "this activity used output from that activity" rather than claiming the
    deterministic pipeline itself produced the summary. That, plus
    `fxpcn:llmModel`, lets a consumer filter LLM opinion out of hard numeric
    fact by `rdf:type` alone.

    Each run also asserts `fxpcn:networkName`/`fxpcn:network` directly on
    itself, not just reachable by resolving `wasInformedBy`'s target -- that
    target's own `fxpcn:networkName` triple only exists in `build_graph`'s
    (the numeric export's) output, a separate `.ttl` file graph-nexus can
    register as an independent source. Without asserting it here too, a
    consumer querying this summary graph on its own (not merged with its
    numeric sibling in the same store) would have no way to filter or
    identify runs by network name at all.
    """
    graph = Graph()
    _bind_namespaces(graph)
    if bullets.empty:
        return graph

    params = _single_regime_params(bullets)
    activity_uri = _activity_uri(params)
    regime_slug = _regime_slug(params)
    network_name = str(bullets['network_name'].iloc[0])
    network_uri = _network_uri(network_name)

    for date, rows in bullets.groupby('date', sort=True):
        run_uri = KG[f'summary-run/{date}/{regime_slug}']
        graph.add((run_uri, RDF.type, FXPCN.QualitativeSummaryRun))
        graph.add((run_uri, RDF.type, PROV.Activity))
        graph.add((run_uri, FXPCN.date, Literal(date, datatype=XSD.date)))
        graph.add((run_uri, FXPCN.llmModel, Literal(str(rows.iloc[0]['model']))))
        graph.add((run_uri, FXPCN.networkName, Literal(network_name)))
        graph.add((run_uri, FXPCN.network, network_uri))
        graph.add((run_uri, PROV.wasInformedBy, activity_uri))
        for _, row in rows.sort_values('bullet_index').iterrows():
            graph.add((run_uri, FXPCN.takeawayBullet, Literal(str(row['bullet_text']))))
    return graph


def run_summary_export(bullets_path: Path, output_path: Path) -> Graph:
    bullets = pd.read_parquet(bullets_path)
    graph = build_summary_graph(bullets)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(output_path), format='turtle')
    return graph
