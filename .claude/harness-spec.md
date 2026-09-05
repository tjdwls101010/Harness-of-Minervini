# Harness Spec — Harness of Minervini v2

## Status and purpose

This is the maintainers' design record for the v2 Harness of Minervini. It explains where behavior lives, why the runtime is shaped this way, and how to change it without duplicating contracts. It is not runtime market doctrine and must not be loaded during an analysis session.

The approved implementation plan is `docs/plans/260817/harness-v2-greenfield-plan.md`. That plan is the decision-complete build record; this spec records the resulting architecture and maintenance invariants.

The product objective is an evidence-disciplined Minervini SEPA analyst for US-listed common stocks and ADRs that can assess the market, rank sector and industry leadership, discover candidates, analyze named tickers, and state conditional entry or active-position exit evidence. Portfolio allocation, position-size prescriptions, shorts, intraday trading, crypto, and non-US listings are outside scope.

The quality criterion is not imitation by prose volume. The harness must preserve Minervini's explicit gates and tacit decision standard while improving auditability, point-in-time honesty, missing-evidence handling, interface discoverability, and deterministic composition.

## Binding design decisions

- Principle over rail: `CLAUDE.md` supplies decision principles, invariants, precedence, and scope. Skills adapt those principles to user intent; they do not force one universal sequence or monolithic pipeline.
- Interface over document: exact syntax, defaults, inputs, limits, statuses, schemas, and side effects belong to the executable capability registry and each leaf command's offline `--help`, not duplicated prose catalogs.
- Dense information through progressive disclosure: the analyst loads the small constitution and one routed skill, then discovers only the capability contract needed for the next unresolved question through `capabilities`, `describe`, or leaf `--help`.
- Evidence over narrative: deterministic providers and reducers own precise market facts and verdict mechanics. Web research may explain current context but cannot fill numerical gaps, alter a hard gate, or masquerade as point-in-time evidence.
- Missing is not failure: known failed evidence and unavailable evidence remain separate throughout providers, reducers, envelopes, skills, and user-facing conclusions.
- No-trade is valid: the system is not required to manufacture candidates, bullish regimes, or BUY-READY outcomes.
- One shared harness: Claude Code uses `.claude/skills`; Codex reaches the same files through `.codex/skills -> ../.claude/skills`. `AGENTS.md -> CLAUDE.md` shares the constitution. No duplicated Codex copy exists.

## Information ownership

| Information | Authoritative owner | Duplication rule |
|---|---|---|
| Identity, scope, immutable analyst principles, data integrity, side-effect policy, routing | `CLAUDE.md` | Skills may operationalize but must not redefine these rules. |
| Triggering and adaptive task method | `.claude/skills/*/SKILL.md` | Keep only task-specific judgment and interface-discovery behavior. |
| Capability names, summaries, arguments, defaults, limitations, status semantics, side effects, examples | `scripts/minervini/capabilities.py` and `scripts/minervini/cli.py` | Generate or expose through `capabilities`, `describe`, schema, and detailed leaf `--help`; do not mirror the catalog in Markdown. |
| Executable doctrine claims, precedence, required inputs, failure and missing semantics, provenance | `doctrine/claims.json` through `scripts/minervini/doctrine.py` | Runtime skills use doctrine IDs and embodied principles; source attribution stays in the registry for audit rather than consuming analyst context. |
| Envelope and provider contracts | `scripts/minervini/contracts.py` and `scripts/minervini/providers/` | Schemas and tests must agree with code; prose summarizes only the invariant. |
| Detailed v2 decisions, migration order, and acceptance plan | `docs/plans/260817/harness-v2-greenfield-plan.md` | Do not convert the plan into runtime instructions. |
| Historical source corpora and prototypes | `.tmp/` | Build-time material only; ignored, edit-denied, and forbidden at runtime. |

The runtime skills deliberately do not cite books or maintain human-facing bibliographies. Their job is to make the analyst apply the normalized doctrine. Provenance remains machine-auditable in the doctrine registry, where it can support maintenance without bloating every analysis session.

## Runtime topology

The always-loaded root is `CLAUDE.md`; `AGENTS.md` is its symbolic link. The only routed runtime skills are `.claude/skills/market-scan/SKILL.md` and `.claude/skills/ticker-analysis/SKILL.md`; `.codex/skills` is a symbolic link to that directory.

