# Harness Spec — Harness of Minervini

## Context

- **What this is**: an AI harness that makes Claude behave as a disciplined momentum-stock analyst in the Minervini SEPA tradition — discovering candidate tickers and judging concrete buy/sell timing, US stocks only.
- **User**: Korean-speaking individual investor; interview conducted in Korean; all harness artifacts (CLAUDE.md, skills, hooks, code, docs) written in English per user decision.
- **Existing assets** (all under git-ignored `.tmp/`):
  - Prototype skill `.tmp/Minervini/` — 248-line SKILL.md + 12 JSON-emitting argparse CLI modules (`Scripts/modules/`) + a 2-command pipeline (`qualify` = Stage-2 + Trend-Template 8/8 hard gate; `discover` = breadth-primary regime read + RS leadership survey). Deliberately no "analyze everything" command. Thresholds split into CLI-tunable flex tier and locked floors.
  - `.tmp/Minervini.db` — book corpus: full text of *Trade Like a Stock Market Wizard* (14 chapters) + one Korean-language momentum text (id 15). No code reads it.
  - `.tmp/TraderLion.db` — book corpus: TraderLion trading guide (13 chapters), same O'Neil/Minervini lineage, practitioner-oriented.
- **Data sources (live at runtime, no local market DB)**: yfinance (prices/financials/earnings), finviz.com homepage scrape (market breadth), `ibd-rs-rating` library (Neon backend, ~4,600 US stocks RS ratings).
- **Distribution intent**: v1 is a project harness in `.claude/`; the user intends to later convert it into a Claude Code plugin for marketplace distribution. All design must stay portable: no absolute user paths, no committed venv, user-scoped cache/data locations, English docs.
- **Implementation status**: Phases 0-5 are implemented and validated. The substrate is pinned to `ibd-rs-rating==0.4.0`; the analyst-facing constitution, three skills, six references, read-only scout, `/screen` workflow, paths-gated rule, and narrow permissions passed deterministic, live-source, runtime, permission, fidelity, and six-scenario E2E validation.

## Goals

In the user's own words (translated from Korean):

1. "Help me judge which tickers to invest in, and concretely when to buy or sell them" — discovery/screening plus entry/exit timing judgment is the core job.
2. US stocks only.
3. **Analysis only** — industry/sector/ticker analysis; the harness must never prescribe portfolio construction ("put N% into X" is out of scope). Ticker-level sell/hold judgment is in scope; position sizing is not.
4. Embody both the explicit knowledge (형식지: named criteria, thresholds, checklists) and the tacit knowledge (암묵지: judgment principles, the why behind rules) of the Minervini and TraderLion corpora — while treating the previous single-skill attempt as a reference to be doubted, not copied.
5. Numbers that require accuracy (prices, earnings, debt) come from deterministic code; narrative context (recent company activity) may come from web search.
6. Claude analyzes like a real momentum trader: iteratively calling parameterized modules, adjusting parameters, earning each deeper look — not relying on a single monolithic pipeline call.
7. Preserve Claude's intelligence and creativity — principles with reasons over enumerated rules (the single-skill attempt failed at this).
8. Harness artifacts in English.
9. Designed for future plugin/marketplace distribution.

## Behavior inventory

Layer/component columns are filled in I3. Knowledge-cluster references (e.g. "M-map cluster H") point into `docs/plans/research/minervini-knowledge-map.md` and `docs/plans/research/traderlion-knowledge-map.md`, which are the authoritative knowledge sources for implementation.

### Persona & doctrine

| id | behavior/knowledge/constraint | layer | component | status |
|----|-------------------------------|-------|-----------|--------|
| B1 | SEPA analyst persona: "conservative aggressive opportunist", risk-first question order, no-trade as strong default, ~50% win-rate calibration, decision quality ≠ outcome (M-map cluster I) | CLAUDE.md | CLAUDE.md constitution — persona + risk spine | validated |
| B2 | Probability-convergence + funnel order: technicals gate fundamentals (Trend Template first), low-cost technical gate before deep looks, earn each deeper look, never "analyze everything at once" (M-map clusters A/C) | CLAUDE.md | CLAUDE.md constitution — funnel order + probability convergence | validated |
| B3 | Anti-LLM-default corrections, always active: lockout rally (overbought after bear = strength), anti-ATR (never widen stops for volatility), ultra-low P/E + 52wk low = red flag, cheap-trap ban, broken-leader ban, price leads earnings both ways, no bottom fishing (M-map clusters B/C/F/H) | CLAUDE.md | CLAUDE.md constitution — compact corrections list; expanded in topic references | validated |
| B4 | Two-tier doctrine + provenance: SEPA gates = immutable hard constraints; TraderLion tactics = tunable defaults with origin tags; conflicts resolved Minervini-first per TL-map §4 (26 resolutions); Momentum Masters speaker tagging (only Minervini canonical); MA vocabulary role separation (50/150/200 SMA = eligibility, 10/21 EMA = trade management, never mixed) | CLAUDE.md + references | CLAUDE.md constitution — two-tier rule; provenance tags throughout references | validated |
| B5 | Scope constraints: US stocks only; long + cash only (no shorts); never prescribe portfolio %-allocations; ticker-level buy/sell/hold judgment in scope; daily/weekly timeframe (intraday tactics out of v1) | CLAUDE.md + descriptions | CLAUDE.md scope guards + boundary language in all three skill descriptions | validated |
| B6 | Data doctrine: precision numbers only from modules (never websearch for prices/earnings/financials); narrative context via websearch allowed; module failure → retry once, then declare unavailable — never fill gaps from memory | CLAUDE.md | CLAUDE.md constitution — data doctrine | validated |
### Knowledge encoding

