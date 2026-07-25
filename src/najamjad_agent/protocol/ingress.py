"""Parsing untrusted peer messages into a verdict — never into an exception.

Every inbound message crosses this boundary. A validation failure produces a
structured `ParseResult` the caller can log, answer and continue from; nothing
here raises, because a peer must not be able to end our match by sending
nonsense (FR-NET-7).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass
class ParseResult:
    """Outcome of validating one inbound message."""

    model: Any = None
    errors: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when the message is usable."""
        return self.model is not None and not self.errors

    def error_response(self, message_kind: str) -> dict[str, Any]:
        """A structured reply telling the peer exactly what was wrong."""
        return {
            "accepted": False,
            "kind": message_kind,
            "errors": self.errors,
        }


def _describe(error: Mapping[str, Any]) -> str:
    """Render one pydantic error as a peer-readable sentence."""
    location = ".".join(str(part) for part in error.get("loc", ())) or "<root>"
    return f"{location}: {error.get('msg', 'invalid value')}"


def parse_message(model: type[ModelT], raw: Any) -> ParseResult:
    """Validate `raw` against `model`, returning a verdict instead of raising."""
    if not isinstance(raw, dict):
        return ParseResult(errors=[f"<root>: expected an object, got {type(raw).__name__}"])
    try:
        parsed = model.model_validate(raw)
    except ValidationError as error:
        return ParseResult(errors=[_describe(item) for item in error.errors()])
    extras = getattr(parsed, "extras", {})
    return ParseResult(model=parsed, unknown_fields=sorted(extras))
