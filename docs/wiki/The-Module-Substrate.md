# The Module Substrate

The deterministic Python layer under `scripts/` that produces every precise market number the model reasons over — so judgment rests on measured evidence, never on the model's memory or the web.

The harness rests on a simple division of labour: **the modules measure, the model judges.** Prices, moving averages, earnings, breadth, and relative strength come only from these tools. The model calls them, reads their structured output, and forms the verdict itself — there is deliberately no composite score for it to defer to. This page documents the contract those tools obey, the full catalogue of what they do, how caching keeps a session coherent, how relative strength degrades honestly, and how the model iterates them the way a trader works a funnel.

For where this layer sits in the whole system, see the [architecture overview](Architecture.md). For the doctrine the model applies to these numbers, see [the Minervini method](The-Minervini-Method.md).

## The module contract in plain terms

Every public CLI under `scripts/` honours one contract, spelled out for maintainers in [`.claude/rules/module-contract.md`](Architecture.md). It exists so skills, the [ticker-scout agent](Architecture.md), and the `/screen` workflow can compose these tools from structured output with no human standing by to interpret an ambiguous reply. The rules that matter to you as a reader:

- **One JSON document to stdout.** A normal invocation writes exactly one JSON object through `utils.output_json` — never mixed with prose or debug text, because downstream consumers parse the whole stream.
- **One public failure shape.** Parser, validation, and runtime failures route through `utils.JsonArgumentParser` / `utils.error_json` to `{"error": "..."}` with exit code 1. A missing datum *inside* an otherwise useful result is reported as a section-level `unavailable` rather than crashing the whole command.
- **Explicit subcommands, no "analyze everything" command.** Each operation is a named `argparse` subcommand. There is intentionally no monolith that collects every module into one verdict-shaped blob — that would invite deference to the shape instead of reading the evidence, and it would defeat the cost-earning funnel.
- **A top-level `doctrine` field.** Each successful analysis result carries a `doctrine` string explaining how to interpret the measurement and its limits, so a numeric detector can never silently become a trading verdict.
- **`--help` is the live offline spec.** Top-level and subcommand `--help` document every argument and flag — units, defaults, allowed values, provenance, and whether a threshold is flex or locked. Help construction is fully offline (no fetch, scrape, RS request, or cache write happens before parsing), so it works even when the network does not.
- **`--no-cache` everywhere.** Every module and subcommand accepts `--no-cache`, including utilities that make no cached call, giving callers one predictable diagnostic contract.

### Flex-tier flags vs locked constants

The contract draws a hard line between thresholds you may tune and boundaries you may not. A **flex-tier flag** exists only where changing it preserves the method, and its default reproduces canonical behaviour — running with no flags is the stable contract that skills and tests rely on. A **methodology boundary** is instead a named, module-level *locked constant* with its source tag and rationale beside it; where a related flag exists, it is validated so a caller can *tighten* the rule but never weaken the floor.

`vcp.py detect` shows both in one command:

```
scripts/.venv/bin/python scripts/modules/vcp.py detect NVDA
```

- `--min-contractions` (default 2) may tighten only within the locked 2–6 range.
- `--max-depth` (default 60) — a first correction at or beyond 60% is always rejected and callers may never relax it.
- `--rel-correction-ratio` (default 2.5) is flex within the canonical 2–3x band and cannot exceed 3.
- `--hostile-market` opts into the severe-bear depth exception explicitly; it is never inferred from price history alone.

By contrast, `trend_template.py` hard-codes its distance floors as locked constants (`MIN_PCT_ABOVE_52W_LOW = 1.30`, `MAX_PCT_BELOW_52W_HIGH = 0.75`) with no flag at all, and `rs_ranking.py` locks `MIN_RS_ELIGIBILITY = 70`. Where a threshold genuinely scales with context — for example `volume_analysis.py analyze --lookback`, the institutional supply/demand window — it is a flex flag whose help text tells you *why* you would move it.

### Provenance tags in the code itself

Doctrine attribution is not just in prose; it is stamped on threshold comments and emitted `doctrine`/`provenance` fields so a borrowed number can never masquerade as a Minervini gate:

| Tag | Meaning |
| --- | --- |
| `[M]` | Canonical Minervini SEPA doctrine — the immutable constitution |
| `[TL]` | TraderLion practice layer — tagged, subordinate |
| `[TL-Kell]` | The Kellett 50-SMA position-trail exception |
| `[MM-Ryan]` / `[MM-Zanger]` / `[MM-RitchieII]` | *Momentum Masters* speaker context, attributed to the speaker |
| `[heuristic]` | Harness-invented quantifier that labels itself non-canonical and explains what qualitative evidence it approximates |

Only `[M]` is canonical. Everything else stays explicitly attributed so it reads as practice or context, not as SEPA law.

