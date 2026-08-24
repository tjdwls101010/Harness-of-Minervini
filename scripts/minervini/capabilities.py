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
            limitations=["This is runtime doctrine, not a full book transcript or citation browser.", "--as-of stamps the envelope; doctrine content is versioned with the repository rather than market time.", "A threshold's role bounds what it may do: a gate decides pass or fail, a band reports a measurement inside a range the source stated as a range, and a reference is a population statistic never evaluated against a ticker.", "A claim on the practice layer or attributed to a named practitioner other than Minervini is contrast material, never a gate.", "A claim marked out_of_scope records doctrine this harness may not act on, such as position sizing, and no capability consumes it."],
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
            output="Eligibility route and state, exact Trend Template signals, completed-history depth, RS date/value, missing evidence, and next capabilities. Each criterion's limit and its required-value text are read from the doctrine registry, so the number a verdict used and the number it reports are the same one.",
            limitations=["All eight standard criteria are AND conditions; fundamentals and narrative cannot waive a known failure.", "RS comes only from ibd-rs-rating 0.5.0 and is never approximated.", "When completed price history stops before --as-of the verdict is withheld rather than computed from the earlier session; name that session with --as-of to get an aligned answer.", "A chart judgment is required for ambiguous Primary Base quality.", "Primary Base depth bands are 25% at three weeks, 35% up to five weeks and beyond, and 50% only for a chart-confirmed year-long correction; a base that has not emerged yet is incomplete rather than rejected."],
            status_meanings={"ok": "Available evidence produced eligible, avoid, or incomplete domain state.", "partial": "RS or another independent source is unavailable, or completed price history stops before the requested session and eligibility is withheld.", "unavailable": "Completed price history is unavailable.", "needs_input": "A supplied argument is invalid."},
            examples=["scripts/.venv/bin/python scripts/pipeline ticker qualify AAPL", "scripts/.venv/bin/python scripts/pipeline ticker qualify IPOX --primary-base-quality supports --primary-base-emergence near_high_consolidation"],
        ),
        _capability(
            "ticker.setup",
            "Evaluate price geometry, supply contraction, entry confirmation, confirmation debt, and precise invalidation from completed bars plus chart judgments.",
            inputs=_inputs(
                {
                    "ticker": _field("string", "US-listed ticker symbol.", required=True),
                    "price_geometry": _field("enum", "Independent chart judgment for base geometry.", choices=["pass", "fail", "needs_chart"]),
                    "supply_evidence": _field("enum", "Independent chart judgment for contracting supply and volume.", choices=["pass", "fail", "needs_chart"]),
                    "entry_kind": _field("enum", "Entry structure; TL early is advanced and opt-in.", choices=["completed_pivot", "vcp_cheat", "tl_early"]),
                    "entry_state": _field("enum", "Whether the named entry is confirmed on completed evidence.", choices=["confirmed", "wait", "needs_chart"]),
                    "invalidation_price": _field("number", "Positive invalidation price; pair with invalidation_condition for a precise level."),
                    "invalidation_condition": _field("string", "Observable invalidation condition; pair with invalidation_price."),
                    "tactic_opt_in": _field("boolean", "Explicitly authorize the [TL-EARLY] tactic.", default=False),
                    "confirmation_debt": _field("string[]", "Repeatable unpaid confirmation required by a TL early entry."),
                    "later_pivot_price": _field("number", "Later Minervini pivot price required by a TL early entry."),
                    "later_pivot_condition": _field("string", "Later pivot confirmation condition required by a TL early entry."),
                },
                providers=True,
            ),
            output="READY, WAIT, AVOID, or INCOMPLETE setup state with separate geometry, supply, entry, debt, and invalidation evidence.",
            limitations=["Completed OHLCV can measure a candidate pivot but cannot certify visual base geometry or supply absorption.", "A VCP label alone never passes the supply gate.", "TL early requires opt-in, explicit confirmation debt, a later pivot, and precise invalidation."],
            status_meanings={"ok": "The setup reducer produced ready, wait, or avoid.", "needs_input": "Required chart evidence remains incomplete or needs_chart.", "partial": "Completed price history stops before the requested session, so the setup is not judged.", "unavailable": "Completed price history is unavailable."},
            examples=["scripts/.venv/bin/python scripts/pipeline ticker setup AAPL --price-geometry pass --supply-evidence pass --entry-kind completed_pivot --entry-state confirmed", "scripts/.venv/bin/python scripts/pipeline ticker setup AAPL --entry-kind tl_early --entry-state confirmed --tactic-opt-in --confirmation-debt 'completed pivot breakout' --later-pivot-price 200 --later-pivot-condition 'completed close above 200' --invalidation-price 190 --invalidation-condition 'completed close below 190'"],
        ),
        _capability(
            "ticker.fundamentals",
            "Evaluate filed growth, revenue and margin confirmation, accounting integrity, dilution, leadership profile, and the narrow Power Play exception.",
            inputs=_inputs(
                {
                    "ticker": _field("string", "US-listed ticker symbol.", required=True),
                    "cik": _field("string", "Stable SEC CIK of at most ten digits; required for historical --as-of."),
                    "power_play_quality": _field("enum", "VCP-qualified Power Play quality.", choices=["textbook", "acceptable"]),
                    "power_play_fundamentals_exception": _field("boolean", "Request the sole verified-fundamentals waiver.", default=False),
                    "power_play_technical_eligibility": _field("boolean", "Assert separately verified technical eligibility.", default=False),
                    "power_play_price_volume_structure": _field("boolean", "Assert separately verified VCP-quality structure.", default=False),
                    "power_play_market_alignment": _field("boolean", "Assert separately verified market alignment.", default=False),
                    "power_play_risk_controls": _field("boolean", "Assert separately verified risk controls.", default=False),
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
                    "fundamentals_state": _field("enum", "Fundamentals verdict from ticker.fundamentals.", choices=["supports_convergence", "does_not_support_convergence", "waived_by_exception", "incomplete"]),
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
            output="Chart artifact paths plus an input-hash manifest recording ticker, as-of, timeframe order, and completed-bar provenance.",
            limitations=["Charts corroborate qualitative ambiguity but never override a deterministic hard gate.", "Weekly is rendered before daily; historical as-of is enforced before rendering."],
            status_meanings={"ok": "Both chart artifacts and the manifest were written.", "unavailable": "Completed price history is unavailable.", "partial": "Completed price history stops before the requested session, so no artifact is written.", "needs_input": "The destination path or ticker is invalid."},
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
