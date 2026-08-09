# Our Heroine Debriefs the Currency Conspiracy, and Keeps Every Transcript

### Turning the LLM's Qualitative Read of the Network into Dated, Queryable RDF — Without Ever Confusing an Opinion for a Fact

The wiretaps were never the whole story. Our heroine's seven currency-pair henchmen have had their alliances re-litigated daily for a while now — partial correlations recomputed, Granger-causal chains of command reassigned, the whole conspiracy exported as RDF so the rest of the empire could finally read the surveillance logs in a common language. But a wiretap transcript, however faithfully recorded, doesn't interpret itself. Someone still has to sit down with the day's density numbers and direction flips and say, in plain language, what it actually means that the empire suddenly got 40% denser this week — and whether that's a stress signal worth the boardroom's attention or just Tuesday. That job already existed, handled by an LLM at the end of every HTML report. What didn't exist, until now, was any record of what it said.

## The Debriefing Room Had No Filing Cabinet

`generate-report` has always closed with an LLM-written qualitative summary — a few paragraphs interpreting that day's density and direction-flip data, ending with strategic, actionable takeaways about what's worth watching next. It was genuinely useful, and it was also, structurally, a conversation that left no transcript. The moment tomorrow's report rendered, today's read was gone — not archived, not queryable, just quietly overwritten by whatever the model said next, the way a debriefing room with no stenographer produces a very confident verbal briefing and absolutely nothing you could go back and check three weeks later. Meanwhile, the actual wiretap data — the edges, the density snapshots, the direction flips — had already been taught to speak RDF, joinable across the empire's whole knowledge graph. The hard evidence had a permanent file. The analyst's own interpretation of that evidence did not, which is a strange thing to leave undocumented in an organization this paranoid.

## Only the Takeaways Get Filed, Not the Whole Speech

The fix isn't to dump the entire LLM narrative into the graph — free-flowing prose isn't a fact, it's a speech, and stuffing a paragraph into a single RDF literal doesn't make it queryable, just long. What's actually worth filing are the discrete, specific claims at the end of the summary: the strategic takeaways, the handful of concrete things worth watching. So the prompt now closes with an explicit instruction to write those takeaways under a fixed heading, `STRATEGIC TAKEAWAYS:`, one bullet per line. Parsing that back out is deliberately unglamorous — no JSON schema, no function-calling, no second LLM call asking a model to reformat its own answer. A local model talking to itself through Ollama is far more reliable at echoing back a literal string it was told to use than at emitting well-formed JSON on the first try, so the parser just looks for the heading and reads bullet lines after it. Boring and robust beats clever and occasionally malformed, especially when nobody's proofreading the output before it becomes a triple.

## Filed Separately From the Wiretap Logs, on Purpose

The natural instinct is to fold these new facts straight into the same RDF file the numeric network already exports to — one filing cabinet, one export command, done. That instinct is wrong, and it's worth explaining why. The wiretap logs — the edges, the density snapshots, the direction flips — are produced by a deterministic pipeline with no external dependency once the price data's in hand; they can be exported at any hour, reliably, forever. The debrief depends on an LLM being reachable and cooperative that day, which is a meaningfully less reliable proposition. If the two were exported together, a bad afternoon for the local Ollama server would mean the *entire* RDF export fails — the hard evidence held hostage by whether the analyst felt like talking. So the debrief gets its own export, `export-summary-rdf`, run as an independent step from the numeric `export-rdf`. An unreachable LLM now means one missing debrief for one day, filed as such, while the wiretap logs keep flowing exactly as they always did.

## Testimony, Not Surveillance — and the Graph Says So

