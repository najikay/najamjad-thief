"""The at-least-once receiver contract (kit SPEC §7.1), as a decision table.

Both registered wire shapes ride HTTP, which is at-least-once: a push whose ack
is lost is retried by a *correct* client, so the same message arrives twice by
design. A receiver that treats the second copy as an error turns an ordinary
retry race into a protocol violation — and under App. E rule 35 a self-inflicted
protocol fault zeroes **both** teams. The kit is explicit that this is not a
tightening a strict peer may choose: "zero tolerance is not a tightening here."

Our guard was stricter than the contract in exactly that way. It deduped on the
**step** and refused anything at or below the last accepted one, so a redelivery
and a forged step were the same event to us: both `stale or replayed`. That
conflates the two cases the contract most wants separated —

* **same step, same commit** is the network doing its job, and must be absorbed;
* **same step, different commit** is equivocation, which is tampering evidence
  and the one thing here that must never be quietly swallowed.

Dedupe is therefore on the commit, which is also the only field that can tell
them apart. Nothing here relaxes commit-reveal: transport tolerance, no rules
tolerance.

Kept honest by `tests/unit/test_net/test_delivery_contract.py`, which runs the
kit's own `vectors/delivery_contract.json` decision table through `decide`
rather than restating it in our words.
"""

from __future__ import annotations

import secrets
from typing import Any

#: The next expected step is applied.
APPLY = "apply"
#: A redelivery of a step we already played, with the commit that sealed it.
ABSORB = "absorb"
#: The same step sealed twice, differently. Tampering evidence, never swallowed.
EQUIVOCATION = "equivocation"
#: Ahead of `next` but inside the reorder window: hold it, replay in step order.
BUFFER = "buffer"
#: Past the window. The window IS the flood rule; a second threshold would only
#: disagree with it.
VIOLATION = "violation"
#: Below `next` and never played. Nothing to absorb and nothing to accuse.
DISCARD = "discard"

#: How many out-of-order steps may be buffered. The kit's own fixture runs at 2,
#: and **zero is the value that is actually dangerous** — it is what makes a
#: one-ahead arrival a violation rather than a wait.
REORDER_WINDOW = 2


def decide(played: dict[int, str], nxt: int, step: int, commit: str,
           window: int = REORDER_WINDOW) -> str:
    """What to do with an arriving turn, per the kit's §7.1 table.

    Input: steps already applied as `{step: commit}`, the next expected step,
        the arriving step and its commit, and the reorder window.
    Output: one of the six decisions above.
    Setup: none — this is a pure function so the table can be tested directly
        against the published fixture.
    """
    if step in played:
        # Timing-safe, because this comparison decides whether a message is a
        # harmless redelivery or tampering evidence, and `test_crypto_review`
        # forbids plain equality on a commit anywhere in the tree. It caught
        # this module on its first run, which is the guard doing its job.
        return ABSORB if secrets.compare_digest(played[step], commit) else EQUIVOCATION
    if step == nxt:
        return APPLY
    if step < nxt:
        # Below `next` and never applied. `next` only advances past accepted
        # steps, so there is no window in which this was legitimate.
        return DISCARD
    return BUFFER if step <= nxt + window else VIOLATION


#: Fields that mark a frame as settling rather than taking a turn. The first two
#: are the reference's; `caught` and `verdict` are what a peer building on the
#: book's own vocabulary sends instead, and we have played both shapes — their
#: sealed records differ completely and both audited `Verified OK`, because we
#: re-hash whatever a peer gives us rather than requiring a layout. The wire
#: deserves the same tolerance: a game-ending frame is a game-ending frame under
#: either vocabulary, and the cost of missing one is two teams filing different
#: endings for the same game.
SETTLING_FIELDS = ("claim_response", "win_claim", "caught", "verdict")


def is_settling(message: Any) -> bool:
    """Whether this frame settles a claim or the game rather than taking a turn.

    Checks declared fields and the tolerated extras alike, since a peer whose
    vocabulary our schema does not declare still arrives with the marker in
    `__pydantic_extra__`.
    """
    extras = getattr(message, "extras", None) or {}
    return any(getattr(message, field, None) is not None or extras.get(field) is not None
               for field in SETTLING_FIELDS)
