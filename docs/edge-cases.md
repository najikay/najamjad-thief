# Edge cases

**Version 1.00 · 2026-07-27**

Every boundary condition the agent is known to handle, consolidated from the
epics, with the test that proves each one. **319 tests** across the suite are
edge-case tests by name; this document organises the ones that matter by the
boundary they defend rather than by the epic that produced them.

Two principles run through the whole table and are worth stating once:

1. **Refuse loudly at the edge, never repair silently in the middle.** A
   malformed message is rejected with its reason at ingress. The alternative —
   guessing what the sender meant — is how a protocol disagreement becomes a
   voided game nobody can explain afterwards.
2. **An opponent's bad day must never become our technical loss, and our bad day
   must never become theirs.** Every wait is bounded and every ending is
   announced rather than assumed.

Run any row with `uv run pytest <file>::<test> -q`.

---

## 1. Protocol ingress — messages from the opponent

The opponent is untrusted by the rules themselves (rules 26–27 permit lying), so
this is the boundary that gets the most attention.

| Case | Expected response | Test |
|---|---|---|
| Message of an unknown kind | Refused, kind named | `test_net/test_inbox.py::test_unknown_message_kind_is_refused` |
| Malformed message body | Rejected with the validation errors | `test_net/test_inbox.py::test_malformed_message_is_rejected_with_errors` |
| **Unknown extra fields** | **Accepted and announced, not rejected** | `test_net/test_inbox.py::test_unknown_fields_are_accepted_but_announced` |
| Missing `commit` | Rejected | `test_protocol/test_schemas_wire.py::test_missing_commit_is_rejected` |
| Empty `commit` string | Rejected | `test_protocol/test_schemas_wire.py::test_empty_commit_is_rejected` |
| Negative step number | Rejected | `test_protocol/test_schemas_wire.py::test_negative_step_is_rejected` |
| Polling an empty inbox | `None`, not an exception | `test_net/test_inbox.py::test_poll_returns_none_when_empty` |

The third row is the one to notice, and it is deliberately the opposite of the
others. **Unknown fields are kept, not refused.** Rejecting them would make every
future extension by any other team a breaking change; refusing a *missing
required* field is safety, refusing an *extra* field is brittleness.

## 2. Game rules — illegal play

| Case | Expected response | Test |
|---|---|---|
| Thief attempts to place a barrier | Refused — barriers are the cop's alone | `test_domain/test_barrier_law.py::test_thief_may_never_place_a_barrier` |
| Barrier placed off the board | Rejected | `test_domain/test_barrier_law.py::test_placement_off_board_is_rejected` |
| Barrier on an existing barrier | Rejected | `test_domain/test_barrier_law.py::test_placement_on_existing_barrier_is_rejected` |
| Opponent claims a non-adjacent move | Rejected as a teleport | `test_domain/test_barrier_law.py::test_opponent_teleport_is_rejected` |
| Malformed or off-board barrier in a turn | Ignored, game continues | `test_domain/test_turn_ingress.py::test_malformed_or_off_board_barriers_are_ignored` |
| Partially malformed scent map | Absorbed as far as it parses, and reported | `test_domain/test_turn_ingress.py::test_a_malformed_scent_map_is_partially_absorbed_and_reported` |

## 3. Capture and endings

The area that produced the most defects, because both peers must agree on how a
game ended or rules 33–35 void it **for both sides**.

| Case | Expected response | Test |
|---|---|---|
| Cop stands on the thief's cell **without** claiming | Not a capture | `test_domain/test_capture.py::test_cop_on_thief_cell_without_claim_is_not_capture` |
| Capture claim naming a different cell | No capture | `test_domain/test_capture.py::test_claim_on_a_different_cell_does_not_capture` |
| Barrier dropped on the thief's cell | Capture | `test_domain/test_capture.py::test_barrier_on_thief_cell_captures` |
| Thief walled in with no legal move | Immobilised — a capture | `test_domain/test_capture.py::test_walled_in_thief_is_immobilised` |
| Thief attempts a barrier capture | Impossible | `test_domain/test_endings.py::test_a_thief_cannot_capture_by_barrier` |
| Claim naming no cell at all | Cannot land | `test_domain/test_turn_ingress.py::test_a_claim_naming_no_cell_cannot_land` |
| Unparseable capture claim | Cannot land | `test_domain/test_turn_ingress.py::test_an_unparseable_capture_claim_cannot_land` |

**The subtle one, found by seeded self-play and not by any unit test:** a capture
claim must be answered against the position the thief occupied *when the claim
was made*, not after it has moved away. Answering late is answering
dishonestly, and it produced contradictory reports that would have voided games.
The answer is now settled at absorb time (`domain/turn_ingress.py`).

