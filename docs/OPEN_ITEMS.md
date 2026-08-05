# Open items

**Version 1.80 · 2026-08-05**

Things known to be incomplete, with the evidence gathered so far. Recorded here
rather than left implicit, so nobody has to rediscover them — and so a grader
can see we know.

---

## T-2307 — a full six-game series against the reference: CLOSED

Both peers, all six mini-games, roles alternating, every audit `Verified OK`,
both processes exiting 0.

| game | our role | reference | us | audit |
|---|---|---|---|---|
| g01 | thief | survival, najamjad 10-5 | survival, 35 steps | `Verified OK` |
| g02 | police | survival, segal 10-5 | survival, 34 steps | `Verified OK` |
| g03 | thief | survival, najamjad 10-5 | survival, 35 steps | `Verified OK` |
| g04 | police | survival, segal 10-5 | survival, 34 steps | `Verified OK` |
| g05 | thief | survival, najamjad 10-5 | survival, 35 steps | `Verified OK` |
| g06 | police | survival, segal 10-5 | survival, 34 steps | `Verified OK` |

**Final: 45-45.** Reproduce with `uv run python scripts/rehearsal.py --games 6`.

Getting the first three games to run exposed one more self-inflicted defect: at
game 4 **our own inbound guard rejected the opponent's legitimate turn** —
*"inbound rate limit of 120/min exceeded"* — and we then timed out waiting for
the message we had thrown away ourselves. Nothing shorter than a four-game
series would have found it. Fixed, configured rather than hardcoded, and
regression-tested in `tests/integration/test_inbound_throughput.py`.

## RETRACTED — "the cop now converts captures against the reference"

**Every capture number in this section was measured against our own old thief,
and it is fiction.** Kept rather than deleted because a document whose job is to
show what we know cannot quietly drop the thing it got wrong.

The published cop number of a Cartesian product of two trees is 2, so **one cop
cannot force a capture on a 7×7 grid**. A saturated capture rate could only ever
have been describing the opponent's weakness. Confirmed by exact backward
induction over all 4802 perfect-information states: the only cop-win positions
are the 49 where the two already share a cell. Re-swept against the current
thief, `cop.barrier_threshold` across 0.05–0.60 and `cop.lookahead` across 1–4
both give **0/24 at every value**. See `PRD_strategy_cop.md` §"Re-baseline,
2026-08-03", which is the authority; this section is the retraction.

The protocol fixes below are real and still stand. The scoreline is not:

| game | our role | result | us | them |
|---|---|---|---|---|
| g01/g03/g05 | thief | survival | 10 | 5 |
| g02/g04/g06 | police | **capture** | 20 | 5 |

~~**90-30. Six wins from six.**~~ Both sides did agree on every game and every
audit was `Verified OK` — that part is a protocol result and holds. The 90-30
is a statement about the baseline it was played against, not about our cop.

One strategy change and two protocol fixes, in that order of visibility and
reverse order of importance:

* A **capture step outranks a barrier.** Placing one costs us the move, so
  walling while stood next to the thief traded a capture for a wall — and
  against an opponent who does not concede enclosure, for nothing.
* The answer to a capture claim may arrive **at the step it answers**. The
  reference concedes with a final message without advancing its counter, and our
  monotonic guard rejected the one message we were waiting for, stalling the
  game at the exact moment we had won it.
* That answer is a **reply, not a new turn.** Recording its commit as a fresh
  one read as a peer overwriting history, so we filed `tamper_forfeit` against
  an opponent who had just conceded honestly — while they scored the same game
  as our capture. Contradictory reports void a game for both sides.

The middle two are worth noting as a pair: the first produced a score that
*looked* right (90-30) while our own record said `tamper_forfeit`. A result that
comes out right for the wrong reason is not a result.

## COMPETITIVE RISK — our thief loses to a strong cop (unchanged)

**The largest known risk in the project**, found by the E22 analysis and
recorded here rather than left to be discovered by the league table.

| Our thief against | Games | Captured | Survival |
|---|---|---|---|
| the greedy baseline cop | 60 | 0 | **100 %** |
| **our own cop** | 24 | 23–24 | **~4 %** |

The headline "100 % survival" is a statement about the opponent it was measured
against. Any opponent whose cop is as good as ours should be expected to catch
our thief. Sweeping `thief.horizon` across 1–5 does not help: every value is
caught in 23 or 24 of 24 games, differences well inside the confidence
intervals, so this is not a tuning problem.

Both halves of that table have since been re-measured and both moved.

* The thief's "~4 % against our own cop" was a thief that stood still whenever
  it could not name the cop's cell — a defect, not a strategy (T-2488). It is
  fixed; blind survival is now 43/70 on held-out arenas.
* "The cop scores the same points" was the false half. It does not: the theorem
  above puts the cop's floor at **5 points a game (survival), not 20**, and
  `scripts/strategy_smoke.py` currently measures 40/50 rather than the 100 %
  this document used to claim.

