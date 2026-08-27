"""Compose provider snapshots and pure evaluators into public v2 operations."""

from __future__ import annotations

import re
import os
import sys
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Callable, Mapping

import pandas as pd

from .cache import ProviderCache
from .clock import AnalysisClock, resolve_as_of
from .contracts import RequestError, envelope
from .doctrine import get_claim, has_claim, validate as validate_doctrine
from .eligibility import EligibilityEvidence, evaluate_eligibility
from .fundamentals import ACCOUNTING_INTEGRITY_WORDS as FUNDAMENTALS_ACCOUNTING_INTEGRITY, GOING_CONCERN_WORDS as FUNDAMENTALS_GOING_CONCERN, LEADER_CATEGORIES as FUNDAMENTALS_LEADER_CATEGORIES, MARKET_REGIMES as FUNDAMENTALS_MARKET_REGIMES, evaluate_fundamentals
from .ledger import Ledger
from .market import build_market_candidates, evaluate_market_snapshot, evidence_quality
from .market_evidence import build_market_evidence, carries_a_readable_bar
from .peer_collection import collect_same_industry_peer_rows
from .peers import compare_same_industry_peers
from .providers import DETAIL_LIMIT, ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry, redact
from .providers.finviz import raw_snapshot as finviz_raw_snapshot
from .providers.nasdaq import SecurityRecord, current_security_master, historical_security_master
from .providers.rs import REQUIRED_PACKAGE_VERSION, industry_ranking_snapshot, industry_top_snapshot, rating_snapshot, sector_ranking_snapshot, top_snapshot
from .providers.sec import fetch_company_facts, fetch_company_submissions, fetch_company_tickers, normalize_filed_facts
from .providers.yfinance import completed_daily_bars, current_classification_snapshot, next_earnings_snapshot
from .power_play import FLAG_STILL_FORMING, evaluate_power_play
from .power_play_evidence import CHART_READING_WORDS, build_power_play_evidence
from .management_evidence import AVERAGES as MANAGEMENT_AVERAGES, BLOCKS as MANAGEMENT_BLOCKS, SPLIT_COLUMN as _SPLIT_COLUMN, build_management_evidence, impossible_bar_relations, split_sized_discontinuities
from .risk import AUDIT_BASIS as _AUDIT_BASIS, crosses as _crosses, declares_exit_plan, reduce_risk, settled_breach, supplied_price_path, triggered_state as _triggered_state
from .setup import evaluate_setup
from .swings import canonical_chain
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
EarningsCalendar = Callable[[str], ProviderSnapshot[dict[str, Any]]]
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


def _default_earnings_calendar(ticker: str) -> ProviderSnapshot[dict[str, Any]]:
    return next_earnings_snapshot(ticker)


def _default_industry_top(industry: str, as_of: str, limit: int) -> ProviderSnapshot[list[dict[str, Any]]]:
    return industry_top_snapshot(industry, as_of, n=limit)


def _probe_rs() -> None:
    from .providers.rs import _client

    fetch_with_one_retry("ibd-rs-rating", "dates", _client().dates)


def _probe_sec() -> None:
    user_agent = os.environ.get("MINERVINI_SEC_USER_AGENT", "")
    if not user_agent:
        raise ProviderUnavailable("sec", "identifiable_user_agent_required", operation="company_tickers")
    import requests

    fetch_company_tickers(request_get=requests.get, user_agent=user_agent)


def _local_configuration() -> dict[str, dict[str, Any]]:
    """Report the local settings that silently disable a provider when absent.

    Both were dead here without the runtime saying so: an unpopulated CA bundle
    kills every stdlib-TLS provider, and an unset SEC User-Agent stops filed
    fundamentals before a request is made.
    """

    import ssl

    ca_certificates = ssl.create_default_context().cert_store_stats()["x509_ca"]
    user_agent = os.environ.get("MINERVINI_SEC_USER_AGENT", "")
    return {
        "tls_ca_bundle": {
            "ready": ca_certificates > 0,
            "required": True,
            "detail": None if ca_certificates else "the interpreter loaded no CA certificates; stdlib TLS cannot verify any host",
        },
        "sec_user_agent": {
            "ready": bool(user_agent),
            "required": False,
            "detail": None if user_agent else "MINERVINI_SEC_USER_AGENT is unset; ticker fundamentals cannot reach SEC",
        },
    }


def _probe_yfinance() -> None:
    import yfinance as yf

    frame = fetch_with_one_retry("yfinance", "daily_bars", lambda: yf.Ticker("SPY").history(period="5d", interval="1d"))
    if frame is None or frame.empty:
        raise ProviderUnavailable("yfinance", "no_completed_daily_bars", operation="daily_bars")


def _default_reachability_probes() -> dict[str, Callable[[], None]]:
    """Name the cheapest decisive call per probed provider.

    Nasdaq's security master is a multi-megabyte download, so it is deliberately
    not probed; its failures surface loudly in the operations that need it.
    """

    return {"yfinance": _probe_yfinance, "ibd-rs-rating": _probe_rs, "sec": _probe_sec}


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
    earnings_calendar: EarningsCalendar = field(default_factory=lambda: _default_earnings_calendar)
    industry_top: IndustryTop = field(default_factory=lambda: _default_industry_top)
    ledger_factory: LedgerFactory = field(default_factory=lambda: Ledger)
    reachability_probes: Mapping[str, Callable[[], None]] = field(default_factory=_default_reachability_probes)
    cache: ProviderCache | None = None


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


def _cached_provider(
    runtime: Runtime,
    request: Mapping[str, Any],
    clock: AnalysisClock,
    *,
    capability: str,
    provider: str,
    operation: str,
    params: Mapping[str, Any],
    fetch: Callable[[], ProviderSnapshot[Any]],
    ttl_seconds: float | None = None,
) -> ProviderSnapshot[Any]:
    if runtime.cache is None:
        return fetch()
    return runtime.cache.call(
        provider,
        f"{capability}:{operation}",
        {**params, "as_of": clock.date.isoformat()},
        clock.date,
        fetch,
        ttl_seconds=ttl_seconds,
        no_cache=request.get("no_cache") is True,
    )


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


def _stale_price_gap(meta: SnapshotMeta) -> dict[str, Any] | None:
    """Report price history that could not reach the requested completed session.

    A verdict computed from the previous session but stamped with this one is
    indistinguishable from a current verdict, so callers withhold the judgment
    rather than qualifying it.
    """

    if not meta.stale:
        return None
    return {
        "id": "completed_price_evidence",
        "provider": meta.provider,
        "reason": "session_behind_as_of",
        "required": True,
        "attempts": 1,
        "retryable": True,
        "detail": f"last completed bar {meta.coverage.get('last_completed_bar')} is behind requested session {meta.coverage.get('requested_session')}",
    }


def _missing_provider(error: ProviderUnavailable, *, required: bool = True) -> dict[str, Any]:
    gap = {
        "id": error.operation or error.provider,
        "provider": error.provider,
        "reason": error.reason,
        "required": required,
        "attempts": error.attempts,
        "retryable": error.retryable,
    }
    if error.detail:
        gap["detail"] = error.detail
    return gap


def _clock_operation(request: Mapping[str, Any]) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    return envelope(
        "clock",
        request=_clean_request(request),
        as_of=_as_of(clock),
        data={"date": clock.date.isoformat(), "mode": clock.mode},
    )


