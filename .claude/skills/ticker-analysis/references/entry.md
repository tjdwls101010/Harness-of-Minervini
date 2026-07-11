# Entry and setup doctrine

Use this reference for prospective-buy timing only after the low-cost qualification gate. `[M]` denotes canonical Minervini doctrine; `[TL]` denotes a TraderLion practice-layer addition. The advanced `[TL]` section is opt-in and never replaces SEPA.

## Evidence sequence

Request deterministic evidence in this order, stopping when a hard failure makes deeper work unnecessary:

```text
scripts/.venv/bin/python scripts/pipeline qualify SYMBOL
scripts/.venv/bin/python scripts/modules/base_count.py count SYMBOL
scripts/.venv/bin/python scripts/modules/vcp.py detect SYMBOL
scripts/.venv/bin/python scripts/modules/volume_analysis.py analyze SYMBOL
scripts/.venv/bin/python scripts/modules/volume_analysis.py runrate SYMBOL
```

- The eight Trend Template criteria live in `pipeline qualify`; do not restate, soften, or recompute them in prose.
- A known Stage 2 or Trend Template failure rejects a prospective buy. Missing evidence produces an incomplete verdict, not an assumed pass or fail.
- Run the technical gate before fundamental research because price can reveal institutional withdrawal before the reported story changes.
- Stage 2 matters because the large advances in the Minervini record occur in the advancing and accumulating phase, while a long-term downtrend lowers the odds regardless of the narrative.
- A base within an established Stage 2 advance is a consolidation in that advance, not Stage 1 merely because price moves sideways.
- Treat the gate as eligibility, not a trade signal. Entry still requires constructive supply absorption, demand at the trigger, market alignment, and a predefined exit.

## Base maturity

- Count bases within the current Stage 2 advance, not across unrelated price cycles.
- Bases one and two are the prime zone, especially after a market correction; a third base can remain tradable.
- Bases four and five are late-stage warnings because abrupt failures become more common as the advance matures.
- Base count supplies context rather than a verdict by itself. Combine it with price and volume, fundamentals when required, and current market evidence.
- A stock can terminate through a parabolic climax without completing a neat late base, so do not force every mature leader into the count sequence.
- The flat base is a distinct constructive shape: roughly four to seven weeks sideways, correcting only about 10–15%, with the buy trigger a move above the base high. It refuses to give ground while time passes, which is itself supply-absorption evidence.

## VCP: read the supply footprint

- Write a VCP footprint as `<weeks>W <maximum-depth%>/<final-contraction%> <contraction-count>T`; `40W 31/3 4T` means forty weeks, a 31% maximum correction, a 3% final contraction, and four contractions.
- Read the three footprint dimensions as time, price, and contraction symmetry. A pattern name without those dimensions is not sufficient evidence.
- A valid VCP normally contains two to six contractions, most often two to four, with each contraction roughly half the preceding one within a reasonable range; `25% → 15% → 8%` is the canonical model, and VIVO's actual `31% → 17% → 8% → 3%` four-contraction series (footprint `40W 31/3 4T`, $18 pivot) is a real instance of the same halving character.
- Shrinking price volatility must be accompanied by drying supply. The final contraction must show volume below the 50-day average, including one or two exceptionally quiet sessions.
- The contraction sequence represents strong hands absorbing weak-hand supply. As available stock diminishes, less demand is needed to move price through the line of least resistance.
- A constructive ordinary base is generally 10–35% deep and three to sixty-five weeks long. Reject a correction of 60% or more; depth near 50% is reserved for an exceptional broad bear-market context, not normalized. The reason deep bases fail is overhead supply: a deeper correction traps more break-even sellers waiting above and invites dip-buyers to take profits into any bounce, so the eventual breakout must chew through two seller cohorts. That is why ~50% is tolerable only when a broad bear market forced the depth on an otherwise resilient name.
- Compare the stock with the market over the same interval. Avoid a candidate that declines more than roughly two to three times the market. CRUS's 23% correction against a 10% market decline (2.3:1) sat at the tolerable inclusive edge of that band before it resolved into a valid 3C turn.
- Time is part of supply absorption. A V-shaped or time-compressed right side is not ready merely because price returned to resistance; strong hands have not had enough time to replace weak holders.
- Do not anticipate the unfinished pattern. The default entry is a completed VCP pivot breakout or a VCP-anchored cheat whose own turn has resolved upward.

