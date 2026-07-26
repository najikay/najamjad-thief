"""The push path: bus event in, WebSocket frame out.

The properties that matter on match day are that two people watching both see
everything, and that a viewer who closes their laptop cannot wedge the game
loop. Both are tested here rather than assumed.
"""

import asyncio
import contextlib
from unittest import mock

import pytest

from najamjad_agent.shared.events import EventBus
from najamjad_agent.ui.app import ConnectionHub, attach_bus


class DeadSocket:
    """A socket whose send always fails, like a browser that went away."""

    def __init__(self) -> None:
        self.sends = 0

    async def send_json(self, message):
        self.sends += 1
        raise ConnectionResetError("viewer closed the tab")


class RecordingSocket:
    """A socket that keeps what it was sent."""

    def __init__(self) -> None:
        self.frames = []

    async def send_json(self, message):
        self.frames.append(message)


def test_a_connecting_page_receives_a_full_snapshot(client):
    with client.websocket_connect("/ws") as socket:
        frame = socket.receive_json()

    assert frame["type"] == "snapshot"
    assert frame["board"]["available"] is True
    assert frame["transcript"][0]["text"] == "I am near the park"


def test_a_socket_that_fails_mid_handshake_does_not_take_the_server_down(client, sdk, hub):
    """An error while building the first frame must cost only that viewer."""
    healthy, broken = sdk.snapshot, mock.Mock(side_effect=RuntimeError("panel exploded"))
    sdk.snapshot = broken

    with contextlib.suppress(Exception), client.websocket_connect("/ws"):
        pass

    assert broken.called
    assert hub.viewers == 0

    sdk.snapshot = healthy
    with client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["type"] == "snapshot"


def test_two_viewers_both_receive_every_event(client, hub):
    with client.websocket_connect("/ws") as first, client.websocket_connect("/ws") as second:
        first.receive_json()
        second.receive_json()
        assert hub.viewers == 2

        hub.publish({"event": "turn.committed", "step": 4})

        for socket in (first, second):
            frame = socket.receive_json()
            assert frame["type"] == "event"
            assert frame["event"] == "turn.committed"


@pytest.mark.asyncio
async def test_a_dead_viewer_is_dropped_without_stalling_the_others():
    hub = ConnectionHub()
    dead, alive = DeadSocket(), RecordingSocket()
    hub._sockets.extend([dead, alive])

    await hub.broadcast({"type": "event", "event": "llm.fallback"})

    assert hub.viewers == 1
    assert hub.dropped == 1
    assert alive.frames[0]["event"] == "llm.fallback"


@pytest.mark.asyncio
async def test_publishing_with_no_viewers_costs_the_game_nothing():
    hub = ConnectionHub()
    hub.bind_loop(asyncio.get_running_loop())

    hub.publish({"event": "game.started"})  # must not raise, must not block

    assert hub.viewers == 0


def test_publishing_before_the_server_starts_is_a_no_op():
    hub = ConnectionHub()
    hub._sockets.append(RecordingSocket())

    hub.publish({"event": "early"})  # no loop bound yet

    assert hub._sockets[0].frames == []


def test_the_bus_subscription_survives_a_broken_dashboard():
    hub = ConnectionHub()
    bus = EventBus()
    unsubscribe = attach_bus(bus, hub)

    bus.publish({"event": "turn.sent"})  # no loop bound: hub declines, bus carries on
    unsubscribe()

    assert bus.history[0]["event"] == "turn.sent"


@pytest.mark.asyncio
async def test_an_event_carrying_its_own_type_cannot_rename_the_frame():
    """The bus belongs to the game and may publish any keys; the envelope is
    ours. A shadowed `type` would fail validation and the frame would vanish."""
    hub = ConnectionHub()
    hub.bind_loop(asyncio.get_running_loop())
    socket = RecordingSocket()
    hub._sockets.append(socket)

    await hub.broadcast({**{"event": "audit.done", "type": "system_spec"}, "type": "event"})

    assert socket.frames[0]["type"] == "event"
    assert socket.frames[0]["event"] == "audit.done"


@pytest.mark.asyncio
async def test_a_frame_that_would_leak_is_dropped_rather_than_sent():
    """Never send it, and never drop it silently."""
    hub = ConnectionHub()
    socket = RecordingSocket()
    hub._sockets.append(socket)

    await hub.broadcast({"type": "event", "event": "turn", "opponent_position": [2, 2]})

    assert socket.frames == []
    assert hub.invalid == 1
    assert hub.viewers == 1, "the viewer keeps its connection; only the frame is refused"


@pytest.mark.asyncio
async def test_an_unknown_frame_type_is_dropped_without_killing_the_broadcast():
    hub = ConnectionHub()
    socket = RecordingSocket()
    hub._sockets.append(socket)

    await hub.broadcast({"type": "nonsense"})
    await hub.broadcast({"type": "event", "event": "recovered"})

    assert hub.invalid == 1
    assert [frame["event"] for frame in socket.frames] == ["recovered"]


def test_the_opening_snapshot_is_validated_like_every_other_frame(client, sdk):
    """The largest payload must not be the one the guard never sees."""
    sdk.record_message("in", "hello", provider="peer")

    with client.websocket_connect("/ws") as socket:
        frame = socket.receive_json()

    assert frame["type"] == "snapshot"
    assert "opponent_position" not in str(frame)


def test_a_leaking_snapshot_is_refused_rather_than_served(client, sdk, hub):
    """If a future query ever added a forbidden field, the socket must not
    quietly hand it to a browser. The connection is closed with nothing sent."""
    sdk.snapshot = mock.Mock(return_value={"board": {"opponent_position": [1, 1]}})

    with contextlib.suppress(Exception), client.websocket_connect("/ws"):
        pass

    assert sdk.snapshot.called
    assert hub.viewers == 0


def test_leaving_twice_is_safe(hub):
    socket = RecordingSocket()
    hub._sockets.append(socket)

    hub.leave(socket)
    hub.leave(socket)

    assert hub.viewers == 0
