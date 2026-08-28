"""The component attestations `ticker.risk` accepts, for tests that need a converged entry.

BUY-READY is reached from component envelopes and from nothing else, so every test that
wants one has to carry the references the reducer cross-checks. They live here rather than
in each test file because the fields being compared are the reducer's, and five hand-copied
versions of them is five places to drift into a test that passes for a reason the harness no
longer holds.

What a test says by using this is "these four planes were measured." A test about how an
unmeasured plane is treated writes its own evidence -- see
`tests/260828/unit/test_an_unattested_word_cannot_mint_a_buy_verdict.py`, which is the
specification of this shape and deliberately does not import it.
"""

from __future__ import annotations

from typing import Any

from scripts.minervini.contracts import envelope


TICKER = "TEST"
AS_OF = "2025-12-31"

_OPERATION = {
    "market": "market.snapshot",
    "eligibility": "ticker.qualify",
    "setup": "ticker.setup",
    "fundamentals": "ticker.fundamentals",
}

_CONVERGED = {
    "market": "favorable",
    "eligibility": "eligible",
    "setup": "ready",
    "fundamentals": "supports_convergence",
}


def attested(plane: str, state: str, *, ticker: str = TICKER, as_of: str = AS_OF, status: str = "ok") -> dict[str, Any]:
    """One plane's word, carrying the reference to the envelope that reached it."""

    return {
        "state": state,
        "attested_by": {
            "operation": _OPERATION[plane],
            # The market is measured for the session and not for a ticker.
            "ticker": None if plane == "market" else ticker,
            "as_of": as_of,
            "status": status,
        },
    }


_STATE_FIELD = {
    "eligibility": "eligibility_state",
    "setup": "setup_state",
    "fundamentals": "fundamentals_state",
}


def envelopes(*, ticker: str = TICKER, as_of: str = AS_OF, **states: str) -> list[dict[str, Any]]:
    """The four component envelopes, in the shape their capabilities return them.

    For the callers that go through `ticker.risk` itself rather than through the reducer: the
    capability builds the attestations from these, so a test that hands it envelopes is
    testing the channel a person uses and not a shape only tests produce.
    """

    out: list[dict[str, Any]] = []
    for plane, default in _CONVERGED.items():
        state = states.get(plane, default)
        data = {"regime": {"judgment": state}} if plane == "market" else {"ticker": ticker, _STATE_FIELD[plane]: state}
        out.append(
            # Through the real builder, so a test envelope cannot be a shape the capabilities
            # never produce -- which is the shape `ticker.risk` refuses.
            envelope(
                _OPERATION[plane],
                request={"ticker": None if plane == "market" else ticker},
                as_of={"mode": "explicit", "date": as_of, "timezone": "America/New_York", "completed_session": True},
                status="ok",
                data=data,
                sources=[{"provider": "fixture-prices", "as_of": as_of, "stale": False}],
            )
        )
    return out


def stub(plane: str, state: str, *, ticker: str = TICKER, as_of: str = AS_OF) -> dict[str, Any]:
    """The fields `ticker.risk` reads, and nothing else -- what a hand-assembled attachment is."""

    return {
        "operation": _OPERATION[plane],
        "as_of": {"date": as_of},
        "status": "ok",
        "data": {"regime": {"judgment": state}} if plane == "market" else {"ticker": ticker, _STATE_FIELD[plane]: state},
    }


def planes(*, ticker: str = TICKER, as_of: str = AS_OF, **states: str) -> dict[str, Any]:
    """The four attested planes plus the ticker and session they are attested against.

    Both identity fields travel with them: the reducer compares every attestation against
    the request it is reducing, so a payload carrying attestations and no ticker is not a
    converged entry, it is four references to nothing.
    """

    return {
        "ticker": ticker,
        "as_of": as_of,
        **{
            plane: attested(plane, states.get(plane, default), ticker=ticker, as_of=as_of)
            for plane, default in _CONVERGED.items()
        },
    }
