# The Minervini Method

This page explains the trading methodology the harness encodes — Mark Minervini's SEPA — so you can read the harness's verdicts knowing exactly what discipline produced them.

If you have never heard of SEPA (Specific Entry Point Analysis), start here. The harness does not invent a trading philosophy; it faithfully operationalizes an existing one. Understanding the method is the difference between reading a verdict and trusting it. For how that method is split across configuration layers, see [the architecture](Architecture.md); for the Python tools that measure it, see [the module substrate](The-Module-Substrate.md).

> This page is analysis and education, not financial advice. The harness never prescribes position sizes, it can be wrong, and markets can lose you money. See the [FAQ & Disclaimer](FAQ-and-Disclaimer.md).

## Three decisions, not one

SEPA frames trading as **three separate decisions**, and the harness keeps them separate on purpose:

1. **What to buy** — a genuine market leader with the fundamentals, relative strength, and institutional demand to move.
2. **When to buy** — a precise, low-risk entry after a constructive base, at a pivot where supply has been absorbed.
3. **When to sell** — a predefined exit plan, written *before* entry, that treats being wrong as normal and staying wrong as the only real error.

A strong company never substitutes for timing, and good timing never substitutes for an exit plan. All three must be present. Much of what looks like discipline in the harness is simply its refusal to let one strong decision paper over a missing one.

## The stance: conservative-aggressive opportunist

The analyst persona the harness adopts is a **conservative-aggressive opportunist**. It pursues exceptional upside, but only where the downside is tightly defined — because asymmetry, not raw aggression, is what creates superperformance.

This produces a fixed question order: **"How much can I lose?" comes before "How much can I gain?"** Capital preservation is treated as the prerequisite for compounding, not a constraint on it. Two consequences follow throughout the harness:

- **No-trade is the strong default.** New leaders and fresh setups recur constantly, so a marginal trade never justifies relaxing the criteria. When evidence does not converge, *cash* is a valid conclusion.
- **Decision quality is judged separately from outcome.** The method calibrates to roughly a 40–50% win rate, so losing streaks are diagnostic evidence about entry quality or market regime — not proof that a sound method failed.

## The funnel: earn every deeper look

The harness does not run one monolithic "analyze everything" command. It works the way a disciplined trader does — a cheap gate first, then progressively more expensive scrutiny, stopping the moment a hard failure makes further work pointless.

```text
Stage 2 + Trend Template gate   ← cheap, deterministic, run FIRST
        ↓ (only if eligible)
Base maturity, VCP, price/volume
        ↓
Fundamentals, catalyst, leadership
        ↓
Entry structure + market alignment + exit plan
        ↓
      Manual final judgment
```

Two principles govern the funnel:

- **Technical eligibility comes before deep fundamental work.** Institutions can leave a stock before its reported business story deteriorates, so price and trend are checked first. A stock below a falling 200-day moving average is not rescued by good earnings or a compelling narrative.
- **Trade only where fundamentals, price/volume, and market conditions converge.** A good company alone, a good chart alone, or a good market alone is not a trade. The final call is made manually, by the model reasoning over the deterministic evidence — the screens remove noise, they do not render the verdict.

A known Stage 2 or Trend Template failure **rejects** a prospective buy. Missing evidence produces an **incomplete** verdict — never a silently assumed pass or fail. That three-state honesty (pass / fail / unavailable) runs through every module.

## Stage 2 and the Weinstein stages

Underneath the whole method is the lifecycle model of a stock, borrowed from Stan Weinstein and used by Minervini as the coarse filter for *when* a stock is worth owning:

| Stage | Character | Tradability |
|---|---|---|
| **Stage 1** | Neglect / basing after a decline | Not yet — no demand |
| **Stage 2** | Advancing / accumulation | **The only long zone** |
| **Stage 3** | Topping / distribution | Tighten, prepare exit |
| **Stage 4** | Declining / capitulation | Never long |

The large advances in the Minervini record occur almost entirely in **Stage 2**, when institutions are accumulating. The harness only takes long positions here. A crucial subtlety the harness enforces: **a sideways base *inside* an established Stage 2 advance is a consolidation in that advance, not a fresh Stage 1** — the same shape means different things depending on lifecycle context, so the harness always establishes that context before reading the pattern.

## The Trend Template: an 8-of-8 AND gate

Stage 2 eligibility is made concrete by Minervini's **Trend Template** — eight criteria evaluated deterministically by `trend_template.py`. This is a hard gate: **all eight are AND conditions**, and none can be rationalized away with valuation, narrative, or strong earnings.

```text
scripts/.venv/bin/python scripts/modules/trend_template.py check NVDA
```

The eight criteria, exactly as the module computes them:

