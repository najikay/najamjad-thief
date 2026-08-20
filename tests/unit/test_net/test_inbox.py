"""Tests for the inboxes: validation at intake, sequence guard, drain."""

import pytest

from najamjad_agent.net.inbox import Inboxes

TURN = {"step": 1, "sender": "rival", "commit": "a" * 64, "hint": "by the park"}


@pytest.fixture()
def events() -> list[dict]:
    return []


@pytest.fixture()
def inboxes(events: list[dict]) -> Inboxes:
    return Inboxes(emit=events.append)


def test_valid_turn_is_accepted_and_queued(inboxes: Inboxes, events: list[dict]) -> None:
    assert inboxes.accept("turn", TURN).ok
    assert inboxes.pending("turn") == 1
    assert events[-1]["event"] == "inbox.accepted"


def test_polled_message_is_the_parsed_model(inboxes: Inboxes) -> None:
    inboxes.accept("turn", TURN)
    message = inboxes.poll("turn", timeout=0.1)
    assert message.commit == "a" * 64
    assert message.hint == "by the park"


def test_poll_returns_none_when_empty(inboxes: Inboxes) -> None:
    assert inboxes.poll("turn", timeout=0.01) is None


def test_malformed_message_is_rejected_with_errors(inboxes: Inboxes, events: list[dict]) -> None:
    """The peer gets a structured answer; our queue stays clean."""
    result = inboxes.accept("turn", {"step": 1})
    assert not result.ok
    assert result.errors
    assert inboxes.pending("turn") == 0
    assert events[-1]["event"] == "inbox.rejected"


def test_unknown_message_kind_is_refused(inboxes: Inboxes) -> None:
    assert not inboxes.accept("teleport", TURN).ok


def test_unknown_fields_are_accepted_but_announced(inboxes: Inboxes, events: list[dict]) -> None:
    """Tolerated by design — but never silently (ADR-006)."""
    assert inboxes.accept("turn", {**TURN, "their_extension": 1}).ok
    kinds = [event["event"] for event in events]
    assert "inbox.unknown_fields" in kinds


def test_a_redelivery_is_absorbed_not_rejected(inboxes: Inboxes, events: list[dict]) -> None:
    """Re-pinned to the kit's §7.1 contract, and the reversal is deliberate.

    This asserted `not result.ok` — a replayed turn is refused. That is the
    behaviour the interop kit names as the failure: both registered wire shapes
    ride HTTP, which is at-least-once, so a correct client retries a push whose
    ack was lost and the same turn arrives twice **by design**. Refusing it
    turns an ordinary retry race into a protocol violation, which App. E rule 35
    zeroes for both teams. "Zero tolerance is not a tightening here."

    Absorbed means all three of: the sender is told it landed, so it stops
    retrying; nothing is queued, so the game state does not see it twice; and no
    error is logged, because nothing went wrong.
    """
    assert inboxes.accept("turn", TURN).ok
    queued = inboxes.pending("turn")

    result = inboxes.accept("turn", TURN)

    assert result.ok, "a redelivery is the network working, not a fault"
    assert inboxes.pending("turn") == queued, "absorbed, so state is unchanged"
    assert events[-1]["event"] == "inbox.absorbed"


def test_the_same_step_sealed_differently_is_still_refused(
    inboxes: Inboxes, events: list[dict]
) -> None:
    """The half that must NOT relax: equivocation is tampering evidence.

    Transport tolerance, no rules tolerance. Dedupe is on the commit precisely
    so that this case stays separable from a redelivery — a step-only guard
    calls both "stale" and cannot tell an opponent's retry from a forged step.
    """
    inboxes.accept("turn", TURN)

    result = inboxes.accept("turn", {**TURN, "commit": "b" * 64})

    assert not result.ok
    assert "equivocation" in result.errors[0]
    assert "inbox.equivocation" in [event["event"] for event in events]


def test_out_of_order_step_is_rejected(inboxes: Inboxes) -> None:
    inboxes.accept("turn", {**TURN, "step": 5})
    assert not inboxes.accept("turn", {**TURN, "step": 3}).ok


def test_increasing_steps_are_accepted(inboxes: Inboxes) -> None:
    for step in (1, 2, 3, 7):
        assert inboxes.accept("turn", {**TURN, "step": step}).ok
    assert inboxes.pending("turn") == 4


