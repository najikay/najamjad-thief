"""Project-wide immutable enumerations and physical constants.

Why: the course guidelines forbid hardcoded values inside logic modules
(guidelines §7.2); every symbolic value shared across subsystems is defined
once here. Enum string values match the reference simulator's wire vocabulary
so that our messages interoperate with other league teams (PLAN ADR-001).
"""

from enum import Enum


class Move(str, Enum):
    """Legal move set — four orthogonal steps or staying put (Appendix F Table 15, fixed)."""

    NORTH = "N"
    SOUTH = "S"
    EAST = "E"
    WEST = "W"
    STAY = "STAY"


class Role(str, Enum):
    """The two symmetric agent roles (book Ch. 1)."""

    COP = "police"
    THIEF = "thief"


class Intent(str, Enum):
    """Declared truthfulness of a verbal hint, sealed inside the commit (book Ch. 5)."""

    TRUTH = "truth"
    LIE = "lie"


class Phase(str, Enum):
    """Game state-machine phases (book rules 4-5; PLAN §2.1)."""

    NEGOTIATING = "negotiating"
    WAITING_FOR_OPPONENT = "waiting_for_opponent"
    COMPUTING_MOVE = "computing_move"
    COMMITTING = "committing"
    AWAITING_REVEAL = "awaiting_reveal"
    VERIFYING = "verifying"
    GAME_END = "game_end"
    AUDITING = "auditing"
    REPORTING = "reporting"
    TECHNICAL_LOSS = "technical_loss"


class EndReason(str, Enum):
    """Why a mini-game ended (book Table 2 vocabulary, reference-compatible)."""

    CAPTURE = "capture"
    SURVIVAL = "survival"
    TIMEOUT = "timeout"
    TAMPER_FORFEIT = "tamper_forfeit"
    OPPONENT_QUIT = "opponent_quit"
    STOPPED = "stopped"


# Row/column deltas per move; (0,0) origin at the configured corner, rows grow
# toward the opposite side (axis conventions themselves come from the signed
# shared config, not from code — book Table 13).
MOVE_DELTAS: dict[Move, tuple[int, int]] = {
    Move.NORTH: (-1, 0),
    Move.SOUTH: (1, 0),
    Move.EAST: (0, 1),
    Move.WEST: (0, -1),
    Move.STAY: (0, 0),
}
