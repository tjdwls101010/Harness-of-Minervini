---
paths:
  - "scripts/**"
---

# Deterministic module contract

This is developer-facing maintenance guidance for `scripts/**`, not analyst doctrine. Preserve one public contract because skills, agents, and workflows compose these tools from structured output without a human available to repair an ambiguous response.

## CLI and output

- Use `argparse` for every public CLI. Expose each analysis operation as an explicit subcommand instead of an implicit mode; `market_clock.py` remains the intentional single-operation utility because a synthetic subcommand would add no choice.
- Keep the deliberate absence of an “analyze everything” command. Parameterized modules preserve the evidence funnel and let each deeper call earn its cost.
- A normal invocation writes exactly one JSON document to stdout through `utils.output_json`; never mix explanatory prose or debug output into stdout because downstream consumers parse the whole stream.
- Route parser, validation, and runtime failures through `utils.JsonArgumentParser` or `utils.error_json` so the only public failure shape is `{"error": "..."}` with exit code 1. A missing datum inside an otherwise useful composite result is section-level `unavailable`, not a whole-command crash.
- Include a top-level `doctrine` field in each successful analysis result. The field must explain how to interpret the measurement and its limits so a numeric detector cannot silently become a trading verdict.
- Treat top-level and subcommand `--help` output as the live CLI specification. Document every positional argument and flag, including units, defaults, allowed values, provenance, and whether a threshold is flex or locked.
- Parser construction and every `--help` path must be completely offline: do not fetch through yfinance, scrape Finviz, construct a live RS request, or write cache data before parsing and dispatch. Help is used by bootstrap, tests, and maintainers precisely when network access may be unavailable.
- Add `--no-cache` to every public module or subcommand, including utilities that make no cached call, so callers can use one predictable diagnostic contract.

## Thresholds and provenance

- Expose a contextual threshold as a flex-tier flag only when changing it preserves the method. Its default must reproduce canonical behavior, because running without flags is the stable contract used by skills and tests.
- Encode a methodology boundary as a descriptive module-level locked constant, not a freely adjustable default. Put the source tag and rationale beside the constant; when a related flag is useful, validate it so the caller may tighten the rule but cannot weaken the locked floor.
- Tag threshold comments and emitted doctrine with `[M]`, `[TL]`, `[TL-Kell]`, `[MM-Ryan]`, `[MM-Zanger]`, or `[MM-RitchieII]` as applicable. Only `[M]` is canonical SEPA doctrine; TraderLion and other Momentum Masters values remain explicitly attributed practice or speaker context so they cannot masquerade as Minervini gates.
- Label any harness-authored quantifier as an invented, non-canonical heuristic and explain what qualitative evidence it approximates. An honest approximation is inspectable; an unlabelled number becomes false doctrine.

## Live-source cache

- Route every eligible live read through the shared read-through layer for all three sources: yfinance through the cached ticker proxy, the Finviz homepage scrape through `utils.cached_call` with source `finviz`, and `ibd-rs-rating`/Supabase through `rs_ranking.call_backend` with source `ibd-rs-rating`. Never instantiate `RS` elsewhere, because a direct package path silently bypasses the shared snapshot.
- Preserve the cache identity `(source, symbol, function, params-hash, last-completed-US-session)` and the user-scoped root `${MINERVINI_CACHE_DIR:-~/.cache/minervini-harness}`. The completed New York session, rather than the local calendar day, keeps a KST user’s repeated analysis on one coherent market snapshot.
- During the regular session, price endpoints must bypass the cache or use a TTL of at most 15 minutes; non-price data keeps the completed-session lifetime. `volume_analysis.py runrate` is deliberately cache-exempt because stale cumulative volume would corrupt its purpose.
- `--no-cache` must disable both reads and writes for every source for the rest of the process; use the monotonic `utils.configure_cache` state so a later helper cannot accidentally re-enable caching.
- Do not cache failed fetches. A cache read or write failure may be reported in cache metadata, but it must not hide a usable live value; repeated analysis needs resilience as well as snapshot consistency.

## Contract verification

- When a module contract changes, cover its success JSON, `doctrine`, JSON error/exit-1 behavior, top-level and subcommand help with network blocked, cache hit, and `--no-cache` bypass as applicable. These tests protect the interfaces consumed by the harness rather than incidental market values.
