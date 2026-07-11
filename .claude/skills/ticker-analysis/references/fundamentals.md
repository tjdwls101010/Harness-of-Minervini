# Fundamentals, Catalysts, and Leadership

Use this reference only after a prospective buy has earned a deeper look through the Stage 2 and Trend Template gate. Fundamentals cannot rescue a failed technical gate, and a fundamental pass is never a standalone trade verdict.

A VCP-qualified Power Play is the sole permitted exception that may proceed without verified fundamentals. Label the exception explicitly; it still requires technical eligibility, constructive price and volume, market alignment, and intact risk controls.

## Evidence boundary

- Obtain every precise market or financial number and every module-covered date, including earnings dates, from the repository's `scripts/` modules. Never fill a missing quantitative value from memory or WebSearch.
- Use WebSearch only for current catalyst, company, industry, and competitive narrative, including the timing of a narrative event. Cite the narrative source, distinguish fact from inference, and do not use a web number as a substitute for unavailable module evidence.
- Retry a failed module once. If it still fails, mark the affected item `unavailable`; missing evidence is neither a pass nor a fail.
- Preserve module provenance and data-quality fields in the analysis. A neat narrative does not improve weak or incomplete underlying data.
- Use `--no-cache` only when a genuinely fresh diagnostic is necessary; otherwise same-session values keep the review internally consistent.

The primary evidence calls are:

```text
scripts/.venv/bin/python scripts/modules/earnings_acceleration.py acceleration TICKER
scripts/.venv/bin/python scripts/modules/earnings_acceleration.py code33 TICKER
scripts/.venv/bin/python scripts/modules/earnings_acceleration.py surprise TICKER
scripts/.venv/bin/python scripts/modules/earnings_acceleration.py revisions TICKER
scripts/.venv/bin/python scripts/modules/earnings_acceleration.py margin TICKER
scripts/.venv/bin/python scripts/modules/earnings_acceleration.py valuation TICKER
scripts/.venv/bin/python scripts/modules/actions.py get-earnings-dates TICKER --limit 12 --days-until
scripts/.venv/bin/python scripts/modules/info.py get-info-fields TICKER sector industry marketCap forwardPE trailingPE returnOnEquity
```

Call additional `info.py`, `actions.py`, price/volume, and chart modules only when the checklist requires their evidence. Do not hand-calculate a missing deterministic metric.

## Classify the company before judging it

The first fundamental decision is one of six categories. State the category, the evidence, and any competing category before applying a model, because the wrong category makes otherwise correct numbers misleading.

### 1. Market leader

- Look for an industry sales-and-profit rank near the top one to three, expanding share, and a defensible advantage in a market large enough to support continued scaling.
- EPS growth of at least 20% is the baseline; the best leaders can sustain roughly 35-45% or more during their strongest years.
- Ask what the competitive advantage is and whether the business model can be replicated at much larger scale.
- For a cookie-cutter retail or restaurant leader, apply the store-economics sub-model, because store-count growth outrunning demand marks the end of the growth curve: same-store-sales comps around 10%+ are healthy while 25-30%+ is unsustainable and deceleration below the band is a topping tell; more than roughly 100 net new stores per year is an over-expansion red flag; validate scalability by demonstrated success across regions and compare sales per square foot with peers; and discount franchise-heavy new-store earnings as lower quality. Starbucks in 2006 opened about 1,102 more stores than the prior year, topped, and fell roughly 82% over the next two years.

### 2. Top competitor

- A second-place company can benefit from the leader's group and can outperform while the leader consolidates; it need not be the objectively better company.
- Compare earnings, sales, margins, relative price strength, and scalability with the leader rather than accepting a cheaper multiple as proof of quality.
- Watch disruptive new competitors and IPOs. Capital can rotate away from an incumbent before the incumbent's reported results show the damage.

### 3. Institutional favorite

- Treat a heavily followed blue chip with low-to-mid-teens EPS growth as a different opportunity from an emerging leader.
- A sharp post-correction interval can be useful, but familiarity and sponsorship alone do not imply superperformance potential.

### 4. Turnaround

- Require at least two strong EPS quarters, or one exceptional quarter that restores trailing-twelve-month EPS near or above the old peak.
- Prefer recent two or three quarters near or above 100% growth, margins at new highs, and a step-change from weak three- and five-year growth rates.
- Demand both fundamental strength and price strength. Discount easy comparisons, cost-cutting-only gains, and headline growth that lacks sales confirmation.
- Inspect cash burn, debt, margin recovery, and whether the improvement can persist after the depressed comparison period ends.

