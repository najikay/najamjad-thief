"""Sealing the rule-53 declaration that opens every mini-game.

Before its first move each side seals a record of what it is playing on —
hardware, LLM model, code version and the git commit — so that neither can
retroactively claim different hardware or different code once the results are
known. `reporting/step_zero.py` has built that payload since the first week and
nothing ever called it, so every log we have filed opened at step 1.

That gap costs more than a missing record. A peer's commit hash and token total
are read off *their* step-0 declaration, so a league where nobody emits one
leaves both sides reporting `github_commit: "unknown"` about each other — which
is what our last six mini-games did.

Hardware and commit are resolved **once, at wiring time**, not per mini-game.
Both shell out, and running a subprocess between mini-games puts it on the path
of a watchdog we have already agreed to. Resolving them at boot also turns a
checkout too broken to name its own commit into a startup warning rather than a
surprise in game four.

Nothing here may raise. A declaration is a record *about* a match, and failing
to describe a game is never a reason not to play it — `EmissionPolicy` raising
inside an argument list is why four artifacts once went unwritten.
"""

from collections.abc import Callable
from typing import Any

from ..constants import Role
from ..domain.game_state import GameState
from ..reporting.step_zero import STEP_ZERO, build_declaration, declaration_is_complete
from ..shared.events import Emit
from ..shared.sysinfo import collect_spec, git_commit

Sealer = Callable[[GameState, Role, int], None]


def declaration_sealer(manager: Any = None, meter: Any = None, emit: Emit | None = None) -> Sealer:
    """Build the per-mini-game sealer, resolving the fixed facts up front."""
    publish = emit or (lambda _event: None)
    spec = _attempt(collect_spec, {})
    commit = _attempt(git_commit, "unknown")
    group = _setting(manager, "game.group_name", "")
    model = _setting(manager, "llm.model", "") or "cli-default"
    opponent = _setting(manager, "network.opponent_group_id", "")

    def seal(state: GameState, role: Role, sub_game: int) -> None:
        """Seal step 0 into this mini-game's fresh ledger, before any move."""
        try:
            declaration = build_declaration(
                group_name=group,
                role=role.value,
                sub_game=sub_game,
                model=model,
                opponent_group=opponent,
                spec=spec,
                commit=commit,
                # The series total *so far*, so the per-game figures a reader
                # derives from consecutive declarations are the game's spend.
                tokens_total=_spent(meter),
            )
            state.ledger.commit(STEP_ZERO, declaration)
        except Exception as error:  # noqa: BLE001 - a record, never a reason not to play
            publish({"event": "step_zero.failed", "error": f"{type(error).__name__}: {error}"})
            return
        for problem in declaration_is_complete(declaration):
            publish({"event": "step_zero.incomplete", "sub_game": sub_game, "problem": problem})

    return seal


def _spent(meter: Any) -> int:
    """Tokens spent on the series before this mini-game, or 0 with no meter."""
    return int(getattr(getattr(meter, "series", None), "spent", 0) or 0)


def _setting(manager: Any, key: str, default: str) -> str:
    """One configured string, tolerating the absence of a manager entirely."""
    return str(manager.get(key, default) or default) if manager else default


def _attempt(probe: Callable[[], Any], fallback: Any) -> Any:
    """Run a hardware or git probe, falling back rather than failing to boot."""
    try:
        return probe()
    except Exception:  # noqa: BLE001 - an unprobeable host still plays matches
        return fallback
