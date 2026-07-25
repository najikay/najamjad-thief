# Schema policy — versioning, tolerance, and deviations from the reference

**Version 1.00 · 2026-07-25**

## Where the schemas come from

The project book names the four lifecycle artifacts but does not reproduce their
structure. The authoritative shapes are therefore the lecturer's own sample
artifacts, committed under `tests/goldens/artifacts/` with provenance
(source commit recorded in that folder's README). Every schema in
`src/najamjad_agent/protocol/` is validated against them by
`pytest -m goldens`, which runs in CI.

If the reference repo publishes newer samples, refresh the goldens and re-run
that suite **before** changing any schema — the goldens are the spec.

## The tolerance asymmetry (ADR-006)

| Direction | Policy | Why |
|---|---|---|
| **Inbound** wire messages | `extra="allow"`; unknown fields preserved in `extras`, logged, ignored | Every team writes its own agent. Rejecting a message over an unfamiliar key turns a harmless difference into a forfeited match — Assignment 6's most expensive failure. |
| **Outbound** artifacts & email | `extra="forbid"`, strict types, required booleans | A stray or missing field here means *our* builder is wrong. Better to fail locally than to submit a report the grader reads differently from our opponent's. |

Inbound validation **never raises**: `protocol/ingress.parse_message` returns a
`ParseResult` carrying either a model or a list of human-readable errors, plus a
structured `error_response()` for the peer. A hostile or buggy opponent must not
be able to end our match by sending nonsense (FR-NET-7).

## The egress gate (FR-REP-2)

Every artifact write and every email send passes `validate_egress()`. On failure
it raises `EgressBlockedError` **and** emits an `egress.blocked` operator alert;
the send does not happen. Meta-tests in `test_egress_enforcement.py` assert that
no module serialises artifacts outside the sanctioned path and that the error is
never swallowed.

`REQUIRED_BOOLEAN_PATHS` additionally checks that agreement flags are real
booleans. This exists because Assignment 6 shipped `agreement: null`: pydantic
alone would accept a `bool`-typed field fed `True`, but the explicit path check
also catches `"true"`, `1`, and a missing block — values that serialise into
JSON the grader cannot interpret as agreement.

## Versioning

- `schema_version` defaults to **1.1**, matching the reference artifacts. It is
  carried on every artifact and never silently changed.
- Our own code version lives in `shared/version.py` (starts at 1.00) and is
  reported separately in the Step-0 declaration.
- Config files carry their own `version` key, validated at startup against
  `SUPPORTED_CONFIG_VERSIONS`.

Bump `schema_version` only when the reference does, and record the change here.

## Deviations from the reference (deliberate, documented)

| Deviation | Reason |
|---|---|
| `NegotiateTerms.num_games` defaults to **6** | Appendix F Table 18 fixes a series at 6 mini-games; the reference ships `num_games: 1` as a single-game example. The book governs. |
| Appendix F minimums enforced in the schema (`grid_size ≥ 7`, `max_barriers ≥ 14`, `max_moves ≥ 35`, `survival_threshold ≥ 35`) | Book rule 12: minimums may be raised by agreement, never lowered. A proposal below them is not a negotiation, it is a rule breach, and is refused at parse time. |
| `_`-prefixed keys dropped on input | The reference samples carry `_schema` / `_remark` documentation notes. They are prose for humans; dropping them keeps `extra="forbid"` free to catch real typos. |
| `ControlMessage.kind` restricted to the four known verbs | Guessing at an unimplemented control verb is how two peers desynchronise. |

## Adding a schema

1. Add or refresh a golden sample first.
2. Write the failing test against the golden.
3. Implement the model; keep the file ≤ 120 code lines (split by artifact, not by
   compression).
4. If it is outbound, route it through `validate_egress` and extend the
   enforcement meta-tests if a new send path appears.
