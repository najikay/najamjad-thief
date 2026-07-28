"""Building the report email — construction, separate from delivery.

Split out of `gmail_sender` when that module grew past the size cap holding two
responsibilities: what the message *is*, and what happens when we try to send
it. They fail differently — a malformed attachment is a bug, an undelivered
report is an incident — and they are worth reading apart.
"""

import base64
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path


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
