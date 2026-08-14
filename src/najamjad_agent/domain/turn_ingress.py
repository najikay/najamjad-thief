"""Absorbing the opponent's turn — the untrusted half of the loop.

Split out of the orchestrator because it has a distinct job and a distinct
threat model: everything here arrives from a competitor over the internet.

What a peer legitimately sends us is deliberately thin. Their position and move
stay sealed inside their commitment until the end-of-game audit, so we learn
where they are only from evidence the rules make public:

* the **scent field** they emit involuntarily and cannot fake (book PAGE 22);
* a **free-language hint** that may be a lie;
* any **barrier** the cop placed, which must be declared truthfully (rule 15);
* a **capture claim**, which the thief must answer honestly (rules 21-22).

Because positions are not transmitted, per-turn physics policing is impossible
by design — an illegal move is caught at the audit, where the full sealed
record is finally revealed and re-hashed. That is the book's own trade-off:
hidden information now, verifiable honesty later.
"""

from collections.abc import Callable
from typing import Any

from .declarations import absorb_barrier, absorb_capture_claim, step_of
from .game_state import GameState
from .hint_evidence import claim_likelihood, parse_locally, scent_consistency
from .ledger import ProtocolOrderError


def absorb_turn(
    state: GameState,
    message: dict[str, Any],
    event: Callable[..., None],
) -> str | None:
    """Fold one opponent message into `state`; return a violation reason or None."""
    step = step_of(message, state.step)
    commit = message.get("commit")
    answering = message.get("claim_response") is not None
    if commit and not answering:
        try:
            state.ledger.record_opponent_commit(step, str(commit))
        except ProtocolOrderError as error:
            # A peer re-committing a step it already committed is either buggy
            # or trying to overwrite history. Either way it is their protocol
            # error, reported rather than allowed to crash our turn loop.
            event("peer.duplicate_commit", step=step, reason=str(error))
            return f"opponent protocol error: {error}"
    elif answering:
        # The answer to our capture claim is a *reply*, not a new turn. The
        # reference sends its concession as a final message at the step it is
        # answering, so recording it as a fresh commit reads as a peer
        # overwriting history — and we branded an honest opponent a forger for
        # conceding, filing `tamper_forfeit` against a game they scored as our
        # capture. Two peers disagreeing like that voids it for both.
        event("peer.answered_claim", step=step)

    # A peer that leaks its own position is not a threat to us, but it is worth
    # noticing: either they are running a broken implementation, or baiting us.
    if _has_position(message):
        event("peer.leaked_position", step=step)

    _watch_fair_play(state, step, message, event)
    state.last_opponent_hint = str(message.get("hint", "") or "")
    _watch_silence(state, message)
    grid = message.get("smell_grid") or {}
    # Kept as sent, before absorption merges it into our field: the audit
    # compares what they *claimed* per step against the cell they reveal,
    # and a merged field no longer says which frame carried what.
    state.opponent_frames.record(step, grid, state.last_opponent_hint)
    problems = state.opponent_scent.absorb(grid)
    for problem in problems:
        event("scent.rejected", reason=problem)
    # What arrived, not merely what was wrong with it. Absorbing silently made
    # a peer sending 29 cells and a peer sending none indistinguishable in our
    # own logs, so "do they emit scent at all?" has been unanswerable against
    # two opponents — the sealed records cannot settle it either, because the
    # league's default `smell_binding: none` puts no grid in them by design.
    # Their transmitted form also decides whether decaying their frames on
    # receipt is right or double-ages their trail, so this is the measurement
    # that has to exist before that question can be answered honestly.
    # The peak is computed over numbers only. A hostile or merely broken peer
    # may send a string intensity, and `max` over mixed types raises — which
    # would turn an observability line into the one thing this whole path exists
    # to prevent: a peer crashing our turn.
    numeric = [value for value in grid.values() if isinstance(value, int | float)]
    event("scent.absorbed", step=step, cells=len(grid),
          peak=max(numeric, default=0.0), rejected=len(problems),
          # The hint as sent. A peer whose commit preimage omits the hint text
          # carries none in its revealed records, so judging "do they hint?"
          # from an audit trail measures their sealing choice, not their wire.
          hint=state.last_opponent_hint[:80])
    absorb_barrier(state, message, event)
    absorb_capture_claim(state, message, event)
    return None


def _watch_silence(state: GameState, message: dict[str, Any]) -> None:
    """Count consecutive turns on which the peer told us nothing at all.

    Counted rather than latched: a peer whose scent arrives late, or who skips a
    hint on one turn, has not gone silent, and treating a single quiet turn as a
    policy would have us mirror an opponent who is still talking.
    """
    said_something = bool(message.get("smell_grid")) or bool(
        str(message.get("hint", "") or "").strip()
    )
    state.peer_silent_turns = 0 if said_something else state.peer_silent_turns + 1


