"""The result artifact — the one file that decides our league points.

Rule 35 is unforgiving: a missing or contradictory report voids the match for
**both** teams. So this schema is the strictest in the codebase, and every
agreement flag is a required `bool`. `null` is not in the type; a report that
was never actually agreed cannot be built.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schemas_artifacts import ArtifactModel, MutualAgreement


class SubGameRow(ArtifactModel):
    """One mini-game's outcome as reported to the lecturer."""

    sub_game_number: int = Field(ge=1)
    roles: dict[str, str]
    result: str
    winner_group: str | None
    tie: bool
    score: dict[str, int]
    tokens: dict[str, int] = Field(default_factory=dict)
    github_commit: dict[str, str] = Field(default_factory=dict)
    started_at: str = ""
    ended_at: str = ""
    audit: dict[str, bool] = Field(default_factory=dict)


class FinalResult(ArtifactModel):
    """Series totals used for league scoring."""

    total_score: dict[str, int]
    sub_games_won: dict[str, int]
    ties: int = Field(ge=0)
    winner_group: str | None
    series_tie: bool
    #: Mini-games that ended off the board. Distinct from `ties`, because a
    #: technical ending scores 0/0 for both sides and so looks exactly like
    #: a draw without being one.
    technical_endings: int = 0
    tokens_total_series: dict[str, int] = Field(default_factory=dict)
    #: The book's tie score for both teams (PAGE 87, Appendix F: 2). Present
    #: only on a tied series: `aggregate_series` computed it and the schema had
    #: nowhere to put it, so we told the lecturer a series had tied and never
    #: stated the award. Omitted otherwise, because the lecturer's sample —
    #: which was not a tie — does not carry the key, and a null field a grader
    #: does not expect is a different kind of noise.
    tie_award: int | None = None


class ResultArtifact(BaseModel):
    """`result_<game_id>.json` — emailed as an attachment by each team.

    `extra="forbid"`: unlike inbound messages, a stray key here means our own
    builder is wrong, and we would rather fail locally than submit a report the
    grader parses differently from the opponent's.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_documentation_keys(cls, data: Any) -> Any:
        """Ignore `_`-prefixed annotation keys used by the reference artifacts.

        The lecturer's samples carry `_schema` / `_remark` notes for human
        readers. They are documentation, not data — dropping them keeps
        `extra="forbid"` free to catch what it is actually for: a typo in our
        own builder producing a field the grader will not read.
        """
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if not str(key).startswith("_")}
        return data

    schema_version: str = "1.1"
    report_type: str = "final_game_result"
    game_id: str = Field(min_length=1)
    game_uid: str = Field(min_length=1)
    groups: list[str] = Field(min_length=2, max_length=2)
    num_sub_games: int = Field(ge=1)
    sub_games: list[SubGameRow] = Field(min_length=1)
    final_result: FinalResult
    mutual_agreement: MutualAgreement
    #: Every sub-game's config and log, because `links` names only the
    #: first: on a six-game series that pointed a grader at one sixth of
    #: the evidence. Additive, so `links` keeps the shape peers parse.
    all_configs: list[str] = Field(default_factory=list)
    all_logs: list[str] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)
    #: Both teams' repositories, keyed by group id (rule 49). Chapter 9.4 is
    #: explicit that all four links — cop and thief for each side — appear in
    #: the JSON attached to the match-end email, and only the result artifact
    #: is emailed. `links` above holds the sibling *artifact filenames*, which
    #: is a different thing and does not satisfy it.
    #:
    #: The lecturer's sample carries no repository links at all, so this is an
    #: addition rather than parity. Erring toward including a mandated field
    #: the sample omits is the safer direction: a grader looking for the links
    #: finds them, and one parsing by known keys ignores the extra.
    repositories: dict[str, dict[str, str]] = Field(default_factory=dict)
    timezone: str = "Asia/Jerusalem"


def declaration_filename(game_id: str) -> str:
    """`declaration_<game_id>.json` (match level)."""
    return f"declaration_{game_id}.json"


def config_filename(game_id: str, sub_game: int) -> str:
    """`config_<game_id>_g<NN>.json` (per mini-game, zero-padded)."""
    return f"config_{game_id}_g{sub_game:02d}.json"


def log_filename(game_id: str, sub_game: int) -> str:
    """`log_<game_id>_g<NN>.json` (per mini-game, zero-padded)."""
    return f"log_{game_id}_g{sub_game:02d}.json"


def result_filename(game_id: str) -> str:
    """`result_<game_id>.json` (match level) — the emailed attachment."""
    return f"result_{game_id}.json"


def artifact_links(game_id: str, sub_game: int = 1) -> dict[str, str]:
    """The `links` block shared by all four artifacts of one match."""
    return {
        "declaration": declaration_filename(game_id),
        "config": config_filename(game_id, sub_game),
        "log": log_filename(game_id, sub_game),
        "result": result_filename(game_id),
    }