def _health(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
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
    configuration = _local_configuration()
    ready = doctrine["valid"] and all(item["ready"] for item in dependencies.values())
    ready = ready and all(item["ready"] for item in configuration.values() if item["required"])
    missing = [
        {"id": name, "reason": "package_missing_or_version_mismatch", "required": True}
        for name, item in dependencies.items()
        if not item["ready"]
    ]
    missing.extend(
        {"id": name, "reason": "local_configuration_missing", "required": item["required"], "detail": item["detail"]}
        for name, item in configuration.items()
        if not item["ready"]
    )
    data: dict[str, Any] = {
        "ready": ready,
        "python": sys.version.split()[0],
        "dependencies": dependencies,
        "configuration": configuration,
        "doctrine": doctrine,
        "reachability": {"checked": False, "providers": {}},
    }
    if request.get("probe") is True:
        probed: dict[str, Any] = {}
        for name, probe in runtime.reachability_probes.items():
            try:
                probe()
            except ProviderUnavailable as error:
                probed[name] = {"reachable": False, "reason": error.reason, "detail": error.detail}
                missing.append(_missing_provider(error))
            except Exception as error:  # A diagnostic must diagnose, never become the failure.
                detail = redact(f"{type(error).__name__}: {error}")[:DETAIL_LIMIT]
                probed[name] = {"reachable": False, "reason": "probe_failed", "detail": detail}
                missing.append({"id": name, "provider": name, "reason": "probe_failed", "required": True, "attempts": 1, "retryable": True, "detail": detail})
            else:
                probed[name] = {"reachable": True, "reason": None, "detail": None}
        ready = ready and all(item["reachable"] for item in probed.values())
        data["ready"] = ready
        data["reachability"] = {"checked": True, "providers": probed}
    return envelope(
        "health",
        request=_clean_request(request),
        as_of=_as_of(clock),
        status="ok" if ready else "partial",
        data=data,
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
        prices = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.qualify",
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": ticker},
            fetch=lambda: runtime.price_history(ticker, requested_as_of),
        )
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
    stale_price = _stale_price_gap(prices.meta)
    if stale_price is not None:
        return envelope(
            "ticker.qualify",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="partial",
            data={"ticker": ticker, "eligibility_state": "incomplete", "price_as_of": prices.meta.as_of.isoformat() if prices.meta.as_of else None},
            missing=[stale_price],
            sources=sources,
            next_capabilities=[],
        )
    missing: list[dict[str, Any]] = []
    rating: int | None = None
    rating_date: str | None = None
    try:
        rs = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.qualify",
            provider="ibd-rs-rating",
            operation="rating",
            params={"ticker": ticker},
            fetch=lambda: runtime.rs_rating(ticker, requested_as_of),
        )
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
        primary_base_emergence=request.get("primary_base_emergence"),
        primary_base_long_correction=request.get("primary_base_long_correction"),
    )
    result = evaluate_eligibility(EligibilityEvidence.from_mapping(measured)).to_dict()
    # A band the harness measured has to reach the caller, or the rule that every band
    # is reported with its range is prose nothing carries out.
    primary_base = measured.get("primary_base") or {}
    bands = {"primary_base.depth": primary_base["depth_band"]} if primary_base.get("depth_band") else {}
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
            "bands": bands,
        },
        signals=result["signals"],
        missing=missing,
        sources=sources,
        doctrine_ids=result["doctrine_ids"],
        next_capabilities=next_capabilities,
    )


_SEGMENTATION_CONVENTION = "setup.swing_segmentation_convention"
_CHAIN_COMPLETENESS = "setup.declared_chain_completeness"


_CHART_READING_CONVENTION = "convention.power_play_chart_reading"


def _chart_readings(request: Mapping[str, Any]) -> dict[str, str]:
    """What no amount of price history could make valid, checked before any is fetched.

    Written KEY=word rather than as an object, and parsed here rather than in the command line,
    so the shape a programmatic caller is held to is the shape the flag spells. The key itself is
    not checked here: only a run that has measured the bars knows which questions are open.
    """

    declarations = request.get("chart_readings")
    if declarations is None:
        return {}
    if isinstance(declarations, str) or not isinstance(declarations, Sequence):
        raise RequestError("chart_readings is a list of KEY=observed|absent readings", "chart_readings")
    readings: dict[str, str] = {}
    for declaration in declarations:
        key, separator, word = str(declaration).partition("=")
        key, word = key.strip(), word.strip().lower()
        if not separator or not key or not word:
            raise RequestError(
                "a chart reading is written KEY=observed|absent, using a key from chart_questions",
                "chart_readings",
            )
        if word not in CHART_READING_WORDS:
            raise RequestError(
                f"{key} needs one of {', '.join(CHART_READING_WORDS)} after the equals sign",
                "chart_readings",
            )
        # Two answers to one question is a contradiction, not a correction. Silently keeping the
        # last one picks a winner the caller never chose.
        if key in readings:
            raise RequestError(f"{key} was answered twice; a question takes one reading", "chart_readings")
        readings[key] = word
    return readings


def _chart_digest(
    request: Mapping[str, Any], name: str, required: bool, prints: str, describes: str, kind: str
) -> str | None:
    """One of the digests an answer names the picture by, checked before anything is applied.

    Required with an answer, the way approved_bars is required with a complete chain, and for the
    same reason: a chart reading is a reading of one picture, and the harness never sees it.

    And it has to be a digest rather than any non-empty string. Taken as written, a typo was a
    picture this run had not measured -- so a malformed value came back as an honest reading of
    another vintage, which is a finding about the stock rather than about the request.
    """

    value = request.get(name)
    if required and not (isinstance(value, str) and value.strip()):
        raise RequestError(
            f"{name} is required with chart_readings: name the bars {describes}, as ticker.chart "
            f"reports them in {prints} and every chart question carries them",
            name,
        )
    if value is None:
        return None
    # Accepted on the stripped value, so it has to be *used* stripped too. A padded digest
    # passing validation and then being compared raw is worse than a refusal: it reads as an
    # honest chart of another vintage, and the padding is invisible in the reported reason.
    value = str(value).strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RequestError(
            f"{name} is {kind}: sixty-four lowercase hex characters, as ticker.chart reports "
            f"it in {prints}",
            name,
        )
    return value


