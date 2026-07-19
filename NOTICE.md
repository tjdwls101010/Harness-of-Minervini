# Notice on methodology and third-party content

The [MIT License](LICENSE) covers the source code and documentation of this project only. It grants no rights in the underlying investment methodologies.

## Methodology ownership

The **Minervini SEPA / Trend Template** methodology and the **TraderLion** practitioner materials that this project paraphrases remain the intellectual property of their respective authors and organizations. This project independently paraphrases publicly-taught principles for the purpose of building an analysis tool; it does not reproduce the source books.

This project is **not affiliated with, endorsed by, or sponsored by** Mark Minervini, TraderLion, or Investor's Business Daily.

Source book text is never committed to this repository. Raw authoring material lives only in the git-ignored `.tmp/` directory, and every committed reference paraphrases principles rather than quoting them, because this repository is public. See [CONTRIBUTING.md](CONTRIBUTING.md) for the rule that binds contributors.

## Third-party data sources

The harness reads live market data at runtime from three sources, each subject to its own terms:

| Source | Supplies | Reached via |
|---|---|---|
| Yahoo Finance | Prices, financials, earnings | the `yfinance` package |
| Finviz | Market breadth | an HTML scrape of the public homepage |
| `ibd-rs-rating` | Relative-strength ratings | the package's hosted backend |

You are responsible for ensuring your use of these sources complies with their respective terms of service. The Finviz path in particular is an HTML scrape of a public page, not a licensed API, and it may break or be rate-limited without notice.

"IBD" and "Investor's Business Daily" are trademarks of their owner. The `ibd-rs-rating` package produces an IBD-*style* relative-strength rating; the harness labels it as such and does not present it as a proprietary IBD feed.

## Not financial advice

This software is an analysis and education tool. It is not investment, financial, legal, or tax advice, and it is not a recommendation to buy or sell any security. See the full disclaimer in [README.md](README.md#disclaimer).