There are no project agents, rules, workflows, or duplicate `.codex/skills`. Fixed scout agents and a `/screen` workflow were retired because concurrency and depth should follow the actual candidate set and unresolved evidence rather than a hard-coded fan-out rail. Cross-cutting JSON, schema, clock, retry, and side-effect guarantees are enforced by code and tests, not by advisory hooks.

One hook exists: a `SessionStart` readiness notice. It is not an analytical guarantee — those stay in code — but a report about whether the code can run at all, which no test inside the runtime can deliver to a session that is about to trust it. It runs only the offline half of `health`, so it costs no network, and prints nothing when everything is ready.

`.claude/settings.json` permits only the canonical pipeline and bootstrap command families and denies edits under `/.tmp/**`. Normal analysis remains read-only except for the ignored cache; chart artifacts and research-ledger mutations require their explicitly side-effecting capabilities.

## Interface architecture

The canonical entry point is `scripts/.venv/bin/python scripts/pipeline`. `scripts/pipeline/__main__.py` delegates to `scripts.minervini.cli`; the public analyst interface never calls legacy `scripts/modules` commands.

The registry exposes 22 composable capabilities: discovery and self-description (`capabilities`, `describe`, `health`, `clock`, `doctrine.list`, `doctrine.show`), market work (`market.snapshot`, `market.candidates`), ticker work (`ticker.qualify`, `ticker.swings`, `ticker.power-play`, `ticker.setup`, `ticker.fundamentals`, `ticker.cik`, `ticker.peers`, `ticker.chart`, `ticker.risk`), and explicit research state (`watchlist.show`, `watchlist.history`, `watchlist.record`, `watchlist.annotate`, `watchlist.export`). The count and names are contractual and tested.

Every non-help invocation emits exactly one v2 JSON envelope with `schema_version`, `operation`, `request`, `as_of`, `status`, `data`, `signals`, `missing`, `sources`, `doctrine_ids`, `next_capabilities`, and `side_effects`. Status is one of `ok`, `partial`, `unavailable`, or `needs_input`; it describes contract completeness, not an investment recommendation.

`scripts/minervini/capabilities.py` is the metadata source for listing and description. `scripts/minervini/schema_sync.py` projects that registry into the 22 immutable-ID schemas under `schemas/v2/`. `scripts/minervini/cli.py` builds detailed offline help from the same meanings. Tests reject metadata, help, schema, and envelope drift.

Help is deliberately detailed at the point of use. Root and group help orient the caller; every leaf help explains purpose, required and optional inputs, defaults, as-of behavior, provider or historical limits, status meanings, side effects, and examples. Markdown teaches how to discover help but does not restate all flags.

Candidate pagination bounds both eligible rows and diagnostic bulk. Exclusion evidence retains the complete excluded-record count and complete counts by reason, while returning at most `min(limit, 20)` representative records; auditability therefore does not require sending the current security master's entire excluded population through model context.

`--format compact|full` changes detail only and cannot change verdicts, signals, missing-evidence meaning, doctrine IDs, or source truth. `--no-cache` bypasses cache reads and writes and exists for fresh diagnostics, not ordinary analysis.

## Doctrine and decision architecture

The normalized doctrine registry is the executable source of hard gates and precedence. It currently contains the standard Stage 2 and eight-of-eight Trend Template route, the bounded recent-IPO Primary Base route, VCP supply and setup claims, the narrow Power Play fundamentals exception, `[TL-EARLY]` confirmation debt and the five named early-entry tactics the practice layer defines, risk asymmetry and hard-stop claims, and quarantined non-executable material.

Precedence is scope, safety, and data integrity; Minervini eligibility and risk hard gates; verified explicit exceptions; tagged TraderLion practice-layer defaults; then current narrative context. TraderLion is integrated only where it fills a genuine execution gap without changing a Minervini gate. Conflicting tactics remain tagged and opt-in.

Pure evaluators are separated by decision concern: market regime and candidate scope, technical eligibility, setup and setup evidence, filed fundamentals, same-industry peers, and prospective or active-position risk. No weighted master score is allowed to let strength on one axis erase a hard failure on another.

