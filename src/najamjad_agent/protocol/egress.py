"""The egress gate — nothing invalid leaves this process.

Assignment 6 shipped reports with `agreement: null` because building a payload
and sending it were two unrelated acts. Here they are not: every artifact write
and every email send funnels through `validate_egress`, which refuses anything
that fails its schema and raises an operator alert instead of quietly sending
a report that would void the match for both teams (rule 35).

A meta-test asserts no send path bypasses this module.
"""

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)

# Fields whose truthfulness the whole report depends on. They must be real
# booleans — `null`, "true" or a missing key are all refused.
#
# Scoped per artifact kind: only the log and the result carry an agreement
# block. Demanding one on a declaration or config would block a perfectly valid
# write, and a gate that cries wolf is a gate people switch off.
REQUIRED_BOOLEAN_PATHS: dict[str, tuple[tuple[str, ...], ...]] = {
    "result": (("mutual_agreement", "confirmed"),),
    "log": (("mutual_agreement", "confirmed"),),
    "probe": (("mutual_agreement", "confirmed"),),
}


class EgressBlockedError(Exception):
    """Raised when an outbound payload fails validation. Never suppress."""

    def __init__(self, kind: str, problems: list[str]) -> None:
        """Name the artifact and every reason it was refused."""
        super().__init__(f"{kind} blocked before sending: {'; '.join(problems)}")
        self.kind = kind
        self.problems = problems


def _boolean_problems(payload: dict[str, Any], kind: str) -> list[str]:
    """Check the agreement flags that A6 shipped as null, for this artifact kind."""
    problems: list[str] = []
    for path in REQUIRED_BOOLEAN_PATHS.get(kind, ()):
        node: Any = payload
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        dotted = ".".join(path)
        if node is None:
            problems.append(f"{dotted} is null or missing; it must be a real boolean")
        elif not isinstance(node, bool):
            problems.append(f"{dotted} is {type(node).__name__}, expected bool")
    return problems


def validate_egress(
    model: type[ModelT],
    payload: dict[str, Any],
    kind: str,
    alert: Callable[[dict], None] | None = None,
) -> ModelT:
    """Validate an outbound payload or refuse to let it leave.

    Returns the parsed model on success. On failure it emits an operator alert
    and raises `EgressBlockedError` — the send never happens.
    """
    problems: list[str] = []
    parsed: ModelT | None = None
    try:
        parsed = model.model_validate(payload)
    except ValidationError as error:
        for item in error.errors():
            location = ".".join(str(part) for part in item.get("loc", ())) or "<root>"
            problems.append(f"{location}: {item.get('msg', 'invalid value')}")
    problems.extend(_boolean_problems(payload, kind))
    if problems or parsed is None:
        if alert is not None:
            alert({"event": "egress.blocked", "kind": kind, "problems": problems})
        raise EgressBlockedError(kind, problems)
    return parsed


def egress_is_valid(model: type[ModelT], payload: dict[str, Any]) -> bool:
    """Non-raising probe used by the dashboard's pre-send readiness check."""
    try:
        validate_egress(model, payload, kind="probe")
    except EgressBlockedError:
        return False
    return True
