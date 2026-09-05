# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Composable v2 interface.** 22 capabilities expose market, ticker, doctrine, clock, health, chart, and explicit watchlist operations through one versioned JSON envelope, machine-readable `describe`, immutable-ID schemas, and detailed offline leaf help.
- **Point-in-time provider layer.** Completed Yahoo bars, exact-date `ibd-rs-rating==0.5.0`, filed-as-of SEC facts, current Nasdaq security identity, current Yahoo classification, and captured Finviz breadth now retain typed availability, coverage, retrieval time, version, and content hashes.
- **Doctrine-aware decision engines.** Standard Stage 2 and eight-of-eight qualification, bounded recent-IPO Primary Base eligibility, setup and VCP supply evidence, filed fundamentals and the narrow Power Play exception, current same-industry peers, market vectors, and prospective or active-position risk remain separate auditable axes.
- **Explicit local research state.** A non-creating SQLite ledger records or annotates research only through explicit watchlist write capabilities; the provider cache and chart artifacts use ignored paths and disclose their side effects.
- **V2 verification suite.** Public-seam tests are grouped by module under `tests/{unit,integration,contracts,doctrine}/`; shared fixtures, behavioral E2E artifacts, and baseline evidence live under `tests/{fixtures,e2e,baselines}/`.

### Changed

- **Principle over rail.** The always-loaded constitution now carries compact decision invariants while two intent skills adaptively select only the evidence the question needs; no fixed workflow, scout, batch size, or monolithic score controls the analysis.
- **Interface over document.** Command syntax, defaults, limits, statuses, side effects, and examples moved into the executable registry and detailed CLI help. Human documentation teaches discovery instead of duplicating a flag catalog.
- **Claude and Codex share literal files.** `AGENTS.md -> CLAUDE.md` and `.codex/skills -> ../.claude/skills` remove host-specific prompt copies and drift.
- **Point-in-time and missing-evidence semantics are release gates.** Incomplete bars, post-cutoff filings, mutable current taxonomy, stale or withheld RS, transport failures, and successful no-data responses cannot be silently promoted to usable historical evidence.
- **Active HOLD audits the whole stop window.** A recovered latest price cannot hide an earlier completed-daily-low breach; changed stops carry an effective date, incomplete path coverage stays `INCOMPLETE`, and leaf help explains the distinction from an explicit live check.
- **Candidate transport stays dense.** Discovery pagination returns complete exclusion counts by reason with at most `min(limit, 20)` representative records instead of dumping thousands of excluded instruments into every response.

### Removed

- The v1 module tree, pipeline implementation, test suite, wiki, build plans, fixed agent and workflow, path rule, topic reference library, completed-trade skill, and duplicate Codex layout. V1 remains recoverable from the `harness-v1-final` tag and release; no compatibility shim or `legacy/` copy remains in v2.

## [1.0.0] — 2026-07-11

First public release. A complete, validated Claude Code harness that makes Claude behave as a disciplined Minervini SEPA momentum-stock analyst for US equities.

### Added

- **Analyst constitution (`CLAUDE.md`).** The always-loaded persona, risk spine, funnel order, probability-convergence doctrine, anti-default corrections (lockout rally, anti-ATR, cheap-trap and broken-leader bans, price-leads-earnings), two-tier doctrine with MA-vocabulary role separation, scope guards, and the data doctrine.
- **Three intent-split skills.** `market-scan` (regime, breadth, sector/industry strength, screening, leadership, watchlists), `ticker-analysis` (single- or few-ticker buy / entry / sell / hold / re-entry / earnings / chart, including head-to-head comparisons), and `trade-review` (grading the user's own completed trades), each with on-demand topic references.
- **Read-only `ticker-scout` agent** for screening fan-out and the deterministic **`/screen` workflow** (regime → qualify → synthesize watchlist).
- **Deterministic module substrate (`scripts/`).** 16 parameterized CLI modules plus a two-command pipeline (`qualify`, `discover`), each emitting one JSON document with its verdict, full per-criterion basis, interpretation `doctrine`, and provenance tags. Covers the Trend Template hard gate, Stage analysis, VCP / base / tight-close / volume detectors, earnings-acceleration and Code 33, relative strength, market breadth and the QQQ information switch, dated sell signals (key reversal, extension, MA-trail, failure cascade), a chart renderer, and an earnings-calendar proximity check.
- **Transparent same-session cache** keyed to the last completed US trading session, so iterative re-analysis is fast, rate-limit-safe, and reproducible within a market day; price data bypasses the cache while the market is open.
- **Portable bootstrap** (`scripts/bootstrap.sh`, no committed virtualenv), a paths-gated module-contract rule, and a narrow permission allowlist plus a project-root-anchored deny rule protecting non-runtime source material.
- **Documentation:** README, project Wiki (`docs/wiki/`), LICENSE (MIT), CONTRIBUTING, and CODE_OF_CONDUCT.

### Design principles established

- **Numbers are deterministic; judgment is the model's.** Precise market values come only from the modules; the model never fabricates a number and declares evidence *unavailable* on a data outage.
- **Every gate ships its full basis.** Verdicts carry the per-criterion evidence (measured value vs. required threshold) rather than an opaque aggregate; detectors self-demote author-weighted labels; there is deliberately no 0–100 master score.
- **Doctrine is adjudicated, not averaged.** Minervini SEPA is the immutable constitution; TraderLion is a tagged, subordinate practice layer with 26 documented conflicts resolved Minervini-first.

### Hardened by an independent audit

Before release, the implementation was put through an independent adversarial audit (18 review lenses across spec, knowledge fidelity, code contract, and output-schema design, plus six end-to-end behavioral scenarios). The audit confirmed zero critical defects and drove a round of improvements: the hard-gate verdict now embeds its full per-criterion basis; a tunable volume window is labeled honestly and validated; the screening workflow merges user tickers mechanically and never drops them silently; routing now covers multi-ticker comparisons and re-affirms US-only scope; several map-faithful sell and fundamentals signals were added; and a worked-example case file was retired in favor of inlined calibration anchors. Verification: 72 contract tests and a live schema-shape smoke suite pass, and all six behavioral scenarios pass with cited transcript evidence.

[1.0.0]: https://github.com/tjdwls101010/Harness-of-Minervini/releases/tag/v1.0.0