### 5. Cyclical

- Use the inverse P/E cycle instead of the growth-stock model. Near a cyclical bottom, depressed earnings can make P/E look high; near an earnings peak, record profits can make P/E look deceptively low.
- Falling earnings, dividend cuts, and bad news can accompany a bottom; rising earnings, dividend increases, and uniformly good news can accompany a top.
- Never call a cyclical cheap merely because record earnings produce a low P/E. Determine where earnings, dividends, and the news direction sit in the cycle.

### 6. Past leader or laggard

- A former leader in Stage 4 is not made investable by a large decline or low P/E. Price may be discounting future deterioration that reported numbers have not revealed.
- A low-multiple laggard within a strong group is usually lagging for a reason; late catch-up rallies are not equivalent to leadership.
- Ask what sellers may know that has not yet appeared in public results, and require renewed price and fundamental leadership rather than reputation.
- Read a fresh brokerage upgrade or raised price target on such a name as a red flag rather than support — often a short-candidate marker, because institutions distribute before the sell-side turns cautious. See `sell.md` for the dated rule and the CMG 2012 precedent.

Categories can change as a company matures. Record the current category and the evidence that would move it to another category.

## Leadership and group context

- Expect a new advance to concentrate in roughly three to ten leading industry groups rather than spread evenly across the market.
- Compare the candidate with the top two or three stocks in its group on earnings, sales, margins, and relative price strength.
- More than 60% of historical superperformers advanced with an industry group, so group participation is meaningful context but not a substitute for ticker evidence.
- Detect group strength bottom-up through a growing count of group members near 52-week highs, especially as the market leaves a correction.
- A major leader's abnormal breakdown is an early warning for peers, suppliers, and customers. Recheck the whole group before explaining the leader away as company-specific noise.
- Check whether a disruptive entrant, new business model, or category shift is redirecting institutional attention from the incumbent to a newer leader.
- Distinguish an expanding market from a saturated replacement market. A stale “growth” label cannot substitute for current penetration and demand evidence.

## Catalyst detective work

A catalyst is one of SEPA's five required elements. It may be less obvious than the chart, so investigate it deliberately rather than writing “strong story” after the fact.

1. Identify the discrete change: a new product, regulatory approval, major contract, new chief executive, new business model, or demand inflection.
2. Date the change and separate an active catalyst from an old story already reflected in expectations.
3. Explain the causal path from the change to future sales, earnings, margins, estimate revisions, and institutional demand.
4. Test scalability: ask whether the addressable market is large relative to the company and whether the model can repeat across customers, products, or locations.
5. Check whether analysts or institutions may still misunderstand or under-cover the change; unfamiliarity can be constructive, but it is not evidence by itself.
6. Compare the candidate with affected competitors and group members. A catalyst should create observable relative strength, estimate movement, or demand somewhere in the chain.
7. State what would refute the catalyst thesis, such as delayed adoption, a failed launch, adverse guidance, margin erosion, or a competitor taking the economics.

Use WebSearch to establish the current narrative and its timing, then return to module evidence to test whether the claimed effect appears in the numbers and price/volume response.

## Earnings engine

The operating chain is surprise, upward estimate revisions, higher institutional valuation models, institutional buying, post-earnings drift, and later momentum demand. Each earnings screen exists to detect this process early; a number without this causal context is not the thesis.

### Growth and acceleration screen

- Require recent quarterly EPS growth of at least 20-25% year over year. Typical leaders often show 30-40% or more, and a strong bull market justifies raising the recent two-to-three-quarter standard toward 40-100% or more.
- Inspect the current quarter and the preceding two or three quarters; four to six consecutive strong quarters increase confidence.
- Prefer sequentially rising year-over-year EPS growth rates. Acceleration, not merely a high absolute rate, characterized most historical maximum winners.
- Confirm EPS with strong and accelerating sales. Earnings built only from taxes, cost cuts, plant closures, or accounting choices have short legs.
- Smooth noisy sequences with two-quarter rolling averages across four, six, and eight quarters. The desired signal is persistent improvement, not one flattering comparison.
- Compare current quarterly and annual growth with the company's own three- and five-year rates to find a genuine step-change.
- Require strong annual EPS and look for a breakout above the prior two-to-four-year earnings range, with evidence that acceleration can continue over the next one or two quarters and the next fiscal year.
- Treat roughly +5% estimate revisions as meaningful positive change and roughly -5% as meaningful negative change. Check whether current-quarter and fiscal-year estimates improved over the last 30 days. The direction is asymmetric: the absence of an upward revision is weaker evidence, not an automatic disqualification, whereas a meaningful downward revision (roughly -5% or more) is an affirmative red flag. Under the harness's no-trade default, do not let flat or missing upgrades read as a failed fundamental leg.
- Use ROE near or above 15-17% as supporting evidence within the same industry, not as a substitute for growth, margins, or price confirmation.
- Evaluate how much earnings are growing, how long that growth can persist, and how certain the path is.

