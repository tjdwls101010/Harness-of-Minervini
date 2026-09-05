"""Company identity, fundamentals and peer evidence composition."""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Mapping
import pandas as pd
from ..dates import request_date as _request_date
from ..clock import resolve_as_of
from ..contracts import RequestError, envelope
from ..fundamentals import ACCOUNTING_INTEGRITY_WORDS as FUNDAMENTALS_ACCOUNTING_INTEGRITY, GOING_CONCERN_WORDS as FUNDAMENTALS_GOING_CONCERN, LEADER_CATEGORIES as FUNDAMENTALS_LEADER_CATEGORIES, MARKET_REGIMES as FUNDAMENTALS_MARKET_REGIMES, evaluate_fundamentals
from ..peer_collection import collect_same_industry_peer_rows
from ..peers import compare_same_industry_peers
from ..providers import ProviderUnavailable
from ..runtime import Runtime
from ..setup_structure import session_index

from . import PriceRead, _as_of, _cached_provider, _clean_request, _clock, _missing_provider, _named_doctrine_ids, _price_read, _source, _stale_price_gap, _ticker


def _ticker_cik(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    """Resolve a symbol to the SEC filing identity `ticker.fundamentals` asks for by `--cik`.

    Every refusal here is the same refusal `--cik` exists for. `company_tickers.json` is a
    mutable current snapshot -- a symbol can be reassigned -- so answering a past session from
    it would be current security-master data relabelled as historical, and the analyst would be
    handed an identity the harness cannot vouch for wearing the date they asked about. It
    answers for the current session and says what the answer is; asserting that the identity
    held back then is what `--cik` records, and it stays the analyst's assertion.
    """

    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    echo = _clean_request({**request, "ticker": ticker})

    def unresolved(gap: dict[str, Any], sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return envelope(
            "ticker.cik",
            request=echo,
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker},
            missing=[gap],
            sources=sources or [],
        )

    if request.get("as_of") is not None and clock.date != resolve_as_of().date:
        # `ticker.fundamentals` points here when it wants a CIK for a past session, so this
        # refusal is where that pointer lands. Saying only that the map is current leaves the
        # analyst to work out that dropping the date is what answers, and a gap an analyst has
        # to infer their way out of is the gap this capability was written to close.
        return unresolved(
            {
                "id": "cik",
                "reason": "ticker_to_cik_map_is_current_only",
                "required": True,
                "detail": "run ticker.cik for the current session; asserting that identity also held at the requested one is what ticker.fundamentals --cik records",
            }
        )
    try:
        snapshot = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.cik",
            provider="sec",
            operation="company_tickers",
            params={},
            fetch=runtime.company_tickers,
            # The same lifetime every other current-only snapshot here carries. Held without
            # one, a map whose being current is the reason it cannot answer for a past session
            # was frozen for the rest of the session anyway.
            ttl_seconds=900,
        )
    except ProviderUnavailable as error:
        return unresolved(_missing_provider(error))

    record = snapshot.data.get(ticker)
    if record is None:
        # The source answered and this symbol is not in it, which is a different thing from no
        # answer -- and the reason is the one an analyst can act on: no SEC registrant files
        # under this symbol, so there is no CIK to pass rather than one this run failed to read.
        return unresolved({"id": "cik", "reason": "ticker_not_found", "required": True}, [_source(snapshot.meta)])
    return envelope(
        "ticker.cik",
        request=echo,
        as_of=_as_of(clock),
        status="ok",
        data={"ticker": ticker, "cik": record["cik"], "title": record["title"]},
        sources=[_source(snapshot.meta)],
        next_capabilities=["ticker.fundamentals"],
    )


