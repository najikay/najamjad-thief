"""Turning a finished series into its artifacts, wired to real configuration.

Split out of `bootstrap` because it is a decision rather than wiring: which
group ids the file is keyed by, which shape of the agreement each artifact
records, and where the files land. Bootstrap says *that* a match is filed; this
says *what* gets written.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_filer(manager: Any, bus: Any, session: dict, actions: Any) -> Any:
    """Turn a finished series into its four artifacts, and send the result."""
    from ..negotiation.contract import contract_hash, derive_game_ids
    from ..reporting.filing import MatchFiler

    def file_match(games, outcomes, result) -> None:
        """Called once, after the last mini-game."""
        ours = str(manager.get("game.group_id", "najamjad"))
        peer = session.get("peer") or {}
        theirs = str((peer.get("identity") or {}).get("group_id", "opponent"))
        terms = session.get("terms") or {}
        game_id, game_uid = derive_game_ids(terms, ours, theirs)
        filer = MatchFiler(
            workspace=Path(str(manager.get("paths.artifacts", "workspace/artifacts"))),
            game_id=game_id,
            game_uid=game_uid,
            groups=(ours, theirs),
            sender=None,
            emit=bus.publish,
            rename={str(manager.get("network.opponent_group_id", "them")): theirs},
        )
        # Two different shapes of the same agreement, deliberately. The
        # *signature* is over the flat terms both peers exchanged; the *config
        # artifact* records them in our sectioned form, which is what the
        # artifact schema and a human reader expect.
        written = filer.file_match(
            games, outcomes, result, _config_body(manager), contract_hash(terms),
            groups_block={ours: session.get("identity") or {},
                          theirs: peer.get("identity") or {}},
        )
        actions.last_artifacts = written

    return file_match


def _config_body(manager: Any) -> dict[str, Any]:
    """The agreed terms as the config artifact records them."""
    return {
        section: dict(manager.section(section))
        for section in ("board_and_agents", "movement_and_barriers", "scoring", "pheromones")
    }
