from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path

import litellm
import pandas as pd

from fx_pcn.incremental import merge_incremental
from fx_pcn.network import pairs_from_edges

_DEFAULT_MODEL = os.environ.get('LLM_MODEL', 'ollama_chat/glm-5.2:cloud')

_RUN_PARAM_COLUMNS = [
    'window_days',
    'step_days',
    'min_observations',
    'max_lag',
    'fdr_alpha',
    'granularity',
    'network_name',
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

_BULLETS_TABLE_COLUMNS = [
    'date',
    *_RUN_PARAM_COLUMNS,
    'pairs',
    'model',
    'bullet_index',
    'bullet_text',
]

# The model is instructed to emit this exact heading on its own line, right
# after the narrative -- a plain-text delimiter rather than asking a local
# Ollama model for JSON/function-call output, which is more failure-prone
# than a fixed string it just has to echo back verbatim.
_TAKEAWAYS_HEADING = 'STRATEGIC TAKEAWAYS:'


def run_params(edges: pd.DataFrame) -> dict:
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
        'network_name': str(row['network_name']),
    }


def recent_density_rows(density: pd.DataFrame, n: int = 5) -> list[dict]:
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


def recent_flip_rows(flips: pd.DataFrame, n: int = 10) -> list[dict]:
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


def _build_prompt(
    report_date: datetime.date,
    params: dict,
    pairs: list[str],
    density: pd.DataFrame,
    recent_density: list[dict],
    recent_flips: list[dict],
) -> str:
    stats = density[['density', 'mean_abs_partial_corr']].describe()
    lines = [
        f'You are analyzing a time-varying FX partial-correlation network, '
        f'"{params["network_name"]}", over {len(pairs)} currency pairs '
        f'({", ".join(pairs)}). Each date is a graph: nodes are currency pairs, '
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
            for r in recent_density
        ],
        '',
        'Most recent direction changes (date, pair_i, pair_j, previous -> new):',
        *(
            [
                f'  {r["date"]}: {r["pair_i"]} / {r["pair_j"]}: '
                f'{r["previous_direction"]} -> {r["new_direction"]}'
                for r in recent_flips
            ]
            or ['  (none)']
        ),
        '',
        'Write a brief (3-5 paragraph) qualitative summary interpreting this data '
        'for someone monitoring FX market structure: what the current network '
        'density and directionality suggest, how it compares to the historical '
        'distribution, and what the recent direction changes might indicate. Do '
        'not invent numbers not given above.',
        '',
        f'Then, on its own line, write exactly the heading "{_TAKEAWAYS_HEADING}" '
        'followed by 3-6 bullet points (each on its own line, starting with "- "): '
        'diversification/hedging implications of the current density and '
        'correlation-strength regime, which relationships are worth actively '
        'monitoring given the recent direction changes, and what would confirm or '
        'invalidate this read going forward. Keep any actionable framing at the '
        'level of market structure and risk monitoring -- do not give specific '
        'trading advice (no buy/sell/position-sizing recommendations, no calls on '
        'individual trades).',
    ]
    return '\n'.join(lines)


def _call_llm(prompt: str, model: str | None) -> str | None:
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


def _parse_response(raw: str) -> tuple[str, list[str]]:
    """Split the LLM's raw response into narrative prose and a list of
    takeaway bullets, using `_TAKEAWAYS_HEADING` as the split point. Falls
    back to treating the whole response as narrative with no bullets if the
    model didn't echo the heading back -- degrades gracefully rather than
    raising, consistent with `_call_llm` already returning `None` on
    failure instead of raising."""
    if _TAKEAWAYS_HEADING not in raw:
        return raw.strip(), []
    narrative, _, rest = raw.partition(_TAKEAWAYS_HEADING)
    bullets = [
        line.strip().lstrip('-').strip()
        for line in rest.splitlines()
        if line.strip().startswith('-')
    ]
    return narrative.strip(), bullets


@dataclass(frozen=True)
class Summary:
    report_date: datetime.date
    narrative: str
    bullets: list[str]
    model: str
    params: dict
    pairs: list[str]


