# Mechanism PRD — negotiation

**Version 1.00 · 2026-07-26 · FR-NEG-1..6 · ADR-011**

## Problem

Before a ball is kicked, two strangers' agents must agree on the board, the
rules and the scoring, and prove they agreed on *the same thing*. Assignment 6's
negotiating agent was invisible: when it misbehaved there was nothing to look at,
and the terms it settled were never surfaced.

## Contract

```python
negotiation.propose(terms)                  -> signed message
negotiation.receive(their_proposal)         -> our response
negotiation.agree(terms, identity)          -> signed agreement
negotiation.lock(peer_message, their_group) -> frozen contract
negotiation.abandon(reason)                 -> recorded withdrawal
```

Every step appends to a `timeline` the dashboard renders, so the whole exchange
is visible while it happens rather than reconstructed afterwards.

## The signature

Each peer signs `SHA256(canonical_terms | nonce)` and verifies the opponent's
signature over the **same terms**. Play starts only after both verifications
pass; a mismatch is refusal, not negotiation.

`identity` — group id, name, members — travels alongside but is deliberately
**not** covered by the signature: identity differs per group by definition, so
signing it would make every proposal mismatch. Our schema accepts it as an object
(the reference's shape) or a bare string.

Verified against the reference implementation: it validates our signature and we
validate its, byte for byte.

## The playbook

Terms are proposed from a playbook rather than improvised, and Appendix F's
minimums are floors: rule 12 permits raising a term, never lowering it. A
proposal below a minimum is refused rather than countered, because accepting one
would put us outside the book regardless of what the opponent wanted.

Adapter profiles (ADR-011) let us match a known opponent's dialect without
changing the core — the cost of adapting to another team was one of the seven
Assignment 6 pain points.

## Human approval

FR-NEG-4: the draft is visible and approvable before it goes out. An agent that
silently commits us to terms is exactly what went wrong last time.

## Alternatives considered

| Option | Why not |
|---|---|
| Accept whatever is proposed | Rule 12 violations become ours to answer for. |
| No signature | Then "we agreed" is a claim, not a fact. |
| Sign the identity too | Identity legitimately differs; every proposal would mismatch. |
| Free-form LLM negotiation | Unbounded, unverifiable, and rule 26 governs *hints*, not contracts. |

## Test scenarios

| Scenario | Expectation | Test |
|---|---|---|
| Matching terms | Both verify, play starts | `test_contract.py` |
| Differing terms | `CryptoError`, refusal | `test_contract.py` |
| Term below Appendix F | Refused | `test_playbook_flow.py` |
| Reference proposal | Accepted by our ingress | `test_interop_contract.py` |
| Our proposal | Verified by the reference's crypto | measured |
| Illegal stage transition | `NegotiationError` | `test_playbook_flow.py` |

## What is actually negotiable (2026-08-05)

Two things were being reasoned about as though they were negotiated, and neither
is.

**Timing is not a signed term.** The contract both sides must match is a flat
fourteen keys — `board_size`, `smell_grid_size`, `decay_per_step`,
`emit_intensity`, `min_center_intensity`, `max_steps`, `barriers_max`,
`setting`, `hint_max_words`, `axis_origin_corner`, `axis_start_index`,
`thief_start`, `cop_start`, `num_games`. `response_timeout_sec` and
`watchdog_timeout_sec` are **not among them**. No opponent has ever been able to
lengthen our turns and none can; the values are local config at Appendix F Table
19's own numbers, 30 s and 60 s. We could not shorten them either — waiting less
than 30 s would score a peer as timed out before the book permits — so on the
one axis where an opponent might buy thinking time for a model, we are already
as strict as the rules allow.

**Production does not negotiate at all.** `exchange_agreement` sends our terms
and `verify_peer` requires the peer's to be byte-identical (rule 11). There is
no counter-offer path in a real match: `NegotiationFlow`, which is where the
playbook's red lines are evaluated, has no production caller. The playbook is
therefore a *statement of position* — used by the dashboard and by us when
agreeing values with a team by hand — rather than a live gate.

That makes it more important, not less, that its red lines are honest, which is
why they are now bounded in both directions (T-2499). It also means the real
interop risk is the opposite of being too permissive: **any team differing on any
one of the fourteen fields cannot complete a handshake with us at all**, down to
`setting: "New York"`. `describe_mismatch` exists precisely for that conversation
and names the key and both values, so two teams can settle it in one message
instead of diffing configs under time pressure. Agree the fourteen values with an
opponent *before* match day; `docs/HOW_TO_PLAY_US.md` §3 publishes ours.
