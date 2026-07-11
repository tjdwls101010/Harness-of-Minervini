# FAQ & Disclaimer

Straight answers to the common questions about what this harness does and does not do — followed by the fine print you should read before you rely on any of it.

## Frequently asked questions

### Is this financial advice?

No. This is an **analysis and education tool**, not investment, financial, legal, or tax advice, and not a recommendation, solicitation, or offer to buy or sell any security. It judges *what to buy, when to buy, and when to sell* as a research exercise, but it **never prescribes position sizes or portfolio allocations** — "put N% into X" is explicitly out of scope by design. The authors are not licensed financial advisers. See the [full disclaimer](#disclaimer) below.

### What markets and timeframes does it cover?

**US-listed equities only**, on **daily and weekly** timeframes. It operates **long or in cash** — that is the entire universe of positions it reasons about. Crypto and non-US listings are out of scope; when you ask about them the harness states the scope boundary rather than analyzing them.

### Does it short stocks or day-trade?

No. There are **no shorts and no intraday tactics** in v1. Long-or-cash on daily/weekly bars is the whole game. Intraday tools (opening-range breakouts, gappers, VWAP) and TraderLion "secondary universe" classes (non-earnings momentum, swing squeeze names) are deliberately deferred and default-disallowed.

### Where do the numbers come from, and can they be wrong?

Every precise market number — prices, moving averages, earnings, financials, relative strength, dates, breadth — comes **only from deterministic Python modules** under `scripts/`, which read three live sources:

| Source | What it provides |
|---|---|
| **yfinance** | Prices, financials, earnings |
| **Finviz** homepage scrape | Market breadth |
| **`ibd-rs-rating`** (Neon backend) | Relative-strength ratings for ~4,600 US stocks |

Yes, they can be wrong. Third-party data can be **inaccurate, incomplete, or stale**, an upstream source can change or go down, and the model's interpretation over that evidence can also be wrong. The design tries to make that failure *visible* rather than silent: on a data outage the harness **retries once, then declares the evidence `unavailable`** instead of guessing. It never fabricates a substitute or converts missing evidence into a pass or a fail. See [the module substrate](The-Module-Substrate.md) for how the deterministic layer is built.

### Does the model ever invent prices?

**No — by doctrine.** The constitution forbids supplying any missing market number from the model's memory or from the web. WebSearch is allowed only for *narrative* context — current catalysts, company activity, industry background — and can only explain deterministic evidence, never replace it. If a required number is not available from a module, the answer is `unavailable`, full stop.

### Why is there no single 0–100 score?

Deliberately, to avoid **deference**. A single master number invites the model (and you) to anchor on the score instead of reasoning over the underlying evidence. Instead, every gate verdict ships with its full basis — *which* criterion failed and *by how much* (measured value versus required threshold) — and every detector exposes its measurements plus a self-demoting label so the output stays interpretable rather than authoritative. This is the core of the output-schema philosophy; see [Design Principles](Design-Principles.md).

### What is the `[M]` / `[TL]` tagging I keep seeing?

It marks **provenance** in a two-tier doctrine. Minervini's SEPA is the immutable constitution; TraderLion's practitioner tactics are admitted only as a **tagged, subordinate practice layer**, with 26 documented conflicts resolved Minervini-first. Every borrowed threshold carries a tag so a practice-layer number can never masquerade as a hard gate:

| Tag | Meaning |
|---|---|
| `[M]` | Canonical Minervini SEPA doctrine |
| `[TL]` | TraderLion practice layer (tunable, subordinate) |
| `[TL-Kell]` | The 50-SMA position-trail exception |
| `[MM-Ryan]` / `[MM-Zanger]` / `[MM-RitchieII]` | *Momentum Masters* speaker context (not canonical) |
| `[heuristic]` | Harness-invented, self-demoting quantifier |

The full treatment lives in [The Minervini Method](The-Minervini-Method.md).

### Do I need API keys or paid data subscriptions?

No. All three data sources are **free** — yfinance, the Finviz homepage scrape, and the `ibd-rs-rating` package. There are no API keys to configure. What you do need is **[Claude Code](https://claude.com/claude-code)** and **internet access** for live market data. See [Installation](Installation.md).

### Can I use it outside Claude Code, or as a plugin?

Two separate answers:

- **The deterministic modules run standalone.** You can drive them directly from any shell without Claude Code and read the raw JSON evidence yourself, for example:

  ```bash
  scripts/.venv/bin/python scripts/pipeline qualify AAPL
  scripts/.venv/bin/python scripts/modules/vcp.py detect NVDA
  ```

- **The full harness needs Claude Code.** The analyst behavior — the constitution, the intent-split skills, the routing — is Claude Code machinery.

A Claude Code **plugin** packaging (for marketplace distribution) is **future work** per the harness spec; v1 ships as a project harness in `.claude/`. Plugin conversion is a recorded, deferred item because `CLAUDE.md` (the always-loaded constitution) does not ship with plugins and needs a redesign first.

### How current is the data?

The transparent cache is keyed to the **last completed US trading session** (America/New York), so repeated analysis within a day works from one coherent market snapshot. **While the market is open, price endpoints bypass the cache** (or use a TTL of at most 15 minutes) so live prices stay fresh; non-price data keeps the completed-session lifetime. Any module accepts `--no-cache` to force a fully fresh read. See the cache rules in the [module contract](The-Module-Substrate.md).

### What happens if a module fails?

The harness **retries the module once, then reports that evidence as `unavailable`**. It does not substitute a web value, a hand calculation, or a number from memory, and it does not silently downgrade missing evidence into a pass or a fail. A missing datum inside an otherwise useful result is reported as section-level `unavailable` rather than crashing the whole call.

---

## Disclaimer

This software is provided for **educational and informational purposes only**. It is **not** investment, financial, legal, or tax advice, and it is **not** a recommendation, solicitation, or offer to buy or sell any security. The authors are not licensed financial advisers.

Market analysis is inherently uncertain. The deterministic outputs can be **inaccurate, incomplete, or based on stale or erroneous third-party data**, and the model's interpretations can be wrong. Trading and investing involve **substantial risk of loss**. **You are solely responsible for your own investment decisions and for any losses you incur.** Use at your own risk.

The software is provided **"AS IS", without warranty of any kind**, as set out in the project `LICENSE` (MIT).

The **Minervini SEPA** methodology and the **TraderLion** materials referenced here are the intellectual property of their respective authors and organizations. This project independently paraphrases publicly-taught principles for the purpose of building an analysis tool; it does **not** reproduce, and is **not** affiliated with or endorsed by, Mark Minervini, TraderLion, or IBD.

---
[← Wiki Home](Home.md) · [Installation](Installation.md) · [Quickstart](Quickstart.md) · [Architecture](Architecture.md) · [The Minervini Method](The-Minervini-Method.md) · [Skills & Usage](Skills-and-Usage.md) · [Module Substrate](The-Module-Substrate.md) · [Design Principles](Design-Principles.md) · [Contributing](Contributing-and-Extending.md) · [FAQ](FAQ-and-Disclaimer.md)