The recommendation vocabulary is stateful and intentionally narrow. Qualification or `PROCEED` is not BUY-READY. Prospective outcomes are BUY-READY, WAIT, AVOID, or INCOMPLETE only after the relevant evidence converges; active-position outcomes are HOLD, SELL, or INCOMPLETE. Market and component operations retain their own descriptive states without pretending to make the final decision.

An active `HOLD` requires a current completed price and a clear completed-daily-low path from the stop's effective calendar date through the analysis session. Any historical breach produces `SELL` even if price later recovers; unavailable coverage produces `INCOMPLETE`. A raised or replaced stop is never projected backward before its supplied effective date, while an explicitly requested partial-session check remains a separate live-stop path.

## Data, identity, time, and cache

All analytical operations resolve one explicit point-in-time boundary through the New York market calendar. A default request uses the last completed US session. Explicit weekends and exchange holidays are rejected rather than silently shifted. Daily price evidence excludes an incomplete current bar, and provider requests use explicit end-exclusive boundaries.

Bar completion is decided at the provider boundary, never by each consumer. Yahoo can return a session with its price fields still blank; a row whose OHLCV values are not all finite is not a completed bar, `meta.as_of` is the last bar that survives that test rather than the requested boundary, and `meta.stale` marks the difference. A hole inside the history is typed unavailability instead of a silent drop, because a shortened window would quietly misreport every moving average. When price evidence stops before the requested session, the operations withhold the domain verdict rather than computing one from the earlier session and stamping it with this one; naming the earlier session with `--as-of` returns an aligned answer.

`meta.stale` means exactly one thing — this evidence did not reach the requested boundary — and it is also what stops a snapshot from being cached, since an unfinished bar will change. Temporal provenance that is normal rather than incomplete, such as reading a current-only page some hours after the close, is disclosed through `coverage` instead.

`ibd-rs-rating==0.5.0`, imported as `rs_rating`, is the sole authoritative first-party cross-sectional percentile source for this harness. The adapter calls its public APIs with an exact date, records package version and declared coverage, keeps `rs_raw` separate from `rs_rating`, and never reproduces the formula or calls the feed official proprietary IBD data.

Yahoo supplies price history and current classification through a narrow adapter. Current mutable sector and industry taxonomy cannot be projected into historical peer analysis. Nasdaq Trader's current security master supplies listing identity and eligibility scope but is likewise unavailable for historical reconstruction. SEC company facts and submissions are normalized only when `filed_at <= as_of`; period end alone is never sufficient, and requests are spaced under the published rate limit because SEC answers a burst by blocking the whole exit address.

Finviz publishes only a live page. It may stand in for the last completed session while no regular session is open, which is a question about the trading clock rather than the calendar date, and the envelope discloses how long after that session's close the page was read. Breadth built from it is context evidence, like the QQQ switch, not a measurement taken at the close.

Provider boundaries retry once, waiting between attempts, and then return typed unavailability carrying the underlying failure so a caller can tell a 403 from a certificate error without reproducing the call outside the CLI. That text is redacted before it leaves the boundary: query strings carry API keys and this harness's own SEC User-Agent carries the operator's email. Successful absence, withheld RS, stale coverage, malformed payloads, and transport failure retain distinct meanings. Every snapshot records source, retrieval time, effective as-of where supportable, version or coverage declarations, and a content hash.

Stdlib TLS is repaired on import when the interpreter has no usable CA bundle, because the python.org macOS builds ship without one and the RS client speaks stdlib `urllib` rather than `requests`. The repair sets `SSL_CERT_FILE` only when it is unset, and can never be the reason an import fails. `health` reports that bundle and the SEC User-Agent as local configuration without touching the network; `health --probe` additionally proves reachability, and unprobed health reports `reachability: not_checked` so readiness is never read as a claim about providers.

The provider cache lives at `.state/cache` by default and may be overridden by `MINERVINI_CACHE_DIR`. Keys include provider, operation, normalized parameters, and completed session. Writes are atomic JSON; corruption, schema mismatch, or expiry becomes a miss and rewrite. The cache supports JSON payloads, completed OHLCV frames, and stable security records without pickle. Research state is not part of this cache.

## Side effects and research state

Normal analytical capabilities do not mutate the research ledger. `watchlist.record`, `watchlist.annotate`, and `watchlist.export` are explicit user-authorized side effects and report what they changed in the envelope. Reads never create the database.

