# Harness of Minervini — Implementation Plan (rev 2)

> **이 문서는 다음 Claude 세션(구현 세션)을 위한 마스터 플랜입니다.** 계획 세션(2026-07-10)에서 사용자와 다섯 단계의 인터뷰 게이트를 거쳐 전부 승인되었고, 이후 4-렌즈 적대적 검증(30개 발견)을 반영해 개정되었습니다. 구현 세션은 이 문서를 위에서 아래로 실행하면 됩니다. 본문은 구현 정밀도를 위해 영어로 작성되었습니다.

## 0. How to use this document

Read these, in this order, before writing any file:

1. `.claude/harness-spec.md` — the **binding record** of what was agreed and why. If this plan and the spec disagree, the spec wins — except where a spec inventory cell is itself stale against the spec's own Component specs / Design rationale (those sections are the authoritative layer); fix any such drift in the same pass.
2. This file — the execution plan: phases, file-by-file specs, acceptance criteria.
3. `docs/plans/research/minervini-knowledge-map.md` (M-map) and `docs/plans/research/traderlion-knowledge-map.md` (TL-map) — the **authoritative knowledge sources** for all doctrine authoring. Every reference file traces to their clusters and (a)/(b)/(c)/(d) encoding buckets. Do not author doctrine from your own training priors — your priors lack this harness's adjudications (TL-map §4 conflict resolutions, TL gap-fillers, flex/locked tier split).
4. Prototype code at `.tmp/Minervini/Scripts/` — migration source. A good substrate with known debts, not gospel.
5. **Tooling**: the validators live in the harness-creator skill, not in this repo — `~/.claude/skills/harness-creator/scripts/{validate_harness.py, test_hook.py, run_e2e.py}`. The binding file-format conventions (rules frontmatter, workflow script constraints, e2e flags, skill authoring doctrine) are in `~/.claude/skills/harness-creator/references/{claude-md-and-rules,skills,workflows,e2e-testing,hooks}.md` — load the relevant reference before authoring each component type in Phases 2-4.

**Prime directive (binding)**: this harness exists to make Claude apply the Minervini methodology to industry/sector/ticker analysis, excellently. Analysis quality is the sole design criterion; maintainability never trades against it.

**Language**: all generated artifacts in English.

**Authoring doctrine** (binding on every prose file):
- Conviction over compliance: every rule ships with its why, vivid enough to re-derive the rule in unenumerated cases.
- Don't write what the model already knows — the maps' (a)-buckets list what NOT to encode. Value concentrates in the gotchas (reversals of model defaults) and adjudications absent from training data.
- Numbers carry their justification and their exception in the same breath.
- No mid-sentence hard-wrapping.
- Paraphrase-first: verbatim quotes ≤200 chars, sparing. Book DBs (`.tmp/*.db`) are gitignored — never commit or quote them at length (public repo).

**Hard budgets (Phase 5 mechanically checks; exceeding = implementation failure)**: CLAUDE.md ≤180 lines; each SKILL.md body ≤120 (excl. frontmatter); each reference ≤350. All counts are all-inclusive (headings and blank lines count).

**Canonical invocation shape (pinned; reused verbatim in CLAUDE.md, ticker-scout, screen.js, permissions.allow)**:

```
scripts/.venv/bin/python scripts/pipeline qualify AAPL
scripts/.venv/bin/python scripts/modules/<module>.py <subcommand> [flags]
```

cd-free, project-root-relative, no env vars required. `$MINERVINI_VENV` (a venv **directory**, default `scripts/.venv`) may override the interpreter as `"$MINERVINI_VENV/bin/python"`. Phase 0 must verify these run from the repo root; if the migrated code still requires `cwd=scripts/`, fix the path bootstrap in code (preferred) rather than changing the canonical shape.

## 1. Target architecture (v2, approved)

