# Wire protocol — what crosses the network, and what never does

**Version 1.10 · 2026-08-05**

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
| `sender` | yes | session binding — carries a **role** (`"police"`/`"thief"`), never a group id |
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
a speculative claim hands the thief the cop's exact position for nothing.

**That price does not deter anyone, and assuming it did cost us games.** Both
reference implementations attach a claim to *every* police move, and so do the
opponents built on them: uoh-sqak claimed on all 15 steps, uoh-ay26 on all 34 of
theirs. A claim forces a cryptographically truthful yes/no, so claiming each
swept cell buys a free bit per turn and the discloser evidently considers that a
good trade. Against a peer who emits no scent and no parseable hint, their claims
are the *entire* position signal in the game — see `cop_sighting.from_claim` for
what reading them is worth, and `scripts/claim_evidence.py` for the measurement.

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

## 6. Canonical form — the thing that voids games silently (2026-08-05)

At the end of every mini-game the opponent re-hashes our sealed records. Two
implementations that are each perfectly correct but serialize JSON differently
each conclude the other tampered, and rules 33-35 void the game for **both**. It
is the cheapest way in this league to score zero while playing perfectly.

```
canonical_json(payload) = json.dumps(payload, sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":"))
commit                  = SHA256(canonical_json(payload) + "|" + nonce)
```

UTF-8 throughout. The two flags are where honest implementations drift, because
both differ from Python's defaults: `ensure_ascii` defaults to `True` (escaping
a Hebrew hint to `\uXXXX` and changing every hash that carries one) and
`separators` defaults to `", "` / `": "` (changing every hash, full stop).

**This cannot be found by playing ourselves.** Our two repos share a
byte-identical core, so cop and thief agree with each other by construction —
including when both are wrong. It needs a second implementation, which is why
`tests/unit/test_protocol/test_interop_vectors.py` asserts *literal* strings and
digests rather than round-tripping through our own function.

Cross-checked on 2026-08-05 against the independent specification at
`github.com/Imreec/copthief-league-protocol` (§2, §3), which states the same
canonical form, the same pipe separator and the same construction. Reviewed and
verified, never imported.

## 7. The claim-answer exemption

The step guard is monotonic, with one exception: the reference concedes a
capture with a final message **at the step it answers**, without advancing its
counter, and a strict guard rejects the one message we are waiting for —
stalling the game at the moment we won it.

That exemption must be exactly one case wide. Unconditional, it is a one-key
bypass of the whole guard. Narrowed to a window and not advancing the counter, it
refuses ordinary turns: the reference attaches `capture_claim` to *every* police
move, so a thief answers on consecutive move-carrying turns, and our archived
matches show `peer.answered_claim` at steps 11-15, 21-27 and 35 in a single
mini-game.

The rule: an answer at the step we last accepted is taken once; anything ahead is
an ordinary turn and advances the counter; anything behind is stale and refused.

## 8. The two places a second byte format applies (2026-08-05)

Cross-checked against the published interop kit. Both are cases where using the
form from §6 is *wrong*, and both fail silently.

**The settlement signature is spaced, not compact.** The consensus signature —
key `חתימת_קונסנזוס_משותפת` — is SHA-256 over sorted-key, raw-UTF-8 JSON with the
standard library's **default** separators, computed *before* the key is inserted
into the report it covers. A peer verifies by popping the key, re-serializing
spaced and re-hashing. Signing the compact form instead produces a valid-looking
digest that simply never matches, at the one moment both teams must agree.
`protocol/canonical.spaced_json` keeps both forms in one module so nobody
unifies them; `reporting/consensus.py` is the only caller.

**The pheromone model is subtractive Chebyshev.** `half = grid // 2`,
`falloff = intensity / (half + 1)`, `value = max(0, intensity − falloff ×
chebyshev)`, rounded to 3 places, decay subtractive and clamped at zero, only
`value > 0` on the wire. Nothing crashes if two teams disagree here — the grid is
not part of the commit, so audits pass — but both sides infer the wrong position
from each other's field for the whole series. Ours is `pheromones.pheromone_model`,
default `reference`.

## 9. Three published commit constructions, only one of which interoperates

The release ships **three** commit formulas, all producing different digests for
the same sealed record. One of them consumes only `nonce|move`, binding neither
state nor intent — position and bluff tampering are invisible to it.

Ours is the reference form, `SHA256(canonical_json(payload) + "|" + nonce)`,
asserted against the kit's vectors in `test_interop_vectors.py`. If your commits
match one of the other two, you implemented from a book listing rather than the
reference, and our audits will contradict each other on the first mini-game.

