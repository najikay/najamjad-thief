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

## Seeing a silent opponent (2026-08-04)

The safety invariant above only runs when the belief names a cell, and against
uoh-sqak it never did. They send **no scent, no hints and no observations**, so
the belief stayed uniform, `_cop_cell` correctly refused to name a cell from a
flat distribution, and the thief fell back to the weighted sum that had already
lost three games. The exact solve and the distance-2 invariant — the two things
that make this brain good — did not execute against them once.

The sealed archive shows the result plainly. Across g02, g04 and g06 our thief
occupied **four distinct cells in eleven steps**, held `[5,5]` for six
consecutive turns, and played a near-identical line all three games. It was not
evading; it was standing still while being swept. Practice-3 then lost 0-6 with
captures at turn 10, three times out of three.

What a silent peer cannot withhold is what the rules make mandatory:

| declaration | what it tells us | rule | seen in one series |
|---|---|---|---|
| capture claim | the cop's **exact** cell — a capture scores only if the cop occupies the cell it claims | 21-22 | 146 |
| barrier | the cop is on that cell or one orthogonal step from it, **and did not move** | 15-16, FR-ENG-3 | 143 |

289 position disclosures per series, every one of them discarded. They are now
read in `domain/cop_sighting.py` and fused by `BeliefGrid.observe_reach`.

Three properties are load-bearing:

* **Fused after diffusion and scent, not at absorb time.** `diffuse` models the
  move they just made and necessarily smears a point observation over five
  cells; the observation is applied on top to say where that move landed. Fused
  before, the belief peaks on a *neighbour* of the true cell — and a thief
  holding distance 2 from a cell one step off the cop is standing next to it.
* **A claim is a point, a barrier is a set.** The Barrier Law admits five cells
  and we cannot tell which, so a barrier is soft evidence. Reporting it as one
  confident cell would claim knowledge the rules do not give.
* **Confidence is posterior mass, not a per-cell multiplier.** As a multiplier
  it interacts with how many cells sit on each side of the split, and at 49
  cells a barrier's 4-cell reach set finished with *less* mass than the 44 cells
  it had just ruled out. Caught by its own unit test.

A declaration that could not have followed the previous one — further than one
step per elapsed turn — is **downgraded, never refused**. Refusing would let an
opponent freeze our belief by declaring nonsense, which is a cheaper attack than
the bluff being defended against.

Measured: **35/35 survival** against uoh-sqak's recorded line with a peer that
transmits nothing, replayed through the real `absorb_turn` and
`decay_after_full_turn` rather than a hand-rolled belief
(`tests/regression/test_silent_opponent.py`). Sweep unchanged at 360 games,
0 audit failures, 0 disagreements.

> Historic note: the earlier claim that this brain "survives 96-100 % of games
> against a greedy cop" was measured against our own baselines. Given no cop can
> force a capture, such rates describe the baseline, not the brain.

## The scent problem

We cannot stop emitting. What we *can* do is avoid leaving a trail that reads as
a straight line — a predictable trail lets a pursuer extrapolate rather than
follow. Our evasion therefore prefers paths that keep the trail's centroid
ambiguous, which is the same property the cop's lie detector exploits in reverse.

### How much of it we transmit (2026-08-04)

"We cannot stop emitting" is a statement about the *physics*. It is not the same
statement as "we must transmit the whole accumulated field every turn", which is
what we were doing — 25 cells on step 1 of the sealed uoh-sqak log, 29 by step
3, and rising with every cell visited. Our opponent transmitted none of theirs
and beat us 15-60.

`config [emission]` now selects, defaulting to the behaviour we have always had:

| `scent` | what crosses the wire | standing |
|---|---|---|
| `full` | every scented cell (**default**) | unquestioned |
| `window` | only the agreed `pheromone_grid_size` window around us | a defensible reading of the same term — the parameter sizes the emission field, and nothing says the message carries more |
| `none` | an empty map | legal on the text — the book forbids *faking* a trail, not withholding one — but **declare it in negotiation** rather than spring it |

Checked before building, and worth recording:

1. The handshake locks a `model_fingerprint` over the emission *maths* — model,
   centre intensity, decay, grid size. This dial changes none of them, so no
   mode can fail the exchange (rule 23).
2. The hint is sealed **inside** the commit payload, so it is suppressed before
   sealing, never stripped from the wire afterwards. Both halves then carry the
   same empty string and the audit re-hashes clean. Doing it the other way round
   is a `tamper_forfeit` (rules 18-22) — asserted for all three modes in
   `tests/integration/test_emission_modes.py`.
3. Rule 12 caps hints at 15 words and sets no floor, so `hint = false` breaks
   no term.
4. **`window` is not a hiding place.** The centre of a deposit is the agreed
   0.9 and is the unique maximum, so an opponent taking the argmax still reads
   our exact cell. Only `none` hides the current position, and only against an
   opponent with no other fix on us — which, per the section above, a claim or a
   barrier would give them anyway.

Related fix: `ScentField` was being built on its own class defaults, so the
*negotiated* pheromone terms never reached it. The defaults happen to equal the
values in `config/game.json`, which hid it completely — a renegotiated decay
would have been signed, hashed into the fingerprint, and then not used. Now read
from config in `sdk/state_setup.py`.

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
