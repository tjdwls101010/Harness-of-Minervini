# Post-Implementation Review Protocol (Session A's audit of Session B)

> **역할**: 계획 세션(A)이 구현 세션(B)의 결과물을 독립 감사하는 프로토콜. B의 자기 보고는 검증되지 않은 주장으로 취급한다 — 모든 것을 직접 재확인한다. 이 문서는 A가 컴팩트된 뒤에도 검증 강도가 유지되도록 작성되었다.

## Ground truth (read first, in order)

1. `.claude/harness-spec.md` — the binding record. Check its Change history for what B claims to have done.
2. `docs/plans/implementation-plan.md` (rev 2) — what B was told to do, phase by phase, with acceptance criteria.
3. `docs/plans/research/{minervini,traderlion}-knowledge-map.md` — the knowledge ground truth for all doctrine prose.

## Pass 1 — Mechanical re-verification (trust nothing, re-run everything)

- `python3 ~/.claude/skills/harness-creator/scripts/validate_harness.py --path . --strict` → must be 0 errors regardless of what B reported.
- Line budgets, all-inclusive: CLAUDE.md ≤180; each SKILL.md body ≤120 (excl. frontmatter); each reference ≤350.
- `bash scripts/bootstrap.sh` from a clean state; both canonical invocation shapes run **from repo root** (plan §0); second identical fetch hits the cache, including one `rs_ranking` call.
- `scripts/tests/smoke.py` green — run it yourself.
- Deny-rule live probe: attempt an Edit on a `.tmp/` file with cwd ≠ repo root; the deny must fire (plan §7.1 — no structural check covers this).
- Spec status progression: every inventory row `generated`/`validated` must have its file on disk; every file on disk must have a row. Any drift = finding.

## Pass 2 — Adversarial multi-lens review (workflow fan-out; ~4-6 lenses)

Spawn independent reviewers, one per lens, findings schema'd, adversarially framed ("try to refute that this artifact is faithful"):

1. **Spec compliance** — every component vs its Component specs entry; frontmatter exactness (qualified Bash grants, no blanket Bash); permissions shapes (`Edit(/.tmp/**)` anchoring, trailing space-star word boundaries).
2. **Knowledge fidelity** — references vs the maps, threshold by threshold: exact numbers, provenance tags (`[M]`/`[TL]`/`[TL-Kell]`/`[MM-*]`), the 26 conflict resolutions honored (spot-check at least: §4-1 entry timing, §4-5 R-referee, §4-7 dual-gate, §4-24 anti-ATR routing, cascade third stage = prior-high failed retest), (a)-bucket content correctly ABSENT (re-teaching the model known material is a finding), conviction-over-compliance (rules carry their why).
3. **Code contract** — module-contract conformance; sell_signals↔stage_analysis single-ownership; cache session-date semantics (America/New_York last completed session, market-open bypass); honesty caveats present (key-reversal items ①/③, --margin-min-ppt).
4. **Description trigger quality** — the three descriptions against each other + near-miss coverage (validate_harness.py cannot check this; use harness-creator references/skills.md as the bar).
5. **Self-containment** — ticker-scout body assumes no default system prompt; screen.js is thin (no judgment in control flow, no Date.now/Math.random); CLAUDE.md contains no component inventory prose.
6. **Budget-pressure quality** — did B cut the *why*s to fit budgets? A reference that fits ≤350 lines by stripping justifications fails the authoring doctrine even though it passes the mechanical check.

Verify each finding before acting (adversarial verify pass); fix confirmed findings; update spec Change history in the same pass.

## Pass 3 — Behavioral (E2E, consent already granted 2026-07-10)

- If B ran V1-V6: read the actual transcripts/grades — a verdict without cited transcript evidence (tool_use event, file Read) is treated as not-run. Re-run any scenario whose grade lacks evidence.
- If B did not run them: run all 6 per spec Validation via `~/.claude/skills/harness-creator/scripts/run_e2e.py` (read harness-creator references/e2e-testing.md first — headless permission handling is a documented best guess).
- V3 (sell question actually Reads sell.md) and V5 (numbers from modules only) are the designated weak-point probes; if V3 fails after a persuasion-strengthening retry, invoke Plan B (promote the skipped reference to a skill — pre-agreed).
- Re-run failed scenarios only after repairs; record every outcome in spec Validation.

## Pass 4 — Improve

Route every confirmed failure through the repair table (spec Validation section): trigger miss → description; wrong behavior → strengthen the why; reference skip → routing persuasion → Plan B. Then re-validate (Pass 1 mechanical + affected scenarios only). Close with: spec Change history entry (mode: improve), commit in coherent units, push.
