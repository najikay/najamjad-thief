# Failure-path traceability

**Version 1.00 · 2026-07-28 · PRD §4 (Reliability)**

Every failure the PRD says we must survive, mapped to the test that proves we
do. The PRD states the requirement in one line; this says where it is kept.

The mapping is one-directional on purpose: a requirement with no test is a
finding, and a test with no requirement is fine — most of our tests exist
because something broke, not because a document asked for them.

---

## PRD §4 — "Survive: … Every failure path has a test."

| Failure path | What must happen | Test |
|---|---|---|
| **Opponent crashes mid-game** | The series ends cleanly; no exception escapes the loop | `test_chaos_match.py::test_an_opponent_that_crashes_mid_series_leaves_us_with_a_clean_result` |
| **Opponent stops revealing at audit** | Recorded as `AUDIT SKIPPED`, never `TAMPERED` — silence is not forgery | `test_chaos_match.py::test_a_peer_that_stops_revealing_still_lets_us_record_the_game` |
| **Tunnel drops** | Restarted, and the **hostname survives**, so their saved URL still works | `test_chaos_services.py::test_a_tunnel_that_dies_is_restarted_and_keeps_its_hostname` |
| **Tunnel stopped** | The child process is terminated — an unstopped tunnel points a public name at a dead port | `test_chaos_services.py::test_stopping_a_tunnel_terminates_the_child` |
| **Total LLM outage** | Falls through to the zero-token template floor; the game continues | `test_chaos_services.py::test_a_total_llm_outage_falls_through_to_the_template_floor` |
| **Every provider fails, no floor** | Raises rather than inventing an answer | `test_chaos_services.py::test_every_provider_failing_raises_rather_than_returning_nothing` |
| **Gmail 429 storm** | Parked as `UNSENT_*` **and** re-raised — undelivered must never read as sent | `test_chaos_services.py::test_a_429_storm_dead_letters_instead_of_resending_blindly` |
| **Malformed inbound payload** | Rejected with its reason; the loop survives | `test_fault_garbage.py`, `test_inbox.py::test_malformed_message_is_rejected_with_errors` |
| **Replayed turn** | Refused as stale | `test_series_continuity.py::test_a_replay_inside_a_mini_game_is_still_refused` |
| **Clock skew / NTP correction** | Deadlines unaffected — `time.monotonic` cannot go backwards | `test_chaos_services.py::test_deadlines_are_immune_to_wall_clock_skew_by_construction` |
| **Missed deadline** | Clean protocol resolution, never a hang | `test_deadline.py::test_expired_reports_when_the_budget_is_spent`, `test_chaos_services.py::test_a_deadline_expires_rather_than_wrapping_when_time_runs_past_it` |
| **Prompt injection in a hint** | Sanitised, fenced, confidence discounted | `test_injection_guard.py::test_a_detected_attack_has_its_confidence_discounted` |
| **Long series soak** | Queues drain to zero; the event log does not degrade | `test_chaos_services.py::test_three_consecutive_series_leave_no_residue` |
| **Fresh clone, no workspace** | Created on first write | `test_chaos_services.py::test_the_workspace_path_is_not_required_to_exist_up_front` |

## Failures the PRD did not anticipate

Found by running the thing rather than by reading the requirement. Listed
separately because pretending they were foreseen would misrepresent how they
were found.

| Failure path | What must happen | Test |
|---|---|---|
| **Our own inbound guard throttles honest play** | A full match of traffic never trips it | `test_inbound_throughput.py::test_a_full_match_of_traffic_is_never_rate_limited` |
| **Next mini-game's opening turn read as a replay** | Step 1 opens a new game | `test_series_continuity.py::test_step_one_opens_a_new_mini_game_rather_than_reading_as_a_replay` |
| **The reset deletes the turn already in hand** | The opening turn is kept, leftovers dropped | `test_series_continuity.py::test_starting_a_sub_game_keeps_the_opening_turn_and_drops_the_leftovers` |
| **A concession arriving at the step it answers** | Accepted as a reply, not a duplicate commit | `test_capture_conversion.py::test_a_concession_is_absorbed_as_a_reply_not_a_duplicate_commit` |
| **A per-match config directory loads the wrong terms** | The terms beside it win | `test_series_continuity.py::test_a_per_match_config_directory_brings_its_own_agreed_terms` |
| **A config key the brain does not accept** | Fails at wiring, naming the key | `test_plugins.py::test_a_bad_plugin_path_fails_while_wiring_not_mid_match` |
| **Artifacts drift from the lecturer's shape** | Compared field-by-field against their samples | `test_golden_drift.py::test_the_result_keeps_every_top_level_field_the_sample_has` |

## The gates themselves

A control that has only ever seen clean input is an assumption.

| Gate | Proven to reject | Test |
|---|---|---|
| File size | An oversize file | `test_gates_bite.py::test_the_file_size_gate_rejects_an_oversize_file` |
| Repo rules | `pip install`, a bare interpreter call, a swallowed exception, a leaked key | `test_gates_bite.py::test_the_repo_rules_gate_rejects_each_forbidden_pattern` |
| Repo rules | A secret file by name | `test_gates_bite.py::test_a_committed_secret_file_is_rejected_by_name` |
| Repo rules | A violation that is **not committed yet** | `test_gates_bite.py::test_the_repo_rules_gate_sees_a_file_that_is_not_committed_yet` |
| Local runner | Drifting from CI | `test_check_all.py::test_every_ci_command_is_covered_by_the_local_runner` |

## Coverage of this table

`tests/unit/test_docs/test_traceability.py` asserts every test named here
exists. A traceability table whose references have rotted is worse than none: it
reads as evidence and is not.
