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
        validate_egress(MODELS[kind], payload, kind=kind, alert=self._alert)
        self.workspace.mkdir(parents=True, exist_ok=True)
        path = self.workspace / filename
        path.write_text(canonical_json(payload), encoding="utf-8")
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
    ) -> Path:
        """`log_<game_id>_g<NN>.json` — the sealed chain for replay verification."""
        payload = {
            **self._identity(),
            "summary": summary,
            "records": records,
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
        """`result_<game_id>.json` — the file that is emailed and scored."""
        payload = {
            **self._identity(),
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
