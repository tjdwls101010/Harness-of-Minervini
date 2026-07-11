# Harness of Minervini — Wiki

A Claude Code harness that turns Claude into a disciplined Minervini SEPA momentum-stock analyst for US equities, where every precise number comes from deterministic code and the judgment stays with the model.

## What this is

An AI agent is a model plus a harness: `ai-agent = ai-model + ai-harness`. The harness is the thin layer of context and capability that surrounds the model without touching its judgment. **This** harness makes Claude behave as a conservative-aggressive momentum-stock analyst in the tradition of Mark Minervini's SEPA (Specific Entry Point Analysis) — it discovers candidate leaders, judges concrete buy/sell/hold timing on US-listed stocks, and grounds every price, earnings figure, moving average, and relative-strength value in a suite of deterministic Python modules. The model never invents a market number; on a data outage it says *unavailable* rather than guessing. And there is deliberately **no 0–100 master score** — a single number invites deference, so each verdict ships with its full basis and the model reasons over the evidence to reach the call.

Two things keep the analyst honest. First, doctrine is *adjudicated, not averaged*: Minervini's SEPA is the immutable constitution, and TraderLion's practitioner tactics enter only as a tagged, subordinate practice layer with 26 documented conflicts resolved Minervini-first. Second, it is analysis-only — it judges what to buy, when, and when to sell, but **never** prescribes position sizes or portfolio percentages.

## Who this is for

- **Individual investors** who want rigorous, transparent, opinionated US growth-stock momentum research — a research assistant that gates before it opines and shows its work, not a black-box signal.
- **Builders and students of LLM harnesses** studying how to encode an expert methodology into a Claude Code harness without flattening it into a brittle scoring rubric — a reference design for keeping deterministic evidence and model judgment cleanly separated.

## What it does

You ask in plain language; the harness routes by intent. There is one fixed-shape sweep worth freezing — the `/screen` workflow.

| You ask… | Routes to… | and it… |
|---|---|---|
| "How's the market? What's strong?" | [`market-scan`](Skills-and-Usage.md) | reads breadth plus bottom-up leadership, calls a regime verdict with refutation conditions, and builds a watchlist |
| "Is PLTR a buy? NVDA vs AMD? Should I sell my NVDA?" | [`ticker-analysis`](Skills-and-Usage.md) | runs the Stage-2 + Trend-Template hard gate first, then earns entry / fundamentals / exit-plan convergence per ticker |
| "Grade my last 10 trades." | [`trade-review`](Skills-and-Usage.md) | scores each action /10 and computes batting average, R-multiples, hold-time asymmetry, and the Loss Adjustment Exercise |
| `/screen NVDA AMD AVGO --max-candidates 10` | [`/screen` workflow](Skills-and-Usage.md) | fans out a regime → qualify → synthesize sweep into ranked PROCEED / watch / avoid buckets |

The hard gate every prospective buy must clear is **Stage 2 AND Trend Template 8-of-8** (all AND conditions), with a relative-strength floor of RS ≥ 70. Underneath the skills sits a code substrate of 16 CLI modules and a two-command pipeline (`qualify`, `discover`) that pulls live data from yfinance, a Finviz breadth scrape, and the `ibd-rs-rating` package (~4,600 US stocks). See [the module substrate](The-Module-Substrate.md) for the full catalog.

## Documentation map

| Page | What's in it |
|---|---|
| [Installation](Installation.md) | Requirements, cloning, `bash scripts/bootstrap.sh`, data sources, and troubleshooting. |
| [Quickstart](Quickstart.md) | Your first analysis: worked natural-language prompts and driving the raw modules directly. |
| [Architecture](Architecture.md) | Every harness layer — constitution, skills, agent, workflow, rule, permissions — and why each lives where it does. |
| [The Minervini Method](The-Minervini-Method.md) | SEPA, the Trend Template 8-of-8, Stage analysis, VCP, and the two-tier Minervini/TraderLion doctrine. |
| [Skills & Usage](Skills-and-Usage.md) | Each skill and the `/screen` workflow: triggers, procedure, and example sessions. |
| [The Module Substrate](The-Module-Substrate.md) | The deterministic Python code, the JSON CLI contract, the same-session cache, and iterative parameter calls. |
| [Design Principles](Design-Principles.md) | The output-schema philosophy — verdict-plus-basis, no master score, provenance tags — that makes the split work. |
| [Contributing & Extending](Contributing-and-Extending.md) | Adding a module, respecting the contract, and the v2 backlog. |
| [FAQ & Disclaimer](FAQ-and-Disclaimer.md) | Scope, limits, data caveats, and the full fine print. |

## 30-second start

1. **Requirements:** [Claude Code](https://claude.com/claude-code) (2.1.154+ for the `/screen` workflow), Python 3.10+, and internet access for live market data.
2. **Bootstrap** the deterministic substrate from the repo root, then open the project in Claude Code and approve workspace trust:

```bash
git clone https://github.com/tjdwls101010/Harness-of-Minervini.git
cd Harness-of-Minervini
bash scripts/bootstrap.sh
```

3. **Ask, in natural language** — Claude routes by intent:

```
How does the market look right now?
Is AVGO a buy here?
Should I hold or sell my CRWD position from $410?
/screen NVDA AMD AVGO --max-candidates 10
```

Full setup lives in [Installation](Installation.md); your first worked analysis is in [Quickstart](Quickstart.md).

## Scope and the fine print

US-listed equities only, on daily and weekly timeframes, long or in cash — no shorts, no intraday tactics, and no portfolio-sizing prescriptions. This is an analysis and education tool, **not** financial advice; it can be wrong, and you are solely responsible for your own decisions — see [FAQ & Disclaimer](FAQ-and-Disclaimer.md).

---
[← Wiki Home](README.md) · [Installation](Installation.md) · [Quickstart](Quickstart.md) · [Architecture](Architecture.md) · [The Minervini Method](The-Minervini-Method.md) · [Skills & Usage](Skills-and-Usage.md) · [Module Substrate](The-Module-Substrate.md) · [Design Principles](Design-Principles.md) · [Contributing](Contributing-and-Extending.md) · [FAQ](FAQ-and-Disclaimer.md)