### Code 33

Code 33 is simultaneous acceleration in EPS, sales, and net profit margin across three consecutive quarterly improvements. All three legs must strengthen together; one strong series cannot waive another.

Use the module's `code33_status`, component series, quarter counts, data-quality fields, and margin basis. If operating margin is the fallback, disclose that it is weaker than canonical net-margin evidence; do not recreate or infer the status when history is insufficient.

The doctrine requires directional margin expansion. Any numeric minimum margin-change parameter exposed by the module is a tunable implementation heuristic, not an extra canonical gate.

Code 33 is powerful evidence of demand and operating leverage, but it still sits inside technical eligibility, catalyst, market, entry, and risk convergence.

### Surprise, revisions, and reaction

- Discount one-to-three-cent “penny beats”; they can reflect expectation management rather than new information.
- Inspect at least the recent two reports for meaningful positive surprises and estimate changes. The “cockroach effect” means a genuine surprise often repeats in the company and can foreshadow related group surprises; negative surprises can repeat as well.
- Treat the first or second earnings gap as the freshest evidence, not as direct permission to enter. Do not chase a missed first reaction: institutional accumulation can create post-earnings drift over subsequent weeks or months, while later repeated gaps deserve more skepticism.
- Read the reaction in three parts: the initial response, the stock's resistance to subsequent profit-taking, and its resilience in recovering from the pullback.
- Require that drift to resolve into a structural daily/weekly entry such as a new base, pivot, or documented tennis-ball recovery; Day 1-2 intraday gap tactics remain outside this harness.
- Treat the tape as the final verdict on unknowable embedded expectations. Abnormal weakness after objectively good news carries more weight than the favorable headline.
- An approximately 15% post-earnings decline followed by an inability to rally is a serious deterioration flag even when the report appears strong.
- Track earnings dates for the candidate, holdings, watchlist names, and close peers because one report can reveal the group's demand and expectation cycle.

### Guidance forensics

- Require a meaningful beat together with positive near-term guidance for the next quarter or current fiscal year before treating the report as clean positive-surprise evidence.
- A beat after management lowered guidance and pulled estimates down is a lowered-bar beat, not clean positive surprise evidence.
- Discount vague long-range optimism when near-term conditions are weak. “Next year will improve” without near-term confirmation is spin rather than useful guidance.
- A guidance increase is high-confidence evidence only if price accepts it. A fast reversal from raised to lowered guidance is a flip-flop warning; one documented case reversed within roughly eleven trading days.
- Compare each new statement with prior guidance, consensus movement, and subsequent price behavior. Read changes, not isolated wording.

### Quality and balance-sheet forensics

- Remove one-time and non-operating gains before judging core growth. Repeated “one-time” costs are recurring economics and weaken earnings quality.
- Require sales and margin confirmation. Compare net margin with the industry and prefer improvement driven by demand and pricing power over temporary cost or commodity benefits.
- Examine differential disclosure when available: a large gap between accrual earnings and cash-oriented tax or regulatory evidence, or strong reported profit with unusually little tax, is a warning.
- Compare inventory growth with sales growth and split inventory into raw materials, work in process, and finished goods. Finished goods growing much faster than the other components can signal unsold product.
- Raw-material accumulation can be constructive only when there is a credible explanation and subsequent sales acceleration confirms it.
- If both inventory and receivables grow at least twice as fast as sales without a credible explanation, flag `double trouble`: markdowns, write-offs, or a disappointing report may follow.
- Apply an explanation test before condemning inventory. Expansion inventory or advantageous raw-material purchases can be constructive, while unexplained finished-goods accumulation is not.
- Treat a fad as a potentially powerful but finite growth cycle. It is eligible only with an exit plan defined before entry; never mistake temporary hypergrowth for durable demand.

### Earnings maturity and deceleration

