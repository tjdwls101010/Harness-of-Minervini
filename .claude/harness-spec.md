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
- One shared harness: Claude Code uses `.claude/skills`; Codex reaches the same files through `.agents/skills -> ../.claude/skills`. `AGENTS.md -> CLAUDE.md` shares the constitution. No duplicated Codex copy exists.

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

The always-loaded root is `CLAUDE.md`; `AGENTS.md` is its symbolic link. The only routed runtime skills are `.claude/skills/market-scan/SKILL.md` and `.claude/skills/ticker-analysis/SKILL.md`; `.agents/skills` is a symbolic link to that directory.

There are no project agents, rules, workflows, hooks, or duplicate `.codex/skills`. Fixed scout agents and a `/screen` workflow were retired because concurrency and depth should follow the actual candidate set and unresolved evidence rather than a hard-coded fan-out rail. Cross-cutting JSON, schema, clock, retry, and side-effect guarantees are enforced by code and tests, not by advisory hooks.

`.claude/settings.json` permits only the canonical pipeline and bootstrap command families and denies edits under `/.tmp/**`. Normal analysis remains read-only except for the ignored cache; chart artifacts and research-ledger mutations require their explicitly side-effecting capabilities.

## Interface architecture

The canonical entry point is `scripts/.venv/bin/python scripts/pipeline`. `scripts/pipeline/__main__.py` delegates to `scripts.minervini.cli`; the public analyst interface never calls legacy `scripts/modules` commands.

The registry exposes 18 composable capabilities: discovery and self-description (`capabilities`, `describe`, `health`, `clock`, `doctrine.show`), market work (`market.snapshot`, `market.candidates`), ticker work (`ticker.qualify`, `ticker.setup`, `ticker.fundamentals`, `ticker.peers`, `ticker.chart`, `ticker.risk`), and explicit research state (`watchlist.show`, `watchlist.history`, `watchlist.record`, `watchlist.annotate`, `watchlist.export`). The count and names are contractual and tested.

Every non-help invocation emits exactly one v2 JSON envelope with `schema_version`, `operation`, `request`, `as_of`, `status`, `data`, `signals`, `missing`, `sources`, `doctrine_ids`, `next_capabilities`, and `side_effects`. Status is one of `ok`, `partial`, `unavailable`, or `needs_input`; it describes contract completeness, not an investment recommendation.

`scripts/minervini/capabilities.py` is the metadata source for listing and description. `scripts/minervini/schema_sync.py` projects that registry into the 18 immutable-ID schemas under `schemas/v2/`. `scripts/minervini/cli.py` builds detailed offline help from the same meanings. Tests reject metadata, help, schema, and envelope drift.

Help is deliberately detailed at the point of use. Root and group help orient the caller; every leaf help explains purpose, required and optional inputs, defaults, as-of behavior, provider or historical limits, status meanings, side effects, and examples. Markdown teaches how to discover help but does not restate all flags.

`--format compact|full` changes detail only and cannot change verdicts, signals, missing-evidence meaning, doctrine IDs, or source truth. `--no-cache` bypasses cache reads and writes and exists for fresh diagnostics, not ordinary analysis.

## Doctrine and decision architecture

The normalized doctrine registry is the executable source of hard gates and precedence. It currently contains the standard Stage 2 and eight-of-eight Trend Template route, the bounded recent-IPO Primary Base route, VCP supply and setup claims, the narrow Power Play fundamentals exception, `[TL-EARLY]` confirmation debt, risk asymmetry and hard-stop claims, and quarantined non-executable material.

Precedence is scope, safety, and data integrity; Minervini eligibility and risk hard gates; verified explicit exceptions; tagged TraderLion practice-layer defaults; then current narrative context. TraderLion is integrated only where it fills a genuine execution gap without changing a Minervini gate. Conflicting tactics remain tagged and opt-in.

Pure evaluators are separated by decision concern: market regime and candidate scope, technical eligibility, setup and setup evidence, filed fundamentals, same-industry peers, and prospective or active-position risk. No weighted master score is allowed to let strength on one axis erase a hard failure on another.

The recommendation vocabulary is stateful and intentionally narrow. Qualification or `PROCEED` is not BUY-READY. Prospective outcomes are BUY-READY, WAIT, AVOID, or INCOMPLETE only after the relevant evidence converges; active-position outcomes are HOLD, SELL, or INCOMPLETE. Market and component operations retain their own descriptive states without pretending to make the final decision.

