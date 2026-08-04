# Our Heroine Wiretaps Seven Currency Pairs

### Building a Time-Varying Partial-Correlation Network with Granger-Causal Direction Over the Seven Major FX Pairs — And Owning Up to a Naming Mistake in Front of the Entire Henchman Roster

Every supervillain empire runs on rumor control. Our heroine's currency henchmen — EUR/USD, GBP/USD, USD/JPY, USD/CHF, USD/CAD, AUD/USD, and NZD/USD, seven degenerates who have never once RSVP'd honestly to a staff meeting — move in suspicious lockstep some weeks and go completely silent on each other the next. She has long suspected an org chart hiding under the org chart: a shadow network of who's actually coordinating with whom, updated continuously, that no amount of glaring across the boardroom table was ever going to reveal by inspection. So she built a pipeline to extract it from the only thing henchmen can't fake in real time — how their returns actually move together, hour by hour, net of everyone else's excuses.

She also, in an act of administrative hubris she is choosing to narrate rather than bury, spent several months calling the resulting org chart a "Bayesian network." It is not a Bayesian network. More on that humiliation below, after the part where the pipeline actually works.

## What Is a Partial-Correlation Network, and Why Wouldn't Plain Correlation Do

Ordinary correlation is the henchman-relations equivalent of "USD/CAD and USD/JPY seem chummy lately" — true, unhelpful, and blind to the possibility that they're both just individually reporting to USD/CHF and only *look* close because they share a boss. Plain pairwise correlation cannot distinguish a real, direct alliance from one that's entirely mediated through a third pair. Every USD-quoted henchman in this empire shares a boss by construction, so this isn't a hypothetical edge case — it's the default failure mode.

What our heroine actually wants to know, for every pair of henchmen, is: are these two still talking once you account for what the other five are doing? That's a **partial correlation**, and the way to get all twenty-one pairwise answers at once, correctly, is **graphical lasso**. Fed the standardized hourly log returns of a trailing window (five days by default, at least sixty complete observations required, because it's hard to catch a conspiracy on a sample size of four), graphical lasso estimates a *sparse* inverse covariance matrix — an L1-penalized maximum-likelihood fit that drives an entry to exactly zero unless two henchmen are still dependent conditional on the other five. Zero means "this apparent alliance was actually just triangulated through someone else." Nonzero means a real edge, weighted by the partial correlation itself — sign and all, so the pipeline knows not just *that* two pairs are coordinating but whether they're moving together or working at cross-purposes.

This is also where the empire's henchmen make the job needlessly hard on themselves: because they're collinear — every one of them shares a USD leg with at least itself, and mostly with each other — scikit-learn's default automatic penalty search wanders into a near-singular regime and produces nonsense. The fix was an explicitly constrained cross-validation grid rather than trusting the library's instincts, which is as close as this document gets to a moral about not blindly trusting default settings when your suspects all know each other a little too well.

## Who Moved First: Granger Causality and the Problem of Symmetric Suspicion

A partial correlation is symmetric. It will confirm that EUR/USD and GBP/USD are conditionally entangled and then shrug when asked which one started it — which, for an org chart, is close to useless. Knowing two henchmen are coordinating without knowing who gives the orders is just a nicer-looking rumor.

So for every edge the lasso skeleton keeps, the pipeline runs pairwise **Granger causality** in both directions: does one henchman's recent lagged returns improve a prediction of the other's return, beyond what that other henchman's own history already explains — and does it work the other way too? Both directions get tested, because alliances in this empire are not always exclusive, and an honest org chart has to allow for the possibility that two lieutenants are quietly running each other.

With a nontrivial skeleton, a single window fires off a lot of these tests simultaneously, and calling all of them "significant" without correction is how you end up promoting henchmen based on coincidence. Every p-value from every directional test in a window gets pooled and corrected together with Benjamini-Hochberg FDR before anyone's loyalty gets labeled. What comes out the other side is one of four verdicts per edge: `i->j`, `j->i`, `i<->j` for the henchmen who are, infuriatingly, running each other simultaneously, and `undirected` for the ones caught coordinating with no discernible chain of command. That last category, incidentally, describes most of middle management in any organization, villainous or otherwise.

## A Confession, Delivered With As Much Dignity As Possible

This project used to be called `fx-bn`, and its repository was titled `forex-bayesian-belief-networks`. Our heroine would like it on the record that this was not laziness — she had a specific, load-bearing, and ultimately wrong idea in mind, and she is prepared to walk the whole empire through exactly how wrong.

