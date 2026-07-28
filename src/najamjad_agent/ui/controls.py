"""The few actions a dashboard is allowed to take (T-1820, T-1821).

Two rules shape this module, and the second is the interesting one.

**Server-driven state.** A control returns the state the server now holds, and
the page re-renders from that. It never assumes the action worked and paints the
result optimistically — a button that shows "serving" while the server failed to
bind is worse than no button, because the operator stops checking.

**Not everything belongs behind a button.** Serving and stopping are safe and
reversible. *Playing a counted match* is not: it is graded, it cannot be undone,
and `docs/RUNBOOK.md` is the interface for it. The line is drawn at reversible.

Negotiation approval is here for the opposite reason — FR-NEG-4 requires a human
to approve terms before they are signed, and a rule that says "a person decides"
is badly served by a command line nobody is watching.

Controls are **off unless `features.controls` is true** in `config/setup.json`.
A dashboard is loopback-only, but a disabled-by-default write path is one fewer
thing to reason about on match day.
"""

from __future__ import annotations

from typing import Any


class ControlDeniedError(RuntimeError):
    """The action is not permitted in this configuration."""


def controls_enabled(sdk: Any = None) -> bool:
    """Whether write actions are allowed at all.

    Read off the SDK, not out of a config file. The UI package may reach the
    agent **only** through the SDK facade (ADR-005), and a meta-test enforces
    it — the first version of this module imported `shared.app_config` directly
    and was caught by that test, correctly.
    """
    return bool(getattr(sdk, "controls_enabled", False))


def peer_state(sdk: Any) -> dict[str, Any]:
    """What the server currently believes about serving.

    Read from the SDK rather than remembered here, so the panel cannot drift
    from the process it is describing.
    """
    actions = sdk.actions
    return {
        "serving": bool(getattr(sdk, "ready", False)),
        "public_url": str(getattr(actions, "public_url", "") or ""),
        "controls_enabled": controls_enabled(sdk),
    }


def start_peer(sdk: Any, tunnel: bool = False, dashboard: bool = False) -> dict[str, Any]:
    """Begin serving; returns the state afterwards, not a promise about it."""
    _require_enabled(sdk)
    sdk.actions.start_peer(with_tunnel=tunnel, with_dashboard=dashboard)
    return peer_state(sdk)


def stop_peer(sdk: Any) -> dict[str, Any]:
    """Stop serving. Safe because it is reversible and costs no graded action.

    It also stops the tunnel, which matters: an unstopped tunnel points a public
    name at a dead port, and an opponent reads that as us being unreachable
    rather than stopped.
    """
    _require_enabled(sdk)
    sdk.actions.stop_peer()
    return peer_state(sdk)


def negotiation_state(sdk: Any) -> dict[str, Any]:
    """The draft terms awaiting a human, and how we got here (FR-NEG-4)."""
    return {
        "timeline": sdk.negotiation_timeline(),
        "controls_enabled": controls_enabled(sdk),
        "awaiting_approval": _awaiting(sdk),
    }


def approve_terms(sdk: Any, terms: dict[str, Any], identity: dict[str, Any] | None = None
                  ) -> dict[str, Any]:
    """Sign terms a person has read.

    The terms are passed back in rather than taken from the server's draft on
    purpose: approving means approving *what was shown*, and a draft that
    changed between rendering and clicking must not be signed by that click.
    """
    _require_enabled(sdk)
    if not terms:
        raise ControlDeniedError("nothing to approve — the draft was empty")
    sdk.actions.approve_terms(terms, identity)
    return negotiation_state(sdk)


def _awaiting(sdk: Any) -> bool:
    """Whether a proposal is sitting unanswered."""
    timeline = sdk.negotiation_timeline()
    if not timeline:
        return False
    last = timeline[-1]
    return str(last.get("action", "")) in {"proposed", "countered", "received"}


def _require_enabled(sdk: Any) -> None:
    """Refuse every write path unless the operator turned them on."""
    if not controls_enabled(sdk):
        raise ControlDeniedError(
            "controls are disabled; set features.controls in config/setup.json to enable them"
        )