def _power_play(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    readings = _chart_readings(request)
    # Two digests, because the picture and the overlay drawn on it have different inputs. The
    # candles are the five price columns; the span is not, and a history with the same prices and
    # a different corporate-action column asks different questions -- reproduced as two questions
    # from here, no span at all on the chart, and `input_sha256` matching on both, which let an
    # answer read off a blank picture through to `qualified`.
    drawn_bars = _chart_digest(
        request,
        "drawn_bars",
        bool(readings),
        "input_sha256",
        "the chart was read from",
        "a bars_fingerprint",
    )
    measured_bars = _chart_digest(
        request,
        "measured_bars",
        bool(readings),
        "power_play.measured_bars",
        "the overlay was drawn from",
        "the digest the overlay was computed from",
    )
    try:
        prices = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.power-play",
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": ticker},
            fetch=lambda: runtime.price_history(ticker, clock.date.isoformat()),
        )
    except ProviderUnavailable as error:
        return envelope(
            "ticker.power-play",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "power_play_state": "incomplete"},
            missing=[_missing_provider(error)],
        )
    stale_price = _stale_price_gap(prices.meta)
    if stale_price is not None:
        return envelope(
            "ticker.power-play",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="partial",
            data={"ticker": ticker, "power_play_state": "incomplete"},
            missing=[stale_price],
            sources=[_source(prices.meta)],
        )
    evidence = build_power_play_evidence(
        prices.data, chart_readings=readings, drawn_bars=drawn_bars, measured_bars=measured_bars
    )
    # Refused rather than dropped, and before the verdict is assembled. The ordinary way an
    # approval stops matching is a session closing between the chart and the request; a caller
    # told nothing would read the unchanged answer as the harness ignoring them.
    stale = evidence["unmatched_chart_readings"]
    if stale:
        raise RequestError(
            "no question here is named by "
            + ", ".join(stale)
            + " -- read chart_questions from this capability and answer a key it issued",
            "chart_readings",
        )
    verdict = evaluate_power_play(evidence)
    rejection = verdict["structure"].get("rejection")
    if rejection is not None:
        return envelope(
            "ticker.power-play",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "power_play_state": "incomplete"},
            missing=[{"id": "usable_daily_bars", "reason": rejection, "required": True}],
            sources=[_source(prices.meta)],
            doctrine_ids=["fundamentals.power_play_exception", "scope.data_integrity"],
        )
    # Each gap names its own cause. Wrapping them all as one reason -- the shape the fundamentals
    # operation still uses for filed evidence -- would report a chart reading nobody has made and
    # a history that cannot say whether a split happened as the same kind of absence.
    reasons = {
        "corporate_action_evidence": (
            "corporate_action_inside_the_measured_span"
            if verdict["corporate_action_sessions"]
            else "corporate_action_evidence_missing"
        ),
        "peak_identity": "peak_identity_disputed",
        "peak_confirmation": "peak_not_a_confirmed_turning_point",
        "distribution_evidence": "distribution_evidence_missing",
    }
    contested = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["contested_criteria"]
    }
    payout_sensitive = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["payout_sensitive_criteria"]
    }
    awaiting_elsewhere = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["awaiting_chart_under_another_top"]
    }
    payout_elsewhere = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["payout_decided_under_another_top"]
    }
    action_elsewhere = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["corporate_action_under_another_top"]
    }
    rejected_elsewhere = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["rejected_under_another_top"]
    }
    # While an action stands, no criterion here was measured on one coordinate system, so the
    # cause of every gap is the action rather than anything a reader could supply.
    unreadable = (
        verdict["corporate_action_evidence"] != "present"
        or verdict["corporate_action_sessions"]
        or verdict["distribution_evidence"] != "present"
    )

    # Which criteria this run is still asking a reader about. Answered questions come back in the
    # payload with their answer, so counting those too would leave the envelope asking forever --
    # it would name a key that comes back already answered, and the next run would say the same.
    # And a gap reported as waiting on a chart with no key to answer it is a contradiction one
    # line apart.
    awaited = {
        f"fundamentals.power_play_exception.{question['condition']}"
        for question in verdict["chart_questions"]
        if question["answered"] is None
    }
    # A rejection is finished. Whatever it left unsatisfied stays in the payload as the shape of
    # the rejection, but it is not evidence anybody still owes -- neither the reason nor the
    # required flag may read as an instruction.
    decided = verdict["power_play_state"] == "not_qualified"

    # An answer read from another vintage of the series. Nothing was applied, so every criterion
    # it would have closed is open under that cause rather than under the chart it still waits on.
    other_bars = verdict["readings_cover_other_bars"]

    def _reason(item: str) -> str:
        if item in reasons:
            return reasons[item]
        if unreadable:
            if verdict["corporate_action_evidence"] != "present":
                return "corporate_action_evidence_missing"
            if verdict["distribution_evidence"] != "present":
                return "distribution_evidence_missing"
            return "corporate_action_inside_the_measured_span"
        if item == "lower_top_left_unread":
            return "history_ends_before_lower_top"
        if item in set(verdict["held_by_short_history"]):
            return "history_ends_before_lower_top"
        if item in set(verdict["held_by_another_top"]):
            return "structure_stands_under_another_top"
        if item in payout_sensitive:
            return "distribution_inside_the_measured_span"
        if item in contested:
            return "peak_identity_disputed"
        # The highest top answered it and a top that may contest it has not been looked at. What
        # closes it is that top's chart, not settling which top the structure hangs from.
        if item in awaiting_elsewhere:
            return "chart_unread_under_another_top"
        if item in payout_elsewhere:
            return "distribution_under_another_top"
        # A top whose own span holds a corporate action. Reported as a chart nobody has opened, it
        # named a picture no key exists for and pointed the reader at ticker.chart for an answer
        # this capability would refuse.
        if item in action_elsewhere:
            return "corporate_action_under_another_top"
        # A top the bars already threw out. It was issued no key either, so a reader sent to draw
        # its chart would come back with an answer this capability refuses.
        if item in rejected_elsewhere:
            return "structure_rejected_under_another_top"
        # The one gap that closes by itself. Reported as a chart reading, it would be closed by
        # whatever approval seam answers the chart -- and a twelve-session minimum would have been
        # waived by a reading of the volume.
        if item == FLAG_STILL_FORMING:
            return "flag_still_forming"
        # Two ways a chart criterion stops being something a chart closes. The structure was
        # rejected -- by the bars, or by this caller's own `absent` reading of another criterion --
        # and nothing supplied now moves it. Or no key was issued for it, because the reading it
        # belongs to was already out when the questions were handed round.
        #
        # Ahead of the vintage, because a rejection is not waiting on a picture of any vintage.
        # Read the other way round, a rejected structure answered from the wrong bars reported
        # every criterion as `approval_covers_different_bars` and sent a reader to redraw a chart
        # for a verdict that was finished -- the same mistake as reporting a still-forming flag
        # under the chart's name, one layer further out.
        if decided:
            return "structure_is_already_rejected"
        if other_bars:
            return "approval_covers_different_bars"
        if item not in awaited:
            return "reading_rejected_before_a_chart_was_needed"
        return "chart_reading_required"

    # `required` follows the verdict rather than the cause. Every gap keeps the reason that is
    # actually true of it -- a disputed peak on a rejected structure was still disputed -- but a
    # finished rejection owes nobody anything, and nine of twenty-three real tickers were coming
    # back `ok` with gaps marked required and no capability named to close them.
    #
    # And a criterion whose own reading is out owes nothing either, whatever the verdict does. No
    # key exists for it and none can, so it is unsatisfied evidence rather than evidence anybody
    # still has to supply -- which is what `required` has meant everywhere else in this harness.
    missing = [
        {
            "id": item,
            "reason": (reason := _reason(item)),
            "required": not decided and reason != "reading_rejected_before_a_chart_was_needed",
        }
        for item in verdict["missing"]
    ]
    # A rejection is finished, so it proposes nothing; an incomplete answer proposes a chart only
    # when a chart is what one of its gaps is actually waiting on.
    # Every gap a picture closes, because they are the same errand: read the highest top's chart,
    # read a contesting top's, or read the right vintage of either. Naming the capability for some
    # of them leaves a reader told to look at a chart with nowhere sent to draw it.
    awaits_a_chart = verdict["power_play_state"] == "incomplete" and any(
        item["reason"]
        in ("chart_reading_required", "chart_unread_under_another_top", "approval_covers_different_bars")
        for item in missing
    )
    return envelope(
        "ticker.power-play",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        # The status is whether the evidence contract was satisfied; the state is the verdict.
        # A qualified Power Play has no gap left in it, so reporting it as `partial` would send
        # the reader looking for a missing piece that does not exist.
        status="partial" if verdict["power_play_state"] == "incomplete" else "ok",
        data={"ticker": ticker, **verdict},
        signals=verdict["signals"],
        missing=missing,
        sources=[_source(prices.meta)],
        # The two conventions belong here too: one converts every limit the source states in
        # weeks, the other decides where one reading of the structure stops and another begins.
        # Both move verdicts, so a reader auditing this one has to be able to reach them.
        doctrine_ids=[
            "fundamentals.power_play_exception",
            "convention.trading_week",
            "convention.power_play_top_candidates",
            # The candidates are the turning points that convention cuts, so the rule deciding
            # which highs count as tops is cited beside the one deciding how far down they argue.
            "setup.swing_segmentation_convention",
            # What a reading of the chart is bound to, and what it can never close. Cited on every
            # answer here, because a reader auditing a qualified verdict has to be able to reach
            # the rule that let a human sentence become a machine pass.
            _CHART_READING_CONVENTION,
            "scope.data_integrity",
        ],
        next_capabilities=["ticker.chart"] if awaits_a_chart else [],
    )


