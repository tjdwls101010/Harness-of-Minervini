"""Compose provider snapshots and pure evaluators into public v2 operations."""

from __future__ import annotations

import re
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable, Mapping

from .clock import AnalysisClock, resolve_as_of
from .chart import render_chart_artifacts
from .contracts import RequestError, envelope
from .doctrine import get_claim, validate as validate_doctrine
from .eligibility import EligibilityEvidence, evaluate_eligibility
from .fundamentals import evaluate_fundamentals
from .ledger import Ledger
from .market import build_market_candidates, evaluate_market_snapshot
from .market_evidence import build_market_evidence
from .peer_collection import collect_same_industry_peer_rows
from .peers import compare_same_industry_peers
from .providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta
from .providers.finviz import raw_snapshot as finviz_raw_snapshot
from .providers.nasdaq import SecurityRecord, current_security_master, historical_security_master
from .providers.rs import REQUIRED_PACKAGE_VERSION, industry_ranking_snapshot, industry_top_snapshot, rating_snapshot, sector_ranking_snapshot, top_snapshot
from .providers.sec import fetch_company_facts, fetch_company_submissions, fetch_company_tickers, normalize_filed_facts
from .providers.yfinance import completed_daily_bars, current_classification_snapshot
from .risk import reduce_risk
from .setup import evaluate_setup
from .setup_evidence import build_setup_evidence
from .technical import build_eligibility_evidence


PriceHistory = Callable[[str, str | None], ProviderSnapshot[Any]]
RatingSnapshot = Callable[[str, str | None], ProviderSnapshot[dict[str, Any]]]
SecurityMaster = Callable[[str | None], ProviderSnapshot[list[SecurityRecord]]]
LedgerFactory = Callable[[], Ledger]
FundamentalsEvidence = Callable[[str, str, str | None], ProviderSnapshot[dict[str, Any]]]
RankedRows = Callable[[str], ProviderSnapshot[list[dict[str, Any]]]]
MarketLeaders = Callable[[str, int], ProviderSnapshot[list[dict[str, Any]]]]
FinvizBreadth = Callable[[str], ProviderSnapshot[str]]
CurrentClassification = Callable[[str], ProviderSnapshot[dict[str, str]]]
IndustryTop = Callable[[str, str, int], ProviderSnapshot[list[dict[str, Any]]]]


def _default_price_history(ticker: str, as_of: str | None) -> ProviderSnapshot[Any]:
    return completed_daily_bars(ticker, as_of=as_of)


def _default_rs_rating(ticker: str, as_of: str | None) -> ProviderSnapshot[dict[str, Any]]:
    return rating_snapshot(ticker, as_of=as_of)


def _default_security_master(as_of: str | None) -> ProviderSnapshot[list[SecurityRecord]]:
    if as_of is not None and resolve_as_of(as_of).date != resolve_as_of().date:
        return historical_security_master(as_of)
    try:
        import requests
    except Exception as error:
        raise ProviderUnavailable("nasdaq", "requests_package_unavailable", operation="security_master") from error

    def request(url: str) -> str:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    return current_security_master(request)


def _default_fundamentals_evidence(ticker: str, as_of: str, cik: str | None) -> ProviderSnapshot[dict[str, Any]]:
    user_agent = os.environ.get("MINERVINI_SEC_USER_AGENT", "")
    if not user_agent:
        raise ProviderUnavailable("sec", "identifiable_user_agent_required", operation="filed_facts")
    try:
        import requests
    except Exception as error:
        raise ProviderUnavailable("sec", "requests_package_unavailable", operation="filed_facts") from error

    snapshots: list[ProviderSnapshot[Any]] = []
    resolved_cik = cik
    if resolved_cik is None:
        ticker_lookup = fetch_company_tickers(request_get=requests.get, user_agent=user_agent)
        snapshots.append(ticker_lookup)
        record = ticker_lookup.data.get(ticker)
        if record is None:
            raise ProviderUnavailable("sec", "ticker_not_found", operation="company_tickers")
        resolved_cik = record["cik"]
    facts = fetch_company_facts(resolved_cik, request_get=requests.get, user_agent=user_agent)
    submissions = fetch_company_submissions(resolved_cik, request_get=requests.get, user_agent=user_agent)
    snapshots.extend((facts, submissions))
    evidence = normalize_filed_facts(facts.data, submissions.data, as_of=as_of)
    content_hashes = [snapshot.meta.content_sha256 for snapshot in snapshots if snapshot.meta.content_sha256]
    return ProviderSnapshot(
        evidence,
        SnapshotMeta(
            provider="sec",
            retrieved_at=max(snapshot.meta.retrieved_at for snapshot in snapshots),
            as_of=date.fromisoformat(as_of),
            coverage={
                "kind": "filed_facts_as_of",
                "cik": resolved_cik,
                "documents": [dict(snapshot.meta.coverage) for snapshot in snapshots],
            },
            content_sha256=sha256("|".join(content_hashes).encode()).hexdigest() if content_hashes else None,
        ),
    )


