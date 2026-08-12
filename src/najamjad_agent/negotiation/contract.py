"""The signed contract — terms both peers hold byte-identically.

Book rule 11: the shared config must be byte-identical on both sides and the
pre-game signature exchange refuses to play on any mismatch. Rule 12: an
Appendix F minimum may be raised by agreement, never lowered.

Both peers derive `game_id` and `game_uid` from data they already share, so no
extra round-trip is needed to agree on identifiers — and because the derivation
is a pure function, two honest peers always compute the same values. Signature
and id derivation are byte-compatible with the reference implementation.
"""

import hashlib
import secrets
import uuid

from ..domain.crypto import commit_of, verify
from ..domain.params import (
    FIXED_MOVE_SET,
    MIN_GRID_SIZE,
    MIN_MAX_BARRIERS,
    MIN_MAX_MOVES,
    MIN_SURVIVAL_THRESHOLD,
)
from ..domain.scoring import FIXED_SCORES
from ..protocol.canonical import canonical_json

# Appendix F floors, checked before we ever sign (book rule 12).
MINIMUMS = {
    "grid_size": MIN_GRID_SIZE,
    "max_barriers": MIN_MAX_BARRIERS,
    "max_moves": MIN_MAX_MOVES,
    "survival_threshold": MIN_SURVIVAL_THRESHOLD,
}
FIXED_TERMS = {"num_agents": 2, **FIXED_SCORES}
#: The four keys the reference agreement message owns. A declaration may never
#: take one of these names.
_RESERVED = frozenset({"terms", "nonce", "signature", "identity"})


class ContractError(Exception):
    """Raised when terms are unacceptable or a peer's signature does not match."""


def validate_terms(terms: dict) -> None:
    """Refuse any contract that weakens the book before we sign it."""
    for key, floor in MINIMUMS.items():
        if key in terms and int(terms[key]) < floor:
            raise ContractError(
                f"{key}={terms[key]} is below the Appendix F minimum of {floor}; "
                "minimums may be raised by agreement, never lowered (rule 12)"
            )
    for key, fixed in FIXED_TERMS.items():
        if key in terms and int(terms[key]) != fixed:
            raise ContractError(f"{key} is fixed at {fixed} by Appendix F; got {terms[key]}")
    if "move_set" in terms and set(terms["move_set"]) != set(FIXED_MOVE_SET):
        raise ContractError(f"move_set is fixed by Appendix F; got {terms['move_set']}")


def derive_game_ids(terms: dict, group_a: str, group_b: str) -> tuple[str, str]:
    """Return the (game_id, game_uid) both peers compute independently."""
    pair = sorted([group_a, group_b])
    game_id = f"{pair[0]}-vs-{pair[1]}"
    seed = f"{canonical_json(terms)}|{'|'.join(pair)}"
    game_uid = str(uuid.UUID(bytes=hashlib.sha256(seed.encode("utf-8")).digest()[:16]))
    return game_id, game_uid


def contract_hash(terms: dict) -> str:
    """SHA-256 over the canonical terms — the `config_sha256` in artifacts."""
    return hashlib.sha256(canonical_json(terms).encode("utf-8")).hexdigest()


class Contract:
    """One peer's side of the agreement handshake."""

    def __init__(
        self, terms: dict, identity: dict | None = None, declarations: dict | None = None
    ) -> None:
        """Validate our own terms before offering them to anybody."""
        validate_terms(terms)
        self.terms = terms
        self.identity = identity or {}
        self.declarations = declarations or {}
        self._nonce = secrets.token_hex(16)
        self.peer_identity: dict = {}
        self.verified = False

    @property
    def sha256(self) -> str:
        """The locked hash of the agreed terms."""
        return contract_hash(self.terms)

    def signed(self) -> dict:
        """Our agreement message, in the reference-compatible shape.

        Identity is deliberately outside the signature: it differs per group, so
        it is not a must-match term — the *terms* are what both peers verify.

        Declarations sit outside it for the same reason and one more: they are
        guards a peer may or may not implement, so covering them would make our
        signature unverifiable to anyone who does not send them. They cannot
        collide with the four reference keys — `_RESERVED` is enforced here
        rather than trusted, because a declaration overwriting `signature` would
        be a self-inflicted refusal at the one moment nothing can be debugged.
        """
        extra = {k: v for k, v in self.declarations.items() if k not in _RESERVED}
        return {
            "terms": self.terms,
            "nonce": self._nonce,
            "signature": commit_of(self.terms, self._nonce),
            "identity": self.identity,
            **extra,
        }

    def verify_peer(self, message: dict) -> None:
        """Confirm the peer signed exactly our terms, or refuse to play."""
        for field in ("terms", "nonce", "signature"):
            if field not in message:
                raise ContractError(f"agreement message is missing {field!r}")
        if message["terms"] != self.terms:
            raise ContractError(
                "terms mismatch: the contract is not byte-identical on both sides (rule 11)"
            )
        if not verify(message["terms"], message["nonce"], message["signature"]):
            raise ContractError("peer signature does not match the agreed terms")
        self.peer_identity = message.get("identity", {}) or {}
        self.verified = True

    def game_ids(self, our_group: str, their_group: str) -> tuple[str, str]:
        """The shared identifiers for this match."""
        return derive_game_ids(self.terms, our_group, their_group)
