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
    def decay(self) -> float:
        """The agreed decay per step, so a reader can age a frame as we do."""
        return self._decay

    @property
    def grid_size(self) -> int:
        """The agreed field width, for rebuilding a kernel at a candidate cell."""
        return self._grid_size

    @property
    def ceiling(self) -> float:
        """Upper clamp for any intensity (the agreed centre intensity)."""
        return self._centre

    def deposit(self, centre: Cell, intensity: float | None = None) -> None:
        """Lay a fresh field around `centre`, merged by the model's own rule.

        **The two registered models accumulate differently, and we ran the wrong
        one for both.** This was a max-merge unconditionally — `max(tau, delta)`
        — which is right for `subtractive_chebyshev_v1` and wrong for
        `multiplicative_book_v1`, whose registered document pins

            tau' = clamp((1 - rho) * tau + kernel_delta, 0, center_intensity)

        an **addition**, not a maximum. `(1 - rho) * tau` is the decay, which
        `decay_all` already applies at the turn boundary, so what belongs here is
        the `+ delta` and the clamp.

        The two agree exactly on an empty field and diverge from the second
        deposit onward, which is why it survived every self-test we had: our own
        two repos share this code, so cop and thief agreed with each other while
        both were wrong. anrbj666's per-frame gate caught it live on 2026-08-21 —
        34 of 35 frames refused in one window, 33 of 35 in the next, the single
        passing frame in each being turn 1. Verified against the kit's own
        `scent_book_v3.json` `field_walk`, three turns of a moving agent on an
        empty board: turn 1 matched, turn 2 differed on 19 cells, turn 3 on 27.

        Max-merge stays for the subtractive model. The kit publishes no
        accumulation vector for it, ahk-yosi independently reported theirs is a
        max-merge identical to ours, and a stationary agent must still plateau at
        `emit_intensity` rather than climb — which the clamp guarantees either
        way.
        """
        strength = self._centre if intensity is None else intensity
        if not 0.0 < strength <= self._centre:
            raise ValueError(f"intensity {strength} must lie in (0, {self._centre}]")
        emitted = emission_field(centre, strength, self._grid_size, self._model, self._board_size)
        additive = self._model is ScentModel.BOOK
        for cell, value in emitted.items():
            held = self._values.get(cell, 0.0)
            merged = held + value if additive else max(held, value)
            self._values[cell] = min(self._centre, merged)

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

    def age_and_deposit(self, centre: "tuple[int, int]") -> None:
        """One full turn of our own trail, in the kit's serve order.

        Decay the prior field, then merge the fresh deposit undecayed — the
        convention `field_walk` publishes and the single call the orchestrator
        makes per turn, so the snapshot taken right after this IS the frame
        the wire carries. Two separate calls at the call site is how the
        thief's trail crossed the wire one decay step too fresh for a week.
        """
        self.decay_all()
        self.deposit(centre)

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

        **Full precision, deliberately.** This rounded to three decimals, for
        "stable values" in peers and logs. Stability is not worth the
        conformance: the kit publishes its field walk at full IEEE-754
        (`0.032400000000000005`), and a peer gating frames at the 1e-6 the kit
        itself recommends refuses a three-decimal grid on sight — the error runs
        to 5e-4, five hundred times the tolerance. anrbj666 refused 34 of 35
        frames on 2026-08-21 and the accumulation rule was only half of why.

        Comparing floats across implementations is the peer's job and the kit
        says so: two correct builds can differ in the last bit, so grids are
        diffed with a tolerance, never byte-compared. Sending fewer digits than
        we have does not help that and actively breaks it.
        """
        return {
            f"{row},{col}": value
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
        # Not rounded either: their field is theirs to compute, and truncating
        # it here would make our belief disagree with what they actually sent.
        return min(self._centre, value)
