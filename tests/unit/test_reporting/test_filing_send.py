"""Sending a filed result (T-2424).

Two defects lived on this path, and both were invisible for the same reason:
no Gmail service was ever injected, so `send_report` raised before the code
below it ever ran. A dead path cannot be wrong until it is reached.

    1. the report was never sent at all (no service)
    2. once it sent, the success event carried a `SendResult` dataclass into a
       JSON log, so the emit raised and filing was recorded as FAILED *after
       the mail had gone out*

The second is the nastier one: the operator's log said the match failed to
file, while the lecturer had the report. These tests pin the shape of what
gets emitted, because that is what made the difference between the two.
"""

import json

from najamjad_agent.reporting.filing import MatchFiler
from najamjad_agent.reporting.mail_message import SendResult


class Sender:
    """A sender that succeeds, which is the case that had never been exercised."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send_report(self, attachment, subject: str = "", body: str = "") -> SendResult:
        self.sent.append(subject)
        return SendResult(message_id="msg-1", mode="send", recipient="me@example.invalid")


def filer(tmp_path, sender=None) -> MatchFiler:
    events: list[dict] = []
    made = MatchFiler(tmp_path, "najamjad-vs-rival", "uid", ("najamjad", "rival"),
                      sender=sender, emit=events.append)
    made.events = events  # type: ignore[attr-defined]
    return made


def result_file(tmp_path):
    path = tmp_path / "result.json"
    path.write_text('{"ok": true}', encoding="utf-8")
    return path


def test_a_successful_send_returns_the_message_id_not_the_result_object(tmp_path):
    """The return is quoted as proof of delivery, so it must be the id."""
    made = filer(tmp_path, Sender())

    assert made.send(result_file(tmp_path)) == "msg-1"


def test_the_success_event_survives_being_written_to_the_log(tmp_path):
    """The regression test.

    The event log is JSON lines on disk. An event carrying a dataclass raises
    at serialisation time, which turned a successful send into a recorded
    failure. Asserting the event is *serialisable* is the assertion that
    matters — asserting only its keys would have passed before the fix.
    """
    made = filer(tmp_path, Sender())

    made.send(result_file(tmp_path))

    sent = [event for event in made.events if event["event"] == "report.sent"]
    assert sent, "a successful send must be recorded"
    json.dumps(sent[0])  # must not raise


def test_the_success_event_names_where_the_report_actually_went(tmp_path):
    """In practice mode this is the redirect address, not the configured one."""
    made = filer(tmp_path, Sender())

    made.send(result_file(tmp_path))

    sent = next(event for event in made.events if event["event"] == "report.sent")
    assert sent["message_id"] == "msg-1"
    assert sent["recipient"] == "me@example.invalid"


def test_an_unwired_sender_is_reported_rather_than_silently_skipped(tmp_path):
    """Rule 35 punishes not reporting like false reporting, so silence is not an option."""
    made = filer(tmp_path, None)

    assert made.send(result_file(tmp_path)) is None
    assert [event["event"] for event in made.events] == ["report.not_sent"]