def _default_finviz_breadth(as_of: str) -> ProviderSnapshot[str]:
    try:
        import requests
    except Exception as error:
        raise ProviderUnavailable("finviz", "requests_package_unavailable", operation="raw_snapshot") from error

    def fetch() -> str:
        response = requests.get(
            "https://finviz.com/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; MinerviniHarness/2.0)"},
            timeout=30,
        )
        response.raise_for_status()
        return response.text

    return finviz_raw_snapshot(fetch=fetch, as_of=as_of)


def _default_sector_ranking(as_of: str) -> ProviderSnapshot[list[dict[str, Any]]]:
    return sector_ranking_snapshot(as_of)


def _default_industry_ranking(as_of: str) -> ProviderSnapshot[list[dict[str, Any]]]:
    return industry_ranking_snapshot(as_of)


def _default_market_leaders(as_of: str, limit: int) -> ProviderSnapshot[list[dict[str, Any]]]:
    return top_snapshot(as_of, n=limit)


def _default_current_classification(ticker: str) -> ProviderSnapshot[dict[str, str]]:
    return current_classification_snapshot(ticker)


def _default_industry_top(industry: str, as_of: str, limit: int) -> ProviderSnapshot[list[dict[str, Any]]]:
    return industry_top_snapshot(industry, as_of, n=limit)


@dataclass(frozen=True)
class Runtime:
    """Replace only external boundaries in deterministic integration tests."""

    price_history: PriceHistory = field(default_factory=lambda: _default_price_history)
    rs_rating: RatingSnapshot = field(default_factory=lambda: _default_rs_rating)
    security_master: SecurityMaster = field(default_factory=lambda: _default_security_master)
    fundamentals_evidence: FundamentalsEvidence = field(default_factory=lambda: _default_fundamentals_evidence)
    sector_ranking: RankedRows = field(default_factory=lambda: _default_sector_ranking)
    industry_ranking: RankedRows = field(default_factory=lambda: _default_industry_ranking)
    market_leaders: MarketLeaders = field(default_factory=lambda: _default_market_leaders)
    finviz_breadth: FinvizBreadth = field(default_factory=lambda: _default_finviz_breadth)
    current_classification: CurrentClassification = field(default_factory=lambda: _default_current_classification)
    industry_top: IndustryTop = field(default_factory=lambda: _default_industry_top)
    ledger_factory: LedgerFactory = field(default_factory=lambda: Ledger)


def _clock(value: Any) -> AnalysisClock:
    try:
        return resolve_as_of(value)
    except ValueError as error:
        raise RequestError(str(error), "as_of") from error


def _as_of(clock: AnalysisClock) -> dict[str, Any]:
    return {
        "mode": clock.mode,
        "date": clock.date.isoformat(),
        "timezone": clock.timezone,
        "completed_session": clock.completed_session,
    }


def _clean_request(request: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in request.items() if value is not None}


def _ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker):
        raise RequestError("ticker must be a US-listed symbol", "ticker")
    return ticker


def _source(meta: SnapshotMeta) -> dict[str, Any]:
    return {
        "provider": meta.provider,
        "retrieved_at": meta.retrieved_at.isoformat(),
        "as_of": meta.as_of.isoformat() if meta.as_of is not None else None,
        "provider_version": meta.provider_version,
        "coverage": dict(meta.coverage),
        "stale": meta.stale,
        "content_sha256": meta.content_sha256,
    }


def _missing_provider(error: ProviderUnavailable, *, required: bool = True) -> dict[str, Any]:
    return {
        "id": error.operation or error.provider,
        "provider": error.provider,
        "reason": error.reason,
        "required": required,
        "attempts": error.attempts,
        "retryable": error.retryable,
    }


