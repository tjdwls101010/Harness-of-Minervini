"""Explicit research-ledger operations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping
from ..contracts import RequestError, envelope
from ..runtime import Runtime

from . import _as_of, _clean_request, _clock, _ticker


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
