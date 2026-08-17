# Security Policy

## Reporting a vulnerability

Do not report security vulnerabilities in a public issue. Use [GitHub Private Vulnerability Reporting](https://github.com/tjdwls101010/Harness-of-Minervini/security): open the repository's Security tab, choose **Report a vulnerability**, and include the affected commit or version plus reproduction steps.

The maintainer aims to acknowledge a report within 7 days and provide a status update within 30 days. These are good-faith targets for a personal open-source project, not a service-level agreement. There is no bug bounty.

## Supported versions

| Version | Supported |
|---|---|
| 2.x and the default branch | Yes |
| 1.x and older | No; v1 remains available only for historical recovery. |

## Security boundary

Harness of Minervini runs locally as the current user. It has no hosted application, inbound service, user accounts, or project-managed credentials. It does make outbound requests, parse untrusted provider data, cache responses, write optional chart artifacts, and maintain an explicit local research ledger.

In-scope security issues include dependency vulnerabilities in the exact pins; unsafe parsing or deserialization of Yahoo, SEC, Nasdaq Trader, Finviz, or `ibd-rs-rating` responses; cache or ledger path traversal; SQL injection; arbitrary file overwrite through chart or export paths; symlink or atomic-write flaws; secret leakage; and permission configurations that authorize commands beyond the declared pipeline and bootstrap boundary.

The provider cache defaults to the ignored `.state/cache` directory and uses JSON rather than pickle. The research ledger defaults to `.state/research-ledger.sqlite3`. Chart artifacts default to `.artifacts`. A vulnerability that turns any of these local data formats or caller-controlled paths into code execution or an unintended write is in scope.

Out of scope are inaccurate investment conclusions, losing trades, stale or missing upstream market data, provider rate limits or outages, and behavior that requires an attacker to already possess arbitrary local code execution as the same user. Running an agent with its permission system disabled also falls outside the project's security guarantee.

## Operational guidance

- Bootstrap from the repository root with `bash scripts/bootstrap.sh`; exact dependency pins mean security updates require an explicit pin change and bootstrap rerun.
- Use `scripts/.venv/bin/python scripts/pipeline health` for an offline runtime check and leaf `--help` for offline command documentation.
- Treat `.state` and `.artifacts` as sensitive local research data even though git ignores them.
- Use `--no-cache` for a fresh diagnostic; it bypasses both reads and writes.
- Do not place credentials or book corpora in tracked files. `.tmp/` is a protected, ignored build-time source directory.
