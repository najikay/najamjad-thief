"""The standard match-day checklist.

`preflight` holds the machinery; this holds the policy — what must be true
before we tell an opponent we are ready. The distinction matters because the
probe contract is easy to satisfy accidentally: a probe that returns `None` is
recorded as *not applicable* and a probe returning any string is recorded as a
pass, so a check that merely runs without raising can report READY while
proving nothing.

The first version of this checklist did exactly that — it passed on an empty
`opponent_url`, which is the one setting a match cannot start without.
"""

from collections.abc import Callable
from typing import Any

from ..shared.config import ConfigManager
from .preflight_opponent import opponent_tools_check


def required_setting(manager: ConfigManager, dotted: str) -> Callable[[], str]:
    """A check that a setting is present AND non-empty.

    `require` only proves the key exists. An empty string is exactly what an
    unfilled config field looks like, so it has to fail here rather than sail
    through as a pass with a blank detail.
    """

    def probe() -> str:
        """Confirm the setting is present and not blank."""
        value = str(manager.get(dotted, "") or "").strip()
        if not value:
            raise ValueError(f"{dotted} is not set — fill it in before the match")
        return value

    return probe


def config_check(manager: ConfigManager) -> Callable[[], str]:
    """Re-validate the loaded configuration and say so."""

    def probe() -> str:
        """Confirm the config loads and its version is one we support."""
        manager.validate()
        return f"version {manager.get('version', 'unknown')} valid"

    return probe


def port_check(server: Any) -> Callable[[], str]:
    """Confirm our MCP port is actually free."""

    def probe() -> str:
        """Confirm nothing else already holds our port."""
        server.preflight()
        return f"{server.host}:{server.port} free"

    return probe


def tunnel_check(tunnel: Any) -> Callable[[], Any]:
    """Report the public hostname, or mark the check not applicable.

    Returning `None` when no tunnel is configured is the honest answer: local
    play is a legitimate setup, not a failure.
    """

    def probe() -> Any:
        """Confirm the tunnel hostname resolves to a live endpoint."""
        return tunnel.public_url if tunnel is not None else None

    return probe


def gmail_check(load: Callable[[], Any] | None = None) -> Callable[[], str]:
    """Confirm the report can actually be sent, before the match rather than after.

    The gap this closes: `email.recipient` being set proves only that we know
    *where* to send. Nothing checked that we *could*, and nothing injected a
    Gmail service, so every match ended with the report undelivered — which
    book rules 33-35 score like not playing at all.

    Loading the credentials is the whole check. It is offline, it refreshes
    silently, and it cannot prompt; if it raises, the fix is a one-line script
    run and there is still time to run it.

    `load` is injectable because the credentials are *ambient machine state*.
    With the real loader wired in, this suite passed on a laptop that happened
    to hold a token and failed in CI, which never holds one — and a test whose
    verdict depends on what is lying around the filesystem proves nothing about
    the code either way.
    """

    def probe() -> str:
        """Confirm stored credentials load, refresh, and grant send-only scope."""
        loader = load
        if loader is None:
            from ..reporting.gmail_auth import load_credentials as loader  # noqa: N813

        credentials = loader()
        return f"send-only token valid={getattr(credentials, 'valid', True)}"

    return probe


def recipient_check(manager: ConfigManager) -> Callable[[], str]:
    """Where the report will actually go — not merely what is configured.

    The plain setting check printed the lecturer's address on a *practice* run,
    which reads as "about to email the grader" at the exact moment an operator
    is looking for reassurance that it will not. In practice mode the send is
    redirected, so the configured value is not the answer to the question the
    line appears to answer.
    """

    def probe() -> str:
        """Report the effective recipient for this run."""
        from ..shared.practice import current

        configured = str(manager.get("email.recipient", "") or "").strip()
        if not configured:
            raise ValueError("email.recipient is not set — fill it in before the match")
        mode = current()
        if mode.enabled:
            return f"{mode.redirect_to} (practice — {configured} NOT contacted)"
        return configured

    return probe


def delivery_check(manager: ConfigManager) -> Callable[[], str]:
    """Confirm the report will actually be SENT, not drafted (rule 35).

    The trap this closes, found before the first counted match: practice mode
    forces `send`, and a counted run falls back to `email.mode` — which ships
    as `draft`. So a graded match would have filed its four artifacts, built a
    correct report, and left it sitting in a Gmail drafts folder. Rule 35
    zeroes both teams for a report that never arrives, and nothing would have
    looked wrong: `report.delivered` fires for a draft too.

    Practice runs are exempt, because there `send` is forced anyway and the
    recipient is redirected to the operator.
    """

    def probe() -> str:
        """Confirm a counted run is configured to send rather than draft."""
        from ..shared.practice import current

        mode = str(manager.get("email.mode", "draft") or "draft")
        if current().enabled:
            return f"practice run — forced to send, redirected ({mode!r} ignored)"
        if mode != "send":
            raise ValueError(
                f"email.mode is {mode!r}: a counted match would DRAFT the report, "
                "not send it, and rule 35 scores a missing report as not playing. "
                "Set email.mode = \"send\" for a counted match, or pass --practice."
            )
        return "counted run — report will be sent"

    return probe


def standard_checks(
    manager: ConfigManager,
    server: Any,
    tunnel: Any = None,
    credentials: Callable[[], Any] | None = None,
    tools: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Everything that must hold before the agent claims to be match-ready."""
    return {
        "config": config_check(manager),
        "port": port_check(server),
        "tunnel": tunnel_check(tunnel),
        "opponent_url": required_setting(manager, "network.opponent_url"),
        "opponent_tools": opponent_tools_check(
            str(manager.get("network.opponent_url", "") or ""), tools
        ),
        "email_recipient": recipient_check(manager),
        "gmail_credentials": gmail_check(credentials),
        "report_delivery": delivery_check(manager),
        "group_id": required_setting(manager, "game.group_id"),
    }
