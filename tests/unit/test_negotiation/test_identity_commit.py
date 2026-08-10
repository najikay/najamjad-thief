"""We negotiated without ever declaring our commit (T-2537).

Rule 53 makes the commit each side plays with mandatory, and we put it in two of
the three places it belongs: sealed into every step-0 record, and written into
every result artifact. **Never into the handshake identity** — which is where a
peer validating the negotiated block looks.

uoh-ay26 blocked their own six-game submission over it on 2026-08-08: "the
opponent negotiated without providing a valid 40-character Git commit SHA".
They were right, and the shape of the defect is the dangerous one — it cost them
a report and cost us nothing visible, so nothing on our side ever complained.
"""

import re

from najamjad_agent.negotiation.identity import identity_from_config
from tests.role_config import load_role_config

SHA = re.compile(r"^[0-9a-f]{40}$")


def _identity() -> dict:
    return identity_from_config(load_role_config())


def test_the_handshake_declares_a_real_commit() -> None:
    """A 40-character SHA, which is what their validator asked for by name."""
    identity = _identity()

    assert SHA.match(identity["git_commit_hash"]), identity["git_commit_hash"]


def test_both_spellings_carry_the_same_value() -> None:
    """`git_commit_hash` is what reference-derived peers send and read.

    `github_commit` is the name the book gives the same value in the result
    email (rule 53). Two keys, one value: a few bytes against a whole class of
    "which name did they use" failure.
    """
    identity = _identity()

    assert identity["git_commit_hash"] == identity["github_commit"]


def test_the_commit_matches_what_our_own_artifacts_report() -> None:
    """One value in three places, or the report contradicts the handshake.

    A peer comparing our declared identity against the `github_commit` in our
    emailed result must find the same string; two different answers about which
    code we played is exactly the contradiction rules 33-35 void a match for.
    """
    from najamjad_agent.shared.sysinfo import git_commit

    assert _identity()["git_commit_hash"] == git_commit()


def test_every_key_the_reference_indexes_is_present() -> None:
    """Their `group_block()` indexes these directly — a miss is a KeyError.

    And it raises in *their* process after the games are played, losing the
    series to a missing dictionary key rather than to anything we did on the
    board. We shipped without `members` once and did exactly that.
    """
    identity = _identity()

    for key in ("group_id", "group_name", "members", "repos", "mcp_servers",
                "llm_model", "spec", "counted_matches_played", "git_commit_hash"):
        assert key in identity, f"identity is missing {key!r}"