def _fundamentals(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    cik = request.get("cik")
    if cik is not None and (not isinstance(cik, str) or not cik.isdigit() or len(cik) > 10):
        raise RequestError("cik must contain at most ten digits", "cik")
    # What the filings do not carry and an analyst may. Refused here against the same
    # vocabularies the evaluator holds, so a word it could only misread never reaches it.
    declared: dict[str, str | None] = {}
    for field, allowed in (("going_concern", FUNDAMENTALS_GOING_CONCERN), ("accounting_integrity", FUNDAMENTALS_ACCOUNTING_INTEGRITY), ("leader_category", FUNDAMENTALS_LEADER_CATEGORIES), ("market_regime", FUNDAMENTALS_MARKET_REGIMES)):
        value = request.get(field)
        if value is not None and (not isinstance(value, str) or value not in allowed):
            raise RequestError(f"{field} must be one of {', '.join(allowed)}", field)
        declared[field] = value
    breakout_date = _request_date(request.get("breakout_date"), "breakout_date") if request.get("breakout_date") is not None else None
    if breakout_date is not None and breakout_date > clock.date:
        return envelope(
            "ticker.fundamentals",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="needs_input",
            data={"ticker": ticker, "fundamentals_state": "incomplete"},
            missing=[{"id": "breakout_date", "reason": "breakout_date_after_as_of", "required": True}],
        )
    if request.get("as_of") is not None and cik is None:
        return envelope(
            "ticker.fundamentals",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="needs_input",
            data={"ticker": ticker, "fundamentals_state": "incomplete"},
            missing=[{"id": "cik", "reason": "stable_historical_identity_required", "required": True}],
            # A required value the interface does not carry is a gap an analyst cannot close by
            # reading the envelope. Naming the capability that produces one is the whole of what
            # was missing here -- the lookup itself was always there, one call inside this one.
            next_capabilities=["ticker.cik"],
        )
    try:
        snapshot = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.fundamentals",
            provider="sec",
            operation="filed_facts",
            params={"ticker": ticker, "cik": cik},
            fetch=lambda: runtime.fundamentals_evidence(ticker, clock.date.isoformat(), cik),
        )
    except ProviderUnavailable as error:
        return envelope(
            "ticker.fundamentals",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "fundamentals_state": "incomplete"},
            missing=[_missing_provider(error)],
        )
    # The price is not filed evidence, so a provider that cannot answer does not stop the
    # filings from reaching a verdict: the gap is reported where the multiple would have been
    # and marked not required.
    sources = [_source(snapshot.meta)]
    provider_missing: list[dict[str, Any]] = []
    closes: dict[str, float | None] = {"last_close": None, "breakout_close": None}
    try:
        prices, _, _ = _price_read(runtime, request, clock, ticker, PriceRead("ticker.fundamentals"))
    except ProviderUnavailable as error:
        provider_missing.append({**_missing_provider(error), "required": False})
    else:
        sources.append(_source(prices.meta))
        if prices.meta.stale:
            # A close from an earlier session published as the last completed one is a price
            # nobody could have paid on the session this envelope is dated. The multiple is
            # withheld rather than dated wrongly, and the gap says which session was reached.
            provider_missing.append({"id": "stale_price_evidence", "provider": prices.meta.provider, "reason": "price_history_behind_requested_session", "through": prices.meta.as_of.isoformat() if prices.meta.as_of else None, "required": False})
        else:
            closes = _valuation_closes(prices.data, as_of=clock.date, breakout_date=breakout_date)
        if breakout_date is not None and not prices.meta.stale and closes["breakout_close"] is None:
            # The caller named a date the tape has no completed session for. Dropping it and
            # carrying on left the envelope echoing the date in `request` while the reading
            # beside it said no breakout date had been supplied.
            return envelope(
                "ticker.fundamentals",
                request=_clean_request({**request, "ticker": ticker}),
                as_of=_as_of(clock),
                status="needs_input",
                data={"ticker": ticker, "fundamentals_state": "incomplete"},
                sources=sources,
                missing=[{"id": "breakout_date", "reason": "no_completed_session_on_breakout_date", "required": True}],
            )
    result = evaluate_fundamentals(
        snapshot.data,
        as_of=clock.date.isoformat(),
        # The date the caller gave, whether or not a close could be found for it. Dropping it
        # made the reading name a missing breakout date beside a request that carried one.
        breakout_date=breakout_date.isoformat() if breakout_date is not None else None,
        breakout_close=closes["breakout_close"],
        last_close=closes["last_close"],
        **declared,
    )
    missing = [{"id": item, "reason": "filed_evidence_missing", "required": True} for item in result["missing"]] + provider_missing
    # A gap of any kind is a partial answer. `status` describes contract completeness rather
    # than verdict polarity, so a negative verdict a declaration settled is still an answer
    # built on filings that never arrived -- and reading it as `ok` told the caller the
    # evidence was whole while four required items sat in `missing` beside it.
    status = "partial" if missing else "ok"
    # Every reading in this evaluator names the claim it came from, so the citation list is
    # read off the payload rather than kept beside it. A hand-maintained list of one said the
    # result used one claim while its readings named two dozen, and the reader's index into
    # them was the thing that went missing.
    base = ["scope.data_integrity"]
    doctrine_ids = base + sorted(_named_doctrine_ids(result) - set(base))
    return envelope(
        "ticker.fundamentals",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        data={"ticker": ticker, **result},
        signals=result["signals"],
        missing=missing,
        sources=sources,
        doctrine_ids=doctrine_ids,
        next_capabilities=["ticker.peers", "ticker.risk"],
    )


