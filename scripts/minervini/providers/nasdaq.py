from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from . import ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry


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


def _classification(symbol: str, name: str, etf: str, test_issue: str) -> tuple[str, bool, str | None]:
    lower = name.lower()
    if etf.upper() == "Y":
        return "etf", False, "etf"
    if test_issue.upper() == "Y":
        return "test_issue", False, "test_issue"
    if " unit" in lower or symbol.endswith("U"):
        return "unit", False, "unit"
    if "warrant" in lower or symbol.endswith("W"):
        return "warrant", False, "warrant"
    if "preferred" in lower:
        return "preferred", False, "preferred"
    if "acquisition" in lower or "shell" in lower or "spac" in lower:
        return "spac_or_shell", False, "spac_or_shell"
    if "american depositary" in lower or " adr" in f" {lower}":
        return "adr", True, None
    if "common stock" in lower or "ordinary share" in lower:
        return "common_stock", True, None
    return "unsupported", False, "unsupported_instrument_type"


def parse_current_security_master(document: str) -> list[SecurityRecord]:
    """Parse a frozen/current Nasdaq Trader listing without claiming historical coverage."""

    rows = [line.split("|") for line in document.splitlines() if "|" in line]
    if not rows:
        raise ProviderUnavailable("nasdaq", "invalid_security_master", operation="current_security_master")
    header = {name.strip(): index for index, name in enumerate(rows[0])}
    required = {"Symbol", "Security Name", "Test Issue", "ETF"}
    if not required.issubset(header):
        raise ProviderUnavailable("nasdaq", "invalid_security_master", operation="current_security_master")

    records: list[SecurityRecord] = []
    for row in rows[1:]:
        symbol = row[header["Symbol"]].strip().upper() if len(row) > header["Symbol"] else ""
        if not symbol or symbol.startswith("FILE CREATION"):
            continue
        name = row[header["Security Name"]].strip()
        etf = row[header["ETF"]].strip()
        test_issue = row[header["Test Issue"]].strip()
        instrument_type, eligible, reason = _classification(symbol, name, etf, test_issue)
        records.append(
            SecurityRecord(
                instrument_id=f"nasdaq-current:{symbol}",
                symbol=symbol,
                exchange="NASDAQ",
                security_name=name,
                instrument_type=instrument_type,
                is_adr=instrument_type == "adr",
                eligible=eligible,
                exclusion_reason=reason,
            )
        )
    return records


def current_security_master(
    fetch: Callable[[], str], *, retrieved_at: datetime | None = None
) -> ProviderSnapshot[list[SecurityRecord]]:
    document = fetch_with_one_retry("nasdaq", "current_security_master", fetch)
    observed_at = retrieved_at or datetime.now(timezone.utc)
    return ProviderSnapshot(
        data=parse_current_security_master(document),
        meta=SnapshotMeta(
            provider="nasdaq",
            retrieved_at=observed_at,
            as_of=observed_at.date(),
            coverage={"kind": "current_security_master_only", "historical": False},
        ),
    )


def historical_security_master(as_of: str | date) -> ProviderSnapshot[list[SecurityRecord]]:
    """Refuse to substitute today's master for a historical as-of request."""

    raise ProviderUnavailable("nasdaq", "historical_security_master_unavailable", operation="security_master")
