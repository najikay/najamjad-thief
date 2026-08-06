"""Tests for the event bus: correlation, secret scrubbing, fan-out isolation."""

import json
from datetime import datetime
from pathlib import Path

from najamjad_agent.shared.events import EventBus


def test_published_events_are_kept_in_order() -> None:
    bus = EventBus()
    bus.publish({"event": "first"})
    bus.publish({"event": "second"})
    assert [item["event"] for item in bus.history] == ["first", "second"]


def test_correlation_ids_are_stamped_onto_every_event() -> None:
    """One game_uid across logs, UI and analysis — or they cannot be joined."""
    bus = EventBus(correlation={"game_uid": "uid-1"})
    bus.publish({"event": "turn.sent"})
    assert bus.history[0]["game_uid"] == "uid-1"


def test_correlation_can_be_extended_mid_match() -> None:
    bus = EventBus(correlation={"game_uid": "uid-1"})
    bus.correlate(sub_game=2)
    bus.publish({"event": "x"})
    assert bus.history[0]["sub_game"] == 2


def test_event_fields_win_over_correlation() -> None:
    bus = EventBus(correlation={"step": 0})
    bus.publish({"event": "x", "step": 7})
    assert bus.history[0]["step"] == 7


def test_nonces_are_never_written_to_the_stream() -> None:
    """Book rule 18: a leaked nonce inverts our commitments."""
    bus = EventBus()
    bus.publish({"event": "seal", "nonce": "deadbeef" * 4})
    assert bus.history[0]["nonce"] == "<redacted>"


def test_api_keys_and_tokens_are_scrubbed() -> None:
    bus = EventBus()
    bus.publish({"event": "llm.call", "api_key": "sk-ant-secret", "token": "tok"})
    assert bus.history[0]["api_key"] == "<redacted>"
    assert bus.history[0]["token"] == "<redacted>"


def test_scrubbing_reaches_nested_payloads() -> None:
    bus = EventBus()
    bus.publish({"event": "x", "detail": {"nonce": "secret", "safe": 1}})
    assert bus.history[0]["detail"] == {"nonce": "<redacted>", "safe": 1}


def test_subscribers_receive_live_events() -> None:
    bus = EventBus()
    seen: list[dict] = []
    bus.subscribe(seen.append)
    bus.publish({"event": "turn.sent"})
    assert seen[0]["event"] == "turn.sent"


def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    seen: list[dict] = []
    stop = bus.subscribe(seen.append)
    stop()
    stop()  # idempotent
    bus.publish({"event": "x"})
    assert seen == []


def test_a_broken_subscriber_cannot_stop_the_game() -> None:
    """A dead dashboard socket must not take down the turn loop feeding it."""
    problems: list[tuple[str, Exception]] = []
    bus = EventBus(on_error=lambda source, error: problems.append((source, error)))
    healthy: list[dict] = []

    def broken(_event: dict) -> None:
        raise RuntimeError("socket closed")

    bus.subscribe(broken)
    bus.subscribe(healthy.append)
    bus.publish({"event": "x"})

    assert healthy, "the healthy subscriber still received the event"
    assert problems[0][0] == "subscriber"


def test_events_are_appended_as_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "events.jsonl"
    bus = EventBus(path=path, correlation={"game_uid": "uid-9"})
    bus.publish({"event": "one"})
    bus.publish({"event": "two"})
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["game_uid"] == "uid-9"


def test_secrets_never_reach_the_file(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    bus = EventBus(path=path)
    bus.publish({"event": "seal", "nonce": "supersecretnonce"})
    assert "supersecretnonce" not in path.read_text(encoding="utf-8")


def test_an_unwritable_path_is_reported_not_fatal(tmp_path: Path) -> None:
    """A full disk must not end a match that is otherwise going fine."""
    problems: list[tuple[str, Exception]] = []
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    bus = EventBus(path=blocker / "events.jsonl", on_error=lambda s, e: problems.append((s, e)))
    bus.publish({"event": "x"})
    assert bus.history, "the event is still recorded in memory"
    assert problems and problems[0][0] == "file"


def test_publish_returns_the_enriched_event() -> None:
    bus = EventBus(correlation={"game_uid": "u"})
    published = bus.publish({"event": "x"})
    assert published["event"] == "x"
    assert published["game_uid"] == "u"


def test_every_event_carries_a_utc_timestamp() -> None:
    """Without this the log cannot be lined up against an opponent's server log.

    Ten thousand events were written with no time on them, which is why the one
    diagnostic an opponent offered — their timestamped request log against ours
    — could not be run at all.
    """
    bus = EventBus()
    stamped = bus.publish({"event": "client.sending"})
    assert datetime.fromisoformat(stamped["ts"]).tzinfo is not None


def test_a_caller_supplied_timestamp_is_not_overwritten() -> None:
    """A replayed event keeps the time it happened, not the time it was re-read."""
    bus = EventBus()
    published = bus.publish({"event": "turn.sent", "ts": "2026-08-02T19:47:36.000+00:00"})
    assert published["ts"] == "2026-08-02T19:47:36.000+00:00"


def test_timestamps_are_written_to_the_log_file(tmp_path: Path) -> None:
    bus = EventBus(path=tmp_path / "events.jsonl")
    bus.publish({"event": "x"})
    bus.close()
    assert "ts" in json.loads((tmp_path / "events.jsonl").read_text().splitlines()[0])
