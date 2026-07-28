"""Shared Gmail doubles.

Extracted so `test_gmail_sender` and `test_gmail_practice` share one fake
rather than two that can drift apart — a second copy of a double is a second
definition of how Gmail behaves, and only one of them gets fixed.
"""

import pytest

from najamjad_agent.shared.gatekeeper import ApiGatekeeper
from najamjad_agent.shared.rate_limits import RateLimitConfig

RECIPIENT = "rmisegal+uoh26finalgame@gmail.com"


class FakeGmail:
    """Mimics the slice of the Gmail API we actually call.

    Parameter names keep Google's camelCase (`userId`) deliberately: a fake that
    renames them would pass while the real call fails.
    """

    def __init__(self, response: dict | None = None, error: Exception | None = None) -> None:
        self.response = {"id": "msg-123"} if response is None else response
        self.error = error
        self.sent: list[dict] = []
        self.drafted: list[dict] = []

    def users(self):
        return self

    def messages(self):
        parent = self

        class Messages:
            def send(self, userId: str, body: dict):  # noqa: N803 - Gmail API spelling
                parent.sent.append({"userId": userId, "body": body})
                return parent

            def execute(self):
                if parent.error:
                    raise parent.error
                return parent.response

        return Messages()

    def drafts(self):
        parent = self

        class Drafts:
            def create(self, userId: str, body: dict):  # noqa: N803 - Gmail API spelling
                parent.drafted.append({"userId": userId, "body": body})
                return parent

            def execute(self):
                if parent.error:
                    raise parent.error
                return parent.response

        return Drafts()

    def execute(self):
        if self.error:
            raise self.error
        return self.response


def _gatekeeper(events: list[dict] | None = None) -> ApiGatekeeper:
    return ApiGatekeeper(
        service="gmail",
        config=RateLimitConfig(requests_per_minute=30, max_retries=2, retry_after_seconds=5),
        emit=(events.append if events is not None else None),
        sleep=lambda _seconds: None,
    )


@pytest.fixture()
def report(tmp_path):
    """A result artifact to attach."""
    path = tmp_path / "result_najamjad-vs-rival.json"
    path.write_text('{"ok": true}', encoding="utf-8")
    return path