Place the company in the sequence from value, to surprise, to upward revisions, to EPS momentum, to widely recognized growth, to deceleration, negative surprise, and eventual value status.

Buy analysis belongs in the technically eligible portion where growth is strong and accelerating. Once the story is universally recognized, institutions may distribute shares before reported growth looks weak.

Measure deceleration against the company's own prior trend. The first material slowdown matters more than the first formal miss; a move from 50-60% growth to 20-30% can be severe despite still-positive headlines. Dell stepped down from roughly 80% EPS growth in 1995-97 to 65% in 1998 to 28% in 1999 — still a respectable absolute rate, yet the deceleration relative to its own trend preceded the 2000 top and a subsequent decline of about 80%.

Price can lead earnings in both directions. Respect abnormal weakness before waiting for the public explanation or a later negative report.

## Valuation de-biasing

- Never reject, sell, or cap a candidate solely because P/E or PEG is high. Historical maximum winners often began at 30-40 times earnings or more, and one winner sample ranged from 8.6 to 223 times.
- Do not place a P/E ceiling in screening. Use P/E only as a gauge of expectations and market psychology.
- Record the P/E near the original breakout. At roughly twice that baseline, increase vigilance; at roughly 2.5-3 times the baseline, combine expansion with EPS deceleration or price weakness to escalate late-cycle risk.
- A very low P/E near 3-5 times, or far below the industry, becomes a red flag when price is also near a 52-week low. The market may be discounting an earnings collapse that trailing numbers have not captured.
- Never use “it is cheap now” as a buy or hold reason, and never average down into a falling thesis.
- Reject broken-leader logic. A former leader down 70-75% can lose most of the remaining capital again because every new buyer still has 100% of their invested capital at risk.
- Apollo shows why high P/E alone is not the risk: its price rose about 200% while P/E stayed near 60 because earnings kept pace.
- The Crocs pair shows the opposite readings of price and P/E: buying near its highest P/E preceded roughly a 700% rise over about twenty months, while buying near its lowest P/E preceded an approximately 99% loss within a year.
- Growth persistence, estimate revisions, catalyst, and demand determine whether expectations can be met. Valuation expansion measures recognition; it does not replace those drivers.

## Twelve-item final-candidate review

Use this review only for a candidate that has earned the final manual stage. Record `strong`, `mixed`, `weak`, or `unavailable` for each item, cite the supporting module or narrative evidence, and add one sentence explaining why the evidence matters.

1. **Reported earnings and sales:** Are the latest reported results strong, recurring, and supported by both bottom-line and top-line growth?
2. **Earnings and sales surprise history:** Are meaningful beats repeating, or are the results penny beats, lowered-bar beats, or negative surprises?
3. **EPS growth and acceleration:** Is year-over-year EPS above the relevant floor and improving across quarters and smoothed windows?
4. **Sales growth and acceleration:** Does revenue confirm the earnings trajectory and show durable demand?
5. **Company guidance:** Is near-term guidance constructive, consistent, and accepted by price rather than spun or reversed?
6. **Analyst estimate revisions:** Are current-quarter and fiscal-year estimates moving upward by a meaningful amount over the recent 30-day window?
7. **Profit margins:** Are margins expanding for demand-driven reasons, and does Code 33 or related evidence support operating leverage?
8. **Industry and market position:** Which of the six categories applies, what is the company's rank and competitive advantage, and is that category improving or deteriorating?
9. **Potential catalyst:** What discrete change can drive future surprise and institutional demand, and what evidence would refute it?
10. **Performance versus sector peers:** Is the candidate among the top two or three group names, and is the group itself producing expanding leadership?
11. **Price and volume analysis:** Does deterministic price/volume evidence confirm the fundamental story, or is abnormal behavior contradicting it?
12. **Liquidity risk:** Is trading liquidity sufficient for clean execution without distorting the intended entry and exit?

Do not reduce the twelve items to a blind sum. A known technical-gate failure rejects a prospective buy, missing required evidence makes the review incomplete, and probability convergence across fundamentals, price/volume, market, entry, and risk outranks a high checklist count.

## Fundamental conclusion

Finish with the category, catalyst, earnings phase, Code 33 state, guidance and balance-sheet risks, valuation-expectation state, peer leadership, and the twelve-item evidence table.

Classify the fundamental leg as `supports convergence`, `does not support convergence`, or `incomplete`. Then return it to the full ticker workflow; fundamentals alone cannot authorize a buy, sell, or hold verdict.
