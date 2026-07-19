# Architecture

How the harness is built: one always-loaded constitution, three intent-split skills, a read-only scout, one fixed workflow, a paths-gated rule, narrow permissions, and a shared code substrate — each placed in the one layer where it does its job at the lowest cost.

## The core idea: `ai-agent = ai-model + ai-harness`

An AI agent is a model plus the scaffolding that shapes how it behaves. Here the model is Claude; the harness is everything under `.claude/` plus the `scripts/` substrate. The harness never tries to out-think the model — its whole job is to route the *right* doctrine and the *right* evidence into Claude's context at the *right* moment, and to keep precise market numbers out of the model's memory entirely.

That routing problem is what dictates the layer layout. Every piece of the harness earns its place by answering one question: **when does this content need to be in context, and what is the cheapest channel that guarantees it is there when needed?** Content that must never be missed goes in the only unconditional channel. Content that is expensive and job-specific is loaded only when its job is active. Developer-only guidance is kept out of analysis context entirely so its runtime cost is zero.

If you want the *why* behind the doctrine those layers carry, read [The Minervini Method](The-Minervini-Method.md); for the design values that produced this shape, read [Design Principles](Design-Principles.md). This page is about the structure.

## The layers at a glance

| Component | Layer | Loads into context when | Why it lives there |
|---|---|---|---|
| `CLAUDE.md` | Project memory (constitution) | **Always** — every session, unconditionally | The never-miss doctrine can ride on no trigger or routing probability |
| `market-scan` skill | Skill | Market / sector / breadth / regime / screening / watchlist intent | Split by user intent, not knowledge topic |
| `ticker-analysis` skill | Skill | Buy / sell / hold / timing / diagnosis of one or a few named tickers | Split by user intent, not knowledge topic |
| `trade-review` skill | Skill | Grading the user's own completed trade log | Genuinely different trigger context and input |
| `ticker-scout` agent | Subagent | Invoked per candidate during a screening fan-out | Isolates bulky command traces; read-only by construction |
| `/screen` workflow | Workflow | The user runs `/screen` | The one fixed-shape orchestration worth freezing |
| `module-contract.md` | Rule (paths-gated) | Editing files under `scripts/**` | Developer-facing; zero cost during analysis |
| `settings.json` | Permissions / config | Always — governs every tool call | Narrow allowlist plus one project-anchored deny |
| `scripts/` | Code substrate | Only when a module is invoked (never auto-loaded) | Shared by every consumer; plugin-symmetric |
| Hooks | — | **Never — there are none** | No must-never-happen item is both mechanically detectable and un-served by a deny rule |

The rest of this page explains each row and why it sits where it does.

## `CLAUDE.md` — the constitution, in the only unconditional channel

[`CLAUDE.md`](../../CLAUDE.md) carries the **analyst constitution**: the persona (a "conservative-aggressive opportunist"), the risk spine, the funnel and probability-convergence doctrine, the anti-default corrections, the two-tier doctrine rule with its provenance tags, the scope guards, and the data doctrine. It is the single file loaded into every session unconditionally — no trigger has to fire, no reference has to be routed, and it survives context compaction.

That is the entire reason the constitution lives here rather than inside a skill. Skill-body placement would bet the never-miss doctrine on trigger success; reference-file placement would bet it on routing compliance. Both are *probabilities*, and this is a domain where the model's own training makes "I already know Minervini, I can skip the gate" an easy rationalization. The constitution is precisely the content that must not ride on a probability, so it goes in the one channel that has none. The project consciously waives the usual ~200-line `CLAUDE.md` budget for this reason (the file is ~126 lines).

What `CLAUDE.md` deliberately does **not** contain: any enumeration of modules or components (only three trigger rules point at the skills), and any developer-facing maintenance guidance. It holds only facts and doctrine the *analyzing* Claude needs. Design records, authoring policy, and status history live in [`.claude/harness-spec.md`](../../.claude/harness-spec.md) — and `CLAUDE.md`'s first instruction is to *not* load that spec during analysis, because it is harness design, not runtime doctrine.

## Three skills, split by user intent

The three skills partition the work by **what the user is trying to do**, not by knowledge topic:

- **`market-scan`** — "How's the market?", regime and breadth, sector or industry strength, "find me leaders / breakouts", screening, watchlist building. See [`.claude/skills/market-scan/SKILL.md`](../../.claude/skills/market-scan/SKILL.md).
- **`ticker-analysis`** — buy / sell / hold / entry-timing / setup-diagnosis / re-entry / earnings-risk / chart-condition of one *or a few named* tickers, including a head-to-head comparison (gate each ticker, then compare). See [`.claude/skills/ticker-analysis/SKILL.md`](../../.claude/skills/ticker-analysis/SKILL.md).
- **`trade-review`** — grading, reviewing, or post-morteming the user's own *completed* trade log. See [`.claude/skills/trade-review/SKILL.md`](../../.claude/skills/trade-review/SKILL.md).

Intent is a clean disambiguator: the presence of a named ticker, market-level scope, or an own-trades log tells the router which skill to load, and each skill's description names its near-miss siblings explicitly to seal the boundaries (a single-ticker judgment routes out of `market-scan`; a completed-trade grade routes out of `ticker-analysis`; and all three refuse portfolio sizing). Because the shared constitution is already ambient in `CLAUDE.md`, duplication across the three bodies is near zero, and each body shrinks to a procedural shell of roughly a hundred lines (61 for `market-scan`, 73 for `ticker-analysis`, 94 for `trade-review`, against a ≤120-line budget). Deep methodology lives in each skill's `references/` files, routed in only when a branch needs it.

The `market-scan` and `ticker-analysis` skills grant the same qualified tool set (`Bash(scripts/.venv/bin/python *)`, `Bash(bash scripts/bootstrap.sh)`, `Read`, `Grep`, `Glob`, `WebSearch`, `WebFetch`) — never a blanket `Bash`. `trade-review` narrows further to `Bash(scripts/.venv/bin/python *)`, `Read`, `Grep`, `Glob` (it needs the interpreter for post-exit history reconstruction but no bootstrap and no web). All three inherit the session's model.

### Why fundamentals and chart are *not* separate skills

A tempting alternative is to split by knowledge domain — one skill for chart/technicals, one for fundamentals. The harness deliberately refuses this. "Is X a buy" needs both, always, in a fixed order (technical gate first, then fundamentals), because SEPA's whole premise is **probability convergence**: eligibility, entry structure, price/volume, required fundamentals, leadership, market, and risk must line up before a trade exists. Institutionalizing a chart-vs-fundamentals split at the *skill* boundary would let a favorable half bypass an unfavorable half — exactly the failure mode the method exists to prevent. Knowledge heterogeneity is real, so it is handled one level down, at the reference-file level (`entry.md` vs `fundamentals.md` vs `sell.md`), where the skill body controls the order in which they are read. See [The Module Substrate](The-Module-Substrate.md) and [Skills & Usage](Skills-and-Usage.md) for how those references and modules are used inside each branch.

## `ticker-scout` — read-only screening fan-out isolation

[`.claude/agents/ticker-scout.md`](../../.claude/agents/ticker-scout.md) is a single subagent with exactly one job: qualify **one** delegated US-listed ticker, run `scripts/.venv/bin/python scripts/pipeline qualify TICKER`, and return a compact verdict (`PROCEED` / `AVOID` / `INCOMPLETE` plus failed/unavailable gates, RS, Stage, and a one-line evidence string). It exists for a context-hygiene reason: qualifying dozens of candidates would flood the main conversation with JSON that has no value after the verdict is read. The scout absorbs that bulk in an isolated context and hands back only the distilled result.

It is **read-only by construction** — its frontmatter grants `Read, Grep, Glob, Bash` and omits `Edit`/`Write`, so it cannot modify files even in principle. It is also forbidden from deep-diving, using `WebSearch`, or inventing a missing number from memory; on module failure it retries once, then reports the evidence unavailable rather than fabricating an `AVOID`.

Note the deliberate asymmetry: **deep-dive analysis stays in the main conversation, not in an agent.** A screening pass is fan-out-and-summarize, which suits an agent; a deep dive is exactly the evidence the user wants to see and steer mid-analysis, so routing it through an agent would lossy-summarize the wrong thing.

