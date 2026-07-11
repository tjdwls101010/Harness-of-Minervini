# Sell and position-management doctrine

Use this reference for an existing-position sell or hold decision and for defining the exit plan before a prospective entry. `[M]` is the controlling Minervini doctrine; `[TL]` supplies tagged gap-fillers and explicitly adjudicated defaults, always subordinate when the two conflict. Judge the ticker and its evidence, never prescribe portfolio percentages or position size.

## Evidence before judgment

Obtain dates, prices, moving-average states, drawdowns, and earnings proximity from the deterministic modules. Do not reconstruct missing values from memory, a web page, or visual estimation.

```text
scripts/.venv/bin/python scripts/modules/stage_analysis.py risk SYMBOL
scripts/.venv/bin/python scripts/modules/sell_signals.py extension SYMBOL --base-top PIVOT
scripts/.venv/bin/python scripts/modules/sell_signals.py reversal SYMBOL --base-top PIVOT --breakout-date YYYY-MM-DD
scripts/.venv/bin/python scripts/modules/sell_signals.py trail SYMBOL --ma 21e --start YYYY-MM-DD
scripts/.venv/bin/python scripts/modules/sell_signals.py trail SYMBOL --ma 50s --start YYYY-MM-DD
scripts/.venv/bin/python scripts/modules/sell_signals.py cascade SYMBOL --start YYYY-MM-DD
scripts/.venv/bin/python scripts/modules/actions.py get-earnings-dates SYMBOL --days-until
```

Supply a prior-high anchor and tolerance to `cascade` only when the chart or user provides an honest anchor. A module's `needs_input`, `needs_chart`, or unavailable result stays unresolved; it is not a pass. Retry a failed command once, then identify the evidence gap.

## The controlling risk spine `[M]`

### Define risk before reward

- Let one `R` equal the distance from the entry to the original hard stop. Preserve that original distance when comparing expected reward, open profit, and realized results.
- Derive the ticker-level initial stop from the trader's own realized record: `stop_pct = min(0.5 × realized_average_gain_pct, 10%)`. The half-average-gain rule is a feedback loop, while 10% is an absolute ceiling rather than a target.
- Keep realized average losses near 6–7%. A single ordinary loss must not be allowed to consume the average winner.
- If the trader's realized average gain is unavailable, say that the calibrated stop cannot be computed. Do not invent a substitute statistic or treat the 10% ceiling as the recommended stop.
- Require expected reward of at least 2R and prefer 3R. The method assumes ordinary win rates around 40–50%, so payoff asymmetry—not a promise of frequent correctness—must carry expectancy.
- At 3R, defend at least breakeven. A position that has earned several times its initial risk must not be allowed to become a loss.

### Execute loss controls without negotiation

- Write the stop before entry and execute it when reached. Do not postpone it for a story, good fundamentals, an analyst opinion, or hope for a rebound.
- If a gap or fast decline crosses the stop, sell at the next available quote. Waiting for price to return to the skipped stop converts bounded risk into an unbounded negotiation.
- Never widen a stop because the stock or market has become more volatile. The anti-ATR rule is deliberate: increasing the loss side breaks the payoff arithmetic when the win rate is below 50%.
- In a hostile market, tighten the ticker-level stop rather than widen it; the adverse-market operating range is roughly 5–6%. Demand quicker progress and be readier to take available gains.
- Repeated stop-outs diagnose either poor entry quality or a hostile/immature regime. Correct the setup selection, reduce activity, or wait in cash; never cure the feedback by granting every trade more room.
- Never average down. A proper entry that immediately loses ground has become less attractive because price is rejecting the thesis.

### Treat behavior and time as evidence

