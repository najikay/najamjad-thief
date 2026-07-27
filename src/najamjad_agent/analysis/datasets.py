"""Typed readers for the measurement files the notebook plots (T-2214).

The notebook is a *presentation* layer. Everything it does beyond drawing lives
here so it can be unit-tested and held to the same line and type gates as the
rest of the source — a chart nobody can test is a chart nobody should trust.

Every loader is total on the data we actually produce and raises a named error
on anything else, so a notebook run against a truncated or hand-edited results
file fails loudly instead of quietly plotting nonsense.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

RESULTS = Path("results")


class MissingDataError(FileNotFoundError):
    """A measurement file the notebook needs has not been generated yet."""


@dataclass(frozen=True)
class Point:
    """One parameter value, measured over `played` seeded games.

    `ci` is `None` when the source file carries no interval, which is not the
    same as an interval of zero width and must not be drawn as one.
    """

    value: float
    played: int
    successes: int
    rate: float
    ci: tuple[float, float] | None = None

    @property
    def error(self) -> tuple[float, float]:
        """Asymmetric (lower, upper) bar lengths, as matplotlib wants them.

        No interval means no bar. Substituting `(0, 0)` for a missing interval
        would draw a whisker from the axis to the point — inventing an enormous
        uncertainty for a measurement that simply did not record one.
        """
        if self.ci is None:
            return (0.0, 0.0)
        return (max(0.0, self.rate - self.ci[0]), max(0.0, self.ci[1] - self.rate))


@dataclass(frozen=True)
class Sweep:
    """One knob varied one-at-a-time, everything else held at its default."""

    knob: str
    why: str
    points: tuple[Point, ...]

    @property
    def best(self) -> Point:
        """The measured optimum — what the default should be set to."""
        return max(self.points, key=lambda point: point.rate)

    @property
    def span(self) -> float:
        """Swing in outcome across the knob's range: the sensitivity itself."""
        rates = [point.rate for point in self.points]
        return max(rates) - min(rates)


def _point(raw: dict, rate_key: str, count_key: str) -> Point:
    """Build a point, tolerating the two shapes our writers emit."""
    interval = raw.get(f"{rate_key}_ci95") or raw.get("ci95")
    return Point(
        value=float(raw["value"]),
        played=int(raw["played"]),
        successes=int(raw.get(count_key, 0)),
        rate=float(raw[rate_key]),
        ci=(float(interval[0]), float(interval[1])) if interval else None,
    )


def load_sweeps(path: Path | str = RESULTS / "latest.json") -> dict[str, Sweep]:
    """Read the one-at-a-time sensitivity sweeps, points sorted by value."""
    raw = _read(Path(path), "scripts/sweep.py")
    sweeps = {}
    for knob, body in raw["sweeps"].items():
        points = sorted(
            (_point(entry, "capture_rate", "captures") for entry in body["points"]),
            key=lambda point: point.value,
        )
        sweeps[knob] = Sweep(knob=knob, why=body.get("why", ""), points=tuple(points))
    return sweeps


def load_baselines(path: Path | str = RESULTS / "baselines.json") -> dict[str, Point]:
    """Read head-to-head results against the reference baselines."""
    raw = _read(Path(path), "scripts/baselines.py")
    return {
        name: Point(
            value=0.0,
            played=int(body["played"]),
            successes=int(body["captures"]),
            rate=float(body["capture_rate"]),
            ci=tuple(body["capture_rate_ci95"]),  # type: ignore[arg-type]
        )
        for name, body in raw["matchups"].items()
    }


def load_tokens(path: Path | str = RESULTS / "tokens.json") -> dict:
    """Read the measured token census produced by `scripts/measure_tokens.py`."""
    return _read(Path(path), "scripts/measure_tokens.py")


def _read(path: Path, producer: str) -> dict:
    """Load JSON, naming the script that produces it when it is absent."""
    if not path.exists():
        raise MissingDataError(
            f"{path} does not exist yet — generate it with `uv run python {producer}`"
        )
    return json.loads(path.read_text(encoding="utf-8"))
