# Skills & Usage

How the three analyst skills fire, what each one does step by step, the modules it drives, and how the `/screen` workflow and `ticker-scout` agent tie a market sweep together.

The harness routes your request to exactly one of three intent-split skills. Each is a `SKILL.md` under `.claude/skills/` that loads only when its trigger matches, keeping [the always-loaded constitution](Architecture.md) lean. Two of the three inject the current session clock at load time and read controlling reference files before any verdict, so Claude reasons over this harness's Minervini-first adjudications rather than its training priors. For the deterministic engine those skills call, see [the module substrate](The-Module-Substrate.md); for the doctrine they enforce, see [The Minervini Method](The-Minervini-Method.md).

This page is analysis and education, not financial advice. See the [FAQ & Disclaimer](FAQ-and-Disclaimer.md).

## Routing at a glance

| Your intent | Skill | Not this skill because… |
|---|---|---|
| How is the market? What's strong? Find leaders / build a watchlist | `market-scan` | A judgment about named tickers routes to `ticker-analysis` |
| Should I buy / sell / hold TICKER? Is this a good entry? Compare A vs B | `ticker-analysis` | Market-wide, screening, or leader-finding routes to `market-scan` |
| Grade my completed trades / trade log; what does my record reveal? | `trade-review` | A live position or prospective decision routes to `ticker-analysis` |

Three near-misses worth internalizing:

- "Is XYZ a buy here?" is single-ticker judgment → `ticker-analysis`, even though it feels like screening.
- "Find me strong semiconductor names" is discovery → `market-scan`, even though the output is a list of tickers.
- "Was selling XYZ last month the right call?" is a completed post-mortem → `trade-review`, but "should I still hold XYZ?" is a live position → `ticker-analysis`.

Across all three, portfolio sizing and allocation percentages are out of scope. The skills offer setup, risk, and evidence-quality analysis instead of a position size.

---

## market-scan

Analyze the US market regime, breadth, sector or industry strength, leadership, screening results, discovery, breakouts, and watchlists.

### When it fires

It triggers whenever you ask how the market is, what areas are strong, to find stocks or leaders, or to build or refresh a watchlist — even if you never say "Minervini." It deliberately does **not** fire for a buy/sell/hold/timing/diagnosis judgment about one or a few named tickers (that routes to `ticker-analysis`), for grading your completed trades (`trade-review`), or for portfolio sizing (out of scope).

### Procedure

At load, the skill injects `scripts/.venv/bin/python scripts/modules/market_clock.py` so Claude anchors to the current ET session and cache context rather than a KST calendar date. It then works through four movements from the `SKILL.md` body:

1. **Ground the analysis.** Read `references/regime.md` before any regime conclusion and `references/screening.md` before discovering, filtering, ranking, or changing a watchlist. WebSearch is allowed only for current narrative or catalyst context — never for prices, breadth, RS, dates, or financial values.
2. **Establish the environment.** Run `scripts/.venv/bin/python scripts/pipeline discover`, then inspect every section independently — Finviz breadth, the QQQ switch, RS leaders and movers, sector ranks, industry leaders, and provenance. Retry a failed section once, then preserve its `unavailable` state. Apply the dual gate: QQQ-versus-21EMA is `[TL]` environmental information, while `[M]` leader quality and actual trade traction decide whether a stronger conclusion is earned.
3. **Reach a regime conclusion.** Distinguish `observation`, `probe`, `earned expansion`, `defense`, `cash`, and `incomplete evidence` — not a vague bull/bear label. A QQQ `ON` transition alone cannot authorize favorable exposure; a QQQ `OFF` alone cannot force liquidation. State the evidence that would refute the read.
4. **Discover and qualify.** Take the union of several loose screens, keep funnel counts visible, dedupe, and honor the requested maximum. If the regime is hostile, return a watch-only report instead of a broad fan-out. Otherwise run one `ticker-scout` per retained ticker (or prefer the fixed `/screen` workflow), then bucket candidates as `PROCEED`, `watch/incomplete`, or `AVOID` and apply the watch → buy-alert → buy-ready state machine.

### Modules and references it drives

| Reads | Drives |
|---|---|
| `references/regime.md`, `references/screening.md` | `market_clock.py` (injected), `scripts/pipeline discover`, `rs_ranking.py screen` / `score` / `compare`, `ticker-scout` fan-out, the `/screen` workflow |

