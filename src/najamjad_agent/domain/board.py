"""The playing grid: bounds, neighbours, distance, and barrier state.

Why immutable: a board value is shared with the strategy search (expectimax
explores hypothetical futures) and with the audit trail. Copy-on-write via
`with_barrier` makes accidental mutation of a past game state impossible, so a
replayed log can never diverge from what was committed.

Axis conventions (origin corner, start index) are negotiated per match
(Appendix F Table 13), so compass directions are resolved here rather than
baked into move constants.
"""

from collections.abc import Iterable, Iterator

from ..constants import MOVE_DELTAS, Move
from .params import GameParams, Position


class Board:
    """A grid plus its permanent barrier set, under agreed axis conventions."""

    def __init__(self, params: GameParams, barriers: Iterable[Position] | None = None) -> None:
        """Create a board; `barriers` seeds already-placed impassable cells."""
        self._params = params
        self._barriers: frozenset[Position] = frozenset(barriers or ())
        # Compass deltas in `constants` assume a top-left origin (north = row-1);
        # a bottom-* origin flips the row axis, a *-right origin the column axis.
        self._row_sign = 1 if params.axis_origin_corner.startswith("top") else -1
        self._col_sign = -1 if params.axis_origin_corner.endswith("right") else 1

    @property
    def params(self) -> GameParams:
        """The agreed parameters this board was built from."""
        return self._params

    @property
    def size(self) -> int:
        """Side length of the square grid."""
        return self._params.grid_size

    @property
    def barriers(self) -> frozenset[Position]:
        """Every cell made impassable so far (permanent for the mini-game)."""
        return self._barriers

    @property
    def barrier_count(self) -> int:
        """How much of the cop's barrier budget has been spent."""
        return len(self._barriers)

    def cells(self) -> Iterator[Position]:
        """Yield every cell of the board in row-major order."""
        start = self._params.axis_start_index
        for row in range(start, self._params.last_index + 1):
            for col in range(start, self._params.last_index + 1):
                yield (row, col)

    def in_bounds(self, cell: Position) -> bool:
        """True when the cell exists in the agreed coordinate space."""
        return self._params.contains(cell)

    def is_blocked(self, cell: Position) -> bool:
        """True when a barrier occupies the cell (impassable for both sides)."""
        return cell in self._barriers

    def is_open(self, cell: Position) -> bool:
        """True when the cell is on the board and free of barriers."""
        return self.in_bounds(cell) and not self.is_blocked(cell)

    def delta_for(self, move: Move) -> Position:
        """Row/col delta of a compass move under the negotiated axis origin."""
        row_delta, col_delta = MOVE_DELTAS[move]
        return (row_delta * self._row_sign, col_delta * self._col_sign)

    def neighbours(self, cell: Position) -> tuple[Position, ...]:
        """Open orthogonally adjacent cells (barriers and edges excluded)."""
        candidates = ((cell[0] + dr, cell[1] + dc) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)))
        return tuple(candidate for candidate in candidates if self.is_open(candidate))

    def with_barrier(self, cell: Position) -> "Board":
        """Return a new board with `cell` permanently blocked."""
        return Board(self._params, self._barriers | {cell})

    @staticmethod
    def manhattan(first: Position, second: Position) -> int:
        """Grid distance used by both pursuit and evasion policies."""
        return abs(first[0] - second[0]) + abs(first[1] - second[1])
