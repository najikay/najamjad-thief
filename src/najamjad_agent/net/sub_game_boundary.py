"""Clearing the inbox between mini-games, without losing the next one's opening.

Split out of `inbox.py` to keep that file inside the 150-line budget, and
because this is a distinct decision: the inbox's job is to validate and queue,
while this is the rule for what survives the boundary between two mini-games.

Both halves of that rule were learned the hard way against a real opponent.
"""

from __future__ import annotations

from queue import Empty, Queue
from typing import Any

#: The step number every mini-game restarts from.
FIRST_STEP = 1


def clear_finished_game(queues: dict[str, Queue]) -> tuple[dict[str, int], bool]:
    """Drop the finished game's leftovers; keep what the next game needs.

    Draining everything is the obvious implementation and it is wrong. The peer
    who finishes a mini-game first sends the next game's opening turn
    immediately, so by the time the slower peer starts that game the turn is
    already queued — and a blanket drain deletes it, after which both sides wait
    for each other until the match dies. Whoever wins that race should not
    decide whether the series continues.

    Two things are therefore kept:

    * the **opening turn** of the new mini-game, identified by its step number,
      because nothing on the wire names the sub-game;
    * any **agreement**, because opponents built on the course reference
      re-negotiate per mini-game and may have sent theirs the moment the last
      game ended. Terms do not change between mini-games, so keeping it is both
      safe and necessary.

    Returns what was dropped, and whether an opening turn is now in hand — the
    caller needs the second to keep its sequence mark consistent with the queue.
    """
    dropped: dict[str, int] = {}
    held_opening = False
    for kind, box in queues.items():
        kept: list[Any] = []
        count = 0
        while True:
            try:
                message = box.get_nowait()
            except Empty:
                break
            if kind == "negotiate" or kind == "turn" and getattr(message, "step", None) == FIRST_STEP:
                kept.append(message)
            else:
                count += 1
        for message in kept:
            box.put_nowait(message)
            held_opening = held_opening or kind == "turn"
        if count:
            dropped[kind] = count
    return dropped, held_opening
