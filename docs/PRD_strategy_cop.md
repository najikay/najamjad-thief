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

## The harness could not score a capture — 2026-08-16

Every cop number in this document above was measured with an instrument that
**could not end a game the way real ones end.** `cop_duel.run_cop_duel` checked
co-location once per step, *before* the cop moved, so it detected only the thief
walking into a stationary cop. The move that actually decides mini-games — the
thief moves, the cop steps onto the cell it moved to and claims it — was never
checked at all.

Settled from real games rather than from the rule text, because the rule text is
where the earlier reading came from. In the moaamoha friendly of 2026-08-15 our
cop captured three times and our thief was captured twice, and **all five were
that move**: g02 their `[6,6]→[5,6]` against our `[5,5]→[5,6]`; g04 `[6,6]→[6,5]`
against `[5,5]→[6,5]`; g06 `[6,4]→[6,3]` against `[5,3]→[6,3]`; and the two we
lost are the same geometry from the other side. Their `is_captured` answers a
claim from the sealed position of that step, so the cell the thief has just
moved to is exactly what the claim is compared against.

With the check added, against the greedy evader the same pursuit ends at **step
13** instead of running the full 35 while sitting at distance 1 for its last 23
steps. `test_the_cop_takes_a_thief_that_lets_it_reach_striking_range` is the new
ratchet; tracking and closing are now separate assertions, which they always
should have been.

**What is still true.** One cop cannot *force* a capture on an open 7x7 — that
is ADR-021 and it is a theorem about a thief that keeps its distance, which our
own thief does: it still survives all 35 against our own cop under the corrected
rule, holding distance 3. The theorem was never the thing that was wrong; the
instrument was reporting it about every thief rather than about that one.

**Owed:** the five candidates rejected on 2026-08-15 were all measured on the
old instrument, and at least the two pursuit candidates deserve re-running now
that closing can be scored.

## Lowering `barrier_threshold` — adopted, 0.40 -> 0.22 (2026-08-16)

The vibecode post-mortem asked why a full-strength cop holding a near-perfect
belief declined **eleven of its fourteen walls**. The answer was the dial:
`plan_barrier` scores a placement by the escape routes it removes from cells
holding belief mass, at 0.40 almost nothing clears it, and the value itself was
measured on an instrument that could not price a barrier.

**Why the old measurement was void.** The sweep behind 0.40 — and the reading
that "walling is self-harm" — ran against *replayed* opponent lines. A replayed
line is a list of cells the thief is teleported through: it cannot be blocked,
so our barriers constrained only us. **36 of the 56 archived lines put the thief
on a cell we had walled.** That instrument charges the cop for every barrier and
credits it with nothing, and no barrier question can be settled on it. It is
still the right instrument for pursuit-without-walls, which is what it was
originally built for.

**Re-measured against four thieves that see the live board**, 40 starting
positions each, 160 games per value:

| value | our thief | sandbagged | greedy | room evader | total |
|---|---|---|---|---|---|
| 0.40 (was shipped) | 0/40 | 40/40 | 40/40 | 9/40 | **89/160** |
| 0.25 | 0/40 | 40/40 | 40/40 | 21/40 | 101/160 |
| 0.24 | 40/40 | 40/40 | 40/40 | 27/40 | 147/160 |
| **0.22** | 40/40 | 40/40 | 40/40 | 28/40 | **148/160** |
| 0.21 | 40/40 | 40/40 | 40/40 | 27/40 | 147/160 |
| 0.20 | 40/40 | 40/40 | 40/40 | 0/40 | 120/160 |

Strictly better on every one of the four and worse on none. 0.22 sits in the
middle of the [0.21, 0.24] band rather than on a cliff: at 0.25 the walls that
convert stop being taken, at 0.20 walls that fence us out start being taken. The
`room evader` in that table is the honest adversary — a thief that keeps its
distance *and* maximises the room it keeps — and it is the column that matters,
because a wall policy which only beats thieves indifferent to enclosure has not
been tested against the thing walls are for.

**The theory agrees, and it is the reason to trust the direction rather than the
digits.** Conway's angel problem: a blocker that removes one square per turn
defeats a king-stepping evader on a bounded board by *progressive* encirclement
(the angel of power 1 loses). Our thief steps one orthogonal square per turn on
49 cells, which is weaker than a king, and we hold fourteen blocks. Enclosure is
the cop's winning idea; the previous value simply never bought it.

**What did not change.** A barrier is still impassable for both sides, which is
exactly why the band has a floor — `_still_reachable` refuses a placement that
walls us away from the mass we are chasing, and below 0.21 the planner starts
taking walls it cannot see past. And the theorem still stands: against a thief
that defends against encirclement properly, the cop captures none of 40 (see
`PRD_strategy_thief.md`, same date) — which is ADR-021 doing what it says.

### Region-shrinking as the barrier objective — tried, measured, weaker

Written as `FenceCop` while checking whether the thief's new defence generalises:
score a placement by how much it shrinks the thief's *component*, preferring
walls that continue a fence or lean on the board edge. That is the intuitive
reading of the angel argument and it appears to be what uoh-sqak did to us.

It converts nothing. Over 40 starting positions it spends 9.6 barriers a game
and captures **0 of 40** against both our current thief and the one-cut thief it
was built to exploit — including the variant given our own pursuit policy, so
the only difference is the wall objective itself.

The shipped objective wins because it is denominated in the escapes the thief is
*about to use*, weighted by where we believe it is, rather than in the size of
the room. The room is a lagging measure of the same thing and pays for walls too
early. Recorded because it is the obvious next idea and it is worse.
