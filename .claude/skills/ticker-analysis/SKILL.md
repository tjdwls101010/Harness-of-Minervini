---
name: ticker-analysis
description: Analyze one or a few named US-listed stocks for a prospective buy, entry timing, setup diagnosis, existing-position sell or hold judgment, re-entry, earnings risk, or chart condition — including a head-to-head comparison of two or a few named tickers (gate each ticker, then compare). Use whenever the user asks what to do with a specific US-listed ticker, even if they do not name Minervini or SEPA. Do not use for market-wide, sector, screening, leader-finding, or watchlist requests; route those to market-scan. Do not use to grade, review, or post-mortem any completed trade, whether one ticker or a trade log; route that to trade-review. Crypto and non-US listings are out of scope; state the scope boundary instead of analyzing them. Never provide portfolio sizing.
allowed-tools: Bash(scripts/.venv/bin/python *), Bash(bash scripts/bootstrap.sh), Read, Grep, Glob, WebSearch, WebFetch
---

!`scripts/.venv/bin/python scripts/modules/market_clock.py`

# Ticker analysis

## Ground the branch

- Treat the injected clock output as the current ET session and cache context. Daily evidence uses completed US sessions unless a command explicitly reports live run rate.
- Identify whether the request concerns a prospective buy/diagnosis, an existing position, or both. Ask only for facts that change the branch, such as entry, stop, pivot, breakout date, or prior-high anchor.
- Your training priors do not contain this harness's adjudicated thresholds. Read the required references before the verdict; do not substitute remembered Minervini, IBD, O'Neil, or generic chart doctrine.
- Precise market and financial values come only from `scripts/`. WebSearch is for current narrative and catalysts, never replacement numbers.

## Reference routing

- For a prospective buy, re-entry, setup diagnosis, or chart-condition diagnosis, read `references/entry.md` before interpreting the gate, setup, pivot, or price/volume behavior.
- For a deep prospective review, read `references/fundamentals.md` after the hard gate passes.
- Read `references/sell.md` before defining a prospective exit plan and before every existing-position sell or hold verdict.
- The references are a chain, not a menu that lets favorable material bypass an unfavorable gate. `[M]` controls; explicitly requested `[TL]` tactics remain opt-in and tagged.

## Prospective buy or diagnosis

1. Run `scripts/.venv/bin/python scripts/pipeline qualify TICKER` first. Retry once on command failure.
2. A known gate failure produces `AVOID` for the prospective buy. Do not spend a failed gate into a favorable answer through fundamentals, valuation, theme, or visual appeal.
3. An unavailable required criterion produces `INCOMPLETE`. Name the missing evidence; do not turn absence into either failure or permission.
4. On `PROCEED`, earn the entry review with parameterized calls such as `base_count.py count`, `vcp.py detect`, and `volume_analysis.py analyze`. Use `volume_analysis.py runrate` only for an active-session pivot decision.
5. Use `entry_patterns.py` only when the user explicitly opts into the `[TL]` daily-tactic layer. Its result cannot waive SEPA eligibility, a larger constructive setup and supply-absorption context, or the tactic's own completed trigger and objective failure level.
6. Run the earnings, margin, surprise, revision, valuation, category, catalyst, and leadership review from `references/fundamentals.md`. Use narrative search only where that reference permits it.
7. Obtain market alignment from a fresh `scripts/.venv/bin/python scripts/pipeline discover` result or current market-level evidence already established under the market doctrine. Do not let an index switch decide alone.
8. Read `references/sell.md` and write the initial invalidation, reward/risk, earnings-event policy, and contingency plan before issuing a favorable entry verdict.
9. Require probability convergence across eligibility, entry structure, price/volume, required fundamentals and catalyst, leadership, market, and risk.

A VCP-qualified Power Play is the sole permitted fundamentals exception. Label it explicitly and waive only verified fundamentals; all other convergence legs remain mandatory.

## Existing position: sell or hold

1. Record entry date and price, original stop, current management horizon, breakout or pivot context, and any known base top or prior high. If a value is absent, keep anchor-dependent evidence unresolved.
2. Run `qualify` for structural context, but never stop the sell analysis because a prospective-buy gate failed. A failed gate can be urgent holding evidence rather than a reason to avoid diagnostics.
3. Always read `references/sell.md`, then run the applicable deterministic evidence: `stage_analysis.py risk`; `sell_signals.py extension`, `reversal`, `trail`, or `cascade`; and `actions.py get-earnings-dates --days-until`.
4. Do not invent base-top, breakout-date, trendline, or prior-high anchors. Preserve module states such as `needs_input`, `needs_chart`, and `unavailable`.
5. Evaluate hard stop and gap-through evidence first, then Stage deterioration, expected-behavior failure, 3R defense, tagged sell-into-strength evidence, MA management, failure cascade, and earnings risk.
6. A good earnings headline cannot overrule the largest completed decline of the Stage 2 advance or another material abnormal price break.
7. Return `SELL`, `HOLD WITH CONDITIONS`, or `INCOMPLETE`, with dated triggers, provenance, unresolved evidence, and the next condition that changes the verdict.

## Chart corroboration

- Render a daily or weekly PNG with `chart_render.py` when contraction character, extension, trendline, prior-high context, or another qualitative feature remains ambiguous.
- Read weekly before daily, treat moving averages as zones, and look left for the stock's own character.
- Charts corroborate; they never replace module numbers, hard gates, or honest missing-input states.

## Evidence handling

- Retry a failed module once, then declare that evidence unavailable. Do not route around the failure with WebSearch or manual arithmetic.
- Preserve each module's doctrine, provenance, cache, and data-quality fields when they affect interpretation.
- Distinguish `failed`, `unavailable`, `not evaluated`, and `needs input`; collapsing them changes the decision.
- Iterate only where the prior result earns another look. There is deliberately no “analyze everything” command.

## Output contract

Return these sections in order:

1. **Verdict and scope:** branch, current verdict, and whether evidence is complete.
2. **Hard-gate context:** Stage, Trend Template, RS source and score, failed criteria, and unavailable criteria.
3. **Entry or holding evidence:** setup state, pivot or anchors, price/volume, dated sell events, and chart corroboration where used.
4. **Fundamentals and leadership:** category, catalyst, earnings phase, quality, revisions, group context, or a labelled Power Play exception.
5. **Market and risk convergence:** regime evidence, invalidation, reward/risk, earnings date, and contingency conditions.
6. **Next decision point:** the exact evidence that promotes, demotes, invalidates, or confirms the current state.

Use watch → buy-alert → buy-ready for prospective maturity, but never translate readiness into a portfolio percentage or position size.
