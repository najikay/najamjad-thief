"""`ui.host` was configuration that nothing read (T-2533).

`config/setup.json` has carried a `ui.host` key, and a note explaining why it is
loopback, since the file was written. `bootstrap` read `ui.port` beside it and
never the host, so the bind was whatever `ui/server.py` defaulted to and the key
was decoration — the same defect class as `attach_game`, `reconcile` and
`step_zero`: correct code, real config, no caller.

It surfaced on WSL2, where a Windows browser reaches a loopback-bound server
only while localhost forwarding holds. When it stops, the dashboard is
unreachable for a whole match and there is no supported way to move the bind.

The default does not change, and these tests pin that as hard as they pin the
fix: the dashboard renders our belief grid and our sealed state, so anything
that can reach it gets what commit-reveal exists to hide (rules 8-9).
"""

from najamjad_agent.shared.app_config import LOOPBACK, dashboard_bind
from najamjad_agent.shared.events import EventBus


def test_the_default_is_still_loopback() -> None:
    """An absent key must never widen the bind (rules 8-9)."""
    assert dashboard_bind({}) == (LOOPBACK, 8000)


def test_an_empty_host_is_read_as_loopback_not_as_every_interface() -> None:
    """`""` binds to all interfaces in uvicorn, so it must not survive.

    A key someone blanked while editing is the likeliest way to expose this by
    accident, and it is exactly the case a bare `str(...)` would let through.
    """
    assert dashboard_bind({"ui": {"host": ""}})[0] == LOOPBACK


def test_a_configured_host_and_port_are_honoured() -> None:
    """The whole point: the file gets to decide, which it never did before."""
    assert dashboard_bind({"ui": {"host": "0.0.0.0", "port": 8123}}) == ("0.0.0.0", 8123)


def test_a_note_cannot_shadow_the_host() -> None:
    """`_note` sits beside `host` in the real file; `setting` ignores it."""
    setup = {"ui": {"_note": "loopback by design", "host": "192.168.1.50"}}

    assert dashboard_bind(setup)[0] == "192.168.1.50"


def _attach(monkeypatch, setup: dict, override: str = ""):
    """Run the real `_attach_dashboard` and report where it bound."""
    from najamjad_agent.sdk import bootstrap
    from najamjad_agent.ui import server as server_module

    seen: dict = {}

    class FakeServer:
        def __init__(self, _sdk, _hub, host="127.0.0.1", port=8000):
            seen["host"], seen["port"] = host, port

    class FakeActions:
        def attach_dashboard(self, server):
            seen["attached"] = server

    monkeypatch.setattr(bootstrap, "load_setup", lambda *_a, **_k: setup)
    monkeypatch.setattr(server_module, "DashboardServer", FakeServer)
    bus = EventBus()
    events: list = []
    bus.subscribe(events.append)
    bootstrap._attach_dashboard(object(), FakeActions(), object(), bus, override)  # noqa: SLF001
    return seen, events


def test_bootstrap_binds_where_the_config_says(monkeypatch) -> None:
    """The wiring, which is the actual defect — not `dashboard_bind` alone.

    A test of the helper passes just as happily when nothing calls it, which is
    how this shipped as decoration in the first place.
    """
    seen, _ = _attach(monkeypatch, {"ui": {"host": "0.0.0.0", "port": 8321}})

    assert (seen["host"], seen["port"]) == ("0.0.0.0", 8321)
    assert "attached" in seen


def test_bootstrap_still_binds_loopback_when_nothing_is_configured(monkeypatch) -> None:
    """The default has to survive the change that made it configurable."""
    seen, _ = _attach(monkeypatch, {})

    assert seen["host"] == LOOPBACK


def test_leaving_loopback_is_announced(monkeypatch) -> None:
    """Reachable from another machine is a decision, so the log records it.

    Rules 8-9: the dashboard shows our belief and our sealed state. If this is
    ever exposed it must be visible in the same event log as every other
    match-day change, not inferred later from a config file.
    """
    _, events = _attach(monkeypatch, {"ui": {"host": "0.0.0.0"}})

    warnings = [e for e in events if e.get("event") == "dashboard.not_loopback"]
    assert len(warnings) == 1
    assert warnings[0]["host"] == "0.0.0.0"


def test_staying_on_loopback_says_nothing(monkeypatch) -> None:
    """A warning on the safe default would train the operator to ignore it."""
    _, events = _attach(monkeypatch, {"ui": {"host": "localhost"}})

    assert not [e for e in events if e.get("event") == "dashboard.not_loopback"]


def test_the_run_override_beats_the_shipped_config(monkeypatch) -> None:
    """`--dashboard-host`, and why it exists rather than a config edit.

    `test_the_dashboard_binds_to_loopback` pins the *shipped* file at
    127.0.0.1 for rules 8-9, and it is right to. Editing that file to reach the
    panel from Windows would have meant loosening the guard — the same trade
    `--group-id` already refused, in the same words: applied at runtime so it
    never touches the committed config.
    """
    seen, events = _attach(monkeypatch, {"ui": {"host": "127.0.0.1"}}, override="0.0.0.0")

    assert seen["host"] == "0.0.0.0"
    assert [e for e in events if e.get("event") == "dashboard.not_loopback"]


def test_no_override_leaves_the_config_in_charge(monkeypatch) -> None:
    """An unset flag is not a value; it must not shadow the file."""
    seen, _ = _attach(monkeypatch, {"ui": {"host": "192.168.1.9"}}, override="")

    assert seen["host"] == "192.168.1.9"