def _clock_operation(request: Mapping[str, Any]) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    return envelope(
        "clock",
        request=_clean_request(request),
        as_of=_as_of(clock),
        data={"date": clock.date.isoformat(), "mode": clock.mode},
    )


def _health(request: Mapping[str, Any]) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    dependencies: dict[str, dict[str, Any]] = {}
    for distribution, required in (("ibd-rs-rating", REQUIRED_PACKAGE_VERSION), ("yfinance", None)):
        try:
            installed = version(distribution)
        except PackageNotFoundError:
            installed = None
        dependencies[distribution] = {
            "installed": installed,
            "required": required,
            "ready": installed is not None and (required is None or installed == required),
        }
    doctrine = validate_doctrine()
    ready = doctrine["valid"] and all(item["ready"] for item in dependencies.values())
    missing = [
        {"id": name, "reason": "package_missing_or_version_mismatch", "required": True}
        for name, item in dependencies.items()
        if not item["ready"]
    ]
    return envelope(
        "health",
        request=_clean_request(request),
        as_of=_as_of(clock),
        status="ok" if ready else "partial",
        data={"ready": ready, "python": sys.version.split()[0], "dependencies": dependencies, "doctrine": doctrine},
        missing=missing,
    )


def _doctrine_show(request: Mapping[str, Any]) -> dict[str, Any]:
    claim_id = request.get("claim_id")
    if not isinstance(claim_id, str) or not claim_id:
        raise RequestError("claim_id is required", "claim_id")
    try:
        result = get_claim(claim_id)
    except KeyError as error:
        raise RequestError(str(error), "claim_id") from error
    clock = _clock(request.get("as_of"))
    return envelope(
        "doctrine.show",
        request=_clean_request(request),
        as_of=_as_of(clock),
        data={"claim": result["claim"]},
        sources=[{"provider": "doctrine_registry", "provenance": result["provenance"]}],
        doctrine_ids=[claim_id],
    )


def _qualify(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    requested_as_of = clock.date.isoformat()
    try:
        prices = runtime.price_history(ticker, requested_as_of)
    except ProviderUnavailable as error:
        return envelope(
            "ticker.qualify",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "eligibility_state": "incomplete"},
            missing=[_missing_provider(error)],
            next_capabilities=[],
        )

    sources = [_source(prices.meta)]
    missing: list[dict[str, Any]] = []
    rating: int | None = None
    rating_date: str | None = None
    try:
        rs = runtime.rs_rating(ticker, requested_as_of)
    except ProviderUnavailable as error:
        missing.append(_missing_provider(error))
    else:
        rating = int(rs.data["rating"])
        rating_date = str(rs.data["rating_date"])
        sources.append(_source(rs.meta))

    measured = build_eligibility_evidence(
        prices.data,
        rs_rating=rating,
        primary_base_quality=request.get("primary_base_quality"),
    )
    result = evaluate_eligibility(EligibilityEvidence.from_mapping(measured)).to_dict()
    next_capabilities = ["ticker.setup", "ticker.fundamentals"] if result["eligibility_state"] == "eligible" else []
    if result["eligibility_state"] == "incomplete" and result["route"] == "recent_ipo_primary_base":
        next_capabilities = ["ticker.chart"]
    return envelope(
        "ticker.qualify",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status="partial" if missing else "ok",
        data={
            "ticker": ticker,
            "route": result["route"],
            "eligibility_state": result["eligibility_state"],
            "completed_session_count": len(prices.data),
            "price_as_of": measured["as_of"],
            "rs_rating": rating,
            "rs_rating_date": rating_date,
        },
        signals=result["signals"],
        missing=missing,
        sources=sources,
        doctrine_ids=result["doctrine_ids"],
        next_capabilities=next_capabilities,
    )


