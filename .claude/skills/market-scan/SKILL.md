---
name: market-scan
description: Analyze the US market regime, breadth, sector or industry strength, leadership, stock discovery, screening results, and watchlist candidates. Use whenever the user asks how the market is, which areas are strong, what tickers look promising, or to build or refresh a watchlist, even if Minervini is not named. Do not use for a buy, sell, hold, entry condition, or diagnosis judgment about one or a few named tickers; use ticker-analysis. Crypto, non-US listings, completed-trade grading, portfolio sizing, and allocation advice are outside scope.
allowed-tools: Bash(${CLAUDE_PROJECT_DIR}/scripts/.venv/bin/python ${CLAUDE_PROJECT_DIR}/scripts/pipeline *), Bash(bash ${CLAUDE_PROJECT_DIR}/scripts/bootstrap.sh), Read, Grep, Glob, WebSearch, WebFetch
---

# Market scan

## Orient through the interface

- Work from the repository root. If the canonical interpreter is missing or imports fail, run the bootstrap command declared in the root constitution once.
- If the needed capability is uncertain, run the capability-catalog command declared in the root constitution.
- Before invoking a selected capability for the first time, inspect only `describe <capability>` or that leaf command's `--help`. The CLI owns syntax, defaults, limitations, status meanings, and side effects; do not reconstruct them here.
- Compose calls around unresolved evidence. Do not execute every capability, preload all help, or force a fixed screening rail.

## Establish the environment

- Start with the market snapshot appropriate to the user's as-of request. Treat each source and breadth section independently; a composite response can be usable while one section is unavailable.
- Actual trade traction is a separate bottom-up gate. If the user has not supplied recent pilot, breakout, or stop-out feedback, preserve `needs_input` and do not promote QQQ or breadth alone to a favorable regime.
- QQQ versus 21 EMA is environmental context only. Leaders and real trade behavior decide whether apparent strength has earned confidence.
- Read persistent overbought action with shallow pullbacks as possible lockout demand, not an automatic sell signal. Also surface leader/index divergence and the evidence that would refute the regime read.
- If the environment is hostile or evidence is materially incomplete, reduce the discovery depth and return watch-only conditions. Sparse qualified leadership is itself evidence; never loosen hard gates to fill a list.

## Find leaders without manufacturing a score

- Use provider-ranked sectors, industries, and leading stocks as observations, not as a weighted master score.
- Preserve each candidate's discovery origin. Repeated appearance across independent evidence is useful context but cannot erase a failed gate.
- Use same-industry peer comparison on promising leaders to establish current classification, stable identity, and relative leadership. Current taxonomy must not be projected backward into a historical answer.
- Treat the candidate-universe capability as scope and pagination, not an automatic recommendation engine.
- Keep the set small enough to investigate well. When independent qualification calls can run concurrently, parallelize them adaptively; do not depend on a fixed agent, workflow, batch size, or quota.

## Make every candidate earn depth

- Run technical qualification before setup, fundamentals, narrative research, or recommendation language.
- A known Stage 2 or Trend Template failure ends prospective promotion for that ticker. Missing RS or history remains incomplete and should state how it could be resolved.
- For finalists that pass qualification, collect only the setup, filed fundamentals, peer, chart, and risk evidence needed by the user's question.
- A `PROCEED`, eligible, or high-RS state is not BUY-READY. Actionable language requires a completed setup, market alignment, required fundamentals or the explicit Power Play exception, and a valid risk contract.
- Use web search after deterministic evidence for current catalysts and industry explanation. Cite it as narrative context and never use it to fill a numeric gap or reverse a hard gate.

## Synthesize

Lead with the completed US session, evidence quality, and the regime state. Then report leading sectors and industries with the supporting vector rather than a naked rank.

For each candidate, show ticker, current industry identity, discovery origin, eligibility state, exact failed or missing gates, why it merits attention, and the observable condition for promotion or removal. Distinguish ranked leader, watch candidate, setup-ready, and final BUY-READY states.

When no candidate earns recommendation, say so plainly. Cash and an empty high-quality list are valid outcomes.

Do not prescribe portfolio percentages or position sizes. Offer market, setup, risk, and evidence-quality analysis instead.
