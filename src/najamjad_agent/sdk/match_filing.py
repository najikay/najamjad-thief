"""Turning a finished series into its artifacts, wired to real configuration.

Split out of `bootstrap` because it is a decision rather than wiring: which
group ids the file is keyed by, which shape of the agreement each artifact
records, and where the files land. Bootstrap says *that* a match is filed; this
says *what* gets written.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..shared.app_config import setting


def build_filer(manager: Any, bus: Any, session: dict, actions: Any,
                setup: dict | None = None) -> Any:
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
            workspace=Path(setting(setup or {}, "paths.artifacts", "workspace/artifacts")),
            game_id=game_id,
            game_uid=game_uid,
            groups=(ours, theirs),
            sender=_mail_sender(manager, bus, setup or {}),
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
        # Filing and sending are separate steps on purpose: the artifacts are
        # on disk and recoverable even when the mail fails, and rule 35 cares
        # that the report goes — so a failure here is loud rather than silent.
        filer.send(written["result"])

    return file_match


def _config_body(manager: Any) -> dict[str, Any]:
    """The agreed terms as the config artifact records them."""
    return {
        section: dict(manager.section(section))
        for section in ("board_and_agents", "movement_and_barriers", "scoring", "pheromones")
    }


def _mail_sender(manager: Any, bus: Any, setup: dict) -> Any:
    """A Gmail sender when credentials are present, otherwise None.

    Built lazily and defensively. A match must not fail because the mailbox is
    unauthorised — the artifacts are already on disk and can be sent by hand —
    so the absence is reported as an event and the series still closes cleanly.

    `email.mode` stays `draft` until a counted match: a draft is recoverable, a
    wrongly-addressed send is not. Practice mode is passed down rather than
    applied here, so the redirect and its guard live at the point of no return
    instead of at one of the several places a sender can be constructed. It is
    read fresh (`current()`) rather than from the captured `setup`: the switch
    must reflect the operator's most recent decision, not the value that
    happened to be on disk when the process booted.
    """
    from ..reporting.gmail_sender import GmailSender
    from ..shared.gatekeeper import ApiGatekeeper
    from ..shared.practice import current
    from ..shared.rate_limits import for_service, load_rate_limits

    try:
        limits = load_rate_limits(
            Path(setting(setup, "paths.rate_limits", "config/rate_limits.json"))
        )
        return GmailSender(
            gatekeeper=ApiGatekeeper(service="gmail", config=for_service(limits, "gmail"),
                                     emit=bus.publish),
            recipient=str(manager.require("email.recipient")),
            mode=str(manager.get("email.mode", "draft")),
            emit=bus.publish,
            dead_letter_dir=Path(setting(setup, "paths.dead_letters", "workspace/dead_letters")),
            practice=current(),
        )
    except Exception as error:  # noqa: BLE001 - reported, never fatal to a match
        bus.publish({"event": "mail.unavailable", "reason": f"{type(error).__name__}: {error}"})
        return None
