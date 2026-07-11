# Screening and Watchlist Doctrine

Screening discovers evidence-worthy US-listed leaders; it does not issue a buy decision. Keep the universe long-or-cash, exclude ETFs, ETNs, warrants, shorts, and TraderLion secondary/swing classes, and never turn a screen rank into a portfolio-allocation or position-sizing instruction.

Source tags distinguish authority: `[M]` is canonical Minervini/SEPA doctrine, `[TL]` is the subordinate TraderLion practice layer, and `[Synthesis]` is their adjudicated use in this harness.

## Candidate-generation architecture

- `[M]` Run several loose, simple screens in parallel. Do not build one giant discovery-time AND expression that erases a future leader for narrowly missing one of many preliminary fields.
- Treat each screen as an independent lens: price and volume expansion, relative strength, resilient Stage 2 structure, growth, recent-new-high proximity, or an emerging group can each surface a name.
- Keep a recurrence ledger with ticker, session, originating screens, and the evidence that caused each appearance. Repeated independent appearances raise manual-review priority because several lenses are seeing the same demand; recurrence is not itself an eligibility pass.
- During market weakness, favor stocks resisting the decline, holding higher lows while the indexes make lower lows, and sitting roughly 5-15% from a 52-week high. Never use a new-low list to hunt for apparent bargains.
- A previous-cycle leader is not presumed to lead again. Require current strength and a fresh Stage 2 structure; a familiar name in Stage 4 remains a broken leader, not a discounted candidate.
- Apply the canonical Stage 2 plus Trend Template eight-of-eight gate after loose discovery. The ban on a monolithic discovery screen never weakens this hard qualification AND gate.
- A known hard-gate failure makes a prospective buy `AVOID`; missing evidence makes it `INCOMPLETE`. Neither status may be improved by theme, valuation, narrative, or a different screen.
- Deterministic screens remove noise, but the final candidate review remains manual because setup quality, supply absorption, market alignment, and expected behavior do not collapse into one score.

## Funnel and workload discipline

`[TL]` supplies the operating counts below; `[M]` remains the eligibility authority.

1. Maintain a workable weekly universe of roughly 400-500 names assembled from the union of loose screens, not a permanent list of favorites.
2. A broad screen normally returns about 75-400 names; a specialist screen should normally return fewer than 50. These are calibration bands, not reasons to relax a hard gate.
3. Reduce the weekly first pass to about 75 names after deduplication and recurrence review.
4. Limit the weekly focus list to at most about 15 names through chart and evidence review.
5. Limit the daily focus list to 1-5 names whose next decision point can be stated clearly.

If the funnel is too large, tighten the preliminary lens or split it into meaningful independent lenses; do not add an arbitrary score. If it is too small, inspect unavailable data and market conditions before loosening criteria.

Record the result count for each unchanged screen over time. `[TL]` uses a contraction such as about 200 usual results falling to about 77 as an example of deteriorating breadth, but this is a within-screen comparison rather than a universal threshold and cannot declare the regime by itself.

## TIGERS review

Use `[TL]` TIGERS as a review organizer after candidate generation, never as a substitute for the SEPA gate:

- **T — Theme:** Is an identifiable industry or product wave attracting demand? Narrative research may describe it, but cannot provide missing market numbers.
- **I — Innovation:** Is a new product, service, process, or business model creating a plausible institutional catalyst?
- **G — Growth:** Are quarterly EPS or sales growing at least 25% year over year, preferably accelerating and potentially reaching triple digits? This preliminary flag does not replace the deeper Minervini earnings-quality review.
- **E — Edges:** Does the chart show more than one constructive edge, such as leadership, tightening supply, or unusual demand, without using a point total to waive a failed gate?
- **R — Relative strength:** Is the stock outperforming the market and its peers in the role appropriate to the measurement horizon?
- **S — Setup:** Is a valid setup forming with a definable pivot and failure level, rather than merely an attractive company or a rising price?

TIGERS can order manual attention among otherwise eligible candidates. Theme prominence, short-horizon strength, or an edge count may not admit a non-SEPA secondary, pre-profit, performance-enhancer, or squeeze name in v1.

## Portable field vocabulary

- **Closing range (CR) `[TL]`:** `(close - low) / (high - low) * 100`; above 50 means the bar finished in its upper half, and above 70 is a stronger close. A zero-range bar is unavailable, not 0 or 100.
- **Volume run rate:** projected regular-session volume divided by the selected average volume. For a completed daily bar, use actual volume divided by the same average. It is demand evidence, not an intraday entry tactic.
- **Average dollar volume:** the lookback average of each session's daily price multiplied by daily volume; keep the lookback and currency explicit.
- **ADR%:** use the value emitted by the volume module. Do not invent a replacement formula when the module cannot produce it.
- **Short-horizon strength percentile (AS):** a cross-sectional percentile over the named 1-week, 1-month, 3-month, or 6-month horizon. It is not the local self-historical RS proxy described below.
- **Industry rank:** lower rank numbers are stronger. Always state the horizon and universe rather than comparing unlike rank series.

