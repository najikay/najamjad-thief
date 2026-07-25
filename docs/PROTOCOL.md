# Wire protocol — what crosses the network, and what never does

**Version 1.00 · 2026-07-25**

This document exists because we got it wrong once, and the mistake was the kind
that would have quietly lost every match while all 1,000 tests stayed green.

---

## 1. The rule

**A peer learns nothing about our position or our move until the end-of-game
audit.** Everything we transmit mid-game is either unfakeable evidence, free
language, or something the rules oblige us to declare.

| Field | Sent per turn | Why |
|---|---|---|
| `step` | yes | ordering and replay detection |
| `sender` | yes | session binding to the negotiated opponent |
| `commit` | yes | SHA-256 over our sealed record — the anchor of the audit |
| `hint` | yes | free-language dialogue is mandatory (rule 26); may be a lie |
| `smell_grid` | yes | scent is emitted involuntarily and cannot be faked (PAGE 22) |
| `barrier_placed` | when placed | the cop must declare barriers truthfully (rules 15-16) |
| `capture_claim` | when claiming | the thief must be able to answer (rules 21-22) |
| `claimed_cell` | when claiming | see §3 |
| **`position`** | **never** | it is the secret the whole game is played over |
| **`move`** | **never** | reveals position given a known start |
| **`intent`** | **never** | truth/lie is what makes bluffing meaningful |
| **`nonce`** | **never until audit** | early release inverts our commitments (rule 18) |

## 2. The bug we shipped and then removed

An early implementation sent the *whole sealed payload* alongside each commit —
position, move and intent included. It passed every test, because the tests had
been written against that same wrong assumption.

The consequences would have been total:

* the opponent would have known our exact cell every turn, so scent, belief,
  bluffing and hint-credibility modelling — most of this project — would have
  been decoration;
* nothing would remain to reveal at audit, so commit-reveal would have verified
  data the opponent already had;
* and we would have looked, to a careful grader, like a team that had not
  understood the game.

It was caught by asking what the "local truth only" UI rule (book rules 8-9)
implied for the *wire*, then comparing our outbound message against the
reference implementation's `TurnMessage`, which carries no position and no move.

`test_nothing_we_transmit_ever_reveals_our_position` now plays several turns and
scans every transmitted byte for `position`, `MOVE:` and `intent`, so the leak
cannot return.

## 3. Why a capture claim names a cell

The book requires the thief to answer a capture claim truthfully (rules 21-22).
But the thief does not know where the cop is — so an unqualified "I have caught
you" is unanswerable.

A claim therefore carries `claimed_cell`: the cop asserts *which* cell it is
standing on, and the thief compares that against its own true position. This is
the one moment a cop discloses its location, and that disclosure is the design:
a speculative claim hands the thief the cop's exact position for nothing, which
is what stops a cop from claiming every turn "just in case".

## 4. Consequences for validation

Per-turn physics policing is impossible by design — we cannot check that an
opponent's move was legal when we never see their moves. Illegality is caught at
the **audit**, where the full sealed record is revealed and re-hashed; a peer
whose revealed path contains a teleport or a diagonal is exposed then, and rule
19 voids the game for them.

That is the book's own trade-off, and it is a good one: hidden information
during play, verifiable honesty afterwards. What we *do* police per turn is
protocol-level misbehaviour that cannot wait — replayed or stale steps, a peer
re-committing a step, malformed payloads, and unknown senders.

## 5. What we do when a peer leaks

Some opponents will send their position, either from a naive implementation or
as bait. We do not consume it — belief comes from scent and hints only — but we
emit `peer.leaked_position`, because a team broadcasting its own location is
useful to know about and worth mentioning to them.
