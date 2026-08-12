"""An in-memory transport that behaves like the network actually does.

`LinkedTransport` in the headless tests is deliberately non-blocking: those
tests drive both peers by hand, so a message is always waiting. Two peers
running concurrently need the real semantics — block until the message arrives
or the deadline passes — otherwise the first peer to look finds an empty queue,
reports a timeout, and forfeits a game nobody was losing.

That is exactly what `PeerTransport` does against a live opponent, so a test
using this is testing the same control flow that runs on match day.
"""

import queue
from typing import Any

from najamjad_agent.net.turn_sequence import TurnSequence


class BlockingLink:
    """A pair of queues joining two peers, with real timeout behaviour."""

    def __init__(self) -> None:
        """Start unconnected; `connect` joins two of these together."""
        self.turns: queue.Queue[dict[str, Any]] = queue.Queue()
        self.audits: queue.Queue[Any] = queue.Queue()
        self.peer: BlockingLink | None = None
        self.sent_turns = 0
        self.resets = 0
        self.new_sessions = 0
        self.boundaries = 0
        self.in_play = False
        self.rejected_stale = 0
        # The production guard itself, so this fake cannot drift from the rule
        # it is meant to model.
        self._sequence = TurnSequence()

    def connect(self, other: "BlockingLink") -> None:
        """Point each link at the other, so a send lands in their inbox."""
        self.peer = other
        other.peer = self

    def send_turn(self, message: dict[str, Any]) -> None:
        """Deliver one turn to the peer's inbox, enforcing the real guard.

        The production inbox refuses a step it has already seen (a replay), and
        this fake did not. That gap hid a defect that ended every real series
        after one mini-game: game 2 restarts at step 1, which the live guard
        read as "stale, last accepted was 11". A fake without the constraint
        cannot fail the way the wire fails.
        """
        assert self.peer is not None, "link was never connected"
        step = message.get("step")
        if isinstance(step, int):
            # Production's own guard, not a second copy of it. This fake used to
            # re-implement the rule — including an unconditional bypass for any
            # message carrying `claim_response` — so it accepted exactly what
            # production had started refusing, and no integration test could
            # surface the difference. A fake that is kinder than the wire is how
            # five separate defects reached a real match (ADR-017).
            refusal = self.peer._sequence.check(
                step, message.get("claim_response") is not None
            )
            if refusal:
                # Dropped, exactly as the real inbox drops it: rejected at
                # ingress and never queued. Raising here would be louder but
                # wrong — on the wire the sender learns nothing and simply waits,
                # which is precisely how the defect presented in a real match.
                self.rejected_stale += 1
                return
        self.sent_turns += 1
        self.peer.turns.put(message)

    def receive_turn(self, timeout: float) -> dict[str, Any] | None:
        """Wait for the peer's turn; None once the deadline passes."""
        try:
            return self.turns.get(timeout=timeout)
        except queue.Empty:
            return None

    def send_audit(self, payload: Any) -> None:
        """Hand our revealed records to the peer, exactly as sent.

        Forwarded untouched. This fake used to wrap the payload in a
        `{"records": …}` envelope the real transport never added, so the domain
        sent a bare list, every in-memory test passed, and the reveal was
        rejected by the peer's validator in every real match. A fake kinder
        than the wire tests nothing.
        """
        assert self.peer is not None, "link was never connected"
        self.peer.audits.put(payload)

    def receive_audit(self, timeout: float) -> Any:
        """Wait for the peer's revealed records; None once the deadline passes."""
        try:
            return self.audits.get(timeout=timeout)
        except queue.Empty:
            return None

    def reset(self) -> None:
        """Forget the previous mini-game, as the real transport does.

        The new game's opening turn may already be queued — the peer who
        finished first sends it immediately — so it is kept while the finished
        game's leftovers are dropped.
        """
        self.resets += 1
        self.in_play = True  # the real transport shuts the handshake gate here
        kept = []
        while not self.turns.empty():
            message = self.turns.get_nowait()
            if message.get("step") == 1:
                kept.append(message)
        while not self.audits.empty():
            self.audits.get_nowait()
        for message in kept:
            self.turns.put(message)
        self._sequence.begin_sub_game(bool(kept))

    def new_session(self) -> None:
        """Replace the outbound session, as the real transport does.

        Counted rather than ignored: the real one must do this *before* each
        sub-game's handshake, because a peer running a fresh process per
        sub-game leaves our held socket attached to a process that is gone. A
        fake that quietly accepted the call would let that ordering regress
        without a single test noticing.
        """
        self.new_sessions += 1

    def finish_sub_game(self) -> None:
        """Reopen the handshake gate, as the real transport does.

        Modelled rather than stubbed: a gate left shut would make the agent
        refuse every subsequent opponent while still looking healthy, and a
        fake that always answered "open" could not fail that way.
        """
        self.in_play = False
        self.boundaries += 1


def linked_pair() -> tuple[BlockingLink, BlockingLink]:
    """Two connected links, ready to hand to two peers."""
    left, right = BlockingLink(), BlockingLink()
    left.connect(right)
    return left, right
