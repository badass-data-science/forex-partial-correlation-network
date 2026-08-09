# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this is

`fx-pcn` builds a time-varying partial-correlation network (an undirected
Gaussian graphical model, not a Bayesian network -- see the "Not actually a
Bayesian network" note in README.md if that distinction matters to you) with
Granger-causal edge direction, over a configurable set of FX pairs -- by
default the 7 major pairs (`EUR/USD`, `GBP/USD`, `USD/JPY`, `USD/CHF`,
`USD/CAD`, `AUD/USD`, `NZD/USD`), named `forex-network-seven-majors`
(`config.DEFAULT_NETWORK_NAME`). `run-pipeline --pairs ... --network-name
...` builds a differently-scoped network instead -- `--network-name` is
**required** whenever `--pairs` is given, so a custom pair set is never
allowed through unnamed (see README's "Custom pair sets"). Every downstream
command reads a network's identity (`network_name`, and the ordered `pairs`
list) back out of the edge table's own columns -- only `run-pipeline` itself
takes `--pairs`/`--network-name`. For each rolling window of H1 bars it:

1. Fetches wide-form price data from InfluxDB (`src/fx_pcn/influx_client.py`, `data.py`).
2. Computes log returns, masking any return that spans a forward-filled bar (`returns.py`).
3. Fits an undirected partial-correlation skeleton via graphical lasso (`network.fit_skeleton`).
4. Orients each skeleton edge with pairwise Granger causality, BH-FDR corrected
   across the window's tests (`network.infer_direction`).
5. Writes one row per `(date, pair_i, pair_j)` edge -- plus `network_name`/`pairs`
   -- to a parquet file (`pipeline.py`; `network.pairs_from_edges` recovers
   the ordered pair list back out for `density.py`/`direction_flips.py`).
6. Optionally renders the most recent date's graph as a PNG via Graphviz (`render_graph.py`).
7. Optionally exports the edge table (plus density/direction-flips) as RDF/Turtle
   (`rdf_export.py`) -- output only, nothing here loads it into a triple store.
   `EdgeObservation`/`NetworkSnapshot`/`DirectionFlip` URIs fold in a regime
   slug that now also includes the (slugified) `network_name` (not just
   reachable via `prov:wasGeneratedBy`), since multiple regimes' -- and,
   since `--pairs`/`--network-name`, differently-scoped networks' -- `.ttl`
   files get loaded into the same Neo4j graph via n10s and would otherwise
   collide on its unique-URI constraint. A new `fxpcn:Network` node per
   distinct `network_name` (`fxpcn:hasPair` per pair in that network,
   linked from its `prov:Activity` via `fxpcn:network`) lets a consumer
   resolve which pairs a given regime's Activity was actually built from.
   Includes a static
   currency -> region/institution vocabulary layer
   (`macro_vocabulary.py`; shared RDF namespace constants in `ontology.py`,
   split out to avoid a circular import between the two) designed to be
   extractable into its own repo later if it's ever reused outside fx-pcn.
   The LLM qualitative summary's takeaway bullets (see step 8's `generate-report`
   note) get their own, independent RDF export too (`export-summary-rdf`,
   `fxpcn:QualitativeSummaryRun` linked to the regime's `prov:Activity` via
   `prov:wasInformedBy`) -- kept separate from the numeric export so an
   LLM/Ollama outage never blocks it.
   As of 2026-08-06, that layer is actually registered with `graph-nexus`
   and linked in production (`/home/emily/output/graph-nexus`, outside this
   repo) -- see README's "The currency -> region/institution vocabulary
   layer" for status and `graph-nexus`'s own README/CHANGELOG for the full
   registration/linking story, including a manual override needed for
   `Bank of England`. If the export is regenerated and re-registered, the
   command used was:
   ```bash
   graph-nexus register-source fx-pcn \
     --repo-root /home/emily/output/graph-nexus \
     --ttl-path <path to the latest export-rdf output> \
     --concept-type skos:Concept \
     --label-property skos:prefLabel \
     --base-iri https://fx-pcn.local/kg/
   graph-nexus link fx-pcn --repo-root /home/emily/output/graph-nexus
   ```
8. Optionally runs all of the above (steps 1-6, plus RDF export, HTML
   report generation (which also writes the summary-bullets sidecar via
   `--bullets-output`/`--append-bullets`), and the summary RDF export, for
   regimes that need it) automatically every weekday
   at 6:30pm Eastern, for four of the five parameter regimes in README's
   "Other parameter regimes" table
   (`flows.py`, Prefect -- see README's "Automated daily runs (Prefect)"
   for the regime table, exact `REGIME_PARAMS` values, and the systemd
   unit). Follows the same shared-local-server-plus-per-project-`.serve()`
   convention as the sibling `ETL-forex-time-series-data` and
   `strategic-report-generator` repos -- don't invent a different pattern
   (e.g. a work pool/worker) without a reason. Granularity strings must
   match InfluxDB's actual tag values exactly (OANDA's real codes: `H1`,
   `H4`, `M15`, `D` -- no numeric suffix on `D`); a wrong string like `D1`
   fails silently (an empty query result, not an error) rather than
   raising, so don't assume a new regime works until it's actually been run
   once against real data.

