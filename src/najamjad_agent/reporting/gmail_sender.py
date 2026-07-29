"""Sending the result report — the last thing that has to work.

Assignment 6's worst failure lived here: the send path ran on a background
thread, swallowed every exception, and could silently demand interactive OAuth
consent that nobody was there to give. A match could be won on the board and
score nothing.

So this module is built around three commitments:

* **Never interactive.** Credentials come from an existing token, refreshed
  non-interactively; failure surfaces *at preflight*, never mid-match.
* **Delivery is proven, not assumed.** A send returns the API message id; no id
  means failure, with an alert. "It didn't raise" is not evidence.
* **Nothing is lost.** An unsendable report is dead-lettered, not vanished.

Scope is `gmail.send` only (book rule 30) — we never request read access.
"""

from pathlib import Path
from typing import Any

from ..shared.gatekeeper import ApiGatekeeper
from ..shared.practice import PracticeError, PracticeMode
from .mail_message import SendResult, build_message

__all__ = ["DRAFT", "SEND", "GmailError", "GmailSender", "SendResult", "build_message"]

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SCOPES = (SEND_SCOPE,)
DRAFT = "draft"
SEND = "send"


class GmailError(Exception):
    """Raised when a report could not be delivered."""


class GmailSender:
    """Delivers the result JSON to the lecturer, and proves it did."""

    def __init__(
        self,
        gatekeeper: ApiGatekeeper,
        recipient: str,
        service: Any = None,
        sender: str = "me",
        mode: str = DRAFT,
        emit: Any = None,
        dead_letter_dir: Path | None = None,
        practice: PracticeMode | None = None,
    ) -> None:
        """Wire the sender; `service` is injected so tests never touch Gmail."""
        if mode not in (DRAFT, SEND):
            raise ValueError(f"mode must be {DRAFT!r} or {SEND!r}; got {mode!r}")
        self._gatekeeper = gatekeeper
        self._service = service
        self.recipient = recipient
        self.sender = sender
        self.mode = mode
        self._emit = emit or (lambda _event: None)
        self._dead_letter = dead_letter_dir
        self._practice = practice or PracticeMode()

    def _api(self) -> Any:
        """The Gmail service, which must already exist — never built here."""
        if self._service is None:
            raise GmailError(
                "no Gmail service configured; run preflight to load and refresh "
                "credentials before a match (never interactively mid-game)"
            )
        return self._service

    def _dispatch(self, raw: str) -> dict[str, Any]:
        """One API call — the unit the gatekeeper wraps and retries."""
        messages = self._api().users().messages()
        if self.mode == DRAFT:
            return self._api().users().drafts().create(
                userId=self.sender, body={"message": {"raw": raw}}
            ).execute()
        return messages.send(userId=self.sender, body={"raw": raw}).execute()

    def send_report(self, attachment: Path, subject: str, body: str = "") -> SendResult:
        """Deliver one report and return proof, or raise with the report saved.

        In practice mode the recipient is redirected and then *checked*:
        `verify` refuses to send anywhere but the redirect, so a rewrite that
        silently did not happen fails here instead of mailing the lecturer.
        """
        # Checked before the gatekeeper: a missing service is a configuration
        # error, and retrying it three times only buries the actionable message
        # under a generic "failed after N attempts". It is parked on the way
        # out, though — this branch used to raise past the dead-letter handler,
        # so the one failure most likely to happen was the one that left no
        # recoverable copy behind.
        try:
            self._api()
        except GmailError as unusable:
            self._park(attachment, str(unusable))
            raise
        recipient = self._practice.route(self.recipient)
        self._practice.verify(recipient)
        subject = self._practice.subject(subject)
        raw = build_message(self.sender, recipient, subject, body or subject, attachment)
        try:
            response = self._gatekeeper.execute(self._dispatch, raw)
        except PracticeError:
            raise
        except Exception as error:  # noqa: BLE001 - re-raised after preserving the report
            self._park(attachment, str(error))
            raise GmailError(f"report not delivered: {error}") from error

        message_id = str((response or {}).get("id", ""))
        if not message_id:
            self._park(attachment, "API returned no message id")
            self._emit({"event": "report.unconfirmed", "recipient": recipient})
            raise GmailError("Gmail returned no message id; delivery is unconfirmed")

        self._emit(
            {
                "event": "report.delivered",
                "message_id": message_id,
                "mode": self.mode,
                "recipient": recipient,
                "practice": self._practice.enabled,
            }
        )
        return SendResult(message_id=message_id, mode=self.mode, recipient=recipient)

    def _park(self, attachment: Path, reason: str) -> Path | None:
        """Preserve an undelivered report so it can be sent by hand."""
        self._emit({"event": "report.dead_letter", "reason": reason, "file": attachment.name})
        if self._dead_letter is None:
            return None
        self._dead_letter.mkdir(parents=True, exist_ok=True)
        parked = self._dead_letter / f"UNSENT_{attachment.name}"
        parked.write_bytes(attachment.read_bytes())
        return parked
