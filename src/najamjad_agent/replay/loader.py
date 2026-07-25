"""Loading logs — ours, the reference simulator's, and other teams'.

The replay viewer's real job is auditing logs we did not write. Every team
implements the book independently, so the container shape varies even when the
cryptography underneath is identical: some nest the sealed record under
`payload`, some flatten it; some call the hash `commit`, others `commitment`.
Refusing a log over a key name would mean failing to verify an opponent who was
in fact honest, which is worse than being tolerant here.

What this module will *not* do is guess about the cryptography. Normalisation
only renames containers and unwraps nesting; the bytes that get hashed are
whatever the log actually carries, so a normalised record either verifies or
fails loudly. There is no path where a lenient reader turns a tampered log into
a passing one.

Unlike the live dashboard, the replay viewer may show positions: it runs after
the audit, on records the peer itself revealed (book rule 18). Rules 8-9 govern
a game in progress, not the post-mortem.
"""

import json
from pathlib import Path
from typing import Any

RECORD_KEYS = ("records", "steps", "log", "entries")
COMMIT_KEYS = ("commit", "commitment", "hash", "commit_hash")
NONCE_KEYS = ("nonce", "salt", "secret")
PAYLOAD_KEYS = ("payload", "record", "data")


class ReplayLoadError(Exception):
    """The file is not a log we can make sense of at all."""


def _first(source: dict[str, Any], names: tuple[str, ...]) -> tuple[str, Any] | None:
    """The first present key from `names`, with its value."""
    for name in names:
        if name in source:
            return name, source[name]
    return None


def _records_of(document: dict[str, Any]) -> list[Any]:
    """Find the record list, whatever the surrounding document calls it.

    Always receives a dict: `load_document` is the only caller and it has
    already wrapped a bare list and rejected everything else.
    """
    found = _first(document, RECORD_KEYS)
    if found is None or not isinstance(found[1], list):
        raise ReplayLoadError(f"no record list found (looked for {', '.join(RECORD_KEYS)})")
    return found[1]


def normalise_record(record: Any) -> dict[str, Any]:
    """Reduce one record to the canonical `{payload, nonce, commit}` shape.

    A flattened record is read as "everything except the nonce and commit was
    the sealed payload" — the only interpretation available, and one that
    verifies exactly when it is right.
    """
    if not isinstance(record, dict):
        return {"payload": record, "nonce": "", "commit": ""}
    commit = _first(record, COMMIT_KEYS)
    nonce = _first(record, NONCE_KEYS)
    payload = _first(record, PAYLOAD_KEYS)
    if payload is not None and isinstance(payload[1], dict):
        body = payload[1]
    else:
        skip = {name for name, _ in (commit, nonce) if name} if commit or nonce else set()
        body = {key: value for key, value in record.items() if key not in skip}
    return {
        "payload": body,
        "nonce": nonce[1] if nonce else "",
        "commit": commit[1] if commit else "",
    }


def load_document(source: Any) -> dict[str, Any]:
    """Read a log from a path, JSON text, or an already-parsed object."""
    if isinstance(source, Path):
        try:
            source = source.read_text(encoding="utf-8")
        except OSError as error:
            raise ReplayLoadError(f"cannot read {source}: {error}") from error
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except json.JSONDecodeError as error:
            raise ReplayLoadError(f"not valid JSON: {error}") from error
    if isinstance(source, list):
        return {"records": source}
    if not isinstance(source, dict):
        raise ReplayLoadError("a log must be an object or a list of records")
    return source


def load_records(source: Any) -> list[dict[str, Any]]:
    """Every record from `source`, normalised for verification."""
    records = [normalise_record(record) for record in _records_of(load_document(source))]
    if not records:
        raise ReplayLoadError("the log contains no records")
    return records
