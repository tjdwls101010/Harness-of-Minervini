"""Audit completed stop paths and attest the evidence governing a position."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Mapping

import pandas as pd

from .numbers import REPORTED_PRECISION as _REPORTED_PRECISION
from .numbers import positive
from .contracts import RequestError, envelope
from .management_evidence import SPLIT_COLUMN as _SPLIT_COLUMN, impossible_bar_relations, split_sized_discontinuities
from .setup_structure import session_index
from .risk import AUDIT_BASIS as _AUDIT_BASIS, is_non_passing


def _positive(value: Any) -> float | None:
    number = positive(value)
    return number if number is not None and round(number, _REPORTED_PRECISION) > 0 else None


# What each state-bearing field the caller may hand in is allowed to say. A word outside its
# own vocabulary is not a quiet "no": read through a triggered-or-not test an unknown word
# means untriggered, through a clear-or-breached test it means unaudited, and either way an
# input nobody can interpret would decide a verdict by being unrecognised. The lists are the
# CLI's own choices, so one surface cannot accept what the other refuses.
_STATE_VOCABULARY: dict[str, frozenset[str]] = {
    "market": frozenset({"favorable", "cautious", "defensive", "incomplete"}),
    "eligibility": frozenset({"eligible", "avoid", "incomplete"}),
    "setup": frozenset({"ready", "wait", "avoid", "incomplete"}),
    "fundamentals": frozenset({"supports_convergence", "does_not_support_convergence", "incomplete"}),
    "completed_stop": frozenset({"triggered", "not_triggered"}),
    "stop_event": frozenset({"triggered", "not_triggered"}),
    "live_stop": frozenset({"triggered", "not_triggered"}),
    "completed_price_path": frozenset({"clear", "breached", "unavailable"}),
}
_MAPPING_FIELDS = ("invalidation", "risk", "management", *_STATE_VOCABULARY)


def _check_declared_shapes(evidence: Mapping[str, Any]) -> None:
    """Refuse a declared field whose shape or state word the reducer could only misread."""

    for field in _MAPPING_FIELDS:
        value = evidence.get(field)
        if value is None:
            continue
        if not isinstance(value, Mapping):
            raise RequestError(f"{field} must be an object", field)
        allowed = _STATE_VOCABULARY.get(field)
        if allowed is None:
            continue
        state = value.get("state", value.get("status"))
        if state is None:
            continue
        if not isinstance(state, str) or state.strip().lower() not in allowed:
            raise RequestError(f"{field}.state must be one of {', '.join(sorted(allowed))}", field)


# A window whose refusal is a coordinate-system break rather than a missing bar.
_UNCROSSABLE_REASONS = frozenset({"share_split_inside_stop_window", "corporate_action_evidence_missing"})
_COVERAGE_FIELDS = frozenset({"first_bar_checked", "last_bar_checked", "bars_checked"})


def _combine_audits(audits: list[dict[str, Any]]) -> dict[str, Any]:
    """One path verdict over several levels, each audited from its own effective date.

    A breach anywhere is irreversible, so it outranks every clear audit; a level
    whose window could not be covered leaves the whole path unresolved.
    """

    breaches = [audit for audit in audits if audit["state"] == "breached"]
    if breaches:
        # Earliest breach first. Inside one session the order is not the levels' order but
        # the prices': a stop resting in the market is taken out the moment the Low reaches
        # it, and the close prints afterwards, so a session that took out a stop intraday and
        # invalidated at the close ended at the stop. The role decides that, not the record's
        # own basis: a completed close handed in below a resting stop proves the session
        # traded at least that low, which is an intraday fill. Among levels read from the
        # same price the highest wins -- price falls from above, so that is the line it crossed first,
        # and picking the lower one publishes a record under a line reached second.
        governing = min(breaches, key=lambda audit: (audit["breach_date"], 0 if _AUDIT_BASIS.get(audit.get("role"), audit.get("basis")) == "completed_daily_low" else 1, -audit["level"]))
    else:
        unresolved = [audit for audit in audits if audit["state"] != "clear"]
        governing = unresolved[0] if unresolved else max(audits, key=lambda audit: audit["level"])
    shared = {key: value for key, value in governing.items() if key not in {"level", "role", "effective_from"}}
    return {
        **shared,
        "checked_level": governing["level"],
        # Which level this record is about. A breached invalidation and a breached stop are
        # both a SELL, but they are not the same finding, and a reader auditing the trade
        # has to see which line the market crossed.
        "governing_role": governing["role"],
        "from": governing["effective_from"],
        "audits": audits,
    }


def _uncrossable_sessions(ordered: Any) -> list[tuple[date, str]]:
    """Sessions no measurement may span, each with the reason it cannot be spanned.

    Three different findings share one shape. A declared split is an event the provider
    handed over: the prices before and after it are two coordinate systems, and a level or
    a percentage across it is arithmetic between two different shares. A history with no
    event column has not said there was no split, so a split-sized jump in the closes is
    the same refusal reached from the other side -- the harness cannot tell a share-count
    change from a fall the market made, and the two call for opposite answers.

    The third is an event column whose cell is empty. Reading that blank as a zero turns
    missing evidence into an assertion that nothing happened, which is the one move a gap
    may never make: the session beside it can carry a split-sized fall and the audit would
    walk straight through it. So an unreadable cell is refused as evidence missing, which
    is what it is, rather than as a split the provider never declared. The reason travels
    with the session because one frame can hold both kinds at once.
    """

    if _SPLIT_COLUMN in ordered.columns:
        events = pd.to_numeric(ordered[_SPLIT_COLUMN], errors="coerce")
        marked: list[str | None] = []
        for factor in events:
            value = float(factor)
            if not math.isfinite(value):
                marked.append("corporate_action_evidence_missing")
            else:
                marked.append("share_split" if value not in (0.0, 1.0) else None)
    else:
        discontinuities = split_sized_discontinuities(ordered.get("Close"))
        if discontinuities is None:
            return []
        marked = ["corporate_action_evidence_missing" if flagged else None for flagged in discontinuities]
    return [(timestamp.date(), reason) for timestamp, reason in zip(ordered.index, marked) if reason is not None]


def _max_high_since(frame: Any, *, entry_date: date, as_of: date) -> dict[str, Any]:
    """The highest completed High after the entry session through ``as_of``, and its date.

    Three R is measured from the furthest a position got. The last close only says where
    it is now, and a position that reached three R and gave some back is the one the rule
    is for. The entry session itself is excluded: a daily bar cannot say whether its High
    printed before or after the fill, and a fill at that session's close would otherwise be
    credited with a spike it never had -- profit protection would then raise a stop and cut
    a position on a gain that did not exist. The last completed close remains the floor of
    what was reached, so a position genuinely at three R today is still protected.

    A window the harness cannot measure across -- a declared split, or a split-sized jump
    in a history that carries no split column -- returns the reason instead of a peak. A
    High from the other side of such an event is a different share, and three R measured
    against it raises a stop on a gain the position never had.
    """

    if not isinstance(frame, pd.DataFrame) or frame.empty or "High" not in frame.columns:
        return {}
    timestamps = pd.to_datetime(frame.index, errors="coerce")
    if timestamps.isna().any():
        return {}
    timestamps = session_index(timestamps)
    ordered = frame.copy()
    ordered.index = timestamps
    ordered = ordered.sort_index()
    # Deduplicated before the question is asked, because two prints of one session are one
    # session: the superseded print sitting beside the one that completed is a jump between
    # two prices the same day had, and reading it as a discontinuity would withhold a peak
    # over a session the stop audit -- which deduplicates first -- reads as continuous.
    ordered = ordered[~ordered.index.normalize().duplicated(keep="last")]
    uncrossable = _uncrossable_sessions(ordered)
    # The highest High before a split is in the old coordinate system and the entry price
    # three R is measured against is in whichever one the trader declared. Reading a peak
    # across the event either invents a gain or hides one, and both raise a stop.
    inside = [(session, reason) for session, reason in uncrossable if entry_date < session <= as_of]
    if inside:
        session, reason = inside[0]
        return {"max_high_withheld_reason": f"{reason}_inside_excursion_window", "max_high_withheld_date": session.isoformat()}
    highs = pd.to_numeric(frame["High"], errors="coerce")
    highs.index = timestamps
    # Sorted before the last print wins, because "last" has to mean the latest session's
    # latest print and not the last row the provider happened to hand over. The stop audit
    # sorts first for the same reason, and the two must choose the same bar.
    highs = highs.sort_index()
    highs = highs[~highs.index.normalize().duplicated(keep="last")]
    dates = pd.Index([timestamp.date() for timestamp in highs.index])
    # From the session after entry. A daily bar cannot say whether its High printed before
    # or after the fill, and crediting the entry session's own High to the position invents
    # a gain it may never have had -- which here would raise a stop and cut a position on a
    # move that never happened. The stop audit reads the entry session because that error
    # runs the other way: it can only find a breach earlier, never later.
    # A history that begins after the position was opened cannot say how far it got: the
    # peak would be the highest of the sessions the provider happened to return, published
    # under a name that promises the highest since entry.
    first_available = dates.min()
    if first_available > entry_date:
        return {"max_high_withheld_reason": "history_starts_after_entry_date", "max_high_withheld_date": first_available.isoformat()}
    held = highs[(dates > entry_date) & (dates <= as_of)]
    if held.empty:
        return {}
    # The peak is a statistic over every session held, so it is read whole. Dropping the
    # holes and taking the maximum of what is left publishes the highest readable High
    # under a name that promises the highest High -- and three R measured from it raises a
    # stop on a peak nobody can say was the peak.
    usable = held.notna() & (held > 0) & (held != math.inf)
    if not bool(usable.all()):
        return {"max_high_withheld_reason": "invalid_high_since_entry", "max_high_withheld_date": held.index[int((~usable).to_numpy().argmax())].date().isoformat()}
    # Positional, not by label: the provider layer permits a repeated session, and a label
    # lookup on a repeated index returns every bar under it rather than the one that was highest.
    position = int(held.to_numpy().argmax())
    return {"max_high_since_entry": float(held.iloc[position]), "max_high_date": held.index[position].date().isoformat()}


def _bars_that_spoke(path_rows: list[tuple[date, Any]]) -> dict[str, Any]:
    """Which bars the audit actually read.

    A requested window start is a date the caller named, not a promise that a session
    printed there. Naming the first and last bar that spoke keeps a window whose first
    session the provider never delivered from reading as if it had been examined -- the
    harness has no trading calendar and cannot tell a missing session from a holiday.
    """

    return {
        "first_bar_checked": path_rows[0][0].isoformat(),
        "last_bar_checked": path_rows[-1][0].isoformat(),
        "bars_checked": len(path_rows),
    }


def _completed_stop_path(frame: Any, *, effective_date: date, as_of: date, protective_level: float, end_before: date | None = None, require_session: bool = False, basis: str = "completed_daily_low") -> tuple[dict[str, Any], float | None]:
    """Audit every completed session against ``protective_level`` from ``effective_date``.

    ``basis`` says which price the level is a level of. A hard stop is an order resting in
    the market, so the tape takes it out the moment the Low reaches it. A structural
    invalidation is a statement about where a session finished -- the harness's own
    vocabulary for one is "completed close below the base low" -- so a poke through it that
    closed above is not the exit the trader declared, and selling on it puts a condition in
    their mouth. The record names the basis it used, and the two are different findings.

    ``end_before`` bounds the window for a level a later stop superseded: only sessions
    strictly before that date are audited, and the window counts as fully covered once the
    frame holds any bar on or past it -- the sessions inside the window all exist then, and
    the record's ``through`` is the calendar eve of the raise so the reducer can compare it
    with the window it requires without knowing the trading calendar.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"Low", "Close"}.issubset(frame.columns):
        return {"state": "unavailable", "reason": "completed_ohlc_path_unavailable"}, None
    timestamps = pd.to_datetime(frame.index, errors="coerce")
    if timestamps.isna().any():
        return {"state": "unavailable", "reason": "invalid_completed_bar_date"}, None
    timestamps = session_index(timestamps)
    ordered = frame.copy()
    ordered.index = timestamps
    ordered = ordered.sort_index()
    # A repeated session is one session printed twice, and the last print is the one
    # that completed; auditing a superseded print would sell on a Low the session no
    # longer has. Two prints of one session can carry different clock times, so the
    # comparison is the session date, not the timestamp. Every reader of these bars --
    # the favorable-excursion measurement and the management evidence -- reads the same rule.
    ordered = ordered[~ordered.index.normalize().duplicated(keep="last")]
    dated_rows = [(timestamp.date(), row) for timestamp, row in ordered.iterrows() if timestamp.date() <= as_of]
    if not dated_rows:
        return {"state": "unavailable", "reason": "no_completed_bars_through_as_of"}, None

    latest_date, latest_row = dated_rows[-1]
    try:
        current_price = float(latest_row["Close"])
    except (TypeError, ValueError):
        current_price = None
    if current_price is not None and (not math.isfinite(current_price) or current_price <= 0):
        current_price = None

    first_available = dated_rows[0][0]
    if first_available > effective_date:
        return {
            "state": "unavailable",
            "reason": "history_starts_after_stop_effective_date",
            "requested_from": effective_date.isoformat(),
            "first_available": first_available.isoformat(),
            "through": latest_date.isoformat(),
        }, current_price
    uncrossable = _uncrossable_sessions(ordered)
    # Strictly after the window opens. The event is stamped on the session that printed the
    # new coordinate system, so a window starting there is entirely inside that system -- the
    # position was opened in it and the declared level is in it. Refusing that window would
    # call a coordinate change a crossing when nothing crossed. The excursion reads its own
    # window the same way, and the two must not disagree about one frame.
    inside = [(session, reason) for session, reason in uncrossable if effective_date < session <= as_of and (end_before is None or session < end_before)]
    # The declared level is in the pre-split coordinate system and the closes after the
    # event are in the post-split one. Comparing them is arithmetic between two different
    # shares, and it would sell a position the market never took out. But the sessions
    # before the event are in the trader's own coordinate system and were audited honestly,
    # and a breach found among them already happened: an event two sessions later cannot
    # un-take-out a stop the market took out. So the audit runs up to the event and refuses
    # only from there. The current price is withheld either way -- it is on the far side of
    # the event and the declared stop is not.
    refuse_from, split_reason = inside[0] if inside else (None, "share_split")
    refused: tuple[dict[str, Any], float | None] | None = None
    if refuse_from is not None:
        current_price = None
        prefix = [(bar_date, row) for bar_date, row in dated_rows if effective_date <= bar_date < refuse_from and (end_before is None or bar_date < end_before)]
        refused = (
            {
                "state": "unavailable",
                "reason": "share_split_inside_stop_window" if split_reason == "share_split" else split_reason,
                "date": refuse_from.isoformat(),
                "requested_from": effective_date.isoformat(),
                # The sessions before the event were audited and came through clear. Saying
                # so is the difference between a window nothing was read in and one that was
                # read up to the point it stopped being readable.
                **(_bars_that_spoke(prefix) if prefix else {}),
            },
            None,
        )
        if refuse_from <= effective_date:
            return refused
    if require_session and not any(bar_date == effective_date for bar_date, _ in dated_rows):
        # The position existed inside its entry session, so a frame that skips that bar is
        # missing a session this level had to survive. Starting at the next bar would let a
        # breach the provider never delivered read as a window that came through clear.
        return {
            "state": "unavailable",
            "reason": "no_completed_bar_on_window_start",
            "requested_from": effective_date.isoformat(),
            "through": latest_date.isoformat(),
        }, current_price
    path_rows = [
        (bar_date, row)
        for bar_date, row in dated_rows
        if bar_date >= effective_date and (end_before is None or bar_date < end_before) and (refuse_from is None or bar_date < refuse_from)
    ]
    if not path_rows:
        return refused if refused is not None else ({"state": "unavailable", "reason": "no_completed_bars_in_stop_window"}, current_price)
    # A session whose own prices contradict each other is not a session, and which of the
    # four numbers is wrong is unknowable. It is refused here as well as in the structure
    # blocks, because this loop reads one column and the current price is read from another:
    # left alone, the audit would clear a window on Lows while the Close sold the position.
    relations = impossible_bar_relations(ordered)
    broken_sessions = frozenset() if relations is None else frozenset(timestamp.date() for timestamp, flagged in zip(ordered.index, relations) if flagged)
    intraday = basis == "completed_daily_low"
    column = "Low" if intraday else "Close"
    unreadable = "invalid_low_in_stop_window" if intraday else "invalid_close_in_stop_window"
    breach_key = "breach_low" if intraday else "breach_close"
    # A stop is a price the position transacts at, so reaching it is enough. A structural
    # invalidation is a threshold the thesis has to be carried through -- the condition a
    # caller writes beside one says "below" -- and a close that stopped exactly on it did
    # not go below it.
    crossed_level = (lambda value: value <= protective_level) if intraday else (lambda value: value < protective_level)
    for bar_date, row in path_rows:
        # The sessions before this one were audited and came through clear. Saying so is the
        # difference between a window nothing was read in and one that was read up to the
        # point it stopped being readable.
        spoken = [(spoken_date, spoken_row) for spoken_date, spoken_row in path_rows if spoken_date < bar_date]
        broke_off = ({"state": "unavailable", "reason": unreadable, "date": bar_date.isoformat(), **(_bars_that_spoke(spoken) if spoken else {})}, current_price)
        if bar_date in broken_sessions:
            return ({"state": "unavailable", "reason": "invalid_ohlc_history", "date": bar_date.isoformat(), **(_bars_that_spoke(spoken) if spoken else {})}, None)
        try:
            level_price = float(row[column])
        except (TypeError, ValueError):
            return broke_off
        if not math.isfinite(level_price) or level_price <= 0:
            return broke_off
        if crossed_level(level_price):
            # A session that opened below the level never offered the level's price; the
            # record says so rather than letting the stop read as if it had been filled there.
            opened: float | None = None
            if "Open" in row.index:
                try:
                    opened = float(row["Open"])
                except (TypeError, ValueError):
                    opened = None
                if opened is not None and (not math.isfinite(opened) or opened <= 0):
                    opened = None
            checked = [checked_date for checked_date, _ in path_rows if checked_date <= bar_date]
            # The audit stopped here, so the record stops here: reporting the whole window
            # would claim sessions after the breach were examined when the loop never
            # reached them, and after a breach there is nothing left to examine.
            return {
                "state": "breached",
                "basis": basis,
                "from": effective_date.isoformat(),
                "through": bar_date.isoformat(),
                "first_bar_checked": checked[0].isoformat(),
                "last_bar_checked": bar_date.isoformat(),
                "bars_checked": len(checked),
                "breach_date": bar_date.isoformat(),
                breach_key: level_price,
                "breach_open": opened,
                "gap_through_stop": None if opened is None else opened < protective_level,
            }, current_price
    if refused is not None:
        return refused
    if end_before is not None:
        if latest_date >= end_before:
            # A bar past the window's end proves every session inside it was seen.
            return {
                "state": "clear",
                "basis": basis,
                "from": effective_date.isoformat(),
                "through": (end_before - timedelta(days=1)).isoformat(),
                **_bars_that_spoke(path_rows),
            }, current_price
        return {
            "state": "unavailable",
            "reason": "history_ends_before_stop_raise",
            "requested_from": effective_date.isoformat(),
            "last_available": latest_date.isoformat(),
            "requested_through": (end_before - timedelta(days=1)).isoformat(),
            **_bars_that_spoke(path_rows),
        }, current_price
    if latest_date < as_of:
        # No breach in the bars that exist. A later missing bar cannot prove HOLD,
        # but it could never have erased a breach found above either.
        return {
            "state": "unavailable",
            "reason": "history_ends_before_as_of",
            "requested_from": effective_date.isoformat(),
            "last_available": latest_date.isoformat(),
            "requested_through": as_of.isoformat(),
            **_bars_that_spoke(path_rows),
        }, current_price
    return {
        "state": "clear",
        "basis": basis,
        "from": effective_date.isoformat(),
        "through": latest_date.isoformat(),
        **_bars_that_spoke(path_rows),
    }, current_price


