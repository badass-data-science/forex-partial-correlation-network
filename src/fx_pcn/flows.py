"""Daily Prefect scheduling for all four documented parameter regimes (see
README's "Other parameter regimes" table). Each regime is an independent
deployment of the same flow rather than one flow looping over regimes, so
one regime failing or being re-run doesn't touch the others' schedules or
runs.

Run this as its own long-running process (its own systemd unit -- see
README for the exact unit file), registered against the same local Prefect
server every other project in this ecosystem shares
(`PREFECT_API_URL=http://localhost:4200/api`), not a Prefect Cloud account:

    python -m fx_pcn.flows

Trigger a one-off run without waiting for the schedule:

    prefect deployment run 'fx-pcn-regime-pipeline/fx-pcn-default'
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from prefect import flow, get_run_logger, task

from fx_pcn import config, density, direction_flips, pipeline, rdf_export, render_graph, report

DEFAULT_OUTPUT_DIR = Path.home() / 'output' / 'forex-partial-correlation-network'

# Every weekday at 6:30pm Eastern. `timezone=` (not a hand-computed UTC
# offset) so this stays correct across the EST/EDT switch -- a fixed-UTC
# cron would be off by an hour for half the year.
_SCHEDULE_CRON = '30 18 * * 1-5'
_SCHEDULE_TIMEZONE = 'America/New_York'


class RegimeParams(TypedDict):
    granularity: str
    window_days: int
    step_days: int
    max_lag: int
    min_observations: int
    fdr_alpha: float


# The README's "Other parameter regimes" table gives ranges, not exact
# values -- these pick one point in each range. `min_observations` keeps
# roughly the same completeness fraction as `default` (~60/120, half a
# window's max possible bars); `max_lag` stays in bar-count terms
# consistent with each row's stated time units (a daily bar is one day, so
# "N days" of lag there is max_lag=N directly). `intraday`'s step stays
# daily, not intraday -- `rolling_windows`/`--step-days` only support
# whole-day steps today, so a true intraday-step regime is out of scope
# here, not an oversight.
#
# Granularity is `'D'`, not `'D1'` -- OANDA's actual granularity codes have
# no numeric suffix on D/W/M (only sub-daily codes do, e.g. H1/H4/M15), and
# that's what's actually stored in InfluxDB. Confirmed by hand: querying
# `'D1'` silently returned zero rows (no such tag value exists) rather than
# erroring, which is what surfaced this in the first place.
REGIME_PARAMS: dict[str, RegimeParams] = {
    'default': {
        'granularity': config.GRANULARITY,
        'window_days': config.WINDOW_DAYS,
        'step_days': config.STEP_DAYS,
        'max_lag': config.MAX_LAG,
        'min_observations': config.MIN_OBSERVATIONS_PER_WINDOW,
        'fdr_alpha': config.FDR_ALPHA,
    },
    'intraday': {
        'granularity': 'M15',
        'window_days': 2,
        'step_days': 1,
        'max_lag': 12,
        'min_observations': 96,
        'fdr_alpha': 0.05,
    },
    'macro': {
        'granularity': 'D',
        'window_days': 60,
        'step_days': 7,
        'max_lag': 3,
        'min_observations': 30,
        'fdr_alpha': 0.05,
    },
    'policy': {
        'granularity': 'D',
        'window_days': 180,
        'step_days': 30,
        'max_lag': 7,
        'min_observations': 90,
        'fdr_alpha': 0.05,
    },
}


def regime_output_path(
    output_dir: Path,
    artifact: str,
    *,
    window_days: int,
    step_days: int,
    min_observations: int,
    max_lag: int,
    fdr_alpha: float,
    granularity: str,
    ext: str,
) -> Path:
    """The `<artifact>---window-days-N---step-days-N---min-observations-N---
    max-lag-N---fdr-alpha-N---granularity-X.<ext>` naming convention already
    in use for every file in `~/output/forex-partial-correlation-network` --
    keeps every artifact traceable to the exact regime that produced it
    without needing to open the file.
    """
    name = (
        f'{artifact}'
        f'---window-days-{window_days}'
        f'---step-days-{step_days}'
        f'---min-observations-{min_observations}'
        f'---max-lag-{max_lag}'
        f'---fdr-alpha-{fdr_alpha}'
        f'---granularity-{granularity}'
        f'.{ext}'
    )
    return output_dir / name


@task(retries=3, retry_delay_seconds=30)
def _run_pipeline_task(output_path: Path, params: RegimeParams) -> None:
    """This task hits InfluxDB; `_generate_report_task` below is the only
    other one with a retry policy, for the same reason (a network call --
    the LLM summary -- rather than InfluxDB). The remaining tasks are
    local/fast and don't need one."""
    logger = get_run_logger()
    edges = pipeline.run(
        output_path=output_path,
        window_days=params['window_days'],
        step_days=params['step_days'],
        min_observations=params['min_observations'],
        max_lag=params['max_lag'],
        fdr_alpha=params['fdr_alpha'],
        granularity=params['granularity'],
        append=True,
    )
    logger.info(
        'run-pipeline: %d edges across %d dates -> %s',
        len(edges),
        edges['date'].nunique(),
        output_path,
    )


