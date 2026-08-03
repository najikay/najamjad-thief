"""Real opponents, captured from real matches, replayable offline.

Asserting that a strategy is better is not evidence. This holds the actual lines
opponents played against us, so a change either survives longer against a team
that beat us or it does not, and the number says which.

`UOH_SQAK_SWEEP` is the one that matters most. Their cop played it three times
out of three, byte-identical each time, from an agent declaring
`llm_model: "template"` — no LLM at all. It is a lawnmower sweep: down the left
edge, across the bottom, up the middle, then along the top. Our thief started at
[3,3] and was caught at [1,6] on step 16 in all three games.

That last detail is the diagnosis. [1,6] is on the right edge, and our thief ran
there of its own accord — which is exactly the death `thief_escape.py` describes
in its own docstring: *"a corner is far from a cop on the far side of the board
right up until it becomes a coffin"*. The penalties for it exist; they lose to
`DISTANCE_WEIGHT` in the weighted sum.
"""

from __future__ import annotations

from najamjad_agent.domain.params import Position

#: The cop cells uoh-sqak claimed, in order, in every one of g02, g04 and g06.
#: Read as their cop's position at steps 1..15; step 0 is the agreed [0,0].
#: They claimed on *every* step, not only when they had us — a claim forces a
#: cryptographically truthful yes/no, so claiming each swept cell buys a free
#: bit of information per turn. `lands: true` came at step 15, on [1,6].
UOH_SQAK_SWEEP: tuple[Position, ...] = (
    (1, 0), (2, 0), (3, 0), (4, 0), (5, 0),
    (5, 1), (5, 2),
    (4, 2), (3, 2), (2, 2), (1, 2),
    (1, 3), (1, 4), (1, 5), (1, 6),
)

#: Their barrier at each step, from `barrier.observed` — all 14 of their budget.
#:
#: **This is the part that beats you, and it took a replay to see it.** Read the
#: cells against the sweep above: at step 2 they wall [0,0], the cell they stood
#: on at step 1. At step 3, [1,0] — where they were at step 1. Column 0 is
#: sealed as they descend it, then column 1, then [0,2] and [1,2] behind the
#: turn. They are not blocking *us*; they are sealing the region they have
#: already cleared so we cannot slip back into it behind them.
#:
#: That is textbook graph searching: a lone sweeper on a grid is normally
#: evadable by recontamination — you step back into cleared ground once the
#: frontier passes. Barriers remove that option, and 14 is enough to do it on a
#: 7x7. The result is an *information-free* capture: it does not matter where
#: the thief is or how well it plays. Their agent declares `llm_model:
#: "template"` and needs no model at all, which is exactly why it beat us 3/3
#: with the identical line.
UOH_SQAK_BARRIERS: tuple[Position, ...] = (
    (0, 1), (0, 0), (1, 0), (2, 0), (3, 0),
    (4, 0), (4, 1), (5, 1), (4, 3), (3, 1),
    (2, 1), (0, 2), (1, 2), (0, 4),
)

#: Steps our thief survived, out of the 35 that would have scored 10 instead of
#: 5. Identical in g02, g04 and g06.
UOH_SQAK_BASELINE_STEPS = 15

#: Where their sweep caught us, all three times.
UOH_SQAK_CAPTURE_CELL: Position = (1, 6)
