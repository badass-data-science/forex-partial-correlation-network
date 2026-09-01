# Findings

Research log for exploratory analyses run against fx-pcn's output. Distinct
from `README.md` (how the tool works) and `CHANGELOG.md` (code changes) --
this tracks what was *tried* and what it showed, including rejected ideas,
so they don't get re-tried from scratch later.

---

## 2026-08-31 -- Direction-flip bursts as a calendar-free event detector

**Idea:** rather than watching for single directed-edge flips, flag days/weeks
where an unusually large number of pairs flip simultaneously -- a
structural-shock signature that doesn't need an economic calendar to notice.
Two questions: does the network "see" scheduled events (FOMC), and does it
catch things a calendar would miss (volatility regime shifts, via VIX)?

Primary series used: `direction` + `density` output for
`window-days-60---step-days-7---min-observations-30---max-lag-3---fdr-alpha-0.05---granularity-D`
(606 weekly evaluation steps, 2015-02-16 to 2026-08-26). Burst = count of
directed-edge flips per evaluation step. Distribution: mean 3.39, std 1.92,
right-skewed, max 13. Unprompted top bursts (13, 13, 11, 10 flips) landed on
2020-03-16/03-23 (COVID crash), 2020-05-18, 2020-02-03 -- a good sign the
tail isn't noise.

### FOMC calendar -- REJECTED

Cross-checked burst dates against the FOMC statement/minutes release
schedule (`EDA/fomc.py`, pulled from
`vtasca/fed-statement-scraping/communications.csv`).

- Flip-count vs. distance-to-nearest-FOMC-release: Spearman r = -0.05,
  not significant.
- Flip-count at the evaluation step nearest each FOMC **statement** day
  (n=95): mean 3.63 vs. 3.39 overall -- permutation test p=0.18.
- High-burst steps (>=7 flips, top ~6%) sit within 3 days of a statement
  17.6% of the time vs. 15.7% baseline for all steps -- no meaningful gap.

**No detectable relationship.** The network does not "see" scheduled FOMC
events.

### FOMC Granger-causality sweep -- REJECTED (spurious, confirmed mechanism)

`EDA/Untitled1.ipynb` (unannotated) ran `grangercausalitytests` between each
FOMC dummy (`is_statement`, `is_minutes`, `is_statement_or_minutes`) and each
network metric (`density`/`edge_count`/`mean_abs_partial_corr`/
`directed_edge_count`/`bidirected_edge_count`/`undirected_edge_count`/
`direction_change_count`), on the
`window-days-5---step-days-1---min-observations-60---max-lag-4---granularity-H1`
config (daily-aggregated, 2992 obs, maxlag=10). The one result printed in the
notebook (`is_statement -> direction_change_count`) looked like a strong
signal: -log10(p) up to 9.91 at lag 6.

This was reproduced, then stress-tested:

- **Shuffled-label placebo** (200 trials, random days relabeled as
  "statement days," same count preserved): null max(-log10p) across lags
  tops out at 2.26. The real result (9.91) isn't an artifact of the
  regressor just being mostly zeros.
- **Reverse-direction placebo** (`direction_change_count -> is_statement`):
  FOMC dates are scheduled years in advance, so true causality in this
  direction is impossible. It should show nothing. Instead it was **more**
  significant than the forward direction (-log10(p) up to 12.35 at lag 10).
  This is the standard smoking gun for spurious Granger causality: both
  series are picking up FOMC's regular ~6-week meeting cadence as shared
  calendar structure, not a real dynamic relationship.