The default ledger is `.state/research-ledger.sqlite3`, overridable by `MINERVINI_LEDGER_PATH`. It stores stable instrument identity, as-of, output hash, verdict, conditions, invalidation, doctrine IDs, evidence quality, and notes. It is an auditable research memory, not an automatic portfolio manager.

`ticker.chart` is the other side-effecting analytical capability. It renders ignored weekly-first and daily PNG artifacts plus a manifest from the same completed-bar input used by the deterministic analysis. Visual judgment can resolve qualitative `needs_chart` evidence but cannot reverse a deterministic gate.

## Component inventory

| Component | Responsibility | Current state |
|---|---|---|
| `scripts/minervini/clock.py` | Completed-session, session-open, and explicit as-of resolution | Implemented and contract-tested. |
| `scripts/minervini/tls.py` | Stdlib CA-bundle repair for providers that bypass `requests` | Implemented; silent when the interpreter already has a bundle. |
| `.claude/hooks/provider-readiness.sh` | Session-start offline readiness notice | Implemented; silent unless the runtime cannot answer honestly. |
| `scripts/minervini/providers/` | Yahoo, RS, Nasdaq, SEC, and Finviz typed snapshots | Implemented with frozen provider fixtures and retry/PIT tests. |
| `scripts/minervini/cache.py` | Session-scoped atomic provider cache | Implemented and corruption/TTL/no-cache tested. |
| `scripts/minervini/technical.py`, `eligibility.py` | Trend Template evidence and eligibility routing | Implemented with standard and recent-IPO fixtures. |
| `scripts/minervini/setup_evidence.py`, `setup.py` | Deterministic observations plus explicit qualitative setup judgment | Implemented; absent chart judgment remains `needs_chart`. |
| `scripts/minervini/fundamentals.py` | Filed-as-of growth, integrity, leadership, and Power Play handling | Implemented with original/amendment cutoff fixtures. |
| `scripts/minervini/market_evidence.py`, `market.py` | Breadth, environmental context, group vectors, trade traction, and candidate scope | Implemented without a bullish weighted score. |
| `scripts/minervini/peer_collection.py`, `peers.py` | Stable-identity same-industry evidence | Implemented for current taxonomy with exact RS/date and completed-price checks. |
| `scripts/minervini/risk.py` | Final prospective and active-position reducers | Implemented with full completed stop-path, effective-date, recovered-breach, and missing-coverage tests. |
| `scripts/minervini/chart.py` | Auditable chart artifact generation | Implemented with input hash and manifest verification. |
| `scripts/minervini/ledger.py` | Explicit research-state persistence | Implemented with non-creating reads and export tests. |
| `scripts/minervini/runtime.py` | Replaceable provider dependencies and readiness probes | Extracted without changing runtime defaults. |
| `scripts/minervini/stop_audit.py` | Completed stop-path audit and component attestation | Shares session-label handling with price readers. |
| `scripts/minervini/numbers.py`, `dates.py`, `states.py` | Shared readings with distinct numeric, date, and state policies | Existing caller contracts preserved. |
| `scripts/minervini/doctrine.py` | Indexed claim access, runtime discovery, and doctrine validation | `doctrine.list` exposes computability, roles, and consumers. |
| `scripts/minervini/operations.py` | Provider/evaluator composition and envelope data | Implemented with cache and operation integration tests. |
| `scripts/minervini/contracts.py`, `capabilities.py`, `cli.py`, `schema_sync.py` | Public interface, help, metadata, schemas, and output envelope | Implemented and parity-tested. |

## Verification strategy

All v2 tests live under `tests/260817`. The suite is layered into doctrine, unit, contract, integration, frozen provider fixtures, behavioral E2E, and v1 baseline evidence. Public seams were fixed before implementation and developed RED to GREEN under the repository's TDD contract.

Required deterministic gates are: doctrine registry validation; all reducer unit tests; provider, cache, ledger, chart, and operation integration tests; exact envelope and schema parity; detailed offline help coverage; harness topology; bootstrap; compile; dependency health; and the harness-creator validator.

Behavioral acceptance uses independent Codex runs over market, sector/industry, ticker qualification, setup, Power Play, same-industry comparison, active stop, missing evidence, point-in-time refusal, scope boundary, and side-effect prompts. Critical assertions require three independent passes, with an adversarial final synthesis checking for false BUY-READY, fabricated data, hidden portfolio sizing, and rail-driven overcalling.

