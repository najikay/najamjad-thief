"""Tests for the Gmail sender — fully mocked; no test touches a real account.

This is where Assignment 6 lost matches it had won on the board, so the
assertions here are about *proof of delivery*, not about the call not raising.
"""

import base64
import json
from email import message_from_bytes
from pathlib import Path

import pytest
from gmail_fakes import RECIPIENT, FakeGmail, _gatekeeper

from najamjad_agent.reporting.gmail_sender import (
    SCOPES,
    SEND_SCOPE,
    GmailError,
    GmailSender,
    build_message,
)


@pytest.fixture()
def report(tmp_path: Path) -> Path:
    path = tmp_path / "result_najamjad-vs-rival.json"
    path.write_text(json.dumps({"game_id": "najamjad-vs-rival"}), encoding="utf-8")
    return path


def test_only_the_send_scope_is_ever_requested() -> None:
    """Book rule 30: least privilege — we never ask to read mail."""
    assert SCOPES == (SEND_SCOPE,)
    assert SEND_SCOPE.endswith("gmail.send")
    assert "readonly" not in SEND_SCOPE and "modify" not in SEND_SCOPE


def test_the_report_travels_as_an_attachment_not_a_body(report: Path) -> None:
    """Rules 33-34: a plaintext report is rejected outright."""
    raw = build_message("me", RECIPIENT, "subject", "body", report)
    parsed = message_from_bytes(base64.urlsafe_b64decode(raw))
    attachments = [part for part in parsed.walk() if part.get_filename()]
    assert len(attachments) == 1
    assert attachments[0].get_filename() == report.name
    assert attachments[0].get_content_type() == "application/json"


def test_the_recipient_is_the_book_mandated_address(report: Path) -> None:
    raw = build_message("me", RECIPIENT, "s", "b", report)
    parsed = message_from_bytes(base64.urlsafe_b64decode(raw))
    assert parsed["To"] == RECIPIENT


def test_a_successful_send_returns_a_message_id(report: Path) -> None:
    """'It did not raise' is not evidence of delivery (A6 pain #1)."""
    gmail = FakeGmail()
    sender = GmailSender(_gatekeeper(), RECIPIENT, service=gmail, mode="send")
    result = sender.send_report(report, subject="Result")
    assert result.delivered
    assert result.message_id == "msg-123"
    assert gmail.sent


def test_delivery_is_evented_for_the_dashboard(report: Path) -> None:
    events: list[dict] = []
    sender = GmailSender(
        _gatekeeper(), RECIPIENT, service=FakeGmail(), mode="send", emit=events.append
    )
    sender.send_report(report, subject="Result")
    delivered = [event for event in events if event["event"] == "report.delivered"]
    assert delivered and delivered[0]["message_id"] == "msg-123"


def test_a_response_without_an_id_is_treated_as_failure(report: Path, tmp_path: Path) -> None:
    """The exact silent-success shape that hid A6's broken sends."""
    events: list[dict] = []
    sender = GmailSender(
        _gatekeeper(),
        RECIPIENT,
        service=FakeGmail(response={}),
        mode="send",
        emit=events.append,
        dead_letter_dir=tmp_path / "dead",
    )
    with pytest.raises(GmailError, match="no message id"):
        sender.send_report(report, subject="Result")
    assert any(event["event"] == "report.unconfirmed" for event in events)


def test_draft_mode_creates_a_draft_for_development(report: Path) -> None:
    gmail = FakeGmail()
    sender = GmailSender(_gatekeeper(), RECIPIENT, service=gmail, mode="draft")
    assert sender.send_report(report, subject="Result").mode == "draft"
    assert gmail.drafted and not gmail.sent


def test_an_unknown_mode_is_refused() -> None:
    with pytest.raises(ValueError, match="mode must be"):
        GmailSender(_gatekeeper(), RECIPIENT, mode="fire-and-forget")


def test_a_missing_service_fails_loudly_and_points_at_preflight(report: Path) -> None:
    """No interactive OAuth may ever trigger from the send path (A6 lesson)."""
    sender = GmailSender(_gatekeeper(), RECIPIENT, service=None, mode="send")
    with pytest.raises(GmailError, match="preflight"):
        sender.send_report(report, subject="Result")


def test_an_api_failure_preserves_the_report_for_manual_sending(
    report: Path, tmp_path: Path
) -> None:
    """Nothing is lost: an unsent report can still be filed by hand."""
    dead_letter = tmp_path / "dead"
    sender = GmailSender(
        _gatekeeper(),
        RECIPIENT,
        service=FakeGmail(error=RuntimeError("429 rate limited")),
        mode="send",
        dead_letter_dir=dead_letter,
    )
    with pytest.raises(GmailError, match="not delivered"):
        sender.send_report(report, subject="Result")
    parked = list(dead_letter.glob("UNSENT_*"))
    assert parked and json.loads(parked[0].read_text())["game_id"] == "najamjad-vs-rival"


def test_a_rate_limit_is_retried_through_the_gatekeeper(report: Path) -> None:
    """Book PAGE 95: blind resends get the account suspended."""
    events: list[dict] = []
    sender = GmailSender(
        _gatekeeper(events),
        RECIPIENT,
        service=FakeGmail(error=RuntimeError("429 Too Many Requests")),
        mode="send",
    )
    with pytest.raises(GmailError):
        sender.send_report(report, subject="Result")
    assert any(event["event"] == "gatekeeper.retry" for event in events)


def test_a_failure_without_a_dead_letter_dir_still_raises(report: Path) -> None:
    sender = GmailSender(
        _gatekeeper(), RECIPIENT, service=FakeGmail(error=OSError("network")), mode="send"
    )
    with pytest.raises(GmailError):
        sender.send_report(report, subject="Result")
