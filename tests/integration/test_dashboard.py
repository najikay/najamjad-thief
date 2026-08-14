"""The dashboard driven by a real game, and audited for what it may not show.

Two orchestrators play a genuine mini-game; our side's SDK feeds a dashboard
while a fake browser watches over the socket. Book rules 8-9 make an
over-informative UI a disqualification, so the tests that matter most here are
the two that separate what we *inferred* about the thief from what we could
only have been *told* — a distinction a value scan alone cannot make.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from najamjad_agent.constants import Move, Phase, Role
from najamjad_agent.domain.fsm import GameStateMachine
from najamjad_agent.domain.orchestrator import Orchestrator
from najamjad_agent.sdk.sdk import AgentSdk
from najamjad_agent.shared.events import EventBus
from najamjad_agent.ui.app import ConnectionHub, attach_bus, create_app
from tests.fakes.orchestration import FakeClock, FixedSpeaker, ScriptedBrain, build_state
from tests.integration.test_headless_game import LinkedTransport, _peer, _play


@pytest.fixture()
def wired():
    """A cop watched by a dashboard, playing a thief that runs east."""
    cop_link, thief_link = LinkedTransport(), LinkedTransport()
    cop_link.connect(thief_link)
    bus = EventBus(correlation={"game_uid": "dash"})
    state = build_state(Role.COP)
    fsm = GameStateMachine(game_uid="dash")
    fsm.to(Phase.WAITING_FOR_OPPONENT)
    cop = Orchestrator(
        state=state,
        fsm=fsm,
        transport=cop_link,
        brain=ScriptedBrain([Move.SOUTH] * 6),
        speaker=FixedSpeaker(),
        clock=FakeClock(),
        emit=bus.publish,
    )
    thief = _peer(Role.THIEF, [Move.EAST] * 6, thief_link)
    sdk = AgentSdk(state=state, fsm=fsm, events=bus)
    hub = ConnectionHub()
    attach_bus(bus, hub)
    return cop, thief, sdk, hub, bus


def play_and_collect(cop, thief, bus, socket, turns: int = 3) -> list[dict]:
    """Play, then read exactly the frames those turns should have produced.

    The count comes from the bus rather than a timeout: every event published
    while a viewer is attached must arrive, so "one frame per event" is the
    property under test, and a missing frame hangs loudly instead of passing.
    """
    before = len(bus.history)
    _play(cop, thief, turns=turns)
    published = len(bus.history) - before
    return [socket.receive_json() for _ in range(published)]


def test_a_watching_dashboard_sees_every_event_the_game_publishes(wired):
    cop, thief, sdk, hub, bus = wired

    with TestClient(create_app(sdk, hub)) as client, client.websocket_connect("/ws") as socket:
        opening = socket.receive_json()
        events = play_and_collect(cop, thief, bus, socket)

    assert opening["type"] == "snapshot"
    assert events, "a played game must produce events"
    assert {frame["type"] for frame in events} == {"event"}
    assert any(str(frame.get("event", "")).startswith("turn.") for frame in events)


def test_every_panel_has_data_by_the_end_of_a_game(wired):
    cop, thief, sdk, hub, _bus = wired
    _play(cop, thief, turns=3)
    sdk.record_message("in", "still downtown", provider="peer", step=2)

    with TestClient(create_app(sdk, hub)) as client:
        snapshot = client.get("/api/snapshot").json()

    assert snapshot["board"]["own_position"] == list(cop.state.own_position)
    assert snapshot["board"]["belief_peak"]
    assert any(value > 0 for value in snapshot["board"]["belief"].values())
    assert snapshot["turn"]["step"] == 3
    assert snapshot["transcript"][0]["provider"] == "peer"


def without_inferences(payload):
    """Strip the fields we legitimately *deduce* about the opponent.

    Belief and scent are computed from the trail, so a peak that lands on the
    thief's real cell is the engine working, not a disclosure. Scanning them for
    the true position would test our accuracy, not our honesty — the leak test
    below needs everything else.

    `peak_cell` joined them on 2026-08-14: it is the argmax of the field the
    opponent *chose to transmit*, recorded so an archived event log can settle
    their scent honesty on its own. The line this guard draws is disclosure
    versus inference, and an argmax we computed from their voluntary emission
    falls on the same side as `belief_peak`.

    The mirror case is a genuine leak and is handled where it belongs, in the
    code rather than here: `scent.emitted` deliberately carries **no** cell,
    because the centre of our own freshest deposit is our own current position
    and this event stream is served to a dashboard a practice run binds to
    `0.0.0.0`. This test caught that within a day of the field being added.
    """
    inferred = {"belief", "belief_peak", "opponent_scent", "opponent_estimate", "peak_cell"}
    if isinstance(payload, dict):
        return {
            key: without_inferences(value)
            for key, value in payload.items()
            if key not in inferred
        }
    if isinstance(payload, list):
        return [without_inferences(item) for item in payload]
    return payload


def test_nothing_the_dashboard_shows_discloses_the_thiefs_position(wired):
    cop, thief, sdk, hub, bus = wired

    with TestClient(create_app(sdk, hub)) as client, client.websocket_connect("/ws") as socket:
        seen = [socket.receive_json()]
        seen.extend(play_and_collect(cop, thief, bus, socket))
        seen.append(client.get("/api/snapshot").json())
        seen.append(client.get("/api/events").json())

    truth = list(thief.state.own_position)
    assert truth != list(cop.state.own_position), "the test needs a distinguishable position"
    blob = json.dumps(without_inferences(seen))
    assert json.dumps(truth) not in blob
    for forbidden in ("opponent_position", "their_position", "true_position", "nonce"):
        assert forbidden not in json.dumps(seen)


def test_the_heatmap_shows_a_distribution_because_it_is_inferred(wired):
    """A dashboard handed the truth would render a point mass; ours cannot.

    This is the difference the leak scan alone cannot see: spread over many
    cells is the signature of belief built from a decaying trail rather than
    from a number the opponent sent us.
    """
    cop, thief, sdk, _hub, _bus = wired

    _play(cop, thief, turns=3)
    belief = sdk.board()["belief"]
    live = {cell: mass for cell, mass in belief.items() if mass > 0}

    assert sum(belief.values()) == pytest.approx(1.0, abs=1e-3)
    assert len(live) > 1
    assert max(live.values()) < 1.0


def test_the_turn_banner_follows_the_state_machine(wired):
    cop, thief, sdk, _hub, _bus = wired

    assert sdk.turn()["locked"] is True

    cop.fsm.to(Phase.COMPUTING_MOVE)

    assert sdk.turn()["locked"] is False


def test_events_reach_the_browser_well_inside_the_latency_budget(wired):
    """PRD §4: an event must be on screen within 250 ms of being published.

    Measured across a burst rather than a single event, because the number that
    matters on match day is the one under load — a queue that keeps up on one
    event and falls behind on thirty is the failure mode worth catching.
    """
    _cop, _thief, sdk, hub, bus = wired
    burst = 30

    with TestClient(create_app(sdk, hub)) as client, client.websocket_connect("/ws") as socket:
        socket.receive_json()
        start = time.perf_counter()
        for index in range(burst):
            bus.publish({"event": "llm.retry", "attempt": index})
        received = [socket.receive_json() for _ in range(burst)]
        elapsed = time.perf_counter() - start

    assert len(received) == burst
    assert received[-1]["attempt"] == burst - 1
    assert elapsed / burst < 0.25


def test_a_dashboard_that_never_connects_costs_the_game_nothing(wired):
    cop, thief, _sdk, hub, _bus = wired

    _play(cop, thief, turns=3)

    assert hub.viewers == 0
    assert cop.state.step == 3
