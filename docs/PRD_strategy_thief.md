# Mechanism PRD — thief strategy

**Version 1.00 · 2026-07-26 · FR-STR-5..7 · ADR-007**

## Problem

Survive a fixed number of steps against a pursuer you cannot see, who can also
wall the board against you, while emitting a scent trail you cannot suppress.

## Contract

Identical to the cop's — `pick_move` / `pick_barrier` over `TurnFacts` — so the
orchestrator is role-agnostic and roles can alternate every mini-game without the
turn loop knowing.

The thief has no barrier quota; `pick_barrier` always returns `None`.

## The safety invariant (2026-08-03, supersedes the weighted sum)

**One cop cannot catch a careful thief on an open grid.** A 7×7 board is P₇ □ P₇,
the Cartesian product of two paths, and the cop number of a product of two trees
is 2 (Maamoun & Meyniel). Exact retrograde analysis over all 2401 positions
agrees: the only states the cop wins are those where it already shares our cell.
Survival is therefore not a heuristic target, it is achievable by discipline.

The policy is three rules, in order:

1. **Never end a turn within one step of the cop.** At graph-distance 2 the cop
   cannot reach us next turn, so we are safe by construction. Corners are
   survivable — cornered at `[0,6]` against a cop at `[0,5]`, step to `[1,6]`; it
   follows, step back. The oscillation never loses.
2. **Among safe cells, take the most room** — measured at *two* scales.
   Component size separates a sealed pocket from the open board; escape routes
   discriminate inside one room. Component size alone is constant across an
   intact board, which silently collapses the ranking back to distance-only —
   the original bug wearing a different hat, and two existing tests caught it.
3. **Never stand beyond a cut cell** while the cop can still spend barriers,
   because that is exactly the one wall that seals us in. Once the budget is
   spent, a cul-de-sac is just a room.

Ties are broken by a seed derived from `(sub_game, step)`: unpredictable across
games, reproducible within one for the audit, and **only ever among moves that
already satisfy rule 1** — unpredictability is never bought with safety.

Measured: 35/35 against uoh-sqak's recorded line (was: captured at step 14),
0 captures in 90 games against a perfect chaser, a barrier-spending waller and a
random cop, and 47/49 starting cells survive a perfect chaser. The two that fail
are the cells adjacent to the cop's start, where it moves first and takes us
before we move — unavoidable, and not reachable under the agreed terms.

Cost: ~10 ms per turn against a 30-second budget.

### What this replaced, and why

The previous policy scored a weighted sum of distance, room, risk and scent. It
was not mistuned; it optimised the wrong thing. Maximising distance from a
*sweeping* cop means running ahead of the broom into the corner the broom is
heading for, and our thief did exactly that against uoh-sqak — caught at `[1,6]`
on step 15, three games out of three, by a scripted opponent with no LLM.

The sum survives as the fallback for a peer that transmits no scent at all.

> Historic note: the earlier claim that this brain "survives 96-100 % of games
> against a greedy cop" was measured against our own baselines. Given no cop can
> force a capture, such rates describe the baseline, not the brain.

## The scent problem

We cannot stop emitting. What we *can* do is avoid leaving a trail that reads as
a straight line — a predictable trail lets a pursuer extrapolate rather than
follow. Our evasion therefore prefers paths that keep the trail's centroid
ambiguous, which is the same property the cop's lie detector exploits in reverse.

## Answering a claim

Rules 21-22 oblige an honest answer to a capture claim, and the answer is settled
**at the moment the claim arrives**, against the cell we occupied then. Deciding
it later meant answering from a cell we had already left — a dishonest "no" to a
claim that had landed, provable at the audit, in a game we had ourselves recorded
as a capture (ADR-015).

## Hints

Bluffing is a resource with a cost. The hint policy chooses truth or misdirection
against the credibility we believe the opponent assigns us: a peer who has caught
us lying discounts everything afterwards, so a lie spent early is expensive.

## Alternatives considered

| Option | Why not |
|---|---|
| Maximise distance greedily | Measured: caught in most games; corners itself. |
| Always tell the truth | Forfeits a legitimate rule-26 instrument. |
| Always lie | Credibility collapses; hints stop working entirely. |
| Randomised evasion | Breaks replay determinism (ADR-007). |

## Test scenarios

| Scenario | Expectation | Test |
|---|---|---|
| Cornered | Prefers the cell retaining escape routes | `test_thief_escape.py` |
| Distance ties | Broken by survival horizon, not arbitrarily | `test_thief_brain.py` |
| Claim lands | Honest `caught: true` before the game closes | `test_turn_ingress.py` |
| Claim misses | Honest `caught: false`, not silence | `test_turn_ingress.py` |
| Versus the baseline | Survives the greedy cop | `test_self_play_harness.py` |
