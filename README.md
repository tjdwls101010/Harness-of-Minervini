# Harness of Minervini

A Claude Code project harness for disciplined US-stock momentum analysis in the Minervini SEPA tradition. It supports market and leadership scans, single-ticker buy/sell/hold analysis, and reviews of completed trades. It does not prescribe portfolio allocations or position sizes.

## Setup

From the repository root, run:

```bash
bash scripts/bootstrap.sh
```

This creates the ignored `scripts/.venv` environment, installs the pinned free data libraries, and verifies the analysis modules. Precise market values come from those modules rather than model memory. A thin user-scoped cache keeps repeated calls consistent within a market session; use a module's `--no-cache` flag when a fresh diagnostic is required.

Open the repository in Claude Code and approve workspace trust. Project permission rules, including the narrow module-command allowlist, become active only after trust is granted.

## Use

Ask in natural language. Claude routes the request by intent:

- Market regime, breadth, sector or industry strength, leader discovery, and watchlists use `market-scan`.
- A named ticker's prospective buy, entry timing, setup, sell, hold, or re-entry question uses `ticker-analysis`.
- A review or post-mortem of completed trades uses `trade-review`.

For the fixed market-to-watchlist sweep, run:

```text
/screen
/screen AAPL MSFT --max-candidates 2
```

The workflow reads the regime, qualifies candidates in parallel, and returns `PROCEED`, watch/incomplete, and `AVOID` buckets. `PROCEED` clears only the deterministic hard gate; it is not a buy recommendation.

Dynamic Workflows require Claude Code 2.1.154 or newer and a paid plan. On Pro, enable the feature in `/config`; Claude Code asks for launch approval when needed. If the workflow is unavailable, ask for a market scan and Claude follows the sequential fallback in `market-scan`.

## Permission safety

The project denies edits under `.tmp/` in normal Claude Code permission modes because that directory contains non-runtime source material. Do not use `--dangerously-skip-permissions` on the real repository: that flag bypasses project permission enforcement, including the `.tmp/` deny rule. Validation uses it only inside disposable isolated copies.
