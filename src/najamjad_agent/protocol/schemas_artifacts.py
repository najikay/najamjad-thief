"""Schemas for the four lifecycle artifacts the lecturer receives.

`declaration_<game_id>.json`, `config_<game_id>_g<NN>.json`,
`log_<game_id>_g<NN>.json`, `result_<game_id>.json` — all sharing one
`game_uid` so files from different matches can never be conflated.

**The `mutual_agreement` block is the point of this module.** In Assignment 6
that field went out as `null` and the report was worthless. Here `confirmed` is
a plain `bool` with no default and no `None` in its type: a report that has not
actually been agreed cannot be constructed, let alone sent.

Shapes mirror the lecturer's own sample artifacts (`tests/goldens/artifacts/`),
which are the authoritative schema — the book names these files but does not
reproduce them.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ArtifactModel(BaseModel):
    """Base for artifacts: tolerant of the samples' documentation keys."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class MutualAgreement(BaseModel):
    """Both teams' confirmation that they agree on the result.

    `confirmed` is intentionally a required, non-optional bool — the single
    strongest guard against repeating A6's `agreement: null` report.
    """

    model_config = ConfigDict(extra="allow")

    sha256: str = Field(min_length=64, max_length=64)
    confirmed: bool
    opponent_group_id: str = ""


class HardwareSpec(ArtifactModel):
    """Machine declaration used for the computational-fairness bonus."""

    cpu_type: str
    cpu_cores: int = Field(ge=1)
    ram_gb: float = Field(gt=0)
    cpu_freq_mhz: int | None = None
    gpu_model: str = ""
    vram_gb: float | None = None


class GroupDeclaration(ArtifactModel):
    """One team's identity, repos, endpoints and hardware."""

    group_id: str
    group_name: str
    members: list[str]
    repos: dict[str, str]
    mcp_servers: dict[str, str] = Field(default_factory=dict)
    llm_model: str = ""
    hardware_spec: HardwareSpec | None = None
    signature: str = ""


class DeclarationArtifact(ArtifactModel):
    """Pre-game declaration covering the whole match."""

    schema_version: str = "1.1"
    declaration_type: str = "pre_game_declaration"
    game_id: str
    game_uid: str
    groups: dict[str, GroupDeclaration]
    links: dict[str, str] = Field(default_factory=dict)
    timezone: str = "Asia/Jerusalem"
    game_started_at: str = ""
    game_ended_at: str = ""
    num_sub_games: int = Field(default=6, ge=1)
    max_tokens_per_game: int = Field(default=200000, ge=0)


class ConfigArtifact(ArtifactModel):
    """The agreed, cryptographically locked terms for one mini-game."""

    schema_version: str = "1.1"
    game_id: str
    game_uid: str
    sub_game_number: int = Field(ge=1)
    agreed_between: list[str]
    board_and_agents: dict[str, Any]
    movement_and_barriers: dict[str, Any]
    scoring: dict[str, Any]
    pheromones: dict[str, Any]
    config_sha256: str = Field(min_length=64, max_length=64)
    config_name: str = ""


class AuditSummary(ArtifactModel):
    """Outcome of the mutual audit for one mini-game."""

    passed: bool
    verified_steps: int = Field(default=0, ge=0)
    failed_steps: list[int] = Field(default_factory=list)


class LogSummary(ArtifactModel):
    """Header block of a mini-game log."""

    sub_game_number: int = Field(ge=1)
    group_id: str
    role: str
    opponent_group_id: str
    result: str
    winner_role: str = ""
    steps: int = Field(default=0, ge=0)
    started_at: str = ""
    ended_at: str = ""
    tokens_total: int = Field(default=0, ge=0)
    audit: AuditSummary


class LogArtifact(ArtifactModel):
    """Full mini-game log enabling independent replay verification."""

    schema_version: str = "1.1"
    game_id: str
    game_uid: str
    summary: LogSummary
    records: list[dict[str, Any]] = Field(min_length=1)
    mutual_agreement: MutualAgreement
    links: dict[str, str] = Field(default_factory=dict)
