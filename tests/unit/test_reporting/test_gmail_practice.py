"""Practice mode through the real send path (T-2420).

`test_shared/test_practice.py` tests the mode object in isolation. This tests
that `send_report` actually *uses* it, and asserts on the bytes handed to the
Gmail API — because a sender that forgot to call the redirect would still pass
every test that only exercised `PracticeMode.route`.
"""

import base64

import pytest
from gmail_fakes import RECIPIENT, FakeGmail, _gatekeeper

from najamjad_agent.reporting.gmail_sender import GmailSender
from najamjad_agent.shared.practice import PracticeError, PracticeMode

MINE = "najikayal4@gmail.com"


def delivered_bytes(service: FakeGmail) -> str:
    """What actually went out on the wire."""
    return base64.urlsafe_b64decode(service.sent[-1]["body"]["raw"]).decode("utf-8")


def report_file(tmp_path) -> "object":
    """A minimal result artifact to attach."""
    path = tmp_path / "result.json"
    path.write_text('{"ok": true}', encoding="utf-8")
    return path


def test_a_practice_send_goes_to_the_operator_not_the_lecturer(tmp_path):
    """The redirect has to hold where it matters: in the bytes we transmit."""
    service = FakeGmail()
    sender = GmailSender(
        gatekeeper=_gatekeeper(),
        recipient=RECIPIENT,
        service=service,
        mode="send",
        practice=PracticeMode(enabled=True, redirect_to=MINE),
    )

    result = sender.send_report(report_file(tmp_path), "Result")

    delivered = delivered_bytes(service)
    assert MINE in delivered
    assert RECIPIENT not in delivered
    assert result.recipient == MINE, "the proof of delivery names where it went"


def test_the_practice_subject_is_marked_in_the_delivered_bytes(tmp_path):
    """So a practice report is never mistaken for a real one in the inbox."""
    service = FakeGmail()
    GmailSender(
        gatekeeper=_gatekeeper(), recipient=RECIPIENT, service=service,
        mode="send", practice=PracticeMode(enabled=True, redirect_to=MINE),
    ).send_report(report_file(tmp_path), "Result najamjad vs rival")

    assert "[PRACTICE]" in delivered_bytes(service)


def test_a_practice_run_with_no_redirect_configured_sends_nothing(tmp_path):
    """Refusing beats falling through to the configured recipient.

    The half-configured case is the dangerous one: practice mode on, redirect
    empty. Passing the lecturer's address through there would be the exact
    accident the mode exists to prevent.
    """
    service = FakeGmail()
    sender = GmailSender(
        gatekeeper=_gatekeeper(), recipient=RECIPIENT, service=service,
        mode="send", practice=PracticeMode(enabled=True),
    )

    with pytest.raises(PracticeError):
        sender.send_report(report_file(tmp_path), "Result")

    assert service.sent == [], "nothing may leave while the mode is misconfigured"


def test_a_non_practice_send_is_completely_unaffected(tmp_path):
    """The default path must not change shape because a mode object exists."""
    service = FakeGmail()

    result = GmailSender(
        gatekeeper=_gatekeeper(), recipient=RECIPIENT, service=service, mode="send",
    ).send_report(report_file(tmp_path), "Result")

    assert RECIPIENT in delivered_bytes(service)
    assert "[PRACTICE]" not in delivered_bytes(service)
    assert result.recipient == RECIPIENT
