"""Writing the four lifecycle artifacts the lecturer receives.

Every write goes through `validate_egress`, so an artifact that fails its schema
is never written at all — it raises an operator alert instead. That ordering is
the point: Assignment 6 built payloads and sent them as two unrelated acts, and
a `null` where a boolean belonged reached the lecturer.

Files land in the match workspace (`matches/<opponent>/`) under the names the
book fixes, so a match can be reconstructed from its folder alone.
"""

from pathlib import Path
from typing import Any

from ..protocol.canonical import canonical_json
from ..protocol.egress import validate_egress
from ..protocol.schemas_artifacts import (
    ConfigArtifact,
    DeclarationArtifact,
    LogArtifact,
)
from ..protocol.schemas_report import (
    ResultArtifact,
    artifact_links,
    config_filename,
    declaration_filename,
    log_filename,
    result_filename,
)
from .agreement import agreement_block

MODELS: dict[str, Any] = {
    "declaration": DeclarationArtifact,
    "config": ConfigArtifact,
    "log": LogArtifact,
    "result": ResultArtifact,
}


#: Fields that mean "not applicable" when null and should simply not appear.
#: Deliberately a *named list* rather than a blanket `exclude_none`: some nulls
#: carry meaning and must survive. `winner_group: null` is the report's own way
#: of saying a mini-game was drawn, and dropping it would turn a stated draw
#: into a missing field the opponent's report contradicts.
OMIT_WHEN_NULL = frozenset({"tie_award", "step_budget", "opponent_group_id"})


def _without_absent(payload: Any) -> Any:
    """Drop `OMIT_WHEN_NULL` keys whose value is null, at any depth.

    `"tie_award": null` was appearing in every emitted result, including the
    ones that were not ties, because the schema default is None and dumping the
    *model* (which we do deliberately, so `schema_version` and friends survive)
    re-adds every default the builder had omitted.
    """
    if isinstance(payload, dict):
        return {
            key: _without_absent(value)
            for key, value in payload.items()
            if not (value is None and key in OMIT_WHEN_NULL)
        }
    if isinstance(payload, list):
        return [_without_absent(item) for item in payload]
    return payload


class ArtifactWriter:
    """Builds, validates and persists one match's artifacts."""

    def __init__(
        self,
        workspace: Path,
        game_id: str,
        game_uid: str,
        groups: tuple[str, str],
        alert: Any = None,
    ) -> None:
        """Bind the writer to one match and its output folder."""
        self.workspace = workspace
        self.game_id = game_id
        self.game_uid = game_uid
        self.groups = groups
        self._alert = alert

    def _write(self, kind: str, payload: dict[str, Any], filename: str) -> Path:
        """Validate then persist — never the other way round."""
        parsed = validate_egress(MODELS[kind], payload, kind=kind, alert=self._alert)
        self.workspace.mkdir(parents=True, exist_ok=True)
        path = self.workspace / filename
        # The **validated model**, not the raw payload. Fields the schema
        # supplies by default — `schema_version`, `report_type`, `timezone` —
        # exist only on the model, so writing the payload silently dropped every
        # one of them from the file we email. The grader reads the file.
        path.write_text(
            canonical_json(_without_absent(parsed.model_dump(mode="json"))), encoding="utf-8"
        )
        return path

    def _identity(self) -> dict[str, Any]:
        """Fields every artifact carries so files can never be mixed up."""
        return {
            "game_id": self.game_id,
            "game_uid": self.game_uid,
            "links": artifact_links(self.game_id),
        }

    def write_declaration(self, groups_block: dict[str, Any], **extra: Any) -> Path:
        """`declaration_<game_id>.json` — the whole match's fixed facts."""
        payload = {**self._identity(), "groups": groups_block, **extra}
        return self._write("declaration", payload, declaration_filename(self.game_id))

    def write_config(self, sub_game: int, terms: dict[str, Any], config_sha256: str) -> Path:
        """`config_<game_id>_g<NN>.json` — the locked terms for one mini-game."""
        payload = {
            **self._identity(),
            "sub_game_number": sub_game,
            "agreed_between": sorted(self.groups),
            "config_sha256": config_sha256,
            "config_name": config_filename(self.game_id, sub_game),
            **terms,
        }
        return self._write("config", payload, config_filename(self.game_id, sub_game))

    def write_log(
        self,
        sub_game: int,
        summary: dict[str, Any],
        records: list[dict[str, Any]],
        opponent_group_id: str,
        confirmed: bool,
        sub_games: list[dict[str, Any]],
        opponent_records: list[dict[str, Any]] | None = None,
    ) -> Path:
        """`log_<game_id>_g<NN>.json` — the sealed chain for replay verification."""
        payload = {
            **self._identity(),
            "summary": summary,
            "records": records,
            "opponent_records": list(opponent_records or []),
            "mutual_agreement": agreement_block(
                self.game_id, self.game_uid, self.groups, sub_games, opponent_group_id, confirmed
            ),
        }
        return self._write("log", payload, log_filename(self.game_id, sub_game))

    def write_result(
        self,
        sub_games: list[dict[str, Any]],
        final_result: dict[str, Any],
        opponent_group_id: str,
        confirmed: bool,
        **extra: Any,
    ) -> Path:
        """`result_<game_id>.json` — the file that is emailed and scored.

        The `links` block inherited from `_identity` names `..._g01.json` for the
        config and the log, because it defaults to sub-game 1. On a six-game
        series that is a graded file pointing a grader at one sixth of the
        evidence. `all_logs` / `all_configs` name every one; `links` keeps its
        original shape so an opponent's parser sees exactly what it always did.
        """
        numbers = [int(game.get("sub_game_number", index)) for index, game in enumerate(sub_games, 1)]
        payload = {
            **self._identity(),
            "all_configs": [config_filename(self.game_id, number) for number in numbers],
            "all_logs": [log_filename(self.game_id, number) for number in numbers],
            "groups": sorted(self.groups),
            "num_sub_games": len(sub_games),
            "sub_games": sub_games,
            "final_result": final_result,
            "mutual_agreement": agreement_block(
                self.game_id, self.game_uid, self.groups, sub_games, opponent_group_id, confirmed
            ),
            **extra,
        }
        return self._write("result", payload, result_filename(self.game_id))
