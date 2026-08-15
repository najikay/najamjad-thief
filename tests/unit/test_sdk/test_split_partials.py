"""Clearing our own half-series, at the one moment it is safe to.

Book Appendix ה rule 1 runs the two roles as two processes, and each leaves its
half of the series on disk for the other to merge (`reporting/sibling_merge`).
Which half belongs to *this* attempt cannot be decided by any clock — the two
halves are independent streams — so it is decided by deletion instead.
"""


def test_a_split_series_drops_the_half_it_left_behind_before_playing(tmp_path, monkeypatch):
    """`game_uid` is deterministic, so a replayed series reuses the filename.

    An earlier attempt's half would otherwise be merged into the new one and
    file a report describing games from two runs — self-contradictory in the
    way rules 33-35 void both teams for. No clock can separate them (see
    `sibling_merge.clear_partials`), so each process removes its own before it
    plays. Through `play_match` rather than by calling the helper directly,
    because the moment matters as much as the act: `preflight` and `peer` build
    the same runner, and clearing there would delete a half our sibling is
    still waiting to merge.
    """
    from najamjad_agent.constants import Role
    from najamjad_agent.reporting.sibling_merge import partial_path, write_partial
    from najamjad_agent.sdk import actions as actions_module
    from najamjad_agent.sdk.actions import AgentActions

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(actions_module, "wait_for_opponent", lambda *_a, **_k: True)
    write_partial(tmp_path, "uid-1", Role.COP, [], [])
    write_partial(tmp_path, "uid-1", Role.THIEF, [], [])

    class Tracker:
        our_role = Role.COP
        outcomes: list = []

    class Match:
        tracker = Tracker()
        games: list = []

        def play_series(self):
            return "played"

    AgentActions(opponent_url="https://peer.invalid/mcp", match=Match()).play_match()

    assert not partial_path(tmp_path, "uid-1", Role.COP).exists()
    assert partial_path(tmp_path, "uid-1", Role.THIEF).exists(), "never our sibling's"
