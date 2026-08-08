"""How much of our own evidence we put on the wire, as one named setting.

We broadcast the whole cumulative pheromone field every turn. uoh-sqak broadcast
nothing — no scent, no hints, no observations of any kind — and still played a
legal series that beat us 15-60. The asymmetry is worth naming: they knew where
we were and we did not know where they were, for six games.

**What the terms actually say, checked before this was built:**

1. `pheromone_grid_size: 5` sizes the *emission field* — one deposit is 5x5
   around the emitter. It does not say the wire message carries only that. We
   send `ScentField.snapshot()`, which is the accumulated board-wide map: 25
   cells on step 1 of the sealed uoh-sqak log, 29 by step 3, and rising with
   every cell the thief visits. `WINDOW` transmits the agreed 5x5 and nothing
   else, which is a defensible reading of the same term rather than a new one.
2. **Scent is physics, not speech.** The book is explicit that an agent
   "cannot plant a fake trail, it can only strengthen scent where it actually
   is" (PAGE 22). That forbids *falsifying* the field; it does not obviously
   compel transmitting it, and our opponent transmits none. `NONE` is therefore
   available but is the one mode that should be *declared* rather than simply
   used — see `docs/PRD_strategy_thief.md`. Default stays `FULL`.
3. The handshake locks a `model_fingerprint` over the emission *maths* — model,
   centre intensity, decay, grid size (`scent_models.model_fingerprint`). None
   of those change here, so no mode on this dial can fail the exchange.
4. The hint is sealed inside the commit payload, so it must be suppressed
   *before* sealing, never stripped from the wire afterwards. Both halves then
   carry the same empty string and the audit re-hashes clean. Rule 12 caps hint
   length at 15 words; it sets no floor, so an empty hint breaks no term.

**What `WINDOW` does not buy.** The centre of a 5x5 deposit is the agreed
`pheromone_center_intensity` of 0.9 and is the unique maximum, so an opponent
taking the argmax of the window still reads our exact cell. `WINDOW` reduces how
much of our *history* we hand over; only `NONE` hides the current position, and
only against an opponent who has no other fix on us.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .params import Position

#: Chebyshev radius implied by the agreed `pheromone_grid_size`.
DEFAULT_GRID_SIZE = 5


class ScentEmission(str, Enum):
    """How much of the pheromone field crosses the wire."""

    #: The whole accumulated field. What we have always sent, and the default.
    FULL = "full"
    #: Only the agreed `pheromone_grid_size` window around our current cell.
    WINDOW = "window"
    #: Nothing. Legal to send an empty map; declare it rather than spring it.
    NONE = "none"


class EmissionError(ValueError):
    """Raised when a configured emission mode is not one we implement."""


@dataclass(frozen=True)
class EmissionPolicy:
    """What we disclose voluntarily each turn.

    Input:  a `ScentEmission` and whether hints are spoken at all.
    Output: `scent()` and `hint()`, applied at the point the turn is composed —
            which is *before* sealing, so the commitment and the wire always
            agree and the audit cannot see a difference.
    Setup:  `from_config(...)`, or the default, which is what we have always
            done. Defaults must never silently change how a match plays.
    """

    scent_mode: ScentEmission = ScentEmission.FULL
    hints: bool = True
    grid_size: int = DEFAULT_GRID_SIZE
    #: Mirror a peer who tells us nothing. Off by default, because going quiet
    #: is a choice worth making deliberately rather than one that happens to us.
    reciprocal: bool = False

    def mirroring(self, peer_silent: bool) -> EmissionPolicy:
        """This policy, or its silent form when the peer emits nothing.

        Input: whether the opponent has gone a full grace period without
        sending scent or a hint.
        Output: the policy to use this turn.
        Setup: `emission.reciprocal = true`.

        Symmetry is the whole justification, so it has to be *actual* symmetry:
        we go as quiet as they are and no quieter, and we do it only after
        watching them do it first. Anything else is a unilateral choice wearing
        a reciprocal label, and rule 49 means this file gets read.

        Returns `self` unchanged when reciprocity is off or the peer is talking,
        so the common path allocates nothing.
        """
        if not self.reciprocal or not peer_silent:
            return self
        return EmissionPolicy(ScentEmission.NONE, False, self.grid_size, True)

    @classmethod
    def from_config(cls, section: dict | None, grid_size: int = DEFAULT_GRID_SIZE) -> EmissionPolicy:
        """Read `[emission]`, refusing a mode we do not implement.

        An unknown mode must not quietly mean `full`: a typo would be invisible
        in exactly the direction that matters, which is the same reasoning
        `shared/strength.py` gives for refusing an unknown level.
        """
        values = dict(section or {})
        raw = str(values.get("scent", ScentEmission.FULL.value)).strip().lower()
        try:
            mode = ScentEmission(raw)
        except ValueError as error:
            allowed = [each.value for each in ScentEmission]
            raise EmissionError(f"emission.scent {raw!r} is not one of {allowed}") from error
        return cls(
            mode,
            bool(values.get("hint", True)),
            int(grid_size),
            bool(values.get("reciprocal", False)),
        )

    def scent(self, snapshot: dict[str, float], centre: Position) -> dict[str, float]:
        """The pheromone map to put on the wire, given the full field.

        Filters the *real* decayed field rather than recomputing a fresh
        deposit: what we transmit stays a true statement about the board, which
        is the property that makes `WINDOW` a reading of the agreed term rather
        than a different physics.
        """
        if self.scent_mode is ScentEmission.NONE:
            # An empty map, not a missing key. The reference parser rejects a
            # message whose declared fields it cannot find, and a turn it cannot
            # read is a turn we forfeit — a far worse outcome than emitting.
            return {}
        if self.scent_mode is ScentEmission.FULL:
            return snapshot
        reach = self.grid_size // 2
        return {
            key: value
            for key, value in snapshot.items()
            if _within(key, centre, reach)
        }

    def hint(self, text: str) -> str:
        """The hint to seal and send — empty when hints are switched off."""
        return text if self.hints else ""

    def as_declaration(self) -> dict[str, str]:
        """What we tell an opponent we are doing, for the negotiation record.

        Emitting less than the maximum is a tactical choice and not a secret
        one. These repositories are read by the lecturer under rule 49, and a
        documented setting reads as the choice it is where the same behaviour
        undeclared reads as something we were hiding.
        """
        return {"scent": self.scent_mode.value, "hint": "spoken" if self.hints else "silent"}


def _within(key: str, centre: Position, reach: int) -> bool:
    """Whether a `"r,c"` wire key falls inside the window around `centre`."""
    row, _, col = key.partition(",")
    try:
        offset = (abs(int(row) - centre[0]), abs(int(col) - centre[1]))
    except ValueError:
        return False
    return max(offset) <= reach


def emission_overlay(
    quiet: bool = False, scent: str = "", hints: bool | None = None
) -> dict[str, Any]:
    """The `[emission]` overlay a run's flags imply; empty when none are set.

    Two independent dials were reachable only through one switch. `--quiet` set
    scent *and* hints off together, and `--talk` set both on, so the middle
    ground could be described in `config/<role>/game.toml` and not asked for on
    a command line — the two-switch setup that has cost this project games.

    The middle ground is the case that actually occurs. uoh-ay26 sent a hint on
    every one of 135 sealed records and **not one scent cell**, across all six
    mini-games; uoh-sqak sent neither. Mirroring the first needs
    `--scent none --hints`, which no combination of `--quiet`/`--talk` could
    express.

    `--quiet` stays as a preset rather than a third mode, and the explicit
    flags win over it: `--quiet --hints` is "match a peer who speaks but does
    not emit", not a contradiction worth rejecting.

    Returns `{}` when nothing is passed, so a bare command is unchanged and the
    shipped config keeps deciding. The mode string is *not* validated here —
    `from_config` already refuses an unknown one by name, and duplicating that
    list is how the two get to disagree.
    """
    section: dict[str, Any] = (
        {"scent": ScentEmission.NONE.value, "hint": False} if quiet else {}
    )
    if scent:
        section["scent"] = scent.strip().lower()
    if hints is not None:
        section["hint"] = bool(hints)
    return {"emission": section} if section else {}
