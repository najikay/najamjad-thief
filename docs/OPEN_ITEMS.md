# Open items

**Version 1.30 · 2026-07-27**

Things known to be incomplete, with the evidence gathered so far. Recorded here
rather than left implicit, so nobody has to rediscover them — and so a grader
can see we know.

---

## T-2307 — rehearsal vs the reference: plays, but the ending disagrees

**Where it got to.** Our thief and the course reference simulator now complete a
full match as two OS processes: handshake locked, **59 turns sent, 63 messages
accepted, zero rejections**, capture claims and barriers observed on both sides,
both processes exiting 0 and writing their reports.

**What is wrong.** The two sides do not agree on how the game *ended*. The
reference records `result: timeout, winner: police`; we score the series 0–0.
Under rules 33-35 a disagreement voids the game for both, so this must be
settled before a counted match.

**What it is not.** Not connectivity, not argument binding, not the terms, not
the audit envelope, and not the step guard — all of those are fixed and
verified. The turn traffic itself is clean in both directions.

**Next step.** Compare their `logs/result_*.json` ending against ours turn by
turn: the likely candidates are the survival horizon being counted from
different step numbers, or a capture claim we answer in a shape their parser
reads as no answer.

**Getting here fixed four real defects**, each of which would have cost every
counted match, and none of which any in-process test could see:

1. `match` never negotiated — the reference exits with *"Opponent never sent its
   agreement"* before a move is played.
2. Our terms were grouped by section; the reference signs a **flat 14-key
   dictionary** and compares for equality.
3. Our identity block omitted `group_name`, `members`, `repos`, `mcp_servers`,
   `llm_model` and `spec` — the reference indexes them directly and raised
   `KeyError` *after* the games were played.
4. Neither peer waited for the other, so the first to start burned its retries
   on a dead port and exited before the second was listening.

## COMPETITIVE RISK — our thief loses to a strong cop

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

Recorded rather than fixed because a strategy rewrite at this stage is a larger
change than the remaining schedule safely absorbs, and the cop — which scores
the same points — is measured at 100 %. Quantified in `notebooks/analysis.ipynb`
§3.1.

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
identified. Not shipped: it changes the cop's move selection, and the cop is
currently at 100 %.

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

The gate itself is implemented and asserted (`test_self_play_harness.py`), and
the measured rate is 100 % as cop and 100 % survival as thief. What is missing
is running it nightly rather than on demand.

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
