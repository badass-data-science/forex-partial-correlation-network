# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `run-pipeline --pairs`/`--network-name`: build the network from any set of
  currency pairs, not just the default 7 majors (`config.DEFAULT_NETWORK_NAME`,
  `'forex-network-seven-majors'`). `--network-name` is **required** whenever
  `--pairs` is given (enforced in `cli.main`, before InfluxDB is ever hit) --
  a custom pair set is never allowed to pass through unnamed, so it can't get
  silently conflated with another network downstream. `--network-name` alone
  (without `--pairs`) is also allowed, to rename the default network without
  changing its pair set.
  - `network_name` and `pairs` (the ordered pair list, comma-joined) are now
    columns on every edge-table row, stamped by `network.build_edge_table`
    the same way `window_days`/`granularity`/etc. already are.
    `network.pairs_from_edges` recovers the ordered list back out for
    consumers that need the network's *full* pair universe, not just
    whichever pairs happen to appear in `pair_i`/`pair_j` on a given date --
    `density.compute_density_table`'s max-possible-edges denominator (no
    longer a fixed `C(7,2)=21` constant) and `direction_flips.run`'s
    complete `no_edge` grid both need this, since a pair the lasso penalty
    zeroes out on *every* date never otherwise appears in either column.
    Only `run-pipeline` itself takes `--pairs`/`--network-name`; every other
    command (`compute-density`, `find-direction-flips`, `generate-report`,
    `export-rdf`) reads a network's identity back out of the edge table
    it's given.
  - `pipeline.run --append` now refuses to append rows for one
    `--network-name` into an `--output` file already holding a different
    one, rather than silently mixing two networks' rows into a table every
    downstream consumer assumes describes exactly one.
  - `export-rdf`: new `fxpcn:Network` node per distinct `network_name`
    (`kg:network/<slugified-name>`, `fxpcn:label`, one `fxpcn:hasPair` per
    pair in that network -- including a pair with zero surviving edges,
    read from the edge table's `pairs` column rather than inferred from
    `pair_i`/`pair_j`), linked from its `prov:Activity` via `fxpcn:network`/
    `fxpcn:networkName`. `network_name` joined the tuple `prov:Activity` and
    every `EdgeObservation`/`NetworkSnapshot`/`DirectionFlip`/
    `QualitativeSummaryRun` URI's regime slug is keyed by (alongside
    `window_days`/`step_days`/etc.), for the same n10s unique-URI-collision
    reason the regime slug already existed -- two differently-scoped
    networks under an otherwise identical regime need to stay
    distinguishable once loaded into the same Neo4j graph, same as two
    regimes already did.
  - `generate-report`: the HTML report now shows the network's name and
    pair list in the front matter and title, and the "About this report"
    explainer's pair count/"all possible pairings" math is now derived from
    the network's own pairs rather than hardcoded to "7 majors"/"21 total".
    `fx_pcn.summary`'s LLM prompt likewise names the network and its pairs
    instead of assuming "the 7 major currency pairs".

### Fixed
- `run-pipeline --append`: the network-name mismatch guard above crashed
  with `KeyError('network_name')` against any edge-table parquet written
  before this feature existed (no `network_name`/`pairs` columns at all) --
  broke the scheduled `flows.py` `--append` runs against real production
  output on first deploy. `pipeline.run` now backfills a legacy file as the
  default 7-majors network (`config.DEFAULT_NETWORK_NAME`/`config.PAIRS`) in
  memory the first time `--append` touches it, then persists the migrated
  schema on the normal full-table rewrite -- a straight migration, not a
  guess, since every edge table written before this feature always was the
  7-majors network.

