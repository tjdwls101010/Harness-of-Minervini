"""Market and universe evidence composition."""

from __future__ import annotations

from typing import Any, Callable, Mapping
from ..clock import AnalysisClock, resolve_as_of
from ..contracts import RequestError, envelope
from ..market import build_market_candidates, evaluate_market_snapshot, evidence_quality
from ..market_evidence import build_market_evidence, carries_a_readable_bar
from ..providers import ProviderSnapshot, ProviderUnavailable
from ..providers.nasdaq import SecurityRecord
from ..runtime import Runtime
from ..setup_structure import read_bars

from . import _as_of, _cached_provider, _clean_request, _clock, _missing_provider, _named_doctrine_ids, _source, _stale_price_gap


def _candidate_row(record: SecurityRecord) -> dict[str, Any]:
    exchange = record.exchange.upper()
    exchange = {
        "NYSE AMERICAN": "NYSEAMERICAN",
        "NYSE NATIONAL": "NYSE",
        "CBOE BZX": "CBOE",
    }.get(exchange, exchange)
    return {
        "instrument_id": record.instrument_id,
        "ticker": record.symbol,
        "exchange": exchange,
        "listing_country": "US",
        "instrument_type": record.instrument_type,
        "is_adr": record.is_adr,
        "origins": ["nasdaq_security_master"],
    }