- Define expected behavior before entry. A correctly selected leader should act promptly; failure to make the expected progress can justify an exit even before the price stop is touched.
- Treat profits as principal, not house money. An appreciated position receives no extra downside allowance merely because part of the value is an unrealized gain. This is why an exit plan is not optional: superperformance stocks give back roughly 50–70% of the advance on average, about a third surrender the entire gain, and bubble names can retrace 80–90% and take years to recover — an unrealized profit left undefended is a loss waiting to be realized.
- Detect the involuntary-investor error: if the original short- or intermediate-term reason no longer holds, do not rename the position a long-term investment to avoid realizing a loss. Ask whether the position would be initiated today with the same evidence and risk.
- A stop-out does not blacklist the ticker. Re-entry requires a fresh valid setup, a new risk/reward assessment, and price confirmation; it is not permission to chase the old thesis.

### Respect lifecycle deterioration

- Run `stage_analysis.py risk` for the largest completed daily and weekly decline since the Stage 2 advance proxy began. A new maximum decline is a sell signal in most cases, even when it occurs immediately after apparently good earnings.
- Respect abnormal price deterioration before the public explanation arrives. Reported fundamentals and reassuring management language cannot overrule a major Stage 2 break.
- Do not duplicate or visually approximate this drawdown test in prose; `stage_analysis risk` is its single deterministic owner.
- `[M]` Before the max-decline day confirms the top, read the Stage 3 distribution signature — the hand-off from strong hands to weak hands: expanding day-to-day volatility, erratic wide swings, the 200-day line beginning to flatten, and heavy-volume down days outnumbering up days. This qualitative read usually precedes the deterministic max-drawdown and corroborates it; treat it as a reason to tighten and prepare the exit, not as a replacement for the `stage_analysis risk` signal.
- `[M]` A brokerage upgrade or raised price target arriving on a Stage 3/4 or already-broken leader is a red flag, not reassurance — often a short-candidate marker. Institutions distribute before the sell-side turns cautious, so the tape is the verdict, not the analyst rating (CMG in 2012 was upgraded near $400 shortly before roughly a 40% three-month decline). Never let a fresh upgrade or target convert an abnormal price break into a reason to hold.

## Daily audit and contingency rehearsal `[M]`

At every completed session, ask: Is the original thesis still valid? Did price behave as expected? Has the stop, reward/risk relationship, Stage 2 structure, or earnings-event risk changed? If the evidence no longer supports a bullish answer, state why the position is still held or recommend the appropriate exit action.

Before each market session, rehearse four plans for every position:

1. **Initial-stop plan:** Record the exact invalidation price, the evidence it represents, and the immediate execution response, including gap-through handling.
2. **Re-entry plan:** Define what reset or new setup would make the stopped ticker eligible again; a rebound alone is insufficient.
3. **Profit-sale plan:** Define the R-based defense, any sell-into-strength evidence to monitor, and the price-based trailing method before emotion is involved.
4. **Disaster plan:** Define how to act through a gap, an SEC-investigation gap-down, power loss, or an internet outage.

Premarket rehearsal turns each response into a procedure rather than an intraday debate. Add genuinely new failure scenarios to the playbook after they occur.

## Tagged sell-into-strength tools `[TL]`

These instruments fill a mechanical gap in the Minervini corpus. They are observations that inform an R-controlled decision, not independent permission to ignore a hard stop.

### Base extension and RME

- `[TL]` A price roughly 20–25% above the relevant base top or pivot enters a common pause/consolidation zone. Treat it as a prompt to evaluate selling into strength, not an automatic full exit and not a generic distance-from-any-MA threshold.
- `[TL]` Relative Measured Extension near 100 is an overextension warning relative to the stock's own moving-average history. Use it only when an approved deterministic source supplies it; do not invent or hand-calculate a missing RME value.
- `[M]` Read the climax / blow-off signature as a distinct `[M]` sell-into-strength trigger, not a variant of the `[TL]` RME above: after a long advance, a sharp parabolic acceleration extended far above the 50-day MA with expanding daily ranges is exhaustion, not strength. Take it from the `climax_extension` block that `sell_signals.py extension` and `stage_analysis.py risk` emit (percent above the 50-day MA, weeks of advance, range expansion); the measured `heuristic_climactic` flag surfaces the pattern, but the exhaustion judgment — a sharp late-stage run versus early post-breakout power — is yours.
- Early power immediately after a breakout is not the same as late, exhausted extension. Combine distance with lifecycle, velocity, volume, and reversal evidence.