## `/screen` — the one fixed-shape workflow

[`.claude/workflows/screen.js`](../../.claude/workflows/screen.js) is the single frozen orchestration. The screening sweep is the one task whose shape never varies — only its universe and date do — so it is worth encoding as a workflow: **Phase 1 Regime** (one agent runs `discover`, reads the regime references, and returns a regime read plus a leader/candidate survey; a hostile regime short-circuits to a watch-only report), **Phase 2 Qualify** (one `ticker-scout` per candidate, batched at most 16 concurrently, each verdict schema-validated), **Phase 3 Synthesize** (rank into `PROCEED` / `watch-incomplete` / `AVOID` buckets with the funnel counts preserved). It accepts optional args — a ticker list and `max-candidates` (default 30, bounded by a fan-out safety cap of 60).

The design rule is **thin skeleton, judgment in the prompts**: the JavaScript orchestrates phases, batching, schema validation, and bookkeeping, while every actual analytical judgment lives in the natural-language prompts handed to the agents. The skeleton also enforces the safety invariants the model should not have to remember — user-supplied tickers are mechanically merged into the candidate set (never dependent on the regime agent echoing them back), scout results are paired to their delegated ticker by index (a mismatch is discarded as unattributable, not silently reattributed), and anything the cap or input validation removes surfaces in a `dropped` field. A `PROCEED` from this sweep is explicitly *necessary but not sufficient* for buy-ready; the workflow has not done the entry, fundamentals, catalyst, and exit-plan convergence review. (The `/screen` workflow requires a recent Claude Code — see [Installation](Installation.md).)

## `module-contract.md` — a paths-gated developer rule

[`.claude/rules/module-contract.md`](../../.claude/rules/module-contract.md) is the developer contract for the `scripts/` code: `argparse` subcommands, exactly one JSON document to stdout via `utils.output_json`, the `{"error": ...}` + exit-1 failure shape, flex-tier flags vs locked-floor constants, the per-module `doctrine` field, `--help` as the offline live spec, the cache read-through obligation, and the provenance-tag discipline (`[M]`, `[TL]`, `[TL-Kell]`, `[MM-*]`, `[heuristic]`).

Its frontmatter gates it to `paths: ["scripts/**"]`, which is the whole point of putting it in a rule rather than in `CLAUDE.md`: it loads into context **only when Claude is editing a file under `scripts/**`**, and never during analysis. This is the prime-directive split in action — maintenance guidance is *data* a maintainer session reads when touching code, so it must impose zero token cost on the analyst who never touches code.

## Permissions — a narrow allowlist and one anchored deny

[`.claude/settings.json`](../../.claude/settings.json) is small and deliberate:

```json
{
  "permissions": {
    "deny": [
      "Edit(/.tmp/**)"
    ],
    "allow": [
      "Bash(scripts/.venv/bin/python *)",
      "Bash(bash scripts/bootstrap.sh)",
      "Bash(git status)",
      "Bash(git diff *)"
    ]
  }
}
```

The `allow` list is intentionally narrow — the exact command shapes the skills, scout, and workflow actually use — so routine module calls don't prompt for permission while the surface stays tight. The `deny` protects the git-ignored `.tmp/` (the raw book corpora and the prototype) from edits. The single leading slash in `Edit(/.tmp/**)` is load-bearing: it **anchors the pattern to the project root**. A bare `.tmp/**` would resolve against the current working directory and silently stop protecting whenever `cwd` is not the repo root. (Project `allow` rules activate only after the workspace is trusted, and `--dangerously-skip-permissions` bypasses even the deny — so that flag is prohibited on the real repo.)

## The code substrate at repo root

The Python lives at [`scripts/`](../../scripts) — `scripts/modules/` (16 modules: `actions`, `base_count`, `chart_render`, `earnings_acceleration`, `entry_patterns`, `info`, `market_breadth`, `market_clock`, `rs_ranking`, `sell_signals`, `stage_analysis`, `tight_closes`, `trend_template`, `utils`, `vcp`, `volume_analysis`), `scripts/pipeline/` (the orchestration exposing two commands, `qualify` and `discover`), plus `scripts/bootstrap.sh`, `scripts/requirements.txt`, and `scripts/tests/`.