## Data, identity, time, and cache

All analytical operations resolve one explicit point-in-time boundary through the New York market calendar. A default request uses the last completed US session. Explicit weekends and exchange holidays are rejected rather than silently shifted. Daily price evidence excludes an incomplete current bar, and provider requests use explicit end-exclusive boundaries.

`ibd-rs-rating==0.5.0`, imported as `rs_rating`, is the sole authoritative first-party cross-sectional percentile source for this harness. The adapter calls its public APIs with an exact date, records package version and declared coverage, keeps `rs_raw` separate from `rs_rating`, and never reproduces the formula or calls the feed official proprietary IBD data.

Yahoo supplies price history and current classification through a narrow adapter. Current mutable sector and industry taxonomy cannot be projected into historical peer analysis. Nasdaq Trader's current security master supplies listing identity and eligibility scope but is likewise unavailable for historical reconstruction. SEC company facts and submissions are normalized only when `filed_at <= as_of`; period end alone is never sufficient. Finviz breadth is a captured current snapshot, not a historical data source.

Provider boundaries retry once and then return typed unavailability. Successful absence, withheld RS, stale coverage, malformed payloads, and transport failure retain distinct meanings. Every snapshot records source, retrieval time, effective as-of where supportable, version or coverage declarations, and a content hash.

The provider cache lives at `.state/cache` by default and may be overridden by `MINERVINI_CACHE_DIR`. Keys include provider, operation, normalized parameters, and completed session. Writes are atomic JSON; corruption, schema mismatch, or expiry becomes a miss and rewrite. The cache supports JSON payloads, completed OHLCV frames, and stable security records without pickle. Research state is not part of this cache.

## Side effects and research state

Normal analytical capabilities do not mutate the research ledger. `watchlist.record`, `watchlist.annotate`, and `watchlist.export` are explicit user-authorized side effects and report what they changed in the envelope. Reads never create the database.

The default ledger is `.state/research-ledger.sqlite3`, overridable by `MINERVINI_LEDGER_PATH`. It stores stable instrument identity, as-of, output hash, verdict, conditions, invalidation, doctrine IDs, evidence quality, and notes. It is an auditable research memory, not an automatic portfolio manager.

`ticker.chart` is the other side-effecting analytical capability. It renders ignored weekly-first and daily PNG artifacts plus a manifest from the same completed-bar input used by the deterministic analysis. Visual judgment can resolve qualitative `needs_chart` evidence but cannot reverse a deterministic gate.

## Component inventory

| Component | Responsibility | Current state |
|---|---|---|
| `scripts/minervini/clock.py` | Completed-session and explicit as-of resolution | Implemented and contract-tested. |
| `scripts/minervini/providers/` | Yahoo, RS, Nasdaq, SEC, and Finviz typed snapshots | Implemented with frozen provider fixtures and retry/PIT tests. |
| `scripts/minervini/cache.py` | Session-scoped atomic provider cache | Implemented and corruption/TTL/no-cache tested. |
| `scripts/minervini/technical.py`, `eligibility.py` | Trend Template evidence and eligibility routing | Implemented with standard and recent-IPO fixtures. |
| `scripts/minervini/setup_evidence.py`, `setup.py` | Deterministic observations plus explicit qualitative setup judgment | Implemented; absent chart judgment remains `needs_chart`. |
| `scripts/minervini/fundamentals.py` | Filed-as-of growth, integrity, leadership, and Power Play handling | Implemented with original/amendment cutoff fixtures. |
| `scripts/minervini/market_evidence.py`, `market.py` | Breadth, environmental context, group vectors, trade traction, and candidate scope | Implemented without a bullish weighted score. |
| `scripts/minervini/peer_collection.py`, `peers.py` | Stable-identity same-industry evidence | Implemented for current taxonomy with exact RS/date and completed-price checks. |
| `scripts/minervini/risk.py` | Final prospective and active-position reducers | Implemented with hard-stop and current-price completeness tests. |
| `scripts/minervini/chart.py` | Auditable chart artifact generation | Implemented with input hash and manifest verification. |
| `scripts/minervini/ledger.py` | Explicit research-state persistence | Implemented with non-creating reads and export tests. |
| `scripts/minervini/operations.py` | Provider/evaluator composition and envelope data | Implemented with cache and operation integration tests. |
| `scripts/minervini/contracts.py`, `capabilities.py`, `cli.py`, `schema_sync.py` | Public interface, help, metadata, schemas, and output envelope | Implemented and parity-tested. |

