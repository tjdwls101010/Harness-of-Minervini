"""Pure same-industry leadership comparison from normalized provider rows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from .numbers import finite as _number


_US_EXCHANGES = frozenset({"NASDAQ", "NYSE", "NYSEAMERICAN", "NYSE ARCA", "CBOE", "IEX", "MEMX"})
_COMMON_TYPES = frozenset({"common", "common_stock", "common stock", "adr"})
_RANK_BASIS = [
    "rs_rating_desc",
    "return_3m_pct_desc",
    "distance_from_52_week_high_pct_asc",
    "ticker_asc",
    "instrument_id_asc",
]


def compare_same_industry_peers(target: Mapping[str, Any], candidates: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare one US-listed common stock or ADR with supplied industry peers.

    The caller owns classification and evidence collection. This seam neither
    looks up providers nor infers industry identities; it ranks only exact,
    in-scope matches with dated IBD RS and yfinance price evidence.
    """
    target_identity = _required_target_identity(target)
    target_row, target_missing = _leadership_row(target)
    if not isinstance(candidates, Iterable) or isinstance(candidates, (str, bytes, Mapping)):
        raise ValueError("candidates must be an iterable of provider rows")

    exclusions: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    if target_missing:
        missing.append(_missing_record(target, target_missing))

    eligible: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            exclusions.append({"instrument_id": None, "ticker": None, "reasons": ["invalid_instrument_record"]})
            continue
        if _same_instrument(candidate, target_identity["instrument_id"]):
            continue
        reasons = _candidate_exclusions(candidate, target_identity["industry_id"])
        if reasons:
            exclusions.append(_exclusion_record(candidate, reasons))
            continue
        candidate_row, candidate_missing = _leadership_row(candidate)
        if candidate_missing:
            missing.append(_missing_record(candidate, candidate_missing))
            continue
        eligible.append(candidate_row)

    if target_missing:
        return {
            "comparison_state": "incomplete",
            "target": _target_record(target, None),
            "peer_count": 0,
            "peers": [],
            "rank_basis": list(_RANK_BASIS),
            "missing": missing,
            "exclusions": exclusions,
        }

    ranked = sorted([target_row, *eligible], key=_rank_key)
    records = [_ranked_record(row, rank) for rank, row in enumerate(ranked, start=1)]
    target_record = next(record for record in records if record["instrument_id"] == target_identity["instrument_id"])
    peers = [record for record in records if record["instrument_id"] != target_identity["instrument_id"]]
    return {
        "comparison_state": "incomplete" if missing else "complete",
        "target": target_record,
        "peer_count": len(peers),
        "peers": peers,
        "rank_basis": list(_RANK_BASIS),
        "missing": missing,
        "exclusions": exclusions,
    }


