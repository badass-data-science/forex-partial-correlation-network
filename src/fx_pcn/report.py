from __future__ import annotations

import base64
import datetime
import json
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use('Agg')  # headless: no display server on a CLI/server host

import matplotlib.pyplot as plt
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from matplotlib.figure import Figure

from fx_pcn import density as density_mod
from fx_pcn import direction_flips as direction_flips_mod
from fx_pcn import render_graph
from fx_pcn import summary as summary_mod
from fx_pcn.incremental import merge_incremental

# Reuses render_graph's palette so the matplotlib plots read as the same visual
# system as the network graph rather than introducing a second color scheme.
_ACCENT_COLOR = render_graph.POS_COLOR
_INK_COLOR = render_graph.INK_COLOR
_SURFACE_COLOR = render_graph.SURFACE_COLOR
_MUTED_COLOR = render_graph.MUTED_COLOR
_MARKER_COLOR = render_graph.NEG_COLOR  # already the palette's "red", reused for visibility

_LATEST_VALUE_LABEL = 'Most recent value'

_TRAILING_YEAR = datetime.timedelta(days=365)

_EDGE_TABLE_COLUMNS = [
    'pair_i',
    'pair_j',
    'partial_corr',
    'direction',
    'granger_p_i_to_j',
    'granger_p_j_to_i',
]

_TEMPLATES_DIR = Path(__file__).parent / 'templates'
_D3_BUNDLE_PATH = _TEMPLATES_DIR / 'vendor' / 'd3.v7.min.js'


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


