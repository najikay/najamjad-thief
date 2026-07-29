"""Loading Gmail credentials (T-2423).

This module's absence was the most expensive defect in the project: every
`GmailSender` was built with `service=None`, so a match ended with the report
undelivered — scored under book rules 33-35 like not having played. The suite
was green throughout, because nothing asserted that the send path was *wired*,
only that it behaved correctly once it was.

So the load-bearing test here is `test_the_real_wiring_injects_a_service`. The
rest guard the two commitments: never interactive, and send-only scope.
"""

import json
import pathlib

import pytest

from najamjad_agent.reporting import gmail_auth
from najamjad_agent.reporting.gmail_auth import (
    SCOPES,
    GmailAuthError,
    load_credentials,
    service_or_none,
)

OTHER_SCOPE = "https://www.googleapis.com/auth/gmail.modify"


def token_file(tmp_path, scopes=None, refresh="r-token"):
    """A stored token as the authorisation script writes one."""
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps(
            {
                "token": "a-token",
                "refresh_token": refresh,
                "client_id": "cid",
                "client_secret": "secret",
                "scopes": scopes if scopes is not None else SCOPES,
            }
        ),
        encoding="utf-8",
    )
    return path


class FakeCredentials:
    """Stands in for google's Credentials, including the refresh side effect."""

    def __init__(self, scopes, valid=True, refresh_token="r-token") -> None:
        self.scopes = scopes
        self.valid = valid
        self.refresh_token = refresh_token
        self.refreshed = 0

    def refresh(self, _request) -> None:
        self.refreshed += 1
        self.valid = True

    def to_json(self) -> str:
        return json.dumps({"token": "refreshed"})


@pytest.fixture()
def loaded(monkeypatch):
    """Intercept google's loader so no test touches a real account."""
    made: list[FakeCredentials] = []

    def install(credentials: FakeCredentials) -> FakeCredentials:
        made.append(credentials)
        monkeypatch.setattr(
            "google.oauth2.credentials.Credentials.from_authorized_user_file",
            classmethod(lambda _cls, *_a, **_k: credentials),
        )
        return credentials

    return install


def test_a_missing_token_names_the_script_that_creates_one(tmp_path):
    """The operator reading this is short of time; the fix belongs in the message."""
    with pytest.raises(GmailAuthError, match="authorise_gmail"):
        load_credentials(tmp_path / "absent.json")


def test_a_broader_scope_is_refused(tmp_path, loaded):
    """Book rule 30 is least privilege, and assignment 6's token had gmail.modify.

    A token that has quietly acquired read access is a rule breach we would
    otherwise never notice — it would send perfectly well.
    """
    loaded(FakeCredentials([OTHER_SCOPE]))

    with pytest.raises(GmailAuthError, match="rule 30"):
        load_credentials(token_file(tmp_path, scopes=[OTHER_SCOPE]))


def test_a_valid_token_is_returned_untouched(tmp_path, loaded):
    credentials = loaded(FakeCredentials(SCOPES))

    assert load_credentials(token_file(tmp_path)) is credentials
    assert credentials.refreshed == 0, "a valid token must not be refreshed needlessly"


def test_an_expired_token_refreshes_silently(tmp_path, monkeypatch, loaded):
    """The routine case between matches: offline, and no human involved."""
    credentials = loaded(FakeCredentials(SCOPES, valid=False))
    monkeypatch.setattr("google.auth.transport.requests.Request", lambda *_a, **_k: object())

    load_credentials(token_file(tmp_path))

    assert credentials.refreshed == 1


def test_an_expired_token_with_no_refresh_token_raises(tmp_path, loaded):
    """Not recoverable without a person, so it must not fail at send time."""
    loaded(FakeCredentials(SCOPES, valid=False, refresh_token=""))

    with pytest.raises(GmailAuthError, match="cannot refresh"):
        load_credentials(token_file(tmp_path, refresh=""))


def test_no_interactive_flow_can_start_from_this_module():
    """The assignment 6 failure: consent demanded on a thread nobody watches.

    Asserted over the *imports* rather than the text. A substring search failed
    here for an instructive reason — the module docstring explains that
    `InstalledAppFlow` is never imported, and the word in that sentence tripped
    the grep. Prose about a rule is not a violation of it.
    """
    import ast

    tree = ast.parse(pathlib.Path(gmail_auth.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not any("oauthlib" in name for name in imported), imported


def test_service_or_none_swallows_the_failure_but_not_the_match(tmp_path):
    """A match must not die because the mailbox is unauthorised — the artifacts
    are on disk and can be sent by hand. Preflight is where this gets surfaced."""
    assert service_or_none(tmp_path / "absent.json") is None


def test_the_real_wiring_injects_a_service(monkeypatch):
    """The test whose absence let the defect ship.

    Every sender used to be built with `service=None`. Correct behaviour of a
    sender that is never wired is worth nothing, so this asserts the wiring
    itself: the production builder must pass a service through.
    """
    from najamjad_agent.sdk import match_filing

    sentinel = object()
    monkeypatch.setattr(
        "najamjad_agent.reporting.gmail_auth.service_or_none", lambda *_a, **_k: sentinel
    )

    class Manager:
        def require(self, _key):
            return "someone@example.invalid"

        def get(self, _key, default=None):
            return default

    class Bus:
        def publish(self, _event):
            return None

    sender = match_filing._mail_sender(Manager(), Bus(), {})

    assert sender is not None, "a sender must be built"
    assert sender._service is sentinel, "the Gmail service must be injected"


def test_no_credentials_builds_no_sender_rather_than_one_that_raises(monkeypatch):
    """Reported by a peer running without a Gmail token (T-2431).

    They saw `artifacts.failed` immediately after `artifacts.written` and
    concluded the artifacts were broken — all fourteen had been written
    correctly. The send raised at the point of use, `filing.send` did not catch
    it, and `_file` recorded the WHOLE filing step as failed.

    Artifacts on disk and a report we could not send are two different
    outcomes, and only one of them needs a person.
    """
    from najamjad_agent.sdk import match_filing

    monkeypatch.setattr("najamjad_agent.reporting.gmail_auth.service_or_none",
                        lambda *_a, **_k: None)

    class Manager:
        def require(self, _key):
            return "someone@example.invalid"

        def get(self, _key, default=None):
            return default

    class Bus:
        def __init__(self):
            self.events = []

        def publish(self, event):
            self.events.append(event)

    bus = Bus()

    assert match_filing._mail_sender(Manager(), bus, {}) is None
    assert bus.events[-1]["event"] == "mail.unavailable"
    assert "authorise_gmail" in bus.events[-1]["reason"], "the fix belongs in the message"
