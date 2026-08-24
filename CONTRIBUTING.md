# Contributing to Harness of Minervini

Thank you for improving the harness. Contributions should preserve the v2 separation between analyst principles, executable doctrine, interface contracts, provider evidence, and model judgment.

## Design invariants

1. Analysis quality and evidence honesty govern. A data gap remains missing; it never becomes an inferred pass, failure, remembered value, web substitute, or home-grown proxy.
2. Minervini eligibility and risk hard gates are immutable. TraderLion material may fill a genuine execution gap only as a tagged subordinate default or opt-in tactic.
3. Precise prices, dates, financials, breadth, classifications, and RS values come through typed providers. Web research may explain current narrative but cannot replace them.
4. Point-in-time support must be explicit. Completed bars, `filed_at <= as_of`, exact RS dates, mutable classification limits, retrieval time, source version, coverage, and content hashes are contract data rather than implementation trivia.
5. Do not introduce a weighted master score. Preserve independent axes and let no favorable signal erase a hard failure.
6. Do not commit book text. `.tmp/` is ignored build-time source material and is never a runtime dependency.
7. Keep one source of truth. Always-on judgment belongs in `CLAUDE.md`, task judgment in a routed skill, executable claims in `doctrine/claims.json`, exact usage in capability metadata and CLI help, and behavior in tests.

## Public interface contract

The canonical interface is `scripts/.venv/bin/python scripts/pipeline`. Use `capabilities`, `describe <capability>`, and leaf `--help` to inspect the current contract.

Every non-help operation emits exactly one v2 envelope. If a capability changes, update its registry metadata, parser and detailed help, operation implementation, schema projection, and parity tests together. A flag is valid only when code consumes it; compatibility-only decorative flags are prohibited.

Keep leaf help offline and detailed enough to explain purpose, inputs, defaults, as-of and provider limits, statuses, side effects, and examples. Markdown should teach interface discovery rather than duplicate the flag catalog.

## Test-driven workflow

Read the repository's TDD instructions before writing tests. Agree on a public seam, write the smallest failing test under the current dated suite directory in `tests/`, observe the intended RED failure, implement the smallest production change, and refactor only after GREEN.

```bash
bash scripts/bootstrap.sh
scripts/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
scripts/.venv/bin/python -m compileall -q scripts/minervini scripts/pipeline
scripts/.venv/bin/python -m pip check
```

Provider tests use frozen source-shaped fixtures and injected transports; they do not record live responses during the test run. Historical tests must include a future fact or bar that would expose look-ahead leakage. Side-effecting capabilities need adjacent tests proving that read-only operations do not create or mutate state.

Regenerate capability schemas with `PYTHONPATH=scripts scripts/.venv/bin/python -m minervini.schema_sync`, then run the schema and CLI contract suite. Validate harness topology with the harness-creator validator when `CLAUDE.md`, `.claude/`, `.agents/`, or permissions change.

## Doctrine changes

Change the normalized claim and its doctrine test before changing a reducer. Keep the claim's neutral ID, context, required inputs, failure and missing semantics, precedence, provenance, and quarantine status accurate. Runtime skills embody the result; they do not need bibliographic prose or source-database paths.

Explain why the change is faithful and which competing interpretation was rejected. A threshold without rationale becomes a brittle rail even when the number happens to be correct.

## Provider changes

Declare current and historical support separately. Add source, retrieval timestamp, effective as-of where supportable, version or coverage metadata, and content hash. Retry once at the provider boundary, then return typed unavailability. Never silently fall back to another provider or reconstructed formula.

## Pull requests

Keep commits coherent and surgical. In the pull request, state what changed, why the ownership layer is correct, impact on point-in-time and missing-evidence behavior, and the exact verification commands with result counts. Update `.claude/harness-spec.md` whenever topology, information ownership, permissions, routed skills, or validation requirements change.

By contributing, you agree that your contribution is licensed under the project's [MIT License](LICENSE).