`rs_ranking.py` is used only in its defined roles: `screen` and `compare` need comparable backend ratings (no local-proxy substitution across a universe), and `score` resolves one ticker as cached/live package rating → labelled `local_rs_line_proxy` → `unavailable`.

### Output contract

Five sections, in order:

1. **Session and source health** — ET session, last completed session, cache state, unavailable sections.
2. **Regime evidence** — QQQ information filter, leader gate, trade feedback, dual-gate conclusion, refutation conditions.
3. **Funnel** — source counts, deduplicated count, qualification count, final bucket counts.
4. **Watchlist** — per ticker: state, qualification verdict, RS source and score, Stage, originating screens, one-line evidence, missing evidence, and the next promotion/demotion condition.
5. **Narrative context** — only sourced context that explains, never replaces, module evidence.

### Worked example

> **You:** How does the market look right now, and are there any strong leaders worth watching?

Claude reads the injected clock, reads `regime.md` and `screening.md`, runs `scripts/pipeline discover`, and returns something shaped like:

```text
Session & source health: Last completed US session 2026-07-10; cache warm; all sections available.
Regime: QQQ ON vs 21EMA (info only). Leaders firm, breakouts holding → conclusion: PROBE, not earned expansion.
   Refutation: two failed breakouts + shrinking unchanged screen would flip to DEFENSE.
Funnel: 312 union → 71 deduped → 18 qualified → 5 PROCEED / 9 watch / 4 AVOID.
Watchlist:
   NVDA  buy-alert  PROCEED  RS 96 (ibd pkg)  Stage 2  [pv-expansion, stage-leader]  pivot ~ base high; confirm on volume
   ...
```

---

## ticker-analysis

Analyze one or a few named US-listed stocks for a prospective buy, entry timing, setup diagnosis, an existing-position sell/hold judgment, re-entry, earnings risk, or a chart condition — including a head-to-head comparison (gate each ticker, then compare).

### When it fires

It triggers whenever you ask what to do with a specific US-listed ticker, even without naming Minervini. It does **not** fire for market-wide, sector, screening, leader-finding, or watchlist requests (→ `market-scan`) or for grading a completed trade (→ `trade-review`). Crypto and non-US listings are out of scope — the skill states the boundary instead of analyzing them.

### Procedure

The clock is injected at load. Claude first identifies the branch — a prospective buy/diagnosis, an existing position, or both — and reads references as a **chain, not a menu**, so favorable material can never bypass an unfavorable gate.

**Reference routing:** read `references/entry.md` before interpreting a gate, setup, pivot, or price/volume; read `references/fundamentals.md` only after the hard gate passes; read `references/sell.md` before any exit plan and before every sell/hold verdict.

**Prospective buy or diagnosis:**

1. Run `scripts/.venv/bin/python scripts/pipeline qualify TICKER` first (retry once on failure).
2. A known gate failure produces `AVOID`; an unavailable required criterion produces `INCOMPLETE` (name the missing evidence — do not turn absence into failure or permission).
3. On `PROCEED`, earn the entry review with parameterized calls: `base_count.py count`, `vcp.py detect`, `volume_analysis.py analyze` (and `volume_analysis.py runrate` only for an active-session pivot).
4. Use `entry_patterns.py` only when you explicitly opt into the `[TL]` daily-tactic layer; it cannot waive SEPA eligibility or its own completed trigger.
5. Run the earnings/margin/surprise/revision/valuation/category/catalyst/leadership review from `fundamentals.md`, get market alignment from a fresh `scripts/pipeline discover`, then write the invalidation, reward/risk, earnings-event policy, and contingency plan from `sell.md` **before** any favorable entry verdict.
6. Require probability convergence across eligibility, entry structure, price/volume, fundamentals and catalyst, leadership, market, and risk. A VCP-qualified **Power Play** is the sole fundamentals exception — label it explicitly and waive only verified fundamentals; every other convergence leg still holds.

**Existing position — sell or hold:**

1. Record entry date/price, original stop, management horizon, breakout/pivot context, and any base top or prior high; keep anchor-dependent evidence unresolved if a value is absent.
2. Run `qualify` for structural context, but never stop the sell analysis because a prospective-buy gate failed — a failed gate can be urgent holding evidence.
3. Read `references/sell.md`, then run the applicable evidence: `stage_analysis.py risk`; `sell_signals.py extension` / `reversal` / `trail` / `cascade`; and `actions.py get-earnings-dates --days-until`.
4. Evaluate hard stop and gap-through first, then Stage deterioration, expected-behavior failure, 3R defense, tagged sell-into-strength, MA management, the failure cascade, and earnings risk.
5. Return `SELL`, `HOLD WITH CONDITIONS`, or `INCOMPLETE` with dated triggers and provenance.