def _setup(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    try:
        prices = runtime.price_history(ticker, clock.date.isoformat())
    except ProviderUnavailable as error:
        return envelope(
            "ticker.setup",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "setup_state": "incomplete"},
            missing=[_missing_provider(error)],
        )
    judgments = request.get("chart_judgments")
    if judgments is not None and not isinstance(judgments, Mapping):
        raise RequestError("chart_judgments must be an object", "chart_judgments")
    evidence = build_setup_evidence(
        prices.data,
        chart_judgments=judgments,
        tactic_opt_in=request.get("tactic_opt_in") is True,
    )
    result = evaluate_setup(evidence)
    missing = [{"id": item, "reason": "evidence_required", "required": True} for item in result["missing"]]
    status = "needs_input" if result["setup_state"] == "incomplete" else "ok"
    return envelope(
        "ticker.setup",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        data={"ticker": ticker, **result},
        signals=[result["price_geometry"], result["supply_evidence"], result["entry"]],
        missing=missing,
        sources=[_source(prices.meta)],
        doctrine_ids=["setup.vcp_supply_contraction"],
        next_capabilities=["ticker.chart"] if status == "needs_input" else ["ticker.risk"],
    )


def _fundamentals(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    cik = request.get("cik")
    if cik is not None and (not isinstance(cik, str) or not cik.isdigit() or len(cik) > 10):
        raise RequestError("cik must contain at most ten digits", "cik")
    if request.get("as_of") is not None and cik is None:
        return envelope(
            "ticker.fundamentals",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="needs_input",
            data={"ticker": ticker, "fundamentals_state": "incomplete"},
            missing=[{"id": "cik", "reason": "stable_historical_identity_required", "required": True}],
        )
    power_play = request.get("power_play")
    if power_play is not None and not isinstance(power_play, Mapping):
        raise RequestError("power_play must be an object", "power_play")
    try:
        snapshot = runtime.fundamentals_evidence(ticker, clock.date.isoformat(), cik)
    except ProviderUnavailable as error:
        return envelope(
            "ticker.fundamentals",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "fundamentals_state": "incomplete"},
            missing=[_missing_provider(error)],
        )
    result = evaluate_fundamentals(snapshot.data, as_of=clock.date.isoformat(), power_play=power_play)
    missing = [{"id": item, "reason": "filed_evidence_missing", "required": True} for item in result["missing"]]
    status = "partial" if result["fundamentals_state"] == "incomplete" else "ok"
    doctrine_ids = ["scope.data_integrity"]
    if power_play is not None:
        doctrine_ids.append("fundamentals.power_play_exception")
    return envelope(
        "ticker.fundamentals",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        data={"ticker": ticker, **result},
        signals=result["signals"],
        missing=missing,
        sources=[_source(snapshot.meta)],
        doctrine_ids=doctrine_ids,
        next_capabilities=["ticker.peers", "ticker.risk"],
    )


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
        classification = runtime.current_classification(ticker)
        master = runtime.security_master(None)
        industry = str(classification.data["industry"])
        industry_rows = runtime.industry_top(industry, clock.date.isoformat(), limit + 1)
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
        rating = runtime.rs_rating(ticker, clock.date.isoformat())
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
            prices = runtime.price_history(symbol, clock.date.isoformat())
        except ProviderUnavailable as error:
            missing = _missing_provider(error, required=symbol == ticker)
            missing["ticker"] = symbol
            provider_missing.append(missing)
        else:
            completed_prices[symbol] = prices.data
            sources.append(_source(prices.meta))

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
        "recommendation_state": "not_recommended",
    }


