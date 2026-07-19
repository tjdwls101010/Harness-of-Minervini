# Security Policy

## Reporting a vulnerability

**Please do not report security issues in public GitHub issues.** A public issue discloses the problem to everyone before a fix exists.

Report privately through **GitHub Private Vulnerability Reporting**:

1. Go to the [Security tab](https://github.com/tjdwls101010/Harness-of-Minervini/security) of this repository.
2. Click **Report a vulnerability**.
3. Describe the issue, the affected version or commit, and how to reproduce it.

You will get an acknowledgement within **7 days** and a status update within **30 days**. This is a personal open-source project maintained in spare time, so please treat those as good-faith targets rather than a commercial SLA. If a report goes unacknowledged past 30 days, opening a non-specific public issue asking the maintainer to check the Security tab is a reasonable escalation.

There is no bug bounty for this project.

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x | Yes |
| < 1.0 | No |

Fixes land on the default branch and ship in the next release.

## What this project's attack surface actually is

Being specific here saves everyone time, because this repository is not a service and several common vulnerability classes simply do not apply.

**Harness of Minervini runs entirely on your own machine.** It has no server, no hosted component, no user accounts, no authentication, no database, and it stores no credentials or secrets. It accepts no inbound network connections. It is a set of Python CLI modules plus Claude Code configuration, and everything it does runs as your local user with your local permissions.

That leaves a real but narrow surface:

- **Third-party dependency vulnerabilities.** `scripts/requirements.txt` pins eight packages exactly (`yfinance`, `pandas`, `numpy`, `lxml`, `requests`, `certifi`, `ibd-rs-rating`, `mplfinance`). A vulnerability in any of them reaches this project, and exact pins mean an upstream fix does not arrive until we bump the pin. Reports that a pinned version carries a known CVE are in scope and welcome.
- **Untrusted data from live sources.** Every run pulls remote data — Yahoo Finance via `yfinance`, an HTML scrape of the Finviz homepage parsed with `lxml`, and the `ibd-rs-rating` backend. A parsing or deserialization flaw reachable from a hostile or compromised response is in scope. The Finviz path is the most exposed, because it parses attacker-influenceable HTML rather than a typed API.
- **The local cache.** Cached payloads are written under `${MINERVINI_CACHE_DIR:-~/.cache/minervini-harness}` as JSON, and reads decode structured values (including pandas frames) back out. Anything that turns a cache file into code execution, or that lets a path be written outside the cache root, is in scope.
- **Chart output paths.** `chart_render.py` writes PNGs to a caller-supplied `--out`. Path handling flaws there are in scope.
- **The permission configuration.** `.claude/settings.json` ships a deliberately narrow allowlist and a project-root-anchored `Edit(/.tmp/**)` deny rule. A way to make Claude Code execute commands outside that allowlist, or to defeat the deny rule's root anchoring, is in scope.

### Out of scope

- **Bad market analysis, wrong verdicts, or losing trades.** The harness is an analysis and education tool, not financial advice; an inaccurate verdict is a correctness matter, not a security vulnerability. File it as a normal issue. See the [disclaimer](README.md#disclaimer).
- **Stale, wrong, or missing third-party market data.** Upstream data-quality problems belong to the upstream source. By design the modules report such evidence as `unavailable` rather than guessing.
- **Rate limiting or outages** from Yahoo Finance, Finviz, or the `ibd-rs-rating` backend.
- **Anything that requires an attacker to already have local code execution as your user.** At that point they can read the cache, edit the modules, and run the interpreter directly regardless of what this project does.
- **Running Claude Code with `--dangerously-skip-permissions`.** That flag bypasses the project's own deny rule and is explicitly prohibited on this repository; issues that depend on it are not vulnerabilities in this project.

## Notes for anyone running this

- The bootstrap script creates a git-ignored virtual environment and installs the exact pins. Re-running `bash scripts/bootstrap.sh` after a pin bump is how you pick up a dependency security fix.
- The cache holds only market data. Deleting `~/.cache/minervini-harness` at any time is safe and costs nothing but a re-fetch.
- `--help` is offline by contract and makes no network call, so it is always safe to run when you are unsure what a module does.