## Verification strategy

All v2 tests live under `tests/260817`. The suite is layered into doctrine, unit, contract, integration, frozen provider fixtures, behavioral E2E, and v1 baseline evidence. Public seams were fixed before implementation and developed RED to GREEN under the repository's TDD contract.

Required deterministic gates are: doctrine registry validation; all reducer unit tests; provider, cache, ledger, chart, and operation integration tests; exact envelope and schema parity; detailed offline help coverage; harness topology; bootstrap; compile; dependency health; and the harness-creator validator.

Behavioral acceptance uses independent Codex runs over market, sector/industry, ticker qualification, setup, Power Play, same-industry comparison, active stop, missing evidence, point-in-time refusal, scope boundary, and side-effect prompts. Critical assertions require three independent passes, with an adversarial final synthesis checking for false BUY-READY, fabricated data, hidden portfolio sizing, and rail-driven overcalling.

Live smoke testing is limited to safe read-only provider and CLI paths. It verifies current integration but cannot replace frozen point-in-time contract tests. Network absence or source unavailability is reported honestly and is not treated as a deterministic failure of the doctrine engine.

The v1 diagnostic baseline is `tests/260817/baselines/v1/manifest.json`. The final v1 commit is preserved through the `harness-v1-final` annotated tag and GitHub release so obsolete runtime files can be deleted from v2 without losing recoverability.

## Design rationale

The v1 harness encoded substantial knowledge but spread the same facts among the root document, references, module documentation, a fixed agent, a workflow, and command implementations. That made drift likely and spent context before the analyst knew what evidence mattered. V2 keeps principles always available, task judgment in two skills, and exact mechanical detail behind a discoverable executable interface.

There is no trade-review skill in v2 because completed-trade grading is not part of the requested market, industry, sector, and live ticker analyst. There is no permanent scout agent because fan-out is an execution choice that should scale to the candidate set, provider health, and unresolved questions. There is no hook because no universal session lifecycle action was justified; deterministic contracts are stronger when enforced directly by code and tests.

Legacy calculation code is not imported by v2. The old modules mutate import paths, install a process-global Yahoo proxy, mix network and stdout side effects with calculations, and frequently lack explicit historical cutoffs. Reusing isolated formulas would preserve those hidden couplings, so the v2 implementation promotes only independently tested concepts into package-clean modules.

The two host harnesses share files through symbolic links because Claude and Codex should receive identical scope, principles, and routed skills. A second generated copy would introduce drift without adding capability.

Obsolete v1 runtime and design documents are removed after the v1 tag and release exist. Git history is the archive; leaving live-looking duplicates in the worktree would make discovery ambiguous and invite accidental reuse.

## Maintenance protocol

When adding or changing a capability, first define or update the public test seam under `tests/260817`, then change the registry, CLI parser/help, operation, schema projection, and contract tests together. A flag exists only when the implementation consumes it; decorative compatibility flags are prohibited.

When changing doctrine, edit the normalized registry and its doctrine tests before changing a reducer. Preserve provenance and precedence in the registry. Add text to `CLAUDE.md` only if it is an always-on invariant; add text to a skill only if it changes task-specific judgment; put syntax and defaults in the interface.

When adding a provider, declare present and historical support separately, use an injected or frozen raw fixture, retain source metadata and content hash, enforce the common as-of boundary, retry once, and represent unsupported reconstruction as typed unavailability. Never silently substitute one provider or formula for another.

When adding a side effect, mark it in capability metadata, disclose it in leaf help and the envelope, require explicit user intent, place generated state in ignored paths by default, and add a non-side-effect regression test for adjacent read operations.

Before accepting a harness change, run the focused RED/GREEN test, the complete `tests/260817` suite, help/schema parity, bootstrap and compile checks, and the harness validator. Update this spec in the same change whenever topology, information ownership, permissions, skills, or validation requirements change.

## Change history

- 2026-08-17: Rebuilt the harness as v2 around principle over rail, interface over document, dense progressive disclosure, typed point-in-time providers, composable deterministic reducers, explicit research state, two shared host skills, and detailed just-in-time CLI help. Retired v1 agents, rules, workflow, reference libraries, trade-review route, duplicate Codex skill link, and legacy runtime substrate after preserving the v1 baseline for release.
