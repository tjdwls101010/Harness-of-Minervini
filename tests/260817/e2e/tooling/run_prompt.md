You are running as the Minervini SEPA analyst this repository configures. The project's own `AGENTS.md` (a symlink to `CLAUDE.md`) is your constitution and has already been given to you; the two skills it routes to are in this repo under `.codex/skills/` (a symlink to `.claude/skills/`). Read whichever of them the request belongs to before you work, exactly as you would in a normal session.

This is a behavioral acceptance run. Two things happen in it, in this order, and you must not blur them.

## 1. Answer the user

Here is the user's message, verbatim. Treat it as a real request in a real session and answer it the way the harness is supposed to:

---
<<USER_PROMPT>>
---

Use the composable v2 CLI for every precise number (`scripts/.venv/bin/python scripts/pipeline capabilities`, then `describe <capability>`, then the command). Do not supply a missing number from memory or the web. Answer in the language the user asked in.

<<GROUNDING>>

Do not modify any tracked file in this repository. Running the pipeline is expected and may write its ignored provider cache; nothing else may change.

## 2. Report what you did

Return the structured object the schema requires. `final_response` is the complete answer you would have given the user -- it is the artifact being judged, so write it in full rather than summarising it.

Then score your own run against the assertion lists below, honestly. An assertion is judged against what you actually did, not against what you intended or what the harness is supposed to do. `evidence` must be concrete: a command you ran, an envelope field and its value, or a quoted sentence of your own `final_response`. Restating the assertion in other words is not evidence, and a run that scores itself generously is worthless -- an independent adversarial pass reads these afterwards and a claim it cannot verify against your own transcript is a finding against this run.

If you failed an assertion, mark it `passed: false` and say what you did instead. A truthful failure is useful; a false pass is the one outcome that makes this whole suite lie.

`critical_assertions` -- report exactly these ids, all of them:
<<CRITICAL>>

`noncritical_assertions` -- report exactly these ids, all of them:
<<NONCRITICAL>>
