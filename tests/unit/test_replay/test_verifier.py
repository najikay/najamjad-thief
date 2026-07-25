"""Re-verification, and the two banners it produces.

The golden tests here are the ones that matter for submission: the lecturer's
own sample log must replay to `Verified OK`, and a log we corrupted on purpose
must replay to `TAMPERED` pointing at the exact step we edited. A verifier that
passes everything is indistinguishable from one that does nothing, which is why
the negative fixture is built and asserted rather than assumed.
"""

from pathlib import Path

import pytest

from najamjad_agent.domain.crypto import seal
from najamjad_agent.replay.verifier import verify_log

GOLDENS = Path(__file__).resolve().parents[2] / "goldens" / "artifacts"
REFERENCE = GOLDENS / "log_segal-police-team-vs-segal-thief-team_g01.json"
TAMPERED = GOLDENS / "log_tampered_step7.json"


def clean_log(steps: int = 3) -> dict:
    """A small honest log, sealed the way the game seals one."""
    records = []
    for step in range(1, steps + 1):
        sealed = seal({"step": step, "state": f"grid=7x7;self=[{step}, 0];barriers=[]"})
        records.append(sealed.audit_view())
    return {"records": records}


@pytest.mark.goldens
def test_the_reference_sample_log_replays_verified_ok():
    """T-1911: the lecturer's own artifact must pass our viewer end to end."""
    result = verify_log(REFERENCE)

    assert result.banner == "Verified OK"
    assert result.passed is True
    assert result.void is False
    assert len(result.steps) == 19
    assert result.failed_indices == []


@pytest.mark.goldens
def test_the_tampered_fixture_replays_tampered_at_exactly_the_edited_step():
    """T-1903/T-1912: localisation, not just a verdict."""
    result = verify_log(TAMPERED)

    assert result.banner == "TAMPERED"
    assert result.void is True
    assert result.failed_indices == [7]
    assert sum(1 for step in result.steps if step.verified) == 18


@pytest.mark.goldens
def test_the_tampered_fixture_differs_from_the_reference_only_at_step_seven():
    """Guards the fixture itself: a negative test that stopped biting is worse
    than no test, so prove the corruption is present and narrow."""
    import json

    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))["records"]
    tampered = json.loads(TAMPERED.read_text(encoding="utf-8"))["records"]

    differing = [index for index, (a, b) in enumerate(zip(reference, tampered, strict=True)) if a != b]

    assert differing == [7]


def test_a_clean_log_verifies_every_step():
    result = verify_log(clean_log())

    assert result.passed is True
    assert [step.step for step in result.steps] == [1, 2, 3]
    assert all(step.recomputed == step.commit for step in result.steps)


@pytest.mark.parametrize("target", [0, 1, 2])
def test_editing_any_single_step_flags_exactly_that_step(target):
    log = clean_log()
    log["records"][target]["payload"]["state"] = "grid=7x7;self=[6, 6];barriers=[]"

    result = verify_log(log)

    assert result.failed_indices == [target]
    assert result.banner == "TAMPERED"


def test_a_swapped_nonce_is_caught():
    """Reusing another step's nonce must not verify (book rule 18)."""
    log = clean_log()
    log["records"][1]["nonce"] = log["records"][0]["nonce"]

    result = verify_log(log)

    assert result.failed_indices == [1]


def test_a_record_missing_its_commitment_fails_with_a_reason():
    log = clean_log(steps=1)
    log["records"][0]["commit"] = ""

    result = verify_log(log)

    assert result.passed is False
    assert result.steps[0].reason == "no commitment stored"


def test_a_malformed_record_produces_a_verdict_rather_than_an_exception():
    """A peer sending garbage must not crash us into a technical loss."""
    result = verify_log({"records": [{"payload": "not an object", "nonce": 1, "commit": None}]})

    assert result.passed is False
    assert result.steps[0].reason == "record is malformed"


def test_the_failure_reason_names_what_went_wrong():
    log = clean_log(steps=1)
    log["records"][0]["payload"]["move"] = "MOVE:N"

    result = verify_log(log)

    assert "does not produce the stored commit" in result.steps[0].reason
    assert result.steps[0].recomputed != result.steps[0].commit


def test_the_viewer_verdict_never_disagrees_with_the_audit():
    """Both must come from `domain.audit`, or nobody knows which to believe."""
    from najamjad_agent.domain.audit import audit_records

    log = clean_log(steps=4)
    log["records"][2]["payload"]["hint"] = "edited after the fact"
    result = verify_log(log)

    assert result.report == audit_records(result.records)
    assert result.report.failed_steps == [step.step for step in result.steps if not step.verified]
