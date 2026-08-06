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

import pytest

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


def test_the_hash_we_publish_is_the_hash_we_sign() -> None:
    """`docs/HOW_TO_PLAY_US.md` §3 prints a digest for opponents to check against.

    A published number that drifts from the code is worse than none: a team
    computes it, matches it, and still fails the handshake — and they will
    reasonably conclude the fault is theirs. This ties the document to the
    config so the two cannot separate silently.
    """
    import re

    from najamjad_agent.negotiation.contract import contract_hash
    from najamjad_agent.negotiation.terms import terms_from_config
    from tests.role_config import REPO_ROOT, load_role_config

    root = REPO_ROOT
    manager = load_role_config()
    published = re.findall(
        r"^([0-9a-f]{64})$", (root / "docs/HOW_TO_PLAY_US.md").read_text(encoding="utf-8"), re.M
    )

    assert published, "HOW_TO_PLAY_US no longer publishes a contract hash"
    assert contract_hash(terms_from_config(manager)) in published


# --- Cross-checked against the published interop kit, 2026-08-05 -------------
# Values taken from github.com/Imreec/copthief-league-protocol `vectors/`, run
# against our own implementation. Every one passed on the first attempt. They
# are reproduced here rather than fetched so the suite stays offline and so a
# divergence is caught by our gate rather than by an opponent's audit.

KIT_CANONICAL = [
    ({"b": 1, "a": {"d": 4, "c": 3}}, '{"a":{"c":3,"d":4},"b":1}'),
    ({"hint": "אני ליד הכיכר", "move": "MOVE:N"}, '{"hint":"אני ליד הכיכר","move":"MOVE:N"}'),
    ({"emoji": "🙂", "x": 1}, '{"emoji":"🙂","x":1}'),
    ({"a": True, "b": None, "c": [1, 2, 3]}, '{"a":true,"b":null,"c":[1,2,3]}'),
]


@pytest.mark.parametrize(("payload", "expected"), KIT_CANONICAL)
def test_we_agree_with_the_published_kit(payload, expected) -> None:
    """An independent implementation's expectations, not our own round-trip."""
    assert canonical_json(payload) == expected


def test_keys_sort_by_code_point_not_utf16_code_unit() -> None:
    """The divergence we could never have found alone.

    `U+FF5E` sorts *before* `U+1F642` by code point, which is what Python does.
    A UTF-16 code-unit sort — JavaScript's `Object.keys().sort()`, and Java and
    C# by default — orders them the other way, because the surrogate `0xD83D`
    compares below `0xFF5E`. Every hash of any payload containing both would
    then differ, and neither side could see why.

    Credited to anrbj666 via the interop kit; we are correct here by Python's
    default rather than by design, which is exactly why it needs a test.
    """
    assert canonical_json({"🙂": "astral key", "～": "high-BMP key"}) == (
        '{"～":"high-BMP key","🙂":"astral key"}'
    )


def test_float_repr_is_pinned_at_the_exponent_cliff() -> None:
    """`1e-07` not `1e-7`; `1e+16` not the expanded integer.

    Game values never reach these magnitudes, but the canonical form is pinned
    to these bytes regardless, and other languages' shortest-repr rules differ
    here. Pinned so a future switch to a different serializer is caught.
    """
    assert canonical_json({"tiny": 1e-07, "huge": 1e16}) == '{"huge":1e+16,"tiny":1e-07}'


def test_our_commit_is_the_reference_form_not_a_book_listing() -> None:
    """The release publishes **three** commit constructions and they disagree.

    All three hash the same sealed record to different digests. One of them,
    `book_audit_snippet_form`, structurally consumes only `nonce|move` — so it
    binds neither state nor intent, and position or bluff tampering would go
    undetected by it entirely.

    A team that implemented from one of the book's illustrative listings rather
    than the reference will mutually `tamper_forfeit` against us on the first
    audit, and both sides score zero (rules 33-35). This asserts which of the
    three we are, using the kit's own record and expected digests.
    """
    payload = {
        "step": 1,
        "state": "grid=7x7;self=[4, 3];barriers=[]",
        "position": [4, 3],
        "move": "MOVE:S",
        "intent": "truth",
        "hint": "I keep to the main avenues.",
    }
    nonce = "112233445566778899aabbccddeeff00"
    reference_form = "aa6420e2d3a907d6c140856caecbb351b4d5ad98e381549c28268669af378dcc"
    book_ch5_listing_form = "833e47c675448a9072660b984d8514a5786792372f415caea1b0d4348b301875"
    book_audit_snippet_form = "8041fe9546f17d67b1c60b881b79daf20f932a2dcbc7ee87fb92c4c1bdfaa9a0"

    ours = commit_of(payload, nonce)

    assert ours == reference_form
    assert ours != book_ch5_listing_form
    assert ours != book_audit_snippet_form


def test_the_kit_step_zero_and_non_ascii_records_match() -> None:
    """Their other two CORE commit vectors, including an astral-emoji hint."""
    assert commit_of(
        {
            "step": 0,
            "type": "system_spec",
            "spec": {"os": "Linux", "cpu_cores": 4, "ram_gb": 16.0, "vram_gb": 0.0},
            "model": "cli-default",
            "code_version": "1.0",
            "group_name": "Example-Team",
            "sub_game_number": 1,
        },
        "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
    ) == "69c9a786d18829990291cd0ffb768eacfa009011b0c89a6f4f32330551e2003e"

    assert commit_of(
        {
            "step": 2,
            "state": "grid=7x7;self=[2, 4];barriers=[[1, 1]]",
            "position": [2, 4],
            "move": "MOVE:N",
            "intent": "lie",
            "hint": "אני ליד הכיכר 🙂",
        },
        "deadbeefcafef00dfeedface00c0ffee",
    ) == "2caaeb0a7e656868b85166a9ebe34226bae4fdcb79cb7a0a23759121769d9338"
