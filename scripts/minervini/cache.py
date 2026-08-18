"""Small JSON cache for provider snapshots at external operation boundaries."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, TypeVar

import pandas as pd

from . import SCHEMA_VERSION
from .providers import ProviderSnapshot, SnapshotMeta


# Bumped when a stored snapshot's meaning changes. Version 1 accepted an
# unfinished daily bar as a completed session, so those entries must not be read.
CACHE_SCHEMA_VERSION = "2"

T = TypeVar("T")


def resolve_cache_dir(
    *,
    root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the ignored repo-local cache directory, unless explicitly overridden."""

    environment = os.environ if environ is None else environ
    override = environment.get("MINERVINI_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    repository = root or Path(__file__).resolve().parents[2]
    return repository / ".state" / "cache"


def _normalized_params(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, Mapping):
        return {str(name): _normalized_params(item, key=str(name)) for name, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalized_params(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        normalized = value.strip()
        return normalized.upper() if key in {"symbol", "ticker"} else normalized
    return value


def _session_value(value: str | date) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def _data_document(data: Any) -> Any:
    from .providers.nasdaq import SecurityRecord

    if isinstance(data, list) and data and all(isinstance(item, SecurityRecord) for item in data):
        return {"kind": "security_records", "rows": [asdict(item) for item in data]}
    if not isinstance(data, pd.DataFrame):
        return {"kind": "json", "value": data}
    if isinstance(data.columns, pd.MultiIndex):
        raise TypeError("provider cache supports only single-level DataFrame columns")
    if isinstance(data.index, pd.DatetimeIndex):
        index = {
            "kind": "datetime",
            "values": [value.isoformat() if not pd.isna(value) else None for value in data.index],
            "timezone": str(data.index.tz) if data.index.tz is not None else None,
            "name": data.index.name,
        }
    else:
        index = {"kind": "plain", "values": data.index.tolist(), "name": data.index.name}
    rows = data.astype(object).where(pd.notna(data), None).values.tolist()
    return {
        "kind": "dataframe",
        "columns": data.columns.tolist(),
        "dtypes": [str(dtype) for dtype in data.dtypes],
        "index": index,
        "rows": rows,
    }


def _restore_data(document: Any) -> Any:
    from .providers.nasdaq import SecurityRecord

    if not isinstance(document, Mapping):
        raise ValueError("cache data document is invalid")
    if document.get("kind") == "json":
        return document["value"]
    if document.get("kind") == "security_records":
        rows = document.get("rows")
        if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
            raise ValueError("cache security records document is invalid")
        return [SecurityRecord(**dict(row)) for row in rows]
    if document.get("kind") != "dataframe":
        raise ValueError("cache data document is invalid")
    columns = document["columns"]
    dtypes = document["dtypes"]
    index_document = document["index"]
    if not isinstance(columns, list) or not isinstance(dtypes, list) or not isinstance(index_document, Mapping):
        raise ValueError("cache dataframe document is invalid")
    frame = pd.DataFrame(document["rows"], columns=columns)
    if len(dtypes) != len(columns):
        raise ValueError("cache dataframe dtypes are invalid")
    for column, dtype in zip(columns, dtypes, strict=True):
        frame[column] = frame[column].astype(dtype)
    index_values = index_document["values"]
    if index_document.get("kind") == "datetime":
        timezone_name = index_document.get("timezone")
        index = pd.to_datetime(index_values, utc=timezone_name is not None)
        if timezone_name is not None:
            index = index.tz_convert(timezone_name)
    elif index_document.get("kind") == "plain":
        index = pd.Index(index_values)
    else:
        raise ValueError("cache dataframe index is invalid")
    frame.index = index
    frame.index.name = index_document.get("name")
    return frame


def _snapshot_document(snapshot: ProviderSnapshot[Any]) -> dict[str, Any]:
    return {
        "data": _data_document(snapshot.data),
        "meta": {
            "provider": snapshot.meta.provider,
            "retrieved_at": snapshot.meta.retrieved_at.isoformat(),
            "as_of": snapshot.meta.as_of.isoformat() if snapshot.meta.as_of else None,
            "provider_version": snapshot.meta.provider_version,
            "coverage": snapshot.meta.coverage,
            "stale": snapshot.meta.stale,
            "content_sha256": snapshot.meta.content_sha256,
        },
    }


def _restore_snapshot(document: Mapping[str, Any]) -> ProviderSnapshot[Any]:
    raw_meta = document["meta"]
    if not isinstance(raw_meta, Mapping):
        raise ValueError("cache snapshot metadata is invalid")
    as_of = raw_meta.get("as_of")
    return ProviderSnapshot(
        data=_restore_data(document["data"]),
        meta=SnapshotMeta(
            provider=str(raw_meta["provider"]),
            retrieved_at=datetime.fromisoformat(str(raw_meta["retrieved_at"])),
            as_of=date.fromisoformat(as_of) if isinstance(as_of, str) else None,
            provider_version=raw_meta.get("provider_version"),
            coverage=raw_meta.get("coverage", {}),
            stale=bool(raw_meta.get("stale", False)),
            content_sha256=raw_meta.get("content_sha256"),
        ),
    )


def _atomic_json_write(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, allow_nan=False, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


class ProviderCache:
    """Session-keyed on-disk cache for JSON-safe provider snapshots."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = resolve_cache_dir(root=root, environ=environ)
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _key(
        self,
        provider: str,
        operation: str,
        params: Mapping[str, Any],
        completed_session: str | date,
    ) -> str:
        identity = {
            "adapter_version": SCHEMA_VERSION,
            "provider": provider,
            "operation": operation,
            "params": _normalized_params(params),
            "completed_session": _session_value(completed_session),
        }
        payload = json.dumps(identity, allow_nan=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def call(
        self,
        provider: str,
        operation: str,
        params: Mapping[str, Any],
        completed_session: str | date,
        fetch: Callable[[], ProviderSnapshot[T]],
        *,
        ttl_seconds: float | None = None,
        no_cache: bool = False,
    ) -> ProviderSnapshot[T]:
        """Return a session-stable snapshot, or call the provider and save its response."""

        if no_cache:
            return fetch()
        key = self._key(provider, operation, params, completed_session)
        path = self.path / f"{key}.json"
        cached = self._read(path, provider, operation, params, completed_session, ttl_seconds)
        if cached is not None:
            return cached
        snapshot = fetch()
        if not isinstance(snapshot, ProviderSnapshot):
            raise TypeError("provider cache fetch must return a ProviderSnapshot")
        if snapshot.meta.stale:
            # The session this snapshot missed will be filled in by the provider
            # later; storing it now would pin the gap for as long as the key lives.
            return snapshot
        document = {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "runtime_schema_version": SCHEMA_VERSION,
            "provider": provider,
            "operation": operation,
            "params": _normalized_params(params),
            "completed_session": _session_value(completed_session),
            "created_at": self._now().astimezone(timezone.utc).isoformat(),
            "snapshot": _snapshot_document(snapshot),
        }
        _atomic_json_write(path, document)
        return snapshot

    def _read(
        self,
        path: Path,
        provider: str,
        operation: str,
        params: Mapping[str, Any],
        completed_session: str | date,
        ttl_seconds: float | None,
    ) -> ProviderSnapshot[Any] | None:
        try:
            with path.open(encoding="utf-8") as handle:
                document = json.load(handle)
            if not isinstance(document, Mapping) or document.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
                return None
            if document.get("runtime_schema_version") != SCHEMA_VERSION:
                return None
            if (
                document.get("provider") != provider
                or document.get("operation") != operation
                or document.get("params") != _normalized_params(params)
                or document.get("completed_session") != _session_value(completed_session)
            ):
                return None
            if ttl_seconds is not None:
                created_at = datetime.fromisoformat(str(document["created_at"]))
                if self._now().astimezone(timezone.utc) > created_at.astimezone(timezone.utc) + timedelta(seconds=ttl_seconds):
                    return None
            snapshot = document["snapshot"]
            if not isinstance(snapshot, Mapping):
                return None
            return _restore_snapshot(snapshot)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return None


__all__ = ["CACHE_SCHEMA_VERSION", "ProviderCache", "resolve_cache_dir"]