def test_sequence_guard_only_applies_to_turns(inboxes: Inboxes) -> None:
    control = {"kind": "status"}
    assert inboxes.accept("control", control).ok
    assert inboxes.accept("control", control).ok


def test_queues_are_independent(inboxes: Inboxes) -> None:
    """A flood of control messages must not delay a turn."""
    for _ in range(5):
        inboxes.accept("control", {"kind": "status"})
    inboxes.accept("turn", TURN)
    assert inboxes.pending("control") == 5
    assert inboxes.pending("turn") == 1


def test_full_queue_reports_backpressure(events: list[dict]) -> None:
    small = Inboxes(emit=events.append, maxsize=2)
    for step in (1, 2):
        small.accept("turn", {**TURN, "step": step})
    result = small.accept("turn", {**TURN, "step": 3})
    assert not result.ok
    assert events[-1]["event"] == "inbox.full"


def test_drain_clears_queues_between_mini_games(inboxes: Inboxes, events: list[dict]) -> None:
    """Leftovers from a finished game must not open the next one."""
    inboxes.accept("turn", TURN)
    inboxes.accept("control", {"kind": "status"})
    dropped = inboxes.drain()
    assert dropped == {"turn": 1, "control": 1}
    assert inboxes.pending("turn") == 0
    assert events[-1]["event"] == "inbox.drained"


def test_drain_resets_the_sequence_guard(inboxes: Inboxes) -> None:
    """Each mini-game restarts numbering from step 1."""
    inboxes.accept("turn", {**TURN, "step": 30})
    inboxes.drain()
    assert inboxes.accept("turn", {**TURN, "step": 1}).ok


def test_drain_on_empty_queues_is_quiet(inboxes: Inboxes, events: list[dict]) -> None:
    assert inboxes.drain() == {}
    assert not any(event["event"] == "inbox.drained" for event in events)


def test_audit_and_negotiate_messages_validate(inboxes: Inboxes) -> None:
    negotiate = {"identity": "rival", "terms": {}, "nonce": "n", "signature": "s"}
    audit = {"records": [{"payload": {"step": 1}, "nonce": "n", "commit": "c"}]}
    assert inboxes.accept("negotiate", negotiate).ok
    assert inboxes.accept("audit", audit).ok


def test_a_turn_without_a_step_skips_the_sequence_guard(inboxes: Inboxes) -> None:
    """Guard on what exists: a message with no step cannot be out of order."""
    assert inboxes._sequence_problem(object()) is None


NEGOTIATE = {"identity": "rival", "terms": {}, "nonce": "n", "signature": "s"}


def test_a_handshake_mid_mini_game_is_refused_not_queued(
    inboxes: Inboxes, events: list[dict]
) -> None:
    """The ahk-yosi failure, reproduced.

    Their hosted peer retried our endpoint on a loop while we dialled theirs.
    We accepted 58 inbound handshakes during one six-game series, so two games
    ran over a single inbox and every mini-game scored 0-0 technical. The
    handshake had to be refused *before* it reached a queue.
    """
    inboxes.begin_sub_game()

    result = inboxes.accept("negotiate", NEGOTIATE)

    assert not result.ok
    assert inboxes.pending("negotiate") == 0
    assert any(event["event"] == "handshake.refused" for event in events)


def test_the_refusal_tells_the_peer_to_try_again(inboxes: Inboxes) -> None:
    """Retriable, never fatal.

    Opponents re-handshake before every mini-game, and one whose clock runs
    ahead of ours proposes the next game while we finish this one. Answering
    anything that reads as "you are broken" would turn a timing skew into a
    forfeit; their retry is what resynchronises us.
    """
    inboxes.begin_sub_game()

    errors = " ".join(inboxes.accept("negotiate", NEGOTIATE).errors)

    assert "re-send" in errors and "boundary" in errors


def test_a_handshake_between_mini_games_still_lands(inboxes: Inboxes) -> None:
    """The gate must not break the normal per-sub-game re-handshake."""
    inboxes.begin_sub_game()
    inboxes.gate.end_sub_game()

    assert inboxes.accept("negotiate", NEGOTIATE).ok
    assert inboxes.pending("negotiate") == 1


def test_turns_are_unaffected_by_the_gate(inboxes: Inboxes) -> None:
    """Only handshakes are gated — a live game's own turns must flow."""
    inboxes.begin_sub_game()

    assert inboxes.accept("turn", TURN).ok
