# ADR-015 — A peer announces an ending rather than letting the other infer it

**Status:** accepted (build-time, E21)

**Context:** The turn order means one side sees an ending half a turn before the
other. Our first implementation had whoever saw it simply stop. The other side
then waited out its deadline and recorded a *timeout* for a game the first had
recorded as a *capture* — and under rules 33-35 two contradictory reports void
the game for both. It happened for captures, again for survival, and again for
barrier captures. Every unit test passed throughout, because each peer was only
ever tested alone.

**Decision:** an ending only one side can observe is **deferred**, announced on
one final sealed turn, and closes the game only then.

- A landed capture claim is answered honestly by the thief before it closes
  (rules 21-22), the answer settled at the moment the claim arrives rather than
  when we get round to replying.
- A peer detecting survival declares it via `win_claim`.
- A barrier capture needs no announcement: rules 15-16 make the placement
  public, so both sides reach the same verdict on the same turn.
- A `win_claim` naming a reason we do not recognise is ignored — a peer cannot
  end a game by inventing an outcome.

**Trade-off:** one extra sealed step in the thief's record on a capture, and a
slightly larger wire vocabulary. Both are cheap against a voided game.