def _market_candidates(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    limit = request.get("limit", 50)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise RequestError("limit must be a positive integer", "limit")
    try:
        snapshot = runtime.security_master(request.get("as_of"))
    except ProviderUnavailable as error:
        return envelope(
            "market.candidates",
            request=_clean_request(request),
            as_of=_as_of(clock),
            status="unavailable",
            data={"candidates": [], "exclusions": [], "page": {}},
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


def _qqq_rows(frame: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
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
    return rows


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
    provider_missing: list[dict[str, Any]] = []

    def collect(fetch: Callable[[], ProviderSnapshot[Any]]) -> ProviderSnapshot[Any] | None:
        try:
            snapshot = fetch()
        except ProviderUnavailable as error:
            provider_missing.append(_missing_provider(error, required=False))
            return None
        sources.append(_source(snapshot.meta))
        return snapshot

    qqq = collect(lambda: runtime.price_history("QQQ", as_of))
    finviz = collect(lambda: runtime.finviz_breadth(as_of))
    sectors = collect(lambda: runtime.sector_ranking(as_of))
    industries = collect(lambda: runtime.industry_ranking(as_of))
    leaders = collect(lambda: runtime.market_leaders(as_of, leader_limit))

    sector_rows = _ranked_groups(sectors.data, "sector", as_of) if sectors is not None else None
    industry_rows = _ranked_groups(industries.data, "industry", as_of) if industries is not None else None
    leader_rows = _ranked_leaders(leaders.data, as_of) if leaders is not None else None
    evidence = build_market_evidence(
        qqq_daily_ohlcv=_qqq_rows(qqq.data) if qqq is not None else None,
        finviz_html=finviz.data if finviz is not None else None,
        sector_rows=sector_rows,
        industry_rows=industry_rows,
        leader_rows=leader_rows,
        trade_traction={"state": trade_traction} if trade_traction is not None else None,
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
    if not sources:
        status = "unavailable"
    elif trade_traction in {None, "needs_input"}:
        status = "needs_input"
    elif missing:
        status = "partial"
    else:
        status = "ok"
    return envelope(
        "market.snapshot",
        request=_clean_request(request),
        as_of=_as_of(clock),
        status=status,
        data={**result, "leaders": leader_rows or []},
        signals=result["signal_vector"],
        missing=missing,
        sources=sources,
        doctrine_ids=["scope.data_integrity"],
        next_capabilities=["market.candidates", "ticker.qualify"] if sources else [],
    )


def _risk(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    mode = request.get("mode", "prospective")
    if mode not in {"prospective", "active"}:
        raise RequestError("mode must be prospective or active", "mode")
    evidence = {key: value for key, value in request.items() if key not in {"ticker", "as_of", "format", "no_cache"}}
    evidence["mode"] = mode
    sources: list[dict[str, Any]] = []
    provider_missing: list[dict[str, Any]] = []
    has_stop_or_invalidation = evidence.get("stop_price") is not None or isinstance(evidence.get("invalidation"), Mapping)
    has_position_anchors = evidence.get("entry_price") is not None and evidence.get("entry_date") is not None and has_stop_or_invalidation
    if mode == "active" and evidence.get("current_price") is None and has_position_anchors:
        try:
            prices = runtime.price_history(ticker, clock.date.isoformat())
        except ProviderUnavailable as error:
            provider_missing.append(_missing_provider(error))
        else:
            current_price = float(prices.data["Close"].iloc[-1])
            evidence["current_price"] = current_price
            sources.append(_source(prices.meta))
            stop_price = evidence.get("stop_price")
            if isinstance(stop_price, (int, float)) and not isinstance(stop_price, bool) and current_price <= float(stop_price):
                evidence["completed_stop"] = {"state": "triggered", "price": current_price, "stop_price": float(stop_price)}
    result = reduce_risk(evidence)
    status = "partial" if provider_missing else "needs_input" if result["verdict"] == "INCOMPLETE" else "ok"
    missing = [*provider_missing, *({"id": item, "reason": "evidence_required", "required": True} for item in result["missing"])]
    return envelope(
        "ticker.risk",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        data={"ticker": ticker, **result, "current_price": evidence.get("current_price")},
        signals=[
            {"id": item, "state": "fail"} for item in result["failed"]
        ] + [{"id": item, "state": "not_triggered"} for item in result["waiting"]],
        missing=missing,
        sources=sources,
        doctrine_ids=["risk.initial_stop_and_reward", "risk.hard_stop_and_no_average_down", "risk.profit_protection_at_3r"],
    )


def _chart(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    try:
        prices = runtime.price_history(ticker, clock.date.isoformat())
    except ProviderUnavailable as error:
        return envelope(
            "ticker.chart",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker},
            missing=[_missing_provider(error)],
        )
    output_dir = request.get("output_dir")
    if output_dir is not None and (not isinstance(output_dir, str) or not output_dir.strip()):
        raise RequestError("output_dir must be a non-empty path", "output_dir")
    destination = Path(output_dir) if output_dir else Path(__file__).resolve().parents[2] / ".artifacts" / "charts"
    result = render_chart_artifacts(
        prices.data,
        ticker=ticker,
        as_of=clock.date.isoformat(),
        output_dir=destination,
    )
    side_effects = [
        {
            "type": "chart_artifact",
            "path": artifact["path"],
            "as_of": result["as_of"],
            "input_sha256": result["input_sha256"],
        }
        for artifact in result["artifacts"]
    ]
    side_effects.append(
        {
            "type": "artifact_manifest",
            "path": result["manifest_path"],
            "as_of": result["as_of"],
            "input_sha256": result["input_sha256"],
        }
    )
    return envelope(
        "ticker.chart",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        data=result,
        sources=[_source(prices.meta)],
        next_capabilities=["ticker.qualify", "ticker.setup"],
        side_effects=side_effects,
    )


def _watchlist(request: Mapping[str, Any], operation: str, runtime: Runtime) -> dict[str, Any]:
    ledger = runtime.ledger_factory()
    if operation == "watchlist.show":
        return envelope(operation, request=_clean_request(request), data={"records": ledger.show()})
    if operation == "watchlist.history":
        ticker = _ticker(request.get("ticker"))
        return envelope(operation, request={"ticker": ticker}, data={"ticker": ticker, "events": ledger.history(ticker)})
    if operation == "watchlist.record":
        ticker = _ticker(request.get("ticker"))
        clock = _clock(request.get("as_of"))
        required = ("instrument_id", "output_hash", "verdict")
        for field_name in required:
            if not isinstance(request.get(field_name), str) or not str(request[field_name]).strip():
                raise RequestError(f"{field_name} is required", field_name)
        output_hash = str(request["output_hash"]).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", output_hash):
            raise RequestError("output_hash must be a SHA-256 hex digest", "output_hash")
        doctrine_ids = request.get("doctrine_ids", [])
        if not isinstance(doctrine_ids, list) or not all(isinstance(item, str) for item in doctrine_ids):
            raise RequestError("doctrine_ids must be a list of claim IDs", "doctrine_ids")
        record = ledger.record(
            instrument_id=str(request["instrument_id"]),
            symbol=ticker,
            as_of=clock.date.isoformat(),
            output_hash=output_hash,
            verdict=str(request["verdict"]),
            condition=request.get("condition"),
            invalidation=request.get("invalidation"),
            doctrine_ids=doctrine_ids,
            evidence_quality=request.get("evidence_quality"),
            note=request.get("note"),
        )
        return envelope(
            operation,
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            data={"record": record},
            doctrine_ids=doctrine_ids,
            side_effects=[{"type": "sqlite_write", "path": str(ledger.path)}],
        )
    if operation == "watchlist.annotate":
        ticker = _ticker(request.get("ticker"))
        note = request.get("note")
        if not isinstance(note, str) or not note.strip():
            raise RequestError("note is required", "note")
        try:
            record = ledger.annotate(ticker, note)
        except KeyError as error:
            raise RequestError(f"no recorded research for {ticker}", "ticker") from error
        return envelope(
            operation,
            request={"ticker": ticker, "note": note},
            data={"record": record},
            side_effects=[{"type": "sqlite_write", "path": str(ledger.path)}],
        )
    if operation == "watchlist.export":
        output = request.get("output")
        if not isinstance(output, str) or not output.strip():
            raise RequestError("output is required", "output")
        result = ledger.export(Path(output))
        return envelope(
            operation,
            request={"output": output},
            data=result,
            side_effects=[{"type": "file_write", "path": result["path"]}],
        )
    raise RequestError(f"unknown operation: {operation}", "operation")


def execute(operation: str, request: Mapping[str, Any], *, runtime: Runtime | None = None) -> dict[str, Any]:
    """Execute one composable capability without printing or mutating implicit state."""

    if not isinstance(request, Mapping):
        raise RequestError("request must be an object", "request")
    runtime = runtime or Runtime()
    if operation == "clock":
        return _clock_operation(request)
    if operation == "health":
        return _health(request)
    if operation == "doctrine.show":
        return _doctrine_show(request)
    if operation == "ticker.qualify":
        return _qualify(request, runtime)
    if operation == "ticker.setup":
        return _setup(request, runtime)
    if operation == "ticker.fundamentals":
        return _fundamentals(request, runtime)
    if operation == "ticker.peers":
        return _peers(request, runtime)
    if operation == "ticker.risk":
        return _risk(request, runtime)
    if operation == "ticker.chart":
        return _chart(request, runtime)
    if operation == "market.candidates":
        return _market_candidates(request, runtime)
    if operation == "market.snapshot":
        return _market_snapshot(request, runtime)
    if operation.startswith("watchlist."):
        return _watchlist(request, operation, runtime)
    return envelope(
        operation,
        request=_clean_request(request),
        status="unavailable",
        data={"reason": "capability implementation pending"},
        missing=[{"id": operation, "reason": "implementation_pending", "required": True}],
    )


__all__ = ["Runtime", "execute"]
