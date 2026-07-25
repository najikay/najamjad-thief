"""Commit-reveal sealing over SHA-256 — the game's integrity backbone.

Without a referee, honesty is enforced cryptographically (book Ch. 5). Each step
a peer seals its true state, move, intent and hint under

    commit = SHA256(canonical_json(payload) + "|" + nonce)

and transmits only `commit`. The nonce stays secret until the end-of-game audit,
so neither side can rewrite history after seeing the outcome — and the nonce
(16 random bytes) defeats dictionary attacks over the tiny move space.

The `|` separator, canonical encoding and hex nonce are byte-compatible with the
reference implementation, proven against its sample log (`test_crypto_golden`).
"""

import hashlib
import secrets
from dataclasses import dataclass
from typing import Any

from ..protocol.canonical import canonical_json

NONCE_BYTES = 16
SEPARATOR = "|"


class CommitMismatchError(Exception):
    """Raised when a revealed payload does not match its commitment."""


@dataclass(frozen=True)
class SealedRecord:
    """A sealed step: the payload, its secret nonce, and the public commit."""

    payload: dict[str, Any]
    nonce: str
    commit: str

    def public_view(self) -> dict[str, Any]:
        """What a peer may see before the audit: the commitment, nothing else.

        The sealed payload holds our position, move and intent. Transmitting it
        would hand the opponent perfect information and make the whole
        hidden-state game — scent, belief, bluffing — pointless, while also
        leaving nothing to reveal at audit. Only the hash goes out.
        """
        return {"commit": self.commit}

    def audit_view(self) -> dict[str, Any]:
        """Full form for the end-of-game audit, nonce included."""
        return {"payload": self.payload, "nonce": self.nonce, "commit": self.commit}


def new_nonce() -> str:
    """Fresh cryptographic nonce (hex) — never reused across steps or games."""
    return secrets.token_hex(NONCE_BYTES)


def commit_of(payload: dict[str, Any], nonce: str) -> str:
    """Compute the commitment hash for a payload under a nonce."""
    material = f"{canonical_json(payload)}{SEPARATOR}{nonce}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def seal(payload: dict[str, Any], nonce: str | None = None) -> SealedRecord:
    """Seal a payload under a fresh (or supplied) nonce."""
    chosen = nonce or new_nonce()
    return SealedRecord(payload=payload, nonce=chosen, commit=commit_of(payload, chosen))


def verify(payload: dict[str, Any], nonce: str, commit: str) -> bool:
    """True when (payload, nonce) reproduces `commit`.

    Uses `compare_digest` so a peer cannot learn anything from response timing.
    """
    return secrets.compare_digest(commit_of(payload, nonce), commit)


def require_match(payload: dict[str, Any], nonce: str, commit: str) -> None:
    """Verify or raise — used where a mismatch must stop the game."""
    if not verify(payload, nonce, commit):
        recomputed = commit_of(payload, nonce)
        raise CommitMismatchError(
            f"commit mismatch: declared {commit[:16]}..., recomputed {recomputed[:16]}..."
        )


def step_payload(
    step: int,
    role: str,
    sub_game: int,
    position: tuple[int, int],
    move: str,
    intent: str,
    hint: str,
    state: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the sealed per-step payload in the interop field shape."""
    payload: dict[str, Any] = {
        "step": step,
        "role": role,
        "sub_game": sub_game,
        "position": [position[0], position[1]],
        "move": move,
        "intent": intent,
        "hint": hint,
        "state": state,
    }
    if extra:
        payload.update(extra)
    return payload
