"""Runner helpers split from `domain/match` for the file budget.

Two pieces, both with `MatchRunner` as their only caller: the desync healer
(rewind to the window the peer still holds — the mechanism is documented on
the function) and the per-mini-game orchestrator builder.
"""

from __future__ import annotations

from typing import Any

from ..constants import Phase, Role
from .fsm import GameStateMachine
from .game_state import GameState
from .orchestrator import Orchestrator
from .series import plays_window


def ready_orchestrator(runner: Any, state: GameState, fsm: GameStateMachine,
                       role: Role) -> Orchestrator:
    """One conductor per mini-game, with a brain chosen for the role."""
    fsm.to(Phase.WAITING_FOR_OPPONENT)
    return Orchestrator(
        state=state,
        fsm=fsm,
        transport=runner._transport,
        brain=runner._build_brain(role, state),
        speaker=runner._speaker,
        clock=runner._clock,
        emit=runner._emit,
        response_timeout=runner._response_timeout,
        max_retries=runner._max_retries,
    )


def rewind_if_peer_is_behind(runner: Any, sub_game: int) -> bool:
    """Return to a window the peer is demonstrably still offering.

    The desync that killed the anrbj666 friendly of 2026-08-21: our side
    times a dead window out and advances, theirs re-offers it forever, and
    from then on every handshake either side sends names a window the
    other refuses. Ours was at 5 against their 3 — with their window-3
    negotiates arriving the whole time, dropped as mismatches.

    Those mismatches are now *held* by the handshake keyed by the window
    they name (`handshake_setup`), so the peer's true position is
    knowable. When it is behind ours and everything since was a step-0
    technical, rewinding is strictly more truthful than pressing on: the
    held agreement seeds the retried handshake at zero extra round-trips,
    both reports end up carrying the same real game under the same
    number, and rules 33-35 have nothing to void.

    Once per window (`_rewound`), so two peers both running this logic —
    or one peer that truly died on window 3 — still converge on an ended
    series instead of a rewind loop.
    """
    held = getattr(runner._handshake, "held_agreements", None)
    if held is None:
        held = {}
    rewound: set[int] = runner._rewound if hasattr(runner, "_rewound") else set()
    runner._rewound = rewound
    ours = runner.tracker.our_role
    for window in sorted(w for w in held if 0 < w < sub_game):
        usable = (
            (ours is None or plays_window(window, runner.first_role, ours))
            and window not in rewound
            and runner.tracker.rewind_to(window)
        )
        if not usable:
            # Purged, not kept: a held window we cannot return to — the
            # sibling's, one already rewound to once, or one with a real
            # result behind it — would otherwise re-trigger the early
            # abort in `agree_on_terms` on every later window and eat the
            # sixteen-minute patience that was itself a hard-won fix.
            held.pop(window, None)
            continue
        rewound.add(window)
        runner.games = [g for g in runner.games if int(g.get("sub_game", 0)) < window]
        for spent in [k for k in runner._attempts if k >= window]:
            runner._attempts.pop(spent, None)
        runner._emit({"event": "series.rewound", "to": window, "from": sub_game})
        return True
    return False

