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


def counted_ledger_check(manager: ConfigManager, sibling: Any = None) -> Callable[[], str | None]:
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

    A missing sibling is *not applicable* rather than a failure: the repos are
    submitted standalone (ADR-002) and a grader unpacking one of them alone must
    not see a red preflight for it.
    """

    def probe() -> str | None:
        """Compare our declared count against the sibling repo's."""
        from ..negotiation.counted_games import DEFAULT_PATH, CountedGames

        here = Path(str(manager.get("paths.counted_games", DEFAULT_PATH) or DEFAULT_PATH))
        root = sibling if sibling is not None else _sibling_repo()
        if root is None or not (root / DEFAULT_PATH).exists():
            return None
        ours, theirs = CountedGames.load(here), CountedGames.load(root / DEFAULT_PATH)
        if sorted(ours.opponents) != sorted(theirs.opponents):
            raise ValueError(
                f"this repo declares {ours.count} counted ({ours.opponents}), "
                f"{root.name} declares {theirs.count} ({theirs.opponents}) — "
                "run scripts/reconcile_counted.py before the match"
            )
        return f"{ours.count} counted, agreed with {root.name}"

    return probe


def _sibling_repo() -> Any:
    """The other half of the pair, when it is checked out beside us."""
    here = Path.cwd()
    for name in ("najamjad-cop", "najamjad-thief"):
        candidate = here.parent / name
        if candidate.is_dir() and candidate.resolve() != here.resolve():
            return candidate
    return None