def _swings(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    try:
        prices = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.swings",
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": ticker},
            fetch=lambda: runtime.price_history(ticker, clock.date.isoformat()),
        )
    except ProviderUnavailable as error:
        return envelope(
            "ticker.swings",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "state": "unavailable", "anchors": []},
            missing=[_missing_provider(error)],
        )
    stale_price = _stale_price_gap(prices.meta)
    if stale_price is not None:
        return envelope(
            "ticker.swings",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="partial",
            data={"ticker": ticker, "state": "unavailable", "anchors": []},
            missing=[stale_price],
            sources=[_source(prices.meta)],
        )
    chain = canonical_chain(prices.data)
    resolved = chain["state"] == "resolved"
    return envelope(
        "ticker.swings",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        # Not needs_input: the parameters are deliberately out of the caller's reach, so there
        # is no argument that turns an unstable segmentation into a stable one. What is absent
        # is the evidence this capability exists to produce.
        status="ok" if resolved else "unavailable",
        data={"ticker": ticker, **chain},
        missing=[] if resolved else [{"id": "stable_segmentation", "reason": _segmentation_reason(chain), "required": True}],
        sources=[_source(prices.meta)],
        # The convention is the harness's; the boundary it bounds the base at is the source's.
        doctrine_ids=[_SEGMENTATION_CONVENTION, "setup.structural_pivot_and_trigger"],
        # A proposal is not an approval, and the chart is where a person turns one into the
        # other. With nothing proposed the chart draws no anchors, so pointing at it would send
        # a reader to a picture that cannot answer what they came for.
        next_capabilities=["ticker.chart"] if resolved else [],
    )


def _segmentation_reason(chain: Mapping[str, Any]) -> str:
    """Which of the ways a segmentation can fail this one failed.

    A chain that moves with the parameter and a chain with a session no daily bar can order
    are different problems, and a single reason word would hide which one a reader is looking
    at.
    """
    if chain.get("rejection"):
        return str(chain["rejection"])
    if chain.get("left_edge_disputed"):
        return "base_left_edge_ambiguous"
    if chain.get("ambiguous_sessions_in_base"):
        return "ambiguous_session_inside_the_base"
    if chain.get("sensitivity"):
        return "neighbouring_parameters_disagree"
    return "history_segments_into_no_base"


def _setup(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    # Before the provider, not after: a malformed request that reaches the network comes back as
    # a provider outage when the fault was the caller's, and pays for a fetch nobody can use.
    _refuse_unusable_setup_request(request)
    try:
        prices = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.setup",
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": ticker},
            fetch=lambda: runtime.price_history(ticker, clock.date.isoformat()),
        )
    except ProviderUnavailable as error:
        return envelope(
            "ticker.setup",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "setup_state": "incomplete"},
            missing=[_missing_provider(error)],
        )
    stale_price = _stale_price_gap(prices.meta)
    if stale_price is not None:
        return envelope(
            "ticker.setup",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="partial",
            data={"ticker": ticker, "setup_state": "incomplete"},
            missing=[stale_price],
            sources=[_source(prices.meta)],
        )
    swings = request.get("swing")
    entry = request.get("entry")
    evidence = build_setup_evidence(
        prices.data,
        swings or [],
        entry_kind=request.get("entry_kind") or "completed_pivot",
        tactic_opt_in=request.get("tactic_opt_in") is True,
        entry=entry,
        right_side_development=request.get("right_side_development"),
        chain_completeness=request.get("chain_completeness"),
        approved_bars=request.get("approved_bars"),
        entry_price=request.get("entry_price"),
        pivot_reset=request.get("pivot_reset"),
        entry_proximity=request.get("entry_proximity"),
    )
    result = evaluate_setup(evidence)
    # Two different questions, and they were being answered by one flag. Whether the verdict is
    # corroborated turns on the chain everything was measured off: a declared chain the detector
    # did not produce measures some other span, and one such chain reported an up/down volume
    # ratio of 0.08 where the base's own was 3.65, published as AVOID. Whether the caller can act
    # turns on something else entirely -- they can declare the detector's chain, and they cannot
    # make an unstable segmentation stable.
    corroborated = evidence["chain_corroborated"]
    unvouched = evidence["segmentation"].get("state") != "resolved"
    if not corroborated:
        # Every measurement was read off the declared chain, so a segmentation nothing vouched
        # for disqualifies what was measured from it -- a hard gate's failure included. Leaving
        # the reducer's AVOID in the payload while the envelope said unavailable published a
        # finding about the stock that rested on a data-integrity gap.
        # The reason travels with the state. Completeness failing lands in `unsatisfied` rather
        # than `missing`, so overriding the verdict without moving it left an incomplete answer
        # with nothing in it naming what was incomplete.
        missing_ids = [item for item in result["missing"] if item != _CHAIN_COMPLETENESS]
        result = {
            **result,
            "setup_state": "incomplete",
            "uncorroborated_verdict": result["setup_state"],
            "missing": [*missing_ids, _CHAIN_COMPLETENESS],
            "unsatisfied": [item for item in result["unsatisfied"] if item != _CHAIN_COMPLETENESS],
        }
    # A reading nobody declared and a reading nothing will corroborate are different absences.
    # The first is fixed by declaring one; the second is fixed by nothing the caller can type,
    # and reporting both as "evidence required" sends a reader looking for an argument.
    missing = [{"id": item, "reason": _missing_reason(item, evidence), "required": True} for item in result["missing"]]
    if unvouched:
        # The same gap ticker.swings calls unavailable, and for the same reason: the parameters
        # are out of the caller's reach and the chart draws no anchors for a chain the detector
        # refuses, so needs_input named nothing they could supply and the chart was a dead end.
        #
        # Ahead of the reducer's own state, not only when it came back incomplete. A hard gate
        # failing on an uncorroborated chain is still a verdict read off a segmentation nothing
        # vouched for, and letting it through returned ok, AVOID, and a pointer at ticker.risk
        # over a data-integrity gap the engine already knew about.
        status = "unavailable"
    elif result["setup_state"] != "incomplete":
        status = "ok"
    else:
        status = "needs_input"
    return envelope(
        "ticker.setup",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        # Contrast evidence rides in the payload, never in `signals`: a reducer or a caller
        # scanning signal states would read another practitioner's disagreement as this
        # harness's own missing evidence.
        data={"ticker": ticker, **result, "contrast": evidence["contrast"]},
        # `signals` is the machine channel: what the verdict was built from. Measurements taken
        # off a chain nothing vouched for were not built into a verdict, and a caller or a later
        # reducer scanning states would read a hard gate's failure there as this harness's
        # finding about the stock. They stay in the payload, where a person reads them beside the
        # reason nothing counted. This is the rule contrast evidence already follows, for the
        # same reason.
        signals=result["signals"] if corroborated else [
            item for item in result["signals"] if item.get("id") == _CHAIN_COMPLETENESS
        ],
        missing=missing,
        sources=[_source(prices.meta)],
        # The detector's own convention decided the chain every measurement was read off, so it
        # is cited alongside the claims the signals name. Deriving the list from signals alone
        # left the one rule that is the harness's rather than the source's out of the answer.
        # The reducer's own list rather than a second derivation of it: the declared tactic is a
        # claim this verdict was reached under, and it appears in no signal because the caller
        # declared it instead of the bars measuring it.
        doctrine_ids=sorted({*result["doctrine_ids"], _SEGMENTATION_CONVENTION}),
        next_capabilities=[] if status == "unavailable" else ["ticker.chart"] if status == "needs_input" else ["ticker.risk"],
    )


