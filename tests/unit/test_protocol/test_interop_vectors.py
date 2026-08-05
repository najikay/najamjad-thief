"""Known-answer vectors for the two things that void a game for both sides.

At the end of every mini-game the opponent re-hashes our sealed records. Two
implementations that are each perfectly correct, but serialize JSON even
slightly differently, will each conclude the other tampered — and rules 33-35
void a contradicted game for *both* teams. It is the cheapest way in this league
to score zero while playing perfectly, and it cannot be found by playing
ourselves: our two repos share a byte-identical core, so cop and thief agree
with each other by construction, including when both are wrong.

So these are **literal** expected strings and digests, not round-trips. A test
that hashes with `canonical_json` and checks with `canonical_json` passes no
matter what `canonical_json` does; only a hard-coded answer notices the day
someone "tidies up" a serialization flag.

Cross-checked 2026-08-05 against the independent interop specification published
at github.com/Imreec/copthief-league-protocol (§2, §3), which states the same
canonical form and the same `SHA256(canonical_json(payload) + "|" + nonce)`
construction. Reviewed, not copied: the values below are computed from our own
implementation and asserted here so that a future divergence is *ours* to
notice, and the agreement is evidence rather than an import.
"""

import hashlib

from najamjad_agent.domain.crypto import SEPARATOR, commit_of, verify
from najamjad_agent.protocol.canonical import canonical_bytes, canonical_json


def test_keys_are_sorted_and_separators_are_compact() -> None:
    """`sort_keys=True` and `separators=(",", ":")`, stated as an answer.

    Python's default separators are `", "` and `": "`. A team that simply called
    `json.dumps(payload, sort_keys=True)` produces different bytes from us for
    *every* payload, and therefore a different commit for every step.
    """
    payload = {"step": 2, "move": "N", "position": [3, 3]}

    assert canonical_json(payload) == '{"move":"N","position":[3,3],"step":2}'


def test_non_ascii_is_emitted_raw_not_escaped() -> None:
    """`ensure_ascii=False`, and this is the one most likely to bite.

    Python's default is `True`, which would render the same hint as
    `"\\u05e9\\u05dc\\u05d5\\u05dd"` and hash to something else entirely. Hints
    are free text and this cohort writes Hebrew, so the divergence is not
    hypothetical — it is one hint away, in a field the rules positively
    encourage us to use.
    """
    payload = {"hint": "שלום"}

    assert canonical_json(payload) == '{"hint":"שלום"}'
    assert "\\u" not in canonical_json(payload)
    assert canonical_bytes(payload) == '{"hint":"שלום"}'.encode()


def test_the_commit_is_sha256_of_canonical_then_pipe_then_nonce() -> None:
    """The exact construction, spelled out rather than recomputed.

    Anything else — a different separator, hashing the dict repr, hashing the
    nonce first — produces a commit the opponent cannot reproduce, which their
    audit reads as tampering.
    """
    payload = {"move": "N", "position": [3, 3], "step": 1}
    nonce = "0123456789abcdef"

    expected = hashlib.sha256(b'{"move":"N","position":[3,3],"step":1}|0123456789abcdef').hexdigest()

    assert SEPARATOR == "|"
    assert commit_of(payload, nonce) == expected
    assert verify(payload, nonce, expected)


def test_a_known_commit_stays_known() -> None:
    """The regression guard: one frozen digest for one frozen input.

    If this value ever changes, our sealed records stopped matching every
    implementation we have interoperated with, and the next audit is a mutual
    `tamper_forfeit`. Change it only with a reason written down.
    """
    payload = {"hint": "שלום", "intent": "evade", "move": "STAY", "state": "grid=7x7"}

    assert commit_of(payload, "n0nce") == hashlib.sha256(
        '{"hint":"שלום","intent":"evade","move":"STAY","state":"grid=7x7"}|n0nce'.encode()
    ).hexdigest()


def test_key_order_in_the_source_dict_cannot_change_the_commit() -> None:
    """Two peers building the same record in a different order must agree.

    `sort_keys=True` is what makes this true, and it is why the audit can
    compare records built by two independently written agents at all.
    """
    ours = {"move": "N", "state": "s", "intent": "i", "nonce_hint": 1}
    theirs = {"nonce_hint": 1, "intent": "i", "state": "s", "move": "N"}

    assert commit_of(ours, "x") == commit_of(theirs, "x")


def test_floats_that_matter_survive_the_round_trip() -> None:
    """The negotiated scent terms are floats, and floats are a classic divergence.

    `decay_per_step` 0.1 and `emit_intensity` 0.9 are signed terms, so a peer
    that renders them `0.10` or `9e-1` disagrees with our contract hash and the
    handshake fails before a move is played.
    """
    terms = {"decay_per_step": 0.1, "emit_intensity": 0.9, "min_center_intensity": 0.5}

    assert canonical_json(terms) == (
        '{"decay_per_step":0.1,"emit_intensity":0.9,"min_center_intensity":0.5}'
    )
