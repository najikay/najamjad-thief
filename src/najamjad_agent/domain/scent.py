"""Scent field state: what one peer knows about the opponent's trail.

Scent is the *unfakeable* channel — an agent emits by existing, so it can only
strengthen scent where it truly is (book PAGE 22). That is why the field is the
anchor of belief and the lie detector for hints.

Only the intensity map ever crosses the wire (`snapshot`), never a coordinate,
which is what keeps the opponent's position hidden while still leaking evidence.
"""

from .scent_models import Cell, ScentModel, decay_value, emission_field


class ScentField:
    """Board-wide intensities known to one peer, with max-merge semantics."""

    def __init__(
        self,
        board_size: int,
        grid_size: int = 5,
        decay: float = 0.10,
        centre_intensity: float = 0.9,
        model: ScentModel = ScentModel.BOOK,
    ) -> None:
        """Configure the field from the locked pheromone terms."""
        self._board_size = board_size
        self._grid_size = grid_size
        self._decay = decay
        self._centre = centre_intensity
        self._model = model
        self._values: dict[Cell, float] = {}

    @property
    def model(self) -> ScentModel:
        """The negotiated pheromone model in force."""
        return self._model

    @property
    def ceiling(self) -> float:
        """Upper clamp for any intensity (the agreed centre intensity)."""
        return self._centre

    def deposit(self, centre: Cell, intensity: float | None = None) -> None:
        """Lay a fresh field around `centre`; stronger values win (max-merge)."""
        strength = self._centre if intensity is None else intensity
        if not 0.0 < strength <= self._centre:
            raise ValueError(f"intensity {strength} must lie in (0, {self._centre}]")
        emitted = emission_field(centre, strength, self._grid_size, self._model, self._board_size)
        for cell, value in emitted.items():
            self._values[cell] = min(self._centre, max(self._values.get(cell, 0.0), value))

    def absorb(self, cells: dict) -> list[str]:
        """Merge a received `{"r,c": intensity}` map; return rejection reasons.

        Peers are untrusted: a malformed key or out-of-range intensity is
        reported for the caller to log as an event, and never crashes the turn.
        """
        problems: list[str] = []
        for key, raw in cells.items():
            cell = self._parse_key(str(key))
            value = self._coerce_intensity(raw)
            if cell is None:
                problems.append(f"unparsable cell key {key!r}")
            elif not self.in_bounds(cell):
                problems.append(f"cell {cell} outside board")
            elif value is None:
                problems.append(f"invalid intensity {raw!r} at {cell}")
            else:
                self._values[cell] = max(self._values.get(cell, 0.0), value)
        return problems

    def decay_all(self) -> None:
        """Apply one full-turn decay (called once both agents have moved)."""
        for cell in list(self._values):
            decayed = decay_value(self._values[cell], self._decay, self._model)
            if decayed <= 0.0:
                del self._values[cell]
            else:
                self._values[cell] = decayed

    def in_bounds(self, cell: Cell) -> bool:
        """True when the cell exists on this board."""
        return 0 <= cell[0] < self._board_size and 0 <= cell[1] < self._board_size

    def intensity_at(self, cell: Cell) -> float:
        """Known intensity at a cell (0.0 when never scented or fully decayed)."""
        return self._values.get(cell, 0.0)

    def strongest_cell(self) -> Cell | None:
        """Most fragrant known cell — the naive opponent guess, ties broken low."""
        live = {cell: value for cell, value in self._values.items() if value > 0.0}
        if not live:
            return None
        best = max(live.values())
        return min(cell for cell, value in live.items() if value == best)

    def snapshot(self) -> dict[str, float]:
        """Wire/log form: `{"r,c": intensity}` for positive intensities only.

        The single rounding boundary: internal state stays full-precision so
        decay cannot drift, while peers and logs see stable 3-decimal values.
        """
        return {
            f"{row},{col}": round(value, 3)
            for (row, col), value in self._values.items()
            if value > 0.0
        }

    def _parse_key(self, key: str) -> Cell | None:
        """Parse a `"r,c"` wire key, returning None when malformed."""
        parts = key.split(",")
        if len(parts) != 2:
            return None
        try:
            return (int(parts[0]), int(parts[1]))
        except ValueError:
            return None

    def _coerce_intensity(self, raw: object) -> float | None:
        """Coerce an inbound intensity into [0, ceiling], or None when invalid."""
        try:
            value = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if value != value or value < 0.0:  # NaN or negative
            return None
        return min(self._centre, round(value, 3))