def _refuse_unusable_setup_request(request: Mapping[str, Any]) -> None:
    """What no amount of price history could make valid."""

    swings = request.get("swing")
    if swings is not None and not isinstance(swings, list):
        raise RequestError("swing must be a list of completed session dates", "swing")
    entry = request.get("entry")
    if entry is not None and not isinstance(entry, Mapping):
        raise RequestError("entry must be an object", "entry")
    # Which entry this is, and whether the caller opted into it, are contract terms with their own
    # arguments. Restated inside the declaration they are a caller who has misunderstood the seam,
    # and dropping them quietly leaves that caller reading a gap they believe they filled.
    for reserved in ("kind", "opt_in"):
        if isinstance(entry, Mapping) and reserved in entry:
            raise RequestError(
                f"entry.{reserved} cannot be supplied; use entry_kind and tactic_opt_in",
                "entry",
            )
    for reserved in ("completeness_source", "detected_chain", "segmentation"):
        if request.get(reserved) is not None:
            # Naming a supplier is not being one, and neither is handing in a segmentation and
            # calling it independent. The seam exists for one this harness produced.
            raise RequestError(f"{reserved} cannot be supplied by the caller", reserved)
    # A chart reading with no picture named is a reading of nothing in particular. The value is
    # printed by both ticker.swings and ticker.chart, so carrying it costs a copy and buys the
    # one thing the date comparison cannot see: that the approval was of these bars. Only for
    # `complete`, which is the reading it gates -- a caller admitting a gap is telling the truth
    # whichever vintage they read it from, and charging them for the receipt would be the
    # opposite of costing them nothing.
    if request.get("chain_completeness") == "complete" and request.get("approved_bars") is None:
        raise RequestError(
            "approved_bars is required with chain_completeness complete: name the bars the chain was approved from, as ticker.swings and ticker.chart report them",
            "approved_bars",
        )


def _missing_reason(item: str, evidence: Mapping[str, Any]) -> str:
    """Which absence this is, because they are not fixed by the same thing.

    A reading nobody declared is fixed by declaring one. A reading the detector will not
    corroborate is fixed by nothing the caller can type. An approval of other bars is fixed by
    looking at the current chart again. Reporting all three as "evidence required" sends a
    reader looking for an argument in two of the three cases.
    """
    # Not evidence the caller could have supplied. "Early" is a time, and the source names five
    # tactics; what closes this is picking one, and telling a reader to supply evidence sends them
    # looking for a measurement of a tactic nobody named.
    if item == "named_entry_tactic":
        return "no_tactic_named"
    if item != _CHAIN_COMPLETENESS:
        return "evidence_required"
    segmentation = evidence["segmentation"]
    if segmentation.get("state") != "resolved":
        return "segmentation_unstable"
    if not evidence["chain_corroborated"]:
        return "declared_chain_is_not_the_detected_one"
    signal = next((item for item in evidence["signals"] if item.get("id") == _CHAIN_COMPLETENESS), {})
    measured = signal.get("measured") or {}
    if "approved_bars" in measured:
        return "approval_covers_different_bars"
    return "evidence_required"


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
        prices = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.fundamentals",
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": ticker},
            fetch=lambda: runtime.price_history(ticker, clock.date.isoformat()),
        )
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
    if timestamps.tz is not None:
        timestamps = timestamps.tz_convert("America/New_York").tz_localize(None)
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
            prices = _cached_provider(
                runtime,
                request,
                clock,
                capability="ticker.peers",
                provider="yfinance",
                operation="daily_bars",
                params={"ticker": symbol},
                fetch=lambda symbol=symbol: runtime.price_history(symbol, clock.date.isoformat()),
            )
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


