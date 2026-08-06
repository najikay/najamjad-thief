"""The settlement signature uses the release's *spaced* form, not our canonical one.

Every other hash in this project uses compact canonical JSON. This one does not:
`json.dumps(report, sort_keys=True, ensure_ascii=False)` with default separators
(`", "` and `": "`), signed *before* the signature key is inserted.

Using the compact form here fails at the single moment both teams must agree,
and rules 33-35 then void the match for both. The vectors below are the ones
published by the interop kit (found by alonengel / anrbj666), including their
`compact_form_sha256` counter-examples — so this file proves the divergence
exists rather than taking it on faith.
"""

import hashlib
import json

from najamjad_agent.protocol.canonical import canonical_json
from najamjad_agent.reporting.consensus import (
    SIGNATURE_KEY,
    settlement_signature,
    sign_report,
    verify_report,
)

HEBREW_REPORT = {
    "קבוצה_א": "team-aleph",
    "קבוצה_ב": "team-bet",
    "תוצאה": {"מנצחת": "team-aleph", "ניקוד": [20, 5]},
    "game_uid": "f757f50d-d4f4-17e7-06cf-755905739b16",
    "tokens_total_series": 0,
    "github_commit": "abc1234",
}
HEBREW_SIGNATURE = "af661c4101cfe73470794102ab7417b67ef0ea5b8c3bc55b38133ac5f8e95049"
HEBREW_COMPACT = "a87d61b5c1b7ea838a8e5fc7acc9f9004e28e50acb8c243431ab6ff78be33397"

NESTED_REPORT = {
    "סדרה": [{"משחקון": 1, "ניקוד": [5, 10]}, {"משחקון": 2, "ניקוד": [20, 5]}],
    "ram_gb": 31.8,
    "decay_per_step": 0.1,
    "mutual_agreement": True,
}
NESTED_SIGNATURE = "77c4cce023b641406db0dd3efd7ca44563aa8e4b8eaa9e02c128fa9b9ef7bbd7"
NESTED_COMPACT = "4f9234b867116a1367245a65a0b18ff0f1390bea65f982e42576104321b6845b"


def test_we_reproduce_the_published_settlement_signatures() -> None:
    """Their vectors, our code — the whole point of having them."""
    assert settlement_signature(HEBREW_REPORT) == HEBREW_SIGNATURE
    assert settlement_signature(NESTED_REPORT) == NESTED_SIGNATURE


def test_the_compact_form_would_not_settle() -> None:
    """The counter-example, so nobody 'tidies' this into `canonical_json`.

    These are the kit's own `compact_form_sha256` values. Reproducing them
    proves the two forms genuinely differ on the same input — a team signing
    compact fails settlement against a team signing spaced, and neither can see
    why from their own side.
    """
    for report, spaced, compact in (
        (HEBREW_REPORT, HEBREW_SIGNATURE, HEBREW_COMPACT),
        (NESTED_REPORT, NESTED_SIGNATURE, NESTED_COMPACT),
    ):
        assert hashlib.sha256(canonical_json(report).encode()).hexdigest() == compact
        assert compact != spaced


def test_the_signature_is_computed_before_the_key_is_inserted() -> None:
    """Sign-then-insert, which is what makes it verifiable at the other end.

    A peer checks it by popping the key, re-serializing spaced and re-hashing.
    That only works if the value covers the report *without* itself.
    """
    signed = sign_report(HEBREW_REPORT)

    assert signed[SIGNATURE_KEY] == HEBREW_SIGNATURE
    assert {k: v for k, v in signed.items() if k != SIGNATURE_KEY} == HEBREW_REPORT
    assert verify_report(signed)


def test_signing_twice_is_stable() -> None:
    """Re-signing an already-signed report must not hash its own signature."""
    once = sign_report(HEBREW_REPORT)

    assert sign_report(once) == once


def test_a_tampered_report_fails_verification() -> None:
    """What the signature is for: a changed score no longer verifies."""
    signed = sign_report(HEBREW_REPORT)
    tampered = {**signed, "תוצאה": {"מנצחת": "team-bet", "ניקוד": [5, 20]}}

    assert verify_report(signed)
    assert not verify_report(tampered)


def test_hebrew_keys_are_not_escaped() -> None:
    """`ensure_ascii=False` on a Hebrew-keyed report is every byte of it."""
    body = json.dumps(HEBREW_REPORT, sort_keys=True, ensure_ascii=False)

    assert "\\u" not in body
    assert "קבוצה_א" in body


def test_the_graded_result_carries_no_signature_and_still_validates(tmp_path) -> None:
    """It is **not** in the result artifact, and this pins why.

    A first attempt inserted it there, after `validate_egress` — so the emailed
    bytes were the only artifact content that never passed validation, and
    `ResultArtifact` is `extra="forbid"`, meaning a strict grader or peer would
    reject the entire report (rule 35). The reference also carries this key in
    its legacy Hebrew match log, not in the result file.
    """
    from najamjad_agent.protocol.schemas_report import ResultArtifact
    from najamjad_agent.reporting.artifacts import ArtifactWriter

    sub_games = [
        {
            "sub_game_number": 1,
            "roles": {"najamjad": "police", "rival": "thief"},
            "result": "capture",
            "winner_group": "najamjad",
            "tie": False,
            "score": {"najamjad": 20, "rival": 5},
            "audit": {"log_verified": True, "tampered": False},
        }
    ]
    final = {
        "total_score": {"najamjad": 20, "rival": 5},
        "sub_games_won": {"najamjad": 1, "rival": 0},
        "ties": 0,
        "winner_group": "najamjad",
        "series_tie": False,
    }
    writer = ArtifactWriter(tmp_path, "najamjad-vs-rival", "uid-1", ("najamjad", "rival"))
    path = writer.write_result(sub_games, final, "rival", confirmed=True)
    written = json.loads(path.read_text(encoding="utf-8"))

    assert SIGNATURE_KEY not in written
    # The real assertion: whatever we publish must survive its own schema.
    ResultArtifact.model_validate(written)
