from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
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
        self.detail = detail
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

    def wait(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = self._min_interval - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
                now += remaining
        self._last_request_at = now


DETAIL_LIMIT = 200


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
        detail=f"{type(last_error).__name__}: {last_error}"[:DETAIL_LIMIT],
    ) from last_error


__all__ = ["ProviderSnapshot", "ProviderUnavailable", "RequestThrottle", "SnapshotMeta", "fetch_with_one_retry"]
