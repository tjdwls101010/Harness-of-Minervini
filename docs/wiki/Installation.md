# Installation

Get the deterministic substrate built and Claude Code trusted so the harness is ready for your first analysis.

This page walks you from a fresh clone to a working install: what you need, what `bash scripts/bootstrap.sh` actually does, why workspace trust matters, where live data and the cache come from, and how to recover when something goes wrong. For your first prompts once installed, continue to the [Quickstart](Quickstart.md).

## Requirements

| You need | Why |
|---|---|
| [Claude Code](https://claude.com/claude-code) | The harness *is* a Claude Code project — the constitution, [skills](Skills-and-Usage.md), agent, and workflow only exist inside it. Version **2.1.154+** is required for the `/screen` workflow. |
| **Python 3.10+** | The deterministic [module substrate](The-Module-Substrate.md) under `scripts/` runs on a local virtual environment that `bootstrap.sh` builds. |
| **Internet access** | Every precise market number is fetched live at runtime — there is no bundled market database. See [Data sources](#data-sources-no-local-database) below. |

You do **not** need to pre-provision any database, API key, or market-data account. The data sources the harness uses are either keyless or handled by a pinned Python package.

## 1. Clone the repository

```bash
git clone https://github.com/tjdwls101010/Harness-of-Minervini.git
cd Harness-of-Minervini
```

All paths in this wiki resolve from this repository root. The canonical way to call the modules is always root-relative — you never `cd scripts`.

## 2. Bootstrap the deterministic substrate

From the repository root:

```bash
bash scripts/bootstrap.sh
```

This one script does three things:

1. **Creates an isolated virtual environment.** By default it lives at `scripts/.venv/`, which is git-ignored (alongside `.tmp/` and `__pycache__/`) so it never enters version control. If a usable interpreter already exists there, it is reused.
2. **Installs pinned dependencies.** It runs `pip install -r scripts/requirements.txt` into that venv. The pins are exact for reproducibility:

   ```text
   yfinance==1.5.1
   pandas==3.0.3
   numpy==2.5.1
   lxml==6.1.1
   requests==2.34.2
   certifi==2026.6.17
   ibd-rs-rating==0.4.0
   mplfinance==0.12.10b0
   ```

3. **Smoke-checks imports.** It imports every module in `scripts/modules/` plus the `pipeline` package and its submodules, failing loudly (exit 1) if any import breaks. On success you see a line like `Import smoke passed for 16 modules and the pipeline package.` This confirms the interpreter, the dependencies, and the module tree all line up before you rely on them.

### The `$MINERVINI_VENV` override

If you want the environment somewhere other than `scripts/.venv/` — a shared cache volume, a different disk — set `MINERVINI_VENV` before bootstrapping:

```bash
MINERVINI_VENV=/opt/envs/minervini bash scripts/bootstrap.sh
```

Bootstrap builds the venv there, then creates a symlink at the canonical `scripts/.venv/bin/python` pointing to it. That preserves the single invocation path the whole harness expects, so every documented command still works verbatim:

```bash
scripts/.venv/bin/python scripts/pipeline qualify AAPL
scripts/.venv/bin/python scripts/modules/vcp.py detect NVDA
```

`scripts/.venv/bin/python` is the canonical interpreter referenced throughout [the module substrate](The-Module-Substrate.md); treat it as the fixed entry point regardless of where the environment physically lives.

## 3. Open in Claude Code and approve workspace trust

Open the cloned folder in Claude Code and **approve workspace trust when prompted.**

This step is not cosmetic. The project ships narrow permission rules in `.claude/settings.json` — an allowlist that lets Claude run the harness's own commands without a prompt for each one:

```json
"allow": [
  "Bash(scripts/.venv/bin/python *)",
  "Bash(bash scripts/bootstrap.sh)",
  "Bash(git status)",
  "Bash(git diff *)"
]
```

Project-scoped permission rules like these **activate only after you trust the workspace.** Until then Claude Code will not apply the project's settings, so the smooth module-calling experience the harness is designed around won't be in effect. Trusting the workspace is what turns the checked-in configuration into live behavior.

## Data sources (no local database)

All precise numbers are pulled live at runtime — there is **no local market database to seed or maintain.** Three sources feed the modules:

| Source | Supplies | How it's reached |
|---|---|---|
| **yfinance** | Prices, financials, earnings | Cached ticker proxy |
| **Finviz** homepage scrape | Market breadth | `utils.cached_call`, source `finviz` |
| **`ibd-rs-rating`** package (Neon backend, ~4,600 US stocks) | Relative-strength ratings | `rs_ranking.call_backend`, source `ibd-rs-rating` |

Because everything is fetched on demand, a working internet connection is part of the requirements. On a source failure the modules report that evidence as `unavailable` rather than guessing — the harness never fabricates a market number.

## The same-session cache

To keep iterative analysis fast and reproducible, eligible live reads pass through a transparent read-through cache. You don't manage it, but it helps to know where it lives:

- **Location:** `~/.cache/minervini-harness` by default. Override the root with `$MINERVINI_CACHE_DIR`:

  ```bash
  export MINERVINI_CACHE_DIR=/path/to/cache
  ```

- **Session key:** entries are keyed to the **last completed US trading session**, not your local calendar day, so repeated calls (even from a different time zone) stay on one coherent market snapshot.
- **Freshness:** during the regular session, price endpoints bypass the cache or use a TTL of at most 15 minutes, while non-price data keeps the completed-session lifetime. Every module also accepts `--no-cache` to bypass reads and writes entirely when you need a fresh diagnostic.

## Verify the install

A quick offline check that the interpreter and CLI are wired up — `--help` is fully offline by contract, so this needs no network:

```bash
scripts/.venv/bin/python scripts/modules/vcp.py --help
scripts/.venv/bin/python scripts/pipeline qualify AAPL
```

The first prints the module's usage; the second runs a real Stage-2 + Trend-Template eligibility gate on AAPL (this one needs internet). If both return structured output, you're ready for the [Quickstart](Quickstart.md).

## Troubleshooting

**"No such file" / missing interpreter at `scripts/.venv/bin/python`.**
The environment was never built, was moved, or a `$MINERVINI_VENV` symlink target went stale. Re-run `bash scripts/bootstrap.sh` — it recreates the venv and the canonical symlink and re-runs the import smoke test.

**An import fails or a module errors on startup.**
Same fix: re-run `bash scripts/bootstrap.sh`. The smoke check will surface the exact failing module and exception so you can see what broke.

**A live source rate-limits or times out.**
The modules are built to survive transient source failures: the same-session cache serves a consistent snapshot, and the harness's contract is to **retry a failed module once, then report that evidence as `unavailable`** rather than fabricate a value. If you're hammering a source during development, prefer running *with* the cache (the default) and reserve `--no-cache` for when you specifically need a fresh read.

**Don't use `--dangerously-skip-permissions` on this repository.**
It is prohibited here because it bypasses the project's permission rules — including the deny rule `Edit(/.tmp/**)` that keeps Claude out of the raw prototype and book-corpus material in `.tmp/` (which is not runtime doctrine). Approve workspace trust instead; the checked-in allowlist already covers the commands the harness needs.

---

*Installation is setup only — nothing here is a buy/sell recommendation. The harness is an analysis and education tool; see the [FAQ & Disclaimer](FAQ-and-Disclaimer.md).*

---
[← Wiki Home](README.md) · [Installation](Installation.md) · [Quickstart](Quickstart.md) · [Architecture](Architecture.md) · [The Minervini Method](The-Minervini-Method.md) · [Skills & Usage](Skills-and-Usage.md) · [Module Substrate](The-Module-Substrate.md) · [Design Principles](Design-Principles.md) · [Contributing](Contributing-and-Extending.md) · [FAQ](FAQ-and-Disclaimer.md)