### Six-item key-reversal checklist

Run `sell_signals.py reversal` and evaluate confluence. One item alone is not a universal sell verdict, and unresolved visual or anchor-dependent items remain unresolved.

1. `[TL]` The stock is at a high and visibly extended from its relevant moving averages.
2. `[TL]` It gaps up, fills the gap, and reverses.
3. `[TL]` It breaks the trendline drawn from the recent highs.
4. `[TL]` It prints abnormal volume or the largest volume since the breakout.
5. `[TL]` It prints the widest price-range bar since the breakout.
6. `[TL]` It reverses below the prior day's low and closes in the lower part of its range.

More aligned items after meaningful extension strengthen the sell-into-strength case. Use a rendered chart only to resolve the qualitative items; deterministic numbers remain controlling.

## Tagged moving-average management `[TL]` / `[TL-Kell]`

- `[TL]` The mechanical baseline is two completed closes below the selected management average. Use the 21-day EMA for a swing-management horizon; the `[TL-Kell]` 50-day SMA is the approved position-management trail — the one explicit exception that reuses an eligibility-stack average for trade management.
- `[TL]` Treat the first close below the line as a warning and the second qualifying close as the baseline trigger. Report the dated sequence and close quality instead of relying on a current-chart snapshot.
- `[TL]` The 21 EMA and the `[TL-Kell]` 50 SMA manage an already eligible trade; they never replace the 50/150/200 SMA stack used for SEPA eligibility and Stage analysis.
- `[M]` A hard price stop and the 3R breakeven rule remain controlling. The two-close convention cannot delay an already-triggered hard stop.

## Failure cascade `[TL]`

Read the cascade as a dated deterioration sequence:

1. Loss of the 21-day EMA is the first failure signal.
2. Loss of the 50-day SMA confirms deeper deterioration.
3. A downside reversal at or near the prior high after a retest confirms the failed retest/top. This is not a reversal below the prior low.
4. Loss of the 200-day SMA is the terminal state of the cascade.

Run `sell_signals.py cascade` and state the highest evidenced stage, its dates, and any missing prior-high anchor. Do not jump from a lone 21 EMA close to a completed cascade, and do not substitute the key-reversal checklist's prior-low item for the cascade's prior-high failed retest.

## Earnings-event policy

- `[TL, hard harness rule]` Do not open a new position immediately before a scheduled earnings report. Use `actions.py get-earnings-dates --days-until`; an unknown report date is an evidence gap, not proof that the event is distant.
- `[TL, beginner default]` Reduce event exposure before the report rather than treating a binary gap as an ordinary technical risk. This reference deliberately does not prescribe a percentage.
- `[M, experienced discretion]` A position with a meaningful profit cushion may be managed through the report under a written disaster plan, while a thin or absent cushion argues for defense. Cushion-based discretion never permits widening the hard stop after the event.
- `[M]` After the report, judge the price response. A largest decline of the Stage 2 advance remains a sell signal even when the headline results look strong.

## Referee for conflicting triggers

- `[TL]` A +5% gain is a beginner-mode simplification for initiating profit defense; it is an absolute percentage, not an R calculation.
- `[M, controlling]` When +5% and the trade's R-multiple imply different actions, the R-multiple wins. Preserve the 2R–3R payoff structure and the 3R breakeven rule rather than optimizing for a fixed headline gain.
- No signal in this reference determines portfolio allocation or position size. Return a ticker-level sell, hold-with-conditions, or incomplete-evidence judgment with the stop, trigger, date, provenance tag, and unresolved evidence stated explicitly.