## The last weak hand and the turn

- One to three shakeouts inside the base can improve a setup by forcing clustered stops and removing weak holders before the real move.
- The objective is to enter after the final weak-hand event has resolved, not to predict the low while forced selling is still active.
- An undercut in progress is not a buy signal. Wait for price to reclaim or otherwise complete the upward turn with contracting supply and visible demand.
- A familiar support level can attract clustered stops just below it; the flush only becomes useful evidence after price demonstrates that sellers can no longer keep it below the level.
- Interpret what price has completed. Do not promote an expected reclaim, anticipated accumulation, or unfinished right side into evidence.

## Pivot execution and demand confirmation

- Anchor the decision to the final-contraction pivot. Wait for price to trade five to twenty cents above it rather than treating a one-cent print as confirmation.
- Demand must accompany the breakout: volume should exceed the stock's own 50-day average, with 50% above average as the strict form. More volume strengthens the evidence.
- Price supplies the trigger and volume confirms it. Do not wait for the closing print merely to know the full-day total; use the intraday run-rate diagnostic while the session is active.
- `volume_analysis.py runrate` extrapolates current regular-session volume from elapsed session time and is deliberately cache-exempt. Treat it as a pace estimate, not completed volume.
- `[TL]` The default chase ceiling is 1.5% above the pivot. If price is already farther extended, decline the entry and wait for a new low-risk structure instead of converting momentum into poor asymmetry.
- Never let an attractive breakout waive the Stage 2 and Trend Template gate, market alignment, or the planned failure level.
- Adapt the entry tactic to the market's character: in a strong, trending regime, buy the pivot breakout as it happens; in a choppy, whipsaw regime, prefer a pullback or undercut-reclaim entry into a defined level, because raw breakouts fail more often when the broad tape is not carrying them.

## Breakout response: squat, tennis ball, and reset

- A pivot retest is common: roughly half of even the best breakouts revisit or briefly undercut the pivot. That behavior is not an automatic failure while the original hard stop remains intact.
- A squat occurs when a breakout is pushed back into the range or closes below the breakout high. If the hard stop has not fired, allow one or two days for reversal and recovery; documented examples extend the observation window to roughly ten days, not indefinitely.
- A close below the 20-day moving average reduces the odds of a healthy post-breakout response and demands stricter judgment.
- A tennis-ball response is a low-volume pullback to the pivot area followed by a forceful return to new highs within several days to one or two weeks, preferably with renewed volume on the recovery.
- Widening, increasingly erratic action is the opposite of a healthy recovery. Do not relabel deterioration as a shakeout merely to preserve the thesis.
- Classify the failure before considering re-entry. A failed base needs an entirely new base and usually weeks of repair; a failed pivot can form a superior reset within days if the larger base remains intact.
- A stopped-out ticker is not permanently blacklisted. Re-entry must be earned by a completed reset, not justified by attachment to the original idea.

## Specialized Minervini setups

### 3C cup-completion cheat `[M]`

- Require a prior advance of at least 25% within the preceding three to thirty-six months; stronger candidates often approach 100%, and the strongest documented examples advanced 200–300%.
- Require price above a rising 200-day moving average and a pattern lasting three to forty-five weeks, most often seven to twenty-five weeks.
- The cup correction is normally 15–40%; allow up to about 50% only in a hostile broad market and reject collapse beyond 60%.
- After recovering roughly one-third to one-half of the preceding decline, require a tight plateau only 5–10% from high to low.
- Buy only the plateau-high break that completes the turn, ideally after the pause has drifted into a shakeout and then shown tight price with exhausted volume.
- A 3C is a VCP-anchored early entry, not permission to buy the unfinished bottom or waive required fundamentals.

### Power Play `[M]`

