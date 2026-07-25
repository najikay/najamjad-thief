"""Immutable value object holding the negotiated, signed game terms.

Why: the domain must never read raw config dicts (guidelines §7.2) nor trust a
peer's numbers blindly. `GameParams.from_config` is the single validation gate
where Appendix F status semantics are enforced: *minimum* values may only be
raised, *fixed* values may not change at all. A contract that tries to weaken
the book is rejected here, before any game logic runs (book rule 12).
"""

from dataclasses import dataclass, field

from ..constants import Move

Position = tuple[int, int]

# Appendix F binding floors (Tables 13, 15) — raising is legal, lowering never is.
MIN_GRID_SIZE = 7
MIN_MAX_BARRIERS = 14
MIN_MAX_MOVES = 35
MIN_SURVIVAL_THRESHOLD = 35
FIXED_MOVE_SET = tuple(move.value for move in Move)
VALID_CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")


@dataclass(frozen=True)
class GameParams:
    """Agreed per-match parameters, already validated against Appendix F."""

    grid_size: int
    thief_start: Position
    cop_start: Position
    max_barriers: int
    max_moves: int
    survival_threshold: int
    axis_origin_corner: str = "top-left"
    axis_start_index: int = 0
    move_set: tuple[str, ...] = field(default=FIXED_MOVE_SET)

    @classmethod
    def from_config(cls, config: dict) -> "GameParams":
        """Build params from a shared `game.json` mapping, validating every term."""
        board = config["board_and_agents"]
        rules = config["movement_and_barriers"]
        params = cls(
            grid_size=int(board["grid_size"]),
            thief_start=tuple(board["thief_start"]),  # type: ignore[arg-type]
            cop_start=tuple(board["cop_start"]),  # type: ignore[arg-type]
            max_barriers=int(rules["max_barriers"]),
            max_moves=int(rules["max_moves"]),
            survival_threshold=int(rules["survival_threshold"]),
            axis_origin_corner=board.get("axis_origin_corner", "top-left"),
            axis_start_index=int(board.get("axis_start_index", 0)),
            move_set=tuple(rules.get("move_set", FIXED_MOVE_SET)),
        )
        params.validate()
        return params

    def validate(self) -> None:
        """Raise ValueError on any term that violates the binding parameter table."""
        self._check_minimum("grid_size", self.grid_size, MIN_GRID_SIZE)
        self._check_minimum("max_barriers", self.max_barriers, MIN_MAX_BARRIERS)
        self._check_minimum("max_moves", self.max_moves, MIN_MAX_MOVES)
        self._check_minimum("survival_threshold", self.survival_threshold, MIN_SURVIVAL_THRESHOLD)
        if set(self.move_set) != set(FIXED_MOVE_SET):
            raise ValueError(f"move_set is fixed by Appendix F; got {self.move_set!r}")
        if self.axis_origin_corner not in VALID_CORNERS:
            raise ValueError(f"axis_origin_corner must be one of {VALID_CORNERS}")
        for name, cell in (("thief_start", self.thief_start), ("cop_start", self.cop_start)):
            if not self.contains(cell):
                raise ValueError(f"{name} {cell} lies outside the agreed board")
        if self.thief_start == self.cop_start:
            raise ValueError("thief_start and cop_start must be distinct cells")

    @staticmethod
    def _check_minimum(name: str, value: int, floor: int) -> None:
        if value < floor:
            raise ValueError(f"{name}={value} is below the Appendix F minimum of {floor}")

    @property
    def last_index(self) -> int:
        """Highest valid row/column index given the agreed start index."""
        return self.axis_start_index + self.grid_size - 1

    def contains(self, cell: Position) -> bool:
        """True when `cell` lies inside the agreed coordinate space."""
        return all(self.axis_start_index <= value <= self.last_index for value in cell)
