---
name: market-scan
description: Analyze the US market regime, breadth, sector or industry strength, leadership, screening results, stock discovery, breakouts, and watchlists. Use whenever the user asks how the market is, what areas are strong, to find stocks or leaders, or to build or refresh a watchlist, even if Minervini is not named. Do not use for a buy, sell, hold, or timing judgment about one named ticker; route that to ticker-analysis. Do not use to grade the user's completed trades; route that to trade-review. Portfolio sizing is out of scope.
allowed-tools: Bash(scripts/.venv/bin/python *), Bash(bash scripts/bootstrap.sh), Read, Grep, Glob, WebSearch, WebFetch
---

!`scripts/.venv/bin/python scripts/modules/market_clock.py`

# Market scan

## Ground the analysis

- Treat the injected clock output as the current ET session and cache context. Use the last completed US session for daily evidence; do not confuse a KST calendar date with the US market session.
- Read `references/regime.md` before any market-regime conclusion. Read `references/screening.md` before discovering, filtering, ranking, or changing a watchlist.
- Your training priors do not contain this harness's Minervini-first adjudications. The references are controlling doctrine, not optional background, and `[TL]` material remains subordinate and tagged.
- Use WebSearch only for current narrative, catalyst, sector, or industry context. All prices, breadth, RS, dates, and financial values must come from the deterministic modules.

## Establish the environment

1. Run `scripts/.venv/bin/python scripts/pipeline discover` from the repository root.
2. Inspect every section independently: Finviz breadth, QQQ switch, RS leaders and movers, sector ranks, industry leaders, and module provenance. A successful composite can still contain an unavailable section.
3. Retry a failed module or section once. If it still fails, preserve `unavailable`; never fill the gap from memory, WebSearch, another metric, or a local RS proxy pretending to be a cross-sectional rank.
4. Apply the dual gate from `references/regime.md`: QQQ-versus-21EMA is `[TL]` environmental information, while `[M]` leader quality and actual trade traction decide whether the regime has earned a stronger conclusion.
5. State the evidence that would refute the read. A regime label without observable invalidation conditions is an opinion, not an analysis.

## Regime conclusion

- Distinguish `observation`, `probe`, `earned expansion`, `defense`, `cash`, and `incomplete evidence`; do not compress disagreement into a vague bull or bear label.
- A QQQ `ON` transition alone cannot authorize a favorable exposure verdict. Require qualified leaders, traction, and a second wave of setups.
- A QQQ `OFF` transition alone cannot force opinion liquidation. Tighten price-based protection and let each position's evidence govern.
- Treat repeated stop-outs, failed breakouts, and a shrinking unchanged screen as adverse feedback; never respond by widening stops or loosening SEPA gates.
- Identify lockout-rally evidence and leader/index divergence explicitly because ordinary overbought and index-first heuristics read these turns backward.

## Discover and qualify candidates

1. Use several loose screens and the union of their results. Preserve each ticker's source and recurrence instead of building one monolithic discovery-time AND filter.
2. Keep the funnel counts visible: candidate universe, first pass, weekly focus, and daily focus. Counts are breadth and workload evidence, not a scoring system.
3. Deduplicate user tickers and module-supplied RS, mover, sector, and industry candidates. Honor the requested maximum before qualification.
4. If the regime is hostile, return a watch-only report rather than spending calls on a broad qualification fan-out.
5. For each retained ticker, run one `ticker-scout` per ticker when parallel subagents are available; each scout executes `scripts/.venv/bin/python scripts/pipeline qualify TICKER`. Prefer the fixed `/screen` workflow for the full sweep. If workflows or parallel agents are unavailable, use the sequential `ticker-scout` or direct qualification fallback in `references/screening.md` without changing the contract.
6. Validate each compact result before synthesis: verdict, failed or unavailable gates, RS source and score, Stage, and one-line evidence. Retry one malformed or failed result once, then keep it incomplete.
7. Bucket candidates as `PROCEED`, `watch/incomplete`, or `AVOID`, then apply the watch → buy-alert → buy-ready state machine from `references/screening.md`. `PROCEED` is necessary but never sufficient for buy-ready.

## Iterate rather than over-call

- Use `rs_ranking.py screen`, `score`, or `compare` only for the roles defined in the screening reference. Never rank multiple stocks using self-historical local proxy percentiles.
- When a loose screen is too broad, tighten that lens or split it into meaningful independent lenses. Do not invent a master score that lets one strong field erase a hard failure.
- When too few candidates appear, inspect source failures and market breadth before relaxing criteria. A genuinely sparse market is itself information.
- Keep the main context compact. Preserve detailed JSON only long enough to verify the conclusion; retain the ticker-level evidence summary needed for the watchlist.

## Output contract

Return these sections in order:

1. **Session and source health:** ET session, last completed session, cache state, and unavailable sections.
2. **Regime evidence:** QQQ information filter, leader gate, trade feedback, dual-gate conclusion, and refutation conditions.
3. **Funnel:** source counts, deduplicated count, qualification count, and final bucket counts.
4. **Watchlist:** ticker, state, qualification verdict, RS source and score, Stage, originating screens, one-line evidence, missing evidence, and the next promotion or demotion condition.
5. **Narrative context:** only sourced current context that explains, but never replaces, module evidence.

Do not prescribe portfolio percentages or position sizes. If asked, explain the scope boundary and offer market, setup, and evidence-quality analysis instead.
