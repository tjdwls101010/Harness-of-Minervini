# Quickstart

Your first session with the harness — the natural-language way for everyday analysis, and the direct-CLI way to see the raw deterministic evidence underneath.

This page assumes the substrate is already installed. If not, do [Installation](Installation.md) first — the one-time step is `bash scripts/bootstrap.sh` from the repo root, then open the project in Claude Code and approve workspace trust so the narrow module permissions activate. You need [Claude Code](https://claude.com/claude-code) (2.1.154+ for the `/screen` workflow) and Python 3.10+.

> This is an analysis and education tool, not financial advice, and it never prescribes position sizes. See [FAQ & Disclaimer](FAQ-and-Disclaimer.md).

## Two ways to drive it

1. **Natural language** — you ask in plain English; Claude routes to the right skill, calls the deterministic modules for every number, and returns an evidence-cited verdict. This is how you will use it 95% of the time.
2. **Direct CLI** — you run the Python modules yourself and read the raw JSON. Useful for spot-checks, scripting, or seeing exactly what evidence the model is reasoning over.

Both paths hit the same code substrate, so they never disagree on a number. For the deeper tour of what sits behind them, see [Architecture](Architecture.md) and [the module substrate](The-Module-Substrate.md).

## The natural-language way

Just type your question. Claude reads your intent and routes to one of three skills — you do not name the skill, and you do not need to say "Minervini."

| What you type | Routes to | What comes back |
|---|---|---|
| `How does the market look right now?` | `market-scan` | Session/source health, a regime read with refutation conditions, funnel counts, and a bucketed watchlist |
| `Is AVGO a buy here?` | `ticker-analysis` | The hard-gate result first, then entry/fundamentals/market/exit convergence — or an early stop if the gate fails |
| `NVDA vs AMD — which setup is better?` | `ticker-analysis` | Each ticker gated independently, then compared side by side |
| `Should I hold or sell my CRWD from $410?` | `ticker-analysis` | `SELL` / `HOLD WITH CONDITIONS` / `INCOMPLETE`, with dated triggers |
| `Grade my last 10 trades.` | `trade-review` | Per-action /10 grades, batting average, R-multiples, hold-time asymmetry, and the Loss Adjustment Exercise |
| `/screen NVDA AMD AVGO --max-candidates 10` | `/screen` workflow | A regime → qualify → synthesize sweep into ranked PROCEED / watch / AVOID buckets |

### Example prompts by intent

**Market read** (→ `market-scan`)

```
How's the market? What's leading?
Is this a risk-on environment or should I be in cash?
Build me a watchlist of current leaders.
```

Expect a bottom-up regime call: the `[TL]` QQQ-versus-21EMA switch is treated as environmental information only, while `[M]` leader quality and actual trade traction decide the conclusion. Every regime label ships with the observable evidence that would refute it — a label without invalidation conditions is an opinion, not an analysis.

**Single-ticker buy / diagnosis** (→ `ticker-analysis`)

```
Is PLTR a buy here?
What's wrong with this SMCI setup?
Is there a valid entry pivot on ANET?
```

Expect **qualify-before-opinion**: Claude runs the Stage-2 + Trend-Template hard gate *first*. A known gate failure returns `AVOID` for the prospective buy and stops — favorable fundamentals or a nice chart cannot buy back a failed gate. Only on `PROCEED` does it earn the deeper look (entry structure, then required fundamentals, then market alignment, then a written exit plan). Missing evidence returns `INCOMPLETE`, not a fabricated pass or fail.

**Multi-ticker comparison** (→ `ticker-analysis`)

```
NVDA vs AMD vs AVGO — rank the setups.
Compare CRWD and PANW for a new position.
```

Each ticker is gated on its own before any comparison, so one strong name never launders a structurally disqualified one.

**Sell / hold on an existing position** (→ `ticker-analysis`)

```
Should I sell my NVDA? I got in at $118 with a stop at $109.
I'm up big on VRT from $85 — hold or trim?
```

Give Claude your entry, stop, and any base-top/breakout anchors — it asks only for facts that change the branch and will not invent them. Expect a `SELL` / `HOLD WITH CONDITIONS` / `INCOMPLETE` verdict backed by dated sell diagnostics (extension, reversal, MA trail, failure cascade) and earnings-date risk.

**Trade-log grading** (→ `trade-review`)

```
Grade my last 10 trades: [ticker, entry date/price, exit date/price, stop]
What does my trading record reveal?
```

Expect a *process* audit, not a P&L scoreboard — a profitable rule violation can score low and a clean small loss can score high. You get a metrics table, per-action /10 grades citing named doctrine, and the Loss Adjustment Exercise (recompute the record with every loss set to 10% to isolate whether loss distribution, not stock selection, hurt expectancy).

**The `/screen` workflow**

```
/screen
/screen NVDA AMD AVGO
/screen PLTR CRWD --max-candidates 10
```

This runs the one fixed-shape sweep: a regime + leader survey, one read-only scout per candidate running `qualify`, then synthesis into `proceed` / `watch` / `avoid` buckets with explicit funnel counts. Your own tickers are always kept as candidates and surface first. `--max-candidates` defaults to 30 (a default, not a hard ceiling; a fan-out safety cap of 60 prevents a typo from spawning hundreds of scouts). If the regime is hostile, the workflow stops at a watch-only report instead of spending calls on qualification. See [Skills & Usage](Skills-and-Usage.md) for the full procedure.

### What every verdict has in common

- **Routing is automatic.** Intent picks the skill; you never wire it up.
- **Qualify runs before any opinion.** The low-cost Stage-2 + Trend-Template gate (all 8 criteria as AND conditions, RS ≥ 70 floor) is the first thing checked. Structure gates the trade.
- **The verdict is cited, never asserted.** A gate result does not just say "7 of 8" — it names *which* criterion failed and *by how much*. There is deliberately **no composite 0–100 score**, because a single number invites deference instead of reasoning.
- **`PROCEED` is not a buy.** Candidates mature through a `watch → buy-alert → buy-ready` state machine; `PROCEED` only means the hard gate earned a deeper look.
- **The scope boundary holds.** US-listed equities only, long or cash, daily/weekly. Ask for a position size or portfolio percentage and Claude explains the boundary and offers setup, risk, and evidence-quality analysis instead.

## The direct-CLI way

Every number the model uses comes from these modules, and you can run them yourself. Use the canonical root-relative form — run from the repo root, and never `cd scripts`:

```bash
scripts/.venv/bin/python scripts/pipeline qualify AAPL
scripts/.venv/bin/python scripts/modules/<module>.py <subcommand> [flags]
```

Start with the eligibility gate. `qualify` is the same Tier-0 gate the skills run first:

```bash
scripts/.venv/bin/python scripts/pipeline qualify AAPL
```

The verdict ships **with its full basis** — the per-criterion measured-vs-required values and a plain-language `doctrine` field explaining how to read it (trimmed):

```json
{
  "ticker": "AAPL",
  "verdict": "PROCEED",
  "failed_gates": [],
  "unavailable_gates": [],
  "hard_gates": [
    { "gate": "stage_2", "status": "PASS", "current_stage": 2, "required": 2 },
    { "gate": "trend_template", "status": "PASS", "score": "8/8", "required": "8/8",
      "criteria": [
        { "id": 8, "description": "RS Ranking >= 70", "status": "PASS",
          "value": "RS Score = 75 (ibd_rs_rating_backend)",
          "threshold": "[M] RS >= 70; local proxy uses only its 12M historical percentile provisionally" }
      ]
    }
  ],
  "stage": 2,
  "trend_template_score": "8/8",
  "rs_rating": 75,
  "rs_source": "ibd_rs_rating_backend",
  "interpretation": {
    "PROCEED": "both hard gates pass (Stage 2 + Trend Template 8/8) — worth a full read, NOT yet a buy",
    "AVOID": "a hard gate failed — structurally disqualified; stop here",
    "INCOMPLETE": "required gate evidence is unavailable and no known gate failed"
  },
  "doctrine": "[M] These two gates are deterministic and non-negotiable, and that is ALL they are: eligibility, not a trade. There is deliberately no composite score..."
}
```

Two things to notice: the `[M]` tag marks canonical Minervini doctrine (a `[TL]` tag would mark the subordinate TraderLion practice layer), and the `interpretation` + `doctrine` fields travel *with* the data so the output can never be mistaken for a buy signal.

Then earn the deeper look with a few modules — each emits one self-describing JSON document. Run any subcommand with `--help` offline to see its flags, and add `--no-cache` to force a fresh read:

```bash
# Entry structure: how tight are the base's contractions? (VCP footprint)
scripts/.venv/bin/python scripts/modules/vcp.py detect NVDA

# Price/volume: is there institutional demand behind the move?
scripts/.venv/bin/python scripts/modules/volume_analysis.py analyze NVDA

# Sell-side: run the dated 21e → 50s → prior-high → 200s failure cascade
scripts/.venv/bin/python scripts/modules/sell_signals.py cascade TSLA --start 2026-04-01
```

A `qualify` returning `AVOID` means the ticker is structurally disqualified — stop there. `PROCEED` means keep going. `INCOMPLETE` means required evidence was unavailable (retry once, then report it unavailable — never guess). The available modules and their contract are catalogued in [the module substrate](The-Module-Substrate.md).

## Where to go next

- New to the methodology? Read [The Minervini Method](The-Minervini-Method.md) for SEPA, the Trend Template, VCP, and the two-tier doctrine.
- Want the full procedure behind each skill? See [Skills & Usage](Skills-and-Usage.md).
- Curious *why* the outputs are shaped this way? [Design Principles](Design-Principles.md) explains the no-master-score, evidence-with-basis philosophy.

---
[← Wiki Home](Home.md) · [Installation](Installation.md) · [Quickstart](Quickstart.md) · [Architecture](Architecture.md) · [The Minervini Method](The-Minervini-Method.md) · [Skills & Usage](Skills-and-Usage.md) · [Module Substrate](The-Module-Substrate.md) · [Design Principles](Design-Principles.md) · [Contributing](Contributing-and-Extending.md) · [FAQ](FAQ-and-Disclaimer.md)
