"""One report per team, from two processes that each saw half the series.

Book Appendix ה Table 7 rule 1 puts the cop's code and the thief's code in two
completely separate processes. A series still alternates roles across its six
mini-games, so neither process witnesses more than three of them — but rules
33-35 want **one** report per team describing all six, and score a missing or
self-contradictory one as not having played at all.

So the halves are rejoined here, and the rules that govern how are the reason
this is a module rather than four lines in the filer:

* **Only one process files.** Whichever holds the last window does it, because
  it is the one still running when the series ends. The other writes its half
  and exits quietly. Both filing would put two reports on one series, which is
  the contradiction rules 33-35 void.
* **The rejoin happens after play, never during it.** Rule 2 forbids sharing
  memory or variables between the two sides — the concern being a back door
  onto the opponent's local truth. What crosses here is a finished record of
  games that are already over, written to disk by a process that has stopped
  playing, read by one whose own games are done. No live state, no channel
  between two agents that are mid-game.
* **A missing half is loud and never silently dropped.** Filing three games as
  though they were six would understate the series in our own report while the
  opponent's names all six — exactly the mismatch that voids both.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..constants import EndReason, Role
from ..domain.match_record import now_iso
from ..domain.scoring import ScoreTable
from ..domain.series import SeriesTracker, SubGameOutcome, role_for, split_roles
from ..protocol.canonical import canonical_json
from ..shared.events import Emit

#: Where a process leaves its half for its sibling. Inside our own workspace,
#: not a directory both repos share: the sibling reaches in to read it, which
#: keeps the direction of the dependency visible to anyone auditing us.
PARTIALS = "workspace/partials"

#: How long the filing process waits for its sibling's half. The sibling writes
#: as soon as its last window ends, which is normally while we are still
#: playing ours — but it may be finishing an audit, so we wait rather than file
#: a half series. Bounded, because a report that is late still counts and one
#: that never comes does not.
WAIT_SECONDS = 90.0


def partial_path(root: Path, game_uid: str, role: Role) -> Path:
    """Where the half played by `role` lives under `root`."""
    return root / PARTIALS / f"{game_uid}-{role.value}.json"


def _encode(outcome: SubGameOutcome) -> dict[str, Any]:
    """One scored mini-game, in a shape that survives a round trip through JSON."""
    return {
        "sub_game": outcome.sub_game,
        "role": outcome.role.value,
        "end_reason": outcome.end_reason.value,
        "our_score": outcome.our_score,
        "their_score": outcome.their_score,
        "steps": outcome.steps,
        "audit_passed": outcome.audit_passed,
    }


def _decode(row: dict[str, Any]) -> SubGameOutcome:
    """Rebuild a scored mini-game written by our sibling."""
    return SubGameOutcome(
        sub_game=int(row["sub_game"]),
        role=Role(row["role"]),
        end_reason=EndReason(row["end_reason"]),
        our_score=int(row["our_score"]),
        their_score=int(row["their_score"]),
        steps=int(row.get("steps", 0)),
        audit_passed=bool(row.get("audit_passed", True)),
    )


def write_partial(
    root: Path, game_uid: str, role: Role, games: list[dict[str, Any]],
    outcomes: list[SubGameOutcome],
) -> Path:
    """Leave our half of the series where our sibling will look for it."""
    path = partial_path(root, game_uid, role)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"game_uid": game_uid, "role": role.value, "written_at": now_iso(),
            "games": games, "outcomes": [_encode(outcome) for outcome in outcomes]}
    # The one pinned encoder, never a second serializer with its own flags —
    # `test_canonicalisation_is_pinned_in_one_module` exists because a rival
    # encoding is how audits break silently, and it greps for the call by name.
    # This payload is internal rather than something a peer hashes, but the
    # rule is about there being exactly one encoder, and a half-series is the
    # sort of file that later grows into something a peer does read.
    path.write_text(canonical_json(body), encoding="utf-8")
    return path


def clear_partials(root: Path, role: Role | None, emit: Emit | None = None) -> int:
    """Drop the halves *we* left behind, at the moment we start playing again.

    `None` is an unsplit run, which never writes a partial: nothing to clear,
    and the caller does not have to know which mode it is in.

    The hazard is real and `derive_game_ids` is why: the same opponent on the
    same terms produces the same `game_uid` every time, by design, so that both
    peers compute it independently. A series that stalls and is replayed
    therefore writes to the same partial path, and merging the earlier
    attempt's half would file one report describing games from two runs —
    self-contradictory in exactly the way rules 33-35 void both teams for.

    **Timestamps cannot decide it, and two rehearsals proved that in a row.**
    The first version refused any half written before our own first mini-game,
    on the reasoning that our sibling could not finish its last window before we
    began ours. The second moved the line back to when this process started.
    Both are false, because the halves are *independent streams*: our sibling
    opens window 1 while we wait for window 2, so it can finish, write its half
    and exit while we are still importing the MCP stack. Measured: the half was
    written at 20:02:01 and our own server bound at 20:02:07. Each guard called
    a live half stale, announced `sibling_half_missing`, and filed a two-game
    series as one game — the very mismatch the merge exists to prevent.

    So the attempt is identified by *deletion* instead, which needs no clock and
    no agreement between the two processes: each removes its own halves before
    it plays, and never touches its sibling's. Whatever is found afterwards
    under the sibling's role was therefore written by the sibling's current
    run — it wipes its own at startup exactly as we do (rule 2 is untouched:
    nothing is shared, each process only ever deletes what it wrote itself).
    """
    if role is None:
        return 0
    directory = root / PARTIALS
    dropped = 0
    for path in sorted(directory.glob(f"*-{role.value}.json")):
        path.unlink()
        dropped += 1
    if dropped and emit is not None:
        emit({"event": "series.partials_cleared", "role": role.value, "count": dropped})
    return dropped


def await_partial(
    root: Path, game_uid: str, role: Role, emit: Emit,
    wait: float = WAIT_SECONDS, sleep: Any = None,
) -> dict[str, Any] | None:
    """Our sibling's half of this attempt, waiting a bounded while for it.

    Anything present belongs to the current attempt — see `clear_partials` for
    why that holds and why no timestamp is compared here.
    """
    sleep = sleep or time.sleep
    path = partial_path(root, game_uid, role)
    deadline = time.monotonic() + wait
    while True:
        if path.exists():
            return dict(json.loads(path.read_text(encoding="utf-8")))
        if time.monotonic() >= deadline:
            emit({"event": "series.sibling_half_missing", "path": str(path),
                  "waited": wait, "role": role.value})
            return None
        sleep(1.0)


def sibling_repo(here: Path) -> Path | None:
    """The other half of the pair, when it is checked out beside us."""
    for name in ("najamjad-cop", "najamjad-thief"):
        candidate = here.parent / name
        if candidate.is_dir() and candidate.resolve() != here.resolve():
            return candidate
    return None


def assemble(
    manager: Any, our_role: Role, game_uid: str, games: list[dict[str, Any]],
    outcomes: list[SubGameOutcome], result: Any, groups: tuple[str, str],
    table: ScoreTable, emit: Emit, root: Path | None = None,
    wait: float = WAIT_SECONDS,
) -> tuple[list[dict[str, Any]], list[SubGameOutcome], Any] | None:
    """The whole series to file, or None when our sibling files it instead.

    Unsplit runs are returned untouched, so nothing about the single-process
    path changes until `game.opening_role` is set.
    """
    opens, own = split_roles(str(manager.get("game.opening_role", "") or ""), our_role)
    if own is None:
        return games, outcomes, result
    here = root or Path.cwd()
    write_partial(here, game_uid, own, games, outcomes)
    last = int(manager.get("network_and_league.num_games", 6))
    if role_for(last, opens) is not own:
        emit({"event": "series.sibling_files", "sub_games": [o.sub_game for o in outcomes]})
        return None
    other = Role.THIEF if own is Role.COP else Role.COP
    theirs = await_partial(sibling_repo(here) or here, game_uid, other, emit, wait) or {}
    merged = sorted(list(games) + list(theirs.get("games", [])),
                    key=lambda game: int(game.get("sub_game", 0)))
    scored = sorted(list(outcomes) + [_decode(row) for row in theirs.get("outcomes", [])],
                    key=lambda outcome: outcome.sub_game)
    emit({"event": "series.rejoined", "sub_games": [o.sub_game for o in scored],
          "sibling_half": bool(theirs)})
    tracker = SeriesTracker(our_group=groups[0], their_group=groups[1],
                            table=table, outcomes=scored)
    return merged, scored, tracker.result()
