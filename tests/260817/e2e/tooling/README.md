# Running a behavioral round

`test_behavioral_artifacts.py` reads artifacts; it does not produce them. This directory is what produces them, so that a round can be re-run, or a family added, without rebuilding the pipeline from the artifacts it left behind.

The unit is a **round**: one or more prompt families from `../scenarios.json`, each answered `required_runs` times by an independent codex run that then scores itself, followed by one adversarial pass that reads all the reports and looks for scores its own evidence does not support.

## The sequence

```
render_tasks.py  -->  batch start  -->  write_report.py  -->  synthesis run  -->  build_aggregate.py
```

Add or edit the family in `../scenarios.json` first -- it is the catalog, and everything downstream reads it. Then:

```bash
python3 tests/260817/e2e/tooling/render_tasks.py --out /tmp/round.jsonl \
    --grounding-file tests/260817/e2e/tooling/grounding/isolated_sandbox.md \
    my_new_family another_family
```

```bash
python3 ~/.claude/skills/codex/scripts/codex_bridge.py batch start --group p7-round \
    --tasks-file /tmp/round.jsonl --model gpt-5.6-sol --effort high \
    --schema tests/260817/e2e/tooling/report.schema.json --sandbox workspace-write
```

Collect each member once the group is done, one at a time -- `result --group` does not parse schema output:

```bash
python3 tests/260817/e2e/tooling/write_report.py my_new_family 1 <run_id>
```

`synthesis_prompt.md` is a fill-in-the-blank document rather than a template a script renders, because its round-specific section is prose about what is new this round. Copy it, fill in `<<REPO>>`, the two counts and the `This round` section, and run the copy read-only against the same model:

```bash
cp tests/260817/e2e/tooling/synthesis_prompt.md /tmp/synthesis.md   # then edit /tmp/synthesis.md
```

```bash
python3 ~/.claude/skills/codex/scripts/codex_bridge.py start --label synthesis --sandbox read-only \
    --model gpt-5.6-sol --effort xhigh --schema tests/260817/e2e/tooling/synthesis.schema.json \
    --prompt-file /tmp/synthesis.md
```

Turn its verdict into `../aggregate.json`, which is the file the suite's release gate reads:

```bash
python3 tests/260817/e2e/tooling/build_aggregate.py <synthesis_run_id> 2026-09-01
```

Finally run the acceptance suite, which is the thing that decides whether the round holds:

```bash
scripts/.venv/bin/python -m unittest discover -s tests/260817/e2e -t . -p 'test_*.py'
```

## What each piece is for

| File | What it holds |
|---|---|
| `run_prompt.md` | The stable run prompt. `<<USER_PROMPT>>`, `<<CRITICAL>>` and `<<NONCRITICAL>>` come from the catalog; `<<GROUNDING>>` is the round's own paragraph. |
| `grounding/isolated_sandbox.md` | The paragraph the last Phase 7 rounds used, and the one that supersedes the shorter variants the earlier ones ran with: no network, stipulated facts are the evidence, check a threshold's role before treating it as a gate. |
| `report.schema.json` | What one run must return. Assertions come back as arrays because a structured-output schema cannot pin caller-chosen keys; `write_report.py` converts them to the dict the suite reads. |
| `synthesis_prompt.md` | The adversarial pass, with the round-specific section marked. |
| `synthesis.schema.json` | What the adversarial pass must return. |
| `render_tasks.py` `write_report.py` `build_aggregate.py` | The three steps above. `_bridge.py` finds the codex bridge (`CODEX_BRIDGE` overrides). |

## What a new round has to know

**Probe one run before starting the round.** A scenario premise can be one this harness cannot produce, and the round will not tell you -- it will produce `families x required_runs` articulate runs answering a question that does not exist. The first Phase 7 draft failed a candidate "because there were only two contractions"; `setup.vcp_contraction_count`'s [2, 6] is a **band**, so no such failure exists. `pipeline doctrine show <claim-id>` settles it: only a `gate` decides pass or fail.

**An isolated codex run has no network.** A provider-backed command fails after its retries unless the ignored provider cache happens to hold the answer, which makes the gap intermittent rather than absent -- a family cannot rely on either outcome. A family therefore reasons from facts the prompt stipulates, or from fixture envelopes under `../../fixtures/e2e/`, and the grounding paragraph has to say so -- otherwise the run reads the outage as the harness being broken and spends its answer on that.

**A scenario that hands over fixture envelopes must use the ticker those envelopes are about.** `--evidence` refuses a mismatch with `envelope_is_about_another_ticker`, and a run has been observed reading that refusal as an alias and reporting a verdict the envelope never reached. Nothing in the assertion list caught it until one was added that names the verdict the envelope actually holds.

**The reports are self-scored, and that is the whole reason the adversarial pass exists.** A run that marks an assertion passed with evidence that does not establish it is the failure mode; `build_aggregate.py` therefore counts the pass rate off the artifacts rather than taking the reviewer's tally, and demotes an unsupported claim inside the artifact it was claimed in, so the suite refuses on the count rather than on anyone's word.

**What a report says it ran is the run's own word, and only partly checked.** `write_report.py` refuses a report that lists more commands than the bridge launched -- a strict superset holds at least one command nobody executed -- and stores the bridge's `observed_command_count` beside the list so the adversarial pass has an independently sourced number to read. It does not compare the commands themselves against the transcript, so a run can still substitute one command for another of the same count. Treat a cited command as a claim rather than as a record.

**Do not build a round out of refusals alone.** Ten of the first families tested something the analyst must not do, and a harness that answers no to everything passes all ten. `converged_buy_ready` is why `test_at_least_one_family_asks_whether_the_harness_can_say_yes` exists; keep at least one family where the evidence converges and withholding is the wrong answer.

**A run that fails an assertion is evidence, not a re-roll.** Three of the Phase 7 families failed their first pass because the harness was wrong, not the run -- `risk.py` reported a control nobody had evaluated as `False`, and `ticker-analysis/SKILL.md` had no rule against typing a band reading into a declared plane state. Fix the harness and re-run all of the family's runs; re-rolling the one that failed is how a suite starts agreeing with itself.