def _ohlcv_rows(frame: Any) -> list[dict[str, Any]]:
    """Completed rows from a provider frame, or none at all from anything that is not one."""

    if not callable(getattr(frame, "iterrows", None)):
        return []
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
                rows = _ohlcv_rows(history.data)
                if carries_a_readable_bar(rows):
                    leader_history[symbol] = rows
                else:
                    # A snapshot that arrived and carried nothing readable is a gap the
                    # payload already shows; without this the envelope counts it as read.
                    provider_missing.append(
                        {"id": "leader_price_history", "ticker": symbol, "reason": "daily_bars_unreadable", "required": False}
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
    evidence = build_market_evidence(
        qqq_daily_ohlcv=_ohlcv_rows(qqq.data) if qqq is not None else None,
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


# Every price the harness publishes is rounded to this many places, so a positive number
# below it is a price the reader would be handed as zero -- and the measurements divided by
# it come back infinite beside that zero. Such a scale is refused rather than reported on.
_REPORTED_PRECISION = 10


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not (value > 0 and math.isfinite(value)):
        return None
    return float(value) if round(float(value), _REPORTED_PRECISION) > 0 else None


def _request_date(value: Any, field: str) -> date:
    """A calendar date the caller wrote as ``YYYY-MM-DD``, or a refusal naming the field.

    The extended form only. ``date.fromisoformat`` also reads the basic form and a full
    timestamp, and the reducer's own reader takes neither -- so a request written either way
    parses here, is written back in a shape the reducer answers "missing" to, and the two
    halves of the harness disagree about whether the field was supplied at all. A number is
    refused for the same reason: ``20251201`` is not a date the reducer can read.
    """

    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise RequestError(f"{field} must be an ISO date written YYYY-MM-DD", field)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise RequestError(f"{field} must be an ISO date written YYYY-MM-DD", field) from error


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
    if timestamps.tz is not None:
        timestamps = timestamps.tz_convert("America/New_York").tz_localize(None)
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
    if timestamps.tz is not None:
        timestamps = timestamps.tz_convert("America/New_York").tz_localize(None)
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


def _risk(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    mode = request.get("mode", "prospective")
    if mode not in {"prospective", "active"}:
        raise RequestError("mode must be prospective or active", "mode")
    evidence = {key: value for key, value in request.items() if key not in {"ticker", "as_of", "format", "no_cache"}}
    evidence["mode"] = mode
    # The reducer measures every audit window against the decision date, so it
    # cannot be the one input the operation keeps to itself.
    evidence["as_of"] = clock.date.isoformat()
    sources: list[dict[str, Any]] = []
    provider_missing: list[dict[str, Any]] = []
    _check_declared_shapes(evidence)
    invalidation = evidence.get("invalidation")
    # The audit needs the date the position started and a plan to clear; what it
    # was bought at decides 3R protection, not whether a level was breached. Both
    # predicates come from the reducer so routing cannot drift from the verdict.
    has_position_anchors = evidence.get("entry_date") is not None and declares_exit_plan(evidence)
    raw_stop_price = evidence.get("stop_price")
    stop_price = _positive(raw_stop_price)
    raw_invalidation_price = invalidation.get("price") if isinstance(invalidation, Mapping) else None
    invalidation_price = _positive(raw_invalidation_price)
    raw_initial_stop = evidence.get("initial_stop_price")
    initial_stop_price = _positive(raw_initial_stop)
    raw_current_price = evidence.get("current_price")
    current_price_input = _positive(raw_current_price)
    raw_entry_price = evidence.get("entry_price")
    entry_price = _positive(raw_entry_price)
    for raw, resolved, field in (
        (raw_stop_price, stop_price, "stop_price"),
        (raw_invalidation_price, invalidation_price, "invalidation_price"),
        (raw_initial_stop, initial_stop_price, "initial_stop_price"),
        # A price the caller hands in decides the verdict where the audit could not speak,
        # so a zero, a negative or a string in that field is not a value to drop quietly:
        # dropping it falls back on the provider and answers a question the caller asked a
        # different way, and keeping it sells the position at a price that is not a price.
        (raw_current_price, current_price_input, "current_price"),
        (raw_entry_price, entry_price, "entry_price"),
    ):
        if raw is not None and resolved is None:
            raise RequestError(f"{field} must be a finite positive number", field)
    widened = initial_stop_price is not None and stop_price is not None and stop_price < initial_stop_price
    protective_level = max(
        [level for level in (stop_price, invalidation_price, initial_stop_price if widened else None) if level is not None],
        default=None,
    )
    stop_effective_date: date | None = None
    entry_date: date | None = None
    if mode == "active" and evidence.get("entry_date") is not None:
        entry_date = _request_date(evidence["entry_date"], "entry_date")
        raw_effective_date = evidence.get("stop_effective_date")
        stop_effective_date = entry_date if raw_effective_date is None else _request_date(raw_effective_date, "stop_effective_date")
        # Chronology is checked before any evidence is fetched: a position that does
        # not exist on the decision date cannot be sold, held, or audited.
        if entry_date > clock.date:
            raise RequestError("entry_date cannot be after as_of", "entry_date")
        if stop_effective_date < entry_date:
            raise RequestError("stop_effective_date cannot precede entry_date", "stop_effective_date")
        if stop_effective_date > clock.date:
            raise RequestError("stop_effective_date cannot be after as_of", "stop_effective_date")
        # A stop the trade started with sits below the price it was entered at, or the
        # position runs no risk for the stop to bound and every measurement read from it --
        # the loss percent, the reward-to-risk, the R multiple -- is about a trade nobody
        # could have taken. A stop raised later is the opposite case and is left alone:
        # defending a gain above entry is the rule this harness is built on.
        if stop_price is not None and entry_price is not None and stop_price >= entry_price and stop_effective_date == entry_date:
            raise RequestError("stop_price must be below entry_price unless it was raised later, on a stop_effective_date after entry_date", "stop_price")
        if evidence.get("stop_effective_date") is not None:
            # Written back only when the caller declared it: the reducer's request contract
            # says a stop that differs from the initial one was raised on some date, and
            # materialising the default here would answer that question for them.
            evidence["stop_effective_date"] = stop_effective_date.isoformat()
    stage2_start: date | None = None
    if evidence.get("stage2_start") is not None:
        stage2_start = _request_date(evidence["stage2_start"], "stage2_start")
        if stage2_start > clock.date:
            raise RequestError("stage2_start cannot be after as_of", "stage2_start")
        evidence["stage2_start"] = stage2_start.isoformat()
    if evidence.get("management_average") is not None and evidence["management_average"] not in MANAGEMENT_AVERAGES:
        raise RequestError(f"management_average must be one of {', '.join(MANAGEMENT_AVERAGES)}", "management_average")
    raw_base_top = evidence.get("base_top")
    base_top = _positive(raw_base_top)
    if raw_base_top is not None and base_top is None:
        raise RequestError("base_top must be a finite positive number", "base_top")
    if evidence.get("earnings_date") is not None:
        evidence["earnings_date"] = _request_date(evidence["earnings_date"], "earnings_date").isoformat()
        evidence["earnings_source"] = "declared"
        evidence["earnings_confirmation"] = "declared_by_caller"
    elif not (mode == "active" and has_position_anchors):
        # Nothing to manage, so nothing to look up. Fetching a calendar for a request that
        # declares no position spends a provider call and puts a gap in `missing` about a
        # question the request never asked.
        pass
    elif clock.mode != "last_completed_session":
        # A calendar entry is a forecast, and no feed can say what it forecast last March.
        # Dating today's answer to an explicit past session would put a schedule nobody
        # published then inside a point-in-time verdict.
        evidence["earnings_unavailable_reason"] = "earnings_calendar_is_current_only"
    else:
        try:
            calendar = _cached_provider(
                runtime,
                request,
                clock,
                capability="ticker.risk",
                provider="yfinance",
                operation="next_earnings",
                params={"ticker": ticker},
                fetch=lambda: runtime.earnings_calendar(ticker),
                # The same short life every mutable current snapshot gets. A schedule that
                # moves is the normal case, and a day-old cached date would answer "still
                # ahead" about a report that has already been released.
                ttl_seconds=900,
            )
        except ProviderUnavailable as error:
            provider_missing.append({**_missing_provider(error), "required": False})
            evidence["earnings_unavailable_reason"] = error.reason
        else:
            sources.append(_source(calendar.meta))
            evidence["earnings_date"] = calendar.data["earnings_date"]
            evidence["earnings_source"] = "provider"
            evidence["earnings_confirmation"] = calendar.data["confirmation"]
            evidence["earnings_window"] = calendar.data["window"]
    raw_base_count = evidence.get("base_count")
    if raw_base_count is not None:
        if isinstance(raw_base_count, bool) or not isinstance(raw_base_count, int) or raw_base_count < 1:
            raise RequestError("base_count must be a whole number of bases, at least 1", "base_count")
    breakout_date: date | None = None
    if evidence.get("breakout_date") is not None:
        breakout_date = _request_date(evidence["breakout_date"], "breakout_date")
        if breakout_date > clock.date:
            raise RequestError("breakout_date cannot be after as_of", "breakout_date")
        evidence["breakout_date"] = breakout_date.isoformat()

    # A stop raised later is only in force from its own date, while the structural
    # invalidation has stood since entry. Auditing both against one date would let
    # the later start hide a breach the earlier level already suffered.
    protective_plan: list[tuple[str, float, date, date | None]] = []
    if stop_price is not None and stop_effective_date is not None:
        protective_plan.append(("stop", stop_price, stop_effective_date, None))
    if invalidation_price is not None and entry_date is not None:
        protective_plan.append(("invalidation", invalidation_price, entry_date, None))
    if initial_stop_price is not None and stop_price is not None and entry_date is not None and stop_effective_date is not None:
        if stop_price >= initial_stop_price:
            # The initial stop governed every completed session before the raise took effect.
            if stop_effective_date > entry_date:
                protective_plan.append(("initial_stop", initial_stop_price, entry_date, stop_effective_date))
        else:
            # A stop is never widened, so a lower later stop does not relieve the initial
            # one; the initial stop stays in force over the whole window.
            protective_plan.append(("initial_stop", initial_stop_price, entry_date, None))

    explicit_current = evidence.get("current_price")
    explicit_declared = protective_level is not None and isinstance(explicit_current, (int, float)) and not isinstance(explicit_current, bool)
    # Each level is read the way its own audit reads it: a stop is a price the position
    # transacts at, an invalidation a threshold the close has to be carried through.
    explicit_crossed = (
        [(role, level, effective) for role, level, effective, _end in protective_plan if _crosses(role, float(explicit_current), level)]
        if explicit_declared
        else []
    )
    explicit_completed_breach = bool(explicit_crossed)
    explicit_path: dict[str, Any] | None = None
    explicit_audits: list[dict[str, Any]] = []
    if mode == "active" and explicit_completed_breach and stop_effective_date is not None:
        price = float(explicit_current)
        # One price says one thing: which levels it is at or below. A level under it was not
        # cleared -- no bar was read, and a session last week could have taken it out -- so
        # it is unaudited rather than clear. The record is about the level the price actually
        # crossed, named by role, because a breached invalidation is not a breached stop.
        # A completed close below a resting stop proves the session traded at least that low,
        # so that stop was taken out intraday, before the close could invalidate anything.
        # Among levels read from the same price the highest is the one crossed first -- and
        # that is also why no expired-window filter is needed here: a window only ends when a
        # raise replaced it, so the level that expired is always below the one that replaced
        # it, and this comparison never reaches it. The audits below check the window itself.
        governing_role, governing_level, governing_from = min(explicit_crossed, key=lambda item: (0 if _AUDIT_BASIS[item[0]] == "completed_daily_low" else 1, -item[1]))
        explicit_audits = [
            {
                "role": role,
                "level": level,
                "effective_from": effective.isoformat(),
                **(
                    {"through": clock.date.isoformat(), "state": "breached", "basis": "explicit_completed_price", "breach_date": clock.date.isoformat(), "breach_price": price}
                    if _crosses(role, price, level) and (end_before is None or clock.date < end_before)
                    else {"state": "unavailable", "reason": "not_audited_after_explicit_breach"}
                ),
            }
            for role, level, effective, end_before in protective_plan
        ]
        explicit_path = {
            "state": "breached",
            "basis": "explicit_completed_price",
            "from": (governing_from or stop_effective_date).isoformat(),
            "through": clock.date.isoformat(),
            "checked_level": governing_level,
            "governing_role": governing_role,
            "breach_date": clock.date.isoformat(),
            "breach_price": price,
            "audits": explicit_audits,
        }
    # An assertion settles the verdict, not the record. It says the position ended without
    # saying when, and the bars can hold an exit that happened first -- so they are read, and
    # the earliest dated exit names the failure. What a settled verdict does buy is that the
    # absence of those bars cannot downgrade it: they were consulted, not depended on.
    # The one exception is a price path the caller handed in, which is the same record the
    # bars would produce; re-deriving it would discard what they supplied.
    settled = settled_breach(evidence)
    if mode == "active" and has_position_anchors and not supplied_price_path(evidence) and _triggered_state(evidence.get("completed_price_path")):
        # Not a record, so it does not stand in for one. It is still what the caller said,
        # and a verdict that quietly drops it is a payload the caller cannot reconcile with
        # their own request -- so it travels as the assertion it is and meets the bars.
        evidence["asserted_price_path"] = evidence.pop("completed_price_path")
    if mode == "active" and has_position_anchors and supplied_price_path(evidence):
        # The structural blocks still travel with the SELL, saying why they are empty: a
        # block that vanishes reads as a measurement with nothing to report.
        evidence["management"] = {
            key: {"state": "unavailable", "reason": "price_history_not_fetched_after_supplied_price_path"}
            for key in MANAGEMENT_BLOCKS
        }
    if mode == "active" and has_position_anchors and not supplied_price_path(evidence):
        try:
            prices = _cached_provider(
                runtime,
                request,
                clock,
                capability="ticker.risk",
                provider="yfinance",
                operation="daily_bars",
                params={"ticker": ticker},
                fetch=lambda: runtime.price_history(ticker, clock.date.isoformat()),
            )
        except ProviderUnavailable as error:
            provider_missing.append({**_missing_provider(error), "required": not settled})
            # The blocks still travel with a verdict the request settled on its own, and they
            # say what actually happened: the history was asked for and the provider had none.
            # A block that vanishes reads as a measurement with nothing to report instead.
            evidence["management"] = {key: {"state": "unavailable", "reason": "price_history_unavailable"} for key in MANAGEMENT_BLOCKS}
        else:
            sources.append(_source(prices.meta))
            stale_price = _stale_price_gap(prices.meta)
            if stale_price is not None:
                provider_missing.append(stale_price)
            current_price = None
            # A High that was printed is a fact whether or not the history reaches as_of,
            # so this is measured before staleness is weighed; the reducer only acts on
            # it under a HOLD the audit has established.
            if entry_date is not None:
                evidence.update(_max_high_since(prices.data, entry_date=entry_date, as_of=clock.date))
                evidence["management"] = build_management_evidence(
                    prices.data,
                    entry_date=entry_date,
                    as_of=clock.date,
                    management_average=evidence.get("management_average"),
                    stage2_start=stage2_start,
                    base_top=base_top,
                    breakout_date=breakout_date,
                )
            if protective_plan:
                # Runs even when the history stops early: a completed breach is
                # irreversible, and a later missing bar cannot undo one.
                audits: list[dict[str, Any]] = []
                path_price = None
                for role, level, effective, end_before in protective_plan:
                    audit, audit_price = _completed_stop_path(
                        prices.data,
                        effective_date=effective,
                        as_of=clock.date,
                        protective_level=level,
                        end_before=end_before,
                        # A stop can be moved on a day the market was shut; an entry cannot happen on one.
                        require_session=effective == entry_date,
                        basis=_AUDIT_BASIS[role],
                    )
                    audits.append({**audit, "role": role, "level": level, "effective_from": effective.isoformat()})
                    path_price = audit_price if audit_price is not None else path_price
                # A price handed in is an observation dated as_of, which is the latest date any
                # exit can carry. It stands where the bars found no breach of that level, and
                # yields to a breach the bars printed, because that one happened first.
                crossed_now = {item["role"]: item for item in explicit_audits if item["state"] == "breached"}

                def with_price(audit: dict[str, Any]) -> dict[str, Any]:
                    told = crossed_now.get(audit["role"])
                    # A window the audit refused because it spans a corporate action is not a
                    # window one more price can settle: the declared level is in the old
                    # coordinate system and the price is in the new one, and comparing them is
                    # the arithmetic that refusal exists to prevent.
                    if told is None or audit["state"] == "breached" or audit.get("reason") in _UNCROSSABLE_REASONS:
                        return audit
                    # The bars still covered what they covered; the price only added what they
                    # could not say. Both belong in one record.
                    return {**told, **{key: value for key, value in audit.items() if key in _COVERAGE_FIELDS}}

                audits = [with_price(audit) for audit in audits]
                price_path = _combine_audits(audits)
                evidence["completed_price_path"] = price_path
                if stale_price is None:
                    current_price = path_price
                # Whichever observation the record was built from is the one published beside
                # it: two different latest prices for one session tells the reader the trade
                # ended at a price the payload denies.
                if price_path.get("basis") == "explicit_completed_price":
                    current_price = float(explicit_current)
                    # The history stopping a session short is what the price was handed in
                    # for. It is still reported, as evidence this reading did without.
                    provider_missing = [item if item["id"] != "completed_price_evidence" else {**item, "required": False} for item in provider_missing]
                elif price_path.get("reason") in _UNCROSSABLE_REASONS:
                    current_price = None
                    evidence.pop("current_price", None)
                if price_path.get("state") == "unavailable":
                    provider_missing.append(
                        {
                            "id": "completed_price_path",
                            "provider": prices.meta.provider,
                            "reason": price_path.get("reason", "completed_price_path_unavailable"),
                            "required": True,
                            "attempts": 1,
                            "retryable": False,
                        }
                    )
            elif stale_price is None:
                # A price from an earlier session can only make a position look
                # safer than the evidence supports, so it is withheld entirely.
                try:
                    current_price = float(prices.data["Close"].iloc[-1])
                except (AttributeError, KeyError, IndexError, TypeError, ValueError):
                    current_price = None
            if current_price is not None:
                evidence["current_price"] = current_price
    if explicit_path is not None and evidence.get("completed_price_path") is None:
        # No audit reached the levels -- the provider had nothing to give, or the request
        # declared no plan to audit. The price the caller handed in is then the whole record.
        evidence["completed_price_path"] = explicit_path
    result = reduce_risk(evidence)
    status = "partial" if any(item.get("required") for item in provider_missing) else "needs_input" if result["verdict"] == "INCOMPLETE" else "ok"
    provider_missing_ids = {item["id"] for item in provider_missing}
    missing = [*provider_missing, *({"id": item, "reason": "evidence_required", "required": True} for item in result["missing"] if item not in provider_missing_ids)]
    data = {
        "ticker": ticker,
        **result,
        "current_price": evidence.get("current_price"),
        "max_high_since_entry": evidence.get("max_high_since_entry"),
        "max_high_date": evidence.get("max_high_date"),
        "max_high_withheld_reason": evidence.get("max_high_withheld_reason"),
        "max_high_withheld_date": evidence.get("max_high_withheld_date"),
    }
    return envelope(
        "ticker.risk",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        data=data,
        signals=[
            {"id": item, "state": "fail"} for item in result["failed"]
        ] + [{"id": item, "state": "not_triggered"} for item in result["waiting"]],
        missing=missing,
        sources=sources,
        doctrine_ids=_risk_doctrine_ids(mode, data),
    )


def _risk_doctrine_ids(mode: str, data: Mapping[str, Any]) -> list[str]:
    """The claims this result actually cites: the mode's own risk claims, plus every claim
    the payload names beside a measurement or an action. A fixed list said more than the
    result used in one mode and less than it used in the other."""

    base = (
        ["risk.initial_stop_and_reward", "risk.profit_protection_at_3r"]
        if mode == "prospective"
        else ["risk.hard_stop_and_no_average_down", "risk.profit_protection_at_3r"]
    )
    return base + sorted(_named_doctrine_ids(data) - set(base))


def _named_doctrine_ids(data: Mapping[str, Any]) -> set[str]:
    """Every registered claim the payload names, anywhere in it."""

    named: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            # Every key that names a claim, not only the one called doctrine_id: a block
            # naming the claim a disclaimer came from cites it just as much, and a citation
            # the envelope leaves out is a claim the result used and did not admit to.
            # Caller-supplied evidence travels through the payload, so a name counts only
            # if the registry holds it: an id nobody can look up cites nothing.
            for key, claim in value.items():
                if not isinstance(key, str) or not key.endswith("doctrine_id"):
                    continue
                if isinstance(claim, str) and has_claim(claim):
                    named.add(claim)
            # A block that reads more than one claim -- a measurement plus the convention
            # that sized its window -- names them all, and each is checked the same way.
            for key, extras in value.items():
                if not isinstance(key, str) or not key.endswith("doctrine_ids"):
                    continue
                for extra in extras or []:
                    if isinstance(extra, str) and has_claim(extra):
                        named.add(extra)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(data)
    return named


def _chart(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    try:
        # Imported here so a machine without the plotting stack still runs discovery,
        # help, and every deterministic capability.
        from .chart import render_chart_artifacts
    except ImportError as error:
        return envelope(
            "ticker.chart",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker},
            missing=[
                {
                    "id": "chart_renderer",
                    "reason": f"plotting_stack_unavailable: {error}",
                    "required": True,
                    "retryable": False,
                }
            ],
        )
    try:
        prices = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.chart",
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": ticker},
            fetch=lambda: runtime.price_history(ticker, clock.date.isoformat()),
        )
    except ProviderUnavailable as error:
        return envelope(
            "ticker.chart",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker},
            missing=[_missing_provider(error)],
        )
    stale_price = _stale_price_gap(prices.meta)
    if stale_price is not None:
        return envelope(
            "ticker.chart",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="partial",
            data={"ticker": ticker},
            missing=[stale_price],
            sources=[_source(prices.meta)],
        )
    output_dir = request.get("output_dir")
    if output_dir is not None and (not isinstance(output_dir, str) or not output_dir.strip()):
        raise RequestError("output_dir must be a non-empty path", "output_dir")
    destination = Path(output_dir) if output_dir else Path(__file__).resolve().parents[2] / ".artifacts" / "charts"
    from .chart import ArtifactNameTaken, UnrenderableHistory, UnusableOutputDirectory

    try:
        result = _render(prices.data, ticker, clock, destination)
    except (ArtifactNameTaken, UnusableOutputDirectory) as error:
        # A directory that already holds a different render under this name is something the
        # caller can move, and an internal_error envelope -- which is what an unhandled raise
        # becomes, with the request and the explicit as_of stripped off -- tells them nothing
        # they could act on.
        raise RequestError(str(error), "output_dir") from error
    except UnrenderableHistory as error:
        # The renderer refuses unusable history by raising, and an unhandled raise becomes an
        # internal_error envelope with the request and the explicit as_of stripped off it. The
        # reason it named is the whole point of naming one.
        return envelope(
            "ticker.chart",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker},
            missing=[{"id": "renderable_price_history", "reason": str(error), "required": True}],
            sources=[_source(prices.meta)],
        )
    return _chart_envelope(result, request, ticker, clock, prices)