- Require a dormant stock to surge at least 100% in fewer than eight weeks on exceptional volume.
- Require a three-to-six-week flag lasting at least twelve trading days, with a correction no deeper than 20–25%.
- Require either an exceptionally tight structure of 10% or less or a clear VCP; without contraction evidence it is not a Power Play entry.
- A VCP-qualified Power Play is the sole permitted exception that may proceed without verified fundamentals. Label every use explicitly as the fundamentals-only exception.
- The exception waives only verified fundamentals. Stage 2 and Trend Template eligibility, VCP-quality price and volume, market alignment, the pivot trigger, and risk controls remain mandatory.

## Primary base for a recent IPO `[M]`

- Treat a primary base as the newly listed company's first buyable base, not as an excuse to buy immediately after the offering.
- Require roughly two months of trading history and a correction lasting at least three weeks; some companies need a year or more before supply is absorbed.
- Apply depth by duration: a three-week base may correct no more than 25%; a base of roughly three to five weeks or longer may correct 25–35%; a base lasting about a year can remain valid with a correction up to roughly 50%.
- The trigger is emergence to an all-time high, not merely a 52-week high. A constructive consolidation near the all-time high still needs the high-price breakout for market confirmation.
- Excess depth combined with the absence of a qualifying base is a hard disqualification. FB in 2012 is the documented failure pattern: a 43% decline only twelve days after listing did not create a buyable primary base.
- The primary-base rules add an IPO-specific structure test; they do not convert unavailable Trend Template evidence into a pass. Keep an insufficient-history candidate incomplete or watch-only until the binding gate is satisfied.
- A valid structure improves probability but never guarantees success, so the entry still requires a predefined exit plan.

## Advanced daily tactics — explicit `[TL]` opt-in only

This entire section is inactive unless the user explicitly requests the TraderLion practice layer. Standard SEPA remains a completed pivot breakout or VCP-anchored cheat. Every opt-in tactic still requires the Stage 2 and Trend Template hard gate, a larger constructive setup, a precise trigger, and an objective failure level.

### Post-breakout add-on sequence `[TL]`

- A quick retest of the 10-day SMA can offer the first additional-entry decision after a sound breakout.
- After a one-to-three-week rest, convergence with the 21 EMA can provide the next decision point.
- After a long-base breakout, the first touch of the 50-day SMA or ten-week line is the highest-quality deeper pullback in this sequence; second and third tests are progressively weaker evidence.
- A calendar or moving average alone never authorizes the addition. Demand recovery and the integrity of the original setup must still be visible.

### RS-gated moving-average pullback `[TL]`

- Use only an average that the stock has demonstrably respected; approach near the line and define failure beneath the same structure.
- Require relative-strength evidence before considering the pullback. The canonical signature is a market lower low while the stock holds a higher low.
- A brief undercut can be tolerated only after demand recovers. Failure is the stock bouncing from the average and then rolling back through it.
- This tactic does not permit blind buying of a falling stock and does not exchange the 10/21 EMA management role with the 50/150/200 SMA eligibility role.

### Undercut-reclaim `[TL]`

- Let a meaningful support level, such as the base low or 50-day SMA, be undercut and then strongly reclaimed before acting.
- The reclaimed level is the trigger anchor; losing it again is the tactic's failure evidence.
- Prefer a reclaim that demonstrates trapped sellers were overwhelmed by returning demand.
- This tactic operationalizes the Minervini shakeout mechanism but does not change its sequencing rule: an undercut still in progress is never an entry.

## Decision summary

- Reject on any known hard-gate failure, an invalid lifecycle, excessive or time-compressed structure, an unconfirmed turn, or an overextended entry.
- Mark incomplete when deterministic evidence is unavailable; do not manufacture a pass from visual opinion or web data.
- Mark watch-only when the candidate is strong but still needs a completed contraction, reclaim, pivot, volume confirmation, or binding eligibility evidence.
- Consider an entry only when eligibility, supply absorption, trigger, demand, market alignment, and risk definition converge; the sole missing-fundamentals path is the explicitly labeled VCP-qualified Power Play.

## Doctrine hierarchy

Treat `[M]` as canonical SEPA doctrine. Use `[TL]` only where explicitly tagged and requested as an opt-in practice layer; when the two differ, the Minervini rule controls.