def generate_summary(
    edges: pd.DataFrame,
    density: pd.DataFrame,
    flips: pd.DataFrame,
    *,
    model: str | None = None,
) -> Summary | None:
    """The LLM's qualitative read of the current network, or `None` if the
    call failed or returned no content (see `_call_llm`) -- callers should
    treat that the same way `report.py` already treats a missing summary:
    skip the section/row rather than erroring."""
    report_date = density['date'].max()
    params = run_params(edges)
    pairs = pairs_from_edges(edges)
    prompt = _build_prompt(
        report_date, params, pairs, density, recent_density_rows(density), recent_flip_rows(flips)
    )
    raw = _call_llm(prompt, model)
    if raw is None:
        return None

    narrative, bullets = _parse_response(raw)
    return Summary(
        report_date=report_date,
        narrative=narrative,
        bullets=bullets,
        model=model or _DEFAULT_MODEL,
        params=params,
        pairs=pairs,
    )


def bullets_table(summary: Summary | None) -> pd.DataFrame:
    """One row per takeaway bullet, for `export-summary-rdf` to turn into
    `fxpcn:QualitativeSummaryRun` triples. Empty (but correctly-columned) if
    `summary` is `None` or produced no bullets. Column name is `date`. not
    `report_date`, to match `merge_incremental`'s hardcoded column name --
    this table accumulates across runs via `--append` the same way
    density/flips tables do, not overwritten each run.

    `pairs` (comma-joined, mirroring `network.build_edge_table`'s own edge-table
    column) rides along separately from `summary.params` -- not folded into
    `_RUN_PARAM_COLUMNS` -- so `export-summary-rdf` can recover the network's
    full pair vocabulary to check each bullet's text against for
    `fxpcn:mentionsPair`, without it also polluting the LLM prompt's
    already-explicit "Run parameters" line with a redundant pair list.
    """
    if summary is None or not summary.bullets:
        return pd.DataFrame(columns=_BULLETS_TABLE_COLUMNS)
    return pd.DataFrame(
        [
            {
                'date': summary.report_date,
                **summary.params,
                'pairs': ','.join(summary.pairs),
                'model': summary.model,
                'bullet_index': i,
                'bullet_text': bullet,
            }
            for i, bullet in enumerate(summary.bullets)
        ],
        columns=_BULLETS_TABLE_COLUMNS,
    )


def run(
    edges_path: Path,
    density_path: Path,
    flips_path: Path,
    output_path: Path,
    *,
    model: str | None = None,
    append: bool = False,
) -> pd.DataFrame:
    edges = pd.read_parquet(edges_path)
    density = pd.read_parquet(density_path)
    flips = pd.read_parquet(flips_path)

    fresh = bullets_table(generate_summary(edges, density, flips, model=model))

    if append and output_path.exists():
        existing = pd.read_parquet(output_path)
        # An empty `existing` (e.g. every prior LLM call failed) has no
        # `.max()` date to compare against -- `NaT`, against which every
        # comparison is False, which would silently drop `fresh` too.
        # Nothing to preserve in that case, so just keep `fresh` as-is.
        if not existing.empty:
            # Rows from before `pairs` existed on this table (or, per
            # `merge_incremental`'s plain `pd.concat`, rows appended back when
            # the fresh side didn't have it yet) carry a missing/NaN `pairs`
            # rather than a real comma-joined list. Left as-is, whichever row
            # `export-summary-rdf` happens to read first can be one of these,
            # and `str(nan).split(',')` -> `['nan']` blows up `_add_pairs`'s
            # `pair.split('/')`. Backfilled from this run's own edges the same
            # way `pipeline.run` backfills a legacy edges table's
            # `network_name`/`pairs` -- safe here for the same reason: this
            # output path is per-network, so every row in it (old or new) was
            # always built from the same pair universe.
            if 'pairs' not in existing.columns:
                existing = existing.assign(pairs=None)
            missing_pairs = existing['pairs'].isna()
            if missing_pairs.any():
                existing = existing.copy()
                existing.loc[missing_pairs, 'pairs'] = ','.join(pairs_from_edges(edges))
            fresh = merge_incremental(existing, fresh, last_date=existing['date'].max())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fresh.to_parquet(output_path, index=False)
    return fresh
