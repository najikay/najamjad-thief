# Mechanism PRD — cop strategy

**Version 1.10 · 2026-08-05 · FR-STR-1..4 · ADR-007**

## Problem

Catch an opponent you cannot see, using a blurry unfakeable signal and a precise
untrustworthy one, within a step budget, while spending a finite barrier quota.

## Contract

```python
brain.pick_move(facts)    -> Move        # N/S/E/W/STAY, always legal
brain.pick_barrier(facts) -> Position | None
```

`facts` is a `TurnFacts` snapshot: our own cell, legal moves, the belief map, the
scent field, barriers left, the opponent's last hint. It deliberately does **not**
carry the board — brains read that through a `board_supplier`, because barriers
appear mid-game and a brain reasoning over a stale board walks into a wall it
declared itself.

## Pursuit

Move to minimise expected distance to the *believed* thief, with lookahead
diffusion: the thief will move too, so chasing the current peak chases where they
were. We spread the belief forward `LOOKAHEAD_STEPS` and pursue the result.

The orchestrator hard-filters the choice — an illegal move can never leave this
agent, whatever the brain returns. That guard has fired in tests against our own
buggy brains, which is the point.

## Barriers

Scored by **freedom denied** to the likely thief cells, not by raw distance.
Standing next to a cell you cannot enter is worth nothing; a barrier that removes
an escape route from a corner is worth a great deal. Quota is 14 (Appendix F
minimum, raisable), and the cop refuses to place once spent.

A barrier capture needs no announcement: rules 15-16 make placement public, so
both peers reach the same verdict on the same turn (ADR-015).

## Claiming

A capture claim discloses the claimer's own cell — that is the price the rules
attach to it, and what stops a cop claiming speculatively every turn. We claim
only when our belief peak coincides with where we stand.

## Measured

Through the real match machinery, 150 games, two seeds:

| | capture rate |
|---|---|
| our cop vs greedy thief | **100 %** |
| greedy cop vs greedy thief | 0-4 % |

The sweep that produced it is the most useful thing in this document.
`barrier_threshold` — how much belief must sit on the target before we spend a
barrier — is the single most sensitive dial in the project:

| threshold | capture rate |
|---|---|
| 0.05 | 4 % |
| 0.10 | 8 % |
| 0.15 *(shipped for weeks)* | 43-75 % |
| 0.25 | 96 % |
| **0.40** | **100 % on every seed tried** |

A barrier is impassable for **both** sides. A cop that walls on weak evidence
fences itself away from the thief it is chasing, so spending barriers cheaply is
not aggression — it is self-harm. Confirmed on three seeds with non-overlapping
confidence intervals before the default was changed.

`lookahead` is flat across 1-4 on a 7x7 board: the dial exists, and the sweep
says it does not matter here. Recording that is the point of a sweep.

## Alternatives considered

| Option | Why not |
|---|---|
| Greedy chase of the belief peak | Measured at ~0 % capture; chases the past. |
| Reinforcement learning | ~60 games available; breaks replay (ADR-007). |
| Full expectimax over the horizon | Cost grows past the 5 s move budget on a 7×7 board with barriers. |
| Never place barriers | Forfeits the cop's only asymmetric advantage. |

## Test scenarios

| Scenario | Expectation | Test |
|---|---|---|
| Empty belief | A legal move, never a crash | `test_cop_brain.py` |
| Barrier quota spent | No further placement | `test_cop_barriers.py` |
| Illegal proposal | Filtered by the orchestrator | `test_orchestrator.py` |
| Walled-in thief | Capture recognised | `test_endings.py` |
| Versus the baseline | Beats greedy decisively | `test_self_play_harness.py` |


## Re-baseline, 2026-08-03 — what the cop is actually worth

Every capture-rate number previously recorded here was measured against our own
old thief, and it was fiction. The published cop number of a Cartesian product
of two trees is 2, so **one cop cannot force a capture on a 7×7 grid** — a
saturated 100 % capture rate could therefore only ever have been describing the
opponent's weakness. Confirmed by exact backward induction over all 4802
perfect-information states: the only cop-win positions are the 49 where the two
already share a cell.

Re-swept against the current thief (`--games 24 --seed 7`):

| knob | values swept | capture rate |
|---|---|---|
| `cop.barrier_threshold` | 0.05 … 0.60 | **0/24 at every value** |
| `cop.lookahead` | 1 … 4 | **0/24 at every value** |

Both dials are inert against a correct thief. That is not a tuning failure, it
is the theorem: pursuit cannot win, and neither knob changes what barriers do.

### What this means for match day

* **The cop's floor is 5 points per game (survival), not 20.** Plan the series
  around 3 thief games at 10 and 3 cop games at 5 — a **45-point floor** — and
  treat every cop capture as opportunistic.
* **Cop captures will come from opponent error, not from our pursuit.** The one
  configuration that still beats our own thief is a barrier trap under *exact*
  information; one cell of belief error defeats it.
* **Barriers only matter when they make the region acyclic.** Shrinking the
  thief's room achieves nothing on its own — a sealed 2×2 pocket is a 4-cycle
  and is *not* cop-win, while a sealed 1×3 path is. Every tree is cop-win, so
  "does this placement reduce the cycle rank" is the correct objective, and
  `cop_barriers.score_placement`'s weighted escape-route count is a poor proxy
  for it.

The counting bound behind all of this, since it is short: a guaranteed sweep
needs each of the *n²* cells cleared, a move turn clears at most one
permanently, and a barrier turn clears none while removing one cell from the
board — so `n² − b ≤ 35 − b`, i.e. `n² ≤ 35`. The barrier budget cancels. A 5×5
board is sweepable (25 ≤ 35); a 7×7 is not (49 > 35), and no amount of
computation changes that.


## Retargeting the barrier planner at cycle rank — tried, measured, reverted

Recorded as a negative result because the reasoning still looks right and the
measurement still says no.

**The idea.** `score_placement` values a wall by the weighted escape routes it
removes, and that is the wrong target: a region with a cycle in it is not
cop-win however small it gets. A sealed 2x2 pocket is a 4-cycle the thief
circles forever; wall one of its cells and the remaining L is a tree, and every
tree is cop-win. So the planner should be closing loops, gated on
`remaining_loops < barriers_left` — an intact 7x7 has cycle rank 84 − 49 + 1 =
36 against a quota of 14, so it can only pay in a small region.

**What happened.** Every measurement got worse:

| | before | after |
|---|---|---|
| vs our thief (correct play) | 0/24 | 0/24 |
| vs greedy thief (sweep) | 16/24 | 15/24 |
| vs greedy thief (harness) | ≥ 0.80 | **0.375** |
| audit failures | 0 | **5** |

The audit failures are the decisive part: games were voiding, which costs more
than any tuning gains. Spending barriers on a cycle-rank argument changed which
cells were walled often enough to desynchronise the two peers' boards.

**Reverted in full**, along with `territory.cycle_rank`, which had no other
caller — unused production code is worse than none. What was kept from the
attempt is the `solver` module itself, which pays for itself on the thief side.

**The lesson worth keeping**: the cycle-rank reasoning is sound about *what a
winning position looks like* and useless as a *turn-by-turn objective*, because
the cop cannot reach a tree from an intact board inside 35 moves anyway. The
theory tells you the destination; it does not follow that steering toward it one
barrier at a time is better than playing the position in front of you.
