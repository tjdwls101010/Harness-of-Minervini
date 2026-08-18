from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import re
import threading
import time
from typing import Any, Callable, Generic, Mapping, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class SnapshotMeta:
    """Audit metadata accompanying a provider response without inventing coverage."""

    provider: str
    retrieved_at: datetime
    as_of: date | None
    provider_version: str | None = None
    coverage: Mapping[str, Any] = field(default_factory=dict)
    stale: bool = False
    content_sha256: str | None = None


@dataclass(frozen=True)
class ProviderSnapshot(Generic[T]):
    data: T
    meta: SnapshotMeta


class ProviderUnavailable(RuntimeError):
    """A typed boundary failure callers can convert into unavailable evidence."""

    def __init__(
        self,
        provider: str,
        reason: str,
        *,
        operation: str | None = None,
        attempts: int = 1,
        retryable: bool = False,
        detail: str | None = None,
    ) -> None:
        self.provider = provider
        self.reason = reason
        self.operation = operation
        self.attempts = attempts
        self.retryable = retryable
        self.detail = redact(detail)[:DETAIL_LIMIT] if detail else detail
        detail = f"{provider} unavailable: {reason}"
        if operation:
            detail = f"{detail} ({operation})"
        super().__init__(detail)


class RequestThrottle:
    """Space consecutive requests at a boundary that rate-limits by source address.

    SEC answers a burst with a 403 block on the whole exit IP rather than a
    per-request rejection, so spacing is what keeps the next analysis session
    able to reach it at all.
    """

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = min_interval_seconds
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._monotonic()
            if self._last_request_at is not None:
                remaining = self._min_interval - (now - self._last_request_at)
                if remaining > 0:
                    self._sleep(remaining)
                    # Reread rather than assume: a sleep that overshot would
                    # otherwise be credited to the next interval as well.
                    now = self._monotonic()
            self._last_request_at = now


DETAIL_LIMIT = 200

# A boundary failure is reported to whoever runs the CLI, so the message it
# carries must not become a second channel for whatever the SDK put in its
# exception text: query strings carry API keys, and this harness's own SEC
# User-Agent carries the operator's email.
_SECRET_WORD = r"[\w-]*(?:api[_-]?key|apikey|token|secret|password|passwd|bearer|auth)[\w-]*"
_REDACTIONS = (
    # header form: `Authorization: Basic ...`, `Cookie: session=...`
    (re.compile(r"(?i)\b(authorization|cookie|set-cookie|proxy-authorization)\s*:\s*[^\r\n]+"), r"\1: [redacted]"),
    # assignment form, quoted or bare: `api_key=...`, `"token":"..."`, `Bearer ...`
    (re.compile(r'(?i)\b(' + _SECRET_WORD + r')\b["\']?\s*[=:]\s*["\']?[^\s"\',;&})\]]+'), r"\1=[redacted]"),
    (re.compile(r"(?i)\bbearer\s+\S+"), "bearer [redacted]"),
    # path form: `/v1/token/sk-live-abc`
    (re.compile(r"(?i)/(" + _SECRET_WORD + r")/[^/\s?#]+"), r"/\1/[redacted]"),
    # any query string at all: too many providers put credentials there
    (re.compile(r"\?\S*"), "?[redacted]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[redacted-email]"),
)


def redact(text: str) -> str:
    """Strip credentials and operator identity from an external failure message."""

    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def fetch_with_one_retry(
    provider: str,
    operation: str,
    fetch: Callable[[], T],
    *,
    backoff_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Make the one permitted retry at an external boundary and preserve its failure."""

    last_error: Exception | None = None
    for attempt in range(2):
        if attempt:
            sleep(backoff_seconds)
        try:
            return fetch()
        except Exception as error:  # External SDKs expose unrelated exception classes.
            last_error = error
    assert last_error is not None
    raise ProviderUnavailable(
        provider,
        "request_failed",
        operation=operation,
        attempts=2,
        retryable=True,
        detail=f"{type(last_error).__name__}: {last_error}",
    ) from last_error


__all__ = ["ProviderSnapshot", "ProviderUnavailable", "RequestThrottle", "SnapshotMeta", "fetch_with_one_retry", "redact"]
