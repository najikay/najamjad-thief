"""Per-opponent quirk profiles — interop as data, never as a code change.

Assignment 6's second-worst cost: every opponent difference became an engine
change under time pressure, and one opponent's unexpected field crashed the
server outright. Here a team's quirks are a profile: tool-name aliases, field
renames, timing preferences, and which optional features they support.

Profiles load from `config/opponents/*.json`, so meeting a new team on match day
is a data file — written while talking to them — not a commit.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OpponentProfile:
    """What we know about how one team's agent behaves."""

    group_id: str
    tool_aliases: dict[str, str] = field(default_factory=dict)
    field_aliases: dict[str, str] = field(default_factory=dict)
    response_timeout_sec: float | None = None
    supports_session_token: bool = False
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OpponentProfile":
        """Build a profile from its JSON form, ignoring unknown keys."""
        known = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in known})

    def tool_for(self, kind: str, default: str) -> str:
        """The tool name this opponent exposes for a message kind."""
        return self.tool_aliases.get(kind, default)

    def outgoing(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Rename our fields to the names this opponent expects."""
        if not self.field_aliases:
            return payload
        return {self.field_aliases.get(key, key): value for key, value in payload.items()}

    def incoming(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Rename their fields back to ours, keeping anything unmapped."""
        if not self.field_aliases:
            return payload
        reverse = {theirs: ours for ours, theirs in self.field_aliases.items()}
        return {reverse.get(key, key): value for key, value in payload.items()}


DEFAULT_PROFILE = OpponentProfile(group_id="default", notes="Reference-compatible behaviour.")


class ProfileRegistry:
    """Loads and selects opponent profiles at handshake time."""

    def __init__(self, profiles: dict[str, OpponentProfile] | None = None) -> None:
        """Start from an in-memory mapping; prefer `load` in production."""
        self._profiles = profiles or {}

    @classmethod
    def load(cls, directory: Path) -> "ProfileRegistry":
        """Read every `*.json` profile from a directory (missing dir is fine)."""
        profiles: dict[str, OpponentProfile] = {}
        if directory.exists():
            for path in sorted(directory.glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                profile = OpponentProfile.from_dict(data)
                profiles[profile.group_id] = profile
        return cls(profiles)

    @property
    def known(self) -> list[str]:
        """Group ids we have a profile for."""
        return sorted(self._profiles)

    def for_opponent(self, group_id: str) -> OpponentProfile:
        """The profile for `group_id`, or reference-compatible defaults.

        An unknown opponent is the normal case, not an error: we play them with
        standard behaviour and write a profile only if they surprise us.
        """
        return self._profiles.get(group_id, DEFAULT_PROFILE)
