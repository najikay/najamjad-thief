"""The counted-match tracker — the number we are required to declare honestly.

Book rules 37-38: at the start of every match each team declares how many
*counted* matches it has already played, and the diversity weighting is set from
those declarations. A false declaration discovered at project review
disqualifies the team — so this number must never be typed by hand.

The tracker is the single source of that figure. It persists to the state
directory, records who each counted match was against (one counted match per
opponent, rule 52), and keeps an append-only audit trail of every change.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..protocol.canonical import canonical_json

MAX_COUNTED_MATCHES = 10
MIN_TO_PASS = 2
#: Where the count lives. Under `workspace/` rather than `config/` because it is
#: state we accumulate, not a setting anyone edits — and editing it by hand is
#: precisely the thing rules 37-38 disqualify a team for.
DEFAULT_PATH = "workspace/counted_games.json"


def tracker_for(manager: Any = None) -> "CountedGames":
    """The tracker at its configured home, loaded and ready to declare from.

    One accessor so every caller reads the same file. The count is required to
    be honest at every handshake (rules 37-38), and two callers disagreeing
    about where it is stored would be the quietest possible way to get it
    wrong.
    """
    location = DEFAULT_PATH
    if manager is not None:
        location = str(manager.get("paths.counted_games", DEFAULT_PATH) or DEFAULT_PATH)
    return CountedGames.load(Path(location))


class CountedGameError(Exception):
    """Raised when a match would break the league counting rules."""


@dataclass
class CountedGames:
    """Persistent record of the counted matches we have played."""

    path: Path | None = None
    opponents: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "CountedGames":
        """Read the tracker, starting empty when it does not exist yet."""
        if not path.exists():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            path=path,
            opponents=list(data.get("opponents", [])),
            history=list(data.get("history", [])),
        )

    @property
    def count(self) -> int:
        """How many counted matches we have played — the declared figure."""
        return len(self.opponents)

    @property
    def passes_minimum(self) -> bool:
        """Whether we have met the threshold for a grade at all (rule 31)."""
        return self.count >= MIN_TO_PASS

    @property
    def remaining(self) -> int:
        """Counted matches still available to us (cap of 10)."""
        return max(0, MAX_COUNTED_MATCHES - self.count)

    def already_played(self, opponent: str) -> bool:
        """True when this opponent has already given us a counted match."""
        return opponent in self.opponents

    def check_can_count(self, opponent: str) -> None:
        """Raise if a counted match against `opponent` would be invalid."""
        if self.already_played(opponent):
            raise CountedGameError(
                f"{opponent} has already been counted; only one counted match per "
                "opponent scores (rule 52) — play a warm-up instead"
            )
        if self.remaining <= 0:
            raise CountedGameError(
                f"the cap of {MAX_COUNTED_MATCHES} counted matches is reached (rule 31)"
            )

    def record(self, opponent: str, game_uid: str = "", timestamp: str = "") -> int:
        """Record a completed counted match and persist immediately."""
        self.check_can_count(opponent)
        self.opponents.append(opponent)
        self.history.append(
            {
                "opponent": opponent,
                "game_uid": game_uid,
                "at": timestamp,
                "count_after": self.count,
            }
        )
        self.save()
        return self.count

    def declaration(self) -> dict[str, Any]:
        """The block we send the opponent at match start (rules 37-38).

        The count goes out under **both** spellings. Ours has always been
        `counted_matches_played`; the league's league-block readers look for
        `counted_games_played`, so a peer building its report from our identity
        found nothing and printed zero — imreeyal's friendly artifact stated
        `najamjad: 0` against a truth of 1, and their counted file would have
        said 0 where the truth is 2.

        That is not a cosmetic mismatch. Rule 38 judges counted-match
        declarations on *mutual consistency between the two teams' files* and
        treats a false one as project-level, so our key name would have put a
        wrong number in an honest opponent's report. Both spellings carry the
        same integer from the same tracker, so they cannot disagree, and a peer
        reading either one is correct.
        """
        return {
            "counted_matches_played": self.count,
            "counted_games_played": self.count,
            "counted_matches_remaining": self.remaining,
            "opponents_already_counted": list(self.opponents),
        }

    def save(self) -> None:
        """Persist the tracker; a lost count would mean a false declaration."""
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"opponents": self.opponents, "history": self.history}
        self.path.write_text(canonical_json(payload), encoding="utf-8")