def _render(data: Any, ticker: str, clock: AnalysisClock, destination: Path) -> dict[str, Any]:
    from .chart import render_chart_artifacts

    return render_chart_artifacts(
        data,
        ticker=ticker,
        as_of=clock.date.isoformat(),
        output_dir=destination,
    )


def _chart_envelope(result: Mapping[str, Any], request: Mapping[str, Any], ticker: str, clock: AnalysisClock, prices: Any) -> dict[str, Any]:
    side_effects = [
        {
            "type": "chart_artifact",
            "path": artifact["path"],
            "as_of": result["as_of"],
            "input_sha256": result["input_sha256"],
            # The overlay's own input, because the file at this path depends on it too.
            "power_play_measured_bars": result["power_play"]["measured_bars"],
        }
        for artifact in result["artifacts"]
    ]
    side_effects.append(
        {
            "type": "artifact_manifest",
            "path": result["manifest_path"],
            "as_of": result["as_of"],
            "input_sha256": result["input_sha256"],
            # Both digests here too. The manifest holds the overlay's input and its name is
            # stamped with it, so a record naming only the price digest identifies this file
            # less completely than the pictures it lists.
            "power_play_measured_bars": result["power_play"]["measured_bars"],
        }
    )
    return envelope(
        "ticker.chart",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        data=result,
        sources=[_source(prices.meta)],
        # And back where the overlay came from, when there is one. ticker.power-play sends a
        # reader here to look at a span; without the return leg an orchestrator that follows
        # these lists draws the picture and has nowhere to carry the answer.
        next_capabilities=(
            ["ticker.qualify", "ticker.setup"]
            + (["ticker.power-play"] if (result.get("power_play") or {}).get("spans") else [])
        ),
        side_effects=side_effects,
    )