def _fig_to_data_uri(fig: Figure) -> str:
    buffer = BytesIO()
    fig.savefig(buffer, format='png', dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    return f'data:image/png;base64,{encoded}'


def _style_axes(ax: plt.Axes, title: str) -> None:
    ax.set_title(title, fontsize=10, color=_INK_COLOR)
    ax.set_facecolor(_SURFACE_COLOR)
    ax.tick_params(colors=_MUTED_COLOR, labelsize=8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(_MUTED_COLOR)
    ax.spines['bottom'].set_color(_MUTED_COLOR)
    ax.grid(True, axis='y', color=_MUTED_COLOR, alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)


def _mark_latest_value(ax: plt.Axes, x: int | datetime.date, y: float) -> None:
    """A highly visible marker for the metric's most recent value, with a
    legend entry naming it -- distinguishes "the current reading" from the
    rest of the distribution/trend at a glance."""
    # matplotlib's stubs don't model datetime.date x-values, though plotting dates on the
    # x-axis (as _timeseries_data_uri already does via ax.plot) is supported at runtime.
    ax.scatter(
        [x],  # type: ignore[arg-type]
        [y],
        color=_MARKER_COLOR,
        edgecolor=_INK_COLOR,
        linewidth=0.8,
        s=70,
        zorder=5,
        label=_LATEST_VALUE_LABEL,
    )
    legend = ax.legend(loc='upper right', fontsize=7.5, frameon=False)
    for text in legend.get_texts():
        text.set_color(_INK_COLOR)


@lru_cache(maxsize=1)
def _d3_bundle() -> str:
    """Vendored D3 v7 (github.com/d3/d3, ISC license) rather than a CDN
    <script src>, so the report stays a single self-contained HTML file that
    renders offline -- consistent with how the matplotlib/Graphviz images are
    embedded as data: URIs rather than linked."""
    return _D3_BUNDLE_PATH.read_text(encoding='utf-8')


def _d3_graph_data(edges: pd.DataFrame) -> str:
    """Nodes/links for a D3 force-directed rendering of the most recent date's
    graph. Mirrors render_graph.build_graph's own source/target/arrow-direction
    logic exactly (see its 'if <-> / elif -> / else' block) rather than
    reimplementing it differently, even though build_graph's Graphviz PNG
    itself is no longer rendered here.

    Escaping <, >, & as \\uXXXX (same approach as strategic-report-generator's
    renderer.py:_build_article_jsonld) keeps the JSON semantically identical
    while making a </script> breakout impossible -- defense in depth, since
    the 7 major pairs never actually contain those characters."""
    latest = render_graph._latest_edges(edges)
    node_ids = sorted(set(latest['pair_i']) | set(latest['pair_j']))

    links = []
    for _, row in latest.iterrows():
        pair_i, pair_j = str(row['pair_i']), str(row['pair_j'])
        direction = str(row['direction'])
        partial_corr = float(row['partial_corr'])
        if '<->' in direction:
            source, target, arrow = pair_i, pair_j, 'both'
        elif '->' in direction:
            source, target = direction.split('->')
            arrow = 'forward'
        else:
            source, target, arrow = pair_i, pair_j, 'none'
        links.append(
            {
                'source': source,
                'target': target,
                'partial_corr': partial_corr,
                'arrow': arrow,
                'label': abs(partial_corr) >= render_graph.LABEL_THRESHOLD,
            }
        )

    payload = {'nodes': [{'id': node_id} for node_id in node_ids], 'links': links}
    return (
        json.dumps(payload).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    )


def _latest_edge_rows(edges: pd.DataFrame) -> list[dict]:
    """Every edge for the most recent date, in tabular form -- the same edges
    the graph draws (render_graph._latest_edges keeps every skeleton edge
    regardless of |partial_corr|; only the printed xlabel is gated by
    render_graph.LABEL_THRESHOLD), sorted ascending by pair_i then pair_j."""
    latest = render_graph._latest_edges(edges).sort_values(['pair_i', 'pair_j'])
    return [
        {
            'pair_i': str(row['pair_i']),
            'pair_j': str(row['pair_j']),
            'partial_corr': float(row['partial_corr']),
            'direction': str(row['direction']),
            'granger_p_i_to_j': float(row['granger_p_i_to_j']),
            'granger_p_j_to_i': float(row['granger_p_j_to_i']),
        }
        for _, row in latest[_EDGE_TABLE_COLUMNS].iterrows()
    ]


def _boxplot_data_uri(density: pd.DataFrame) -> str:
    """Distribution of density and mean |partial corr| across the full history,
    each with a marker for that metric's most recent value."""
    date_min, date_max = density['date'].min(), density['date'].max()
    latest = density.sort_values('date').iloc[-1]

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), facecolor=_SURFACE_COLOR)
    columns = [('density', 'Density'), ('mean_abs_partial_corr', 'Mean |partial corr|')]
    for ax, (column, title) in zip(axes, columns, strict=True):
        ax.boxplot(
            density[column].dropna(),
            patch_artist=True,
            boxprops={'facecolor': _SURFACE_COLOR, 'edgecolor': _INK_COLOR},
            medianprops={'color': _ACCENT_COLOR, 'linewidth': 1.6},
            whiskerprops={'color': _INK_COLOR},
            capprops={'color': _INK_COLOR},
            flierprops={'markeredgecolor': _MUTED_COLOR, 'markersize': 3},
        )
        ax.set_xticks([])
        _style_axes(ax, f'{title}\n{date_min} to {date_max}')
        _mark_latest_value(ax, 1, latest[column])
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def _timeseries_data_uri(density: pd.DataFrame) -> str:
    """Density and mean |partial corr| over the trailing year from the source
    data's most recent date, each with a marker for that metric's most recent
    value."""
    cutoff = density['date'].max() - _TRAILING_YEAR
    recent = density[density['date'] >= cutoff].sort_values('date')
    latest = recent.iloc[-1]

    fig, axes = plt.subplots(1, 2, figsize=(9, 4), facecolor=_SURFACE_COLOR)
    columns = [('density', 'Density'), ('mean_abs_partial_corr', 'Mean |partial corr|')]
    for ax, (column, title) in zip(axes, columns, strict=True):
        ax.plot(recent['date'], recent[column], color=_ACCENT_COLOR, linewidth=1.4)
        _style_axes(ax, title)
        _mark_latest_value(ax, latest['date'], latest[column])
    fig.autofmt_xdate(rotation=30)
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def generate_report(
    edges: pd.DataFrame,
    density: pd.DataFrame,
    flips: pd.DataFrame,
    output_path: Path,
    *,
    model: str | None = None,
    include_llm_summary: bool = True,
    bullets_output_path: Path | None = None,
    append_bullets: bool = False,
) -> None:
    """Renders the HTML report and, if `bullets_output_path` is given, also
    writes/appends the LLM summary's takeaway bullets as a parquet sidecar
    for `export-summary-rdf` to consume -- computed from the single
    `summary_mod.generate_summary()` call below, not a second LLM call, so
    the HTML narrative and the RDF bullets can't drift apart from each
    other on any given run."""
    report_date = density['date'].max()
    params = summary_mod.run_params(edges)
    recent_density_rows = summary_mod.recent_density_rows(density)
    recent_flip_rows = summary_mod.recent_flip_rows(flips)

    summary_result = None
    if include_llm_summary:
        summary_result = summary_mod.generate_summary(edges, density, flips, model=model)

    if bullets_output_path is not None:
        fresh_bullets = summary_mod.bullets_table(summary_result)
        if append_bullets and bullets_output_path.exists():
            existing_bullets = pd.read_parquet(bullets_output_path)
            if not existing_bullets.empty:
                fresh_bullets = merge_incremental(
                    existing_bullets, fresh_bullets, last_date=existing_bullets['date'].max()
                )
        bullets_output_path.parent.mkdir(parents=True, exist_ok=True)
        fresh_bullets.to_parquet(bullets_output_path, index=False)

    tmpl = _env().get_template('report.html.j2')
    html = tmpl.render(
        report_date=report_date,
        updated=datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z'),
        params=params,
        d3_js=_d3_bundle(),
        d3_graph_data=_d3_graph_data(edges),
        latest_edge_rows=_latest_edge_rows(edges),
        boxplot_data_uri=_boxplot_data_uri(density),
        timeseries_data_uri=_timeseries_data_uri(density),
        recent_density_rows=recent_density_rows,
        recent_flip_rows=recent_flip_rows,
        llm_summary=summary_result,
        llm_summary_enabled=include_llm_summary,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')


def run(
    edges_path: Path,
    output_path: Path,
    density_path: Path | None = None,
    flips_path: Path | None = None,
    *,
    model: str | None = None,
    include_llm_summary: bool = True,
    bullets_output_path: Path | None = None,
    append_bullets: bool = False,
) -> None:
    edges = pd.read_parquet(edges_path)
    density = (
        pd.read_parquet(density_path)
        if density_path is not None
        else density_mod.compute_density_table(edges)
    )
    flips = (
        pd.read_parquet(flips_path)
        if flips_path is not None
        else direction_flips_mod.find_direction_flips(edges)
    )

    generate_report(
        edges,
        density,
        flips,
        output_path,
        model=model,
        include_llm_summary=include_llm_summary,
        bullets_output_path=bullets_output_path,
        append_bullets=append_bullets,
    )
