# Contributing & Extending

A practical guide to changing this harness without breaking its design spine — the ground rules, the module contract, the dev loop, the maintenance model, and where to start.

This project has a deliberate, opinionated architecture, so contributions land cleanly only when they work *with* it. Read this page before you open a pull request, then follow [`CONTRIBUTING.md`](../../CONTRIBUTING.md) for the PR mechanics. For the shape of what you are extending, see [the architecture](Architecture.md) and [the module substrate](The-Module-Substrate.md).

> This is developer documentation for a project that produces market *analysis*, not financial advice. Nothing here or in the tool output is a recommendation to buy or sell any security — see the [FAQ & Disclaimer](FAQ-and-Disclaimer.md).

## The five ground rules

These come straight from [`CONTRIBUTING.md`](../../CONTRIBUTING.md) and govern every change to the analyst-facing layers.

1. **Analysis quality is the sole design criterion.** The harness exists to make Claude apply the Minervini methodology excellently. Never trade analysis quality for convenience, brevity, or "maintainability" in the analyst-facing layers. (This is the spec's *prime directive*, and it is binding.)
2. **Numbers are deterministic; judgment is the model's.** Any precise market value — price, earnings, moving average, RS, date — must come from a `scripts/` module. Never add a path that fills a market number from memory or the web. On failure a module reports `unavailable`; it does not guess.
3. **Every verdict ships its basis.** If you add or change a flag, score, grade, or label, expose the measurements it rests on plus a `doctrine`/`threshold` field that says how to read it and where it is only a heuristic. **Do not introduce a composite 0–100 "master score"** — the design deliberately refuses one.
4. **Respect the doctrine hierarchy.** Minervini SEPA gates are immutable. TraderLion and other speaker material is a subordinate practice layer and must carry a provenance tag. A practice-layer number may never be presented as a hard gate. Where the two conflict, Minervini wins. See [The Minervini Method](The-Minervini-Method.md) for the two-tier doctrine.
5. **Never commit book text.** The source books are copyrighted and live only in the git-ignored `.tmp/` directory. Committed references must *paraphrase* principles. The repository is public.

### Provenance tags

Every borrowed threshold and every emitted `doctrine` string carries its origin. Use exactly these tags:

| Tag | Meaning |
|-----|---------|
| `[M]` | Canonical Minervini SEPA doctrine — the only tier that is a hard gate |
| `[TL]` | TraderLion practice layer — tunable default, subordinate on conflict |
| `[TL-Kell]` | The TraderLion 50-SMA position-trail exception |
| `[MM-Ryan]` / `[MM-Zanger]` / `[MM-RitchieII]` | *Momentum Masters* speaker context, attributed so it never masquerades as an SEPA rule |

Harness-authored quantifiers that exist in no source get labelled as invented, non-canonical heuristics with a note on what qualitative evidence they approximate — an honest approximation is inspectable; an unlabelled number becomes false doctrine.

## Adding or changing a module

Deterministic code under `scripts/**` follows one public contract, defined in [`.claude/rules/module-contract.md`](../../.claude/rules/module-contract.md) (a paths-gated rule that loads only when you touch those files). Skills, agents, and the workflow compose these tools from structured output with no human present to repair an ambiguous response, so the contract is strict. When you add or change a module, honor all of it:

- **Subcommands, not modes.** Every analysis operation is an explicit `argparse` subcommand. There is deliberately no "analyze everything" command — parameterized calls preserve the evidence funnel. (`market_clock.py` is the one intentional single-operation utility; a synthetic subcommand there would add no choice.)
- **One JSON document to stdout** via the shared `utils.output_json` helper. Never mix prose or debug output into stdout — downstream consumers parse the whole stream.
- **One public failure shape.** Route parser, validation, and runtime errors through `utils.JsonArgumentParser` / `utils.error_json` so failures emit `{"error": "..."}` and exit `1`. A missing datum *inside* an otherwise useful composite result is section-level `unavailable`, not a whole-command crash.
- **A top-level `doctrine` field** on every successful result, explaining how to interpret the measurement and its limits, so a numeric detector cannot silently become a trading verdict.
- **Flex vs. locked constants.** Expose a contextual threshold as a flex-tier flag *only* when changing it preserves the method, and its default must reproduce canonical behavior. Encode a methodology boundary as a named, module-level *locked* constant with its source tag and rationale beside it — never a bare inline literal. Where a related flag is useful, validate it so a caller may *tighten* the rule but cannot weaken the locked floor.
- **`--help` is the live spec, and it must run fully offline.** Document every positional and flag — units, defaults, allowed values, provenance, and whether a threshold is flex or locked. Parser construction and every `--help` path must make no network call and write no cache, because bootstrap, tests, and maintainers hit help precisely when the network may be down.
- **Lower-bound guards.** Add a guard to any new numeric flag so a nonsensical value (e.g. a negative window) errors cleanly instead of returning a mislabeled result. This is a real, tested concern — `volume_analysis analyze` grew a `>= 1` guard after a negative window silently returned a mislabeled `tail(-n)` slice.
- **Cache read-through.** Route every eligible live read through the shared layer for all three sources: yfinance via the cached ticker proxy, the Finviz scrape via `utils.cached_call` with source `finviz`, and `ibd-rs-rating`/Neon via `rs_ranking.call_backend` with source `ibd-rs-rating`. **Never instantiate `RS` elsewhere** — a direct package path bypasses the shared snapshot. Give every module `--no-cache` (it must disable both reads and writes for the rest of the process), and never cache a failed fetch.

If you change what a module emits, treat it as a contract change (below) and update the tests that pin it.

## The development workflow

One-time setup, then the deterministic suite. Use the canonical root-relative invocation — never `cd scripts`:

```bash
# One-time setup: create the venv and install pinned deps
bash scripts/bootstrap.sh

# Contract tests are offline and deterministic
for t in scripts/tests/test_*.py; do scripts/.venv/bin/python "$t"; done

# Smoke tests hit the live APIs (schema-shape assertions, not value assertions)
scripts/.venv/bin/python scripts/tests/smoke.py
```

The offline `test_*.py` files under `scripts/tests/` pin the contract per area — for example `test_contract_stage_vcp.py`, `test_module_extensions_contracts.py`, `test_rs_pipeline_contracts.py`, `test_sell_chart_contracts.py`, `test_cache_clock.py`, `test_contract_base_tight.py`, and `test_contract_earnings_entry.py`. They assert JSON structure, `doctrine` presence, provenance, JSON-error/exit-1 behavior, locked-gate immovability, and cache state — the interfaces the harness consumes, not incidental market values. `smoke.py` checks live schema shape and degrades gracefully when a fragile source (the Finviz scrape, `ibd-rs-rating`) is flaky.

**When you change a module contract**, add or update the tests that cover its success JSON, its `doctrine` field, its JSON-error/exit-1 behavior, its top-level and subcommand `--help` *with the network blocked*, a cache hit, and `--no-cache` bypass — whichever apply. If your change touches the `/screen` fan-out, note that Claude Code **2.1.154+** is required for that workflow (Python **3.10+** for the substrate).

## Proposing changes

Follow the process in [`CONTRIBUTING.md`](../../CONTRIBUTING.md):

1. **Open an issue first** for anything beyond a small fix, so the design implications can be discussed before you invest effort.
2. **Branch from the default branch;** keep commits coherent and well-described.
3. **Make the deterministic tests pass,** and for methodology changes, cite the source and provenance tag in your PR description.
4. **Doctrine changes explain *why*.** A rule without its reasoning is a brittle rail; the harness deliberately prefers principles a capable model can re-derive over enumerated numbers it must obey blindly. See [Design Principles](Design-Principles.md) for why.

Contributions are licensed under the project's [MIT License](../../LICENSE).

## The maintenance model

This harness was authored with the [`harness-creator`](../../CLAUDE.md) methodology, and its **binding design record lives in [`.claude/harness-spec.md`](../../.claude/harness-spec.md)**. That file — not this repo's analyst-facing layers — is where maintenance rationale, component status, and authoring policy belong. Keep it in sync when you change a component.

The split is intentional and load-bearing: during *analysis*, methodology content is live instruction (persona, doctrine); during *maintenance*, it is data (files being edited). So maintenance instructions, status synchronization, and authoring policy stay in `harness-spec.md` or in paths-gated rules, where their analysis-time token cost is zero. `CLAUDE.md` carries only facts and behavior the analyst actually needs. Do not migrate developer notes into the constitution or the skills — that would tax every analysis session for no analytical gain.

## Good first extensions

The spec records a v2 backlog under **"Deferred to v2"** — items judged valuable but not needed for the core analyst loop. Each is a self-contained extension idea:

- **Edge-study / model-book generation workflows** — a study pipeline with an 11-field trade schema and a 6-step model-book procedure (TraderLion cluster I). Useful for systematic post-analysis; out of the way of the core buy/sell loop.
- **TraderLion Ch.12 chart-study recovery** — the source chart images were lost from the corpus and the surviving text is unreliable AI alt-text; recovery means re-extracting from the original PDF or regenerating from a ticker+year register.
- **Intraday tactics module** — ORB, gapper Day 1/2/3, VWAP. Explicitly out of SEPA's daily/weekly scope in v1; a clean opt-in candidate if added with provenance and scope guards.
- **TraderLion secondary universe classes** — non-earnings momentum and swing-tagged squeeze names. Default-disallowed in v1; would need the two-tier constitution to admit them without silently mixing in conflicting doctrine.

Any of these should arrive tagged, tested, and reconciled against the doctrine hierarchy. When in doubt, open an issue and check the change against the five ground rules first.

---
[← Wiki Home](README.md) · [Installation](Installation.md) · [Quickstart](Quickstart.md) · [Architecture](Architecture.md) · [The Minervini Method](The-Minervini-Method.md) · [Skills & Usage](Skills-and-Usage.md) · [Module Substrate](The-Module-Substrate.md) · [Design Principles](Design-Principles.md) · [Contributing](Contributing-and-Extending.md) · [FAQ](FAQ-and-Disclaimer.md)