```
CLAUDE.md                      ← the CONSTITUTION: unconditional, compaction-proof
.claude/
  harness-spec.md              ← exists; update statuses as you generate
  settings.json                ← permissions (deny + narrow allows)
  rules/module-contract.md     ← paths-gated to scripts/**
  agents/ticker-scout.md       ← read-only screening fan-out agent
  workflows/screen.js          ← /screen one-button sweep
  skills/
    market-scan/               ← intent: market/sector/screening
      SKILL.md + references/{regime,screening}.md
    ticker-analysis/           ← intent: single named ticker, full funnel
      SKILL.md + references/{entry,fundamentals,sell,cases}.md
    trade-review/              ← intent: grade the user's own trade log
      SKILL.md
scripts/                       ← shared code substrate (repo root, NOT inside a skill)
  modules/  pipeline/  tests/  bootstrap.sh  requirements.txt
docs/plans/                    ← this plan + research maps
```

Why this shape (full rationale in spec): the constitution is never-miss content and CLAUDE.md is the only channel with no trigger probability, no routing probability, and compaction survival. Skills split by **user intent**, never by knowledge topic — fundamentals and chart are one skill because "is X a buy" always needs both in order, and SEPA's probability-convergence doctrine forbids institutionalizing their separation.

**Two-tier doctrine (constitutional)**: SEPA gates = immutable; TraderLion tactics = tunable defaults with origin tags; on conflict Minervini wins unless his corpus is silent. TL-map §4's 26 resolutions are binding — encode their outcomes, never re-litigate.

## 2. Phase 0 — Environment & migration substrate

1. Copy `.tmp/Minervini/Scripts/modules/*.py` and `Scripts/pipeline/*.py` into `scripts/modules/`, `scripts/pipeline/` (drop `__pycache__`; never copy `.venv`).
2. `scripts/requirements.txt`: keep `yfinance>=0.2.36, pandas, numpy, lxml, requests, ibd-rs-rating`; add `mplfinance`; drop the 6 dead deps (`fredapi, python-dotenv, finvizfinance, finviz, sec-edgar-downloader, sec-analyzer`). Do not carry over `.env` (all 4 keys unused).
3. `scripts/bootstrap.sh`: resolve venv dir (`${MINERVINI_VENV:-scripts/.venv}`), create if missing, `pip install -r`, import-smoke each module. Idempotent.
4. Add `scripts/.venv/` to `.gitignore`.
5. **Acceptance**: `bash scripts/bootstrap.sh` exits 0 on a clean checkout; both canonical shapes (§0) return valid JSON **from the repo root**; second invocation of the same fetch hits the cache (Phase 1 §3.1 — verify with timing or a cache log line, including one `rs_ranking score` call).

## 3. Phase 1 — Code substrate refactors & new modules

### 3.1 Cache layer (utils.py) — all three live sources

