"""An axis recording the drawing operations a chart test observes."""

from typing import Any


class RecordingAxis:
    """Keeps what was drawn on it and what each thing was called.

    The labels are the part under test here and a rendered PNG cannot be asked about them, so
    this is where the wording gets pinned."""

    def __init__(self) -> None:
        self.labels: list[str] = []
        self.markers: list[float] = []
        self.spans: list[tuple] = []
        self.rules: list[Any] = []
        self.points: list[tuple] = []
        self.levels: list[tuple | float] = []
        # How each thing was drawn, not only that it was. A reviewer set every marker to size
        # zero and every rule to width zero and the whole suite passed: the drawing calls all
        # happened, and nothing on the picture could be seen.
        self.drawn: list[dict[str, Any]] = []

    def plot(self, x, y, **kwargs) -> None:
        self.points.append((x[0], float(y[0])))
        self.markers.append(float(y[0]))
        self.drawn.append(kwargs)
        if kwargs.get("label"):
            self.labels.append(str(kwargs["label"]))

    def axvline(self, position, **kwargs) -> None:
        self.rules.append(position)
        self.drawn.append(kwargs)
        if kwargs.get("label"):
            self.labels.append(str(kwargs["label"]))

    def axvspan(self, start, end, **kwargs) -> None:
        self.spans.append((start, end))
        self.drawn.append(kwargs)
        if kwargs.get("label"):
            self.labels.append(str(kwargs["label"]))

    def hlines(self, level, start, end, **kwargs) -> None:
        self.levels.append((float(level), start, end))
        self.drawn.append(kwargs)
        if kwargs.get("label"):
            self.labels.append(str(kwargs["label"]))

    def axhline(self, level, **kwargs) -> None:
        self.levels.append(float(level))
        self.drawn.append(kwargs)
        if kwargs.get("label"):
            self.labels.append(str(kwargs["label"]))

    def legend(self, *_args, **_kwargs) -> None:
        return None