So the asymmetry is real but points the other way from how it was filed here:
the thief is the half we can make guaranteeable, and the cop is the half that
cannot be. Quantified in `notebooks/analysis.ipynb` §3.1 and
`PRD_strategy_cop.md`.

## `cop.lookahead` is inert — and the fix is known

Depths 1–4 produce **byte-identical games**. The knob is wired up and
`_diffuse` genuinely changes the belief field (5 cells at depth 1, 33 at depth
4), but the decision never changes, because the diffusion kernel is
**isotropic**: spreading probability equally in all directions rescales the
expected distance of every candidate move by nearly the same amount and
preserves the ranking.

The fix is an **anisotropic kernel** biased by the thief's last inferred
heading, so diffusion predicts where they are going rather than how far they
could have got. This is the single most promising strategy change the analysis
identified.

Not shipped, and the reason originally given here — "the cop is currently at
100 %" — was withdrawn on 2026-08-03. The real reason is stronger: the sweep now
measures `cop.lookahead` at **0/24 captures at every depth** against a correct
thief, so an anisotropic kernel would be tuning a dial that the theorem says
cannot reach the outcome. Worth trying only in an arena that demonstrably has a
gradient (T-2484).

## `negotiation_model` configures nothing

`config/police/game.toml` declares `negotiation_model = "claude-sonnet-5"`, but
no code reads it and `negotiate_prompt` has no runtime caller — 100 % of model
calls are hint-purpose. This is not an oversight in the *code*:
`docs/PRD_negotiation.md` §62 deliberately rejected free-form LLM negotiation as
unbounded and unverifiable. The config key and the unused prompt template are
the leftovers of the rejected design, and they currently imply a per-purpose
routing optimisation that is not happening. To be resolved in the T-2232 docs
review by removing the key or marking the prompt reserved.

---

## T-2104 — lifecycle-artifact assertions in a CI series

Unblocked now that T-2102 is fixed (below). The artifact writer and its schemas
are tested directly; what is missing is asserting all four artifacts appear with
a shared `game_uid` after a real two-process run.

## T-2113 — golden-drift regression

The goldens are verified byte-for-byte today (`test_verifier.py`, and the
pre-match smoke script). What is missing is diffing *interop-run* artifacts
against expected shapes so a silent format drift raises an alarm.

## T-2125 — failure-path traceability table

Every PRD §4 reliability scenario now has a test, but the mapping lives across
several files rather than in one table. Mechanical to produce; not yet done.

## T-2108 — win-rate gate as a scheduled job

The gate itself is implemented and asserted (`test_self_play_harness.py`). The
rates once recorded here — 100 % as cop, 100 % survival as thief — were both
measured against our own baselines and are withdrawn; see the retraction above.
`scripts/strategy_smoke.py` currently reports 40/50 as cop and full survival as
thief against the scripted opponents it ships with. What is missing is running
it nightly rather than on demand.

---

## Recently closed, for context

- **T-2101 / T-2102 — the two-process series now completes.** It was not
  negotiation, as the previous version of this document guessed. Two defects,
  both invisible in-process:

  1. **The inbox step guard never reset between mini-games.** It correctly
     refuses a replayed step, but each mini-game restarts numbering at 1, so
     game 2's opening turn arrived as *"step 1 is stale or replayed, last
     accepted was 11"*. Both peers then waited each other out. **Our agent could
     not play more than one mini-game against anyone** — a series is six.
     `Transport.reset()` is now part of the protocol and `MatchRunner` calls it
     before every mini-game, which also discards a turn that arrived after the
     previous game ended.
  2. **`--config` redirected only the private config.** The signed
     `config/game.json` was always read from the repository, so a per-opponent
     directory paired that match's settings with *our opening proposal* rather
     than the agreed terms. `shared_config_for()` now takes the terms sitting
     beside the private config.

  Verified: a full six-game series between two real OS processes over real
  MCP/HTTP, every game `Verified OK`, roles alternating, both peers agreeing on
  every outcome, 75–75. Regression tests in
  `tests/integration/test_series_continuity.py` exercise the production
  `Inboxes`, and `BlockingLink` now enforces the same sequence guard so this
  class of defect fails in-process from here on — it is the **fourth** time a
  fake being kinder than the wire hid a real bug (ADR-017).
- **T-2110** sweep runner — found `barrier_threshold` was badly tuned; 43-75 % → 100 %.
- **T-2115..T-2118, T-2120** chaos — tunnel restart, total LLM outage, Gmail 429
  storm, clock skew, soak.
- **T-2121..T-2124** quality gates — coverage floor, honest omit list, move
  latency on a 15×15 board, cross-repo byte-identity.
- **T-2126** pre-match smoke — one command, `MATCH READY` in ~50 s.
