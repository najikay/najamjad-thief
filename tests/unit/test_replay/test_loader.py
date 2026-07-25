"""Log loading — tolerant about containers, strict about cryptography.

Every team implements the book independently, so the shape around the sealed
record varies. Being fussy about a key name would mean failing to verify an
opponent who was in fact honest. Being fussy about the hash is the whole point,
and the last test here is the one that proves tolerance never buys a pass.
"""

import json

import pytest

from najamjad_agent.domain.crypto import seal
from najamjad_agent.replay.loader import (
    ReplayLoadError,
    load_document,
    load_records,
    normalise_record,
)

RECORD = {"payload": {"step": 1, "move": "MOVE:N"}, "nonce": "ab" * 16, "commit": "deadbeef"}


def test_our_own_log_shape_loads():
    records = load_records({"records": [RECORD]})

    assert records[0]["payload"]["move"] == "MOVE:N"


@pytest.mark.parametrize("container", ["records", "steps", "log", "entries"])
def test_the_record_list_is_found_whatever_it_is_called(container):
    records = load_records({container: [RECORD]})

    assert len(records) == 1


def test_a_bare_list_of_records_is_a_valid_log():
    assert len(load_records([RECORD, RECORD])) == 2


@pytest.mark.parametrize("name", ["commit", "commitment", "hash", "commit_hash"])
def test_the_commitment_is_found_whatever_it_is_called(name):
    record = normalise_record({"payload": {"step": 1}, "nonce": "ff", name: "abc123"})

    assert record["commit"] == "abc123"


@pytest.mark.parametrize("name", ["nonce", "salt", "secret"])
def test_the_nonce_is_found_whatever_it_is_called(name):
    record = normalise_record({"payload": {"step": 1}, "commit": "abc", name: "ff00"})

    assert record["nonce"] == "ff00"


def test_a_flattened_record_is_read_as_payload_plus_nonce_and_commit():
    """Some teams inline the sealed fields; that is the only reading available."""
    sealed = seal({"step": 3, "move": "MOVE:E"})
    flat = {**sealed.payload, "nonce": sealed.nonce, "commit": sealed.commit}

    record = normalise_record(flat)

    assert record["payload"] == sealed.payload
    assert record["nonce"] == sealed.nonce


def test_a_flattened_record_still_verifies_after_normalisation():
    """Tolerance must preserve the bytes, or it would break honest peers."""
    from najamjad_agent.domain.crypto import verify

    sealed = seal({"step": 4, "move": "MOVE:W", "hint": "near the bridge"})
    flat = {**sealed.payload, "nonce": sealed.nonce, "commitment": sealed.commit}

    record = normalise_record(flat)

    assert verify(record["payload"], record["nonce"], record["commit"])


def test_normalisation_never_turns_a_tampered_record_into_a_passing_one():
    """The point of the whole module: leniency stops at the hash."""
    from najamjad_agent.domain.crypto import verify

    sealed = seal({"step": 5, "move": "MOVE:N"})
    forged = {"payload": {"step": 5, "move": "MOVE:S"}, "salt": sealed.nonce, "hash": sealed.commit}

    record = normalise_record(forged)

    assert not verify(record["payload"], record["nonce"], record["commit"])


def test_a_log_can_be_loaded_from_json_text():
    assert load_records(json.dumps({"records": [RECORD]}))[0]["nonce"] == RECORD["nonce"]


def test_a_missing_file_is_a_load_error_not_a_crash(tmp_path):
    with pytest.raises(ReplayLoadError, match="cannot read"):
        load_records(tmp_path / "nothing.json")


def test_malformed_json_is_a_load_error(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    with pytest.raises(ReplayLoadError, match="not valid JSON"):
        load_records(broken)


@pytest.mark.parametrize("document", [{"summary": {}}, {"records": "nope"}])
def test_a_document_without_a_record_list_is_rejected(document):
    with pytest.raises(ReplayLoadError, match="no record list"):
        load_records(document)


def test_an_empty_record_list_is_rejected():
    with pytest.raises(ReplayLoadError, match="no records"):
        load_records({"records": []})


@pytest.mark.parametrize("source", [42, None, True])
def test_a_document_that_is_not_an_object_is_rejected(source):
    with pytest.raises(ReplayLoadError, match="must be an object"):
        load_document(source)


def test_a_non_object_record_survives_loading_and_fails_verification_later():
    """Garbage in the list must produce a verdict, not an exception."""
    record = normalise_record("not a record")

    assert record["commit"] == ""
