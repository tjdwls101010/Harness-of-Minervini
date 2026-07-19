# Design Principles

The reasoning behind how this harness is built — the transferable lessons for anyone studying how to make a large language model reason rigorously over a specialist domain.

Most of this wiki tells you *what* the harness does. This page tells you *why* it is shaped the way it is. The Harness of Minervini is, at bottom, a bet about where to draw the line between a machine and a model: deterministic code owns everything that admits no judgment, and Claude owns the judgment. Eight principles fall out of that bet. Each is stated with its reasoning and the general lesson it teaches, because the specifics (SEPA, Trend Template, VCP) are incidental — the design pattern is not.

For how these principles are realized in files, read [Architecture](Architecture.md); for the code they govern, read [the module substrate](The-Module-Substrate.md).

---

## 1. Numbers are deterministic; judgment is the model's

The governing rule of the whole system: **precise market numbers come only from the Python modules under `scripts/`, never from Claude's memory or the web.** The constitution in [`CLAUDE.md`](../../CLAUDE.md) states it directly — obtain prices, earnings, financials, dates, breadth, and RS values only from `scripts/` modules, and never supply a missing market number from memory or WebSearch. WebSearch is admitted for one thing only: current narrative and catalyst context. It may *explain* deterministic evidence; it may never *replace* it.

Why split the work this way? Because the two failure modes are asymmetric. A language model that hallucinates a P/E of 34 when the real number is 84 produces a confident, plausible, wrong answer that no downstream reasoning can recover from. But a language model asked to weigh a *correct* 84 P/E against explosive growth is doing exactly what it is good at. So the harness removes the model from the one job it fails silently (recalling exact figures) and leans on it for the one job code cannot do (integrating messy evidence into a judgment). On module failure the doctrine is retry once, then declare the evidence unavailable — never fabricate a substitute.

**Transferable lesson:** find the sub-tasks where your model fails *silently and unrecoverably*, and move exactly those behind deterministic tools. Don't tool-ify what the model does well; you'll only add brittleness.

## 2. Every verdict ships its basis

A gate never returns a bare label. When `pipeline qualify` computes the two hard gates, it embeds the *evidence that produced them* directly in the payload. The Trend Template gate carries the full eight-criterion array — each criterion's `id`, `description`, measured `value`, and required `threshold` — so a `7/8` near-miss is distinguishable from a `2/8` wreck, and a caller can see *which* criterion failed and *by how much*. The Stage gate carries the classification's `structural_reads` (price-versus-200-day, the MA stack, trend structure). The comments in [`scripts/pipeline/_gates.py`](../../scripts/pipeline/_gates.py) put it plainly: a gate that hides its basis invites the model to anchor on the label instead of reasoning about the evidence.

The same discipline runs through the detectors. `vcp.py`, `stage_analysis.py`, `sell_signals.py` and the rest return their raw measurements *and* a self-labelling provenance block — every number tagged with where it comes from and whether it is doctrine or approximation (see Principle 4).

And there is deliberately **no composite 0-100 master score.** This is the single most load-bearing design choice in the harness, and `_gates.py` explains it in its own words: a single number invites the analyst to *defer* to it instead of reasoning — to anchor on "72/100" rather than read what the modules actually say. SEPA convergence is a judgment about whether the elements line up, and that judgment belongs to the model reading raw outputs against doctrine, not to a weighted average frozen in code. What *does* live in code is only the part that admits no judgment: the two binary hard gates, identical every time, which the model cannot rationalize past.

There is exactly one 0–100 number in the substrate, and the way it is hedged shows where the line actually falls. `vcp.py detect` returns a `setup_readiness.score` — a weighted composite of contraction quality, volume, pivot tightness, shakeout, time symmetry, demand, and pattern type. It is not a master score, and the payload works hard to say so: its `unit` field spells out the full weighting (`contraction 25 + volume 20 + pivot_tightness 15 + shakeout 15 + time_symmetry 10 + demand 10 + pattern 5`) and ends with **"never an eligibility gate"**, while an `eligibility_note` states that *"Pattern-only ranking; Stage 2 and Trend Template eligibility remain external."* If the locked VCP structure and duration checks fail, the classification degrades to `not_applicable` and the note reclassifies the number as *"descriptive only."*

The distinction that makes this consistent rather than hypocritical: this score ranks **one pattern's evidence against itself**, and it is arithmetically incapable of admitting a stock that failed a hard gate, because the gates are computed elsewhere and cannot be outvoted. A master score would be one that aggregates *across* the gate, entry, fundamentals, and market legs into a single number — that is the thing the harness refuses, because it is the thing a reader would defer to.

