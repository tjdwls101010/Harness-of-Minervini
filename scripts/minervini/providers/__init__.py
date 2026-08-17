from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
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
    ) -> None:
        self.provider = provider
        self.reason = reason
        self.operation = operation
        self.attempts = attempts
        self.retryable = retryable
        detail = f"{provider} unavailable: {reason}"
        if operation:
            detail = f"{detail} ({operation})"
        super().__init__(detail)


def fetch_with_one_retry(provider: str, operation: str, fetch: Callable[[], T]) -> T:
    """Make the one permitted retry at an external boundary and preserve its failure."""

    last_error: Exception | None = None
    for _ in range(2):
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
    ) from last_error


__all__ = ["ProviderSnapshot", "ProviderUnavailable", "SnapshotMeta", "fetch_with_one_retry"]
