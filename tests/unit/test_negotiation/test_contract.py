"""Tests for the signed contract: byte-identity, signatures, Appendix F floors."""

import json
from pathlib import Path

import pytest

from najamjad_agent.negotiation.contract import (
    Contract,
    ContractError,
    contract_hash,
    derive_game_ids,
    validate_terms,
)

GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "goldens/artifacts/config_segal-police-team-vs-segal-thief-team_g01.json"
)

TERMS = {
    "grid_size": 7,
    "max_barriers": 14,
    "max_moves": 35,
    "survival_threshold": 35,
    "num_games": 6,
    "hint_max_words": 15,
}


@pytest.fixture()
def contract() -> Contract:
    return Contract(TERMS, identity={"group_id": "najamjad"})


def test_our_own_terms_are_validated_before_we_offer_them(contract: Contract) -> None:
    assert contract.terms["grid_size"] == 7


@pytest.mark.parametrize(
    ("key", "bad"),
    [("grid_size", 6), ("max_barriers", 13), ("max_moves", 34), ("survival_threshold", 34)],
)
def test_a_lowered_minimum_is_refused(key: str, bad: int) -> None:
    """Book rule 12: minimums may be raised by agreement, never lowered."""
    with pytest.raises(ContractError, match="below the Appendix F minimum"):
        validate_terms({**TERMS, key: bad})


def test_raising_a_minimum_is_allowed() -> None:
    validate_terms({**TERMS, "grid_size": 10, "max_moves": 40, "survival_threshold": 40})


def test_an_altered_fixed_score_is_refused() -> None:
    with pytest.raises(ContractError, match="fixed at 20"):
        validate_terms({**TERMS, "capture_cop": 25})


def test_an_altered_move_set_is_refused() -> None:
    with pytest.raises(ContractError, match="move_set is fixed"):
        validate_terms({**TERMS, "move_set": ["N", "S", "NE"]})


def test_the_signed_message_has_the_reference_shape(contract: Contract) -> None:
    message = contract.signed()
    assert set(message) == {"terms", "nonce", "signature", "identity"}
    assert len(message["signature"]) == 64


def test_two_peers_with_identical_terms_verify_each_other() -> None:
    ours = Contract(TERMS, identity={"group_id": "najamjad"})
    theirs = Contract(dict(TERMS), identity={"group_id": "rival"})
    ours.verify_peer(theirs.signed())
    theirs.verify_peer(ours.signed())
    assert ours.verified and theirs.verified
    assert ours.peer_identity == {"group_id": "rival"}


def test_key_order_does_not_break_verification(contract: Contract) -> None:
    """Canonical serialisation means dict ordering is irrelevant."""
    reordered = Contract(dict(reversed(list(TERMS.items()))))
    contract.verify_peer(reordered.signed())
    assert contract.verified


def test_different_terms_refuse_to_play(contract: Contract) -> None:
    """Rule 11: any mismatch and the match does not start."""
    theirs = Contract({**TERMS, "grid_size": 9}).signed()
    with pytest.raises(ContractError, match="not byte-identical"):
        contract.verify_peer(theirs)
    assert not contract.verified


def test_a_forged_signature_is_refused(contract: Contract) -> None:
    theirs = Contract(dict(TERMS)).signed()
    theirs["signature"] = "0" * 64
    with pytest.raises(ContractError, match="signature does not match"):
        contract.verify_peer(theirs)


def test_a_tampered_nonce_is_refused(contract: Contract) -> None:
    theirs = Contract(dict(TERMS)).signed()
    theirs["nonce"] = "deadbeef"
    with pytest.raises(ContractError, match="signature does not match"):
        contract.verify_peer(theirs)


@pytest.mark.parametrize("missing", ["terms", "nonce", "signature"])
def test_an_incomplete_agreement_message_is_refused(contract: Contract, missing: str) -> None:
    theirs = Contract(dict(TERMS)).signed()
    del theirs[missing]
    with pytest.raises(ContractError, match=f"missing '{missing}'"):
        contract.verify_peer(theirs)


def test_both_peers_derive_identical_ids() -> None:
    """No extra round-trip: the derivation is a pure function of shared data."""
    ours = derive_game_ids(TERMS, "najamjad", "rival")
    theirs = derive_game_ids(dict(TERMS), "rival", "najamjad")
    assert ours == theirs


def test_game_id_is_the_sorted_pair() -> None:
    game_id, _ = derive_game_ids(TERMS, "zeta", "alpha")
    assert game_id == "alpha-vs-zeta"


def test_game_uid_is_a_stable_uuid() -> None:
    _, first = derive_game_ids(TERMS, "a", "b")
    _, again = derive_game_ids(TERMS, "a", "b")
    assert first == again
    assert len(first) == 36


def test_different_terms_produce_a_different_uid() -> None:
    _, first = derive_game_ids(TERMS, "a", "b")
    _, other = derive_game_ids({**TERMS, "grid_size": 9}, "a", "b")
    assert first != other


def test_the_contract_hash_is_the_config_sha256_field(contract: Contract) -> None:
    assert len(contract.sha256) == 64
    assert contract.sha256 == contract_hash(TERMS)


def test_the_golden_config_hash_is_64_hex_characters() -> None:
    """Interop: the artifact field we must populate has a fixed shape."""
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(golden["config_sha256"]) == 64
    assert golden["game_id"] == "segal-police-team-vs-segal-thief-team"


def test_game_ids_reproduce_the_golden_naming_convention() -> None:
    game_id, _ = derive_game_ids(TERMS, "segal-police-team", "segal-thief-team")
    assert game_id == "segal-police-team-vs-segal-thief-team"