def _watchlist(request: Mapping[str, Any], operation: str, runtime: Runtime) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    ledger = runtime.ledger_factory()
    if operation == "watchlist.show":
        return envelope(operation, request=_clean_request(request), as_of=_as_of(clock), data={"records": ledger.show()})
    if operation == "watchlist.history":
        ticker = _ticker(request.get("ticker"))
        return envelope(operation, request=_clean_request({**request, "ticker": ticker}), as_of=_as_of(clock), data={"ticker": ticker, "events": ledger.history(ticker)})
    if operation == "watchlist.record":
        ticker = _ticker(request.get("ticker"))
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
            request=_clean_request({**request, "ticker": ticker, "note": note}),
            as_of=_as_of(clock),
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
            request=_clean_request(request),
            as_of=_as_of(clock),
            data=result,
            side_effects=[{"type": "file_write", "path": result["path"]}],
        )
    raise RequestError(f"unknown operation: {operation}", "operation")


def execute(operation: str, request: Mapping[str, Any], *, runtime: Runtime | None = None) -> dict[str, Any]:
    """Execute one composable capability without printing or mutating implicit state."""

    if not isinstance(request, Mapping):
        raise RequestError("request must be an object", "request")
    runtime = runtime if runtime is not None else Runtime(cache=ProviderCache())
    if operation == "clock":
        return _clock_operation(request)
    if operation == "health":
        return _health(request, runtime)
    if operation == "doctrine.show":
        return _doctrine_show(request)
    if operation == "ticker.qualify":
        return _qualify(request, runtime)
    if operation == "ticker.swings":
        return _swings(request, runtime)
    if operation == "ticker.setup":
        return _setup(request, runtime)
    if operation == "ticker.power-play":
        return _power_play(request, runtime)
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
