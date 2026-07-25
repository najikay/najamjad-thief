"""Property-based guarantees for commit-reveal and tamper localisation."""

from hypothesis import given, settings
from hypothesis import strategies as st

from najamjad_agent.domain.audit import audit_records
from najamjad_agent.domain.crypto import commit_of, new_nonce, seal, verify

json_scalars = st.one_of(
    st.none(), st.booleans(), st.integers(-1000, 1000), st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=40)
)
json_values = st.recursive(
    json_scalars,
    lambda children: st.one_of(st.lists(children, max_size=4), st.dictionaries(st.text(max_size=8), children, max_size=4)),
    max_leaves=8,
)
payloads = st.dictionaries(st.text(min_size=1, max_size=10), json_values, min_size=1, max_size=8)


@given(payload=payloads)
@settings(max_examples=200, deadline=None)
def test_seal_then_verify_round_trips_for_any_payload(payload) -> None:
    """Invariant: whatever we seal, we can prove we sealed it."""
    record = seal(payload)
    assert verify(record.payload, record.nonce, record.commit)


@given(payload=payloads)
@settings(max_examples=100, deadline=None)
def test_distinct_nonces_give_distinct_commits(payload) -> None:
    commits = {seal(payload).commit for _ in range(10)}
    assert len(commits) == 10


@given(payload=payloads, nonce=st.text(min_size=1, max_size=40))
@settings(max_examples=200, deadline=None)
def test_commit_is_stable_under_key_reordering(payload, nonce) -> None:
    reordered = dict(reversed(list(payload.items())))
    assert commit_of(payload, nonce) == commit_of(reordered, nonce)


@given(payload=payloads, other=payloads, nonce=st.text(min_size=1, max_size=20))
@settings(max_examples=200, deadline=None)
def test_different_payloads_do_not_share_a_commit(payload, other, nonce) -> None:
    if payload != other:
        assert commit_of(payload, nonce) != commit_of(other, nonce)


@given(
    steps=st.integers(3, 12),
    target=st.integers(0, 11),
    corruption=st.sampled_from(["payload", "nonce", "commit"]),
)
@settings(max_examples=150, deadline=None)
def test_audit_localises_exactly_the_tampered_step(steps, target, corruption) -> None:
    """Whatever is corrupted, the audit must name that step and only that step."""
    index = target % steps
    records = [seal({"step": step, "move": "N"}).audit_view() for step in range(steps)]
    if corruption == "payload":
        records[index]["payload"] = {**records[index]["payload"], "move": "S"}
    elif corruption == "nonce":
        records[index]["nonce"] = new_nonce()
    else:
        records[index]["commit"] = "0" * 64
    report = audit_records(records)
    assert not report.passed
    assert report.failed_steps == [index]
    assert len(report.verified_steps) == steps - 1


@given(steps=st.integers(1, 15))
@settings(max_examples=50, deadline=None)
def test_untampered_games_always_pass(steps) -> None:
    records = [seal({"step": step}).audit_view() for step in range(steps)]
    assert audit_records(records).passed