The final v2 suite contains 167 passing tests. The first behavioral synthesis blocked release at 182/186 critical assertions because three active-position runs used only the latest close and one hypothetical recent-IPO run imported an unrelated fixture. Those failures were preserved in `tests/260817/e2e/round-1-findings.json`, fixed through public-seam TDD and closed-world skill guidance, and rerun by six fresh Codex agents. The final independent sol synthesis approved 186/186 critical and 86/90 noncritical assertions across 30 reports with zero release blockers.

Live smoke testing is limited to safe read-only provider and CLI paths. It verifies current integration but cannot replace frozen point-in-time contract tests. Network absence or source unavailability is reported honestly and is not treated as a deterministic failure of the doctrine engine.

The 2026-08-17 live report at `tests/260817/live/report.json` records healthy local dependencies, completed-session Yahoo prices, current market and security-master composition, representative large-cap, recent-IPO, ADR and excluded-instrument paths, active stop history, and honest Finviz/RS unavailability. It also records the candidate-response density regression and its reduction from a universe-wide exclusion dump to a 2,439-byte bounded summary.

The v1 diagnostic baseline is `tests/260817/baselines/v1/manifest.json`. The final v1 commit is preserved through the `harness-v1-final` annotated tag and GitHub release so obsolete runtime files can be deleted from v2 without losing recoverability.

## Design rationale

The v1 harness encoded substantial knowledge but spread the same facts among the root document, references, module documentation, a fixed agent, a workflow, and command implementations. That made drift likely and spent context before the analyst knew what evidence mattered. V2 keeps principles always available, task judgment in two skills, and exact mechanical detail behind a discoverable executable interface.

There is no trade-review skill in v2 because completed-trade grading is not part of the requested market, industry, sector, and live ticker analyst. There is no permanent scout agent because fan-out is an execution choice that should scale to the candidate set, provider health, and unresolved questions. The single `SessionStart` hook is deliberately the only one: deterministic contracts are stronger enforced by code and tests, and the one thing code inside the runtime cannot do is tell a starting session that the runtime itself is degraded. That gap is exactly what let the v2 rebuild run for a day without RS.

Legacy calculation code is not imported by v2. The old modules mutate import paths, install a process-global Yahoo proxy, mix network and stdout side effects with calculations, and frequently lack explicit historical cutoffs. Reusing isolated formulas would preserve those hidden couplings, so the v2 implementation promotes only independently tested concepts into package-clean modules.

The two host harnesses share files through symbolic links because Claude and Codex should receive identical scope, principles, and routed skills. A second generated copy would introduce drift without adding capability.

Obsolete v1 runtime and design documents are removed after the v1 tag and release exist. Git history is the archive; leaving live-looking duplicates in the worktree would make discovery ambiguous and invite accidental reuse.

## Maintenance protocol

When adding or changing a capability, first define or update the public test seam under the current dated suite directory in `tests/`, then change the registry, CLI parser/help, operation, schema projection, and contract tests together. A flag exists only when the implementation consumes it; decorative compatibility flags are prohibited.

When changing doctrine, edit the normalized registry and its doctrine tests before changing a reducer. Preserve provenance and precedence in the registry. Add text to `CLAUDE.md` only if it is an always-on invariant; add text to a skill only if it changes task-specific judgment; put syntax and defaults in the interface.

When adding a provider, declare present and historical support separately, use an injected or frozen raw fixture, retain source metadata and content hash, enforce the common as-of boundary, retry once, and represent unsupported reconstruction as typed unavailability. Never silently substitute one provider or formula for another.

When adding a side effect, mark it in capability metadata, disclose it in leaf help and the envelope, require explicit user intent, place generated state in ignored paths by default, and add a non-side-effect regression test for adjacent read operations.

Before accepting a harness change, run the focused RED/GREEN test, the complete `tests/` suite, help/schema parity, bootstrap and compile checks, and the harness validator. Update this spec in the same change whenever topology, information ownership, permissions, skills, or validation requirements change.

## Change history

Past entries live in [the change history archive](../docs/history/harness-spec-change-history.md). Add new entries here and move them to the archive at each release.
