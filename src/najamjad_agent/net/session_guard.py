"""Who is allowed to move in our game — and how often.

Our MCP endpoint is public by necessity (book rule 10) and its URL is published
in our repository, so *anyone* can reach it. Commit-reveal protects against the
**opponent** rewriting history, but nothing in the book's protocol stops a
**third party** from injecting a well-formed turn into a live match. That is a
real integrity hole: a stranger could move for our opponent, or flood us into a
technical loss.

Two defences, both cheap:

* **Identity binding** — once a match is negotiated, only the agreed opponent
  id may send turns for that game. Anyone else is refused.
* **Session token** — when the peer supports it, turns carry a token derived
  from the signed contract hash. Both sides can compute it (they hold identical
  contracts) but an outsider cannot, because it is never transmitted. Optional
  by design: an opponent running the reference implementation will not send one,
  and refusing to play them would cost us the match, not protect it.

Rate limiting is global rather than per-IP: the tunnel presents every request
from Cloudflare, so source addresses are not ours to distinguish.
"""

import hashlib
import hmac
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..shared.events import Emit

# A flood backstop, not a throttle on play. The previous value — 120/min —
# assumed turns are human-paced, and they are not: a turn costs us milliseconds,
# so two fast peers pass 2/sec trivially. In a six-game rehearsal we rejected the
# opponent's legitimate turn at game 4 and then timed out waiting for the message
# we had thrown away ourselves, forfeiting a game to our own guard.
#
# The real protection against a peer exhausting memory is the bounded inbox
# queue, which refuses politely and does not grow. This ceiling only has to sit
# above anything honest play can reach; it is overridden from
# `config/rate_limits.json` (service `inbound_peer`), never hardcoded at a call
# site.
DEFAULT_MAX_PER_MINUTE = 3000


def session_token(config_sha256: str, game_uid: str) -> str:
    """Derive the shared session token from the signed contract.

    Both peers hold a byte-identical contract, so both derive the same token
    without ever sending it. It is a proof of "we negotiated together", not a
    secret key — the contract hash is exchanged during negotiation.
    """
    return hmac.new(
        config_sha256.encode("utf-8"), game_uid.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]


@dataclass
class SessionGuard:
    """Admits only the negotiated opponent, at an honest rate."""

    expected_sender: str = ""
    #: A second name the same peer may legitimately use in `sender`. Peers do
    #: not agree on what the field means: three teams put their **role** there
    #: ("police"/"thief" — 5,239 messages across our logs) and nis-yar1 put
    #: their **group id**, which is the more natural reading of a field called
    #: `sender` and is what we asked them for. Both name the peer we signed
    #: with, so refusing either is refusing an honest opponent over a
    #: convention nobody wrote down. The token below is what actually proves
    #: "we negotiated together"; this field only keeps a *third party* out, and
    #: neither form is a third party.
    expected_group: str = ""
    expected_token: str = ""
    max_per_minute: int = DEFAULT_MAX_PER_MINUTE
    emit: Emit | None = None
    clock: Callable[[], float] = time.monotonic
    _timestamps: list[float] = field(default_factory=list)

    @property
    def bound(self) -> bool:
        """True once a match is under way and an identity is enforced."""
        return bool(self.expected_sender)

    def bind(self, opponent_id: str, config_sha256: str = "", game_uid: str = "",
             group_id: str = "") -> None:
        """Lock this agent to one opponent for the duration of a match."""
        self.expected_sender = opponent_id
        self.expected_group = str(group_id or "")
        if config_sha256 and game_uid:
            self.expected_token = session_token(config_sha256, game_uid)
        self._event("session.bound", opponent=opponent_id, token_enforced=bool(self.expected_token))

    def release(self) -> None:
        """Unbind at the end of a match so the next negotiation can proceed."""
        self.expected_sender = ""
        self.expected_group = ""
        self.expected_token = ""
        self._timestamps.clear()
        self._event("session.released")

    def check(self, message: Any) -> str | None:
        """Return a refusal reason, or None when the message may proceed."""
        if throttled := self._rate_limited():
            return throttled
        if not self.bound:
            # Before negotiation any peer may introduce itself; that is how a
            # match starts. Nothing game-affecting is accepted at this stage.
            return None
        sender = str(getattr(message, "sender", "") or "")
        allowed = {self.expected_sender, self.expected_group} - {""}
        if sender and sender not in allowed:
            self._event("session.rejected", reason="sender", sender=sender)
            return (f"sender {sender!r} is not the negotiated opponent "
                    f"{sorted(allowed)!r}")
        token = str(getattr(message, "session_token", "") or "")
        if self.expected_token and token and not hmac.compare_digest(token, self.expected_token):
            self._event("session.rejected", reason="token")
            return "session token does not match the signed contract"
        if self.expected_token and not token:
            # Tolerated: reference-implementation peers do not send one.
            self._event("session.unauthenticated", sender=sender)
        return None

    def _rate_limited(self) -> str | None:
        """Refuse a flood before it can reach the game queue."""
        now = self.clock()
        self._timestamps = [stamp for stamp in self._timestamps if now - stamp < 60.0]
        if len(self._timestamps) >= self.max_per_minute:
            self._event("session.rate_limited", seen=len(self._timestamps))
            return f"inbound rate limit of {self.max_per_minute}/min exceeded"
        self._timestamps.append(now)
        return None

    def _event(self, name: str, **fields: Any) -> None:
        if self.emit is not None:
            self.emit({"event": name, **fields})
