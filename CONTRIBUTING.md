# Contributing to Harness of Minervini

Thank you for your interest in improving the harness. This project has a strong, deliberate design spine, so contributions are most useful when they work *with* it. Please read this guide before opening a pull request.

## Ground rules that keep the harness coherent

1. **Analysis quality is the sole design criterion.** The harness exists to make Claude apply the Minervini methodology excellently. Never trade analysis quality for convenience, brevity, or "maintainability" in the analyst-facing layers.

2. **Numbers are deterministic; judgment is the model's.** Any precise market value (price, earnings, moving average, RS, date) must come from a `scripts/` module. Never add a path that fills a market number from memory or the web. On failure a module reports `unavailable` — it does not guess.

3. **Every verdict ships its basis.** If you add or change a flag, score, grade, or label, expose the measurements it rests on and a `doctrine`/`threshold` field that says how to interpret it and where it is only a heuristic. Do **not** introduce a composite 0–100 "master score" — the design deliberately refuses one.

4. **Respect the doctrine hierarchy.** Minervini SEPA gates are immutable. TraderLion and other speaker material is a subordinate practice layer and must carry a provenance tag (`[M]`, `[TL]`, `[TL-Kell]`, `[MM-Ryan]`, `[MM-Zanger]`, `[MM-RitchieII]`). A practice-layer number may never be presented as a hard gate, and where the two conflict, Minervini wins.

5. **Never commit book text.** The source books are copyrighted and live only in the git-ignored `.tmp/` directory. Committed references must *paraphrase* principles, because the repository is public.

## The module contract

Deterministic code under `scripts/` follows a single public contract (see [`.claude/rules/module-contract.md`](.claude/rules/module-contract.md)). In short:

- One JSON document to stdout via the shared output helper; failures emit `{"error": "..."}` and exit 1.
- Every analysis operation is an explicit `argparse` subcommand; there is deliberately no "analyze everything" command.
- Tunable thresholds are flex-tier flags whose defaults reproduce canonical behavior; methodology boundaries are named module-level locked constants with a source tag and rationale, never bare inline literals.
- Every successful result carries a top-level `doctrine` field, and every threshold and emitted doctrine string carries its provenance tag.
- `--help` is the live spec and must run fully offline; every live source read goes through the shared cache layer.
- Add a lower-bound guard to any new numeric flag so a nonsensical value errors cleanly instead of returning a mislabeled result.

## Development workflow

```bash
# One-time setup
bash scripts/bootstrap.sh

# Run the deterministic test suite (contract tests are offline; smoke hits live APIs)
for t in scripts/tests/test_*.py; do scripts/.venv/bin/python "$t"; done
scripts/.venv/bin/python scripts/tests/smoke.py

# Validate harness structure (requires the harness-creator scripts if you have them)
# python3 <harness-creator>/scripts/validate_harness.py --path . --strict
```

When you change a module contract, add or update the tests that cover its success JSON, `doctrine` field, JSON-error/exit-1 behavior, offline `--help`, and cache behavior.

## Proposing changes

1. Open an issue first for anything beyond a small fix, so the design implications can be discussed before you invest effort.
2. Branch from the default branch, and keep commits coherent and well-described.
3. Make sure the deterministic tests pass, and for methodology changes, cite the source and provenance tag in your description.
4. Doctrine changes (new rules, changed thresholds) should explain *why* — a rule without its reasoning is a brittle rail, and the harness prefers principles a capable model can re-derive.

## Maintenance note

This harness was authored with the `harness-creator` methodology, and its binding design record lives in `.claude/harness-spec.md`. That file — not this repo's analyst-facing layers — is where maintenance rationale, status, and authoring policy belong. Keep it in sync when you change a component.

By contributing, you agree that your contributions are licensed under the project's [MIT License](LICENSE).
