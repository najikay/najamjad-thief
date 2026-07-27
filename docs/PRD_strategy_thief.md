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

## Survival horizon, not distance

The obvious thief maximises distance from the believed cop. That is a trap: the
move that maximises distance frequently walks into a corner that is one barrier
from a capture. Orthogonal moves also tie on Manhattan distance far more often
than intuition suggests, so "maximise distance" underdetermines the choice.

We instead search a horizon for cells that keep **escape routes** open, scoring a
candidate by the freedom still available from it rather than by how far it is
now. Against a greedy cop this survives 96-100 % of games; the greedy thief
survives only 32-44 % against ours.

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
