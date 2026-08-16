# Mechanism PRD — thief strategy

**Version 1.10 · 2026-08-05 · FR-STR-5..7 · ADR-007**

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

The sum survives only for a belief that names a cell. A peer that transmits
nothing is handled by `strategy/blind.py` instead — see "Playing blind" below,
and note that handing the sum a flat belief was itself a defect, not a fallback.

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

| declaration | what it tells us | rule | seen in one series | used |
|---|---|---|---|---|
| barrier | the cop is on that cell or one orthogonal step from it, **and did not move** | 15-16, FR-ENG-3 | 143 | yes |
| capture claim | where the cop asserts **the thief** is — *not* where the cop is | 21-22 | 146 | no |

Barrier declarations are read in `domain/cop_sighting.py` and fused by
`BeliefGrid.observe_reach`.

**Capture claims are deliberately not used, and the first version of this work
used them wrongly.** `capture.answer_capture_claim(true_thief_cell,
claimed_cell)` settles the semantics from our own code: a claim names the cell
the cop asserts the *thief* occupies. That equals the cop's own cell only for a
claim that lands, and a cop may claim speculatively. uoh-sqak happened to claim
only their own cell, which is the sole reason believing it looked right against
their recorded line. Measured cost of believing it: against a cop claiming one
row off, the thief went from 35/35 to captured at step 13; against one claiming
our own cell it was blinded every turn, because 0.99 of the mass landed on our
square and the next `exclude()` deleted it. Both were worse than ignoring claims
outright — and the second is a free attack, since our own scent hands any
opponent our exact cell.

Three properties are load-bearing:

* **Fused after diffusion and scent, not at absorb time.** `diffuse` models the
  move they just made and necessarily smears a point observation over five
  cells; the observation is applied on top to say where that move landed. Fused
  before, the belief peaks on a *neighbour* of the true cell — and a thief
  holding distance 2 from a cell one step off the cop is standing next to it.
* **A barrier is a set, never a point.** The Barrier Law admits five cells and
  we cannot tell which, so a barrier is soft evidence. Reporting it as one
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

> That 35/35 is **geometry, not evasion**, and reporting it alone was
> misleading. Their sweep ends at `[1,6]` and never enters the corner our thief
> parked in, so the number survives with the barrier fix disabled entirely. It
> is kept as a non-regression floor and is not evidence the policy works.

## Playing blind (2026-08-05)

Reading barrier declarations narrows the belief; it does not make it name a
cell, and against a peer that places few barriers the thief is still blind. So
the question the previous section never answered is what to actually *do* then —
and the honest answer had been "run the informed policy on a flat belief", which
is worse than doing nothing.

**Two defects, both measured, neither a matter of tuning.**

1. The fallback consulted the belief through `expected_distance` and
   `_worst_case`. Under a flat distribution neither measures the opponent:
   expected distance measures board geometry and is maximised at the corners,
   and `_worst_case` took `max()` of a flat dict, which returns whichever key
   CPython iterates first — always the cop's start. Together they invented a cop
   in one corner and paid the thief to flee to the opposite one. From `[3,3]`
   against a silent peer: `[6,5]` in five steps, then STAY for the remaining
   thirty. Six distinct cells in a whole mini-game. That is the archived
   immobility, and it was never a preference for standing still.
2. `TurnFacts.scent` carried the **opponent's** field, while the term consuming
   it asks where *we* have been. Against a peer that emits nothing it was a grid
   of zeros. Now `TurnFacts.own_scent` carries ours and `scent` keeps theirs.

**What replaces it.** `cop_start` is a negotiated term, fixed before the first
move and identical in both configs — not a disclosure a peer can withhold — and
movement is one cell per turn (FR-ENG-2). Together they bound the cop inside a
Manhattan ball of radius `step` around its start, so a cell outside it is
*provably* vacant for a known number of turns. `strategy/blind.py` scores room,
minus the trap penalty, plus that warning, **capped at two turns**: the
uncapped version chases the far corner, and a corner has two exits. The bound
goes vacuous past the board's diameter, at which point it contributes a constant
and room decides — real early, gone later, never fabricated.

**What is deliberately absent**, each because it was measured to cost survivals:
`corridor_risk` (20/43 with, 27/43 without — it needs a cop whose position we
know), and our own trail (27/43 with, 36/43 without).

**Why a near-best band rather than the argmax.** Over 70 held-out arenas,
changing only which move wins a *tie* moved survival by fifteen games — against
a fixed line, blind survival is mostly luck about which cell you park in, so
optimising that number is fitting noise. The threat we have actually measured is
the other one: a scripted opponent solved our previous thief 3/3 by replaying
one line, and within a series a peer watches five sub-games before the sixth.
`VARIATION_BAND` spends a survival we cannot rely on to buy variation we can.

| policy | held-out survival | vs an opponent who studied game 1 |
|---|---|---|
| old fallback (phantom cop) | 15/43 | — |
| blind, argmax | 44/70 | 10/100 |
| **blind, banded (shipped)** | **43/70** | **32/100** |

Honest limits: a silent opponent still reads *our* scent, so they see us while
we do not see them. That asymmetry is not fixable by policy, and no blind thief
survives every line — both the mobile and the static variants died 0/20 to a cop
that predicts our moves outright. Movement is not evasion when you are
predictable; the band is what answers that, not the motion.

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

## Breeding strategies, and what it found (2026-08-04)

`scripts/evolve.py` implements the selection rule literally: everyone plays, the
winner survives untouched, a loser mutates, and a lineage past two consecutive
losses is redrawn rather than nudged again. `strategy/genome.py` is the
parameterisation; `strategy/tournament.py` is the selection.