## 4. Commit-reveal and audit

| Case | Expected response | Test |
|---|---|---|
| Committing the same step twice | Refused | `test_domain/test_ledger.py::test_committing_a_step_twice_is_refused` |
| Revealing before acknowledgement | Refused | `test_domain/test_ledger.py::test_reveal_before_acknowledge_is_refused` |
| Acknowledging an uncommitted step | Refused | `test_domain/test_ledger.py::test_acknowledging_an_uncommitted_step_is_refused` |
| Opponent reveals without having committed | Refused | `test_domain/test_ledger.py::test_opponent_reveal_without_commit_is_refused` |
| Same payload, different nonces | Different commits | `test_domain/test_crypto.py::test_same_payload_with_different_nonces_gives_different_commits` |
| Keys reordered in the payload | **Same** commit — canonicalisation holds | `test_domain/test_crypto_properties.py::test_commit_is_stable_under_key_reordering` |
| One step tampered in a log | Audit localises *exactly* that step | `test_domain/test_crypto_properties.py::test_audit_localises_exactly_the_tampered_step` |

Three structural rules are asserted by meta-tests rather than by behaviour,
because the risk is a future edit rather than a current bug:

* SHA-256 is computed only in designated modules — `test_crypto_review.py::test_sha256_is_only_computed_in_designated_modules`
* commits are compared with `compare_digest`, never `==` — `::test_no_module_compares_a_commit_with_plain_equality`
* nonces come only from `secrets` — `::test_nonces_come_from_the_secrets_module_only`

## 5. Negotiation

| Case | Expected response | Test |
|---|---|---|
| Opponent proposes *lowering* a minimum | Rejected, not countered (rule 12) | `test_negotiation/test_playbook_flow.py::test_lowering_a_minimum_is_rejected_not_countered` |
| Proposal crossing a red line | Rejected **with a reason** | `test_negotiation/test_playbook_flow.py::test_red_lines_are_rejected_with_a_reason` |
| Proposal containing terms we do not know | Ignored, not refused | `test_negotiation/test_playbook_flow.py::test_unknown_terms_are_ignored_rather_than_refused` |
| Peer's contract hash does not match ours | Refuse and abandon | `test_negotiation/test_playbook_flow.py::test_a_mismatched_peer_contract_refuses_and_abandons` |
| A fixed score altered in the contract | Refused | `test_negotiation/test_contract.py::test_an_altered_fixed_score_is_refused` |
| The move set altered | Refused | `test_negotiation/test_contract.py::test_an_altered_move_set_is_refused` |

## 6. Network, deadlines and rate limits

| Case | Expected response | Test |
|---|---|---|
| Remaining time on an expired deadline | Clamped at 0, never negative | `test_net/test_deadline.py::test_remaining_never_goes_negative` |
| A call that fails then succeeds | Retried, then returns | `test_net/test_deadline.py::test_await_value_retries_then_succeeds` |
| Burst beyond the permitted rate | **Waits**, does not fail | `test_shared/test_gatekeeper.py::test_burst_beyond_the_rate_waits_instead_of_failing` |
| Rate-limit config above the Appendix F ceiling | Refused at load | `test_shared/test_rate_limits.py::test_too_much_concurrency_is_refused` |
| Backoff shorter than the mandated minimum | Refused at load | `test_shared/test_rate_limits.py::test_too_short_backoff_is_refused` |
| Wall clock jumps (NTP, sleep/resume) | Deadlines unaffected — `time.monotonic` | `test_chaos_services.py::test_deadlines_are_immune_to_wall_clock_skew_by_construction` |
| Tunnel process dies mid-series | Restarted, **hostname preserved** | `test_chaos_services.py::test_a_tunnel_that_dies_is_restarted_and_keeps_its_hostname` |

The rate-limit rows encode a mistake worth remembering: we first applied our own
limiter to *opponent* traffic at 30 requests a minute. The gatekeeper exists to
be a good citizen towards Anthropic and Gmail; throttling our own protocol
traffic protects nobody and can push a reply past the opponent's 30-second
deadline, forfeiting a game to our own code.

## 7. LLM and prompt injection

| Case | Expected response | Test |
|---|---|---|
| Hint containing an injection attempt | Detected; confidence discounted | `test_llm/test_injection_guard.py::test_a_detected_attack_has_its_confidence_discounted` |
| Hint longer than the agreed word cap | Cut to the cap | `test_llm/test_injection_guard.py::test_an_over_long_hint_is_cut_to_the_agreed_cap` |
| A huge payload | Capped by characters first | `test_llm/test_injection_guard.py::test_a_huge_payload_is_capped_by_characters_first` |
| Control characters and newlines | Neutralised | `test_llm/test_injection_guard.py::test_control_characters_and_newlines_are_neutralised` |
| Both paid providers down | Template floor; game continues at zero tokens | `test_chaos_services.py::test_a_total_llm_outage_falls_through_to_the_template_floor` |
| Every provider down, no floor configured | Raises — there is no honest answer to invent | `test_chaos_services.py::test_every_provider_failing_raises_rather_than_returning_nothing` |
| A lie rate outside [0,1] | Refused | `test_llm/test_template_and_guard.py::test_an_impossible_lie_rate_is_refused` |