All numeric recipe fields must come from `scripts/` output. Retry a failed module once and then mark that field unavailable; do not fill it from WebSearch, memory, or a differently defined vendor field.

## Vendor-neutral discovery library and hard gate

Run recipes 1-5 and 7 as separate `[TL]` candidate sources. Recipe 6 is the subsequent `[M]` hard gate, not a discovery lens; none of the other recipes can waive it.

### 1. Price-and-volume expansion

- Daily price change greater than 1.7%, price above $10, CR above 50, 50-day average volume above 200,000 shares, and 50-day average dollar volume above $3 million.
- Require either projected 50-day volume run rate above 120% during an open session or completed-day volume more than 20% above the 50-day average.
- Exclude funds and warrants. Treat the result as evidence of attention, not proof of accumulation or a valid entry.

### 2. Gap expansion

- Gap above 5%, 20-day volume run rate above 120%, and 20-day average dollar volume above $20 million.
- In this daily/weekly harness, a gap is a candidate-generation event. Do not import ORB, VWAP, or other intraday execution tactics.
- Do not chase a clinical-news biotech gap. By contrast, unexplained technical strength in a biotech or medical name may earn watchlist attention before the event is public; that exception admits observation, not a hard-gate pass or a fundamentals waiver.

### 3. Strong-close resilience

- Twenty-day average dollar volume above $5 million, 10-day ADR above 2.75%, CR above 70, and price above both the 50-day and 200-day SMAs.
- Add either 1-month cross-sectional strength above the 90th percentile or 3-month strength from the 85th through 100th percentile.
- This partial MA test is a loose lens only; it is not the eight-of-eight Trend Template.

### 4. Stage-leader survey

- Stage 2 or early Stage 2A, 20-day average dollar volume above $20 million, and either 1-month or 3-month cross-sectional strength above the 85th percentile.
- Add either an industry rank numerically below 25 over three or six months or 1-month strength above the 90th percentile.
- Re-run the canonical harness qualification because an external Stage label does not replace the Minervini stage implementation.

### 5. Growth-and-strength specialist

- Latest quarterly EPS growth above 25%, three-year average EPS growth above 25%, latest quarterly sales growth above 25%, and 6-month cross-sectional strength above the 80th percentile.
- Require price above $10, 50-day average volume above 100,000 shares, and price within 15% of the 52-week high.
- The 6-month strength field is a discovery/timing lens; only the canonical RS eligibility measure can satisfy the Trend Template RS criterion.

### 6. Canonical Trend Template qualification

This is the `[M]` hard gate, not another loose recipe. Use `scripts/.venv/bin/python scripts/pipeline qualify TICKER` rather than reproducing a vendor's near-equivalent template.

The eight criteria are all required: price above the 150-day and 200-day SMAs; 150-day SMA above the 200-day SMA; 200-day SMA rising for at least one month, with four to five months preferred; 50-day SMA above the 150-day and 200-day SMAs; price above the 50-day SMA; price at least 30% above the 52-week low; price within 25% of the 52-week high; and RS at least 70, with the 80s-90s preferred.

The historical `[TL]` recipe used a mandatory five-month monotonic 200-day SMA and a vendor 12-month RS field above 69. Do not substitute either near-equivalent for the canonical one-month rising-SMA minimum and `RS >= 70` definitions.

### 7. Weekend leader union

Begin with a liquid-leader shell of 20-day average dollar volume above $20 million, 10-day ADR above 2%, and price above $12.50. Within that shell, decompose the source's composite leader screen into parallel branches so it does not become a giant discovery-time AND filter:

- **Short-strength branch:** At least one of 1-month strength above 85, 3-month strength above 85, or 1-week strength above 90.
- **Growth confirmation branch:** recent and next-quarter EPS and sales growth above 20%, with EPS surprise above 40%.
- **Revenue-scale branch:** annual sales above $100 million and latest quarterly sales above $25 million.
- **Recent-IPO strength branch:** a review-period recent-IPO cohort with 1-month cross-sectional strength above 95. A source-era calendar cutoff is not a timeless rule, so make the cohort date explicit when this branch is used.

Take the union, record which branches surfaced each ticker, and give recurring names review priority. Still require the Minervini primary-base rules for a recent IPO and the normal hard gate before a prospective buy can advance.

## Relative-strength source and role discipline

Start with the project's unofficial `ibd-rs-rating` package output. It is the authoritative harness source for the cross-sectional 1-99 rating, but it is not the proprietary official IBD feed and its formula is not reimplemented here.

Use these commands from the repository root:

```text
scripts/.venv/bin/python scripts/modules/rs_ranking.py screen --min-rating 80 --limit 50
scripts/.venv/bin/python scripts/modules/rs_ranking.py score TICKER
scripts/.venv/bin/python scripts/modules/rs_ranking.py compare TICKER_A TICKER_B
```