## The pipeline: two composable entry points

`scripts/pipeline/` is the thin orchestration layer over the modules. It has exactly two subcommands — not a closed pipeline, and deliberately without an "analyze everything at once" command.

```
scripts/.venv/bin/python scripts/pipeline qualify AAPL
scripts/.venv/bin/python scripts/pipeline discover
```

| Command | What it does |
| --- | --- |
| `qualify TICKER` | Tier-0 low-cost hard gate. Runs `trend_template check` and `stage_analysis classify` in parallel and returns `PROCEED`, `AVOID`, or `INCOMPLETE`. `PROCEED` means the name earned a closer look — **not** that it is a buy. `AVOID` means a hard gate failed (structurally disqualified — stop). `INCOMPLETE` means required evidence was unavailable and no known gate failed; it is never flattened into `AVOID`. |
| `discover` | Market environment and RS leadership: breadth (new-high vs new-low), the QQQ 21-EMA information switch, RS leaders (top 20), sector/industry rankings, the leadership board, and movers. It reports *evidence readiness* (`evidence_ready` / `partial` / `incomplete`); the [market-scan skill](Skills-and-Usage.md) makes the bottom-up regime judgment. |

The two hard gates that `qualify` reads — **Stage 2 AND Trend Template 8-of-8** (all AND, RS ≥ 70 floor) — are the only thing the tools decide on their own: binary and non-negotiable. Convergence, entry timing, leadership, and risk are read by the analyst from the raw module outputs, not collapsed into a number.

## The 16 modules

`scripts/modules/` holds fifteen tool modules plus the shared `utils.py` library. Confirm any subcommand or flag with `--help` — it is the authoritative offline spec.

| Module | Purpose | Key subcommands |
| --- | --- | --- |
| `trend_template.py` | Minervini's 8-criteria Trend Template; each criterion pass/fail/unavailable, AND-gated | `check` |
| `stage_analysis.py` | Where a stock sits in Weinstein's four-stage lifecycle, decided structurally (no score) | `classify`, `transitions`, `risk` |
| `vcp.py` | Volatility Contraction Pattern detection, including Power Play and cheat structure | `detect` |
| `rs_ranking.py` | Relative-strength eligibility and screening, with an explicit source fallback chain | `score`, `screen`, `compare` |
| `earnings_acceleration.py` | Code 33 triple acceleration and the surprise → revisions → demand causal chain | `code33`, `acceleration`, `surprise`, `revisions`, `margin`, `valuation` |
| `volume_analysis.py` | Institutional supply/demand: up/down-volume, demand days, live run-rate | `analyze`, `demand-days`, `runrate` |
| `base_count.py` | Base number within a Stage 2 advance (later-stage bases are higher-risk) | `count` |
| `tight_closes.py` | Heuristic clusters of narrow-range closes as corroborative context | `daily`, `weekly` |
| `entry_patterns.py` | `[TL]` opt-in entry setups (MA pullback, consolidation pivot, support reclaim) after the M gate | `scan`, `screen` |
| `sell_signals.py` | Deterministic sell instruments with tagged provenance | `reversal`, `extension`, `trail`, `cascade` |
| `market_breadth.py` | Finviz breadth sections plus the QQQ 21-EMA information switch, sources isolated | `breadth` |
| `market_clock.py` | NYSE-aware market clock shared by cache policy and skill preprocessing (single-operation utility, no subcommand) | *(none)* |
| `info.py` | Company metadata, fast quotes, ISIN, shares, history metadata, SEC filings | `get-info`, `get-fast-info`, `get-info-fields`, `get-isin`, `get-shares`, `get-shares-full`, `get-history-metadata`, `get-history`, `get-sec-filings` |
| `actions.py` | Corporate actions, earnings data/dates, calendar, and company news | `get-dividends`, `get-splits`, `get-capital-gains`, `get-actions`, `get-earnings`, `get-earnings-dates`, `get-calendar`, `get-news` |
| `chart_render.py` | Renders daily/weekly OHLCV charts as non-gating visual corroboration | `daily`, `weekly` |
| `utils.py` | Shared substrate: `output_json`/`error_json`, `JsonArgumentParser`, the cache layer, SMA helpers (no CLI) | *(library)* |

A representative call looks like this:

```
scripts/.venv/bin/python scripts/modules/stage_analysis.py classify NVDA
scripts/.venv/bin/python scripts/modules/sell_signals.py cascade TSLA
scripts/.venv/bin/python scripts/modules/earnings_acceleration.py code33 AAPL
```

`sell_signals.py cascade` encodes the failure cascade the doctrine reads on a breaking leader: a single-close **21 EMA loss → 50 SMA loss → caller-anchored prior-high failed retest → terminal 200 SMA loss**. Note the division of labour among the trade-management averages: eligibility and Stage analysis use the 50/150/200 SMA stack, while `[TL]` trade management uses the 10/21 EMA — the same chart, different roles.