**Chart corroboration:** render a daily/weekly PNG with `chart_render.py` when a qualitative feature is ambiguous; read weekly before daily, treat MAs as zones. Charts corroborate — they never override a deterministic gate.

### Modules and references it drives

| Reads | Drives |
|---|---|
| `references/entry.md`, `references/fundamentals.md`, `references/sell.md` | `market_clock.py` (injected), `scripts/pipeline qualify`, `scripts/pipeline discover` (market alignment), `base_count.py`, `vcp.py`, `volume_analysis.py`, `entry_patterns.py` (`[TL]` opt-in), `stage_analysis.py`, `sell_signals.py`, `actions.py`, `chart_render.py` |

### Output contract

Six sections, in order:

1. **Verdict and scope** — branch, current verdict, whether evidence is complete.
2. **Hard-gate context** — Stage, Trend Template, RS source and score, failed criteria, unavailable criteria.
3. **Entry or holding evidence** — setup state, pivot/anchors, price/volume, dated sell events, chart corroboration where used.
4. **Fundamentals and leadership** — category, catalyst, earnings phase, quality, revisions, group context, or a labelled Power Play exception.
5. **Market and risk convergence** — regime evidence, invalidation, reward/risk, earnings date, contingency conditions.
6. **Next decision point** — the exact evidence that promotes, demotes, invalidates, or confirms the current state.

Prospective maturity uses watch → buy-alert → buy-ready, but readiness is never translated into a percentage or position size.

### Worked example

> **You:** Is NVDA a buy here? I don't have a position yet.

Claude runs `qualify NVDA` first. If the hard gate passes it earns deeper calls (`vcp.py detect`, `volume_analysis.py analyze`), checks fundamentals and market alignment, and writes an exit plan before any favorable verdict:

```text
Verdict & scope: Prospective buy. PROCEED at the gate; entry NOT yet buy-ready (evidence complete).
Hard gate: Stage 2, Trend Template 8/8, RS 96 (ibd-rs-rating pkg, 2026-07-10). No failed/unavailable criteria.
Entry evidence: VCP footprint 3W 2T, last contraction ~6%, pivot at 178.40; volume dry-up into the apex.
Fundamentals/leadership: Market leader; EPS accel, positive revisions; group strength intact.
Market & risk: Regime PROBE. Invalidation 172.10 (below pivot low) → ~3.5% risk; reward/risk ~3:1. Earnings in 22d.
Next decision point: A high-volume close above 178.40 promotes to buy-ready; loss of the apex low demotes to watch.
```

If instead `qualify` returned a known failure (say, price below a falling 200-day SMA), the verdict is `AVOID` and no amount of narrative or valuation rescues it.

---

## trade-review

Grade, review, or post-mortem your own completed US-stock trades — winners, losers, entries, exits, rule adherence, R-multiples, batting average, hold-time asymmetry, post-exit behavior, and the Loss Adjustment Exercise.

### When it fires

It triggers whenever you supply past trades or ask what your record reveals. It does **not** fire for a prospective decision or a live position (→ `ticker-analysis`), for screening or leader-finding (→ `market-scan`), or for portfolio sizing. Note this skill's tools deliberately exclude WebSearch — grading evidence is reconstructed deterministically or marked unavailable.

### Procedure

This is a process audit, not a retrospective prediction contest: a profitable rule violation can be a poor decision, and a clean small loss can be excellent execution.

