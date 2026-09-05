"""Interface discovery and runtime readiness."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Mapping
from ..capabilities import CAPABILITIES
from ..contracts import RequestError, envelope
from ..doctrine import get_claim, list as list_doctrine, validate as validate_doctrine
from ..providers import DETAIL_LIMIT, ProviderUnavailable, redact
from ..providers.rs import REQUIRED_PACKAGE_VERSION
from ..runtime import Runtime, _local_configuration

from . import _as_of, _clean_request, _clock, _missing_provider


def _describe(request: Mapping[str, Any]) -> dict[str, Any]:
    name = request.get("capability")
    capability = CAPABILITIES.get(name) if isinstance(name, str) else None
    if capability is None:
        raise RequestError(f"unknown capability: {name}", "capability")
    return envelope("describe", request={"capability": name}, data=capability.description())


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


def _doctrine_list(request: Mapping[str, Any]) -> dict[str, Any]:
    for name in ("context", "family", "layer"):
        value = request.get(name)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise RequestError(f"{name} must be a non-empty string", name)
    clock = _clock(request.get("as_of"))
    rows = []
    for result in list_doctrine(context=request.get("context")):
        record = result["claim"]
        if request.get("family") is not None and not record["id"].startswith(request["family"]):
            continue
        if request.get("layer") is not None and record["layer"] != request["layer"]:
            continue
        row = {key: record[key] for key in ("id", "title", "kind", "layer", "computability", "consumers")}
        row["roles"] = sorted({threshold["role"] for threshold in record.get("thresholds", {}).values()})
        rows.append(row)
    return envelope(
        "doctrine.list",
        request=_clean_request(request),
        as_of=_as_of(clock),
        data={"claims": sorted(rows, key=lambda row: row["id"])},
        sources=[{"provider": "doctrine_registry", "path": "doctrine/claims.json"}],
        next_capabilities=["doctrine.show"] if rows else [],
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
