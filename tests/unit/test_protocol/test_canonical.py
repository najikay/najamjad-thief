"""Tests for the canonical JSON encoder — the pinned interop byte format."""

from najamjad_agent.protocol.canonical import canonical_bytes, canonical_json


def test_keys_are_sorted_so_order_never_changes_a_hash() -> None:
    assert canonical_json({"c": 3, "a": 1, "b": 2}) == '{"a":1,"b":2,"c":3}'


def test_separators_are_compact() -> None:
    assert " " not in canonical_json({"a": [1, 2], "b": {"c": 3}})


def test_unicode_is_preserved_not_escaped() -> None:
    """ensure_ascii=False: a Hebrew hint must hash identically on both peers."""
    assert canonical_json({"hint": "מסתתר"}) == '{"hint":"מסתתר"}'


def test_nested_structures_are_sorted_at_every_level() -> None:
    assert canonical_json({"z": {"b": 1, "a": 2}}) == '{"z":{"a":2,"b":1}}'


def test_canonical_bytes_is_utf8_of_the_canonical_string() -> None:
    payload = {"hint": "🌉 bridge"}
    assert canonical_bytes(payload) == canonical_json(payload).encode("utf-8")


def test_canonical_bytes_round_trips_through_utf8() -> None:
    payload = {"a": "שלום", "b": 1}
    assert canonical_bytes(payload).decode("utf-8") == canonical_json(payload)
