"""Emitting less must not make us look like we tampered.

The whole risk of this feature is in one place. The hint and the scent map are
sealed *inside* the commitment, and the commitment is what the end-of-game audit
re-hashes (rules 18-22). Withhold either one after the commit is computed and
our own sealed record stops matching the turn we sent — which an auditor cannot
distinguish from forging, and which scores `tamper_forfeit` for a game we were
otherwise winning.

So these tests do not check that the field is smaller. They check that the
sealed payload and the wire message are the *same object's* two halves, in every
mode. That is the property that makes the feature safe to use in a counted match.
"""

import pytest

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.emission import EmissionPolicy, ScentEmission
from tests.fakes.orchestration import build_orchestrator

MODES = [ScentEmission.FULL, ScentEmission.WINDOW, ScentEmission.NONE]


def _opponent_turn(step: int) -> dict:
    """A minimal well-formed peer turn, so the loop can alternate legally."""
    return {"step": step, "sender": "police", "commit": f"{step:064x}"}


def play(mode: ScentEmission, hints: bool = True, steps: int = 3):
    """Play a few real turns as the thief; hand back what was sealed and sent.

    Turns alternate through `receive_turn` rather than calling `take_turn` in a
    row, because the FSM refuses two of ours back to back — correctly, since
    that is not a game either peer would recognise. Moving the thief each turn
    also grows the cumulative field, which is what `window` has to shrink.
    """
    orchestrator, transport, _ = build_orchestrator(
        Role.THIEF,
        moves=[Move.SOUTH, Move.EAST, Move.EAST, Move.NORTH][:steps],
        inbox=[_opponent_turn(step) for step in range(1, steps + 1)],
        emission=EmissionPolicy(mode, hints=hints),
    )
    for step in range(steps):
        orchestrator.take_turn()
        if step < steps - 1:
            orchestrator.receive_turn()
    sealed = [
        orchestrator.state.ledger._ours[step].record.payload  # noqa: SLF001
        for step in range(1, steps + 1)
    ]
    return sealed, transport.sent


@pytest.mark.parametrize("mode", MODES)
def test_the_wire_message_matches_what_we_sealed(mode: ScentEmission) -> None:
    """The property that keeps the audit clean in every mode."""
    sealed, sent = play(mode)

    for payload, message in zip(sealed, sent, strict=True):
        assert message["smell_grid"] == payload["smell_grid"]
        assert message["hint"] == payload["hint"]


@pytest.mark.parametrize("mode", MODES)
def test_silencing_hints_seals_the_silence_too(mode: ScentEmission) -> None:
    """An empty hint must be empty in the commitment, not only on the wire."""
    sealed, sent = play(mode, hints=False)

    assert all(payload["hint"] == "" for payload in sealed)
    assert all(message["hint"] == "" for message in sent)


def test_full_mode_is_unchanged_from_what_we_have_always_sent() -> None:
    """The default must not quietly start playing a different game."""
    _, sent = play(ScentEmission.FULL)

    assert all(message["smell_grid"] for message in sent)


def test_none_mode_transmits_an_empty_map_every_turn() -> None:
    _, sent = play(ScentEmission.NONE)

    assert all(message["smell_grid"] == {} for message in sent)
    assert all("smell_grid" in message for message in sent), "the key must still exist"


def test_window_mode_sends_less_than_full_but_not_nothing() -> None:
    """The middle setting has to actually be in the middle."""
    _, full = play(ScentEmission.FULL)
    _, window = play(ScentEmission.WINDOW)

    assert 0 < len(window[-1]["smell_grid"]) <= len(full[-1]["smell_grid"])


def test_our_own_belief_is_unaffected_by_what_we_choose_to_emit() -> None:
    """Emission is about their information, never ours.

    A dial that quietly blinded our own thief while hiding it from the opponent
    would be worse than not having the dial.
    """
    quiet, _, _ = build_orchestrator(
        Role.THIEF, moves=[Move.SOUTH], emission=EmissionPolicy(ScentEmission.NONE)
    )
    loud, _, _ = build_orchestrator(Role.THIEF, moves=[Move.SOUTH])

    quiet.take_turn()
    loud.take_turn()

    assert quiet.state.own_scent.snapshot() == loud.state.own_scent.snapshot()