def _required_target_identity(target: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(target, Mapping):
        raise ValueError("target must be a provider row")
    instrument_id = _text(target.get("instrument_id"))
    if instrument_id is None:
        raise ValueError("target requires a stable instrument_id")
    industry_id = _text(target.get("industry_id"))
    if industry_id is None:
        raise ValueError("target requires an exact industry_id")
    scope_reasons = _scope_exclusions(target)
    if scope_reasons:
        raise ValueError("target must be a US-listed common stock or ADR")
    return {"instrument_id": instrument_id, "industry_id": industry_id}


def _candidate_exclusions(candidate: Mapping[str, Any], industry_id: str) -> list[str]:
    instrument_id = _text(candidate.get("instrument_id"))
    if instrument_id is None:
        return ["missing_instrument_id"]
    candidate_industry = _text(candidate.get("industry_id"))
    if candidate_industry != industry_id:
        return ["different_industry"]
    return _scope_exclusions(candidate)


def _scope_exclusions(row: Mapping[str, Any]) -> list[str]:
    instrument_type = str(row.get("instrument_type", row.get("security_type", ""))).strip().lower()
    exchange = str(row.get("exchange", "")).strip().upper()
    country = str(row.get("listing_country", "")).strip().upper()
    reasons: list[str] = []
    excluded_type = instrument_type in {"etf", "fund", "exchange_traded_fund"}
    if excluded_type or row.get("is_etf"):
        reasons.append("etf_context_only")
    if country != "US":
        reasons.append("non_us_listing")
    if exchange not in _US_EXCHANGES:
        reasons.append("unsupported_exchange")
    is_adr = bool(row.get("is_adr")) or instrument_type == "adr"
    if instrument_type not in _COMMON_TYPES and not is_adr and not excluded_type:
        reasons.append("unsupported_instrument_type")
    return reasons


def _leadership_row(row: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    rs, rs_missing = _rs_evidence(row.get("rs_evidence"))
    price, price_missing = _price_evidence(row.get("price_evidence"))
    return {
        "instrument_id": str(row.get("instrument_id")),
        "ticker": row.get("ticker"),
        "industry_id": row.get("industry_id"),
        "leadership_evidence": {"rs_rating": rs, "price": price},
    }, [*rs_missing, *price_missing]


def _rs_evidence(value: Any) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(value, Mapping):
        return None, ["rs_evidence"]
    missing = _rs_metadata_missing(value)
    rating = value.get("rating")
    if not _number(rating) or not 1 <= float(rating) <= 99:
        missing.append("rs_evidence.rating")
    if missing:
        return None, missing
    return {"value": float(rating), "as_of": value["as_of"], "provider": value["provider"]}, []


def _price_evidence(value: Any) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(value, Mapping):
        return None, ["price_evidence"]
    missing = _price_metadata_missing(value)
    fields = ("return_3m_pct", "distance_from_52_week_high_pct")
    for field in fields:
        if not _number(value.get(field)):
            missing.append(f"price_evidence.{field}")
    if missing:
        return None, missing
    return {
        "return_3m_pct": float(value["return_3m_pct"]),
        "distance_from_52_week_high_pct": float(value["distance_from_52_week_high_pct"]),
        "as_of": value["as_of"],
        "provider": value["provider"],
    }, []


def _rs_metadata_missing(value: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    if value.get("provider") not in {"ibd-rs-rating", "first_party"}:
        missing.append("rs_evidence.provider")
    return [*missing, *_date_missing(value, "rs_evidence")]


def _price_metadata_missing(value: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    if value.get("provider") != "yfinance":
        missing.append("price_evidence.provider")
    return [*missing, *_date_missing(value, "price_evidence")]


def _date_missing(value: Mapping[str, Any], prefix: str) -> list[str]:
    missing: list[str] = []
    as_of = value.get("as_of")
    if not isinstance(as_of, str):
        missing.append(f"{prefix}.as_of")
    else:
        try:
            date.fromisoformat(as_of)
        except ValueError:
            missing.append(f"{prefix}.as_of")
    return missing


def _rank_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    evidence = row["leadership_evidence"]
    rs = evidence["rs_rating"]
    price = evidence["price"]
    return (
        -rs["value"],
        -price["return_3m_pct"],
        price["distance_from_52_week_high_pct"],
        str(row.get("ticker") or ""),
        row["instrument_id"],
    )


def _target_record(target: Mapping[str, Any], rank: int | None) -> dict[str, Any]:
    row, _ = _leadership_row(target)
    return _ranked_record(row, rank)


def _ranked_record(row: Mapping[str, Any], rank: int | None) -> dict[str, Any]:
    return {"rank": rank, **row}


def _missing_record(row: Mapping[str, Any], fields: list[str]) -> dict[str, Any]:
    return {"instrument_id": row.get("instrument_id"), "ticker": row.get("ticker"), "fields": fields}


def _exclusion_record(row: Mapping[str, Any], reasons: list[str]) -> dict[str, Any]:
    return {"instrument_id": row.get("instrument_id"), "ticker": row.get("ticker"), "reasons": reasons}


def _same_instrument(row: Mapping[str, Any], target_id: str) -> bool:
    return _text(row.get("instrument_id")) == target_id


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value and value == value.strip() else None


__all__ = ["compare_same_industry_peers"]
