# fx-bn

A time-varying, Bayesian-network-style graph over the 7 major FX pairs
(`EUR/USD`, `GBP/USD`, `USD/JPY`, `USD/CHF`, `USD/CAD`, `AUD/USD`, `NZD/USD`).

For each day, the pipeline looks back over a trailing window of hourly bars and
asks two questions of every pair of currencies: *are these two conditionally
dependent right now, net of everyone else's influence?* and, if so, *which one
is leading the other?* The result is a graph — nodes are the 7 pairs, edges are
the relationships that window supports — and because it's refit on every date
in the series, that graph can be watched evolving over time.

## Installation

Requires Python >= 3.11.

```bash
pip install .
# or, for development (adds pytest):
pip install -e ".[dev]"
```

This installs the `fx-bn` command (a console-script entry point) along with the
`fx_bn` package. The project is a standard PEP 517/518 package (`hatchling`
backend) — nothing about it is specific to any particular installer.

> This repo's own `.venv` happens to be managed with [`uv`](https://docs.astral.sh/uv/)
> (`uv sync --extra dev`) rather than raw `pip`, but that's a local-development
> choice, not a requirement — plain `pip install` works from a clean checkout.

`render-graph` (below) additionally needs a system install of
[Graphviz](https://graphviz.org/) with the neato-family layout plugin available
— e.g. on Debian/Ubuntu, `apt install graphviz libgvplugin-neato-layout8`.
Check with `dot -v 2>&1 | grep layout`; it should list `circo`/`neato`/`fdp`,
not just `dot`.

## Configuration

The pipeline reads FX bar data from InfluxDB. These environment variables must
already be set in the shell you run `fx-bn` from — there is no `.env` file:

```
INFLUXDB_URL
INFLUXDB_TOKEN
INFLUXDB_ORG
INFLUXDB_BUCKET
```

e.g.:

```bash
export INFLUXDB_URL=https://...
export INFLUXDB_TOKEN=...
export INFLUXDB_ORG=...
export INFLUXDB_BUCKET=...
```

No credentials are needed just to run the test suite (`pytest`) — it exercises
the statistics on synthetic data and never touches InfluxDB.

## Running it

Everything goes through the `fx-bn` command (or `python -m fx_bn.cli`):

```bash
# Build the edge table (full history since 2015)
fx-bn run-pipeline --output output/edges.parquet

# Quick smoke test against the last 30 days only
fx-bn run-pipeline --output output/edges.parquet --days 30

# Later on: pull in whatever's new since the last run, without refitting history
fx-bn run-pipeline --output output/edges.parquet --append

# Render the most recent date's graph as a PNG
fx-bn render-graph --input output/edges.parquet --output output/graph.png
```

`run-pipeline` options (all optional except `--output`):

| Flag | Default | Meaning |
|---|---|---|
| `--output` | *(required)* | Parquet path to write the edge table to |
| `--days` | full history since 2015 | Only pull the last N days |
| `--window-days` | 5 | Trailing window size, in days |
| `--step-days` | 1 | Days between successive windows |
| `--min-observations` | 60 | Minimum complete-case bars required per window, else it's skipped |
| `--max-lag` | 4 | Max lag tested for Granger causality |
| `--fdr-alpha` | 0.05 | Benjamini-Hochberg FDR threshold for direction significance |
| `--granularity` | H1 | Bar granularity to fetch from InfluxDB |
| `--append` | off | Append new dates to an existing `--output` file instead of recomputing it from scratch |

Every one of these settings is also written back into the output as a column
(see [Output](#output) below), so edge tables produced with different settings
stay distinguishable — and safely concatenatable — after the fact.

`render-graph` takes `--input` (an edge-table parquet) and `--output` (a PNG
path), both required, and always renders the *most recent* date in that table.

### Incremental updates (`--append`)

Every row is keyed to a fixed trailing window ending on a specific date, so a
window that's already been fit and written never needs to be recomputed —
only dates after the existing table's most recent one do. `--append` uses
this: if `--output` already exists, it reads that file, finds its latest
`date`, fetches just enough trailing history (`--window-days` back from
there) to fit the windows after it, and appends only those new rows —
`--days` is ignored in this case, since the fetch start is derived from the
existing data instead. If `--output` doesn't exist yet, `--append` has no
effect and it's a normal full run.

This rewrites the whole output file on each call (there's no partial/in-place
parquet write), which is fine at this dataset's size — years of daily rows
across 7 pairs is still a small file. It assumes the source data doesn't get
revised after the fact; if InfluxDB's forward-filled bars could be backfilled
or corrected post hoc, previously-written rows wouldn't reflect that.

## How it works

For each rolling window of hourly bars, the pipeline runs three stages —
returns, then structure, then direction — and two further analyses derive
additional time series from the resulting edge table.

### 1. Returns

Everything operates on log returns, not raw prices:

```
r_t = log(close_t) - log(close_{t-1})
```

A return is set to `NaN` if either bar it spans was forward-filled (a
forward-filled bar is a carried-forward price with a zero return by
construction — treating it as real would inject spurious co-movement into
every pair that happened to be forward-filled at the same time, e.g. over a
market holiday).

### 2. Structure: which pairs are related at all? (graphical lasso)

Within each trailing window (default: 5 days of H1 bars, stepped daily, at
least 60 complete-case observations required), the 7 return series are
standardized (zero mean, unit variance — the next step is scale-sensitive) and
fed to **graphical lasso** ([`GraphicalLassoCV`](https://scikit-learn.org/stable/modules/generated/sklearn.covariance.GraphicalLassoCV.html)),
which estimates a *sparse* precision matrix (inverse covariance matrix) Θ by
solving an L1-penalized maximum-likelihood problem:

$$
\hat\Theta = \arg\max_{\Theta \succ 0} \; \log\det\Theta - \operatorname{tr}(S\Theta) - \alpha \lVert \Theta \rVert_1
$$

where *S* is the sample covariance of the window's standardized returns and
*α* is chosen by cross-validation over a constrained grid (the FX pairs are
collinear — they all share a USD leg — which pushes scikit-learn's default
automatic alpha search into a near-singular regime; the grid here,
`np.logspace(-2.2, 0.3, 30)`, was chosen to avoid that without cutting off the
true optimum).

The point of the L1 penalty: an entry Θ_ij is driven to exactly zero unless
pair *i* and pair *j* are still related once you condition on all 5 *other*
pairs. This is what makes the result a graph rather than a full 7×7 correlation
matrix — e.g. two USD-quoted pairs might look correlated only because they're
both driven by a third pair's USD move, in which case lasso zeroes out their
direct edge and leaves it explained through that third pair instead.

Every nonzero entry becomes an edge, weighted by the **partial correlation**:

$$
\rho_{ij} = \frac{-\Theta_{ij}}{\sqrt{\Theta_{ii}\,\Theta_{jj}}}
$$

### 3. Direction: which pair is leading? (Granger causality)

Partial correlation is symmetric — it says two pairs are related but not which
one moves first. For every edge the skeleton step kept, the pipeline runs a
pairwise **Granger causality** test in both directions using
[`grangercausalitytests`](https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.grangercausalitytests.html):
does adding *i*'s lagged returns (lags 1..`max_lag`) improve a linear
prediction of *j*'s return beyond what *j*'s own lags already explain, and
vice versa? Each direction produces one p-value (an SSR F-test, jointly across
all lags up to `max_lag` — not the minimum p-value across each lag tested
separately, which would stack multiple non-independent tests and inflate the
false-positive rate).

A single window with even a modest number of skeleton edges runs a lot of
these tests at once, so before calling anything "significant" the p-values
from *every* directional test in that window are pooled and corrected together
with **Benjamini-Hochberg FDR** (`statsmodels.stats.multitest.multipletests`,
`method='fdr_bh'`) at `--fdr-alpha` (default 0.05). Each edge is then labeled:

| Result | Label |
|---|---|
| Only i→j survives | `i->j` |
| Only j→i survives | `j->i` |
| Both survive | `i<->j` (bidirected) |
| Neither survives | `undirected` |

### 4. Derived analyses: density and direction flips

Two more computations run on the *finished* edge table rather than on raw
prices, turning the sequence of daily graphs into two additional time series.

**Network density** is a per-date summary of the graph as a whole — just an
aggregation over that date's edge rows:

$$
\text{density}_t = \frac{|E_t|}{21}, \qquad \overline{|\rho|}_t = \frac{1}{|E_t|}\sum_{(i,j) \in E_t} |\rho_{ij}|
$$

where $E_t$ is the set of edges present on date *t* and 21 = C(7,2) is every
possible pair among the 7 majors. Alongside these it also tallies how many of
that date's edges are `i->j`/`j->i`, `i<->j` (bidirected), or `undirected`.
Tracking this over time turns "is the graph getting denser/stronger" from a
mental exercise — scanning 20-odd rows a day by eye — into a single number per
date.

**Direction flips** answer a different question: not "how connected is the
graph today" but "did any specific relationship just change." A missing row
for a pair on some date means the lasso penalty zeroed it out (no edge), and
treating that as absent data would make disappearance invisible — so the full
21-pair grid is reconstructed for every date, with a fifth state, `no_edge`,
filled in wherever a pair has no row that date. Comparing each pair's state on
date *t* to its state on the previous date *actually present* in the table
(not necessarily the calendar day before, if `--step-days` skips days) flags
every pair whose state just changed: an edge appearing or disappearing, a
direction reversing, or a pair gaining or losing Granger significance.

### Why this combination

Graphical lasso answers "is there a direct relationship here, net of the other
5 pairs?" — a question ordinary pairwise correlation can't answer, since it
can't distinguish a real link from one mediated entirely through a third pair.
Granger causality then answers "which one moves first?" — a question partial
correlation, being symmetric, can't answer either. Running both, on the same
rolling window, one after the other, is what turns a static correlation
snapshot into a *directed, time-varying* network.

## Other parameter regimes

The CLI defaults (`--window-days 5 --step-days 1 --granularity H1 --max-lag 4`)
are tuned for one economically reasonable regime: intraweek lead-lag on hourly
bars, with a lag window short enough to plausibly capture session-overlap
effects (e.g. the London/New York handoff). It's not the only regime worth
running, though — the same pipeline, pointed at different window/step/
granularity/lag values, targets different underlying mechanisms and time
horizons:

| Regime | Granularity | Window | Step | Max lag | What it's meant to capture |
|---|---|---|---|---|---|
| **Default** | H1 | 5d | 1d | 4h | Intraweek lead-lag, e.g. session-overlap effects (London/NY) |
| **Intraday/microstructure** | M15 or M5 | 1–2d | 1d (or intraday step) | 8–16 bars (~2–4h) | Session handoffs within a single day (Asia→London→NY), order-flow-driven co-movement |
| **Macro/carry regime** | D1 | 30–90d | 5–7d | 1–5 days | Risk-on/risk-off comovement, carry-trade unwind dynamics — plays out over days, not hours |
| **Policy-cycle regime** | D1 (or weekly resample) | 180d+ | 30d | 5–10 days | Central-bank rate-cycle-driven structure — e.g. USD/JPY vs USD/CAD relationships shifting across a hiking/cutting cycle |
| **Event-conditioned** | H1 | short, anchored to calendar events | irregular (aligned to FOMC/NFP/ECB dates) | 1–4h | Whether the network's structure snaps to a different shape around scheduled macro releases |

The general tradeoff across all of these: shorter windows/granularity are more
responsive and can catch fast, session-driven relationships, but have fewer
observations per fit (weaker Granger power, a noisier lasso skeleton); longer
windows regain statistical power but smooth over regime changes, so a real
shift (say, a central bank pivot) only shows up gradually, blended with the
old regime.

All but the event-conditioned row are just different `--window-days`/
`--step-days`/`--granularity`/`--max-lag` values on the existing CLI — no code
changes needed. The event-conditioned regime would need genuinely new logic
(aligning windows to a macro calendar rather than stepping at a fixed interval).

## Output

`run-pipeline` writes one row per `(date, pair_i, pair_j)` edge that survived
that date's skeleton fit:

| Column | Meaning |
|---|---|
| `date` | The window's end date |
| `pair_i`, `pair_j` | The two FX pairs |
| `partial_corr` | Signed partial correlation from the graphical-lasso precision matrix |
| `granger_p_i_to_j`, `granger_p_j_to_i` | Raw (pre-FDR) Granger p-values in each direction |
| `direction` | `i->j`, `j->i`, `i<->j`, or `undirected` (after FDR correction) |
| `window_days`, `step_days`, `min_observations`, `max_lag`, `fdr_alpha`, `granularity` | The run's settings, carried on every row |

Filtering to a single `date` gives that day's graph: nodes are the 7 pairs,
edges are the rows for that date. Pairs with no row for a given date had their
partial correlation zeroed out by the lasso penalty that window — i.e., no
edge, not missing data.

## Derived analyses

Two more subcommands turn an edge-table parquet into a compact summary, for
spotting structure across the whole time series rather than reading one
date's graph at a time:

```bash
fx-bn compute-density --input output/edges.parquet --output output/density.parquet
fx-bn find-direction-flips --input output/edges.parquet --output output/flips.parquet
```

Both take `--input` (an edge-table parquet from `run-pipeline`) and `--output`
(required), and both support `--append`: like `run-pipeline --append`, if
`--output` already exists, only the dates after its most recent one are
computed and appended rather than rebuilding the whole table from scratch.

**`compute-density`** — one row per date, summarizing that day's graph as a
whole:

| Column | Meaning |
|---|---|
| `date` | The date being summarized |
| `edge_count` | Number of edges the lasso penalty kept that date |
| `density` | `edge_count` divided by 21 (all possible pairs among the 7 majors) |
| `mean_abs_partial_corr` | Mean `\|partial_corr\|` across that date's edges |
| `directed_edge_count`, `bidirected_edge_count`, `undirected_edge_count` | How many of that date's edges came out each way |

A densifying, strengthening graph over time is a plausible regime-shift or
rising-systemic-risk signal — markets tend to lose diversification (comove
more, and more strongly) under stress.

**`find-direction-flips`** — one row per date a given pair's relationship
*changed* from the date before it:

| Column | Meaning |
|---|---|
| `date` | The date the change is first seen on |
| `pair_i`, `pair_j` | The two FX pairs |
| `previous_direction`, `new_direction` | The state before and after — `i->j`, `j->i`, `i<->j`, `undirected`, or `no_edge` |

`no_edge` is distinct from `undirected`: `undirected` means the edge existed
that window but Granger causality found no significant direction, while
`no_edge` means the lasso penalty zeroed the pair out entirely — there was no
edge to test. A pair transitioning between any of these five states (e.g. an
edge disappearing, or reversing which pair leads) is a flip; the very first
date in the series can't flip, since there's nothing before it to compare to.

Both commands are pure functions of the edge table (`fx_bn.density.compute_density_table`,
`fx_bn.direction_flips.find_direction_flips`) wrapped in a thin file-reading/writing
`run()` — no InfluxDB access, so they're fast and fully covered by synthetic-data
tests. A planned next step is a daily report synthesizing both of these into a
single human-readable summary; not built yet.

## Project layout

```
src/fx_bn/
  cli.py               fx-bn command: subcommand definitions and argument parsing
  config.py             Pairs, granularity, and all statistical defaults
  influx_client.py       Minimal read-only InfluxDB client
  data.py                Wide-frame fetch across all 7 pairs
  returns.py             Log returns, forward-fill masking
  network.py             Graphical-lasso skeleton + Granger direction inference
  pipeline.py            Wires the above together, writes the edge table (run-pipeline)
  render_graph.py         Graphviz PNG rendering of the most recent graph (render-graph)
  density.py              Per-date network-density summary (compute-density)
  direction_flips.py       Detects edge-direction changes date over date (find-direction-flips)
  incremental.py           Shared "append only new dates" merge helper
tests/                    Statistical logic tested on synthetic, ground-truth data
```

## Testing

```bash
pytest
```

Tests favor synthetic data with a known ground truth over real fixtures — e.g.
constructing a series where `B` is 90% driven by `A` and asserting the
skeleton recovers that edge, or where `Y` is built to lag `X` and asserting
Granger direction picks it up correctly. No InfluxDB connection is needed.