A Bayesian network, in the sense Judea Pearl and several decades of the literature actually mean it, is a *directed acyclic graph* with a conditional probability distribution at every node given its parents, a joint distribution that factorizes cleanly over that structure, and belief-propagation machinery for updating the whole picture when evidence lands at one node. What this pipeline produces is not that, for three specific and increasingly damning reasons. First, the skeleton step is an undirected Gaussian graphical model — an edge means "conditionally dependent given the other five," which is the undirected-graph notion of conditional independence, not a DAG factorization. Second, Granger causality orients edges by temporal predictive improvement, not by the conditional-independence rules — colliders, Meek's rules — that actual structure-learning algorithms like PC or GES use to keep every orientation consistent with a single coherent DAG. And third, most decisively, the pipeline explicitly emits `i<->j` bidirected edges whenever both directions test significant. A bidirected edge is a cycle. A DAG cannot contain a cycle. The moment any henchman relationship gets labeled bidirected — two lieutenants running each other in a stable mutual loop, which happens constantly in this empire and is presumably why nobody ever gets fired — the entire result is structurally disqualified from being a Bayesian network, by definition, no argument, case closed.

So `fx-bn` became `fx-pcn`, and `forex-bayesian-belief-networks` became `forex-partial-correlation-network`, and the old GitHub URL now quietly redirects to the new one like nothing happened. What this actually is: a time-varying Gaussian graphical model — a partial-correlation network — with Granger-causal lead-lag annotations layered on top. Sometimes called a "mixed graph" informally. Never, ever a Bayesian network, and our heroine will now correct anyone who says otherwise with the specific intensity of someone who spent a full changelog entry apologizing for it.

## The Command Console

The whole thing runs through one CLI, with a subcommand per stage:

```bash
fx-pcn run-pipeline --output output/edges.parquet
fx-pcn run-pipeline --output output/edges.parquet --days 30       # quick smoke test
fx-pcn run-pipeline --output output/edges.parquet --append        # incremental refresh
fx-pcn render-graph --input output/edges.parquet --output output/graph.png
fx-pcn compute-density --input output/edges.parquet --output output/density.parquet
fx-pcn find-direction-flips --input output/edges.parquet --output output/flips.parquet
```

`--append` deserves a small note of pride: every row is keyed to a fixed trailing window ending on a specific date, so a window that's already been fit never needs to be refit — only dates after the table's most recent one do. The incremental logic lives in one shared module, `fx_pcn.incremental.merge_incremental`, reused by all three subcommands that support it, rather than three copies of the same idea slowly drifting apart the way henchman loyalty tends to.

## Reading the Org Chart

Filtering the edge table to a single date gives that day's graph outright — nodes are the seven pairs, edges are whatever survived that window's lasso fit, and a pair with no row that day wasn't *missing data*, it was zeroed out on purpose. Two further computations turn the day-by-day graph into something readable at a glance rather than scanned row by row like a suspicious accountant. **Network density** — edge count over all twenty-one possible pairs, plus the mean absolute partial correlation and a tally of directed versus bidirected versus undirected edges — collapses a day's entire conspiracy into a single number, and a rising one over time is a plausible signal that the whole empire is losing its healthy internal distrust and starting to move as a bloc, which markets under stress reliably do. **Direction flips** ask the sharper question of whether any *specific* relationship just changed — an edge appearing, disappearing, reversing which pair leads, or a pair losing Granger significance without losing the edge entirely. `no_edge` and `undirected` are kept deliberately distinct here, because "these two stopped talking" and "these two are still talking but nobody's clearly in charge" are different kinds of organizational failure and our heroine would like her dashboards to reflect that nuance.

## What's Deliberately Not Here Yet

The default settings — five-day windows, daily steps, hourly bars, a four-hour max lag — target one specific regime: intraweek lead-lag, the kind of thing a London/New York session handoff produces. The same pipeline, pointed at different window/step/granularity/lag values, targets everything from intraday microstructure up through multi-year policy-cycle structure, and every one of those besides an event-conditioned regime anchored to the macro calendar is just a flag change, no code required. The event-conditioned regime — snapping windows to FOMC or NFP dates instead of a fixed interval — is not built. Neither is a daily report that synthesizes density and direction-flip output into one human-readable summary instead of two parquet files an analyst has to correlate by hand, which is next on the list and which our heroine is choosing to announce publicly, mostly so that failing to build it becomes marginally more embarrassing than actually building it.

## Conclusion

An empire this size cannot be run on vibes and pairwise correlation, and it turns out it also cannot be run on a naming convention borrowed from a formalism the pipeline doesn't actually implement. `fx-pcn` now tells our heroine, refit daily, which of her seven currency henchmen are conditionally entangled net of the other five, which one is giving the orders when a relationship has a clear direction, and which ones are just quietly running each other in a loop that no org chart — Bayesian or otherwise — was ever going to capture. The rename cost a changelog entry and a small amount of dignity. Continuing to call an undirected Gaussian graphical model with bidirected Granger edges a Bayesian network in front of people who'd notice would have cost considerably more.

---

*AI Use Statement: this post was drafted by Claude (Anthropic) at the author's direction, working from this project's own README, AGENTS.md, and CHANGELOG.md, and revised by a human before publication.*
