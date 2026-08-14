"""Do both halves of the pair declare the same counted-match count?

Its own module for the same reason `preflight_tunnel` and `preflight_opponent`
are: `preflight_checks.py` holds the checklist, and `net/` modules are capped at
150 lines *including* their docstrings, so a check that needs its reasoning
written down cannot live there.

Rules 37-38 make this figure a declaration, and rule 38 judges it on mutual
consistency between the two teams' files. Ours could not even be consistent with
itself.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..shared.config import ConfigManager


def counted_ledger_check(manager: ConfigManager, sibling: Any = None) -> Callable[[], str]:
    """Confirm both repos would declare the same counted-match count (rules 37-38).

    A series is played from **one** repo — whichever role we open on — and only
    that repo's tracker is written at settlement. So the count silently drifts
    apart: on 2026-08-14 `najamjad-cop` still declared 1 while `najamjad-thief`
    declared 2, having played both counted series. Opening the next series as
    cop would have told that opponent we had one counted match, contradicting
    imreeyal's already-filed artifact — and rule 38 judges this figure on
    exactly that mutual consistency.

    It reports the divergence and never repairs it. `scripts/reconcile_counted.py`
    does the merge, with each entry checked against the archives first, because a
    number that disqualifies a team for being wrong should not be changed by a
    check that runs automatically before every match.

    **With no sibling it still reports the figure, and that is the point.** The
    first version returned `None` here, which `run_preflight` records as *not
    applicable* — and CI, which checks out one repo, went red on
    `test_every_check_actually_proves_something`. That test was right and the
    check was wrong. Only `tunnel` may prove nothing, and a check that goes
    quiet in exactly the environment it is not run in is decoration. Reading the
    ledger and naming the count we are about to declare proves something on its
    own; the cross-repo comparison is an extra assertion on top, not the only
    one. It is also what an operator actually wants to see on the line above
    "READY" — the number that is about to go out on the wire.
    """

    def probe() -> str:
        """Report our declared count, and compare it against the sibling's."""
        from ..negotiation.counted_games import DEFAULT_PATH, CountedGames

        here = Path(str(manager.get("paths.counted_games", DEFAULT_PATH) or DEFAULT_PATH))
        ours = CountedGames.load(here)
        summary = f"declaring {ours.count} counted ({', '.join(ours.opponents) or 'none'})"
        root = sibling if sibling is not None else _sibling_repo()
        if root is None or not (root / DEFAULT_PATH).exists():
            return f"{summary} — no sibling repo beside us to cross-check"
        theirs = CountedGames.load(root / DEFAULT_PATH)
        if sorted(ours.opponents) != sorted(theirs.opponents):
            raise ValueError(
                f"this repo declares {ours.count} counted ({ours.opponents}), "
                f"{root.name} declares {theirs.count} ({theirs.opponents}) — "
                "run scripts/reconcile_counted.py before the match"
            )
        return f"{summary}, agreed with {root.name}"

    return probe


def _sibling_repo() -> Any:
    """The other half of the pair, when it is checked out beside us."""
    here = Path.cwd()
    for name in ("najamjad-cop", "najamjad-thief"):
        candidate = here.parent / name
        if candidate.is_dir() and candidate.resolve() != here.resolve():
            return candidate
    return None
