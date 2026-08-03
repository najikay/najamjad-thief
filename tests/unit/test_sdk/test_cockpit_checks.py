"""The readiness panel must show the checks preflight actually ran (T-2449).

It showed `checks: 0` for weeks with a full green preflight one terminal away.
`cockpit()` read `getattr(report, "checks", None) or []`, and `PreflightReport`
has never had a `checks` attribute — it has `results`. The default swallowed the
mistake, so the panel was always empty and never wrong-looking.

Every test here would have failed against that code. The old ones did not,
because they only ever exercised the path where preflight produced no report at
all — the one path where an empty list is the right answer.
"""

from typing import Any

from najamjad_agent.net.preflight import CheckResult, PreflightReport
from najamjad_agent.sdk.sdk import AgentSdk


class Recorder:
    """An event bus that keeps what was published."""

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def publish(self, event: dict[str, Any]) -> None:
        self.published.append(event)


def cockpit_with(report: Any, events: Any = None) -> dict[str, Any]:
    """Drive the real `cockpit()` over a stand-in whose preflight we control."""

    class Actions:
        public_url = "https://cop.example.com/mcp"
        last_artifacts: dict[str, str] = {}

        def preflight(self) -> Any:
            if isinstance(report, Exception):
                raise report
            return report

    class Sdk:
        ready = True
        actions = Actions()
        _events = events

        def provider(self) -> dict[str, Any]:
            return {"active": "template"}

        def budget(self) -> dict[str, Any]:
            return {"used": 0}

        def practice(self) -> dict[str, Any]:
            return {"enabled": False, "redirect_to": "", "banner": ""}

        _emit_cockpit_failure = AgentSdk._emit_cockpit_failure

    return AgentSdk.cockpit(Sdk())  # type: ignore[arg-type]


def test_the_panel_lists_every_check_preflight_ran() -> None:
    report = PreflightReport([
        CheckResult("tunnel", "ok", "reachable"),
        CheckResult("gmail", "ok", "token valid"),
        CheckResult("opponent tools", "failed", "missing receive_control"),
    ])

    body = cockpit_with(report)

    assert len(body["checks"]) == 3, "an empty panel with a red preflight reads as ready"
    assert [check["name"] for check in body["checks"]] == ["tunnel", "gmail", "opponent tools"]


def test_a_failing_check_reaches_the_panel_as_failing() -> None:
    """The panel is where a red line has to be visible; it is the whole point."""
    report = PreflightReport([CheckResult("opponent tools", "failed", "502")])

    check = cockpit_with(report)["checks"][0]

    assert check["passed"] is False
    assert check["detail"] == "502"


def test_a_skipped_check_is_not_reported_as_failing() -> None:
    """`SKIPPED` means not applicable; painting it red teaches the operator to ignore red."""
    report = PreflightReport([CheckResult("gmail", "skipped", "not applicable")])

    assert cockpit_with(report)["checks"][0]["passed"] is True


def test_the_verdict_matches_the_checks_beside_it() -> None:
    report = PreflightReport([CheckResult("tunnel", "failed", "no response")])

    body = cockpit_with(report)

    assert body["exit_code"] == 1
    assert not body["checks"][0]["passed"]


def test_a_preflight_that_blew_up_says_so_instead_of_showing_nothing() -> None:
    """"Nothing to check" and "the run died" must not look identical."""
    events = Recorder()

    body = cockpit_with(RuntimeError("no config loaded"), events=events)

    assert body["checks"] == []
    assert body["exit_code"] is None, "no report means no verdict, not a pass"
    failure = [event for event in events.published if event["event"] == "cockpit.preflight_failed"]
    assert failure and failure[0]["detail"] == "no config loaded"