**Transferable lesson:** if you hand a model a scalar, it will defer to the scalar. Ship the *decomposed evidence* instead, and reserve frozen numbers for the genuinely binary. A score is a place for reasoning to stop; make your outputs places where reasoning can continue.

## 3. Honest states over fabrication

The system distinguishes several kinds of "not a pass," and never collapses them:

| State | Meaning | Where |
|-------|---------|-------|
| `FAIL` / `AVOID` | A known gate failed — structurally disqualified. Stop. | `_gates.py`, `qualify` |
| `UNAVAILABLE` / `INCOMPLETE` | Required evidence could not be obtained; no known gate failed. | `_gates.py`, `qualify` |
| `needs_input` | The measurement is computable, but only with a caller-supplied anchor the source does not define (e.g. `sell_signals extension` without a `--base-top`; it will not invent a base). | `sell_signals.py` |
| `needs_chart` | Deterministic code cannot resolve this; corroborate visually (e.g. the failed-retest stage of the failure cascade without an explicit prior-high). | `sell_signals.py` |

The distinction between the first two is enforced in code: in `compute_hard_gates`, a known `FAIL` takes precedence, but if evidence is merely missing the function returns `None`, and `qualify` renders that as `INCOMPLETE` — which, the docstring insists, must *never* be flattened into `AVOID`. "I don't know" and "this is disqualified" are opposite claims; conflating them either fabricates a rejection or launders a gap into a pass.

**Transferable lesson:** absence of evidence is its own state. The moment a pipeline coerces "unknown" into "no" (or "yes"), it starts lying with confidence. Give missing data, missing inputs, and missing visual context each a distinct, non-collapsible label — and make the code that could conflate them refuse to.

## 4. Doctrine is adjudicated, not averaged

The methodology is two authors who do not fully agree. Minervini's SEPA is the **immutable constitution**; TraderLion is a **subordinate practice layer**, admitted only where Minervini is silent, with 26 documented conflicts all resolved Minervini-first. Rather than blending them into a mush, the harness keeps every claim *attributed* with provenance tags that travel on the payloads and in the threshold comments:

- `[M]` — canonical Minervini SEPA doctrine (the only tier that is a gate)
- `[TL]` — TraderLion practice layer (tagged, tunable, subordinate)
- `[TL-Kell]` — the specific 50-SMA position-trail management exception
- `[MM-Ryan]` / `[MM-Zanger]` / `[MM-RitchieII]` — *Momentum Masters* speaker context, so conflicting numbers can never masquerade as SEPA rules
- `[heuristic]` — harness-invented quantifiers that *self-demote*: every one is labelled as an approximation and says what qualitative evidence it stands in for

You can see this in the substrate: `base_count.py` tags its base-separation step `[heuristic]` and says the map provides no fixed percentage; `stage_analysis.py`'s output carries a `provenance` block distinguishing `[M]` reads from implementation proxies; the `discover` command tags the QQQ switch `[TL]` and the bottom-up leader read `[M]`. The [module contract](The-Module-Substrate.md) makes this mandatory: only `[M]` is canonical, and every other value stays explicitly attributed so it cannot be mistaken for a Minervini gate.

**Transferable lesson:** when your domain has competing sources of truth, don't average them into a house style — *adjudicate* them and keep the seams visible. Attribution is not bureaucratic overhead; it is what lets the model apply the right precedence rule instead of silently importing a second doctrine's gates.

## 5. Conviction over compliance

Rules in this harness carry their *why*, so the model can re-derive them under pressure rather than merely obey them. Every successful module result includes a top-level `doctrine` field whose job — per the module contract — is to explain how to interpret the measurement and its limits, so that a numeric detector cannot silently become a trading verdict. The `vcp.py` pivot doctrine does not just say "wait for the pivot"; it explains that front-running saves negligible price while assuming the full risk of an unconfirmed setup. The `stage_analysis.py` risk doctrine does not just flag a large decline; it explains that abnormal weakness can reveal institutional exit before public fundamentals catch up.

This is a deliberate reaction against enumerated-rule brittleness. The harness spec records it as a prime goal: principles with reasons, over enumerated rules — because a prior single-skill attempt failed precisely at preserving the model's intelligence. A rule the model merely complies with breaks the moment a situation falls between its cases. A rule the model *understands* survives the edge case, because the model can reason from the underlying purpose. The constitution is placed in `CLAUDE.md` — the one channel that is always loaded and survives compaction — for the same reason: never-miss content should not ride on a trigger or routing probability.

