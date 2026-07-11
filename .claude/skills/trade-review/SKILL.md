---
name: trade-review
description: Grade, review, or post-mortem the user's own completed US-stock trades or trade log, including winners, losers, entries, exits, rule adherence, R-multiples, batting average, hold-time asymmetry, post-exit behavior, and the Loss Adjustment Exercise. Use whenever the user supplies past trades or asks what their trading record reveals. Do not use for a prospective single-ticker decision or a live position (route those to ticker-analysis), market screening or leader-finding (route to market-scan), or portfolio sizing.
allowed-tools: Bash(scripts/.venv/bin/python *), Read, Grep, Glob
---

# Trade review

This is a process audit, not a retrospective prediction contest. A profitable rule violation can be a poor decision, while a clean small loss can be excellent execution.

## Load the grading doctrine

- Read `../ticker-analysis/references/entry.md` before grading entries, resets, and chase distance.
- Read `../ticker-analysis/references/sell.md` before grading stops, exits, holds, and post-entry management.
- Do not duplicate or alter their doctrine here. `[M]` controls, and any `[TL]` practice-layer grade retains its tag.

## Required input

For each trade, seek ticker, entry and exit dates, entry and exit prices, initial stop, action timestamps or sequence, and the trader's stated setup or plan. Position size is optional and used only to calculate equity contribution when the user already provides it; never turn it into sizing advice.

- If entry price or exit price is missing, percentage return cannot be graded; mark it unavailable.
- If the initial stop is missing, `R` and stop-discipline grades are unavailable rather than reconstructed from a later chart.
- If the trade is still open, route the live sell or hold decision to the single-ticker analysis path; do not treat it as a completed post-mortem.
- Preserve the user's original plan separately from facts inferred after the outcome. Hindsight must not rewrite the decision that was actually made.

## Select the review set

1. Calculate each completed trade's percentage return from supplied entry and exit prices.
2. Sort the chosen period and review the top five winners plus bottom ten losers first. If fewer exist, review all and state the smaller sample.
3. If time remains, take the next five winners and ten losers. Depth matters more than grading every ordinary trade.
4. Keep trades from different strategy or market regimes labelled; do not revise a system from one cycle's sample.

## Reconstruct evidence deterministically

- Fetch the relevant raw window with `scripts/.venv/bin/python scripts/modules/info.py get-history TICKER --start YYYY-MM-DD --end YYYY-MM-DD`.
- For exit management, use `scripts/.venv/bin/python scripts/modules/sell_signals.py trail TICKER --ma 21e --start YYYY-MM-DD`, the 50s variant when appropriate, and `cascade --start YYYY-MM-DD` when the trade reached structural deterioration.
- Do not use current-only modules such as `stage_analysis.py risk` or `vcp.py detect` to grade a past action: without an as-of cutoff they leak later evidence into the score. Use the explicit `info.py get-history --start --end` window for historical chart evidence; current-only modules may describe post-exit state only when labelled as such.
- Extend the history several weeks beyond the exit when data is available. Post-exit action separates a bad idea from bad timing, a clean exit from an emotional one, and a missed reset from a correct blacklist decision.
- Retry a failed command once, then mark that grading evidence unavailable. WebSearch and memory are not allowed substitutes.

## Grade each action

Score entry, initial risk, adds or re-entries, profit management, and final exit separately on a ten-point scale. Every score needs a one-sentence evidence citation and a named criterion from the loaded references.

- **9–10:** the action followed the plan and controlling doctrine with precise timing and honest evidence.
- **7–8:** sound process with a limited, identifiable execution defect that did not alter the governing logic.
- **4–6:** mixed process; a meaningful rule or timing error contaminated an otherwise defensible action.
- **1–3:** major doctrine breach, hindsight-driven improvisation, emotional exit, averaging down, stop negotiation, or an entry that bypassed the gate.
- **Unavailable:** required plan or market evidence is missing; never convert missing evidence into an average score.

Do not grade from P&L alone. State explicitly when a winner received a low process score or a loser received a high one.

## Portfolio-level metrics without portfolio advice

Report the metrics the supplied log supports:

- Batting average, excluding scratch trades in the inclusive -1% to +1% band; show wins, losses, scratches, and denominator.
- Average and median winner and loser in both dollars and percentages when the data exists.
- Payoff ratio, with 2:1 as the controlling minimum and 3:1 preferred under the Minervini risk spine.
- `R` for each trade and average realized `R`, using the original stop distance only.
- Maximum gain and loss; investigate a maximum loss materially larger than the average loss as a likely execution breach.
- Average holding time for winners and losers; losers held longer than winners can expose hope and involuntary investing.
- Equity contribution only when the user supplied position weight; label it descriptive, not a recommendation.

Treat a declining batting average as a brake and diagnostic signal, not permission to widen stops. With a small sample, report the metric but do not change rules from it.

## Loss Adjustment Exercise `[M]`

1. Recalculate the historical sequence with every loss set to exactly 10%: raise smaller losses to 10% and reduce larger losses to 10% as the canonical diagnostic specifies.
2. Keep winners and trade order unchanged.
3. Compare original and adjusted compounded returns.
4. Explain the difference as the cost of loss distribution, not as a hypothetical backtest promise.

The exercise diagnoses whether uncontrolled losses—not stock selection—destroyed expectancy. It does not authorize a 10% default stop; the live stop still comes from half the realized average gain with 10% only as the ceiling.

## Post-exit and system-level lessons

- Track whether the ticker continued down, rebuilt a base, formed a quick pivot reset, or resumed higher after the exit.
- Separate selection error, entry error, risk error, management error, and regime error. One trade can contain more than one.
- Convert repeated mistakes into a concrete system change such as an earlier alert or a required pre-entry field; “be more disciplined” is not a repair.
- Preserve a clean small loss as positive evidence. The method seeks bounded failure, not a perfect hit rate.
- Study difference-maker winners as deeply as losses so the process learns what to repeat, not only what to avoid.

## Output contract

Return:

1. **Data quality and sample:** period, trade count, missing fields, and selected Top-5/Bottom-10 set.
2. **Metrics table:** wins, losses, scratches, batting average, average win/loss, payoff ratio, R, hold times, maxima, and optional equity contribution.
3. **Per-trade review:** original plan, reconstructed evidence, action-by-action /10 grades, post-exit path, and error classification.
4. **Loss Adjustment Exercise:** original versus adjusted compounded result and interpretation.
5. **System findings:** recurring strengths, recurring breaches, regime clues, and concrete process repairs.

Do not prescribe portfolio percentages, future position sizes, or a new strategy from this sample. Offer evidence-based process conclusions and identify what more data would change them.