## The same-session cache

A transparent read-through cache keeps repeated analysis inside one turn consistent without going stale on live prices. It wraps all three live sources: yfinance, the Finviz homepage scrape, and the `ibd-rs-rating` backend.

- **Identity.** Each entry is keyed by `(source, symbol, function, params-hash, last-completed-US-session)`. The completed New York session — not the local calendar day — is what anchors the key, so a user in another timezone still gets one coherent market snapshot across a session's worth of calls.
- **User-scoped root.** Entries live under `${MINERVINI_CACHE_DIR:-~/.cache/minervini-harness}`.
- **Market-open bypass.** During the regular session, price endpoints bypass the cache or use a TTL of at most 15 minutes; non-price data keeps the completed-session lifetime. `volume_analysis.py runrate` is deliberately cache-exempt, because stale cumulative volume would corrupt a live extrapolation.
- **`--no-cache` is monotonic.** It disables both reads and writes for every source for the rest of the process, via a state that a later helper cannot accidentally re-enable. Failed fetches are never cached, and a cache read/write error is reported in metadata rather than hiding a usable live value.

Every payload carries a lean `_cache` block (`status`, `counts`, `session_dates`) so you can see whether a value was live or cached and that it belongs to the current session; set `MINERVINI_CACHE_DEBUG=1` for full per-event detail.

## Relative strength degrades honestly

`rs_ranking.py` — and Trend Template criterion 8, which imports it — resolves the RS ≥ 70 eligibility floor in a strict, binding order:

1. **`ibd_rs_rating_backend` first.** The authoritative IBD-style rating from the project's `ibd-rs-rating` Neon backend (~4,600 US stocks). Validated but never recomputed; must fall in 1–99. This is not described as a proprietary IBD feed.
2. **Labelled local proxy second.** If the backend is unavailable, a clearly labelled proxy is computed from the stock/SPY RS line. It reports RS-day share and 1M/3M/6M/12M historical percentiles — but **only its 12-month percentile may provisionally carry the RS ≥ 70 gate.** Shorter lookbacks are marked `timing_only`. The proxy's percentiles are self-relative rolling distributions, not a cross-sectional IBD rank, and the result says so.
3. **Unavailable otherwise.** If neither source can produce the eligibility score, the result is `unavailable` — never a fabricated failure. In `qualify`, that surfaces as `INCOMPLETE`, not `AVOID`.

```
scripts/.venv/bin/python scripts/modules/rs_ranking.py score NVDA
scripts/.venv/bin/python scripts/modules/rs_ranking.py screen --min-rating 90 --limit 25
```

## How the model iterates like a trader

The substrate is built to be *worked*, not run once. Three properties make that possible:

**Flex flags let the model match a tool to the setup.** The same `volume_analysis analyze` call can read a long base or only the most recent leg by moving `--lookback`; `demand-days` scales `--down-vol-lookback` and `--scan-days` to a 5-week handle versus a 26-week base. The default always reproduces canonical behaviour, so tuning is a deliberate act, not a hidden one.

**Composability preserves the funnel.** Because there is no monolith, the model spends the cheapest disqualifying read first — `pipeline qualify` — and only deepens when the gate is earned, calling one tool per question: `vcp detect`, then `earnings_acceleration code33`, then `volume_analysis analyze`, and so on. Each deeper look pays its own way.

**Honest state markers keep missing evidence visible.** Tools never invent an anchor to force an answer. A Trend Template criterion can be `PASS`, `FAIL`, or `UNAVAILABLE`. `sell_signals` items return `needs_input` when the source defines no breakout anchor or maximum lookback (supply `--breakout-date` rather than letting it guess) and `needs_chart` when a signal — like a trendline break — has no deterministic anchor and must be corroborated with `chart_render`. Section-level `unavailable` reports a fragile source that failed without erasing the evidence beside it. The model reads these states as evidence about *what it does and does not know*, retries a failed source once, and then reports it unavailable — it does not paper over the gap.

This is analysis and education, not financial advice, and the harness never prescribes position sizes — see the [FAQ & Disclaimer](FAQ-and-Disclaimer.md). To extend or add a module under this contract, see [Contributing & Extending](Contributing-and-Extending.md).

---
[← Wiki Home](Home.md) · [Installation](Installation.md) · [Quickstart](Quickstart.md) · [Architecture](Architecture.md) · [The Minervini Method](The-Minervini-Method.md) · [Skills & Usage](Skills-and-Usage.md) · [Module Substrate](The-Module-Substrate.md) · [Design Principles](Design-Principles.md) · [Contributing](Contributing-and-Extending.md) · [FAQ](FAQ-and-Disclaimer.md)