**In-process and deterministic rather than a swarm of LLM agents.** A duel is
milliseconds, so this plays thousands of games in the time a handful of agents
would take to play a dozen, and every run replays exactly from its seed. Rule 49
means a grader can re-run it, and a tuning result nobody can reproduce is an
opinion with a number attached.

**A genome may not switch the safety invariant off.** The distance-2 rule and
the exact solve are theorems, not preferences. A search allowed to discard them
would spend its budget rediscovering that being captured is bad. Evolution tunes
the heuristics that choose *among* provably safe moves, and nothing else.

### The result: saturated, and that is the honest answer

    arenas=3 ceiling=105
    shipped   : 105/105
    best found: 105/105

The shipped configuration already survives every arena in full — uoh-sqak's
recorded sweep, the same sweep against a silent peer, and a direct chaser — so
**there is no gradient to climb**. Ten rounds of eight lineages found nothing
better because nothing better is measurable here.

That is consistent with the theorem rather than a defect in the search: one cop
provably cannot catch a careful thief on a 7×7, so a sound thief policy scores
the ceiling against any single pursuer and the fitness landscape is flat by
construction. `test_a_gradient_is_actually_climbed` keeps the instrument honest
by giving it a landscape that *does* have a slope and asserting it climbs it.

**What this means for effort.** The thief is done; further tuning of it cannot
be justified by measurement. The cop is where the points are — it is worth its
5-point survival floor and both of its dials measured 0/24 at every value
against a correct thief. Any future search should be pointed there, and needs
arenas that are not already saturated to be worth running at all.

## Defending against a wall built over several turns — tried, rejected (2026-08-16)

`adversarial_room` scores a landing by the room left after the cop's **single**
most damaging next barrier. That is a defence against one wall, and a cop does
not seal a room with one wall: it builds one over several turns. Conway's angel
problem is the frame — an angel of power 1 loses to a devil blocking one square
a turn by *progressive* encirclement, and our thief moves less than that angel.

The two-cut version works, on the number it was aimed at. Against a cop walling
flat-out (`barrier_threshold` 0.22 with no patience), over 40 starting
positions: one cut deep is captured **40 of 40** at mean step 27.5, two cuts
deep **0 of 40**, for 13.6 ms.

**Rejected on how it survives.** It spends **78.6% of its steps in one of the
four corner cells**, against 14.5% for the shipped version, and 87.7% on an
edge. Corner camping is the exact shape that lost mini-games to uoh-sqak (herded
along row 6 and killed at [6,0]) and to vibecode (sat on (6,5)/(6,6) from step 4
and walled in at 14). `LOCAL_ROOM_RADIUS` and the tie-break rewrite exist to
stop it. Buying survival against one synthetic cop by reintroducing it is the
flattering-number trade, and the number would have looked excellent in a commit
message.

**The exposure it was aimed at is real and stays open.** Against a cop that
spends its barriers freely we are captured 40 of 40 — and uoh-sqak, who beat us
15-60, spent all fourteen. The honest fix has to keep the room *and* the
distance rather than trading one for the other; a defence that answers
encirclement by sitting in the most encirclable cell on the board has not
answered it. Open, not solved.


## The forced-win table, and why the invariant is a 4x4 — 2026-08-16

Everything below is exact: backward induction over every position of the named
board, thief moves first, both sides may stay, capture on co-location either
way, and the cop may spend a barrier *instead* of moving under the Barrier Law.
No heuristics, no sampling.

**Which boards the cop wins, and at what budget.** The entry is the fewest
barriers in hand that force a capture:

|       | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|
| **2** | 1 | 1 | 1 | 1 | 2 | 3 |
| **3** | 1 | 1 | 2 | 4 | 4 | 4 |
| **4** | 1 | 2 | 5 | 5 | 6 | 6 |
| **5** | 1 | 4 | 5 | 6 | 8 | 9 |
| **6** | 2 | 4 | 6 | 8 | 10 | 10 |
| **7** | 3 | 4 | 6 | 9 | 10 | 11 |

Read the diagonal boundary: **width decides, not area.** A 3x5 pocket is fifteen
cells and falls to two barriers; a 4x4 is sixteen and needs five. Everything
three or fewer cells wide collapses cheaply, and 4x4 is the first shape that
does not.

**Our board is 7x7 and the cop holds 14.** The table says 11 suffice, and the
recipe composes: wall a column of 7 to halve it, wall a column of 3 to make 3x6,
wall another to make 3x3 and 2x3, each a forced win with one barrier still in
hand. 13 spent of 14. So on barrier count alone this game is a cop win, and any
thief that treats survival as guaranteed is wrong.

**What saves us is turns, not barriers.** A barrier costs the turn it is placed
in, and the Barrier Law means walking a line places roughly one wall per two
turns. The halving recipe costs about 23 turns of building plus a 6-turn
endgame plus the approach — around 31 of the 35 available, before the thief
interferes at all, and it can interfere by standing on the cell the cop wants
(walling the thief's own square is forbidden). The cheap plans — an 11-turn 3x3
corner seal, a 9-turn 2x3 — fit comfortably but need the thief already in the
corner.

**Hence the invariant.** Every winning shape in that table is at most three
wide, so a thief that always keeps a 4x4 block *reachable before the cop* can
never be in one. That is `territory.keeps_a_free_square`, and the "before the
cop" half is the whole of it: at the moment of every real loss in our archive
the board still held open 4x4s, all of them on the cop's side. Measured across
the 61 archived opponent cop lines, requiring the square to merely exist scores
54; requiring it reachable first scores 60; adding the graded fallback for
positions where no square survives scores **61 of 61, every one at 35 steps**.