**Transferable lesson:** encode the *reason*, not just the rule. A model that knows *why* a constraint exists generalizes it to unseen cases; a model that only knows the constraint fails silently the first time reality doesn't match the checklist.

## 6. No monolith — earn each deeper look

There is deliberately **no "analyze everything at once" command.** The pipeline exposes exactly two composable subcommands — `qualify` (the low-cost Stage-2 + Trend-Template + RS gate, run first) and `discover` (regime and leader survey) — and deepening past the gate means calling the individual module CLIs directly, in the order the funnel earns. [`scripts/pipeline/_commands.py`](../../scripts/pipeline/_commands.py) names the anti-pattern it is avoiding: a total-collect monolith reasons *for* the analyst by grouping every module into one verdict-shaped blob, which invites deference to the shape instead of reading the evidence. The module contract restates it as a standing rule: keep the deliberate absence of an "analyze everything" command, because parameterized modules preserve the evidence funnel and let each deeper call earn its cost.

This mirrors how a disciplined analyst actually works — a cheap technical gate can disqualify a name before any expensive fundamental work is spent on it — and it keeps the model *choosing* what to look at next based on what it has seen, rather than being handed a pre-assembled conclusion.

**Transferable lesson:** a "do everything" endpoint is a conclusion wearing the costume of data. Prefer small composable tools the model orchestrates itself; the sequence of calls *is* the reasoning, and collapsing it into one blob removes exactly the reasoning you wanted.

## 7. Numbers decide; eyes corroborate

The harness can render daily and weekly charts (`chart_render.py`), and the model is encouraged to look at them to resolve qualitative, pattern-character ambiguity. But a rendered chart is **never a gate.** The constitution is explicit: numbers decide and eyes corroborate — rendered charts may resolve qualitative ambiguity, but visual opinion never overrides a deterministic gate. A chart can help decide whether a base *looks* like a proper VCP; it cannot overturn a failed Stage-2 or a `7/8` Trend Template.

The ranking matters because the two evidence types fail differently. A deterministic gate is reproducible and auditable; a visual read is exactly the kind of soft, narratively-persuadable judgment that lets a trader talk themselves past a hard failure. Admitting charts as corroboration captures their real value (character, "look-left" context) without letting them become the loophole through which discipline leaks.

**Transferable lesson:** when you mix hard signals and soft signals, fix the precedence *in advance and in writing*. Soft evidence that can override hard evidence isn't corroboration — it's a bypass.

## 8. Self-contained outputs, paid for by compacting the diagnostics

The harness runs inside a long conversation whose history gets **compacted** — older tool output is summarized away. That creates a specific hazard: if a module's *interpretation* (its `doctrine`, `provenance`, and threshold labels) lived only in a reference file or an earlier turn, compaction could strip the numbers of the very context that makes them safe to use. So the design choice is that the interpretation rides on *every* payload — each result is self-describing, carrying the doctrine and provenance needed to read it correctly even in isolation.

That self-sufficiency has a token cost, and the harness pays it back where the content is *not* interpretation. The `_cache` diagnostic block that rides on every payload is deliberately compacted: `utils.cache_metadata` keeps only the interpretation-bearing fields — whether a value was live or cached (`status`/`counts`) and that it belongs to the current market session (`session_dates`) — and strips the cache-internal plumbing (`params_hash`, cache `key`, `age_seconds`) that would only inflate every repeated call. Full per-event detail stays available for debugging behind `MINERVINI_CACHE_DEBUG=1`.

**Transferable lesson:** in a compaction-bearing context window, make each payload carry the context needed to interpret *itself* — you cannot assume earlier turns survive. Then budget aggressively: spend tokens on what changes the reading, and compact everything that is pure plumbing behind an opt-in debug flag.

---

Everything above serves analysis and education, not financial advice — the harness never prescribes position sizes and never tells you to buy or sell; see [FAQ & Disclaimer](FAQ-and-Disclaimer.md). If you want to *extend* the system while honoring these principles, [Contributing & Extending](Contributing-and-Extending.md) shows where each one is enforced in code.

---
[← Wiki Home](README.md) · [Installation](Installation.md) · [Quickstart](Quickstart.md) · [Architecture](Architecture.md) · [The Minervini Method](The-Minervini-Method.md) · [Skills & Usage](Skills-and-Usage.md) · [Module Substrate](The-Module-Substrate.md) · [Design Principles](Design-Principles.md) · [Contributing](Contributing-and-Extending.md) · [FAQ](FAQ-and-Disclaimer.md)