All of this is driven through a single CLI, `src/fx_pcn/cli.py` (entry point `fx-pcn`,
also runnable as `python -m fx_pcn.cli`) with one subcommand per stage.

This repo doesn't populate InfluxDB itself -- that's a separate repo,
[`ETL-forex-time-series-data`](https://github.com/badass-data-science/ETL-forex-time-series-data),
which must be run first to get real data into the bucket `fx-pcn` reads from.

## Setup

This project's `.venv` is `uv`-managed (`pyvenv.cfg` shows `uv = ...`) — there is no
`pip` inside it. Use `uv`, not `pip`, for all dependency work here:

```bash
uv sync --extra dev
export INFLUXDB_URL=... INFLUXDB_TOKEN=... INFLUXDB_ORG=... INFLUXDB_BUCKET=...
```

`uv sync` alone omits the `dev` extra (drops `pytest`) — always pass `--extra dev`
in this repo. `render-graph` also needs the system Graphviz binaries with the
neato-family layout plugin installed (`libgvplugin-neato-layout8` on Debian/Ubuntu;
`dot -v` should list `circo`/`neato` under `layout`, not just `dot`).

InfluxDB credentials are required to run the pipeline against real data, but
are **not** required to run the test suite — tests build DataFrames in memory
and never touch `influx_client`.

## Common commands

```bash
pytest                                                  # run the test suite
ruff check .                                            # lint
ruff format .                                           # format (single quotes, 100-column lines)
mypy                                                     # type-check src/fx_pcn
fx-pcn run-pipeline --output output/edges.parquet        # full pipeline, full history since 2015
fx-pcn run-pipeline --output output/edges.parquet --days 30   # quick smoke test, last 30 days only
fx-pcn run-pipeline --output output/edges-eu.parquet --pairs EUR/USD USD/CHF GBP/USD \
  --network-name forex-network-european-majors             # custom pair set, name required
fx-pcn render-graph --input output/edges.parquet --output output/graph.png   # PNG of the most recent graph
```

Run `ruff check .`, `ruff format --check .`, and `mypy` before considering any change to
`src/fx_pcn` done -- all three are configured in `pyproject.toml` and expected to pass
clean. New functions need type hints; `mypy` is configured with `disallow_untyped_defs`
and will fail otherwise.

## Conventions to preserve

- `from __future__ import annotations` at the top of every module.
- Single quotes for strings, double quotes only when the string itself contains a `'`.
- Type-hinted function signatures; config defaults are pulled from `fx_pcn.config`
  rather than hardcoded, so window/lag/alpha parameters stay overridable.
- Docstrings explain the *why* behind a non-obvious choice (e.g. why a window is
  skipped, why FDR correction is batched per-window) — not a restatement of the signature.
- `fx_pcn.influx_client` is deliberately independent of the separate ETL repo's
  `InfluxDbTool` — don't reintroduce that coupling.
- New pipeline stages should stay pure/testable: take DataFrames in, return
  DataFrames out, with I/O (InfluxDB, parquet) isolated at the edges
  (`influx_client.py`, `pipeline.py`) the way `network.py` and `returns.py` already are.
- An edge table always describes exactly one network (one `network_name`,
  one `pairs` list) -- every downstream function (`density.compute_density_table`,
  `direction_flips.find_direction_flips` via `run()`, `rdf_export`'s
  `_single_regime_params`) assumes this and raises/errors on a table that
  mixes more than one. Don't add a code path that appends rows for a
  different `network_name` into an existing edge table (`pipeline.run`
  already guards `--append` against this) -- use a separate `--output` path
  per network instead.

## Tests

Tests favor synthetic data with a known ground truth over fixtures pulled from
InfluxDB — e.g. `test_fit_skeleton_recovers_a_strong_direct_relationship`
constructs a series where `B` is 90% driven by `A` and asserts the skeleton
recovers that edge. Follow this pattern for new statistical logic: construct
data where the correct answer is known analytically, don't just snapshot
output.

## Secrets

No `.env` file, by design — `INFLUXDB_URL`/`INFLUXDB_TOKEN`/`INFLUXDB_ORG`/`INFLUXDB_BUCKET`
must already be set in the calling shell's environment (see README.md). Don't
reintroduce a `.env`/`python-dotenv` loading path.

## Knowledge graph (graphify)

`graphify-out/graph.json` (plus `graph.html`, `GRAPH_REPORT.md`) is a
`graphify`-generated knowledge graph of this repo, tracked in git — see
README's "Repository knowledge graph (graphify)" section. If asked a
natural-language question about this codebase and `graphify-out/graph.json`
exists, prefer `graphify query "<question>"` over re-reading files from
scratch. `graphify-out/cache/`, `manifest.json`, `cost.json`, and `.graphify_*`
state files are gitignored and regenerated on each run -- don't hand-edit or
commit them.
