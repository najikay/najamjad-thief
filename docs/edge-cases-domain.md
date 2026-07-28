# Domain edge cases

**Version 1.00 · 2026-07-28**

Boundary conditions in the *rules themselves* — the board, movement, capture,
scent and scoring. `docs/edge-cases.md` covers the protocol and the services
around a match; this covers the game.

Every row names a test. Where a property holds for **all** positions rather than
a chosen one, it is stated as a property and checked with hypothesis over
generated boards, because the cases we thought of are exactly the ones that were
never going to catch us out.

---

## 1. The board and movement

| Case | Behaviour | Test |
|---|---|---|
| Any position, any move sequence | Never leaves the board | `test_movement_properties.py::test_an_agent_never_leaves_the_board` |
| Any barrier layout, any sequence | Never stands on a barrier | `::test_an_agent_never_stands_on_a_barrier` |
| A single legal move | Lands somewhere legal — the induction base for any path | `::test_every_legal_move_lands_somewhere_legal` |
| An illegal move | **Raises**, never clamps | `::test_an_illegal_move_raises_rather_than_moving_us` |
| Adding a barrier | Can only *remove* options, never add | `::test_walling_a_cell_never_widens_the_options` |
| The same sequence twice | Ends in the same cell | `::test_the_same_sequence_always_ends_in_the_same_cell` |

Clamping an illegal move instead of raising is the tempting shortcut and the
wrong one: it would let an opponent's bad move quietly become our position, and
the audit reveals the sealed truth at the end of the game.

`STAY` is never blocked (`::test_staying_put_is_always_available`). An agent
with no other option must still be able to take a turn — immobilisation is
decided over the *mobile* moves (book rule 47), which is a different question
from "can this agent act".

## 2. Corners, corridors and traps

| Case | Behaviour | Test |
|---|---|---|
| Corner start | Two exits, both legal; no special-casing | `test_board.py`, `test_movement.py` |
| Thief in a one-exit cell | Not yet captured — one exit is still an exit | `test_capture.py::test_walled_in_thief_is_immobilised` |
| Thief with zero mobile moves | Captured by immobilisation (rule 47) | `test_capture.py::test_walled_in_thief_is_immobilised` |
| Barrier dropped on the thief's own cell | Capture, but only once the **thief confirms** | `test_endings.py::test_a_barrier_on_the_believed_thief_does_not_end_the_game_by_itself` |
| Thief at the horizon in a pocket | Moves toward room, never trades it away | `test_thief_endgame.py::test_at_the_horizon_the_thief_moves_out_of_a_pocket_toward_room` |

The fourth row is the one that cost us a rehearsal. A cop that *concludes* a
barrier capture from its own belief agrees with a thief that shares the rule and
disagrees with one that does not — and a game the opponent does not agree ended
is void for both (rules 33-35), which scores zero. A capture is a claim the
thief confirms.

## 3. Capture and claims

| Case | Behaviour | Test |
|---|---|---|
| Cop on the thief's cell **without** claiming | Not a capture | `test_capture.py::test_cop_on_thief_cell_without_claim_is_not_capture` |
| Claim naming a different cell | No capture | `::test_claim_on_a_different_cell_does_not_capture` |
| Claim naming no cell / unparseable | Cannot land | `test_turn_ingress.py::test_a_claim_naming_no_cell_cannot_land` |
| Thief answers a claim | Honestly, from its **true** cell, settled at absorb time | `test_turn_ingress.py` |
| Thief attempts a barrier capture | Impossible — barriers are cop-only | `test_endings.py::test_a_thief_cannot_capture_by_barrier` |
| Answer arriving at the step it answers | Accepted; not a replay | `test_capture_conversion.py::test_a_claim_answer_may_arrive_at_the_step_it_answers` |

Answering a capture claim *after* moving away would be answering dishonestly.
The answer is settled when the claim is absorbed, not when we next speak.

## 4. Quota and barriers

| Case | Behaviour | Test |
|---|---|---|
| Quota exhausted (0 left) | No barrier placed; move instead | `test_cop_tactics.py::test_an_exhausted_quota_places_nothing` |
| Barrier on an existing barrier | Refused — buys nothing, costs quota | `::test_a_barrier_is_never_placed_on_an_existing_one` |
| Barrier on our own cell | Refused — would immobilise the pursuer | `::test_a_placed_barrier_is_never_placed_on_ourselves` |
| Off-board placement | Rejected | `test_barrier_law.py::test_placement_off_board_is_rejected` |
| Weak belief | No barrier — a wall on a guess fences *us* out | `test_cop_tactics.py::test_a_barrier_is_not_spent_on_weak_evidence` |
| Uniform belief | No barrier — flat belief is the same as knowing nothing | `::test_a_uniform_belief_places_no_barrier` |

## 5. Scent

| Case | Behaviour | Test |
|---|---|---|
| Unscented cell | Reads zero, not absent | `test_scent.py::test_unscented_cells_read_zero` |
| Intensity out of range | Rejected at deposit | `::test_deposit_rejects_out_of_range_intensity` |
| Repeated decay | Never negative, never above the ceiling | `::test_values_never_exceed_the_ceiling_or_go_negative` |
| A very old trail | Reaches **exactly** zero, not a rounding floor | `test_scent.py` |
| Snapshot on the wire | Intensities only — never a coordinate | `::test_snapshot_omits_zero_cells_and_never_leaks_a_position` |
| All cells equally scented | Thief still moves legally | `test_thief_endgame.py::test_an_all_fresh_scent_field_does_not_paralyse_the_thief` |

The fourth row was a real defect: relative decay rounded to three decimals never
reached zero, so dead trails polluted belief forever. Fixed with an explicit
epsilon, and the test asserts the limit rather than the direction — every test
we had asserted decay *decreased*, which the buggy version also did.

## 6. Scoring and endings

| Case | Behaviour | Test |
|---|---|---|
| Survival reached | Announced on our own move, not merely recorded | `test_orchestrator.py`, `test_series_continuity.py` |
| Both peers score the same game | Identical end reason, or the game is void | `test_self_play_harness.py::test_the_two_peers_never_disagree_about_how_a_game_ended` |
| A drawn mini-game | No winner, `tie: true` — not a default winner | `test_match_filing.py::test_a_drawn_mini_game_has_no_winner_rather_than_a_default_one` |
| Roles across a series | Alternate every mini-game | `test_match_series.py::test_roles_alternate_and_are_opposite_between_peers` |
| A game that times out | Audit **skipped**, not failed | `test_chaos_match.py::test_a_peer_that_stops_revealing_still_lets_us_record_the_game` |

## 7. What is deliberately undefined

Stated so nobody mistakes an interpretation for a rule.

* **The step cap and the survival threshold are the same number** (35), and the
  book leaves the outcome at the cap undefined. We treat reaching either as
  thief survival (PRD A2, book Open-Q 5) and say so in the negotiated terms.
* **A tie inside a mini-game** cannot occur — every ending names a winner or is
  a survival. Series-level ties can, and score 2 apiece.
* **A thief that never moves** is legal. It is a bad idea and the scent field
  makes it a fatal one, but nothing in the rules forbids it.
