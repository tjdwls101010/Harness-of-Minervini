# Notice on methodology and third-party content

The [MIT License](LICENSE) covers this repository's code and documentation only. It grants no rights in the underlying investment methodologies, trademarks, market data, or third-party services.

## Methodology ownership

The Minervini SEPA and Trend Template methodology and the TraderLion practitioner materials remain the intellectual property of their respective authors and organizations. This project independently normalizes and paraphrases ideas for an analysis tool; it does not reproduce the source books and is not affiliated with, endorsed by, or sponsored by Mark Minervini, TraderLion, or Investor's Business Daily.

Raw authoring corpora live only in the git-ignored `.tmp/` directory and are never consulted during market analysis. Runtime skills embody normalized doctrine without book quotations or bibliographic payload. Maintainer-facing provenance is retained in the doctrine registry for audit.

## Third-party data sources

| Source | Use in the harness |
|---|---|
| Yahoo Finance through `yfinance` | Completed price and volume history plus current mutable classification. |
| US Securities and Exchange Commission | Filed company facts and submissions, filtered by filing time. |
| Nasdaq Trader | Current listed-security identity and eligibility scope. |
| Finviz | Current market-breadth HTML snapshot. |
| `ibd-rs-rating` | Cross-sectional IBD-style relative-strength ratings from the package's hosted backend. |

Each source is subject to its own terms, availability, corrections, and rate limits. Users are responsible for ensuring their use complies with those terms. Finviz is parsed from a public HTML page rather than a licensed API. Nasdaq and Yahoo classifications are current mutable data and are not presented as historical snapshots.

The user-maintained `ibd-rs-rating` package is the harness's sole cross-sectional RS source. It is an unofficial IBD-style implementation; the harness does not present it as Investor's Business Daily's proprietary feed or reproduce its calculation.

“IBD” and “Investor's Business Daily” are trademarks of their owner. Yahoo, Finviz, Nasdaq, SEC, Minervini, and TraderLion names and marks belong to their respective owners.

## Not financial advice

This software is an analysis and education tool, not investment, financial, legal, or tax advice and not a recommendation to buy or sell any security. See the full [README disclaimer](README.md#disclaimer).
