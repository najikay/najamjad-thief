# Mechanism PRD — cop strategy

**Version 1.00 · 2026-07-26 · FR-STR-1..4 · ADR-007**

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
| our cop vs greedy thief | **56-68 %** |
| greedy cop vs greedy thief | 0-4 % |

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