Filing the debrief separately from the wiretaps isn't just an operational convenience, though — it's also the honest description of what kind of fact it is. A partial correlation is a measurement; a strategic takeaway is somebody's read of a measurement, one step removed, and mixing the two in a graph without saying so is how "the network is 40% denser this week" quietly turns into "the network is dangerously fragile this week" three queries later, with nobody able to tell where the hard number ended and the opinion began. So each day's takeaways get filed on a new node type, `fxpcn:QualitativeSummaryRun`, holding one `fxpcn:takeawayBullet` literal per bullet and an `fxpcn:llmModel` property naming exactly which model gave this particular read — worth recording on its own, since a different model reading the same numbers might reasonably reach a different verdict, and a good file always says who's talking. That node links back to the same `prov:Activity` node the numeric export already mints for that day's regime — the same provenance record, reused rather than duplicated — but through `prov:wasInformedBy`, not `prov:wasGeneratedBy`. The distinction is small in syntax and large in meaning: `wasGeneratedBy` says *this fact is the output of that process*, the correct claim for a partial correlation the pipeline actually computed; `wasInformedBy` says *this activity used output from that other one*, the correct claim for an opinion formed by reading the pipeline's output after the fact. Get that backwards and a knowledge graph consumer has no honest way to ask "just give me the measured facts" without also getting the analyst's hunches mixed in.

One more detail worth being precise about: the transcript that gets filed and the memo that goes in the boardroom's HTML report come from the exact same conversation, not two separately-conducted debriefings. The bullets exported to RDF are parsed out of the identical LLM call that produces the report's narrative, not a second, independently-prompted one — so there's no version of events where the filed testimony and the report on the boardroom table quietly disagree with each other.

## Making It Date-Aware, Which Is the Part That Almost Got Missed

Here's the part worth walking through carefully, because the first draft of this design got it wrong in a way that's easy to miss and expensive to leave uncaught. The natural pattern to copy was the HTML report's own behavior: recompute fresh, overwrite, done — today's read replaces yesterday's, the same way today's report page replaces yesterday's page. That's exactly right for a report meant to be read once and discarded, and exactly wrong for a knowledge graph, whose entire point is answering questions a single day's snapshot never could — "how has the empire's own read on itself shifted over the last few weeks" is precisely the kind of longitudinal, connect-the-dots question a graph is good for, and a design that silently discards yesterday's testimony the moment today's lands can never answer it, no matter how well-formed the RDF is on any given day.

The fix was to stop treating the debrief as a one-off snapshot and start treating it exactly like every other dated fact this pipeline already tracks. The density and direction-flip tables were never rebuilt from scratch on each run — they're appended, one new date's rows added to the ones already on file, so the whole history stays on the record as the pipeline keeps running. The takeaway bullets now follow that same convention: each report date's bullets get written to an accumulating table, one row per bullet per date, using the identical incremental-merge logic already responsible for appending density and direction-flip history rather than a new mechanism invented just for this. `export-summary-rdf` then walks every distinct date present in that accumulated table and mints a separate `fxpcn:QualitativeSummaryRun` for each one — not just today's — so the resulting graph holds the network's stated interpretation on every day it was ever asked to give one, each carrying the same `fxpcn:date` literal every other dated node in the graph already carries. That shared literal is what makes the whole thing worth doing: it's now possible to ask a graph consumer for both the network's numeric state *and* its own stated read of itself, for the same specific date, which wasn't a question either export could answer on its own before this.

It's also worth being honest about the edge case that motivated checking this so carefully: what happens on a day the debriefing room is simply empty, because the LLM call failed and there's nothing to file? The accumulation logic has to be careful there too — an empty day's file, read back as the "existing" record to append onto, can't be allowed to look like an empty history and silently swallow every future day's bullets along with it. Getting the append logic right for that specific quiet failure mode was most of the actual engineering effort here, which is a very on-brand lesson for an operation this paranoid: it's not the loud failures that burn you, it's the empty room nobody double-checked.

## Conclusion

The wiretap logs already spoke a language the rest of the empire could read. Now the debriefing room's transcripts do too — dated, filed, joinable against the same evidence they were interpreting, and stamped clearly enough as testimony that nobody downstream mistakes an analyst's hunch for a measured fact. And because every debrief gets filed rather than overwritten, our heroine can finally go back and check whether last month's read on the conspiracy held up — which is, after all, the entire point of keeping records instead of just trusting whoever's talking that day.

# Code

Code implementing this project is available [here](https://github.com/badass-data-science/forex-partial-correlation-network).

# AI Use Statement

This post was initially drafted by Claude at the author's direction, working from this project's own README, AGENTS.md, and CHANGELOG.md, and then revised by a human before publication.

## Tags

- Data Science
- Python
- RDF
- Knowledge Graphs
- PROV-O
- LLM Applications
- Forex
- Quantitative Finance
- Time Series
