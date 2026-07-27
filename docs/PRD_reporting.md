# Mechanism PRD — reporting and artifacts

**Version 1.00 · 2026-07-26 · FR-REP-1..6**

## Problem

The match result is the graded output, and Assignment 6 lost it twice over: the
report was never sent when we were not the initiating side, and the artifact it
would have carried recorded `agreement: NULL` — not "we disagreed", not "still
open", but a null nobody noticed until after the deadline.

Rule 35 punishes *not* reporting as heavily as reporting falsely. So the
requirement is not "send an email"; it is **produce the evidence, prove it went,
and make its absence impossible to miss.**

## The four artifacts

| Artifact | When | Contents |
|---|---|---|
| `declaration_<game_id>.json` | before play | teams, repos, hardware, models (rule 53) |
| `config_<game_id>_g<NN>.json` | per mini-game | the agreed terms and their SHA-256 |
| `log_<game_id>_g<NN>.json` | per mini-game | the sealed chain, revealed at audit |
| `result_<game_id>.json` | end of match | scores, winner, mutual agreement |

All four share a `game_uid` so files from different matches can never be mixed —
the filename is derived from the `game_id`, never hand-written.

## Egress gate

Nothing is written before it validates. `validate_egress` runs the artifact's
pydantic model *first*, then persists; the inverse order would leave a malformed
file on disk that a grader reads before we notice.

The gate is scoped per artifact kind. An earlier version demanded an agreement
block on every artifact including the declaration, which cannot have one — a
gate that cries wolf is a gate people switch off.

## Reconciliation

Before sending, we compare our result with the opponent's:

| Status | Meaning | May we send? |
|---|---|---|
| `agreed` | Both sides match | yes |
| `no_reply` | They never answered | **yes** — silence must not stop us filing (rule 35) |
| `mismatch` | We disagree | not without an operator decision; the diff is surfaced |

`confirmed` is a real boolean, and `agreement` is `null` **only** while genuinely
undecided. `bool(None)` used to evaluate to `False`, which would have filed a
confident "not agreed" for a match merely forgotten — that path now raises.

## Gmail

`gmail.send` scope only (rule 30). Not `modify`, not `readonly` — the A6 token
carried `gmail.modify`, which grants read and write over a personal mailbox for
no reason. There is no receive path at all; MCP reconciliation replaced it
(ADR-013).

A send failure is not silent: the report panel turns red, names the reason, and
the artifact is written regardless. **A dead letter is recoverable; a missing
artifact is not.**

## Archiving

`build_archive` bundles artifacts, event log, config and screenshots into one
file, and **refuses to include secrets** — by pattern, not by allow-list, because
the failure is one-directional: a missing log is an inconvenience, a `token.json`
inside a zip that reaches an opponent is an incident. What it withheld is listed
rather than silently dropped.

## Metrics

Reconciliation status, delivery state, message id, and `needs_attention` — all on
the dashboard's report panel. That panel exists specifically so the A6 failure
(reconciled, never sent, nobody knew) is visible without opening a log.

## Alternatives considered

| Option | Why not |
|---|---|
| Send first, validate after | A malformed artifact on disk is what a grader reads. |
| SMTP instead of the Gmail API | Book mandates the API and a scoped token. |
| Retry a failed send blindly | Risks account limits; dead-letter plus an alert is safer. |
| Skip sending on mismatch | Rule 35 punishes not reporting. We file, and surface the diff. |

## Test scenarios

| Scenario | Expectation | Test |
|---|---|---|
| Malformed artifact | Refused before write | `test_artifacts.py` |
| Missing agreement block | `TypeError`, not a plausible `false` | `test_agreement.py` |
| Opponent silent | `no_reply`, send permitted | `test_reconcile.py` |
| Results differ | `mismatch`, operator alert with the diff | `test_reconcile.py` |
| Gmail 429 | Backoff, then dead-letter with an alert | `test_gmail_sender.py` |
| Missing Gmail service | Fails fast with the actionable message | `test_gmail_sender.py` |
| Secret in the workspace | Excluded from the archive and reported | `test_archive.py` |