@task
def _compute_density_task(input_path: Path, output_path: Path) -> None:
    density.run(input_path, output_path, append=True)


@task
def _find_direction_flips_task(input_path: Path, output_path: Path) -> None:
    direction_flips.run(input_path, output_path, append=True)


@task
def _render_graph_task(input_path: Path, output_path: Path) -> None:
    render_graph.render(input_path, output_path)


@task
def _export_rdf_task(
    edges_path: Path, output_path: Path, density_path: Path, flips_path: Path
) -> None:
    rdf_export.run(edges_path, output_path, density_path=density_path, flips_path=flips_path)


@task(retries=3, retry_delay_seconds=30)
def _generate_report_task(
    edges_path: Path, output_path: Path, density_path: Path, flips_path: Path
) -> None:
    report.run(edges_path, output_path, density_path=density_path, flips_path=flips_path)


@flow(name='fx-pcn-regime-pipeline', log_prints=True)
def regime_pipeline_flow(regime: str, output_dir: str = str(DEFAULT_OUTPUT_DIR)) -> None:
    """Runs the full artifact chain (edges -> density -> direction flips ->
    graph PNG -> RDF export -> HTML report) for one named entry in
    `REGIME_PARAMS`, `--append`ing each parquet rather than rebuilding it
    from scratch."""
    params = REGIME_PARAMS[regime]
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def path_for(artifact: str, ext: str) -> Path:
        return regime_output_path(out_dir, artifact, ext=ext, **params)

    edges_path = path_for('parameters', 'parquet')
    density_path = path_for('density', 'parquet')
    flips_path = path_for('direction', 'parquet')
    graph_path = path_for('graph-most-recent-window', 'png')
    rdf_path = path_for('RDF', 'ttl')
    report_path = path_for('report', 'html')

    _run_pipeline_task(edges_path, params)
    _compute_density_task(edges_path, density_path)
    _find_direction_flips_task(edges_path, flips_path)
    _render_graph_task(edges_path, graph_path)
    _export_rdf_task(edges_path, rdf_path, density_path, flips_path)
    _generate_report_task(edges_path, report_path, density_path, flips_path)


if __name__ == '__main__':
    from typing import cast

    from prefect import serve
    from prefect.client.schemas.schedules import CronSchedule
    from prefect.deployments.runner import RunnerDeployment

    # to_deployment()'s return type is annotated as a union with a
    # Coroutine to cover a possible async call path -- called synchronously
    # here (no `await`), it always returns a RunnerDeployment.
    deployments = [
        cast(
            RunnerDeployment,
            regime_pipeline_flow.to_deployment(
                name=f'fx-pcn-{regime}',
                parameters={'regime': regime},
                schedules=[CronSchedule(cron=_SCHEDULE_CRON, timezone=_SCHEDULE_TIMEZONE)],
            ),
        )
        for regime in REGIME_PARAMS
    ]
    serve(*deployments)
