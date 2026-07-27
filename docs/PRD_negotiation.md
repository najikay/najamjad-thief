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