### Added
- `generate-summary`/`export-summary-rdf`: the LLM qualitative summary's
  strategic takeaways are now also available as RDF (`fx_pcn.summary`, new
  `fxpcn:QualitativeSummaryRun`/`fxpcn:takeawayBullet`/`fxpcn:llmModel`
  terms). The prompt now closes with a fixed `STRATEGIC TAKEAWAYS:` heading
  followed by bullet lines, parsed out of the response and rendered both as
  an HTML bullet list (`report.html.j2`'s "Strategic takeaways") and as
  one-bullet-per-triple `fxpcn:takeawayBullet` literals. Kept as a second,
  independent `.ttl` file rather than folded into `export-rdf`'s output --
  the numeric graph must stay exportable even when the LLM/Ollama is down,
  so it can't depend on this step succeeding. The two files stay joinable
  once both are loaded into the same Neo4j graph because both compute the
  identical `prov:Activity` URI for a given regime
  (`fxpcn:QualitativeSummaryRun` links to it via `prov:wasInformedBy`, not
  `wasGeneratedBy` -- correct PROV-O usage for "used output from," and a way
  to filter LLM opinion out of hard numeric fact by `rdf:type` alone).
  `generate-report --bullets-output`/`--append-bullets` write/accumulate the
  underlying bullets parquet (one row per bullet per report date,
  accumulated the same way `compute-density`/`find-direction-flips` tables
  are, not overwritten each run) from the same LLM call the HTML narrative
  already makes -- not a second, potentially inconsistent one. `fx_pcn.flows`:
  `_generate_report_task` now also writes this sidecar, and a new
  `_export_summary_rdf_task` runs after it, independent of the existing
  `_export_rdf_task`.

### Fixed
- `export-rdf`: `EdgeObservation`/`NetworkSnapshot`/`DirectionFlip` URIs were
  keyed only by `(date, pair_i, pair_j)` or `(date)`, with the parameter
  regime reachable only via `prov:wasGeneratedBy` on a separate
  `prov:Activity` node. Different regimes' `.ttl` exports get loaded into
  the same Neo4j graph via n10s (see the ops runbook's
  `load-ttl-files-into-Neo4j.cypher`), which enforces a unique-URI
  constraint -- two regimes observing the same date/pair would collide and
  silently overwrite each other's properties. Fixed by folding a regime
  slug into all three URI schemes; `build_graph()` now raises `ValueError`
  if `density`/`flips` are passed alongside an `edges` table spanning more
  than one regime, since those tables carry no regime column of their own
  to attribute against.

### Added
- `fx_pcn.flows`: `regime_pipeline_flow` now also runs `generate-report` as
  the last step of the artifact chain (after `export-rdf`), writing
  `report---window-days-N---...---granularity-X.html` alongside the other
  regime artifacts via the existing `regime_output_path()` naming
  convention. Gets its own `retries=3` policy like `_run_pipeline_task`,
  since it also makes a network call (the LLM summary), not because it
  touches InfluxDB.
- `graphify-out/graph.html`, `graphify-out/GRAPH_REPORT.md`, and
  `graphify-out/graph.json`: a `graphify`-generated knowledge graph of this
  repo itself (entities/relationships from both AST-parsed code and
  LLM-extracted docs, with community detection), committed for browsing and
  agent querying. Everything else `graphify` writes to `graphify-out/`
  (`cache/`, `manifest.json`, `cost.json`, `.graphify_*` interpreter/state
  files) is gitignored as regenerable working state.
- `generate-report`: renders a single self-contained HTML report
  (`fx_pcn.report`) combining the most recent date's network graph -- an
  interactive D3 v7 force-directed layout, vendored inline rather than a CDN
  link so the report stays offline-renderable, with the same color/width/arrow
  encoding as `render-graph`'s Graphviz output -- an "About this report"
  explainer of the underlying measurements (partial correlation, Granger
  causality, density, mean |partial corr|, direction), a table of contents,
  the last 5 `compute-density` rows and last 10 `find-direction-flips` rows
  (both sorted ascending by date), a full per-edge detail table (every edge
  for the date, not just ones above the graph's own label threshold),
  distribution/trend `matplotlib` plots each marked with that metric's most
  recent value, and an LLM-written qualitative summary with a warning
  immediately above it (not at the document's end) noting only that section
  is LLM-generated. Follows `export-rdf`'s `--edges`-required /
  `--density`+`--flips`-optional flag pattern, and
  `strategic-report-generator`'s Jinja2 (`autoescape=True`,
  `base.html.j2`/`report.html.j2` split) templating strategy and
  `LLM_MODEL`/`OLLAMA_API_BASE`/`OLLAMA_API_KEY` `litellm` env-var setup. New
  deps: `matplotlib`, `jinja2`, `litellm`.
- `fx_pcn.flows`: Prefect scheduling for four of the five parameter regimes
  in README's "Other parameter regimes" table (all but event-conditioned),
  running the full artifact chain (`run-pipeline --append` -> `compute-density
  --append` -> `find-direction-flips --append` -> `render-graph` ->
  `export-rdf`) every weekday at 6:30pm Eastern via
  `CronSchedule(timezone="America/New_York")` -- DST-safe, unlike a
  hand-computed fixed-UTC cron. Each regime is an independent deployment of
  one parameterized flow, not one flow looping over regimes. Follows the
  same shared-local-Prefect-server-plus-per-project-`.serve()`-process
  convention as `ETL-forex-time-series-data`/`strategic-report-generator`.
  Output filenames use the existing `<artifact>---window-days-N---...`
  convention via a new `regime_output_path()` helper.
- `export-rdf` now also mints a static currency -> region/institution
  vocabulary layer (`fx_pcn.macro_vocabulary`): `fxpcn:Currency` per
  currency code, linked from each `CurrencyPair` via `fxpcn:baseCurrency`/
  `fxpcn:quoteCurrency`, and linked to `skos:Concept`/`skos:prefLabel`
  region (always) and institution (only EUR/USD/GBP/JPY, where a real
  concept-vocabulary match was confirmed) nodes -- reusing SKOS directly,
  unlike the rest of the `fxpcn:` ontology, so this layer could be
  registered with `graph-nexus` with no conversion step. Shared RDF
  namespace constants moved to a new `fx_pcn.ontology` module to avoid a
  circular import; the module is deliberately written to have no
  fx-pcn-specific dependencies beyond that, in case it's split into its own
  repo later.
- `export-rdf`: turns an edge table (plus optional `compute-density`/
  `find-direction-flips` output) into a single RDF/Turtle file
  (`fx_pcn.rdf_export`), output-only -- no triple-store loading. Mints a
  small custom `fxpcn:` ontology (`CurrencyPair`, `EdgeObservation`,
  `NetworkSnapshot`, `DirectionFlip`), reusing PROV-O for provenance
  (`prov:Activity`/`prov:wasGeneratedBy` per distinct run-parameter
  combination) rather than inventing that part too. `fxpcn:source`/
  `fxpcn:target` are only asserted on genuinely directed edges; bidirected
  and undirected edges rely on the always-present, unordered `fxpcn:pairA`/
  `fxpcn:pairB` instead.

### Fixed
- Suppressed a numpy `RuntimeWarning` ("invalid value encountered in
  subtract") that could leak from `fit_skeleton` during `run-pipeline`.
  Root-caused by hand against a real offending window (2015-01-11): the
  input going into `GraphicalLassoCV.fit()` had no NaN/inf/zero-variance
  columns, and `precision_` came out fully finite regardless -- the warning
  is a side effect of the solver's internal coordinate descent not
  converging within its iteration cap on a numerically stiff (collinear)
  window, the same root cause as the `ConvergenceWarning` already suppressed
  alongside it, not a sign of corrupted output.

### Added
- GitHub Actions CI (`.github/workflows/ci.yml`): runs `ruff check`,
  `ruff format --check`, `mypy`, and `pytest` on every push to `main` and
  every pull request, across Python 3.11 and 3.13. README badge added.
- `ruff` (lint + format) and `mypy` (type-checking, `disallow_untyped_defs`) as
  dev dependencies, configured in `pyproject.toml`. `src/fx_pcn` is fully
  type-hinted and passes both clean.
- Graphviz-based PNG rendering of the most recent graph in an edge-table
  parquet (`fx_pcn.render_graph`), force-directed `neato` layout with curved
  splines, edges colored by partial-correlation sign and weighted by magnitude.
- Pipeline parameters (window/step/min-observations/max-lag/FDR-alpha/granularity)
  are now CLI-overridable and recorded as columns in the edge table, so runs
  with differing settings stay distinguishable.
- `run-pipeline --append`: incrementally adds new dates to an existing edge
  table instead of recomputing its full history, since already-fit windows
  never need to be refit.
- `compute-density`: derives a per-date network-density time series (edge
  count, density, mean |partial_corr|, directed/bidirected/undirected counts)
  from an edge-table parquet.
- `find-direction-flips`: derives every date a pair's edge relationship
  changed from the date before it, including transitions to/from having no
  edge at all (distinct from `undirected`). Both new subcommands support
  `--append`.

### Changed
- Replaced `scripts/run_pipeline.py` and `scripts/render_graph.py` with a
  single `fx-pcn` CLI (`src/fx_pcn/cli.py`, subcommands `run-pipeline` and
  `render-graph`).
- Extracted the `--append` merge logic (`run-pipeline` originally) into a
  shared `fx_pcn.incremental.merge_incremental`, reused by `compute-density`
  and `find-direction-flips`.
- Renamed the project from `fx-bn` to `fx-pcn` (package, `src/fx_bn` ->
  `src/fx_pcn`, CLI command, PyPI-style metadata) -- "Bayesian-network-style"
  turned out not to accurately describe the method (see the "Not actually a
  Bayesian network" note in README.md); `fx-pcn` ("partial-correlation
  network") names the actual graph object instead.
- Renamed the GitHub repo (and local project directory) from
  `forex-bayesian-belief-networks` to `forex-partial-correlation-network`,
  for the same reason. GitHub redirects the old repo URL automatically.

## [0.1.0] - 2026-08-03

### Added
- Initial pipeline: InfluxDB client and wide-frame fetch for the 7 major FX pairs.
- Log-return computation that masks returns spanning forward-filled bars.
- Rolling-window partial-correlation skeleton via graphical lasso (`GraphicalLassoCV`).
- Edge direction inference via pairwise Granger causality with BH-FDR correction.
- `scripts/run_pipeline.py` CLI, with `--days` for a quick recent-history smoke test.
- Test suite covering rolling windows, skeleton recovery, and direction inference on synthetic data.
