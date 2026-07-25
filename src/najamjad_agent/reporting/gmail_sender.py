"""Sending the result report — the last thing that has to work.

Assignment 6's worst failure lived here: the send path ran on a background
thread, swallowed every exception, and could silently demand interactive OAuth
consent that nobody was there to give. A match could be won on the board and
score nothing.

So this module is built around three commitments:

* **Never interactive.** Credentials are loaded from an existing token and
  refreshed non-interactively. If that fails, it fails *loudly at preflight*,
  not silently mid-match. No browser flow can ever trigger from here.
* **Delivery is proven, not assumed.** A send returns the API message id; no id
  means failure, with an alert. "It didn't raise" is not evidence.
* **Nothing is lost.** An unsendable report is written to a dead-letter file so
  it can be sent by hand rather than vanishing.

Scope is `gmail.send` only (book rule 30) — we never request read access.
"""

import base64
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from ..shared.gatekeeper import ApiGatekeeper

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SCOPES = (SEND_SCOPE,)
DRAFT = "draft"
SEND = "send"


class GmailError(Exception):
    """Raised when a report could not be delivered."""


@dataclass
class SendResult:
    """Proof of what happened to one report."""

    message_id: str
    mode: str
    recipient: str

    @property
    def delivered(self) -> bool:
        """True only when the API returned an id we can quote."""
        return bool(self.message_id)


def build_message(sender: str, recipient: str, subject: str, body: str, attachment: Path) -> str:
    """A MIME message carrying the result JSON as an attachment.

    Book rules 33-34: the report must be a JSON *attachment*. A pasted-in body
    is rejected outright, so the attachment is not a nicety.
    """
    message = EmailMessage()
    message["To"] = recipient
    message["From"] = sender
    message["Subject"] = subject
    message.set_content(body)
    message.add_attachment(
        attachment.read_bytes(),
        maintype="application",
        subtype="json",
        filename=attachment.name,
    )
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


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
        """Deliver one report and return proof, or raise with the report saved."""
        # Checked before the gatekeeper: a missing service is a configuration
        # error, and retrying it three times only buries the actionable message
        # under a generic "failed after N attempts".
        self._api()
        raw = build_message(self.sender, self.recipient, subject, body or subject, attachment)
        try:
            response = self._gatekeeper.execute(self._dispatch, raw)
        except Exception as error:  # noqa: BLE001 - re-raised after preserving the report
            self._park(attachment, str(error))
            raise GmailError(f"report not delivered: {error}") from error

        message_id = str((response or {}).get("id", ""))
        if not message_id:
            self._park(attachment, "API returned no message id")
            self._emit({"event": "report.unconfirmed", "recipient": self.recipient})
            raise GmailError("Gmail returned no message id; delivery is unconfirmed")

        self._emit(
            {
                "event": "report.delivered",
                "message_id": message_id,
                "mode": self.mode,
                "recipient": self.recipient,
            }
        )
        return SendResult(message_id=message_id, mode=self.mode, recipient=self.recipient)

    def _park(self, attachment: Path, reason: str) -> Path | None:
        """Preserve an undelivered report so it can be sent by hand."""
        self._emit({"event": "report.dead_letter", "reason": reason, "file": attachment.name})
        if self._dead_letter is None:
            return None
        self._dead_letter.mkdir(parents=True, exist_ok=True)
        parked = self._dead_letter / f"UNSENT_{attachment.name}"
        parked.write_bytes(attachment.read_bytes())
        return parked
