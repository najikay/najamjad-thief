"""Loading Gmail credentials, non-interactively or not at all.

This module was missing, and its absence was the most expensive defect in the
project. `GmailSender` has always accepted an injected `service`, and nothing
ever injected one: every sender was built with `service=None`, so `send_report`
raised "no Gmail service configured" at the end of a match. Artifacts were
written, the series scored, and the report was never delivered — which under
book rules 33-35 scores the same as not playing. Assignment 6 lost matches to an
unsent report; this repository was set up to lose them the same way, quietly,
with a green test suite.

Two commitments, and they are the reason this is a separate module from
`scripts/authorise_gmail.py`:

* **No interactive flow can start from here.** `InstalledAppFlow` is never
  imported. Consent is a human action taken once, in the script; the agent only
  ever *loads* what that produced. A browser prompt on a background thread with
  nobody watching is precisely how assignment 6 failed.
* **Send-only, verified at load.** Book rule 30 is least privilege, and a token
  that has quietly acquired broader scope is a rule breach we would not
  otherwise notice. The scope is checked here, not assumed.

An expired access token is refreshed silently — that is routine and offline.
A *missing refresh token* is not recoverable without a human, so it raises and
names the script to run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SCOPES = [SEND_SCOPE]
DEFAULT_TOKEN = Path("secrets/token.json")
FIX = "run: uv run python scripts/authorise_gmail.py"


class GmailAuthError(RuntimeError):
    """Credentials could not be loaded without a human."""


def load_credentials(token_path: Path | str = DEFAULT_TOKEN) -> Any:
    """Load and, if needed, refresh the stored token. Never prompts.

    Input: path to the token written by `scripts/authorise_gmail.py`.
    Output: usable, non-expired credentials.
    Setup: requires that script to have been run once by a human.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = Path(token_path)
    if not path.exists():
        raise GmailAuthError(f"no Gmail token at {path} — {FIX}")

    credentials = Credentials.from_authorized_user_file(str(path), SCOPES)
    granted = set(getattr(credentials, "scopes", None) or [])
    if granted != set(SCOPES):
        raise GmailAuthError(
            f"token at {path} grants {sorted(granted)}, need exactly {SCOPES} "
            f"(book rule 30, least privilege) — {FIX}"
        )

    if credentials.valid:
        return credentials
    if not credentials.refresh_token:
        raise GmailAuthError(f"token at {path} is expired and cannot refresh — {FIX}")
    # Offline and silent: this is the routine case between matches, and it is
    # the whole reason a refresh token was requested at consent time.
    credentials.refresh(Request())
    path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def build_service(token_path: Path | str = DEFAULT_TOKEN) -> Any:
    """The Gmail API client `GmailSender` sends through.

    Input: path to the stored token.
    Output: a Gmail service whose `.users().messages().send(...)` works.
    Setup: `google-api-python-client`; discovery caching is off because it
        writes to a shared cache directory and warns noisily under uv.
    """
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=load_credentials(token_path), cache_discovery=False)


def service_or_none(token_path: Path | str = DEFAULT_TOKEN) -> Any:
    """The service, or `None` when credentials are unusable.

    For callers that must not fail a match over mail: the artifacts are already
    on disk and recoverable by hand. The *reason* is never swallowed silently —
    `preflight` surfaces it before a match, which is the moment it can still be
    fixed.
    """
    try:
        return build_service(token_path)
    except Exception:  # noqa: BLE001 - reported by preflight, never fatal here
        return None
