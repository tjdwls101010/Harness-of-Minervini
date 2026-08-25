from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Capability:
    name: str
    summary: str
    inputs: dict[str, Any]
    output: str
    prerequisites: list[str]
    side_effects: list[str]
    errors: list[str]
    limitations: list[str]
    status_meanings: dict[str, str]
    exit_codes: dict[str, str]
    examples: list[str]
    # Dotted paths under `data` that the shared compact filter would strip by name but that are
    # this capability's answer rather than its supporting detail. `anchors` is detail inside a
    # setup's segmentation and is the entire output of ticker.swings, so the exception has to
    # name a place: keyed on the name alone it also kept the verbose chains under `sensitivity`.
    compact_keeps: frozenset[str] = frozenset()

    @property
    def side_effecting(self) -> bool:
        return bool(self.side_effects)

    @property
    def schema_id(self) -> str:
        return f"https://harness.minervini.dev/schemas/v2/{self.name}.schema.json"

    def listing(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "schema_id": self.schema_id,
            "side_effecting": self.side_effecting,
        }

    def description(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "schema_id": self.schema_id,
            "inputs": self.inputs,
            "output": self.output,
            "prerequisites": self.prerequisites,
            "side_effects": self.side_effects,
            "errors": self.errors,
            "limitations": self.limitations,
            "status_meanings": self.status_meanings,
            "exit_codes": self.exit_codes,
            "examples": self.examples,
        }

    def help_epilog(self) -> str:
        status = "\n".join(f"  {name}: {meaning}" for name, meaning in self.status_meanings.items())
        limits = "\n".join(f"  - {item}" for item in self.limitations) or "  - None beyond the shared v2 envelope contract."
        effects = "\n".join(f"  - {item}" for item in self.side_effects) or "  - No explicit user-visible write. Provider-backed commands may use the ignored local cache unless --no-cache is set."
        exits = "\n".join(f"  {code}: {meaning}" for code, meaning in self.exit_codes.items())
        examples = "\n".join(f"  {item}" for item in self.examples)
        prerequisites = "\n".join(f"  - {item}" for item in self.prerequisites) or "  - None."
        return f"Output\n  {self.output}\n\nPrerequisites\n{prerequisites}\n\nTime and data limits\n{limits}\n\nEnvelope status\n{status}\n\nExit codes\n{exits}\n\nSide effects\n{effects}\n\nExamples (run from the repository root)\n{examples}"