# Where each component capability keeps the word `ticker.risk` reads, alongside the plane it
# settles. A path rather than one shared key name because these are four capabilities that
# were designed apart, and renaming an output to make this table shorter would move a field
# every existing reader already reads.
_COMPONENT_PLANES = {
    "market.snapshot": ("market", ("regime", "judgment")),
    "ticker.qualify": ("eligibility", ("eligibility_state",)),
    "ticker.setup": ("setup", ("setup_state",)),
    "ticker.fundamentals": ("fundamentals", ("fundamentals_state",)),
}

# Derived from the builder rather than listed, so a key added to the envelope contract is one
# an attachment is required to carry without anybody remembering to come back here.
_ENVELOPE_KEYS = frozenset(envelope("contract.probe"))


def _attest_components(
    evidence: dict[str, Any], attached: Any, *, ticker: str, as_of: str
) -> list[dict[str, Any]]:
    """Turn attached component envelopes into the attested evidence the reducer will accept.

    Nothing here is trusted for being handed in. An envelope has to be one of the four
    capabilities that settle a plane, and it has to be about this ticker and this session --
    the two ways a real envelope goes wrong are being about another stock and being about
    another day, and both look exactly like a good one until they are compared. The word
    comes from the envelope's own payload rather than from anything the caller typed beside
    it, so an envelope attached under a state word that contradicts it publishes the
    envelope's word and not the caller's.

    A refused envelope is reported rather than dropped: the plane simply goes on being
    unattested, and the reference says which check it failed, because "your evidence did not
    count" with no reason attached sends a reader to re-run a capability that was fine.
    """

    if not isinstance(attached, list):
        raise RequestError("evidence must be a list of capability envelopes", "evidence")
    references: list[dict[str, Any]] = []
    for index, item in enumerate(attached):
        if not isinstance(item, Mapping) or not _ENVELOPE_KEYS <= set(item):
            # Carrying the four fields this function reads is not the same as being an
            # envelope: a dict assembled by hand can hold the operation, the word, the session
            # and the status while holding none of the rest, and four of those reproduce the
            # defect this channel exists to close. The shape is what the capabilities emit.
            raise RequestError(f"evidence[{index}] is not a capability envelope", "evidence")
        operation = item.get("operation")
        plane_path = _COMPONENT_PLANES.get(operation if isinstance(operation, str) else "")
        if plane_path is None:
            raise RequestError(
                f"evidence[{index}] is {operation!r}; ticker.risk reads {', '.join(sorted(_COMPONENT_PLANES))}",
                "evidence",
            )
        plane, path = plane_path
        if any(reference["plane"] == plane for reference in references):
            # Both may be about this ticker and this session, so neither check below sees it,
            # and keeping the last hands the verdict to argument order. Attaching a stale run
            # beside a fresh one is the ordinary way a caller gets here.
            raise RequestError(f"two envelopes both settle {plane}; attach one", "evidence")
        payload = item.get("data")
        payload = payload if isinstance(payload, Mapping) else {}
        state: Any = payload
        for key in path:
            state = state.get(key) if isinstance(state, Mapping) else None
        envelope_ticker = payload.get("ticker") if plane != "market" else None
        envelope_as_of = item.get("as_of", {}).get("date") if isinstance(item.get("as_of"), Mapping) else None
        reference = {
            "operation": operation,
            "ticker": envelope_ticker,
            "as_of": envelope_as_of,
            "status": item.get("status"),
        }
        refusal = None
        if plane != "market" and envelope_ticker != ticker:
            refusal = "envelope_is_about_another_ticker"
        elif envelope_as_of != as_of:
            refusal = "envelope_is_from_another_session"
        elif item.get("status") not in {"ok", "partial"} or not item.get("sources"):
            # `partial` is admissible -- a market read can be favorable with context evidence
            # missing, and fundamentals can support convergence without every optional figure.
            # An empty `sources` list is not: it is the envelope saying it reached no provider,
            # and that emptiness beside a BUY-READY is the tell the original defect published.
            refusal = "envelope_measured_nothing"
        elif state is None:
            refusal = "envelope_carries_no_state_for_this_plane"
        if refusal is not None:
            references.append({**reference, "plane": plane, "refused": refusal})
            # Beside whatever the caller declared for this plane rather than over it: a
            # refused envelope withdraws a pass and must not withdraw a declared failure,
            # which is conservative and binds on its own terms.
            declared = evidence.get(plane)
            declared = dict(declared) if isinstance(declared, Mapping) else ({"state": declared} if declared is not None else {})
            evidence[plane] = {**declared, "attestation_refused": refusal}
            continue
        # The word the envelope reached, over whatever the caller typed -- except where what
        # they typed was a failure or a wait. Those bind on their own terms and only ever make
        # the verdict more cautious, and an envelope raising the plane back to a pass would
        # have overruled a person who looked at this stock with a capability that did not.
        declared = evidence.get(plane)
        declared_state = declared.get("state") if isinstance(declared, Mapping) else declared
        if declared_state is not None and is_non_passing(declared_state):
            # Reported rather than silent: the envelope was read, and a reader looking at a
            # verdict more cautious than their evidence needs to see which word did it.
            references.append({**reference, "plane": plane, "state": state, "yielded_to_declared": declared_state})
            evidence[plane] = {"state": declared_state}
            continue
        references.append({**reference, "plane": plane, "state": state})
        evidence[plane] = {"state": state, "attested_by": reference}
    return references


# The four columns this capability actually reads a price out of. Volume is not among them --
# nothing here decides on it -- and the corporate-action column is an event rather than a price,
# so it stays under the rules the split audit already holds it to.
_AUDITED_COLUMNS = ("Open", "High", "Low", "Close")
