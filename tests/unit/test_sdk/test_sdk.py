"""The facade: every consumer's only door into the agent.

The behaviour worth pinning here is what happens *before* a game exists. A6's
dashboard threw on an empty state and showed a stack trace on the projector, so
each query answers `available: False` rather than raising.
"""

from najamjad_agent.constants import Phase, Role
from najamjad_agent.domain.fsm import GameStateMachine
from najamjad_agent.reporting.gmail_sender import SendResult
from najamjad_agent.reporting.reconcile import Reconciliation
from najamjad_agent.sdk.sdk import AgentSdk
from tests.fakes.orchestration import build_state


def build_sdk(**kwargs) -> AgentSdk:
    """An SDK with a live game attached."""
    sdk = AgentSdk(**kwargs)
    fsm = GameStateMachine(game_uid="ui-test")
    fsm.to(Phase.WAITING_FOR_OPPONENT)
    sdk.attach_game(build_state(Role.COP), fsm)
    return sdk


def test_an_sdk_without_a_game_answers_instead_of_raising():
    sdk = AgentSdk()

    assert sdk.ready is False
    assert sdk.board() == {"available": False}
    assert sdk.turn() == {"available": False}
    assert sdk.snapshot()["transcript"] == []


def test_attaching_a_game_makes_every_panel_available():
    sdk = build_sdk()

    assert sdk.ready is True
    assert sdk.board()["available"] is True
    assert sdk.turn()["phase"] == Phase.WAITING_FOR_OPPONENT.value


def test_attaching_a_new_game_clears_the_previous_transcript():
    sdk = build_sdk()
    sdk.record_message("out", "north-ish", model="claude-fable-5")
    fsm = GameStateMachine(game_uid="second")

    sdk.attach_game(build_state(Role.THIEF), fsm)

    assert sdk.transcript() == []


def test_recorded_messages_keep_their_provenance():
    sdk = build_sdk()
    sdk.record_message("out", "heading east", provider="anthropic", intent="lie", step=3)

    (message,) = sdk.transcript()

    assert (message["provider"], message["intent"], message["step"]) == ("anthropic", "lie", 3)


def test_snapshot_carries_every_panel():
    sdk = build_sdk()

    assert set(sdk.snapshot()) == {
        "board", "turn", "transcript", "negotiation", "budget", "provider",
        "gatekeepers", "report",
    }


def test_the_report_panel_starts_undecided_rather_than_claiming_agreement():
    """A6 filed `agreement: NULL`; an unstarted match must not read as 'no'."""
    sdk = build_sdk()

    report = sdk.report()

    assert report["agreement"] is None
    assert report["status"] == "pending"
    assert report["needs_attention"] is False


def test_a_reconciled_but_unsent_report_demands_attention():
    """The exact A6 failure: reconciled, never emailed, and nobody noticed."""
    sdk = build_sdk()
    sdk.record_report(reconciliation=Reconciliation(status="agreed"), send=None)

    report = sdk.report()

    assert report["agreement"] is True
    assert report["sent"] is False
    assert report["needs_attention"] is True


def test_a_delivered_report_quotes_its_message_id():
    sdk = build_sdk()
    sdk.record_report(
        reconciliation=Reconciliation(status="agreed"),
        send=SendResult(message_id="18f2ab", mode="gmail", recipient="peer@example.com"),
    )

    report = sdk.report()

    assert (report["sent"], report["message_id"]) == (True, "18f2ab")
    assert report["needs_attention"] is False


def test_negotiation_timeline_comes_straight_from_the_flow():
    steps = [{"stage": "propose", "actor": "us"}]
    sdk = build_sdk(negotiation=type("Flow", (), {"timeline": steps})())

    assert sdk.negotiation_timeline() == steps


def test_recent_events_are_the_tail_of_the_bus():
    history = [{"event": f"e{index}"} for index in range(10)]
    sdk = build_sdk(events=type("Bus", (), {"history": history})())

    assert sdk.recent_events(limit=3) == history[-3:]


def test_missing_subsystems_produce_empty_panels_not_errors():
    sdk = build_sdk()

    assert sdk.negotiation_timeline() == []
    assert sdk.recent_events() == []
    assert sdk.gatekeepers() == []