1. **Load grading doctrine.** Read `../ticker-analysis/references/entry.md` before grading entries and `../ticker-analysis/references/sell.md` before grading stops, exits, and management. Do not duplicate or alter that doctrine.
2. **Require input.** For each trade seek ticker, entry/exit dates and prices, initial stop, action sequence, and the stated plan. Missing entry/exit price ⇒ return unavailable; missing stop ⇒ `R` and stop-discipline grades unavailable (never reconstructed from a later chart). An open trade routes to `ticker-analysis`.
3. **Select the review set.** Compute each trade's % return, then review the top five winners plus bottom ten losers first; go deeper only if time remains.
4. **Reconstruct evidence deterministically.** Use `scripts/.venv/bin/python scripts/modules/info.py get-history TICKER --start YYYY-MM-DD --end YYYY-MM-DD` for the window, and `sell_signals.py trail TICKER --ma 21e --start YYYY-MM-DD` (or the 50s variant, or `cascade --start`) for exit management. **Do not** grade a past action with current-only modules such as `stage_analysis.py risk` or `vcp.py detect` — without an as-of cutoff they leak later evidence into the score.
5. **Grade each action** — entry, initial risk, adds/re-entries, profit management, and final exit — separately on a 1–10 scale, each with a one-sentence citation to a named reference criterion. Never grade from P&L alone; state explicitly when a winner scored low or a loser scored high.
6. **Report portfolio-level metrics without portfolio advice** — batting average (excluding the −1% to +1% scratch band), average/median winner and loser, payoff ratio (2:1 minimum, 3:1 preferred), per-trade and average `R` from the original stop only, maxima, and winner/loser hold times.
7. **Run the Loss Adjustment Exercise `[M]`** — recompute the sequence with every loss set to exactly 10% (raise smaller, reduce larger), keep winners and order unchanged, and compare compounded returns. This diagnoses whether uncontrolled losses destroyed expectancy; it does **not** authorize a 10% default stop.

### Modules and references it drives

| Reads | Drives |
|---|---|
| `../ticker-analysis/references/entry.md`, `../ticker-analysis/references/sell.md` | `info.py get-history --start --end`, `sell_signals.py trail` / `cascade` (with `--start`) |

### Output contract

Five sections:

1. **Data quality and sample** — period, trade count, missing fields, selected Top-5/Bottom-10 set.
2. **Metrics table** — wins, losses, scratches, batting average, average win/loss, payoff ratio, R, hold times, maxima, optional equity contribution.
3. **Per-trade review** — original plan, reconstructed evidence, action-by-action /10 grades, post-exit path, error classification.
4. **Loss Adjustment Exercise** — original vs adjusted compounded result and interpretation.
5. **System findings** — recurring strengths, recurring breaches, regime clues, concrete process repairs.

### Worked example

> **You:** Here are my last 12 closed trades [CSV of ticker, entry/exit dates & prices, initial stop]. What does my record say?

Claude sorts by return, pulls `info.py get-history` windows around each trade, grades each action against `entry.md`/`sell.md`, tabulates batting average and payoff ratio, and runs the Loss Adjustment Exercise — for example flagging that losers were held 19 days on average versus 6 for winners (hope and involuntary investing), and that flooring every loss at 10% would have *raised* compounded return, isolating loss distribution rather than stock selection as the leak.

---

## The `/screen` workflow

`/screen` runs the fixed market-to-watchlist sweep as a scripted three-phase pipeline (`.claude/workflows/screen.js`), so the same evidence order holds whether fan-out is parallel or sequential.

### Arguments

```text
/screen
/screen NVDA AVGO PLTR
/screen --max-candidates 40
```

- `tickers` — optional user tickers, seeded first and protected from the cap. Every requested ticker is mechanically guaranteed to become a candidate; it never depends on the regime agent echoing it back.
- `max-candidates` — default **30**. This is a default, not a ceiling: an explicit higher request is honored, bounded only by a `FANOUT_SAFETY_CAP` of **60** so a typo can't spawn hundreds of scouts.

### Phases

1. **Regime.** A read-only agent reads `regime.md` and `screening.md`, runs `scripts/pipeline discover`, applies the two-axis doctrine (QQQ is information; leaders and traction decide), and builds a deduplicated candidate list from user tickers plus discover's RS leaders, movers, sector leaders, and industry leaders — with each ticker's origins and recurrence preserved. If the regime is clearly hostile it sets `hostile=true`.
2. **Qualify.** One `ticker-scout` per candidate runs `scripts/pipeline qualify TICKER` and returns a schema-validated gate result — **at most 16 concurrently**, in batches. Results are paired by delegation, not by the scout's self-reported ticker, so a mix-up (delegated `GOOG`, returned `GOOGL`) is discarded as unattributable rather than misfiled. A scout that returns nothing after its retry becomes an `INCOMPLETE` with `scout_no_result`.
3. **Synthesize.** A read-only agent sorts results into three disjoint buckets — `PROCEED`, `watch/incomplete`, `AVOID` — with exact funnel counts and next-decision points. Recurrence only prioritizes attention among comparable names; it is never a gate or master score. A `PROCEED` result is necessary but **never sufficient** for buy-alert or buy-ready, because this workflow has not done the entry, fundamentals, catalyst, final-candidate, market-alignment, and exit-plan convergence review.