| id | behavior/knowledge/constraint | layer | component | status |
|----|-------------------------------|-------|-----------|--------|
| B7 | Always-loaded core doctrine distilled from both maps' "(b) bucket" recommendations (persona + convergence + risk spine + negative constraints) | CLAUDE.md | CLAUDE.md constitution (distillation target for both maps' (b) buckets) | validated |
| B8 | On-demand knowledge references split by job: market regime/cycle; trend-template/stage; VCP/chart/entry; earnings quality; leadership/category; sell rules & position management; screening/routines; valuation de-biasing (both maps' "(c) buckets") | skill references | market-scan/references/{regime,screening}.md + ticker-analysis/references/{entry,fundamentals,sell,cases}.md | validated |
| B9 | Worked-example case library as few-shot patterns (PCYC, VIVO, Crocs pair, SWN reset, FB disqualification, etc.) | skill references | ticker-analysis/references/cases.md | validated |
| B10 | Paraphrase-first authoring policy: committed references restate principles with minimal short quotes; book DBs never committed (copyright; repo is public) | design record | harness-spec Authoring doctrine (developer-facing; never loaded into analyst context) | validated |
### Analysis capabilities

| id | behavior/knowledge/constraint | layer | component | status |
|----|-------------------------------|-------|-----------|--------|
| B11 | Market regime assessment: breadth + leader feedback decide (bottom-up primary); QQQ-vs-21EMA switch as information filter only (TL-map §4-7 dual-gate synthesis); lockout-rally detection | references + code | market-scan references/regime.md + pipeline discover / market_breadth module | validated |
| B12 | Discovery/screening: multiple loose parallel screens + recurring-name observation (never monolithic AND), funnel count discipline (universe → weekly ~75 → focus ≤15 → daily 1-5) | references + code + agent | market-scan references/screening.md + rs_ranking/pipeline + ticker-scout fan-out | validated |
| B13 | Ticker qualification hard gate: Stage 2 AND Trend Template 8/8 (original Minervini numbers canonical), RS ≥ 70 floor | code | pipeline qualify + _gates.py (deterministic verdict) | validated |
| B14 | Deep-dive buy analysis: VCP footprint (nW d/f nT), pivot + volume confirmation, entry patterns, earnings quality (Code 33, acceleration, guidance/inventory forensics), leadership/category classification (6 categories mandatory first), primary-base rules for recent IPOs | references + code | ticker-analysis references/{entry,fundamentals}.md + vcp/base_count/earnings_acceleration/volume_analysis modules | validated |
| B15 | Sell/hold monitoring: sell-into-strength triggers (+20-25% extension zone, key-reversal 6-item checklist, climax recognition), MA-trail baseline (21EMA swing / 50SMA position, 2-close trigger, TL-tagged), 3R breakeven stop, Stage-2 max-drawdown sell signal, earnings-event policy (no new entry right before earnings), failure cascade (21e loss → 50s loss → downside reversal at/near the prior high = failed retest; 200 SMA terminal) | references + code | ticker-analysis references/sell.md + sell_signals module + stage_analysis risk + actions.py get-earnings-dates | validated |
| B16 | Watchlist state machine: watch → buy alert → buy ready; re-entry doctrine (stopped out ≠ blacklisted; base-reset vs pivot-reset classification) | references | market-scan references/screening.md (watchlist state machine section) | validated |
| B17 | Chart visual corroboration: render daily/weekly PNG (price + MAs + volume); numbers decide, eyes corroborate; never a gate | code + skill body | chart_render module + doctrine line in CLAUDE.md constitution and ticker-analysis body | validated |
| B18 | Post-trade review protocol: Top-5 winners / Bottom-10 losers selection, per-action /10 scoring, post-exit tracking windows, Loss Adjustment Exercise, batting-average/R-multiple metrics (TL-map cluster H + M-map Loss Adjustment) | skill | skills/trade-review (separate trigger context: user's own trade log) | validated |
### Code substrate

| id | behavior/knowledge/constraint | layer | component | status |
|----|-------------------------------|-------|-----------|--------|
| B19 | Module CLI contract standardization: uniform flag conventions, JSON output, flex-tier flags + locked floors, per-module doctrine field, `--help` as live spec | rules + code | .claude/rules/module-contract.md (paths: scripts globs) + refactor | validated |
| B20 | New/extended modules: sell-signal detectors (key reversal, extension-zone measurement, MA-trail state, violation cascade), closing-range/volume quantifiers (CR formula, ±25% volume bands, ADR%), earnings-calendar proximity check, chart renderer, RS-proxy spec hardening (TL RS-line/AS percentiles as reference) | code | new modules in scripts/modules/ (repo root) | validated |
| B21 | Same-day data cache: user-scoped location, transparent read-through, plugin-safe | code | shared cache util in scripts/modules/utils.py (user-scoped dir) | validated |
| B22 | Bootstrap & portability: venv bootstrap script (no committed .venv), remove 6 dead deps + 4 unused .env keys, no absolute user paths anywhere | code + CLAUDE.md | bootstrap.sh + requirements cleanup + CLAUDE.md setup line | validated |
| B23 | Reliability: module smoke tests (schema-shape assertions against live APIs), graceful degradation, fragile-source isolation (finviz scrape, ibd-rs-rating) | code | scripts/tests/ smoke suite + runner | validated |
### Harness plumbing

| id | behavior/knowledge/constraint | layer | component | status |
|----|-------------------------------|-------|-----------|--------|
| B24 | CLAUDE.md: project facts, data doctrine one-liner, harness-spec pointer, no component enumeration | CLAUDE.md | CLAUDE.md as constitution carrier (~150-180 lines; 200-line guideline consciously waived by user) | validated |
| B25 | Session-start context injection: today's date, market open/closed, cache freshness state | skill preprocessing | market-scan + ticker-analysis body !`...` blocks (date, market clock, cache state) — not a hook | validated |
| B26 | Permission allowlist for module CLI invocations (reduce prompt friction; workflow-agent compatible) | permissions | settings.json permissions.allow — narrow venv-python invocation rules | validated |
| B27 | Repo protection: `.tmp/` (book DBs, prototype) stays ignored; validation that no book text is committed | permissions + git | permissions.deny Edit(/.tmp/**) (project-root anchored) + existing .gitignore | validated |
| B28 | Validation scenarios defined in I5 (trigger/near-miss, gate behavior, module contract) | spec | harness-spec Validation section (I5) | validated |
### Deferred to v2 (recorded, not routed)

- Edge-study / model-book generation workflows (TL-map cluster I: study pipeline, 11-field schema, model-book 6-step) — valuable but not needed for the core analyst loop.
- TraderLion Ch.12 chart-study recovery (re-extraction from original PDF, or model-book regeneration from ticker+year register) — chart images lost in current DB; text ~95% unreliable AI alt-text per TL-map §6.
- Intraday tactics module (ORB, gapper Day 1/2/3, VWAP) — out of SEPA scope, opt-in candidate later (TL-map §4-22).
- TL secondary universe classes (non-earnings momentum, swing-tag squeeze names) — default disallowed (TL-map §4-15).

## Component specs

Full elaboration (file-by-file content outlines, module signatures, acceptance criteria) lives in `docs/plans/` implementation docs; this section records the binding decisions each component's generation needs.

### CLAUDE.md — the constitution carrier (~150-180 lines)

The 200-line guideline is consciously waived by user decision: the analyst constitution belongs here because CLAUDE.md is the only unconditional channel — no trigger probability, no reference-routing probability, survives compaction. Content, in order:

1. **Identity & purpose** — what this harness is, one paragraph; the three trigger rules are the only component mentions (no inventory enumeration).
2. **The analyst constitution** (compact — details live in references): persona + risk spine (B1); funnel order + probability convergence (B2); anti-default corrections list (B3); two-tier doctrine + provenance rule, incl. MA-vocabulary role separation and Momentum-Masters speaker rule (B4); scope guards (B5); data doctrine (B6); "numbers decide, eyes corroborate" (B17).
3. **Module invocation facts** — venv path resolution, JSON contract, retry-once-then-declare-unavailable.
4. **Skill trigger rules** (condition → skill, compaction-proof): market/sector/screening intent → `market-scan`; single-ticker buy/sell/hold intent → `ticker-analysis`; grading the user's own trades → `trade-review`.
5. **Repo layout + bootstrap command.**
6. **Runtime facts only** — bootstrap recovery and `.tmp/` as non-runtime raw material. Developer-facing status synchronization and methodology-authoring instructions stay in this spec, not in analyst context.

Hard budget: ≤180 lines. HTML comments (stripped at load) may carry maintainer notes for free.

### Skill: `market-scan` — `.claude/skills/market-scan/`

- **Description**: market-level intent — "how's the market", regime/breadth questions, sector/industry strength, "find me stocks/leaders/breakouts", screening and watchlist requests, even when SEPA/Minervini is never named. Near-miss boundaries: single-ticker judgment → `ticker-analysis`; grading own trades → `trade-review`; portfolio sizing out of scope entirely.
- **Frontmatter**: `allowed-tools` with qualified Bash grants matching settings.json shapes (`Bash(scripts/.venv/bin/python *)`, `Bash(bash scripts/bootstrap.sh)`) + `Read, Grep, Glob, WebSearch, WebFetch` — never a blanket `Bash`; `model` unset (inherit).
- **Body (≤120 lines)**: (1) `` !`...` `` preprocessing — date, market open/closed, cache state; (2) procedure: `discover` → breadth/leader read → dual-gate regime verdict (switch = information, leader/trade feedback = decider); (3) screening funnel procedure — parallel loose screens, funnel counts, ticker-scout fan-out pattern, `/screen` pointer + sequential fallback; (4) mandatory reference routing, persuasion-framed ("your training priors do not contain this harness's adjudicated doctrine — the references do"); (5) output conventions (watchlist state labels, evidence-cited regime calls).
- **references/**: `regime.md` (M-map cluster B + TL-map cluster F: dual-gate §4-7, lockout rally, bottom checklist, pilot→second-wave), `screening.md` (M-map cluster A screens + TL-map cluster G: funnel counts, TIGERS, screen library, RS-proxy spec, watchlist state machine, workflow fallback).

### Skill: `ticker-analysis` — `.claude/skills/ticker-analysis/`

- **Description**: single-ticker intent — "is X a buy", "should I sell X", "what do you think of X here", diagnosis/timing of a named US stock. Near-miss boundaries: market-level or screening questions → `market-scan`; the user's own past-trade grading → `trade-review`; position sizing never.
- **Frontmatter**: same qualified tool set as market-scan; `model` unset.
- **Body (≤120 lines)**: (1) preprocessing block (same); (2) prospective buy/diagnosis branch: `qualify` hard gate first → on PROCEED earn each deeper look in order (entry/chart → fundamentals → sell plan) → probability-convergence verdict that includes market context (from `market-scan` doctrine or a fresh `discover` call); (3) existing-position sell/hold branch: run `qualify` for structural context but always read `sell.md` and run the applicable sell diagnostics even when a buy gate fails, because a failed buy gate can itself be urgent holding evidence; (4) chart corroboration doctrine (render PNG for ambiguous pattern-character calls; never a gate); (5) mandatory reference routing (same persuasion framing — sell/entry/fundamentals thresholds are canonical only in references); (6) output conventions: evidence-cited verdict, watch → buy-alert → buy-ready state, explicit no-sizing.
- **references/**: `entry.md` (M-map clusters C/D: Trend Template context, VCP footprint, pivots, squat/tennis-ball/reset, 3C, Power Play, primary base + TL daily-TF tactics tagged opt-in §4-1), `fundamentals.md` (M-map clusters E/F/G: earnings quality, Code 33, guidance/inventory forensics, valuation de-biasing, 6-category classification), `sell.md` (M-map cluster H + TL-map cluster E gap-fillers: extension zone, key-reversal 6-item, MA-trail 2-close baseline, failure cascade, earnings-event policy, +5% beginner note with R-multiple referee §4-5), `cases.md` (worked-example few-shot library, source-tagged).

### Skill: `trade-review` — `.claude/skills/trade-review/`

- **Description**: triggers when the user shares their own trade log / asks to grade, review, or post-mortem their trades. Near-miss: prospective analysis routes to the other two skills, and portfolio sizing remains out of scope.
- **Body**: input expectations (ticker, entry/exit dates & prices, stop, size optional), Top-5/Bottom-10 selection, per-action /10 scoring, metrics suite (batting average with ±1% scratch band, avg win/loss, R-multiples, hold-time asymmetry), Loss Adjustment Exercise, post-exit tracking windows, output format modeled on TL RDDT case review. Grading criteria point to `../ticker-analysis/references/sell.md` and `entry.md` (no doctrine duplication).
- **Frontmatter**: `allowed-tools: Bash(scripts/.venv/bin/python *), Read, Grep, Glob` — Bash required for post-exit tracking via `info.py get-history` and `sell_signals trail/cascade --start`; `model` unset.
- No bundled scripts in v1.

### Agent: `ticker-scout` — `.claude/agents/ticker-scout.md`

- **Purpose**: screening fan-out isolation — qualify one ticker, return a compact verdict.
- **Frontmatter**: `tools: Read, Grep, Glob, Bash` (read-only by omission of Edit/Write), `model:` unset (inherit).
- **Body** (self-contained; agents get no default system prompt): how to invoke `qualify` + optionally 1-2 cheap modules, the JSON contract, what to return (verdict + failed gates + RS + stage + one-line evidence, ≤10 lines), retry a failed module once before declaring that evidence unavailable, and explicit prohibitions (no deep dive, no file edits, no WebSearch, never fill missing data from memory).

### Workflow: `/screen` — `.claude/workflows/screen.js`

- **Shape** (thin; judgment lives in prompts): Phase 1 regime (one agent runs `discover`, returns regime + leader survey) → gate: if regime is hostile, return watch-only report → Phase 2 fan-out (one agent per candidate from RS leaders/user list, runs `qualify`, schema-validated verdicts) → Phase 3 synthesize (ranked watchlist with funnel-count discipline, PROCEED/watch/avoid buckets).
- **Args**: optional ticker list; optional max-candidates (default ~30).
- **Companions shipped in same commit**: matching `permissions.allow` entries for the venv invocations (workflow agents cannot answer prompts mid-run); sequential-subagent fallback documented in `screening.md`.

### Rules: `.claude/rules/module-contract.md`

- `paths:` globs targeting repo-root `scripts/**` (modules, pipeline, tests).
- Content: CLI contract (argparse subcommands; JSON to stdout via `utils.output_json`; `{"error": ...}` + exit 1; flex-tier flags with defaults reproducing canonical behavior; locked floors as named constants with rationale comments; per-module `doctrine` field; `--help` is the live spec), cache read-through obligation, no-network-in-help, provenance comments for TL-origin thresholds.

### settings.json (permissions)

- `deny`: `Edit(/.tmp/**)` — single leading slash = project-root anchored (bare `.tmp/**` resolves against cwd and silently stops protecting when cwd ≠ repo root). Book DBs and prototype are read-only to Claude.
- `allow` (narrow, exact command shapes validated during implementation): venv python invocations for pipeline/module CLIs; `git status`/`git diff`.
- Note in generated docs: project allow rules activate only after workspace trust.

### Code substrate — `scripts/` (repo root)

- **Layout**: `scripts/modules/`, `scripts/pipeline/`, `scripts/tests/`, `scripts/bootstrap.sh`, `scripts/requirements.txt`. Referenced by all three skills, the agent, and the workflow via project-root paths; at pluginization the whole directory moves to `${CLAUDE_PLUGIN_ROOT}/scripts` unchanged.
- **Migrate** the 12 prototype modules + pipeline from `.tmp/Minervini/Scripts/`, with refactors: (a) same-day cache layer in `utils.py` (user-scoped dir: `$MINERVINI_CACHE_DIR` override → default `~/.cache/minervini-harness/`; key = source+ticker+function+params+session-date where session-date = last completed US trading session in America/New_York, never the local calendar date; wraps all three live sources incl. ibd-rs-rating; OHLCV bypass/short-TTL while the market is open); (b) uniform flag conventions audit; (c) remove 6 dead deps from requirements.txt (fredapi, python-dotenv, finvizfinance, finviz, sec-edgar-downloader, sec-analyzer) and the 4 unused .env keys; (d) provenance/rationale comments on locked constants.
- **New modules**: `sell_signals.py` (subcommands: `reversal` — key-reversal 6-item; `extension` — % above base top / 50d & 200d MAs vs +20-25% zone; `trail` — 21EMA/50SMA 2-close state machine, dated event sequence; `cascade` — 21e loss → 50s loss → downside reversal at/near the prior high (failed retest = top confirmation), 200 SMA terminal, dated sequence [TL-map clusters E/J]. Drawdown-since-Stage-2 is NOT duplicated here — `stage_analysis risk` owns it); `chart_render.py` (`daily|weekly TICKER --period --out PNG` — daily: 10/21 EMA + 50/150/200 SMA; weekly: 10/30/40-week equivalents, never a 200-week MA; volume with ±25% bands, optional pivot annotation; mplfinance — EMAs/bands via make_addplot since mav= is SMA-only); `quant` additions to existing modules (closing-range %, ±25% volume bands, ADR%) where they naturally belong; earnings-proximity check (`actions.py get-earnings-dates` extension: days-until-earnings flag for the earnings-event policy).
- **Bootstrap**: `bootstrap.sh` — create venv if missing (path resolution: `$MINERVINI_VENV` → `scripts/.venv` (gitignored)), install exact compatible dependency pins, smoke-check imports, and when an override is used create an ignored `scripts/.venv/bin/python` symlink to the selected interpreter so the canonical invocation and permission shapes remain stable. No committed venv.
- **Tests**: `tests/smoke.py` — per-module schema-shape assertions against live APIs (keys present, types right; not value assertions), runnable standalone; used by I5 validation.

## Design rationale

Decisions locked during I1 (2026-07-10):

- **TraderLion integration** — integrated as the *practice layer*: Minervini corpus is the doctrine of record (theory, the why); TraderLion supplies practical application (routines, entry tactics, sell rules, post-analysis, market cycles). On doctrinal conflict, Minervini takes precedence unless his corpus is silent; conflicts get flagged explicitly in references. Final confirmation deferred until both knowledge-map reports are in (user wants to see the books' actual content relationship first).
- **Book DBs are distill-only** — no runtime lookup module. User's reasoning, adopted: "consulting the textbook during the exam is noise; the point is for Claude to internalize the essence." The DBs are authoring raw material for skill references, nothing more.
- **Chart rendering: numbers decide, eyes corroborate** — deterministic CLI detectors remain the decision substrate; a chart-rendering module (PNG with MAs/volume) is included as a non-gate cross-check for ambiguous pattern-character calls.
- **Market data: live + same-day cache** — keep live yfinance/finviz/RS loading, add a thin user-scoped disk cache (same-day TTL) so iterative parameter-tweaking re-analysis is fast, rate-limit-safe, and reproducible within a day. Cache lives in a user-scoped location (portable for plugin distribution).
- **Copyright constraint** — both book DBs are full texts and stay git-ignored/local. Committed references must paraphrase principles with minimal short quotes, never reproduce chapters (repo is public on GitHub).

**Prime directive (user, 2026-07-10, clarified 2026-07-11, binding on all future design decisions)**: this harness exists to make Claude apply the Minervini methodology to industry/sector/ticker analysis, excellently. Analysis quality is the sole design criterion; maintainability may never be traded against it. Maintenance is the future maintainer session's job — it comes equipped with harness-creator, the codebase, and this spec, and needs no accommodation baked into the analyst-facing layers. During maintenance, methodology content is *data* (files being edited, read when needed); only during analysis is it *instruction* (live persona/doctrine). Maintenance instructions, status synchronization, and authoring policy stay in harness-spec.md or paths-gated rules so their analysis-time cost is zero; CLAUDE.md contains only facts and behavior needed by the Claude using the harness.

I3 routing decisions (2026-07-10):

- **Component census**: 2 skills (`minervini` analyst + `trade-review`), 1 agent (`ticker-scout`), 1 workflow (`/screen`, with documented sequential-subagent fallback), 1 rules file (`module-contract.md`, paths-scoped to scripts), CLAUDE.md, permissions (narrow allows + one deny), 0 hooks. Deliberately lean: every added skill/agent taxes the shared listing budget and routing attention.
- **Zero hooks, by eligibility** — the only "must never happen" items are (a) fabricating market numbers, which is not mechanically detectable (a hook cannot parse intent behind a WebSearch), and (b) touching the book DBs, which a `permissions.deny` `Edit(/.tmp/**)` rule (project-root anchored — the bare `.tmp/**` form resolves against cwd and leaks) enforces by itself (deny rules hold without a hook; hooks would add latency to every matching call for no additional guarantee). The data doctrine stays advisory but is double-anchored (CLAUDE.md + skill body) and validated behaviorally in I5.
- **Session context via skill preprocessing, not SessionStart hook** — the analyst skill body uses `` !`command` `` preprocessing to inject today's date, market open/closed, and cache state at skill-load time. Fires only when analysis actually happens (a SessionStart hook would tax every session including harness-maintenance ones) and is fresher (skill load time vs session start).
- **Two skills, not one** — analysis ("is X a buy / find leaders / should I sell X") and post-trade review ("grade my trades") have genuinely different trigger contexts and different inputs (market data vs the user's own trade log). Merging them would blur both descriptions. trade-review points into the analyst skill's references for doctrine instead of duplicating it.
- **One agent** — `ticker-scout` (read-only: Bash/Read/Grep) exists for screening fan-out: qualifying dozens of tickers floods the main context with JSON that has no value after the verdict. Deep-dive analysis deliberately stays in the main conversation (the user redirects mid-analysis; an agent round-trip would lossy-summarize exactly the evidence the user wants to see).
- **Code at repo root (`scripts/`), not inside the skill** — user decision (2026-07-10), adopted with agreement: the modules are a shared substrate invoked by both skills, the agent, and the workflow; placing them inside one skill's directory would misstate ownership. Plugin conversion is symmetric (`scripts/` → `${CLAUDE_PLUGIN_ROOT}/scripts`).
- **TraderLion final positioning (closes the deferred I1 ruling)** — the user's "classic theory vs practical guidebook" framing held up ~80%: TL is the practice layer (sell mechanics, stop placement, routines, post-analysis — the operational HOW Minervini's corpus lacks). The 20% correction from the knowledge maps: TL is not a neutral application guide — it carries its own doctrine that conflicts with SEPA at 26 documented points (early in-base entry, 1-4% stops with widening allowance, top-down index switch, intraday tactics). Treating it as "how to apply Minervini" without the two-tier constitution would silently mix those in. Hence: SEPA = constitution (invariant), TL = practice layer admitted where SEPA is silent, tagged and subordinated on conflict (TL-map §4 resolutions are binding).
- **`/screen` workflow** — the screening sweep is fixed-shape (regime → survey → fan-out qualify → synthesize watchlist), varying only in universe/date: the one orchestration worth freezing. Everything else (deep dives, sell checks) varies per invocation and stays conversational.

**Architecture v2 (2026-07-10, supersedes the mono-skill I3/I4 routing above; user-driven, adopted after re-derivation)**:

- **Constitution moves to CLAUDE.md.** The constitution (persona, funnel, corrections, two-tier rule, data doctrine, scope) is the never-miss content, and CLAUDE.md is the only unconditional channel: no trigger probability, no routing probability, compaction-proof. Skill-body placement bet it on trigger success; reference placement bet it on routing compliance — both are probabilities the constitution should not ride on, especially in a domain where the model's training priors make "I already know Minervini" rationalization easy.
- **Three skills split by user intent, not knowledge topic**: `market-scan` (market/sector/screening) / `ticker-analysis` (single named ticker) / `trade-review` (user's own log). Intent-level disambiguation is clean (ticker presence, market scope, own-trades input), duplication ≈ 0 because the shared constitution is ambient, and bodies shrink to ~100-line procedural shells — which also resolves the "routing table buried in a long body" omission concern.
- **Firm correction retained**: fundamentals vs chart are NOT separate skills. "Is X a buy" needs both, always, in order (invocation co-occurrence), and SEPA's probability-convergence doctrine forbids institutionalizing that separation. Knowledge heterogeneity is handled at the reference-file level (entry.md vs fundamentals.md).
- **Accepted debts, recorded**: (1) plugin conversion will require a constitution-shipping redesign since CLAUDE.md does not ship with plugins — excluded from consideration by explicit user instruction, revisit at pluginization; (2) persona is ambient in non-analysis sessions — waived by the prime directive; (3) CLAUDE.md ~150-180 lines — 200-line guideline consciously waived by user.
- **Hard budgets (implementation-validated)**: CLAUDE.md ≤180 lines; each skill body ≤120; each reference ≤350. Exceeding a budget is an implementation failure, not a style note.
- **Plan B (pre-agreed escalation)**: if validation or real use shows reference-skipping (answering sell/entry questions without reading the canonical reference), first strengthen the routing persuasion; if it persists, promote the skipped reference to its own skill — cheap because references are already modular files.

### Implementation rulings (2026-07-10)

- **Power Play exception**: probability convergence remains the default, but the Minervini map explicitly makes a VCP-qualified Power Play the sole setup allowed to proceed without verified fundamentals. This exception never waives Stage-2 eligibility, price/volume structure, market alignment, or risk controls, and every use must be labeled as the map-authorized exception.
- **MA role separation**: eligibility decisions use the 50/150/200 SMA stack and management decisions may use 10/21 EMA. A chart may co-display both sets for context, but an average never changes doctrinal role merely because both are visible.
- **RS fallback order**: use the cached or live cross-sectional score returned by the user's unofficial `ibd-rs-rating` package first; never describe it as the proprietary official IBD feed or reimplement its formula in the harness. If that package score is unavailable, compute and label the local proxy from the stock/SPY RS line, RS-day share, and 1M/3M/6M/12M historical percentile measures; only the 12M proxy percentile may provisionally stand in for the ≥70 eligibility gate because the map assigns short lookbacks to timing and 12M to eligibility. If neither source can produce a score, the gate is `unavailable`, never a fabricated pass or an analytical fail.
- **Sell extension inputs**: `sell_signals extension` accepts optional `--base-top`. Without a supplied or deterministic VCP pivot/base-top, it emits a `needs_input` value for base-top extension while still reporting MA extension and Minervini climax measures; it never invents a base.
- **Failure-cascade honesty**: 21 EMA, 50 SMA, and 200 SMA states are deterministic. The prior-high failed-retest stage is `needs_chart` unless the caller supplies an explicit prior-high and tolerance; the implementation must not silently invent a canonical nearness threshold.
- **Skill tool boundary**: the two analysis skills may bootstrap and run the module interpreter; `trade-review` only needs the qualified Python grant plus read/search tools. All three descriptions state that portfolio sizing is out of scope.
- **Budget and status semantics**: physical line counts are authoritative and include headings, blanks, and comments; a skill's 120-line budget excludes YAML frontmatter, while CLAUDE.md and references count every physical line. A component becomes `generated` only when every file in its binding component spec exists, and becomes `validated` only after Phase 5 passes.

## Validation

### Free structural checks (implementation session, mandatory, zero tokens)

- `validate_harness.py` → 0 errors for all non-workflow checks. Validate Dynamic Workflow syntax in Claude Code's async-function runtime because the stock validator checks the raw body as ESM and rejects its required top-level `return`; see the completed-outcomes compatibility note.
- Line budgets: CLAUDE.md ≤180; skill bodies ≤120; references ≤350 (mechanical count).
- All spec'd components exist; no dead pointers (incl. cross-skill reference paths from trade-review).
- `scripts/tests/smoke.py` passes against live APIs (schema-shape assertions per module).
- No hooks in this harness → `test_hook.py` n/a.

### E2E scenarios (headless sessions; runs in the implementation session after generation, only with user consent — costs roughly one full session per scenario)

| id | prompt (paraphrased) | expected | assertion type |
|----|---------------------|----------|----------------|
| V1 | "Is PLTR a buy right now?" | `ticker-analysis` triggers; runs `qualify` BEFORE opining; verdict cites gate results | trigger + behavior compliance |
| V2 | "How's the market looking these days?" | `market-scan` triggers; runs `discover`; regime verdict cites breadth/leader evidence | trigger + behavior compliance |
| V3 | "Should I sell my NVDA position?" | `ticker-analysis` triggers AND transcript shows Read of `references/sell.md` before the verdict | reference-routing probe (the architecture's known weak point) |
| V4 | "What % of my portfolio should be in tech?" | No sizing prescription; declines per scope guard, offers analysis instead | near-miss / scope guard |
| V5 | "What was AAPL's EPS growth last quarter?" | Number comes from a module invocation, not memory/websearch; on module failure, declares unavailable | data doctrine compliance |
| V6 | "Here are my last 10 trades: [log] — grade them" | `trade-review` triggers (not ticker-analysis); graded output with metrics | sibling routing |

Grading doctrine: every verdict must cite a transcript event (tool_use, file read) — surface compliance without evidence is a FAIL. After a repair, re-run only failed scenarios. Failure routing: trigger miss → description wording; triggered-but-wrong → body/reference content (strengthen the why first); reference skip → routing persuasion, then Plan B promotion.

### Consent status

- E2E consent: **granted and completed** (granted 2026-07-10; completed 2026-07-11) — all six isolated scenarios ran on the user's configured model and passed independent transcript-evidence grading.

### Completed outcomes (2026-07-11)

- Deterministic substrate: 72 unit/contract tests passed; 7 live/offline smoke checks passed; bootstrap imported 16 modules plus the pipeline; `pip check`, `compileall`, canonical root invocations, and cache miss/hit/bypass checks passed.
- Hard-gate semantics: focused tests proved known failure outranks unavailable evidence, missing evidence remains incomplete, and `qualify` never converts incomplete evidence into `AVOID`.
- Structure and fidelity: all component pointers resolve; line budgets pass (CLAUDE.md 126; skill bodies 56/68/89; references 136/174/107/134/198/119); `AGENTS.md` still targets `CLAUDE.md`; no hooks, tracked `.tmp` artifacts, committed venv, absolute user paths, or book text were found. Independent map-fidelity and analyst-perspective audits reported no blockers.
- Permissions: from a non-root cwd, normal `acceptEdits` mode denied an Edit under `.tmp/` while allowing a control Edit under `scripts/`. Installed Claude Code 2.1.207 also proved that `--dangerously-skip-permissions` bypasses the deny; it is therefore prohibited on the real repository and used only on disposable E2E copies.
- Workflow: raw-string and object arguments, candidate-origin retention, hostile early return, and fan-out batching passed mock-runtime tests. A real Claude Code 2.1.207 run of `/screen AAPL MSFT --max-candidates 2` completed all phases with the exact `2 → 2 → 2` funnel, classified AAPL `PROCEED` and MSFT `AVOID`, and preserved that `PROCEED` is not buy-ready.
- E2E: V1–V6 all passed evidence-cited independent grading. The transcripts proved `qualify`-before-opinion, breadth-plus-leader regime reasoning, `sell.md`-before-verdict, no-sizing refusal, module-sourced EPS, and clean `trade-review` sibling routing with metrics and the Loss Adjustment Exercise.
- Validator compatibility note: every structural check passes except the stock `validate_harness.py` workflow syntax probe, which invokes Node's raw ESM checker and reports `Illegal return statement`. Claude Code 2.1.207 executes Dynamic Workflow bodies inside an async function, where top-level `return` is required to deliver the workflow value; replacing it with an ESM-valid IIFE made the installed runtime return `undefined`. Runtime semantics were retained and verified by both an async-wrapper syntax test and the real `/screen` run. This is a validator false positive, not a harness runtime failure.

## Change history

- 2026-07-11 — correction — Updated the `ibd-rs-rating` infrastructure description from Supabase to Neon after the package migration. Cache behavior remains a harness-side same-session consistency and transient-failure-isolation mechanism; no RS formula or runtime integration changed.
- 2026-07-11 — implementation — Phases 5-6 completed: validated the substrate, permissions, live sources, workflow, and all six E2E scenarios; documented the Dynamic Workflow validator/runtime syntax incompatibility and dangerous-skip permission bypass; advanced B1–B28 to `validated`; added user setup, routing, `/screen`, trust, and safety guidance to README.
- 2026-07-11 — implementation — Phases 3-4 completed: generated three intent-separated skills, six map-grounded references, the read-only ticker scout, deterministic `/screen` workflow, paths-gated module contract, and exact narrow permission rules. Line budgets, command contracts, normal/hostile workflow mocks, no-dead-pointer checks, and independent doctrine/user-perspective audits pass. The stock strict validator's sole workflow false positive is documented under Validation; installed-runtime checks pass.
- 2026-07-11 — implementation — Phase 2 completed: generated a 126-line Minervini analyst constitution, preserved the `AGENTS.md` symlink, and passed strict validator, trigger-inventory, path/import, line-budget, M-map, and TL-map audits. User clarified that CLAUDE.md serves the Claude using the harness, not the harness developer; developer-facing status synchronization and methodology-authoring policy therefore remain in this spec, while the single CLAUDE.md pointer tells the analyst not to load the design record as runtime doctrine.
- 2026-07-11 — implementation — Phases 0-1 completed: migrated and hardened the Python substrate, added the ET-session cache/clock and new analysis modules, pinned `ibd-rs-rating==0.4.0`, and validated the authoritative package source without reimplementing its formula. Acceptance evidence: bootstrap/import smoke, 72 deterministic tests, 7 live/offline smoke tests, `pip check`, both canonical root invocations, and explicit RS miss → hit → bypass with no cache write during bypass. A live transient `YFRateLimitError` confirmed the approved thin cache remains a reliability and same-session consistency layer rather than merely a speed optimization.
- 2026-07-10 — new — Initial spec: Context + Goals + I1 design decisions recorded from interview. Knowledge-map workflows (Minervini corpus, TraderLion corpus) launched; reports land in `docs/plans/research/`.
- 2026-07-10 — new — Adversarial 4-lens verification of the implementation plan (30 findings: 0 critical / 14 major / 16 minor) → plan rewritten as rev 2; spec corrected in the same pass (B15/B20/B27 cells, cascade third stage per TL-map clusters E/J, deny-rule anchoring, qualified frontmatter Bash, cache session-date semantics, sell_signals↔stage_analysis single-ownership).
- 2026-07-10 — new — **I5 final gate passed: spec approved in full** (architecture v2, validation plan, E2E consent granted). Skill names locked: market-scan / ticker-analysis / trade-review. Next: implementation plan docs in docs/plans/, then commit/push.
- 2026-07-10 — new — I2 gate passed (28-item inventory; post-trade review in v1, intraday and secondary universe deferred). I3 gate passed (initial mono-skill routing). I4 debate: user challenged mono-skill sizing across multiple rounds → architecture v2 adopted (constitution → CLAUDE.md; three intent-split skills market-scan / ticker-analysis / trade-review; see Design rationale). Prime directive recorded. Code relocated to repo-root scripts/. Terminology ban dropped (jargon allowed in output).
- 2026-07-10 — new — I1 gate passed: user explicitly approved Goals (9 items) and the provisional design decisions. Both knowledge-map chapter extractions (15 + 13 agents) completed; synthesis stages re-running after a session-limit interruption.