def _valuation_closes(frame: Any, *, as_of: date, breakout_date: date | None) -> dict[str, float | None]:
    """The last completed close, and the close of the breakout session if the history holds one.

    Same reading rules as every other consumer of these bars: one session printed twice keeps
    its last print, sessions past ``as_of`` are not completed yet, and a price that is not a
    finite positive number is not a price. A breakout date that names no completed session
    returns nothing rather than the nearest bar -- the nearest bar is a different session, and
    a multiple computed on it is a multiple nobody could have paid.
    """

    closes: dict[str, float | None] = {"last_close": None, "breakout_close": None}
    if not isinstance(frame, pd.DataFrame) or frame.empty or "Close" not in frame.columns:
        return closes
    timestamps = pd.to_datetime(frame.index, errors="coerce")
    if timestamps.isna().any():
        return closes
    timestamps = session_index(timestamps)
    ordered = frame.copy()
    ordered.index = timestamps
    # Stable, so that two prints of one session stay in the order the provider sent them and
    # `keep="last"` keeps the last one it actually sent. The default sort is free to reorder
    # equal timestamps, which made "the last print wins" pick whichever it happened to move.
    ordered = ordered.sort_index(kind="stable")
    ordered = ordered[~ordered.index.normalize().duplicated(keep="last")]
    by_date = {}
    for timestamp, row in ordered.iterrows():
        if timestamp.date() > as_of:
            continue
        try:
            close = float(row["Close"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(close) and close > 0:
            by_date[timestamp.date()] = close
    if not by_date:
        return closes
    closes["last_close"] = by_date[max(by_date)]
    if breakout_date is not None:
        closes["breakout_close"] = by_date.get(breakout_date)
    return closes


def _peers(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    current_clock = resolve_as_of()
    limit = request.get("limit", 10)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise RequestError("limit must be an integer from 1 to 20", "limit")
    if request.get("as_of") is not None and clock.date != current_clock.date:
        return envelope(
            "ticker.peers",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "comparison_state": "incomplete", "target": None, "peers": []},
            missing=[
                {
                    "id": "current_classification",
                    "provider": "yfinance",
                    "reason": "historical_classification_unavailable",
                    "required": True,
                    "attempts": 0,
                    "retryable": False,
                }
            ],
        )

    sources: list[dict[str, Any]] = []
    try:
        classification = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.peers",
            provider="yfinance",
            operation="current_classification",
            params={"ticker": ticker},
            fetch=lambda: runtime.current_classification(ticker),
            ttl_seconds=900,
        )
        master = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.peers",
            provider="nasdaq",
            operation="current_security_master",
            params={},
            fetch=lambda: runtime.security_master(None),
            ttl_seconds=900,
        )
        industry = str(classification.data["industry"])
        industry_rows = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.peers",
            provider="ibd-rs-rating",
            operation="industry_top",
            params={"industry": industry, "limit": limit + 1},
            fetch=lambda: runtime.industry_top(industry, clock.date.isoformat(), limit + 1),
        )
    except ProviderUnavailable as error:
        return envelope(
            "ticker.peers",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "comparison_state": "incomplete", "target": None, "peers": []},
            missing=[_missing_provider(error)],
        )
    sources.extend((_source(classification.meta), _source(master.meta), _source(industry_rows.meta)))

    provider_missing: list[dict[str, Any]] = []
    target_rating: Mapping[str, Any] | int | float = {}
    try:
        rating = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.peers",
            provider="ibd-rs-rating",
            operation="rating",
            params={"ticker": ticker},
            fetch=lambda: runtime.rs_rating(ticker, clock.date.isoformat()),
        )
    except ProviderUnavailable as error:
        provider_missing.append(_missing_provider(error))
    else:
        target_rating = rating.data
        sources.append(_source(rating.meta))

    symbols = [ticker]
    for row in industry_rows.data:
        symbol = row.get("ticker") if isinstance(row, Mapping) else None
        if isinstance(symbol, str) and symbol not in symbols:
            symbols.append(symbol)
    completed_prices: dict[str, Any] = {}
    for symbol in symbols:
        try:
            prices, _, _ = _price_read(runtime, request, clock, symbol, PriceRead("ticker.peers"))
        except ProviderUnavailable as error:
            missing = _missing_provider(error, required=symbol == ticker)
            missing["ticker"] = symbol
            provider_missing.append(missing)
        else:
            sources.append(_source(prices.meta))
            stale_price = _stale_price_gap(prices.meta)
            if stale_price is not None:
                stale_price["ticker"] = symbol
                stale_price["required"] = symbol == ticker
                provider_missing.append(stale_price)
            else:
                completed_prices[symbol] = prices.data

    try:
        collected = collect_same_industry_peer_rows(
            classification.data,
            master.data,
            industry_rows.data,
            target_rating,
            completed_prices,
            as_of=clock.date.isoformat(),
        )
    except ValueError as error:
        raise RequestError(str(error), "ticker") from error
    identity_missing = [
        {
            "id": f"peer_identity.{item['ticker']}",
            "ticker": item["ticker"],
            "reason": item["reason"],
            "required": item["ticker"] == ticker,
        }
        for item in collected["missing"]
    ]
    if collected["target"] is None:
        result = {
            "comparison_state": "incomplete",
            "target": None,
            "peer_count": 0,
            "peers": [],
            "rank_basis": [],
            "missing": [],
            "exclusions": [],
        }
    else:
        try:
            result = compare_same_industry_peers(collected["target"], collected["candidates"])
        except ValueError as error:
            raise RequestError(str(error), "ticker") from error
        result["peers"] = result["peers"][:limit]
        result["peer_count"] = len(result["peers"])
    evidence_missing = [
        {
            "id": f"peer_evidence.{item.get('ticker') or item.get('instrument_id')}",
            "ticker": item.get("ticker"),
            "reason": "required_peer_evidence_missing",
            "fields": item["fields"],
            "required": item.get("ticker") == ticker,
        }
        for item in result["missing"]
    ]
    missing = [*provider_missing, *identity_missing, *evidence_missing]
    status = "ok" if result["comparison_state"] == "complete" and not missing else "partial"
    return envelope(
        "ticker.peers",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        data={
            "ticker": ticker,
            "sector": classification.data["sector"],
            "industry": classification.data["industry"],
            "industry_id": classification.data["industry_id"],
            **result,
        },
        missing=missing,
        sources=sources,
        doctrine_ids=["scope.data_integrity"],
        next_capabilities=["ticker.risk"],
    )
