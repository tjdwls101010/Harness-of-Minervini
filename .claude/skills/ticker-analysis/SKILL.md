---
name: ticker-analysis
description: Analyze one or a few named US-listed stocks for a prospective buy, entry timing, setup diagnosis, active-position HOLD or SELL evidence, re-entry, earnings risk, chart condition, or head-to-head comparison. Use whenever the user asks what to do with a specific US-listed ticker, even if Minervini or SEPA is not named. Do not use for market-wide sector screening or leader discovery; use market-scan. Crypto, non-US listings, completed-trade grading, portfolio sizing, and allocation advice are outside scope.
allowed-tools: Bash(${CLAUDE_PROJECT_DIR}/scripts/.venv/bin/python ${CLAUDE_PROJECT_DIR}/scripts/pipeline *), Bash(bash ${CLAUDE_PROJECT_DIR}/scripts/bootstrap.sh), Read, Grep, Glob, WebSearch, WebFetch
---

# Ticker analysis

## Orient through the interface

- Work from the repository root. If the canonical interpreter is missing or imports fail, run the bootstrap command declared in the root constitution once.
- If the needed capability is uncertain, run the capability-catalog command declared in the root constitution.
- Before invoking a selected capability for the first time, inspect only `describe <capability>` or that leaf command's `--help`. The CLI owns syntax, defaults, time limits, status meanings, and side effects; do not duplicate them here.
- Decide whether the request is prospective, active-position, re-entry, or comparison. Collect only evidence that can change that decision.
- Treat a virtual or fixed-evidence prompt as a closed world: use only its supplied evidence, never an unrelated fixture, live ticker, or web number. If a Primary Base duration, depth, or all-time-high trigger is not supplied, keep it missing; do not infer it.

## Prospective entry

- Qualify first. Do not research a story, inspect valuation, or deepen the setup before the low-cost technical gate earns it.
- If a known Stage 2 or Trend Template gate fails, return AVOID for a prospective entry and stop. Explain the exact failed evidence and do not let fundamentals, cheapness, reputation, or narrative reopen the route.
- If qualification is incomplete, distinguish missing evidence from failure. Resolve only the named gap when possible; use a chart for `needs_chart`, and never infer a pass.
- If eligible, examine weekly structure before daily timing. Require separate price geometry, contracting supply, a completed pivot or VCP-anchored cheat, and precise invalidation.
- A named VCP without supply evidence is incomplete. `[TL-EARLY]` is available only after explicit opt-in, must name one of the five defined tactics, and must retain that tactic's trigger and invalidation alongside confirmation debt and a later Minervini pivot.
- Evaluate SEC filed-as-of fundamentals, accounting integrity, dilution, growth quality, and leadership category. The Power Play exception may waive only unavailable verified fundamentals when every other proof remains intact.
- Compare the ticker with current same-industry peers. Treat historical peer analysis as unavailable when current mutable taxonomy would be the only identity source.
- Recheck the market evidence needed by this setup. QQQ context alone cannot supply market alignment, and absent user trade traction remains a real gap.
- Use the risk reducer for the final prospective state. Never call a ticker BUY-READY from qualification, setup, fundamentals, or RS alone.

## Active position or re-entry

- Use the user's actual entry date, entry price, hard stop, and structural invalidation. If anchors are missing, report INCOMPLETE and ask only for information that can change HOLD or SELL.
- Audit every completed daily low from the stop's effective date through the analysis session. A recovered latest price cannot establish HOLD after an earlier breach; incomplete path coverage means INCOMPLETE. Use a partial-session breach only when the user explicitly requests a live stop check.
- A breached hard stop or triggered invalidation means SELL without negotiation. Never widen the stop, average down, or defend the position with valuation or hope.
- For HOLD, require both current completed-price evidence and a clear completed stop path. If the stop changed after entry, use its actual effective date rather than applying it retroactively. At 3R, call out the requirement to protect at least breakeven.
- Broad-market weakness informs defense but does not sell an exceptional ticker by index opinion alone. Ticker price and invalidation evidence remain controlling.
- A re-entry is a new prospective decision. Re-run qualification, setup, market, and risk rather than treating a prior win or loss as permission.

## Chart and narrative judgment

- Render a chart only when qualitative ambiguity matters. Read weekly before daily, moving averages as zones, overhead supply, base maturity, price/volume character, and expected behavior.
- Visual judgment can resolve geometry or supply evidence but cannot override a deterministic failure.
- Use web search only for current catalyst, company, earnings-event, or industry narrative after deterministic evidence. Cite that context and never import precise market numbers from it.
- Respect abnormal price weakness after apparently good news. Price can reveal deterioration before the public explanation.

## Comparisons and synthesis

- For a few named tickers, gate each independently before comparing. A failed ticker cannot win through relative scoring.
- Compare only aligned evidence and dates: eligibility, setup quality, filed fundamentals, same-industry leadership, market fit, downside, and reward-to-risk.
- Lead with BUY-READY, WAIT, AVOID, INCOMPLETE, HOLD, or SELL and evidence quality. Then separate known failures, missing evidence, qualitative chart judgment, entry or promotion conditions, and invalidation or exit conditions.
- State the completed US session and material provider limitations. If the evidence cannot support a decision, say exactly what remains unresolved.

Do not prescribe portfolio percentages or position sizes. Offer the ticker-level risk contract instead.
