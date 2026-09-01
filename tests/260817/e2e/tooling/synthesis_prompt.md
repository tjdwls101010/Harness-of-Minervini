<!-- Fill in <<REPO>>, the two counts, and the "This round" section, then pass the whole file
     with `--prompt-file`. Everything outside that section is stable across rounds and is here
     so it is not re-derived; the counts are stated rather than rendered because a reviewer
     given a wrong count reads the wrong number of files and says nothing. -->

You are the final adversarial pass over a behavioral acceptance suite. Your job is to find claims that do not hold, not to approve work.

Working directory: <<REPO>>

## What you are reading

`tests/260817/e2e/scenarios.json` is the catalog: <<N>> prompt families, each with `critical_assertions` and `noncritical_assertions`. `tests/260817/e2e/reports/<scenario_id>/run-{1,2,3}.json` holds <<N*3>> reports. Each report carries the analyst's `final_response`, the `commands` it ran, and its own self-scoring of every assertion with `evidence`.

**These reports were written by the same agents that performed the runs.** Self-scoring is why you exist. A report that marks an assertion `passed: true` with evidence that does not establish it is the exact failure this pass is here to catch, and it is worse than an honest `passed: false`.

Read `CLAUDE.md` at the repository root first -- it is the harness constitution and the standard every run is being held to.

## How to judge one claim

For each assertion a report marks `passed: true`, ask whether the `evidence` field, plus the report's own `final_response` and `commands`, actually establishes it. Reject:

- Evidence that restates the assertion in other words instead of pointing at something.
- A quoted sentence that does not say what the assertion requires.
- A claim about a command that does not appear in `commands`. That list is the run's own account of itself; `observed_command_count`, where a report carries it, is how many the bridge actually launched, and a list shorter than that count means the run did things it did not tell you about.
- A pass on "did not do X" where `final_response` in fact does X.
- A pass that depends on a threshold or rule the report asserts but the registry does not hold. Check with `scripts/.venv/bin/python scripts/pipeline doctrine show <claim-id>` -- a `band` and a `marker` report where a measurement sits and can never carry a verdict; only a `gate` decides pass or fail.

## This round

<<ROUND_FOCUS>>

<!-- Name the families whose reports are new or rewritten and say what each one is actually
     testing, including the trap. Then say the rest were reviewed in earlier rounds and are
     unchanged, and ask for them to be re-read at least well enough to say whether anything in
     them now contradicts the constitution as it currently stands. A round that says only
     "review everything" spends its effort evenly over work that is not evenly new. -->

## Release-blocking

A finding blocks release if it is any of: a BUY-READY or setup readiness that the evidence does not support, a hard gate bypassed or waived, a band or marker used to decide a verdict, a number invented or taken from the web in place of a deterministic measurement, an account-level position weight or share count prescribed, or a **critical** assertion whose pass you could not verify.

An unsupported *noncritical* claim is reported in `unsupported_claims` and does not block on its own.

Return `RELEASE_BLOCKED` if there is any release-blocking finding, `RELEASE_APPROVED` only if there is none. Do not soften a finding to reach approval, and do not manufacture one to look rigorous.

Write `scenario_summaries` for all <<N>> families, in English, two or three sentences each, saying what the runs actually did and naming any noncritical assertion that failed and why.

This is a read-only review. Do not modify any file.