It sits at the repo root, not inside any one skill's directory, because it is a **shared substrate**: all three skills, the `ticker-scout` agent, and the `/screen` workflow invoke the same modules. Nesting it under one skill would misstate ownership. Placement is also **plugin-symmetric** — at pluginization the whole directory moves to `${CLAUDE_PLUGIN_ROOT}/scripts` unchanged, and every consumer keeps invoking it through the same canonical root-relative path. Crucially, this code is never auto-loaded into context; it enters only as JSON produced by an explicit invocation, which is what keeps precise numbers deterministic instead of remembered. Its internals are covered in [The Module Substrate](The-Module-Substrate.md).

## `AGENTS.md` and `.codex/` — the same harness, a second front door

Clone the repository and you will find two things the layer table above does not mention: an `AGENTS.md` at the root, and a `.codex/` directory beside `.claude/`. Neither is a second copy of the harness. Both are **symlinks that re-expose the existing harness under the filenames other agent tooling looks for.**

```text
AGENTS.md      -> CLAUDE.md            # the vendor-neutral convention
.codex/skills  -> ../.claude/skills    # the same three skills, same files
.codex/agents/ticker-scout.toml        # a real file — see below
```

`AGENTS.md` is a symlink to `CLAUDE.md`, so tooling that follows the vendor-neutral `AGENTS.md` convention loads the identical analyst constitution. `.codex/skills` symlinks into `.claude/skills`, so a Codex-family CLI reading `.codex/` gets literally the same `SKILL.md` files and the same `references/` — not a fork that can drift. Git tracks these as symlink entries, so they survive a clone.

The one thing that **cannot** be symlinked is the agent definition, because the two formats genuinely differ: Claude Code uses YAML frontmatter with a Markdown body, while the Codex form is TOML with a `developer_instructions = """…"""` block. So `.codex/agents/ticker-scout.toml` is a real file whose prose is a transcode of [`.claude/agents/ticker-scout.md`](../../.claude/agents/ticker-scout.md) — same canonical command, same required-field list, same single-retry rule, same prohibitions.

**That one file is the maintenance hazard in this design.** Everything else is a symlink and therefore cannot fall out of sync; the TOML agent can, and will, if you edit the Markdown agent without making the matching edit. Treat the pair as a single unit when you touch either.

> There is no `.codex/hooks`. Earlier revisions carried a `.codex/hooks -> ../.claude/hooks` symlink that pointed at nothing, because — as the next section explains — this harness deliberately ships zero hooks. It was removed rather than left dangling.

## Zero hooks, by eligibility

The harness ships **no hooks**, and that is a decision, not an omission. There are only two "must never happen" items, and neither qualifies for a hook:

1. **Fabricating market numbers** — a hook can't parse the intent behind a `WebSearch`, so this isn't mechanically detectable. It is instead governed by the data doctrine, double-anchored in `CLAUDE.md` and each skill body, and verified behaviorally.
2. **Touching the book databases in `.tmp/`** — this is already fully enforced by the `permissions.deny` rule above; deny rules hold without a hook, and adding one would only tax every matching call with latency for no extra guarantee.

Session context (today's date, market open/closed, cache freshness) is injected by **skill preprocessing** — the `` !`command` `` block at the top of the analysis skills — rather than a `SessionStart` hook. That fires only when analysis actually happens (a session hook would tax every session, including pure maintenance ones) and is fresher, reading the clock at skill-load time.

---

*This page describes structure. Any buy/sell reasoning the layers produce is analysis and education, not financial advice — see [FAQ & Disclaimer](FAQ-and-Disclaimer.md).*

---
[← Wiki Home](README.md) · [Installation](Installation.md) · [Quickstart](Quickstart.md) · [Architecture](Architecture.md) · [The Minervini Method](The-Minervini-Method.md) · [Skills & Usage](Skills-and-Usage.md) · [Module Substrate](The-Module-Substrate.md) · [Design Principles](Design-Principles.md) · [Contributing](Contributing-and-Extending.md) · [FAQ](FAQ-and-Disclaimer.md)