- `screen` and `compare` require comparable backend ratings. If the backend is unavailable, do not fill an all-universe list or comparison with local proxies.
- `score` resolves one ticker in order: cached or live package rating, then the labelled `local_rs_line_proxy`, then `unavailable`.
- The local proxy uses the stock/SPY RS line, RS-day share, and self-historical 1-month, 3-month, 6-month, and 12-month percentiles. It is explicitly not a cross-sectional rank.
- Only the local proxy's 12-month historical percentile may provisionally carry the `RS >= 70` eligibility criterion. The shorter percentiles are timing evidence only.
- `[TL]` An RS-day share above 60% is corroboration only when its selected window is a documented market correction; it is not a standalone gate.
- Never rank multiple stocks by local proxy percentiles as though they shared a cross-sectional universe. If neither source is available, report RS and the affected qualification as unavailable.

`scripts/.venv/bin/python scripts/pipeline discover` supplies the backend's top RS names, five-day movers, sector ranks, and industry leaders alongside breadth evidence. Use these as candidate sources, preserve each source label, and retry once before declaring a section unavailable.

## Watchlist state machine

The watchlist states describe evidence maturity, not an instruction to commit capital:

### `watch`

- The ticker surfaced in one or more loose screens, showed resilience or unexplained technical strength, or remains on the radar after a stopped-out attempt.
- Qualification has not yet run or is `INCOMPLETE`, or qualification is `PROCEED` but no constructive setup and decision point exists yet.
- Record the screen origins, recurrence, current gate status, missing evidence, and the condition that would justify promotion.

### `buy-alert`

- Current qualification is `PROCEED`, and a constructive base or VCP is approaching a definable pivot or another permitted trigger.
- Required fundamentals are still being confirmed, market alignment is not yet sufficient, or breakout confirmation has not occurred.
- Record the chart-derived decision point early enough to complete the analysis before price reaches it; do not invent a universal alert offset.

### `buy-ready`

- Current qualification remains `PROCEED`; the setup, pivot, price/volume confirmation, catalyst, leadership profile and peer comparison, market context, and preplanned exit evidence converge now.
- Required fundamentals and the twelve-item final-candidate review must also converge, except that a VCP-qualified Power Play may omit verified fundamentals when explicitly labelled as the sole permitted fundamentals exception; it does not waive the other review legs.
- `buy-ready` is an analytical readiness verdict, not a sizing or allocation prescription, and an extended price is not ready merely because the company remains attractive.

Promote only on new evidence and demote when the gate, setup, market alignment, or evidence freshness deteriorates. `PROCEED` is necessary but not sufficient for `buy-ready`; `INCOMPLETE` remains watch with missing fields named, while a known gate failure is a current prospective-buy `AVOID` even if the ticker remains a future radar item.

## Re-entry after a stopped-out attempt

Executing the original stop is final for that attempt, but the ticker is not blacklisted. Return it to the radar, reassess current qualification and market evidence, and classify what failed before considering a fresh trigger. A known gate failure remains a current `AVOID`; otherwise use `watch` until a fresh setup earns promotion.

- **Base reset:** The base itself failed or lost its constructive supply-absorption structure. Require a completely new base, normally taking weeks, with a new pivot; a fast bounce cannot promote the ticker.
- **Pivot reset:** The attempted pivot failed while the larger base remains constructive. A new pivot can form within days after retightening and renewed evidence; do not reuse the old trigger automatically.
- A reset is a new decision. Never widen the previous stop, average down, or treat the desire to recover a loss as evidence.

## `/screen` workflow and sequential fallback

The workflow preserves the same evidence order whether fan-out is parallel or sequential:

1. Run one `discover` pass and read regime, breadth, and leader evidence. If the regime conclusion is hostile, stop qualification fan-out and return a watch-only report.
2. Build a deduplicated candidate list from user tickers and/or RS, sector, industry, and mover results. Preserve origin and recurrence, and honor the requested maximum; the workflow default is about 30.
3. In normal operation, assign one ticker per `ticker-scout` so each scout runs `qualify` and returns the compact gate schema without flooding the main analysis context.
4. If parallel fan-out is unavailable or constrained, invoke the same `ticker-scout` sequentially, one ticker at a time, using the same prompt and return schema. Collect and validate each result before starting the next; do not change criteria because execution is slower.
5. A scout retries a failed module once, then labels the affected evidence unavailable. A malformed or missing field remains incomplete rather than being inferred by the synthesizer.
6. If subagents are unavailable entirely, run `scripts/.venv/bin/python scripts/pipeline qualify TICKER` sequentially in the main context and preserve the same fields and retry rule.
7. Synthesize `PROCEED`, watch/incomplete, and avoid buckets, then apply the watchlist state machine. A `PROCEED` scout result does not by itself create `buy-ready`.

The fallback changes only scheduling. It never changes the Minervini-first universe, hard gates, funnel counts, source honesty, or no-sizing boundary.
