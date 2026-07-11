# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