| # | Criterion | Threshold |
|---|---|---|
| 1 | Price above the 150-day MA **and** the 200-day MA | Price > SMA150 and > SMA200 |
| 2 | 150-day MA above the 200-day MA | SMA150 > SMA200 |
| 3 | 200-day MA trending up | Rising for 1+ month (4–5 months preferred) |
| 4 | 50-day MA above the 150-day MA **and** the 200-day MA | SMA50 > SMA150 and > SMA200 |
| 5 | Price above the 50-day MA | Price > SMA50 |
| 6 | Price at least 30% above the 52-week low | Price ≥ 52w low × 1.30 |
| 7 | Price within 25% of the 52-week high | Price ≥ 52w high × 0.75 |
| 8 | Relative Strength rank at or above the floor | **RS ≥ 70** (80s–90s preferred) |

Criteria 1–7 describe a properly stacked, rising moving-average structure with price near its highs — the geometric signature of an institutional uptrend. The 30%-above-low and 25%-below-high boundaries (criteria 6 and 7) are **locked methodology constants** in the module, not tunable settings.

Criterion 8 — the **RS ≥ 70 floor** — measures how the stock ranks against the broad universe of US stocks. It is the one criterion that can come back `unavailable` rather than pass/fail: the module resolves the authoritative RS rating first, then a labelled local proxy, then declares the evidence unavailable. **A data outage is incomplete evidence, not a failed criterion.** See [the module substrate](The-Module-Substrate.md) for the RS data path.

An honest failure at any one criterion is enough to reject the setup. Seven of eight is not "close" — it is a fail. Below a falling 200-day MA, the harness will not go long at all.

## The VCP: reading the supply footprint

Passing the gate makes a stock *eligible*; it is not yet a trade signal. The **entry** still requires a constructive base, and the harness's primary base pattern is the **Volatility Contraction Pattern (VCP)**.

A VCP is not a shape to pattern-match — it is a story about supply. As a stock bases, successive pullbacks get **shallower** and volume **dries up**: strong hands are absorbing the shares that weak hands are giving up. As available stock shrinks, less and less demand is needed to push price through the **pivot** — the line of least resistance at the top of the final contraction.

The harness records a VCP as a compact **footprint** so the geometry is inspectable:

```text
nW  d/f  nT        e.g.   40W 31/3 4T
│    │    └─ number of contractions (T)
│    └────── max depth % / final contraction %
└─────────── base length in weeks (W)
```

`40W 31/3 4T` reads as forty weeks long, a 31% maximum correction, a 3% final contraction, and four contractions. What the harness looks for inside that footprint:

- **Contractions that roughly halve.** A valid VCP usually shows two to six contractions (most often two to four), each about half the prior one — the canonical `25% → 15% → 8%` model.
- **Volume drying up into the pivot.** The final contraction must show below-average volume, ideally one or two exceptionally quiet sessions. Shrinking price without drying supply is not a VCP.
- **Time as part of the absorption.** A V-shaped or time-compressed right side is not ready just because price returned to resistance — strong hands need time to replace weak holders.
- **A completed pivot, confirmed by demand.** The default entry is the *completed* breakout (price trading meaningfully above the pivot on volume above the stock's 50-day average). The harness does **not** anticipate an unfinished pattern, buy a bottom, or treat an undercut still in progress as a signal.

```text
scripts/.venv/bin/python scripts/modules/vcp.py detect SYMBOL
```

## The risk spine

The exit plan is written before entry, and it is where the method's asymmetry is enforced. The harness treats these as non-negotiable:

- **The initial stop is calibrated, not arbitrary.** `stop_pct = min(0.5 × realized_average_gain_pct, 10%)`. The stop is no wider than half the trader's own realized average gain, hard-capped at an absolute 10% ceiling, aiming to keep average losses near **6–7%**. If the realized average gain is unknown, the harness says the calibrated stop cannot be computed — it does not treat the 10% ceiling as the recommended stop.
- **Reward must dominate risk.** Require at least **2:1** expected reward-to-risk; prefer **3:1**. With a ~40–50% batting average, payoff asymmetry — not frequent correctness — is what carries positive expectancy.
- **At 3R, defend at least breakeven.** Once a position has earned several times its initial risk, letting it become a loss destroys the original asymmetry.
- **Never widen a stop (anti-ATR).** A stop is never loosened because volatility rose or repeated stop-outs feel frustrating. In a hostile market the harness *tightens* the operating range (roughly 5–6%) rather than granting more room.
- **Never average down.** A proper entry that immediately loses ground has become *less* attractive, because price is rejecting the thesis. Adds come only after price confirms.
- **Treat profits as principal, not house money.** An appreciated position gets the same loss discipline; an undefended unrealized gain is a loss waiting to be realized.
- **Respect time.** A correctly chosen leader should act promptly; failure to make expected progress can justify an exit even before the price stop is touched.

When deterioration does begin, the harness reads it as a dated **failure cascade** rather than a single event:

```text
loss of 21-day EMA  →  loss of 50-day SMA  →  failed retest at the prior high  →  loss of 200-day SMA (terminal)
```

Each stage is more serious than the last, and the harness reports the highest *evidenced* stage with its dates — it will not jump from a lone 21 EMA close to a completed cascade. A hard price stop and the 3R breakeven rule always remain controlling.

```text
scripts/.venv/bin/python scripts/modules/sell_signals.py cascade SYMBOL --start YYYY-MM-DD
```

## Corrections to common instincts

A large part of what SEPA teaches is *unlearning* intuitions that feel prudent but lose money. The harness bakes in these corrections:

- **A lockout rally is not an automatic sell.** After a bear market, persistent overbought conditions with shallow (roughly 3–5%) pullbacks can reveal exceptional demand — the first powerful leg up — rather than a top.
- **"It's cheap now" is never a reason to buy or hold.** Cheapness only strengthens a *failing* thesis as price falls, and invites averaging down. An ultra-low P/E near a 52-week low is a **red flag**, not a bargain — price may be discounting an earnings collapse the trailing numbers have not yet shown.
- **Reject broken-leader syndrome.** A former leader down 70–75% in Stage 4 is not made safe by the size of its decline; every new buyer still has 100% of their capital at risk, and substantial downside can remain.
- **Price leads earnings, in both directions.** A material abnormal decline deserves respect *before* the public explanation arrives — even after apparently good news.
- **High P/E alone is never a reject.** Explosive growth routinely earns expanding expectations before the biggest advance; historical maximum winners often began at 30–40× earnings or more.
- **New highs are strength, not "too expensive."** A new high is evidence of demand and the absence of overhead supply. The harness buys *confirmation*, not bottoms — surrendering the first advance is the price paid to avoid downtrends and trapped overhead sellers.

## Two-tier doctrine: Minervini canonical, TraderLion practice

The harness deliberately blends two bodies of knowledge, but it never lets them blur together. **Minervini's SEPA is the immutable constitution.** TraderLion's practitioner tactics are admitted only as a **tagged, subordinate practice layer** — 26 documented conflicts are all resolved Minervini-first. Every borrowed threshold carries a **provenance tag** so a practice-layer number can never masquerade as a hard gate:

| Tag | Meaning | Authority |
|---|---|---|
| `[M]` | Canonical Minervini / SEPA | Immutable gate |
| `[MM-Minervini]` | Minervini in the *Momentum Masters* roundtable | Canonical |
| `[TL]` | TraderLion practice-layer tactic | Subordinate; often opt-in |
| `[TL-Kell]` | The 50-day SMA position-trail exception | Explicitly adjudicated |
| `[MM-Ryan]` / `[MM-Zanger]` / `[MM-RitchieII]` | Other *Momentum Masters* speakers | Speaker context only |
| `[heuristic]` | Harness-invented quantifier | Self-demoting, non-canonical |

The `[TL]` advanced entry tactics (in-base entries, moving-average pullbacks, undercut-reclaims) are **opt-in** — inactive unless you explicitly request the practice layer — and even then they never waive the Stage 2 and Trend Template hard gate.

### One vocabulary the harness keeps strict: the moving averages

Because both doctrines put moving averages on the chart, the harness assigns them **non-interchangeable roles**:

- **50 / 150 / 200-day SMA** — used *only* for eligibility and Stage analysis (the Trend Template stack).
- **10 / 21-day EMA** — used *only* for trade management once a position is already eligible.
- **`[TL-Kell]` 50-day SMA position trail** — the single explicit exception where an eligibility-stack average is reused for management.

The same lines may appear on one chart, but swapping their roles would change the meaning of the gate. The harness will not read a 21 EMA touch as an eligibility signal, nor let the SMA stack manage an open trade.

## Where to go next

- To see how these gates run in practice on a named ticker, read [Skills & Usage](Skills-and-Usage.md).
- To understand *why* the method is split into deterministic code plus model judgment, read [Design Principles](Design-Principles.md).
- To run your first analysis, start with the [Quickstart](Quickstart.md).

---
[← Wiki Home](README.md) · [Installation](Installation.md) · [Quickstart](Quickstart.md) · [Architecture](Architecture.md) · [The Minervini Method](The-Minervini-Method.md) · [Skills & Usage](Skills-and-Usage.md) · [Module Substrate](The-Module-Substrate.md) · [Design Principles](Design-Principles.md) · [Contributing](Contributing-and-Extending.md) · [FAQ](FAQ-and-Disclaimer.md)
