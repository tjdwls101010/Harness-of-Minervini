---
name: ticker-analysis
description: Analyze one or a few named US-listed stocks for a prospective buy, entry timing, setup diagnosis, active-position HOLD or SELL evidence, re-entry, earnings risk, chart condition, or head-to-head comparison. Use whenever the user asks what to do with a specific US-listed ticker, even if Minervini or SEPA is not named. Do not use for market-wide sector screening or leader discovery; use market-scan. Crypto, non-US listings, completed-trade grading, account-level position sizing, and capital allocation advice are outside scope.
allowed-tools: Bash(${CLAUDE_PROJECT_DIR}/scripts/.venv/bin/python ${CLAUDE_PROJECT_DIR}/scripts/pipeline *), Bash(bash ${CLAUDE_PROJECT_DIR}/scripts/bootstrap.sh), Read, Grep, Glob, WebSearch, WebFetch
---

# Ticker analysis

## Orient through the interface

- Work from the repository root; the root constitution holds the bootstrap and capability-catalog commands. Before invoking a capability for the first time, read only its `describe` output or that leaf command's `--help`.
- Decide whether the request is prospective, active-position, re-entry, or comparison. Collect only evidence that can change that decision.
- Treat a virtual or fixed-evidence prompt as a closed world: use only its supplied evidence, never an unrelated fixture, live ticker, or web number. If a Primary Base duration, depth, or all-time-high trigger is not supplied, keep it missing; do not infer it.

## Prospective entry

- Qualify first. Do not research a story, inspect valuation, or deepen the setup before the low-cost technical gate earns it.
- On a known gate failure, stop and name the exact failed evidence. On an incomplete one, resolve only the named gap -- a chart for `needs_chart` -- and never infer a pass.
- Declaring a plane's state is an assertion, and only a gate licenses one. A band or marker below its range is review evidence: typing it into `--fundamentals-state` or `--setup-state` turns a measurement that reports into a verdict that decides, and the reducer takes it because a caller's word is always allowed to be more cautious. Where no gate failed and the other planes are unmeasured, the ticker is INCOMPLETE -- a route you can rule out on its own terms is not the ticker's verdict.
- If eligible, examine weekly structure before daily timing. Require separate price geometry, contracting supply, a completed pivot or VCP-anchored cheat, and precise invalidation.
- A named VCP without supply evidence is incomplete. `doctrine show tactic.<name>` lists what a `[TL-EARLY]` tactic requires; each condition is a chart reading you declare, and one you could not settle is declared as such rather than left out.
- Evaluate SEC filed-as-of fundamentals, accounting integrity, dilution, growth quality, and leadership category, then read the growth numbers under the leader category the filings support.
- Compare the ticker with current same-industry peers.
- Recheck the market evidence this setup needs. QQQ context alone cannot supply market alignment, and absent user trade traction remains a real gap.
- Use the risk reducer for the final prospective state. Never call a ticker BUY-READY from qualification, setup, fundamentals, or RS alone.

## Active position or re-entry

- Use the user's actual entry date, entry price, hard stop, and structural invalidation. If anchors are missing, report INCOMPLETE and ask only for information that can change HOLD or SELL.
- Audit every completed daily low from the stop's effective date through the analysis session. A recovered latest price cannot establish HOLD after an earlier breach; incomplete path coverage means INCOMPLETE. Use a partial-session breach only when the user explicitly requests a live stop check.
- For HOLD, require both current completed-price evidence and a clear completed stop path. If the stop changed after entry, use its actual effective date rather than applying it retroactively.
- Report the `management_actions` the envelope carries beside the verdict, each with the claim and measurement behind it. A HOLD with an untouched stop and deteriorating structure is a HOLD plus REVIEW, never a bare HOLD.
- A re-entry is a new prospective decision. Re-run qualification, setup, market, and risk rather than treating a prior win or loss as permission.

## Chart and narrative judgment

- Render a chart only when qualitative ambiguity matters. Read weekly before daily, moving averages as zones, overhead supply, base maturity, price/volume character, and expected behavior.
- Use web search only for current catalyst, company, earnings-event, or industry narrative, and only after the deterministic evidence is in.
- Respect abnormal price weakness after apparently good news. Price can reveal deterioration before the public explanation.

## Comparisons and synthesis

- For a few named tickers, gate each independently before comparing. A failed ticker cannot win through relative scoring.
- Compare only aligned evidence and dates: eligibility, setup quality, filed fundamentals, same-industry leadership, market fit, downside, and reward-to-risk.
- Lead with BUY-READY, WAIT, AVOID, INCOMPLETE, HOLD, or SELL and evidence quality. Then separate known failures, missing evidence, qualitative chart judgment, entry or promotion conditions, and invalidation or exit conditions.
- If the evidence cannot support a decision, say exactly what remains unresolved.
