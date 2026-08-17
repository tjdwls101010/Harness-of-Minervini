from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Callable

from . import ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry


NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

_OTHER_LISTED_EXCHANGES = {
    "A": "NYSE American",
    "B": "NYSE",
    "C": "NYSE National",
    "N": "NYSE",
    "P": "NYSE Arca",
    "V": "IEX",
    "Z": "Cboe BZX",
}


@dataclass(frozen=True)
class SecurityRecord:
    instrument_id: str
    symbol: str
    exchange: str
    security_name: str
    instrument_type: str
    is_adr: bool
    eligible: bool
    exclusion_reason: str | None


def _classification(symbol: str, name: str, etf: str) -> tuple[str, bool, str | None]:
    lower = name.lower()
    if etf.upper() == "Y":
        return "etf", False, "etf"
    if " unit" in lower or symbol.endswith("U"):
        return "unit", False, "unit"
    if "warrant" in lower or symbol.endswith("W"):
        return "warrant", False, "warrant"
    if "preferred" in lower:
        return "preferred", False, "preferred"
    if "acquisition" in lower or "shell" in lower or "spac" in lower:
        return "spac_or_shell", False, "spac_or_shell"
    if "american depositary" in lower or "depositary share" in lower or " adr" in f" {lower}":
        return "adr", True, None
    if "common stock" in lower or "ordinary share" in lower:
        return "common_stock", True, None
    return "unsupported", False, "unsupported_instrument_type"


def _rows(document: str, required: set[str]) -> tuple[dict[str, int], list[list[str]]]:
    rows = [line.split("|") for line in document.splitlines() if "|" in line]
    if not rows:
        raise ProviderUnavailable("nasdaq", "invalid_security_master", operation="current_security_master")
    header = {name.strip(): index for index, name in enumerate(rows[0])}
    if not required.issubset(header):
        raise ProviderUnavailable("nasdaq", "invalid_security_master", operation="current_security_master")
    return header, rows[1:]


def _value(row: list[str], header: dict[str, int], name: str) -> str:
    index = header[name]
    return row[index].strip() if len(row) > index else ""


def _is_footer(symbol: str) -> bool:
    return symbol.upper().startswith("FILE CREATION TIME:")


def _record(symbol: str, exchange: str, name: str, etf: str) -> SecurityRecord:
    instrument_type, eligible, reason = _classification(symbol, name, etf)
    return SecurityRecord(
        instrument_id=f"nasdaq-trader:{exchange}:{symbol}",
        symbol=symbol,
        exchange=exchange,
        security_name=name,
        instrument_type=instrument_type,
        is_adr=instrument_type == "adr",
        eligible=eligible,
        exclusion_reason=reason,
    )


def _parse_nasdaq_listed(document: str) -> list[SecurityRecord]:
    header, rows = _rows(document, {"Symbol", "Security Name", "Test Issue", "ETF"})
    records: list[SecurityRecord] = []
    for row in rows:
        symbol = _value(row, header, "Symbol").upper()
        if not symbol or _is_footer(symbol) or _value(row, header, "Test Issue").upper() == "Y":
            continue
        records.append(_record(symbol, "NASDAQ", _value(row, header, "Security Name"), _value(row, header, "ETF")))
    return records


def _other_listed_exchange(code: str) -> str:
    return _OTHER_LISTED_EXCHANGES.get(code.upper(), f"OTHER:{code.upper() or 'UNKNOWN'}")


def _parse_other_listed(document: str) -> list[SecurityRecord]:
    header, rows = _rows(document, {"ACT Symbol", "Security Name", "Exchange", "Test Issue", "ETF"})
    records: list[SecurityRecord] = []
    for row in rows:
        symbol = _value(row, header, "ACT Symbol").upper()
        if not symbol or _is_footer(symbol) or _value(row, header, "Test Issue").upper() == "Y":
            continue
        records.append(
            _record(
                symbol,
                _other_listed_exchange(_value(row, header, "Exchange")),
                _value(row, header, "Security Name"),
                _value(row, header, "ETF"),
            )
        )
    return records


def parse_current_security_master(nasdaq_document: str, other_document: str | None = None) -> list[SecurityRecord]:
    """Parse current Nasdaq Trader listings without claiming historical coverage."""

    records = _parse_nasdaq_listed(nasdaq_document)
    if other_document is not None:
        records.extend(_parse_other_listed(other_document))
    return records


def current_security_master(
    request: Callable[[str], str], *, retrieved_at: datetime | None = None
) -> ProviderSnapshot[list[SecurityRecord]]:
    """Fetch both current Nasdaq Trader listings through one retryable boundary."""

    def fetch_documents() -> tuple[str, str]:
        return request(NASDAQ_LISTED_URL), request(OTHER_LISTED_URL)

    nasdaq_document, other_document = fetch_with_one_retry("nasdaq", "current_security_master", fetch_documents)
    observed_at = retrieved_at or datetime.now(timezone.utc)
    source_documents = {
        "nasdaqlisted.txt": (NASDAQ_LISTED_URL, nasdaq_document),
        "otherlisted.txt": (OTHER_LISTED_URL, other_document),
    }
    content = "\0".join(document for _, document in source_documents.values()).encode()
    return ProviderSnapshot(
        data=parse_current_security_master(nasdaq_document, other_document),
        meta=SnapshotMeta(
            provider="nasdaq",
            retrieved_at=observed_at,
            as_of=observed_at.date(),
            coverage={
                "kind": "current_security_master_only",
                "historical": False,
                "sources": {
                    name: {"url": url, "content_sha256": sha256(document.encode()).hexdigest()}
                    for name, (url, document) in source_documents.items()
                },
            },
            content_sha256=sha256(content).hexdigest(),
        ),
    )


def historical_security_master(as_of: str | date) -> ProviderSnapshot[list[SecurityRecord]]:
    """Refuse to substitute today's master for a historical as-of request."""

    raise ProviderUnavailable("nasdaq", "historical_security_master_unavailable", operation="security_master")