### Hostile-regime early return

When Phase 1 flags `hostile`, the workflow **stops before qualification** and returns a watch-only report — every candidate lands in the `watch` bucket with the note that these names are observations only, not buy-ready candidates. This spends no scout calls on a broad fan-out into a market that has not earned it. Names cut by the cap (`by_cap`) or rejected as malformed (`invalid_user_tickers`) are always surfaced under `dropped`, so nothing is lost silently.

If parallel fan-out is unavailable, the same `ticker-scout` runs sequentially with the identical prompt and schema; if subagents are unavailable entirely, `scripts/pipeline qualify TICKER` runs sequentially in the main context. The fallback changes only scheduling — never the Minervini-first universe, hard gates, funnel counts, source honesty, or no-sizing boundary.

---

## The `ticker-scout` agent

`ticker-scout` (`.claude/agents/ticker-scout.md`) is a read-only fan-out worker with tools limited to `Read, Grep, Glob, Bash`. Its entire job is to qualify **exactly one** delegated US-listed ticker, discard the bulky command trace, and return a compact gate result to its parent — keeping the main analysis context clean during a wide sweep.

It normalizes a single ticker token to uppercase (returning `unavailable` if zero or more than one is supplied) and runs the canonical command:

```text
scripts/.venv/bin/python scripts/pipeline qualify AAPL
```

A normal payload contains `ticker`, `verdict` (`PROCEED` / `AVOID` / `INCOMPLETE`), `failed_gates`, `unavailable_gates`, `stage`, `trend_template_score`, `rs_rating`, `rs_rating_date`, `rs_status`, and `rs_source`. On failure it retries the identical command once, then reports the evidence as unavailable — it **never** converts missing evidence into `AVOID`, and it preserves `PROCEED` exactly (which means only that the hard gate earned a deeper look, never that the stock is a buy). It may make at most two extra cheap module calls, and only when the parent explicitly requests a bounded field the qualification does not return — never a VCP, fundamental, catalyst, chart, entry, sell, or risk dive.

---

## The watchlist state machine

Screening produces evidence maturity, not a capital instruction. Both `market-scan` and the `/screen` synthesis classify candidates along `references/screening.md`'s three states:

| State | Meaning |
|---|---|
| **watch** | Surfaced in loose screens, showed resilience or unexplained strength, or remains on the radar after a stop-out. Qualification hasn't run, is `INCOMPLETE`, or is `PROCEED` with no constructive setup yet. |
| **buy-alert** | Qualification is `PROCEED` and a constructive base or VCP is approaching a definable pivot, but fundamentals, market alignment, or breakout confirmation are still pending. Record the decision point early enough to finish the analysis before price arrives. |
| **buy-ready** | Qualification remains `PROCEED` and the setup, pivot, price/volume confirmation, catalyst, leadership and peer comparison, market context, and preplanned exit converge **now** — plus the twelve-item final-candidate review, except a labelled VCP Power Play may omit verified fundamentals. |

Promote only on new evidence; demote when the gate, setup, market alignment, or evidence freshness deteriorates. `PROCEED` is necessary but not sufficient for `buy-ready`; `INCOMPLETE` stays `watch` with missing fields named; a known gate failure is a current prospective-buy `AVOID` even if the name stays a future radar item.

## The no-sizing boundary

Every skill and the workflow stop at the same line: **`buy-ready` is an analytical readiness verdict, never a sizing or allocation prescription.** None of them prescribe portfolio percentages or position sizes. If you ask for sizing, the harness explains the scope boundary and offers setup, risk, and evidence-quality analysis instead — because this is educational analysis, not personalized financial advice. See the [FAQ & Disclaimer](FAQ-and-Disclaimer.md), and see [Design Principles](Design-Principles.md) for why the harness draws its scope lines where it does.

---
[← Wiki Home](README.md) · [Installation](Installation.md) · [Quickstart](Quickstart.md) · [Architecture](Architecture.md) · [The Minervini Method](The-Minervini-Method.md) · [Skills & Usage](Skills-and-Usage.md) · [Module Substrate](The-Module-Substrate.md) · [Design Principles](Design-Principles.md) · [Contributing](Contributing-and-Extending.md) · [FAQ](FAQ-and-Disclaimer.md)