def _market_candidates(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    limit = request.get("limit", 50)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise RequestError("limit must be a positive integer", "limit")
    try:
        historical = request.get("as_of") is not None and clock.date != resolve_as_of().date
        snapshot = _cached_provider(
            runtime,
            request,
            clock,
            capability="market.candidates",
            provider="nasdaq",
            operation="historical_security_master" if historical else "current_security_master",
            params={"historical": historical},
            fetch=lambda: runtime.security_master(request.get("as_of")),
            ttl_seconds=None if historical else 900,
        )
    except ProviderUnavailable as error:
        return envelope(
            "market.candidates",
            request=_clean_request(request),
            as_of=_as_of(clock),
            status="unavailable",
            data={"candidates": [], "exclusions": {"total_count": 0, "reason_counts": {}, "samples": [], "sample_limit": 0}, "page": {}},
            missing=[_missing_provider(error)],
        )
    try:
        result = build_market_candidates(
            (_candidate_row(record) for record in snapshot.data),
            limit=limit,
            cursor=request.get("cursor"),
        )
    except ValueError as error:
        raise RequestError(str(error), "cursor") from error
    return envelope(
        "market.candidates",
        request=_clean_request(request),
        as_of=_as_of(clock),
        data=result,
        sources=[_source(snapshot.meta)],
        next_capabilities=["ticker.qualify"] if result["candidates"] else [],
    )


def _leaders_within_limit(rows: list[dict[str, Any]] | None, limit: int) -> list[dict[str, Any]]:
    """Each ranked leader once, in rank order, no more of them than the caller asked for.

    The limit is passed to the provider, and a provider that answers with more rows than it
    was asked for would otherwise decide how many external calls this snapshot makes -- two
    per name. It would also decide the reducer's denominator: the leaders past the limit are
    published unread, and the majority the leader signal counts is a majority of the list it
    was handed. The observations the caller asked for and the leaders the snapshot publishes
    are the same set. The seen-set is a set because the fan-out is the one place in this
    capability where the list can be long enough for a scan per row to matter.
    """

    bounded: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows or []:
        symbol = row.get("ticker") if isinstance(row, Mapping) else None
        if not isinstance(symbol, str) or symbol in seen:
            continue
        seen.add(symbol)
        bounded.append(row)
        if len(bounded) >= limit:
            break
    return bounded


def _ohlcv_rows(frame: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Completed rows from a provider frame, or none at all and the reason there are none.

    Through the reader that owns what a usable history is, because the readers below this one
    each defend a different part of what it checks and the gaps between them reach the regime
    word. A frame of complex numbers lost its imaginary part on the way through `float()` and
    read as an ordinary advance; a frame of booleans became a flat line at 1.0 sitting on its
    own 52-week low; an index of epoch nanoseconds was published as a session date; and a
    session printed twice at two clock times counted as two sessions, which is how a 259-session
    history satisfied a window that wanted 260.
    """

    bars, rejection = read_bars(frame)
    if bars is None:
        return [], rejection
    rows: list[dict[str, Any]] = []
    for index, row in bars.iterrows():
        timestamp = index.date().isoformat() if hasattr(index, "date") else str(index)
        rows.append(
            {
                "date": timestamp,
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "volume": row.get("Volume"),
                "completed": True,
            }
        )
    return rows, None


def _ranked_groups(rows: list[dict[str, Any]], group_key: str, as_of: str) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "name": row[group_key],
            "rank": rank,
            "rating": row.get("avg_rs"),
            "as_of": as_of,
        }
        for rank, row in enumerate(rows, start=1)
    ]


def _ranked_leaders(rows: list[dict[str, Any]], as_of: str) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "rank": rank,
            "rating": row.get("rs_rating"),
            "as_of": as_of,
        }
        for rank, row in enumerate(rows, start=1)
    ]


def _optional_leader_read(
    runtime: Runtime,
    request: Mapping[str, Any],
    clock: AnalysisClock,
    symbol: str,
    operation: str,
    fetch: Callable[[], ProviderSnapshot[Any]],
    provider_missing: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    *,
    ttl_seconds: int | None = None,
) -> ProviderSnapshot[Any] | None:
    """One leader's optional read, or that leader's gap -- never the whole snapshot's.

    Reading each leader's own bars and taxonomy turned one provider call into two per name,
    and every one of them is optional evidence. A boundary is contracted to raise
    ProviderUnavailable, so anything else escaping is a bug rather than a gap; the bug still
    belongs to the one leader it happened under, and its type is named in the reason so it
    stays findable instead of being smoothed into an ordinary unavailability.
    """

    try:
        snapshot = _cached_provider(
            runtime,
            request,
            clock,
            capability="market.snapshot",
            provider="yfinance",
            operation=operation,
            params={"ticker": symbol},
            fetch=fetch,
            ttl_seconds=ttl_seconds,
        )
    except ProviderUnavailable as error:
        withheld = _missing_provider(error, required=False)
        withheld["ticker"] = symbol
        provider_missing.append(withheld)
        return None
    except Exception as error:
        provider_missing.append(
            {
                "id": f"leader_{operation}",
                "ticker": symbol,
                "reason": f"provider_raised_outside_its_contract:{type(error).__name__}",
                "required": False,
                "retryable": False,
            }
        )
        return None
    sources.append(_source(snapshot.meta))
    return snapshot


def _market_snapshot(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    as_of = clock.date.isoformat()
    leader_limit = request.get("leader_limit", 20)
    if not isinstance(leader_limit, int) or isinstance(leader_limit, bool) or not 1 <= leader_limit <= 100:
        raise RequestError("leader_limit must be an integer from 1 to 100", "leader_limit")
    trade_traction = request.get("trade_traction")
    if trade_traction is not None and trade_traction not in {"supports", "contradicts", "mixed", "needs_input"}:
        raise RequestError("trade_traction must be supports, contradicts, mixed, or needs_input", "trade_traction")

    sources: list[dict[str, Any]] = []
    succeeded: list[ProviderSnapshot[Any]] = []
    provider_missing: list[dict[str, Any]] = []

    def collect(fetch: Callable[[], ProviderSnapshot[Any]]) -> ProviderSnapshot[Any] | None:
        try:
            snapshot = fetch()
        except ProviderUnavailable as error:
            provider_missing.append(_missing_provider(error, required=False))
            return None
        sources.append(_source(snapshot.meta))
        stale_price = _stale_price_gap(snapshot.meta)
        if stale_price is not None:
            provider_missing.append(stale_price)
            return None
        succeeded.append(snapshot)
        return snapshot

    qqq = collect(
        lambda: _cached_provider(
            runtime,
            request,
            clock,
            capability="market.snapshot",
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": "QQQ"},
            fetch=lambda: runtime.price_history("QQQ", as_of),
        )
    )
    finviz = collect(
        lambda: _cached_provider(
            runtime,
            request,
            clock,
            capability="market.snapshot",
            provider="finviz",
            operation="raw_snapshot",
            params={},
            fetch=lambda: runtime.finviz_breadth(as_of),
            ttl_seconds=900,
        )
    )
    sectors = collect(
        lambda: _cached_provider(
            runtime,
            request,
            clock,
            capability="market.snapshot",
            provider="ibd-rs-rating",
            operation="sector_ranking",
            params={},
            fetch=lambda: runtime.sector_ranking(as_of),
        )
    )
    industries = collect(
        lambda: _cached_provider(
            runtime,
            request,
            clock,
            capability="market.snapshot",
            provider="ibd-rs-rating",
            operation="industry_ranking",
            params={},
            fetch=lambda: runtime.industry_ranking(as_of),
        )
    )
    leaders = collect(
        lambda: _cached_provider(
            runtime,
            request,
            clock,
            capability="market.snapshot",
            provider="ibd-rs-rating",
            operation="top",
            params={"limit": leader_limit},
            fetch=lambda: runtime.market_leaders(as_of, leader_limit),
        )
    )

    sector_rows = _ranked_groups(sectors.data, "sector", as_of) if sectors is not None else None
    industry_rows = _ranked_groups(industries.data, "industry", as_of) if industries is not None else None
    leader_rows = _leaders_within_limit(_ranked_leaders(leaders.data, as_of), leader_limit) if leaders is not None else None
    # The RS source ranks a leader and says nothing about how it is behaving, so the behavior
    # reading has to come from the leader's own completed bars. Withheld or session-behind
    # history is left withheld: the evidence adapter reports the gap rather than a word.
    leader_history: dict[str, Any] = {}
    # Group membership comes from a mutable current classification, so it can only be read for
    # the current session. Asking for it against a past `as_of` would attach today's taxonomy
    # to a historical snapshot, which is the one thing the classification rule forbids -- the
    # membership is left unread instead, and every group reports that it was.
    reads_membership = clock.date == resolve_as_of().date
    leader_groups: dict[str, Any] = {}
    for symbol in (row["ticker"] for row in leader_rows or []):
        history = _optional_leader_read(
            runtime, request, clock, symbol, "daily_bars", lambda: runtime.price_history(symbol, as_of), provider_missing, sources
        )
        if history is not None:
            stale_price = _stale_price_gap(history.meta)
            if stale_price is not None:
                stale_price["ticker"] = symbol
                stale_price["required"] = False
                provider_missing.append(stale_price)
            else:
                rows, rejection = _ohlcv_rows(history.data)
                if carries_a_readable_bar(rows):
                    leader_history[symbol] = rows
                else:
                    # A snapshot that arrived and carried nothing readable is a gap the
                    # payload already shows; without this the envelope counts it as read. The
                    # reason is the reader's own, because the payload says `unavailable` for a
                    # history that was withheld and for one that was not prices, and those are
                    # different findings about the leader.
                    provider_missing.append(
                        {"id": "leader_price_history", "ticker": symbol, "reason": rejection or "daily_bars_unreadable", "required": False}
                    )
        if not reads_membership:
            continue
        classification = _optional_leader_read(
            runtime,
            request,
            clock,
            symbol,
            "current_classification",
            lambda: runtime.current_classification(symbol),
            provider_missing,
            sources,
            ttl_seconds=900,
        )
        if classification is None:
            continue
        if isinstance(classification.data, Mapping):
            leader_groups[symbol] = dict(classification.data)
        else:
            provider_missing.append(
                {"id": "leader_classification", "ticker": symbol, "reason": "classification_not_a_record", "required": False}
            )
    if not reads_membership and leader_rows:
        provider_missing.append(
            {"id": "leader_classification", "reason": "historical_session_has_no_current_classification", "required": False}
        )
    qqq_rows, qqq_rejection = _ohlcv_rows(qqq.data) if qqq is not None else ([], None)
    if qqq_rejection is not None:
        provider_missing.append({"id": "qqq_daily_bars", "reason": qqq_rejection, "required": False})
    evidence = build_market_evidence(
        as_of=clock.date,
        qqq_daily_ohlcv=qqq_rows if qqq is not None else None,
        finviz_html=finviz.data if finviz is not None else None,
        sector_rows=sector_rows,
        industry_rows=industry_rows,
        leader_rows=leader_rows,
        trade_traction={"state": trade_traction} if trade_traction is not None else None,
        leader_history=leader_history,
        leader_groups=leader_groups or None,
    )
    result = evaluate_market_snapshot(evidence)
    section_missing = [
        {
            "id": f"breadth.{name}",
            "reason": section.get("reason", "section_unavailable"),
            "required": False,
        }
        for name, section in evidence["breadth"].get("sections", {}).items()
        if section.get("state") == "unavailable"
    ]
    missing = [*provider_missing, *result["missing"], *section_missing]
    if trade_traction == "needs_input":
        missing.append({"id": "trade_traction", "reason": "user_feedback_required", "required": True})
    if not succeeded:
        # A snapshot that was fetched but discarded is provenance, not evidence.
        status = "unavailable"
    elif trade_traction in {None, "needs_input"}:
        status = "needs_input"
    elif missing:
        status = "partial"
    else:
        status = "ok"
    # The reducer graded completeness over the gaps it was handed; the envelope's list also
    # holds every provider, classification and breadth-section gap collected here. Restating
    # the grade over the merged list keeps one answer to one question -- before this, a
    # response could carry status "partial" beside evidence_quality "complete".
    data = {
        **result,
        "leaders": evidence["leaders"] or [],
        "missing": missing,
        "evidence_quality": evidence_quality(result["signal_vector"], missing),
    }
    return envelope(
        "market.snapshot",
        request=_clean_request(request),
        as_of=_as_of(clock),
        status=status,
        data=data,
        signals=result["signal_vector"],
        missing=missing,
        sources=sources,
        doctrine_ids=["scope.data_integrity", *sorted(_named_doctrine_ids(data) - {"scope.data_integrity"})],
        next_capabilities=["market.candidates", "ticker.qualify"] if succeeded else [],
    )