def _field(kind: str, description: str, *, required: bool = False, default: Any = None, choices: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": kind, "required": required, "description": description}
    if default is not None:
        result["default"] = default
    if choices is not None:
        result["choices"] = choices
    return result


_AS_OF = _field("date", "Completed US trading session in YYYY-MM-DD form; defaults to the latest completed regular session.")
_FORMAT = _field("enum", "Output detail only; compact preserves verdict, signals, and missing evidence while omitting verbose basis rows.", default="full", choices=["compact", "full"])
_NO_CACHE = _field("boolean", "Bypass both provider-cache reads and writes for this invocation.", default=False)
_EXIT_CODES = {
    "0": "A valid domain envelope was emitted; its status may still be partial, unavailable, or needs_input.",
    "2": "The request or arguments were invalid; stdout contains a needs_input error envelope.",
    "3": "An unexpected internal contract failure occurred; stdout contains an unavailable error envelope.",
}


def _inputs(specific: dict[str, Any] | None = None, *, providers: bool = False, clocked: bool = True) -> dict[str, Any]:
    result = dict(specific or {})
    if clocked:
        result.update({"as_of": _AS_OF, "format": _FORMAT})
    if providers:
        result["no_cache"] = _NO_CACHE
    return result


def _capability(
    name: str,
    summary: str,
    *,
    inputs: dict[str, Any] | None = None,
    output: str = "One v2 JSON envelope with stable top-level keys.",
    prerequisites: list[str] | None = None,
    side_effects: list[str] | None = None,
    errors: list[str] | None = None,
    limitations: list[str] | None = None,
    status_meanings: dict[str, str] | None = None,
    exit_codes: dict[str, str] | None = None,
    examples: list[str] | None = None,
    compact_keeps: tuple[str, ...] = (),  # dotted paths under `data`
) -> Capability:
    return Capability(
        name=name,
        summary=summary,
        inputs=inputs or {},
        output=output,
        prerequisites=prerequisites or [],
        side_effects=side_effects or [],
        errors=errors or ["invalid_request", "provider_unavailable", "internal_error"],
        limitations=limitations or [],
        status_meanings=status_meanings or {"ok": "The requested contract was satisfied."},
        exit_codes=dict(exit_codes or _EXIT_CODES),
        examples=examples or [],
        compact_keeps=frozenset(compact_keeps),
    )


CAPABILITIES = {
    item.name: item
    for item in [
        _capability(
            "capabilities",
            "List every composable public capability without running market analysis.",
            output="The registry name, summary, immutable schema ID, and explicit-write marker for every public capability.",
            status_meanings={"ok": "The complete registry was returned."},
            examples=["scripts/.venv/bin/python scripts/pipeline capabilities"],
        ),
        _capability(
            "describe",
            "Return the machine-readable contract for one capability.",
            inputs={"capability": _field("string", "Exact capability ID returned by capabilities.", required=True)},
            output="Purpose, inputs, schema ID, prerequisites, limitations, status and exit meanings, side effects, errors, and examples.",
            status_meanings={"ok": "The capability exists.", "needs_input": "The capability ID is unknown."},
            examples=["scripts/.venv/bin/python scripts/pipeline describe ticker.setup"],
        ),
        _capability(
            "health",
            "Check deterministic runtime readiness without making an investment judgment, and optionally probe whether providers are reachable.",
            inputs=_inputs({"probe": _field("boolean", "Additionally make one cheap request per probed provider to prove it is reachable; off by default so the default check stays offline.", default=False)}),
            output="Python, doctrine-registry, yfinance, and exact ibd-rs-rating version readiness, plus per-provider reachability when probed.",
            limitations=["Without --probe this checks installed dependencies and local doctrine only; it does not prove that remote providers are reachable.", "--probe makes one real request per probed provider (yfinance, ibd-rs-rating, SEC) and reports why an unreachable one failed rather than guessing; Nasdaq's multi-megabyte security master is deliberately not probed.", "--as-of stamps the envelope but does not alter dependency readiness."],
            status_meanings={"ok": "All required local components are ready, and every probed provider answered.", "partial": "A required local component is missing or mismatched, or a probed provider is unreachable."},
            examples=["scripts/.venv/bin/python scripts/pipeline health", "scripts/.venv/bin/python scripts/pipeline health --probe"],
        ),
        _capability(
            "clock",
            "Resolve the point-in-time boundary shared by every analytical capability.",
            inputs=_inputs(),
            output="The latest completed US regular session, or the validated explicit completed session.",
            limitations=["Future dates, weekends, exchange holidays, and known special exchange closures are rejected.", "The calendar models regular and standard early closes; it is not an intraday trading clock."],
            status_meanings={"ok": "A completed session boundary was resolved.", "needs_input": "The date is malformed or is not a completed US trading session."},
            examples=["scripts/.venv/bin/python scripts/pipeline clock", "scripts/.venv/bin/python scripts/pipeline clock --as-of 2026-08-14"],
        ),
        _capability(
            "doctrine.show",
            "Inspect one normalized doctrine claim used by the deterministic reducers.",
            inputs=_inputs({"claim_id": _field("string", "Exact doctrine claim ID.", required=True)}),
            output="The executable claim, its registered thresholds with each one's role, and separated provenance carrying the source quotations the claim rests on.",
            limitations=["This is runtime doctrine, not a full book transcript or citation browser.", "--as-of stamps the envelope; doctrine content is versioned with the repository rather than market time.", "A threshold's role bounds what it may do: a gate decides pass or fail, a band reports a measurement inside a range the source stated as a range, a marker reports a measurement beside a single value the source named without bounding it, and a reference is never compared with a ticker's measurement at all.", "A claim on the practice layer or attributed to a practitioner other than Minervini may hold a real filter, but that gate reports contrast_pass or contrast_fail and no reducer reads it.", "A claim marked out_of_scope records doctrine this harness may not act on, such as position sizing, and no capability consumes it."],
            status_meanings={"ok": "The claim exists.", "needs_input": "The claim ID is unknown."},
            examples=["scripts/.venv/bin/python scripts/pipeline doctrine show eligibility.standard_trend_template"],
        ),
        _capability(
            "market.snapshot",
            "Measure market regime, breadth, sector and industry leadership, and leading-stock evidence without forcing a bullish score.",
            inputs=_inputs(
                {
                    "trade_traction": _field("enum", "Whether the user's recent pilot trades confirm the observed environment; required for a favorable regime.", choices=["supports", "contradicts", "mixed", "needs_input"]),
                    "leader_limit": _field("integer", "Maximum first-party RS leader observations, from 1 through 100.", default=20),
                },
                providers=True,
            ),
            output="A transparent signal vector, regime judgment, ranked groups, leader observations, missing evidence, and source metadata.",
            limitations=["QQQ versus 21 EMA is context only and cannot authorize risk-on by itself.", "Finviz publishes only a live page, so breadth is a current observation standing in for the completed session; it is context evidence and the envelope discloses how long after the close it was read.", "Breadth is refused outright while a regular session is open, and an uncaptured historical page can never be reconstructed.", "A missing source remains unavailable; no web or proxy number replaces it."],
            status_meanings={"ok": "All requested evidence is available, including trade traction.", "partial": "Some independent sources or breadth sections are unavailable, or an index history stopped before the requested session.", "needs_input": "Trade traction is absent even though provider evidence may exist.", "unavailable": "No market evidence source succeeded."},
            examples=["scripts/.venv/bin/python scripts/pipeline market snapshot --trade-traction mixed", "scripts/.venv/bin/python scripts/pipeline market snapshot --trade-traction supports --leader-limit 40 --no-cache"],
        ),
        _capability(
            "market.candidates",
            "Return a filtered, paginated US common-stock and ADR discovery universe.",
            inputs=_inputs(
                {
                    "limit": _field("integer", "Page size; this controls transport volume, not a recommendation quota.", default=50),
                    "cursor": _field("string", "Opaque cursor returned by the preceding page."),
                },
                providers=True,
            ),
            output="Eligible instruments, a bounded exclusion summary, and pagination metadata including universe-wide recommendation count.",
            limitations=["Nasdaq Trader supplies a current security master, not historical constituents; unsupported historical requests are unavailable.", "ETF, SPAC, shell, OTC, preferred, warrant, and unsupported instruments are excluded; complete reason counts and at most min(limit, 20) representative records keep the response dense.", "Candidate eligibility is not itself a buy recommendation."],
            status_meanings={"ok": "The requested page, including a legitimate empty page, was returned.", "unavailable": "The required security master is unavailable.", "needs_input": "The limit or cursor is invalid."},
            examples=["scripts/.venv/bin/python scripts/pipeline market candidates --limit 50", "scripts/.venv/bin/python scripts/pipeline market candidates --limit 50 --cursor offset:50"],
        ),
        _capability(
            "ticker.qualify",
            "Apply the low-cost Stage 2 and eight-of-eight Trend Template gate, or the bounded recent-IPO Primary Base route.",
            inputs=_inputs(
                {
                    "ticker": _field("string", "US-listed ticker symbol.", required=True),
                    "primary_base_quality": _field("enum", "Weekly-chart judgment used only when insufficient long history opens the recent-IPO route.", choices=["supports", "contradicts", "needs_chart"]),
                    "primary_base_emergence": _field("enum", "Weekly-chart judgment for the source's second emergence route, a constructive consolidation near the all-time high. A completed close above every prior high already triggers emergence without this.", choices=["near_high_consolidation", "needs_chart"]),
                    "primary_base_long_correction": _field("enum", "Weekly-chart judgment resolving a Primary Base 35 to 50 percent deep, which the source permits only for a correction lasting about a year. Deeper than 50 percent fails regardless.", choices=["confirmed", "not_confirmed", "needs_chart"]),
                },
                providers=True,
            ),
            output="Eligibility route and state, exact Trend Template signals, completed-history depth, RS date/value, missing evidence, and next capabilities. Each criterion's limit and its required-value text are read from the doctrine registry, so the number a verdict used and the number it reports are the same one. `bands` carries any measurement the source stated as a range, with its measured value, the range, and where inside it the measurement landed.",
            limitations=["All eight standard criteria are AND conditions; fundamentals and narrative cannot waive a known failure.", "RS comes only from ibd-rs-rating 0.5.0 and is never approximated.", "When completed price history stops before --as-of the verdict is withheld rather than computed from the earlier session; name that session with --as-of to get an aligned answer.", "A chart judgment is required for ambiguous Primary Base quality.", "Primary Base depth bands are 25% at three weeks, 35% up to five weeks and beyond, and 50% only for a chart-confirmed year-long correction; a base that has not emerged yet is incomplete rather than rejected."],
            status_meanings={"ok": "Available evidence produced eligible, avoid, or incomplete domain state.", "partial": "RS or another independent source is unavailable, or completed price history stops before the requested session and eligibility is withheld.", "unavailable": "Completed price history is unavailable.", "needs_input": "A supplied argument is invalid."},
            examples=["scripts/.venv/bin/python scripts/pipeline ticker qualify AAPL", "scripts/.venv/bin/python scripts/pipeline ticker qualify IPOX --primary-base-quality supports --primary-base-emergence near_high_consolidation"],
        ),
        _capability(
            "ticker.swings",
            "Propose the harness's own swing segmentation for a ticker, so a person can look at it before a setup rests on it.",
            inputs=_inputs({"ticker": _field("string", "US-listed ticker symbol.", required=True)}, providers=True),
            output="The candidate base chain ending on its pivot, the leg price is in now, the sessions a bar could not settle, and the parameters the detector ran at.",
            limitations=[
                "This proposes and decides nothing: no setup state, no signals. Approval is a person reading the chart and declaring the chain back to ticker.setup, which re-runs the same detector rather than trusting what it is handed.",
                "The retracement is the harness's own convention, not the source's, which describes swing reading as chart work and never names a percentage. It is registered as a parameter rather than a threshold, is not a caller input, and is scaled to the stock's own typical daily range rather than fixed: whether a given give-back is noise is a fact about the stock, and a fixed percentage read a quiet name's real contractions and a volatile name's intraday chop as the same event. The multiple, the range it was applied to, and the percentage it came out at all travel with the answer.",
                "The base's left edge is where the stock last broke out of a structure and stayed out -- a close above a prior high, before the pivot formed, on volume above its own preceding fifty sessions, with every low since above that high. Fewer than fifty prior sessions is not that observation and the crossing is unjudged rather than quiet -- an absence folded into a no made all three readings lose the same evidence and agree. An unjudged crossing withholds the whole segmentation only where knowing it would move the base's left edge; one the rim already discards changes no chain and is passed over. Where the base begins is read three ways -- not bounded at all, bounded where holding admits no reset, and bounded where a shallow failure that recovered still counts as leaving -- and a base is proposed only where all three agree. Each reading is defensible and each is wrong somewhere: strict holding misses a departure the source would recognise, tolerant holding cuts at a marginal one, and no boundary lets a structure the stock has left lend a contraction to the one above it. Picking any of them reached ready on a chain the detector had edited, once by deleting the contraction that widened and once by borrowing one. Disagreement is reported as base_left_edge_ambiguous with all three chains, so a reader can see what the dispute was; across fifteen real histories the readings agreed on twelve. That is the source's own buy point, and it is the observation price alone does not supply: on price a rally above an earlier rally top inside a correction and a fresh consolidation under an old peak are the same picture at different magnitudes. A segmentation that neighbouring multiples disagree with is not proposed at all, and neither is one where any run in the sweep could not order a session inside the base: two runs that lost the same evidence agree on every anchor date without either having found anything, which is not agreement. The disagreement, or the session, is returned instead. Most real histories come back that way, because real price structure has no single canonical scale, and an unsettled segmentation is the honest answer rather than a defect to tune away.",
                "A move still underway is never confirmed, so the leg the stock is in now is reported apart from the base. Folding it in would put the pivot on the breakout bar.",
                "Prices are the provider's raw bars: splits and dividends are not adjusted for, and the source metadata says so with coverage.adjusted false. A corporate action is therefore a real price discontinuity to this segmentation -- a two-for-one split reads as a fifty percent decline, and an ex-dividend gap as a small one. Nothing here detects or corrects that, so a history spanning one is a history whose swings are partly the action rather than the stock. Adjusting it belongs to the provider boundary and is not in this slice.",
            ],
            status_meanings={"ok": "A segmentation the detector will vouch for.", "partial": "Completed price history stops before the requested session.", "unavailable": "No segmentation this capability will stand behind: the history is unusable as bars at all (missing or repeated columns, an index that is not dates, non-numeric or non-finite values, a repeated session, a bar whose open or close sits outside its own range), neighbouring multiples disagree, a session inside the base both extended and reversed a move, or the history segments into no base. The reason names which. Not needs_input, because the parameters are deliberately out of the caller's reach and no argument would change the answer."},
            examples=["scripts/.venv/bin/python scripts/pipeline ticker swings AAPL", "scripts/.venv/bin/python scripts/pipeline ticker swings AAPL --as-of 2026-06-19"],
            compact_keeps=("anchors",),
        ),
        _capability(
            "ticker.setup",
            "Measure a declared base against completed bars and decide the setup on evidence each route must positively have.",
            inputs=_inputs(
                {
                    "ticker": _field("string", "US-listed ticker symbol.", required=True),
                    "swing": _field("string[]", "Repeatable swing date, alternating high and low and ending on the high that is the pivot; every date is checked against the completed bars and a bar that is not the extreme of the span its neighbours bound is refused by name. Omitting it is not an error: the setup comes back incomplete with the base structure named as the evidence it lacks, which is the point at which to render the chart and read the swings off it."),
                    "entry_kind": _field("enum", "Which entry this is. The five named tactics are TraderLion's early entries, taken before the traditional pivot; each is advanced, opt-in, and holds the caller to its own trigger and invalidation.", choices=["completed_pivot", "vcp_cheat", "key_support_level_reclaim", "consolidation_pivot_breakout", "key_moving_average_pullback", "oops_reversal", "key_support_level_pullback"]),
                    "chain_completeness": _field("enum", "Whether the declared chain is the base's whole structure. Saying partial admits a gap and costs you nothing. Saying complete is a declaration that gets checked rather than taken: the harness re-runs its own detector over the same bars, at parameters no argument reaches, and the reading counts only when the chain you declared is the chain it produced. Ask ticker.swings for that chain first. When the detector will not vouch for any chain over these bars, nothing declared here can pass, and the missing evidence comes back as segmentation_unstable so the absence is not mistaken for a reading somebody still has to supply.", choices=["complete", "partial", "needs_chart"]),
                    "approved_bars": _field("string", "The bars_fingerprint the chain was approved from, as ticker.swings and ticker.chart both report it. Required whenever chain_completeness is complete, which is the reading it gates -- a caller admitting a gap is telling the truth whichever vintage they read it from. It is needed because a chart reading is a reading of one picture: comparing the anchor dates alone let a chain approved from another vintage of the series vouch for this one, with every date matching while the pivot, the depths and the base the reader looked at had all moved. A value that does not match the bars being judged does not fail the base -- the reading comes back incomplete naming approval_covers_different_bars, with the current fingerprint beside it to re-approve from. It gates a reading that would otherwise have counted: a chain declared partial already fails on its own terms and a chain the bars contradict is refused before any approval is looked at, so neither outcome changes with the vintage."),
                    "entry_price": _field("number", "The price you intend to pay, recorded and reported rather than used to decide. The distance the verdict reads is the latest completed close's, because that is a price the tape recorded; a daily bar does not prove every price between its extremes traded, and a session that closed far higher does not still offer its low. Your figure is reported against the five-to-twenty-cent buffer the source named, and against the session's own range."),
                    "pivot_reset": _field("enum", "Chart reading of a failure that already happened. The source says a pivot failure can reset and recover within a small number of days and gives no number, so a spell below the pivot is neither waved through nor cut at an invented length; the longest spell is reported and the call is the reader's. Only asked for when a failure was measured.", choices=["prompt_reset", "stale_reset", "needs_judgment"]),
                    "entry_proximity": _field("enum", "How close the entry sits to the pivot. The source says to buy as close to the pivot as possible without chasing more than a few percentage points and supplies no number, so how far is too far is the reader's call. The distance judged is the latest completed close's, and the one reading the bars refuse is at_pivot while price sits below the pivot -- there is no entry above a level the stock is under. The distance at the breakout, the breakout's age, any price you declared, and Minervini's own stated five-to-twenty-cent buffer are reported for the reader to judge with.", choices=["at_pivot", "chased", "needs_judgment"]),
                    "right_side_development": _field("enum", "Chart reading of the base's right side. The source names two forms of time compression and only one of them is measurable: a right side with no pause at all is an absence the bars show, while V-shaped action is a shape the source never puts a ratio on. Without this the setup stays incomplete rather than assuming the shape is fine, and a reading of constructive is refused when the bars show no pause.", choices=["constructive", "compressed", "needs_chart"]),
                    "invalidation_price": _field("number", "Positive invalidation price; pair with invalidation_condition for a precise level."),
                    "invalidation_condition": _field("string", "Observable invalidation condition; pair with invalidation_price."),
                    "tactic_opt_in": _field("boolean", "Explicitly authorize the [TL-EARLY] tactic.", default=False),
                    "confirmation_debt": _field("string[]", "Repeatable unpaid confirmation required by a TL early entry."),
                    "tactic_evidence": _field("string[]", "Repeatable condition=observed|absent|unclear:what you read, one per condition the declared tactic requires. Observed satisfies it, absent counts against the tactic, unclear leaves it owed; the tactic's registered claim names the conditions and a name it does not have is refused."),
                    "later_pivot_price": _field("number", "Later Minervini pivot price required by a TL early entry."),
                    "later_pivot_condition": _field("string", "Later pivot confirmation condition required by a TL early entry."),
                },
                providers=True,
            ),
            output="READY, WAIT, AVOID, or INCOMPLETE setup state, the measurements behind it, the evidence the route required, the chart readings the caller declared, and contrast evidence reported separately.",
            limitations=["Swing segmentation is the caller's chart reading, corroborated rather than taken on trust: the bars check that each declared date exists, that the chain alternates and ends on a high, and that each bar really is the extreme of its span, and the harness re-runs its own detector over the same bars and requires the declared chain to be the one it produced. Ask ticker.swings for that chain, read the chart, and declare back what you approved.", "Ready requires every item of a route's declared evidence, so a base nobody described is incomplete rather than unobjectionable.", "Three of those items are readings rather than measurements -- completed bars cannot settle a V-shaped right side, whether a chain describes the base's whole structure, or how far above the pivot stops being close to it -- and a fourth is asked for only when a pivot failure was measured, because how promptly a failure reset is the same kind of question. What the bars refuse differs by reading. A right side with no pause at all is not constructive, and a stock trading below its pivot has no entry above it. How far above it stops being close is the reader's call, and the distance judged is the latest completed close's, because completed bars cannot prove any other price is still on offer -- a declared figure is carried and reported rather than treated as available. Two mechanical rules were tried here and both cut somewhere the source did not: every mechanical rule tried there either invented the number the source withheld or cut somewhere absurd, and using the five-to-twenty-cent band as a ceiling made a band decide a required condition, which its own record forbids. Completeness cannot be self-certified: the detector runs here rather than being handed in, equality with the chain it produced is what the reading rests on, and the approval names the bars it was read from so a reading of an older vintage cannot vouch for this one. When neighbouring parameter values disagree, or a session inside the base both extended and reversed a move, it vouches for nothing and the standard route cannot reach ready over those bars at all, which comes back as incomplete naming segmentation_unstable rather than as a reading still to be supplied. The remaining calls -- how close is close, and whether a pivot failure reset promptly -- are the reader's with the measurements printed beside them, and a reader who declares against those numbers is doing so in plain sight.", "Every reading is listed back in declared_readings so the share of the verdict that came from a person is visible, and everything else in it is measured and cannot be declared away. Where the trust boundary sits is worth stating plainly: chain completeness is checked by comparing two segmentations and cannot be talked past, while how close is close and how prompt a reset was are the reader's calls with the numbers printed beside them. A reader who declares against those numbers is doing so in plain sight, and the harness does not invent a limit the source withheld in order to stop them.", "Price quieting down on the right side is reported rather than decided: the source says 'noticeably' and gives no number, and a strict comparison of two medians passed a pause two ten-thousandths of a percentage point tighter than its base. The volume half of that same sentence is a gate, because a contraction either happened or it did not.", "Contrast evidence from other practitioners is reported beside the verdict and never enters it.", "Prices are the provider's raw bars: splits and dividends are not adjusted for, and the source metadata says so with coverage.adjusted false. A corporate action is therefore a real price discontinuity to this segmentation -- a two-for-one split reads as a fifty percent decline, and an ex-dividend gap as a small one. Nothing here detects or corrects that, so a history spanning one is a history whose swings are partly the action rather than the stock. Adjusting it belongs to the provider boundary and is not in this slice.", "The breakout is the first completed close above the pivot after it and is never re-dated, so its volume and closing range are read where the stock actually left the base. Where price stands now is a separate fact: the source says a pivot failure can reset and recover, so a slip below the pivot is counted beside the trigger rather than held against the base, and the trigger reads whether price is above the pivot today.", "A chain declared from a late high is not a misread swing and is not refused; what it leaves above the entry is measured instead and reported as overhead supply.", "The correction the depth limit reads runs from the highest high in the price history the provider returned to the lowest low after it, not from the base the caller declared, and both dates travel with it so a reader can see whether the peak belongs to this base or an older one.", "A cheat entry is not measurable yet: it is entered inside the base rather than at its pivot, so it returns incomplete naming the cheat geometry it needs rather than borrowing the pivot breakout's evidence.", "An early entry requires opt-in, explicit confirmation debt, a later pivot, and precise invalidation, and it does not waive the supply gates, which are about the base rather than about when the trade is taken. It also requires a name. The source says every entry tactic is two things -- a pivot that triggers the entry and a level it is abandoned at -- and defines five of them on the daily timeframe: the key support level reclaim, the consolidation pivot breakout, the key moving average pullback, the oops reversal, and the key support level pullback. Each holds the caller to its own conditions, read from its registered claim rather than restated here, and no amount of one tactic's evidence answers another's. What is not offered is anything the source names without defining. Upside reversals, range breakouts and inside days appear throughout it -- as labels on annotated charts, and in one trade post-mortem an upside reversal is even entered on the next day's push over the prior high -- but none of the three is given the contract the five have: a stated trigger and a risk-management level that make it that tactic rather than a description of what the chart did. A worked example is not a rule, and registering one as a tactic would put a trigger in the source's mouth. The source's other three tactics, the opening range breakout, the intraday base and the high-volume-close pivot, are intraday and outside this harness's scope. The five that are offered are declared rather than measured: the caller reads the chart and says what they saw, and the envelope returns incomplete naming each condition still owed."],
            status_meanings={"ok": "The setup reducer produced ready, wait, or avoid.", "needs_input": "Required evidence is absent, or the declared chain contradicts the bars, and a caller can supply what is missing.", "partial": "Completed price history stops before the requested session, so the setup is not judged.", "unavailable": "Completed price history is unavailable, or the detector will not vouch for any segmentation of these bars -- the same gap ticker.swings reports, and no argument to this command changes it, so no next capability is offered. A verdict read off a chain nothing vouched for is uncorroborated the same way, and that covers a declared chain the detector did not produce as well as a segmentation it refused: the measurements then describe some other span, so a hard gate failing on them is a finding about that span rather than about this stock. Such a verdict comes back as incomplete with the reducer's own state kept beside it in uncorroborated_verdict, and `signals` then carries only the completeness signal that explains why nothing else counted -- the measurements themselves stay in the payload for a person to read, because a reducer scanning signal states would otherwise read a gate that failed on some other span as a finding about this stock. The status still says whether anything can be done about it -- a chain the detector did not produce is needs_input, because declaring the one it did is exactly what fixes it."},
            examples=["scripts/.venv/bin/python scripts/pipeline ticker setup AAPL --swing 2026-03-19 --swing 2026-04-06 --swing 2026-04-20 --swing 2026-05-06 --swing 2026-05-20 --swing 2026-06-05 --swing 2026-06-19", "scripts/.venv/bin/python scripts/pipeline ticker setup AAPL --swing 2026-03-19 --swing 2026-04-06 --swing 2026-04-20 --swing 2026-05-06 --swing 2026-05-20 --swing 2026-06-05 --swing 2026-06-19 --right-side-development constructive --entry-proximity at_pivot"],
        ),
        _capability(
            "ticker.power-play",
            "Measure the Power Play criteria against completed bars, so the one exception to verified fundamentals has to be earned rather than declared.",
            inputs=_inputs(
                {
                    "ticker": _field("string", "US-listed ticker symbol.", required=True),
                    "drawn_bars": _field(
                        "string",
                        "The bars_fingerprint the chart was read from, as ticker.chart reports it in input_sha256 and every chart question carries it in drawn_bars. Required whenever chart_readings is supplied. A key binds an answer to the bars this verdict is measured on; it cannot attest that the picture in front of the reader came from those bars, and the two capabilities reach the provider through their own cache entry, so one can be drawn from a vintage the other never measured. A value that does not match does not fail the structure: nothing is applied, and every criterion that has no older cause of its own comes back naming approval_covers_different_bars with measured_from beside it to re-read from. A criterion already held by something the vintage did not cause -- a flag that has not finished, a split inside the span -- keeps its own reason, and a structure the bars already rejected stays rejected, because none of those were waiting on a chart.",
                    ),
                    "chart_readings": _field(
                        "string[]",
                        "Repeatable KEY=observed|absent, one per question this capability asked. The key comes from chart_questions and names the bars, the criterion, the reading of the tops and the measurement together, so an answer read from these bars and matching no open question is refused rather than dropped -- the ordinary way one goes stale is a session closing between the chart and the request. An answer read from another vintage is not refused for its keys, because this run issued none of them; nothing is applied and drawn_bars is what comes back. Observed satisfies the criterion for the reading it was asked under and absent settles it against the stock for that same reading -- a top that may contest it goes on holding the criterion open until its own key is answered. A reader who could not tell supplies nothing.",
                    ),
                },
                providers=True,
            ),
            output="The advance, the flag and the volume behind them, each of the source's four criteria read against what was measured, and whether the structure is out, unresolved, or clear on everything the bars can settle. Two digests travel with it and mean different things: measured_bars covers the prices and the split and dividend events together and names the input the verdict was reached on, while measured_from is the price-only bars_fingerprint that ticker.chart also prints, and is what a reader compares against the picture in front of them. chart_questions lists what is still being asked -- one entry per criterion per reading of the tops, each with the key that answers it, the span it is asked about, the measurement it turns on, drawn_bars, and answered, which is the word supplied or null. A finished verdict keeps only the answered entries, because a rejection and a qualification both mean nothing is outstanding. An observation answered by a reader carries read_from_chart so a pass a person supplied never reads like one the numbers reached. Three lists say which criteria a top that may contest them is holding open and how: contested_criteria for a top that answered differently, awaiting_chart_under_another_top for one whose chart is unread, and payout_decided_under_another_top for one whose answer a dividend decided. unread_top names the candidate the loaded history ends before, with its distance below the highest, and unread_top_may_contest says whether that distance lets it withhold a qualification. peak_is_a_confirmed_turning_point says whether the segmentation confirms the top the structure hangs from -- false leaves every measured failure standing and withholds a qualification under peak_not_a_confirmed_turning_point, because a flag tighter than one day's ordinary range confirms no turning point and a structure hanging from a bar nothing confirmed is not one this harness has identified a top for. readings_cover_other_bars says an answer was read from another vintage and nothing was applied.",
            limitations=[
                "This is an evidence pack, not a qualifier. Two of the four criteria end in questions completed bars do not answer -- whether the launch volume was huge rather than merely expanded, and whether a flag outside ten percent nonetheless shows VCP characteristics -- so a structure that clears every measurable limit comes back incomplete naming the reading it waits on. What it does deterministically is remove candidates: an advance short of a hundred percent, a flag past six weeks or deeper than twenty-five, and an advance with no expanded session anywhere in it are all findings the bars support on their own.",
                "Nothing here waives verified fundamentals. The exception the source describes is real and this is what it would have to be measured against, but the surface that could close it needs each control's own evidence rather than a caller's word for it, and no capability holds all of them yet. ticker.fundamentals keeps its growth gap as a gap.",
                "The structure is found rather than declared, inside two windows anchored at the last completed bar: the peak is the highest session of the longest structure the criteria describe, and the advance is the eight weeks before it. Anchoring both at the last bar is what keeps the reading still when a caller loads a different amount of history -- measured against the whole history's maximum instead, fourteen of eighteen real tickers reported a different peak, a different advance, or both. The cost is that a structure whose peak sits further back than the criteria allow is reported as the failure it is rather than searched for.",
                "The eight-week and six-week limits are enforced by not looking past them, which is not the same as forgiving what lies beyond: an advance that took nine weeks is never found by a search that looks back eight, and reports whatever it managed inside eight instead.",
                "The advance is gated on the close-to-close reading and the low-to-high reading is reported beside it. Read on the extremes alone, a single intraday wick to half the peak reports a hundred and four percent advance on a stock whose close moved half a percent. Flag depth runs the other way -- the intraday reading is the deeper and stricter one -- and is measured on the extremes for that reason. One session anchors the size of the move, its length and the volume it came out of: the last session at the window's lowest close. Reading the price close to close and the duration from the lowest low counted them from two different days, and a forty-session advance whose late bar wicked down reported one week of time against eight weeks of price gain.",
                "The volume clause is decided on the heaviest session of the advance, reported with its date, rather than on the anchor bar alone -- the lowest session is not reliably the first one, and a quiet undercut five weeks before the peak reported no expansion at all on a stock that doubled at ten times its usual volume. The baseline it is measured against is the forty sessions before the anchor, not a fixed offset from the peak: a window forty to eighty sessions ahead of the peak is whatever regime the stock was in then, and forty old sessions at ten million behind thirty-one quiet ones made a five-times launch measure as half.",
                "A marginal new high inside a tight flag restarts the structure, because nothing in the source says how large a new high has to be before it means something. The bars are therefore read from every top the search could have landed on -- the highest of the span, then the highest below that, down to the end of the span -- where a top means a confirmed turning point, a high price has since fallen away from by the retracements ticker.swings cuts its chain at -- all of them, the middle value and both sensitivity neighbours, because a top only one of those readings confirms is still a reading of the same chart and its known failure would otherwise never reach the verdict. Every descending high is a weaker thing and read a flag one bar at a time: twenty-eight readings on a structure holding three tops, each one carrying a vote on whether the rejection stands. The distance registered as this harness's own convention for candidate tops decides which of those tops may *contest* a criterion, and nothing else: a top far below the highest is a different structure, and letting it dispute a limit would leave every criterion permanently open. It is not the sources' tight-action figure it happens to equal, which describes a flag's decline after a peak has been chosen and offers VCP character as an alternative to it. The first top past the distance is reported with how far past it stands, so the boundary a contest was decided next to can be audited. What the distance does not decide is which tops may object: a rejection stands only where every top in the span was readable and reached one, so a structure the chain walked past still prevents a rejection, and so does a candidate whose own span holds a corporate action and could not be read at all. A lower top the loaded history cannot reach behind withholds the rejection under its own name -- it is a top nobody read, which is the shape a recently listed stock arrives in, and no chart reading or agreement among tops closes it. It withholds a qualification too, but only when it stands inside the candidate distance: objecting survives that distance and contesting does not, and a Power Play is what a recent listing does, so blocking on every unread top would have closed this exception forever for the stock it was written about. The measurement keeps the price of the top it could not read for exactly that comparison; a top it never priced counts as close. Two readings were not enough: two ticks a hundredth of a percent apart hand the search three tops, and both of the first two reject while the structure they sit inside has nothing decisive against it. Reading all of them costs verdicts and is meant to: measured through this capability on the completed session of 2026-08-24, across the twenty-four in-scope tickers this repository has provider history for -- the cached common stocks and ADRs, with the one cached ETF left out as out of scope, the chain runs one to five tops, twenty-three reject on a criterion every top read agreed on, and the one that does not carries a corporate action inside its span. The distance leaves nine of them with a disputed top and costs nothing for it: eight reject on an agreed criterion anyway, and the ninth is the one whose span holds a corporate action, so nothing there was going to be decided either way. A dispute decides something only on a structure that would otherwise have qualified. A rejection this capability does reach is one no top in the span disputes.",
                "Cash distributions are measured, not corrected either, and unlike a split the amount is known -- so a payout withholds only the criteria it actually decided rather than the whole reading. Both questions are asked against one series with every print on one scale, and asked in that order. First the structure: a session before an ex-date can outprint the top the stock actually made, so the tops are re-found on that series and the whole structure's boundaries are compared, not just the peak -- a payout can leave the top exactly where it was and still move where the advance started, how long it took and which forty sessions the volume was measured against, and any of those moving leaves nothing here deciding. Then the answers, reading by reading, because a structure surviving does not make its answers survive with it: the cash comes out of the prints between the anchor and the peak, so ninety-nine percent on the tape is a hundred and a half on one scale, every boundary matches, and which side of the limit that lands on is the whole verdict. A criterion that answers differently on the two scales is withheld under the payout's own name; an ordinary quarterly payment is a fraction of a percent against a twenty-five percent limit and moves nothing. Per reading rather than pooled across the chain: the tops sit at different sessions, so a longer flag holds payouts a shorter one never saw, and a reading whose answer the payout decided abstains rather than disputes. What was paid is reported beside the structure in two figures, split at the flag's low: cash paid on or before the low came out of the price that made that low, cash paid after it did not, and a reader auditing a withheld criterion needs to see which. A history that does not carry the distribution column has not said there were none, and that absence is its own gap, the same as a missing split column. What is reported stays on the prints the tape made -- the peak, the anchor, the durations, the depths and the volume spans are the printed ones, and the one-scale series decides only what those numbers are allowed to settle, never what they are.",
                "Corporate actions are named, not corrected. The provider supplies the split events and the prices stay the ones the tape printed, so a split inside the measured span -- which runs back through the volume baseline, not just the structure -- leaves nothing here deciding, in the verdict channel and in the signals alike. The session counts are no exception: the peak they are counted from is itself chosen by comparing prices, and the same event that leaves a real top standing in one direction buries it in the other, turning a sixty-five session flag into zero. A history that does not carry the event column has not said there was no split, and that absence is reported as its own gap: without it a one-for-two reverse split is indistinguishable from the hundred percent overnight advance these criteria ask about. The block is bounded by the span rather than permanent: NVDA's ten-for-one on 2024-06-10 left this capability unable to decide through 2024-10-01 and deciding again by 2025-02-03, which is about how long the split takes to fall out of the volume baseline.",
                "Two of the criteria are answered by a reader, and that channel is the only way a human sentence becomes a machine pass here. It is bound accordingly: the capability issues a key per open question and accepts an answer only against a key it issued, where the key is a digest of the composite fingerprint of the bars and their split and dividend events, the criterion, the sentence the reader was answering, the registered values that sentence and the reading of the tops were built from, every boundary session of that reading, and the measurement the criterion turns on. A caller assembling those fields themselves could match the ones they kept and miss the one that moved, so the key is issued rather than described. The sentence and the registry are in the key because the criterion is not a constant: re-register the tight limit at eleven percent and the question changes while a key built from bars and boundaries alone does not, so an answer given to the ten percent question would satisfy the eleven percent one. Two words, observed and absent, both admissible on the same terms -- resolving a question the numbers declined to answer is not overriding a number. A reader who looked and could not tell supplies nothing and the envelope goes on asking. An answer read from these bars and matching no open question is refused by name, because the ordinary way one goes stale is a session closing between the chart and the request. Read from another vintage there is nothing to say about its keys -- this run never issued any of them -- so the vintage is what comes back, and re-reading the right picture reissues the keys anyway.",
                "What no reading of a chart closes falls out of that binding rather than from a rule forbidding it. A flag short of twelve sessions has not failed, it has not finished, and no chart adds a session. Two candidate tops asking the same question about different spans each get their own key, so settling the criterion costs a reader both charts. Answering one of them does not dispute the peak: a top nobody looked at has not disagreed with the one somebody did, and the criterion comes back as chart_unread_under_another_top with the other top's key still open. The same reading of silence runs for the dividend -- a contesting top whose answer a payout decided reports distribution_under_another_top rather than a dispute. A span holding a corporate action, or a history that cannot say whether one happened, is issued no key at all -- a reader cannot be asked to corroborate price action the split manufactured. A reading the bars already threw out is issued no key either, because a visual opinion never overturns a deterministic failure and a key there would send a reader to draw a picture with nothing left to decide. What its criteria then report depends on whether the structure is finished: on a rejection they say structure_is_already_rejected and come back with required false, and on a verdict still held open -- by a top the history ends before, say -- they say reading_rejected_before_a_chart_was_needed, which names the reading rather than the structure because that is what was rejected. That is where the seam sits today: measured on the completed session of 2026-08-24 across the twenty-four in-scope tickers this repository has provider history for -- the cached common stocks and ADRs, with the one cached ETF left out as out of scope, it asks zero questions, because twenty-three reject on measurement and the twenty-fourth carries a corporate action inside its span. Every answered signal carries read_from_chart, so a verdict a person supplied never reads like one the numbers reached.",
            ],
            status_meanings={"ok": "The question this capability was asked has a finished answer, and the state says which one. `not_qualified` is a rejection -- reached by the bars, or by a reader's own `absent` reading of a criterion the bars declined to decide -- and a rejection leaves criteria nobody satisfied behind it, reported with required false because closing them would change nothing. `qualified` means every criterion is satisfied and nothing is outstanding. Neither is a waiver of anything: no surface consumes this state yet, ticker.fundamentals keeps its growth gap as a gap, and ticker.risk has no input that would let this reach a BUY-READY verdict.", "partial": "Either the structure is neither qualified nor rejected, or it was never measured because the provider's last completed bar is behind the requested session -- that one returns before any structure is read and names the stale price evidence as its only gap. Otherwise each gap names its own cause. Something measurable may well have failed: a criterion the highest top read as a failure is withheld while a top the loaded history ends before could still have stood, and that gap closes on more history rather than on anything a caller supplies. The others are a chart nobody has read, at the highest top or at one that may contest it, a payout that decided the answer, and corporate-action evidence that is missing or inside the span.", "unavailable": "Completed price history is unavailable, or the history is unusable as bars at all -- the reason names which, in the same vocabulary ticker.swings and ticker.chart use.", "needs_input": "The request could not be read: a session that is not a completed US trading session, a chart reading written in a shape this capability does not take, an answer naming a key it never issued, or an answer with no drawn_bars beside it."},
            examples=["scripts/.venv/bin/python scripts/pipeline ticker power-play AAOI", "scripts/.venv/bin/python scripts/pipeline ticker power-play NVDA --as-of 2024-10-01"],
            compact_keeps=("measurements",),
        ),
        _capability(
            "ticker.fundamentals",
            "Evaluate filed growth, revenue and margin confirmation, accounting integrity, dilution, leadership profile, and the narrow Power Play exception.",
            inputs=_inputs(
                {
                    "ticker": _field("string", "US-listed ticker symbol.", required=True),
                    "cik": _field("string", "Stable SEC CIK of at most ten digits; required for historical --as-of."),
                },
                providers=True,
            ),
            output="Filed-as-of growth and integrity evidence, leader category, discrepancies, missing facts, and fundamentals convergence state.",
            limitations=["SEC facts are selected by filed_at, never period end alone.", "Current ticker-to-CIK lookup is not used for historical identity; provide --cik.", "Power Play may waive only unavailable verified fundamentals, never integrity, dilution, market, setup, eligibility, or risk controls.", "The current SEC adapter reads the recent submissions index and discloses that older index files were not fetched."],
            status_meanings={"ok": "Filed evidence supports or contradicts convergence, or a fully proven exception applies.", "partial": "Filed evidence exists but required facts are incomplete.", "needs_input": "Historical identity or another required argument is missing.", "unavailable": "SEC evidence could not be obtained after one retry."},
            examples=["MINERVINI_SEC_USER_AGENT='Name email@example.com' scripts/.venv/bin/python scripts/pipeline ticker fundamentals AAPL", "MINERVINI_SEC_USER_AGENT='Name email@example.com' scripts/.venv/bin/python scripts/pipeline ticker fundamentals AAPL --as-of 2026-08-14 --cik 0000320193"],
        ),
        _capability(
            "ticker.peers",
            "Compare a ticker with a same-industry leadership set using stable listing identity, exact RS, and completed-price evidence.",
            inputs=_inputs(
                {
                    "ticker": _field("string", "US-listed common-stock or ADR symbol.", required=True),
                    "limit": _field("integer", "Maximum ranked peers returned, from 1 through 20.", default=10),
                },
                providers=True,
            ),
            output="Current sector/industry identity, target rank, peer ranks, explicit rank basis, exclusions, missing evidence, and sources.",
            limitations=["yfinance industry taxonomy and Nasdaq security master are mutable current snapshots; older historical peer reconstruction is unavailable.", "A symbol absent or ambiguous in the security master never receives a synthetic stable ID.", "Peers lacking exact-date RS or completed 3-month/52-week price evidence remain incomplete rather than rankable."],
            status_meanings={"ok": "The target and all returned peers have complete rank evidence.", "partial": "A usable comparison exists but target, peer, identity, or provider evidence is missing.", "unavailable": "Required current classification, security master, or industry snapshot is unavailable."},
            examples=["scripts/.venv/bin/python scripts/pipeline ticker peers NVDA --limit 10"],
        ),
        _capability(
            "ticker.risk",
            "Reduce converged prospective evidence to BUY-READY, WAIT, AVOID, or INCOMPLETE, or active-position evidence to HOLD, SELL, or INCOMPLETE.",
            inputs=_inputs(
                {
                    "ticker": _field("string", "US-listed ticker symbol.", required=True),
                    "mode": _field("enum", "Prospective entry or active-position reducer.", default="prospective", choices=["prospective", "active"]),
                    "entry_price": _field("number", "Positive planned or actual entry price."),
                    "entry_date": _field("date", "Actual ISO entry date; required in active mode."),
                    "stop_price": _field("number", "Positive hard-stop price. In active mode, every completed daily Low is audited from the stop's effective date through --as-of."),
                    "stop_effective_date": _field("date", "Calendar date when --stop-price became effective in active mode; defaults to --entry-date. The audit begins with the first completed bar on or after this date."),
                    "upside_price": _field("number", "Positive evidence-based reward reference; required in prospective mode."),
                    "current_price": _field("number", "Optional explicit latest completed price. A value at or below the stop can trigger SELL, but a value above it cannot establish HOLD without the provider-audited completed price path."),
                    "average_gain_pct": _field("number", "The trader's realized average gain percentage. Prospective mode cannot reach BUY-READY without it; its absence is reported as missing evidence, not a relaxed cap."),
                    "market_state": _field("enum", "Market verdict from market.snapshot.", choices=["favorable", "cautious", "defensive", "incomplete"]),
                    "eligibility_state": _field("enum", "Eligibility verdict from ticker.qualify.", choices=["eligible", "avoid", "incomplete"]),
                    "setup_state": _field("enum", "Setup verdict from ticker.setup.", choices=["ready", "wait", "avoid", "incomplete"]),
                    "fundamentals_state": _field("enum", "Fundamentals verdict from ticker.fundamentals.", choices=["supports_convergence", "does_not_support_convergence", "incomplete"]),
                    "invalidation_price": _field("number", "Positive structural invalidation price. In active mode it is audited over completed bars from --entry-date, alongside and independently of the hard stop."),
                    "invalidation_condition": _field("string", "Observable structural invalidation condition. Pair it with --invalidation-price in active mode: a condition the harness cannot evaluate against completed bars is reported as missing evidence rather than assumed unbreached."),
                    "completed_stop_breach": _field("boolean", "Assert a stop breach on completed evidence.", default=False),
                    "live_stop_check": _field("boolean", "Explicitly authorize partial-session hard-stop checking.", default=False),
                    "live_stop_breach": _field("boolean", "Assert a live breach; SELL requires live_stop_check too.", default=False),
                },
                providers=True,
            ),
            output="The sole final ticker verdict with component states, completed stop-path evidence, failed/waiting/missing evidence, stop constraints, reward-to-risk, and 3R protection context. Every limit comes from the doctrine registry: a gate decides pass or fail, while a band such as the ordinary loss target reports the measurement, the source's range, and where in that range it landed.",
            prerequisites=["Prospective mode should consume market.snapshot, ticker.qualify, ticker.setup, and ticker.fundamentals verdicts."],
            limitations=["This capability never recommends portfolio allocation or position size.", "A hard stop may not exceed 10% or half the realized average gain; --average-gain-pct is required for a prospective verdict and reward-to-risk must be at least 2:1.", "A completed current price above the protective level cannot establish HOLD: the provider must cover every completed daily Low from --stop-effective-date through --as-of; a recovered price does not erase an earlier breach.", "Each protective level is audited from its own effective date: the hard stop from --stop-effective-date, the structural invalidation from --entry-date. A breach of either is a SELL, and HOLD requires every declared level to be cleared over its whole window.", "--stop-effective-date defaults to --entry-date. When a stop was raised or replaced later, supply its actual effective date so the newer stop is not applied retroactively.", "Active-mode chronology is checked before any evidence is fetched: --entry-date cannot follow --as-of, and --stop-effective-date can neither precede --entry-date nor follow --as-of. An asserted breach outranks evidence nobody gathered, but never a request that contradicts itself or declares no exit plan.", "An explicit --current-price at or below the stop can trigger SELL; a partial-session breach must instead use the explicit live-stop flags.", "A live stop breach triggers SELL only when --live-stop-check is explicit; ordinary gates use completed bars.", "The reducer does not infer unsupported market, eligibility, setup, or fundamentals states."],
            status_meanings={"ok": "A complete BUY-READY, WAIT, AVOID, HOLD, or SELL verdict was produced; active HOLD includes a clear completed stop path.", "partial": "The completed-price provider failed, could not cover the full active stop window, or stopped before the requested session.", "needs_input": "Required evidence is missing, so the domain verdict is INCOMPLETE.", "unavailable": "An internal required capability cannot be evaluated."},
            examples=["scripts/.venv/bin/python scripts/pipeline ticker risk AAPL --market-state favorable --eligibility-state eligible --setup-state ready --fundamentals-state supports_convergence --entry-price 200 --stop-price 188 --upside-price 224 --average-gain-pct 24", "scripts/.venv/bin/python scripts/pipeline ticker risk AAPL --mode active --entry-price 200 --entry-date 2026-08-10 --stop-price 188"],
        ),
        _capability(
            "ticker.chart",
            "Render auditable weekly-first and daily chart artifacts from the same completed bars used by deterministic analysis.",
            inputs=_inputs(
                {
                    "ticker": _field("string", "US-listed ticker symbol.", required=True),
                    "output_dir": _field("path", "Destination directory; defaults to the ignored .artifacts/charts directory."),
                },
                providers=True,
            ),
            output="Chart artifact paths plus an input-hash manifest recording ticker, as-of, timeframe order, completed-bar provenance, and the swing segmentation drawn on the price panel.",
            limitations=["Charts corroborate qualitative ambiguity but never override a deterministic hard gate. A history the measuring side will not read is refused here too rather than rendered: two definitions of a usable bar let a chart succeed off bars ticker.setup rejects, and the artifact then carried a null input digest -- the one thing a setup approval has to name.", "Weekly is rendered before daily; historical as-of is enforced before rendering. A weekly bar is kept for the sessions it aggregates rather than for the Friday it is labelled with, so a week read mid-way through, or one whose Friday is a holiday, keeps its bar and its anchors instead of vanishing. Such a bar aggregates only the sessions it has, which makes its volume short for a reason that is not the stock going quiet, and the manifest flags it as last_bar_partial. Artifact paths carry the bars' own digest, so two renders of different history into one directory cannot interleave into a manifest that names one digest beside a picture drawn from another -- the digest is what a setup approval cites.", "The detector's turning points and its pivot are marked on the price panel, because this is where a person turns that proposal into the approval ticker.setup asks for. A segmentation the detector will not vouch for draws nothing rather than showing a structure the engine refuses to use. Each anchor is placed on the bar containing its session -- the session itself on the daily chart, the week it fell in on the weekly -- and one the chart does not reach is left off. Every manifest artifact lists the anchors its own picture contains, so what was drawn is not inferred from what was available."],
            status_meanings={"ok": "Both chart artifacts and the manifest were written.", "unavailable": "Completed price history is unavailable, or the history the provider returned is not renderable -- the reason names which, in the same vocabulary ticker.swings uses, because a caller told only that something failed cannot tell a data problem from a bug.", "partial": "Completed price history stops before the requested session, so no artifact is written.", "needs_input": "The destination path or ticker is invalid."},
            side_effects=["Writes deterministic PNG artifacts and a manifest to the requested directory; the default directory is git-ignored."],
            examples=["scripts/.venv/bin/python scripts/pipeline ticker chart AAPL", "scripts/.venv/bin/python scripts/pipeline ticker chart AAPL --output-dir .artifacts/review/AAPL"],
        ),
        _capability(
            "watchlist.show",
            "Read the latest explicitly recorded research item for each instrument.",
            inputs=_inputs(),
            output="Current ledger records; an absent ledger returns an empty list without creating a database.",
            limitations=["The ledger stores research decisions, not holdings, allocations, quantities, or account values.", "--as-of stamps this read; it does not filter the ledger's event history."],
            status_meanings={"ok": "Records or a legitimate empty list were returned."},
            examples=["scripts/.venv/bin/python scripts/pipeline watchlist show"],
        ),
        _capability(
            "watchlist.history",
            "Read the explicit research-event history for one ticker symbol.",
            inputs=_inputs({"ticker": _field("string", "Ticker symbol whose recorded history should be read.", required=True)}),
            output="Recorded events in ledger order; an absent ledger or symbol returns an empty list without creating state.",
            limitations=["History is keyed by recorded ticker events; stable instrument identity remains in each record.", "--as-of stamps this read and does not time-filter events."],
            status_meanings={"ok": "Events or a legitimate empty list were returned."},
            examples=["scripts/.venv/bin/python scripts/pipeline watchlist history AAPL"],
        ),
        _capability(
            "watchlist.record",
            "Explicitly persist an auditable research verdict after analysis.",
            inputs=_inputs(
                {
                    "ticker": _field("string", "Ticker symbol at record time.", required=True),
                    "instrument_id": _field("string", "Stable instrument ID from the security master.", required=True),
                    "output_hash": _field("sha256", "64-character SHA-256 of the analysis output being recorded.", required=True),
                    "verdict": _field("string", "Exact recorded verdict.", required=True),
                    "condition": _field("string", "Condition that would authorize or change action."),
                    "invalidation": _field("string", "Condition that invalidates the thesis or setup."),
                    "doctrine_ids": _field("string[]", "Repeatable doctrine claim IDs used by the decision."),
                    "evidence_quality": _field("string", "Recorded evidence-quality label."),
                    "note": _field("string", "Optional user note."),
                }
            ),
            output="The inserted research record and its stable ledger fields.",
            limitations=["This command does not infer or recompute a verdict; it records exactly what the caller supplies.", "No position size, allocation, quantity, or account data is accepted."],
            status_meanings={"ok": "The record was committed.", "needs_input": "A required field or SHA-256 digest is invalid."},
            side_effects=["Creates or updates the ignored SQLite ledger at .state/research-ledger.sqlite3, or MINERVINI_LEDGER_PATH."],
            examples=["scripts/.venv/bin/python scripts/pipeline watchlist record AAPL --instrument-id nasdaq-trader:NASDAQ:AAPL --output-hash 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef --verdict WAIT --condition 'completed close above pivot' --invalidation 'completed close below base low'"],
        ),
        _capability(
            "watchlist.annotate",
            "Append an explicit note to the latest recorded research item for a ticker.",
            inputs=_inputs({"ticker": _field("string", "Ticker symbol with an existing record.", required=True), "note": _field("string", "Non-empty note to append.", required=True)}),
            output="The updated latest record and appended history event.",
            limitations=["A note cannot create the first research record; use watchlist record first.", "--as-of stamps the command envelope and does not rewrite the original research date."],
            status_meanings={"ok": "The note was appended.", "needs_input": "The note is empty or no record exists for the ticker."},
            side_effects=["Updates the ignored local SQLite ledger."],
            examples=["scripts/.venv/bin/python scripts/pipeline watchlist annotate AAPL --note 'pivot confirmation still pending'"],
        ),
        _capability(
            "watchlist.export",
            "Explicitly export the current research-ledger snapshot to a caller-selected JSON path.",
            inputs=_inputs({"output": _field("path", "Non-empty destination JSON path.", required=True)}),
            output="The destination path and exported record count.",
            limitations=["Export contains only allowed research fields and no portfolio sizing data.", "Parent directories are created when needed; choose the destination deliberately."],
            status_meanings={"ok": "The export file was written.", "needs_input": "The output path is missing or invalid."},
            side_effects=["Writes JSON to the exact caller-selected path."],
            examples=["scripts/.venv/bin/python scripts/pipeline watchlist export --output .artifacts/watchlist.json"],
        ),
    ]
}


__all__ = ["CAPABILITIES", "Capability"]
