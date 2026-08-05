from __future__ import annotations

from pathlib import Path

import pandas as pd
from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import PROV

# Small custom ontology -- nothing standard covers "time-varying
# partial-correlation network," so this mints just the handful of terms that
# need it, reusing PROV-O for provenance rather than inventing that too. The
# `.local` base IRIs match the convention the graph-nexus project already
# uses for its registered sources' `--base-iri` (e.g.
# https://strategic-reports.local/kg/), so this would slot in consistently
# if it were ever registered as a graph-nexus source -- not something this
# module does itself.
FXPCN = Namespace('https://fx-pcn.local/ontology#')
KG = Namespace('https://fx-pcn.local/kg/')

_RUN_PARAM_COLUMNS = [
    'window_days',
    'step_days',
    'min_observations',
    'max_lag',
    'fdr_alpha',
    'granularity',
]


def _pair_uri(pair: str) -> URIRef:
    return KG[f'pair/{pair.replace("/", "")}']


def _activity_uri(params: tuple) -> URIRef:
    window_days, step_days, min_observations, max_lag, fdr_alpha, granularity = params
    slug = (
        f'run/w{window_days}-s{step_days}-mo{min_observations}'
        f'-ml{max_lag}-fdr{fdr_alpha}-{granularity}'
    )
    return KG[slug]


def _bind_namespaces(graph: Graph) -> None:
    graph.bind('fxpcn', FXPCN)
    graph.bind('kg', KG)
    graph.bind('prov', PROV)


def _add_pairs(graph: Graph, pairs: set[str]) -> None:
    for pair in pairs:
        uri = _pair_uri(pair)
        graph.add((uri, RDF.type, FXPCN.CurrencyPair))
        graph.add((uri, FXPCN.label, Literal(pair)))


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

        params = (window_days, step_days, min_observations, max_lag, fdr_alpha, granularity)
        uri = _activity_uri(params)
        activities[params] = uri
        graph.add((uri, RDF.type, PROV.Activity))
        graph.add((uri, FXPCN.windowDays, Literal(window_days, datatype=XSD.integer)))
        graph.add((uri, FXPCN.stepDays, Literal(step_days, datatype=XSD.integer)))
        graph.add((uri, FXPCN.minObservations, Literal(min_observations, datatype=XSD.integer)))
        graph.add((uri, FXPCN.maxLag, Literal(max_lag, datatype=XSD.integer)))
        graph.add((uri, FXPCN.fdrAlpha, Literal(fdr_alpha, datatype=XSD.double)))
        graph.add((uri, FXPCN.granularity, Literal(granularity)))
    return activities


def _add_edges(graph: Graph, edges: pd.DataFrame) -> None:
    """One `fxpcn:EdgeObservation` per (date, pair_i, pair_j) row.

    `fxpcn:source`/`fxpcn:target` are only emitted when the row's `direction`
    names a single unambiguous leader (`i->j` or `j->i`) -- mirroring
    render_graph's own three-way arrow logic (dir='forward'/'both'/'none').
    A bidirected (`i<->j`) row has no single source/target to assert without
    inventing an ordering RDF can't actually preserve as two independent
    multi-valued properties on the same node, so it's left to
    `fxpcn:pairA`/`fxpcn:pairB` (always present, unordered) plus the
    `fxpcn:direction` literal itself.
    """
    _add_pairs(graph, set(edges['pair_i']) | set(edges['pair_j']))
    activities = _add_activities(graph, edges)

    for _, row in edges.iterrows():
        pair_i = str(row['pair_i'])
        pair_j = str(row['pair_j'])
        direction = str(row['direction'])
        pair_a_slug = pair_i.replace('/', '')
        pair_b_slug = pair_j.replace('/', '')
        obs = KG[f'edge-observation/{row["date"]}/{pair_a_slug}-{pair_b_slug}']

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

        params = (
            int(row['window_days']),
            int(row['step_days']),
            int(row['min_observations']),
            int(row['max_lag']),
            float(row['fdr_alpha']),
            str(row['granularity']),
        )
        graph.add((obs, PROV.wasGeneratedBy, activities[params]))


def _add_density(graph: Graph, density: pd.DataFrame) -> None:
    """One `fxpcn:NetworkSnapshot` per date, from `compute_density_table`'s output."""
    for _, row in density.iterrows():
        snap = KG[f'network-snapshot/{row["date"]}']
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


def _add_flips(graph: Graph, flips: pd.DataFrame) -> None:
    """One `fxpcn:DirectionFlip` per row of `find_direction_flips`'s output."""
    _add_pairs(graph, set(flips['pair_i']) | set(flips['pair_j']))

    for _, row in flips.iterrows():
        pair_i = str(row['pair_i'])
        pair_j = str(row['pair_j'])
        pair_a_slug = pair_i.replace('/', '')
        pair_b_slug = pair_j.replace('/', '')
        flip = KG[f'direction-flip/{row["date"]}/{pair_a_slug}-{pair_b_slug}']

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
    """
    graph = Graph()
    _bind_namespaces(graph)
    _add_edges(graph, edges)
    if density is not None:
        _add_density(graph, density)
    if flips is not None:
        _add_flips(graph, flips)
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
