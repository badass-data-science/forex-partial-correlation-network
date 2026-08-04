# Our Heroine Wiretaps Seven Currency Pairs

### Building a Time-Varying Partial-Correlation Network with Granger-Causal Direction Over the Seven Major FX Pairs

Every supervillain empire runs on rumor control. Our heroine's currency pair henchmen — EUR/USD, GBP/USD, USD/JPY, USD/CHF, USD/CAD, AUD/USD, and NZD/USD, seven degenerates who have never once RSVP'd honestly to a staff meeting — move in suspicious lockstep some weeks and go completely silent on each other the next. She has long suspected an org chart hiding under the org chart: a shadow network of which pairs are actually coordinating with which, updated continuously, that no amount of glaring across the boardroom table was ever going to reveal by inspection. So she built a pipeline to extract it from the only thing the currency pairs can't fake in real time — how their returns actually move together, hour by hour, net of everyone else's excuses.

## What Is a Partial-Correlation Network, and Why Wouldn't Plain Correlation Do

Ordinary correlation is the henchman-relations equivalent of "USD/CAD and USD/JPY seem chummy lately" — true, unhelpful, and blind to the possibility that they're both just individually reporting to USD/CHF and only *look* close because they share a boss. Plain pairwise correlation cannot distinguish a real, direct alliance from one that's entirely mediated through a third pair. Every USD-quoted henchman in this empire shares a boss by construction, so this isn't a hypothetical edge case — it's the default failure mode.

What our heroine actually wants to know, for every pair of henchmen, is: are these two still talking once you account for what the other five are doing? That's a **partial correlation**, and the way to get all twenty-one pairwise answers at once, correctly, is **graphical lasso**. Fed the standardized hourly log returns of a trailing window (five days by default, at least sixty complete observations required, because it's hard to catch a conspiracy on a sample size of four), graphical lasso estimates a *sparse* inverse covariance matrix — an L1-penalized maximum-likelihood fit that drives an entry to exactly zero unless two henchmen are still dependent conditional on the other five. Zero means "this apparent alliance was actually just triangulated through someone else." Nonzero means a real edge, weighted by the partial correlation itself — sign and all, so the pipeline knows not just *that* two pairs are coordinating but whether they're moving together or working at cross-purposes.

This is also where the empire's henchmen make the job needlessly hard on themselves: because they're collinear — every one of them shares a USD leg with at least itself, and mostly with each other — scikit-learn's default automatic penalty search wanders into a near-singular regime and produces nonsense. The fix was an explicitly constrained cross-validation grid rather than trusting the library's instincts, which is as close as this document gets to a moral about not blindly trusting default settings when your suspects all know each other a little too well.

## Who Moved First: Granger Causality and the Problem of Symmetric Suspicion

A partial correlation is symmetric. It will confirm that EUR/USD and GBP/USD are conditionally entangled and then shrug when asked which one started it — which, for an org chart, is close to useless. Knowing two henchmen are coordinating without knowing who gives the orders is just a nicer-looking rumor.

So for every edge the lasso skeleton keeps, the pipeline runs pairwise **Granger causality** in both directions: does one henchman's recent lagged returns improve a prediction of the other's return, beyond what that other henchman's own history already explains — and does it work the other way too? Both directions get tested, because alliances in this empire are not always exclusive, and an honest org chart has to allow for the possibility that two lieutenants are quietly running each other.

With a nontrivial skeleton, a single window fires off a lot of these tests simultaneously, and calling all of them "significant" without correction is how you end up promoting henchmen based on coincidence. Every p-value from every directional test in a window gets pooled and corrected together with Benjamini-Hochberg FDR before anyone's loyalty gets labeled. What comes out the other side is one of four verdicts per edge: `i->j`, `j->i`, `i<->j` for the henchmen who are, infuriatingly, running each other simultaneously, and `undirected` for the ones caught coordinating with no discernible chain of command. That last category, incidentally, describes most of middle management in any organization, villainous or otherwise.

## Reading the Org Chart

Filtering the edge table to a single date gives that day's graph outright — nodes are the seven pairs, edges are whatever survived that window's lasso fit, and a pair with no row that day wasn't *missing data*, it was zeroed out on purpose. Two further computations turn the day-by-day graph into something readable at a glance rather than scanned row by row like a suspicious accountant. **Network density** — edge count over all twenty-one possible pairs, plus the mean absolute partial correlation and a tally of directed versus bidirected versus undirected edges — collapses a day's entire conspiracy into a single number, and a rising one over time is a plausible signal that the whole empire is losing its healthy internal distrust and starting to move as a bloc, which markets under stress reliably do. **Direction flips** ask the sharper question of whether any *specific* relationship just changed — an edge appearing, disappearing, reversing which pair leads, or a pair losing Granger significance without losing the edge entirely. `no_edge` and `undirected` are kept deliberately distinct here, because "these two stopped talking" and "these two are still talking but nobody's clearly in charge" are different kinds of organizational failure and our heroine would like her dashboards to reflect that nuance.

<img src="graph-2026-07-08.png" width="415" alt="FX partial-correlation network graph for 2026-07-08, rendered by fx-pcn's render-graph command" />

*An actual day's org chart — 2026-07-08. AUD/USD and NZD/USD are the strongest alliance in the room that day (+0.57, blue, thick); EUR/USD and USD/CHF are the one pair caught in open, bidirected conflict (-0.37, red, arrowheads on both ends). Everything else is either a plain undirected line — related, but nobody's provably in charge — or no line at all, meaning the lasso penalty decided the apparent relationship was fully explained by someone else.*

## What's Deliberately Not Here Yet

The default settings — five-day windows, daily steps, hourly bars, a four-hour max lag — target one specific regime: intraweek lead-lag, the kind of thing a London/New York session handoff produces. The same pipeline, pointed at different window/step/granularity/lag values, targets everything from intraday microstructure up through multi-year policy-cycle structure, and every one of those besides an event-conditioned regime anchored to the macro calendar is just a flag change, no code required. Two things, though, are not built yet:

- **An event-conditioned regime** — snapping windows to FOMC or NFP dates instead of stepping at a fixed interval.
- **A daily synthesis report** — one human-readable summary combining density and direction-flip output, instead of two parquet files an analyst has to correlate by hand.

Both are next on the list, which our heroine is choosing to announce publicly, mostly so that failing to build them becomes marginally more embarrassing than actually building them.

## Conclusion

Any villainous empire this size cannot be run on vibes and pairwise correlation, so this pipeline tells our heroine, refit daily, which of her seven currency pair henchmen are conditionally entangled net of the other five, which one is giving the orders when a relationship has a clear direction, and which ones are just quietly running each other in a loop that no org chart was ever going to capture.

# Code

Code implementing this project is available [here](https://github.com/badass-data-science/forex-partial-correlation-network).

# AI Use Statement

This post was initially drafted by Claude at the author's direction, working from this project's own README, AGENTS.md, and CHANGELOG.md, and then revised by a human before publication.

## Tags

- Data Science
- Python
- Forex
- Time Series
- Graphical Lasso
- Gaussian Graphical Models
- Granger Causality
- Network Analysis
- Quantitative Finance

