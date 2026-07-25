"""Custody of nonces until the audit phase opens.

A leaked nonce is a lost game: with the payload space this small, an opponent
holding our nonce early could brute-force our exact position from a commit. So
nonces live behind a gate that physically refuses to hand them out before the
audit phase (book rule 18), rather than relying on callers to be careful.

Spilled state is encrypted with a key held only in memory, so a crash dump or a
stray file read cannot reveal a live game's nonces.
"""

import base64
import hashlib
import json
import secrets
from pathlib import Path

from ..protocol.canonical import canonical_json


class NonceSealedError(Exception):
    """Raised when nonces are requested before the audit phase is open."""


class NonceVault:
    """Per-mini-game nonce custody with an explicit audit gate."""

    def __init__(self) -> None:
        """Create a sealed vault with a fresh in-memory encryption key."""
        self._nonces: dict[int, str] = {}
        self._audit_open = False
        self._key = secrets.token_bytes(32)

    @property
    def audit_open(self) -> bool:
        """True once the mini-game ended and reveal is permitted."""
        return self._audit_open

    @property
    def step_count(self) -> int:
        """How many steps are under custody (safe to expose — not a secret)."""
        return len(self._nonces)

    def store(self, step: int, nonce: str) -> None:
        """Take custody of one step's nonce; re-use of a step is refused."""
        if step in self._nonces:
            raise ValueError(f"step {step} already has a stored nonce")
        self._nonces[step] = nonce

    def open_audit(self) -> None:
        """Open the gate — called only when the mini-game has ended."""
        self._audit_open = True

    def require_open(self) -> None:
        """Raise unless the audit gate is open — the single secrecy check."""
        if not self._audit_open:
            raise NonceSealedError("nonces stay secret until the end-of-game audit")

    def reveal(self, step: int) -> str:
        """Return one nonce, refusing while the vault is still sealed."""
        self.require_open()
        return self._nonces[step]

    def reveal_all(self) -> dict[int, str]:
        """Return every nonce for the audit exchange."""
        self.require_open()
        return dict(self._nonces)

    def _keystream(self, length: int) -> bytes:
        """Deterministic keystream from the in-memory key."""
        stream = b""
        counter = 0
        while len(stream) < length:
            stream += hashlib.sha256(self._key + counter.to_bytes(4, "big")).digest()
            counter += 1
        return stream[:length]

    def _xor(self, data: bytes) -> bytes:
        return bytes(byte ^ key for byte, key in zip(data, self._keystream(len(data)), strict=True))

    def spill(self, path: Path) -> None:
        """Persist encrypted custody so a crash cannot lose the audit trail."""
        blob = canonical_json({str(step): nonce for step, nonce in self._nonces.items()})
        path.write_text(
            base64.b64encode(self._xor(blob.encode("utf-8"))).decode("ascii"), encoding="utf-8"
        )

    def restore(self, path: Path) -> None:
        """Reload encrypted custody written by `spill` in this process."""
        raw = self._xor(base64.b64decode(path.read_text(encoding="utf-8")))
        self._nonces = {int(step): nonce for step, nonce in json.loads(raw).items()}
