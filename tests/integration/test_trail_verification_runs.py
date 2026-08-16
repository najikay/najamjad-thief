"""The trail check must actually run in a real series, not merely exist.

`verify_trail` and its `FrameLog` are pure and unit-tested, which is exactly the
shape of the components this project has repeatedly found finished, tested and
never called — the artifact writer, the reconciler, the session guard, the
thief's strength dial. Every one of them passed its own tests while doing
nothing in a match.

So this drives the real `MatchRunner` against a real opponent link and asserts
the verdict reaches the event log. The two-process harness cannot serve as this
proof: it writes into a `TemporaryDirectory` that is deleted when it exits, so
its events are gone before anyone can read them.
"""

from __future__ import annotations

from najamjad_agent.constants import Role
from tests.fakes.network import linked_pair
from tests.integration.test_match_series import build_runner, play_pair


def test_a_played_series_emits_a_trail_verdict() -> None:
    """One verdict per audited mini-game, naming what it could check."""
    captured: list[dict] = []
    left, right = linked_pair()
    cop_first = build_runner(left, "najamjad", "rival", Role.COP)
    thief_first = build_runner(right, "rival", "najamjad", Role.THIEF)
    cop_first._emit = captured.append  # noqa: SLF001

    play_pair(cop_first, thief_first)

    verdicts = [e for e in captured if str(e.get("event", "")).startswith("scent.trail_")]
    assert verdicts, "the trail check never ran in a played series"
    for verdict in verdicts:
        assert set(verdict) >= {"event", "checked", "agreed", "unverifiable", "mismatches"}


def test_an_honest_peer_is_verified_rather_than_merely_unchecked() -> None:
    """`checked` separates "we looked and agreed" from "there was nothing to
    look at". A silent peer scores clean on both, and the two must not read the
    same — that ambiguity is the reason this module exists."""
    captured: list[dict] = []
    left, right = linked_pair()
    cop_first = build_runner(left, "najamjad", "rival", Role.COP)
    thief_first = build_runner(right, "rival", "najamjad", Role.THIEF)
    cop_first._emit = captured.append  # noqa: SLF001

    play_pair(cop_first, thief_first)

    verdicts = [e for e in captured if str(e.get("event", "")).startswith("scent.trail_")]
    assert any(v["checked"] > 0 for v in verdicts), (
        "every frame was unverifiable — the grids are not reaching the log"
    )
    assert all(v["event"] == "scent.trail_verified" for v in verdicts), (
        "our own emission failed its own honesty check"
    )
