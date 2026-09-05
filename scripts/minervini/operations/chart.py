"""Chart artifact requests and response composition."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from ..clock import AnalysisClock
from ..contracts import RequestError, envelope
from ..power_play_evidence import ASKED_UNDER
from ..runtime import Runtime

from . import PriceRead, _as_of, _clean_request, _clock, _price_read, _source, _ticker


def _chart(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    try:
        # Imported here so a machine without the plotting stack still runs discovery,
        # help, and every deterministic capability.
        from ..chart import render_chart_artifacts
    except ImportError as error:
        return envelope(
            "ticker.chart",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker},
            missing=[
                {
                    "id": "chart_renderer",
                    "reason": f"plotting_stack_unavailable: {error}",
                    "required": True,
                    "retryable": False,
                }
            ],
        )
    prices, gap, _ = _price_read(
        runtime, request, clock, ticker, PriceRead("ticker.chart", {})
    )
    if gap is not None:
        return gap
    output_dir = request.get("output_dir")
    if output_dir is not None and (not isinstance(output_dir, str) or not output_dir.strip()):
        raise RequestError("output_dir must be a non-empty path", "output_dir")
    destination = Path(output_dir) if output_dir else Path(__file__).resolve().parents[3] / ".artifacts" / "charts"
    from ..chart import ArtifactNameTaken, UnrenderableHistory, UnusableOutputDirectory

    try:
        result = _render(prices.data, ticker, clock, destination)
    except (ArtifactNameTaken, UnusableOutputDirectory) as error:
        # A directory that already holds a different render under this name is something the
        # caller can move, and an internal_error envelope -- which is what an unhandled raise
        # becomes, with the request and the explicit as_of stripped off -- tells them nothing
        # they could act on.
        raise RequestError(str(error), "output_dir") from error
    except UnrenderableHistory as error:
        # The renderer refuses unusable history by raising, and an unhandled raise becomes an
        # internal_error envelope with the request and the explicit as_of stripped off it. The
        # reason it named is the whole point of naming one.
        return envelope(
            "ticker.chart",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker},
            missing=[{"id": "renderable_price_history", "reason": str(error), "required": True}],
            sources=[_source(prices.meta)],
        )
    return _chart_envelope(result, request, ticker, clock, prices)


def _render(data: Any, ticker: str, clock: AnalysisClock, destination: Path) -> dict[str, Any]:
    from ..chart import render_chart_artifacts

    return render_chart_artifacts(
        data,
        ticker=ticker,
        as_of=clock.date.isoformat(),
        output_dir=destination,
    )


def _chart_envelope(result: Mapping[str, Any], request: Mapping[str, Any], ticker: str, clock: AnalysisClock, prices: Any) -> dict[str, Any]:
    side_effects = [
        {
            "type": "chart_artifact",
            "path": artifact["path"],
            "as_of": result["as_of"],
            "input_sha256": result["input_sha256"],
            # The overlay's own input, because the file at this path depends on it too.
            "power_play_measured_bars": result["power_play"]["measured_bars"],
        }
        for artifact in result["artifacts"]
    ]
    side_effects.append(
        {
            "type": "artifact_manifest",
            "path": result["manifest_path"],
            "as_of": result["as_of"],
            "input_sha256": result["input_sha256"],
            # Both digests here too. The manifest holds the overlay's input and its name is
            # stamped with it, so a record naming only the price digest identifies this file
            # less completely than the pictures it lists.
            "power_play_measured_bars": result["power_play"]["measured_bars"],
        }
    )
    return envelope(
        "ticker.chart",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        data=result,
        sources=[_source(prices.meta)],
        # And back where the overlay came from, when there is one. ticker.power-play sends a
        # reader here to look at a span; without the return leg an orchestrator that follows
        # these lists draws the picture and has nowhere to carry the answer.
        next_capabilities=(
            ["ticker.qualify", "ticker.setup"]
            + (["ticker.power-play"] if (result.get("power_play") or {}).get("spans") else [])
        ),
        # What decided the picture. The chart publishes a drawing rather than a measurement, so
        # none of these reaches the payload to be harvested -- but the chain it draws anchors
        # for and the span it shades are cut by them, and a reader shown a drawn span with no
        # citation has a picture they cannot argue with.
        #
        # Cited without being registered as their consumer, which is not an oversight: a
        # consumer is a capability that can be handed what its claim requires, and this one
        # takes no `accounting_integrity` to be given for the Power Play exception. It runs the
        # evidence builder to find the span and then draws it; naming what cut the span is how
        # the picture stays auditable, and it is a weaker thing to say than consuming.
        #
        # Taken from the list the power-play module maintains rather than copied into a literal
        # here. A literal was written with four of the five: the convention that decides what a
        # chart answer *is* is read only once there is a question to key, and the fixture the
        # sweep drew had no span and therefore asked nothing. One list, in the module whose
        # question it is, cannot go one claim out of date without that module noticing.
        doctrine_ids=sorted(set(ASKED_UNDER)),
        side_effects=side_effects,
    )