## 8. Reporting

| Case | Expected response | Test |
|---|---|---|
| A scope wider than `gmail.send` | Never requested (rule 30) | `test_reporting/test_gmail_sender.py::test_only_the_send_scope_is_ever_requested` |
| Send response carrying no message id | Treated as **failure**, not success | `test_reporting/test_gmail_sender.py::test_a_response_without_an_id_is_treated_as_failure` |
| Gmail 429 storm | Parked as `UNSENT_*` **and** raised | `test_chaos_services.py::test_a_429_storm_dead_letters_instead_of_resending_blindly` |
| `agreement: null` in an outgoing report | Refused at the egress gate | `test_protocol/test_egress_gate.py::test_null_agreement_is_refused` |
| A truthy look-alike (`"false"`, `1`) for confirmation | Refused | `test_protocol/test_egress_gate.py::test_truthy_lookalikes_are_refused` |

`send_report` parks the report **and** re-raises, deliberately. A caller must not
be able to treat an undelivered report as sent — rule 35 punishes not reporting
as heavily as reporting falsely.

The `agreement: null` row is the direct fix for the Assignment 6 defect where
`null` was used as a stand-in for "we forgot to reconcile".

## 9. Replay and artifacts

| Case | Expected response | Test |
|---|---|---|
| Log file missing | A load error, not a crash | `test_replay/test_loader.py::test_a_missing_file_is_a_load_error_not_a_crash` |
| Record missing its nonce | Fails **verification** rather than loading as valid | `test_replay/test_loader.py::test_a_record_missing_its_nonce_fails_verification_rather_than_loading` |
| Flattened record missing one sealed field | Still loads | `test_replay/test_loader.py::test_a_flattened_record_missing_one_sealed_field_still_loads` |
| Normalisation applied to a tampered record | **Never** turns it into a pass | `test_replay/test_loader.py::test_normalisation_never_turns_a_tampered_record_into_a_passing_one` |
| Stepping outside the log's range | Refused, with the valid range | `test_replay/test_app.py::test_a_step_outside_the_log_is_refused_with_its_range` |
| Opening a missing file in the viewer | Reports why, keeps the current log | `test_replay/test_app.py::test_opening_a_missing_file_reports_why_and_keeps_the_current_log` |

The fourth row guards the most dangerous function in the replay loader.
Normalisation exists to accept the several shapes different teams emit; the
moment it is permissive enough to "fix" a record into verifying, the audit
becomes worthless.

## 10. Configuration and startup

| Case | Expected response | Test |
|---|---|---|
| Private config absent | Boot failure | `test_shared/test_config.py::test_a_missing_private_config_is_a_boot_failure` |
| Unsupported config version | Refuses to boot | `test_shared/test_config.py::test_an_unsupported_version_refuses_to_boot` |
| A required contract value absent | Fails at load | `test_shared/test_config.py::test_a_required_contract_that_is_absent_fails` |
| Signed contract disagreeing with a private value | Contract wins | `test_shared/test_config.py::test_the_signed_contract_overrides_private_values` |
| A plugin path naming something nonexistent | Fails **while wiring**, path quoted | `test_sdk/test_plugins.py::test_a_bad_plugin_path_fails_while_wiring_not_mid_match` |
| Replay of a tampered log via the CLI | Exit code **1**, not 2 | `test_cli/test_verbs.py::test_replay_exits_one_on_a_tampered_log` |
| Replay of a missing log via the CLI | Exit code **2** | `test_cli/test_verbs.py::test_replay_exits_two_on_a_missing_log` |

The last two rows are a single decision: an audit verdict must never be
mistaken for a typo. "The log says TAMPERED" and "you typed the filename wrong"
are different facts and get different exit codes.

---

## Edge cases we know we have *not* covered

Listed because an incomplete list presented as complete is worse than no list.

| Gap | Why it is open |
|---|---|
| A two-process series completing unattended | `docs/OPEN_ITEMS.md` — 101 messages accepted, peers still wait each other out |
| Opponents other than ourselves and the greedy baseline | Nobody has played us but us and the reference simulator |
| Persuasive value of our bluffs | Measurable only against a parser we did not write |
| macOS | Never run there |