- **Full sweep, all 21 combinations** (3 FOMC vars x 7 metrics), forward vs.
  reverse max(-log10p):

  | FOMC var | metric | forward | reverse (placebo) |
  |---|---|---|---|
  | is_statement_or_minutes | direction_change_count | 27.0 | **36.7** |
  | is_minutes | direction_change_count | 14.9 | 12.2 |
  | is_statement | direction_change_count | 9.9 | 12.4 |
  | is_statement | density / edge_count | 4.7 | 5.7 |
  | is_statement_or_minutes | density / edge_count | 4.3 | 6.4 |
  | is_statement_or_minutes | mean_abs_partial_corr | 3.5 | 3.0 |
  | is_statement | undirected_edge_count | 2.9 | 3.8 |
  | is_statement | mean_abs_partial_corr | 2.7 | 3.8 |
  | (remaining 13 combos) | -- | <2 | <2 |

  (`density` and `edge_count` give identical results everywhere -- density
  is just edge_count / 21 possible edges, a linear rescaling, and Granger
  p-values are invariant to that.) Every combination with real forward
  significance has a comparable-or-larger reverse value. One exception
  (`is_minutes` vs. `mean_abs_partial_corr`: forward 1.75, reverse 0.15) is
  weak (p~=0.018) and expected by chance alone across 21 comparisons.

**Conclusion: none of the FOMC-side Granger results in the notebook are
trustworthy.** All share the same periodicity confound as the one result
that had been inspected. Do not reuse `is_statement`/`is_minutes` dummies
as a Granger regressor against these network metrics without controlling
for the confound (e.g. deseasonalizing, or testing against a matched-cadence
placebo calendar) -- the raw test will produce large but meaningless
p-values by construction.

### VIX co-occurrence -- REAL, but tail-only

Same 606-step weekly series, `^VIX` daily close (yfinance) as-of each
evaluation date.

- Overall: Spearman r = 0.055 (p=0.18, not significant) for flip-count vs.
  VIX level; r = 0.012 (p=0.77) for flip-count vs. week-over-week VIX % chg.
  Flat across the bottom 3 VIX-level quartiles (mean flip count 3.1-3.3).
- High-burst steps (>=7 flips) have significantly higher VIX than the rest:
  median 22 vs. 16 (Mann-Whitney p=0.0007), **survives dropping the two
  COVID weeks** (p=0.0035, medians 21 vs. 16).

**Read:** elevated VIX looks necessary but not sufficient for a burst --
most high-VIX weeks don't produce one, but extreme-burst weeks reliably
occur during elevated-vol regimes rather than calm ones. Narrower than a
general "vol event detector," but a real, outlier-robust effect.

### VIX lead/lag -- REAL, but wrong direction for "early warning" framing

Bidirectional Granger causality, `flip_count` vs. `log(VIX level)`, same
weekly series (both pass ADF stationarity), maxlag=10 weeks.

- **VIX -> flip_count**: significant at every lag 1-10, strongest at lag 2
  (p=6e-4, -log10p=3.22), stays under p=0.05 through lag 10.
- **flip_count -> VIX**: flat, max -log10p=0.33 across all lags. No signal.
- **Circular-shift placebo** (200 trials, shifts VIX by a random offset,
  preserving VIX's own autocorrelation but randomizing its alignment to
  flip_count): null max(-log10p) tops out at 2.70, 95th pctile 2.09. The
  real result (3.22) beats every trial -- empirical p<0.005. This is the
  asymmetric, placebo-surviving pattern the FOMC tests above lacked.

**Read:** VIX genuinely leads burst behavior by 1-10 weeks, not the reverse.
That means fx-pcn bursts are a **lagging/confirming** signal of a volatility
regime already visible in VIX, not a novel early-warning detector -- if VIX
already tells you stress is building weeks before a burst shows up, watching
VIX directly gives an earlier warning than waiting on the network. Effect
sizes here are real but modest (p in the 1e-3-1e-2 range across lags), not
dramatic like the (spurious) FOMC numbers above.

### Net verdict on the burst-detector idea

- Not a scheduled-event detector (FOMC: rejected, mechanism confirmed).
- Not a novel early-warning signal (VIX already leads it).
- Is a real, placebo-surviving **confirming/lagging indicator** of broad
  volatility regime, specifically at the extreme tail of burst activity.
  Possible future use: a secondary confirmation signal on top of VIX,
  rather than a standalone trigger -- untested.

**Cross-reference:** the original strategy-idea version of this thread
(direction flips as a trading signal) was already rejected in
`project_fx_pcn_lead_lag_strategy_2026_08_30` (Claude memory) -- that was
about trading on flips directly, not about the flips-as-monitor framing
tested here.