def _watch_fair_play(
    state: GameState, step: int, message: dict[str, Any], event: Callable[..., None]
) -> None:
    """Record any rule breach in their declared turn — never act on it.

    Observational by design. Deciding a match on our own accusation is the
    contradiction rules 33-35 void both teams for, and an honest peer with an
    off-by-one is far likelier than a cheat. It is checked *before* the barrier
    is absorbed, so the board still shows the position they moved from.
    """
    monitor = state.fair_play
    if monitor is None:
        return
    for finding in monitor.observe(state.board, step, message):
        event("opponent.violation", **finding.as_dict())


def _has_position(message: dict[str, Any]) -> bool:
    """True when a peer sent coordinates the protocol does not ask for."""
    payload = message.get("payload")
    if isinstance(payload, dict) and "position" in payload:
        return True
    return "position" in message


def decay_after_full_turn(state: GameState) -> None:
    """Advance the world once both agents have moved (FR-ENG-7).

    Decay and the Bayes step belong together: applying them per half-turn would
    age the trail twice as fast as the agreed physics and desynchronise our
    belief from the opponent's own model of the same field.
    """
    state.own_scent.decay_all()
    state.opponent_scent.decay_all()
    state.belief.diffuse()
    observed = {cell: state.opponent_scent.intensity_at(cell) for cell in state.board.cells()}
    state.belief.update_scent(observed)
    _fuse_sighting(state)
    _fuse_hint(state)
    state.belief.exclude((state.own_position,))
    # With no transmitted position, our estimate of them IS our belief peak.
    state.opponent_estimate = state.belief.peak()


def _fuse_sighting(state: GameState) -> None:
    """Apply this turn's declared-position evidence, after diffusion and scent.

    The ordering is the whole point and it is the same ordering scent already
    uses. `diffuse` models the move the opponent just made, which necessarily
    smears a point observation across five cells; the observation is then fused
    *on top* to say where that move landed. Fusing before the diffusion instead
    would leave the belief peaked on a neighbour of the true cell — and a thief
    keeping its distance-2 invariant from a cell one step off the cop is a thief
    standing next to the cop, which is a capture.

    Applied after `update_scent` for the same reason it is applied at all: a
    declaration is a direct statement of position, and the scent likelihood is an
    inference from a decaying field. When both are present the direct statement
    should win, and against a silent opponent it is the only one there is.
    """
    sighting = state.cop_sighting
    state.cop_sighting = None
    if sighting is None:
        return
    state.belief.observe_reach(sighting.cells, sighting.confidence)
    state.last_sighting = sighting


def _fuse_hint(state: GameState) -> None:
    """Apply what the opponent *said*, weighted by what their word is worth.

    Testimony, so it goes last — after diffusion, scent and any declared
    position. A hint is the weakest evidence on the board and must never
    displace a direct observation; `claim_likelihood` is a multiplicative
    nudge, not a relocation.

    **This was the most expensive unwired component in the project.** The parser,
    the claim, the likelihood, the lie-detector and the credibility tracker were
    all built and tested, `belief.py`'s own docstring described this as step 3 of
    the update, and nothing ever called any of it. Measured against uoh-ay26 on
    2026-08-07: they sent a hint on every one of 135 sealed records, **134 of
    134 direction claims truthful** against their own sealed move — and they
    emitted no scent at all, so `update_scent` received nothing and our cop
    played six mini-games on diffusion alone while they narrated their position
    every turn.

    **It does not trust them.** `credibility` starts neutral and moves only
    through `record`, fed by cross-examining each claim against the scent trail:
    a claim the trail refutes cuts their weight, one it confirms raises it, and
    a perpendicular claim the trail cannot speak to changes nothing. At zero
    credibility `claim_likelihood` returns all-ones — an identity update — so a
    peer we have caught lying is heard and disbelieved rather than silenced.
    Against a peer with no scent the verdict is "unknown" every turn and the
    weight simply stays where it started, which is the honest answer when we
    have no way to check them.

    The reference cell is where we thought they were *before* this move, because
    a direction claim describes the move they just made.
    """
    text = str(state.last_opponent_hint or "").strip()
    reference = state.opponent_estimate
    if not text or reference is None:
        return
    claim = parse_locally(text)
    if not claim.is_informative:
        return
    intensities = {cell: state.opponent_scent.intensity_at(cell) for cell in state.board.cells()}
    verdict = scent_consistency(claim, intensities, reference)
    if verdict != "unknown":
        state.credibility.record(verdict == "consistent")
    cells = tuple(cell for cell in state.board.cells() if state.board.is_open(cell))
    state.belief.apply_likelihood(
        claim_likelihood(cells, claim, reference, state.credibility.coefficient)
    )