Read-through cache wrapping **yfinance fetches, the finviz scrape, AND ibd-rs-rating/Supabase lookups** (`rs_ranking` and pipeline's `from rs_rating import RS` path) — the /screen fan-out re-queries RS for dozens of tickers, exactly the rate-limit-fragile path the cache was approved for.

- Key: `(source, symbol, function, params-hash, session-date)` where **session-date = the last completed US trading session in America/New_York** (roll back over weekends/holidays) — NOT the local calendar date (the user runs from KST; KST midnight falls mid-US-session).
- While the US market is **open**, OHLCV/price endpoints bypass the cache (or use a short TTL ≤15min); financials/info/earnings-dates keep the session TTL. Reuse `market_clock` (§3.5) for open/closed and session-date logic.
- Store JSON under `${MINERVINI_CACHE_DIR:-~/.cache/minervini-harness}/`. `--no-cache` escape hatch on every module.

### 3.2 Contract audit of the 12 migrated modules

Uniform conventions (codified in `.claude/rules/module-contract.md`, Phase 4): argparse subcommands; JSON to stdout via `utils.output_json`; `{"error": ...}` + exit 1; flex-tier flags with canonical defaults; locked floors as named constants with rationale comments; per-module `doctrine` field; `--help` is the live spec. Keep the deliberate absence of an "analyze everything" command. Plus:

- **Provenance tags** on thresholds: `[M]` (Minervini canon) / `[TL]` (TraderLion) / `[TL-Kell]` (Kell lineage via TL) / `[MM-Ryan]`, `[MM-Zanger]`, `[MM-RitchieII]` (Momentum Masters roundtable — a within-M-corpus speaker distinction, separate from the TL origin tag; only `[M]`/Minervini answers are canonical).
- **Fragile-source isolation** (B23): in composite outputs (`discover`), finviz and RS-backend failures degrade per-section (a `"unavailable"` field for that section) — never whole-command failure. Add one smoke assertion for the degraded shape if cheaply simulable.
- **sell_signals ↔ stage_analysis reconciliation**: `stage_analysis risk` already computes largest-decline-since-Stage-2 and climax extension. Single-owner each quantity: sell_signals does NOT reimplement them — its docs point to `stage_analysis risk`. Rewrite stage_analysis's docstring/doctrine, which currently brands key-reversal a "generic-TA fabrication": key-reversal now exists as a TL-tagged instrument in sell_signals (excluded from SEPA canon, admitted via the two-tier practice layer) — the honest provenance framing, not a contradiction between two `--help` texts.

### 3.3 New module: `scripts/modules/sell_signals.py`

Thresholds from M-map cluster H + TL-map cluster E; TL items origin-tagged. Subcommands:

- `reversal SYMBOL` — TL key-reversal 6-item checklist. Per-item output with two honesty rules: item ① (visual extension at highs) is quantified by reusing `extension` thresholds **with an "invented heuristic, not canonical" caveat comment** (the `--margin-min-ppt` precedent); item ③ (high trendline break) has no deterministic anchor in the source doctrine — emit `"needs_chart"` for it and route to chart_render corroboration rather than silently inventing a trendline algorithm as doctrine. Count reflects only determinate items.
- `extension SYMBOL` — % above base top (vs TL +20-25% sell-into-strength zone), % above 50d/200d MAs, climax-velocity flags `[M]`.
- `trail SYMBOL [--ma 21e|50s] [--start DATE]` — 2-consecutive-close MA-trail state machine `[TL-Kell]`. Emits the **full dated event sequence** over the requested period (every violation with dates), not just current state — one contract serves live monitoring and trade-review's retrospective grading.
- `cascade SYMBOL [--start DATE]` — failure-cascade state `[TL]`: 21 EMA loss (first signal) → 50 SMA loss (confirmation) → **downside reversal at/near the prior high (failed retest = top confirmation)**, with 200 SMA loss as terminal state (TL-map clusters E/J; PTON/SHOP cases). Dated sequence output like `trail`. (Note: "reversal below prior low" is key-reversal item ⑥, NOT the cascade's third stage — an earlier draft of this plan and spec B15 had this wrong; the spec was corrected in the same pass as this revision.)
- Drawdown-since-Stage-2 is NOT duplicated here — use `stage_analysis risk` (§3.2 reconciliation).

### 3.4 New module: `scripts/modules/chart_render.py`

`daily|weekly SYMBOL [--period ...] [--out PNG]` via mplfinance. MA sets respect the constitutional MA-vocabulary rule: **daily = 10/21 EMA + 50/150/200 SMA; weekly = 10/30/40-week SMA equivalents** (or resample from daily) — never a 200-*week* MA. Implementation notes: mplfinance's `mav=` computes SMAs only — EMAs, ±25% volume bands, and pivot annotations go through `make_addplot` with self-computed series; fetch `period + longest-MA warmup` so long MAs are populated across the visible window. Output defaults into the cache dir. Doctrine: numbers decide, eyes corroborate — never a gate.

### 3.5 Smaller additions

- **`market_clock.py`** (new, tiny): emits `{now_local, now_et, market_open, session: pre|regular|after|closed, last_completed_session, cache_entries}`. Used by: skill preprocessing blocks (Phase 3), cache session-date logic (§3.1).
- **`info.py get-history SYMBOL --start --end [--interval 1d|1wk]`** — raw OHLCV through the cache layer. Required by trade-review (post-exit tracking windows, as-of grading) so it never violates the data doctrine.
- **`volume_analysis.py runrate SYMBOL`** — current-session cumulative volume extrapolated by fraction-of-session-elapsed (cache-exempt). Required by entry.md's intraday run-rate check; without it the doctrine-compliant path doesn't exist.
- Closing-range % (`CR=(C-L)/(H-L)`), ±25% volume bands, ADR% — add where natural (TL cluster A quantifiers).
- `actions.py get-earnings-dates --days-until` — earnings-event policy needs days-to-next-report.
- **`market_breadth.py`**: add the QQQ-vs-21EMA switch state with the **asymmetric** definition (TL-map cluster F(d) — its #1 flagged gotcha): ON = one QQQ close above the 21 EMA; OFF = two consecutive closes below the 21 EMA **and** the second close below the prior day's low. Not a symmetric boolean.
- **`rs_ranking.py` proxy hardening** (B20): add the harness's own RS-proxy computation — RS line vs SPY, RS-days >60%, AS-style 1M/3M/6M/12M percentile ranks (TL-map §4-4 spec) — as a documented fallback when the ibd-rs-rating backend is unavailable, tagged as proxy (IBD RS is proprietary).

### 3.6 Tests

`scripts/tests/smoke.py`: each module × primary subcommand against AAPL/SPY; assert JSON parses, keys exist, types correct (no value assertions); include one degraded-shape assertion (§3.2) and one cache-hit assertion (§3.1). Runnable standalone.

**Acceptance (Phase 1)**: smoke green; every `--help` documents all flags; TL-origin thresholds tagged; RS cache-hit demonstrated; canonical shapes work cd-free from repo root.

## 4. Phase 2 — CLAUDE.md (the constitution)

Author fresh (current file is empty; AGENTS.md symlinks to it — leave the symlink). **≤180 lines all-inclusive** — cap the constitution section at ~95 content lines so headings/blanks have headroom. Structure:

1. **Identity & purpose** (~10): what this harness is; pointer to `.claude/harness-spec.md` as the binding design record; the three trigger rules below are the only component mentions.
2. **Analyst constitution** (≤95) — distilled from the maps' (b)-buckets, each item with its compact why:
   - Persona & risk spine: conservative-aggressive opportunist; risk-first question order; no-trade strong default; ~50% win-rate calibration; decision quality ≠ outcome. [M-map I]
   - Funnel + probability convergence: Trend Template/Stage-2 gates fundamentals; cheap gate first, earn each deeper look; no trade without fundamentals × price/volume × market alignment. [M-map A/C]
   - Anti-default corrections (one line + why each): lockout rally; anti-ATR; ultra-low P/E + 52wk low = red flag; cheap-trap ban; broken-leader ban; price leads earnings both ways; no bottom fishing / no averaging down. [M-map B/C/F/H]
   - Two-tier doctrine: SEPA immutable / TL tunable+tagged / Minervini-first; MA-vocabulary role separation (50/150/200 SMA = eligibility; 10/21 EMA = trade management; never mixed); Momentum Masters speaker rule.
   - Scope guards: US only; long + cash; never portfolio %-allocations (ticker-level sell/hold in scope); daily/weekly TF.
   - Data doctrine: market numbers only from `scripts/` modules — never memory, never web search; narrative may use web search; module failure → retry once → declare unavailable.
   - Chart doctrine: numbers decide, eyes corroborate.
3. **Module invocation facts** (~15): the canonical shapes from §0, verbatim; JSON contract; `--no-cache` exists.
4. **Trigger rules** (~6): condition → skill for market-scan / ticker-analysis / trade-review (compaction insurance).
5. **Repo layout + bootstrap** (~10).
6. **Authoring policy** (~4): paraphrase-first; book DBs never committed.

Anti-pattern check: no component inventory prose; no generic advice; every line passes "would removing it cause a mistake?"

## 5. Phase 3 — Skills and references

Order: references first (from the maps), then bodies, then descriptions (tuned against each other + near-misses). **Frontmatter for all three skills**: `allowed-tools` with qualified Bash grants matching settings.json shapes — `Bash(scripts/.venv/bin/python *)`, `Bash(bash scripts/bootstrap.sh)` — plus `Read, Grep, Glob` and (analysis skills only) `WebSearch, WebFetch`; `model` unset. Blanket `Bash` is forbidden (it would dead-weight the narrow allow rules exactly when they matter).

**Preprocessing blocks** (both analysis skills, first element of each body): `` !`scripts/.venv/bin/python scripts/modules/market_clock.py` `` — one command supplying date, ET clock, market open/closed, last completed session, cache state. Ship its exact shape in permissions.allow (Phase 4).

### 5.1 `market-scan`

- **references/regime.md** (≤350): M-map cluster B (lockout signature: index pullbacks 3-5%; bottom checklist; leader divergence; pilot → traction + second wave → expand; "tighten stops, don't opinion-liquidate"; repeated stop-outs = timing feedback) + TL-map cluster F per §4-7 dual-gate (QQQ 21EMA switch = information filter with the **asymmetric** on/off definition, never a symmetric boolean; leader/trade feedback = exposure decider; cycle-age calendar as context). Include the "what would refute this regime read" habit.
- **references/screening.md** (≤350): M-map cluster A screening architecture (parallel loose screens; no monolithic AND; recurring-name observation) + TL-map cluster G (funnel counts 400-500→~75→≤15→1-5; TIGERS; screen recipes vendor-agnostic; RS-proxy spec pointing at the §3.5 rs_ranking fallback) + watchlist state machine (watch → buy-alert → buy-ready; re-entry doctrine; base-reset vs pivot-reset) + `/screen` sequential-subagent fallback procedure.
- **SKILL.md body** (≤120): preprocessing; procedure (`discover` → breadth/leader read → dual-gate regime verdict); screening funnel with ticker-scout fan-out + `/screen` pointer + fallback; mandatory persuasion-framed reference routing ("your training priors do not contain this harness's adjudicated doctrine — the references do"); output conventions.
- **description**: enumerate intents (market health, breadth, sector/industry strength, find stocks/leaders/breakouts, watchlist) + near-misses (named single ticker → ticker-analysis; own trades → trade-review; no sizing).

### 5.2 `ticker-analysis`

- **references/entry.md** (≤350): M-map clusters C+D — Trend Template context (the 8 criteria live in code; prose carries the why + Stage semantics + base counting 1-2 prime / 3 ok / 4-5 late), VCP footprint notation (nW d/f nT), contraction-halving, pivot + volume confirmation (5-20¢ buffer; **chase limit: buy within 1.5% of pivot** — TL-tagged harness default per §4-18, M corpus says only "a few %"; intraday run-rate via `volume_analysis runrate` §3.5), last-weak-hand/shakeout logic, squat/tennis-ball/reset playbook (~50% retest base rate), 3C + Power Play (only no-fundamentals setup), primary-base IPO rules (duration-keyed depth bands; all-time-high trigger; FB-2012 disqualification), time-compression invalidation. TL daily-TF tactics (add-on schedule 10d/21e/50d-first-touch; RS-gated MA pullback; undercut-reclaim) in a marked **opt-in section** tagged TL per §4-1.
- **references/fundamentals.md** (≤350): M-map clusters **A(c)**+E+F+G — the **12-item manual review checklist** as the final-candidate scoring instrument and the **catalyst detective-work guide** (catalyst narrative may use WebSearch per data doctrine) [both from A(c) — Catalyst is one of SEPA's five mandatory elements]; earnings screen (EPS ≥20-25% YoY, bull-market 40-100%+, acceleration, 2-quarter rolling smoothing), Code 33, surprise/drift/cockroach, guidance forensics (lowered-bar beat, flip-flop tell, spin rule), inventory/receivables 2x screen, valuation de-biasing (P/E expansion tracker 2x/2.5-3x; no P/E ceiling; Crocs pair), 6-category classification mandatory-first + cyclical inverse-P/E, leader/group rules.
- **references/sell.md** (≤350): M-map cluster H spine (stop = min(half realized avg gain, 10%) with the feedback-loop logic; 2:1-3:1 ratio integrity at 40-50% win rates; 3R breakeven; bad-market tightening; time-based exit; profit = principal; involuntary-investor detector; Stage-2 max-drawdown sell even after good earnings; slippage = next tick; **daily position audit + the 4-plan contingency template with pre-market rehearsal** [H(c)]) + TL gap-fillers tagged (extension zone +20-25%; RME; key-reversal 6-item; MA-trail 2-close baseline 21e/50s; failure cascade **ending in downside reversal at/near the prior high, 200 SMA terminal** — see §3.3; earnings policy: no new entry right before a report [hard], pre-report trim as beginner default with cushion-based discretion as M-mode) + §4-5 referee (R-multiple beats +5% when they disagree) + §4-24 (repeated stop-outs → entry quality or regime, never wider stops).
- **references/cases.md** (≤350): 10-14 worked examples, few-shot format (setup → decision → outcome → lesson), source-tagged: PCYC 2010, Amgen 1990, VIVO 2006-07, MELI 2007, CRUS 2010, TASR 2004, SWN reset, Crocs P/E pair, Dell deceleration top, NFLX 2010 resilience, FB 2012 disqualification, IRBT 2006 clean loss, U.S. Surgical 1990.
- **SKILL.md body** (≤120): **preprocessing (same block as market-scan)**; funnel procedure (qualify gate → earn deeper looks: entry → fundamentals → sell plan → convergence verdict including market context via `market-scan` doctrine or a fresh `discover`); chart corroboration; mandatory persuasion-framed reference routing; output conventions (evidence-cited verdict, watchlist states, no sizing).
- **description**: single named US ticker buy/sell/hold/diagnosis + near-misses (market-level → market-scan; own trades → trade-review; sizing never).

### 5.3 `trade-review`

- **Frontmatter**: `allowed-tools: Bash(scripts/.venv/bin/python *), Read, Grep, Glob` — Bash is required: post-exit tracking and as-of grading fetch data via `info.py get-history` and `sell_signals trail/cascade --start` (§3.5, §3.3), never from memory/web. `model` unset.
- **Body**: input expectations (ticker, entry/exit dates & prices, stop, size optional), Top-5/Bottom-10 selection, per-action /10 scoring, metrics suite (batting average with ±1% scratch band, avg win/loss, R-multiples, hold-time asymmetry), Loss Adjustment Exercise, post-exit tracking windows, RDDT-style output shape. Grading criteria via `../ticker-analysis/references/{sell,entry}.md` (no doctrine duplication). No bundled scripts.

### 5.4 Description cross-check

After all three exist, read the descriptions against each other: no trigger overlap, near-miss language present, each names underlying intent not just keywords. Explicit step — validate_harness.py cannot grade trigger quality (see harness-creator references/skills.md).

## 6. Phase 4 — Agent, workflow, rules, settings

- **`.claude/agents/ticker-scout.md`**: `name: ticker-scout`; description (screening fan-out only); `tools: Read, Grep, Glob, Bash`; model unset. Body self-contained (agents get NO default system prompt): canonical invocation recipe (§0), qualify JSON contract, return format (verdict + failed gates + RS + stage + 1-line evidence, ≤10 lines), prohibitions (no deep dive, no edits, no WebSearch, never fill data from memory; declare unavailable on module failure).
- **`.claude/workflows/screen.js`**: thin, per harness-creator references/workflows.md (pure-literal meta; no Date.now()/Math.random(); judgment only in prompt strings): Phase Regime (one agent runs `discover`) → hostile-regime early return → Phase Fan-out (one agent per candidate, `qualify`, schema-validated) → Phase Synthesize (ranked watchlist, funnel-count discipline).
- **`.claude/rules/module-contract.md`**: frontmatter `paths: ["scripts/**"]`; content = §3.2 contract with whys.
- **`.claude/settings.json`**:
  - `permissions.deny`: **`Edit(/.tmp/**)`** — single leading slash = project-root anchored. The bare form `Edit(.tmp/**)` resolves against cwd and silently stops protecting the book DBs whenever cwd ≠ repo root.
  - `permissions.allow` (narrow; exact strings tested against real invocations — note the trailing space before `*` enforces a word boundary): `Bash(scripts/.venv/bin/python *)`, `Bash(bash scripts/bootstrap.sh)`, `Bash(git status)`, `Bash(git diff *)`. This set also covers the skill preprocessing command and everything screen.js's agents run (workflow agents cannot answer permission prompts mid-run) — ship in the same commit as screen.js.
  - Docs note: project allow rules activate only after workspace trust.

## 7. Phase 5 — Validation (consented plan)

1. **Structural (free, mandatory)**: `python3 ~/.claude/skills/harness-creator/scripts/validate_harness.py --path . --strict` → 0 errors; line budgets (≤180/≤120/≤350, all-inclusive); cross-skill reference paths resolve; smoke suite green; **deny-rule live probe** (attempt an Edit on a `.tmp/` file with cwd ≠ repo root; confirm the deny fires — no structural check covers deny efficacy).
2. **E2E (consented)**: the 6 scenarios in spec Validation (V1-V6) via `run_e2e.py` (`~/.claude/skills/harness-creator/scripts/`; read references/e2e-testing.md first — headless permission handling is a documented best guess; the first real run is the confirmation). Evidence-cited grading; surface compliance without evidence = FAIL. V3 (sell question actually Reads sell.md) and V5 (numbers from modules only) are the designated weak-point probes.
3. **Repair routing**: trigger miss → description; wrong behavior → strengthen the why; reference skip → routing persuasion, then Plan B (promote that reference to a skill); re-run failed scenarios only.
4. Record outcomes in spec Validation; advance inventory statuses `approved → generated → validated` per component.

## 8. Phase 6 — Wrap-up

- Update `.claude/harness-spec.md`: statuses, Change history (mode: new; what was generated; validation results).
- Commit in coherent units (substrate / constitution+skills / agent+workflow+settings / validation), push to origin. Never commit `.tmp/` or any venv.
- README section: bootstrap, the three skills, /screen, workspace-trust note.

## 9. Deferred (v2 backlog — do NOT implement now)

Edge-study/model-book workflows; TraderLion Ch.12 chart recovery (text ~95% unreliable AI alt-text — needs original PDF or model-book regeneration from the ticker+year register); intraday tactics module (§4-22 opt-in); TL secondary universe classes (§4-15, default disallowed); plugin conversion (constitution-shipping redesign + public-name trademark diligence — "Minervini"/"SEPA"/"TraderLion" are commercial marks).

## 10. Implementer gotchas (hard-won; read before Phase 2)

1. Your training priors contain Minervini's public doctrine — NOT this harness's adjudications (26 conflict resolutions, TL gap-fillers, flex/locked split). Author from the maps.
2. Momentum Masters excerpts (M-map appendix O): only Minervini's answers are canonical; Ryan/Zanger/Ritchie II numbers carry `[MM-*]` speaker tags — a within-M-corpus distinction, separate from `[TL]`.
3. `--margin-min-ppt 0.5` in the prototype is an invented heuristic (canonical is directional-only) — keep the honest caveat. Same honesty pattern applies to key-reversal items ① and ③ (§3.3).
4. TL-map §6: don't mine TraderLion Ch.12 text for chart specifics — the alt-text is unreliable (verified: describes up-years as down). Its usable yield is already distilled into the map.
5. Body Central case: the book's "December 2011" is an error for December 2010 (buy date 2011-01-05 is correct).
6. `.codex/` symlinks hooks/skills to `.claude/` — anything you create appears there too; harmless.
7. CLAUDE.md edits don't take effect mid-session; SKILL.md edits do. Iterate skills live; restart to test constitution changes.
8. The failure cascade's third stage is a failed retest at/near the **prior high** (top confirmation), not a break of the prior low — an earlier plan draft and spec B15 had this wrong (fixed 2026-07-10); if you see the old wording anywhere, the TL-map clusters E/J are authoritative.
