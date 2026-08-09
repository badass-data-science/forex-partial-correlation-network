from __future__ import annotations

import base64
import datetime
import json
import os
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use('Agg')  # headless: no display server on a CLI/server host

import litellm
import matplotlib.pyplot as plt
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from matplotlib.figure import Figure

from fx_pcn import density as density_mod
from fx_pcn import direction_flips as direction_flips_mod
from fx_pcn import render_graph

# Reuses render_graph's palette so the matplotlib plots read as the same visual
# system as the network graph rather than introducing a second color scheme.
_ACCENT_COLOR = render_graph.POS_COLOR
_INK_COLOR = render_graph.INK_COLOR
_SURFACE_COLOR = render_graph.SURFACE_COLOR
_MUTED_COLOR = render_graph.MUTED_COLOR
_MARKER_COLOR = render_graph.NEG_COLOR  # already the palette's "red", reused for visibility

_LATEST_VALUE_LABEL = 'Most recent value'

_TRAILING_YEAR = datetime.timedelta(days=365)

_RUN_PARAM_COLUMNS = [
    'window_days',
    'step_days',
    'min_observations',
    'max_lag',
    'fdr_alpha',
    'granularity',
]

_DENSITY_TABLE_COLUMNS = [
    'date',
    'edge_count',
    'density',
    'mean_abs_partial_corr',
    'directed_edge_count',
    'bidirected_edge_count',
    'undirected_edge_count',
]

_FLIPS_TABLE_COLUMNS = ['date', 'pair_i', 'pair_j', 'previous_direction', 'new_direction']

_EDGE_TABLE_COLUMNS = [
    'pair_i',
    'pair_j',
    'partial_corr',
    'direction',
    'granger_p_i_to_j',
    'granger_p_j_to_i',
]

_DEFAULT_MODEL = os.environ.get('LLM_MODEL', 'ollama_chat/glm-5.2:cloud')

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
        json.dumps(payload)
        .replace('<', '\\u003c')
        .replace('>', '\\u003e')
        .replace('&', '\\u0026')
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


def _recent_density_rows(density: pd.DataFrame, n: int = 5) -> list[dict]:
    """The n most recent dates, ascending (oldest of the n first)."""
    recent = density.sort_values('date', ascending=True).tail(n)
    return [
        {
            'date': row['date'],
            'edge_count': int(row['edge_count']),
            'density': float(row['density']),
            'mean_abs_partial_corr': float(row['mean_abs_partial_corr']),
            'directed_edge_count': int(row['directed_edge_count']),
            'bidirected_edge_count': int(row['bidirected_edge_count']),
            'undirected_edge_count': int(row['undirected_edge_count']),
        }
        for _, row in recent[_DENSITY_TABLE_COLUMNS].iterrows()
    ]


def _recent_flip_rows(flips: pd.DataFrame, n: int = 10) -> list[dict]:
    """The n most recent flips, ascending by date then pair_i/pair_j (oldest
    of the n first)."""
    if flips.empty:
        return []
    recent = flips.sort_values(['date', 'pair_i', 'pair_j'], ascending=True).tail(n)
    return [
        {
            'date': row['date'],
            'pair_i': str(row['pair_i']),
            'pair_j': str(row['pair_j']),
            'previous_direction': str(row['previous_direction']),
            'new_direction': str(row['new_direction']),
        }
        for _, row in recent[_FLIPS_TABLE_COLUMNS].iterrows()
    ]


def _run_params(edges: pd.DataFrame) -> dict:
    """Run parameters from the most recent date's row -- every row for a given
    date shares the same regime settings (see network.build_edge_table)."""
    latest_date = edges['date'].max()
    row = edges[edges['date'] == latest_date].iloc[0]
    return {
        'window_days': int(row['window_days']),
        'step_days': int(row['step_days']),
        'min_observations': int(row['min_observations']),
        'max_lag': int(row['max_lag']),
        'fdr_alpha': float(row['fdr_alpha']),
        'granularity': str(row['granularity']),
    }


def _build_summary_prompt(
    report_date: datetime.date,
    params: dict,
    density: pd.DataFrame,
    recent_density_rows: list[dict],
    recent_flip_rows: list[dict],
) -> str:
    stats = density[['density', 'mean_abs_partial_corr']].describe()
    lines = [
        'You are analyzing a time-varying FX partial-correlation network over the '
        '7 major currency pairs. Each date is a graph: nodes are currency pairs, '
        'edges are pairs found conditionally dependent (via graphical lasso) that '
        'window, oriented where Granger causality found a significant lead-lag '
        'relationship.',
        '',
        f'Report date: {report_date}',
        f'Run parameters: {params}',
        '',
        'Full-history summary statistics for density and mean |partial correlation|:',
        stats.to_string(),
        '',
        'Most recent 5 dates (date, edge_count, density, mean_abs_partial_corr, '
        'directed, bidirected, undirected):',
        *[
            f'  {r["date"]}: edges={r["edge_count"]}, density={r["density"]:.4f}, '
            f'mean_abs_pcorr={r["mean_abs_partial_corr"]:.4f}, '
            f'directed={r["directed_edge_count"]}, bidirected={r["bidirected_edge_count"]}, '
            f'undirected={r["undirected_edge_count"]}'
            for r in recent_density_rows
        ],
        '',
        'Most recent direction changes (date, pair_i, pair_j, previous -> new):',
        *(
            [
                f'  {r["date"]}: {r["pair_i"]} / {r["pair_j"]}: '
                f'{r["previous_direction"]} -> {r["new_direction"]}'
                for r in recent_flip_rows
            ]
            or ['  (none)']
        ),
        '',
        'Write a brief (3-5 paragraph) qualitative summary interpreting this data '
        'for someone monitoring FX market structure: what the current network '
        'density and directionality suggest, how it compares to the historical '
        'distribution, and what the recent direction changes might indicate. Do '
        'not invent numbers not given above. Do not give trading advice.',
    ]
    return '\n'.join(lines)


def _llm_summary(prompt: str, model: str | None) -> str | None:
    resolved_model = model or _DEFAULT_MODEL
    api_base = os.environ.get('OLLAMA_API_BASE')
    api_key = os.environ.get('OLLAMA_API_KEY')
    try:
        completion = litellm.completion(
            model=resolved_model,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.2,
            **({'api_base': api_base} if api_base else {}),
            **({'api_key': api_key} if api_key else {}),
        )
        content = completion.choices[0].message.content
        return str(content) if content else None
    except Exception:
        return None


def generate_report(
    edges: pd.DataFrame,
    density: pd.DataFrame,
    flips: pd.DataFrame,
    output_path: Path,
    *,
    model: str | None = None,
    include_llm_summary: bool = True,
) -> None:
    report_date = density['date'].max()
    params = _run_params(edges)
    recent_density_rows = _recent_density_rows(density)
    recent_flip_rows = _recent_flip_rows(flips)

    llm_summary = None
    if include_llm_summary:
        prompt = _build_summary_prompt(
            report_date, params, density, recent_density_rows, recent_flip_rows
        )
        llm_summary = _llm_summary(prompt, model)

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
        llm_summary=llm_summary,
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
        edges, density, flips, output_path, model=model, include_llm_summary=include_llm_summary
    )
