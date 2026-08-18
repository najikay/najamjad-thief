"""The warm-up probe: six candidates, one per window, and the counted pick.

The risk this file exists for is not that the probe chooses badly — a warm-up is
uncounted, so a bad choice costs nothing. It is that the machinery which *makes*
the choice breaks a match. A counted series is played once, so every failure path
here has to end at the shipped brain rather than at an exception, and a counted
run with nothing saved has to behave exactly as it did before any of this existed.
"""

import json

from najamjad_agent.constants import Role
from najamjad_agent.sdk.probe import load_choice, rank, save_choice, score_key, winners
from najamjad_agent.strategy.cop_brain import CopBrain
from najamjad_agent.strategy.seal_cop import SealCop
from najamjad_agent.strategy.thief_brain import ThiefBrain
from najamjad_agent.strategy.variants import (
    COPS,
    THIEVES,
    candidate,
    for_window,
    probing,
)

FULL, PROBE = "full", "sandbagged"


def test_each_window_draws_a_different_candidate() -> None:
    """Three windows per role, three candidates, in a stable order."""
    cops = [for_window("cop", n).name for n in (2, 4, 6)]
    thieves = [for_window("thief", n).name for n in (1, 3, 5)]

    assert cops == [one.name for one in COPS]
    assert thieves == [one.name for one in THIEVES]
    assert len(set(cops)) == 3 and len(set(thieves)) == 3


def test_the_mapping_holds_when_we_open_as_police() -> None:
    """The opening role decides which set of windows a role holds, not the order."""
    assert [for_window("cop", n).name for n in (1, 3, 5)] == [one.name for one in COPS]


def test_probing_is_retired_at_every_level() -> None:
    """`probing` is off, and that is the whole point of the retirement.

    These two tests used to assert the opposite — that a warm-up handicapped
    each candidate to depth 1 without flattening the dial the candidates vary,
    and that `SealCop` was reachable as window 6's cop. Both described real
    behaviour and both were retired on 2026-08-18 for the reason recorded in
    `variants.probing`: at depth 1 all three thieves were captured on exactly
    step 12 and all three cops survived to exactly 34, so six windows produced
    one data point and a ranking decided by list order — and, worse, a counted
    series could be played by a deliberately crippled agent.

    So the invariant is now the inverse: no level probes, and no level
    handicaps.
    """
    assert probing(PROBE) is False, "the level that used to probe"
    assert probing(FULL) is False


def test_no_level_can_reach_a_candidate_or_a_handicap() -> None:
    """Whatever the level, an unprobed run is the shipped brain with no dials.

    `SealCop` still ships — it is what `cop_class` names in `config/*/game.toml`
    — but it arrives through configuration, not through the window roster. This
    test is about the roster no longer being able to substitute a brain behind a
    match's back.
    """
    for level in (PROBE, FULL):
        cop, cop_dials = candidate(Role.COP, 6, level, "them", CopBrain)
        thief, thief_dials = candidate(Role.THIEF, 3, level, "them", ThiefBrain)

        assert (cop, cop_dials) == (CopBrain, {})
        assert (thief, thief_dials) == (ThiefBrain, {})


def test_the_roster_is_kept_coherent_for_reference() -> None:
    """It is documentation now, but broken documentation is worse than none."""
    assert SealCop in {one.brain for one in COPS}, "still listed for reference"


def test_a_counted_run_with_nothing_saved_is_exactly_what_shipped(tmp_path, monkeypatch) -> None:
    """The safety property. No probe file must mean no behaviour change at all."""
    monkeypatch.chdir(tmp_path)

    for role, shipped in ((Role.COP, CopBrain), (Role.THIEF, ThiefBrain)):
        for window in (1, 2, 3, 4, 5, 6):
            brain, dials = candidate(role, window, FULL, "nobody", shipped)
            assert brain is shipped
            assert dials == {}


def test_a_counted_run_plays_what_the_probe_chose(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    save_choice(tmp_path, "MOAAMOHA", {"cop": "seal", "thief": "roomy"})

    cop, cop_dials = candidate(Role.COP, 2, FULL, "MOAAMOHA", CopBrain)
    _thief, thief_dials = candidate(Role.THIEF, 1, FULL, "MOAAMOHA", ThiefBrain)

    assert cop is SealCop
    assert "lookahead" not in cop_dials, "a counted run is never handicapped"
    assert thief_dials == {"stall_room_weight": 8.0}


def test_the_choice_is_per_opponent(tmp_path) -> None:
    """What beats a cornering thief is not what beats one that hides in space."""
    save_choice(tmp_path, "alpha", {"cop": "seal"})
    save_choice(tmp_path, "beta", {"cop": "walls"})

    assert load_choice(tmp_path, "alpha", "cop") == "seal"
    assert load_choice(tmp_path, "beta", "cop") == "walls"
    assert load_choice(tmp_path, "ALPHA", "cop") == "seal", "a card's casing must not split it"


def test_every_broken_choice_file_falls_back_rather_than_raising(tmp_path, monkeypatch) -> None:
    """Absent, unreadable, wrong shape, retired name — all mean the shipped brain."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "workspace" / "probe_choice.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    for body in ("", "{", "[]", '{"them": {"picks": {"cop": "a-name-we-retired"}}}'):
        path.write_text(body, encoding="utf-8")
        assert load_choice(tmp_path, "them", "cop") in ("", "a-name-we-retired")
        brain, dials = candidate(Role.COP, 2, FULL, "them", CopBrain)
        assert brain is CopBrain and dials == {}


def test_a_cop_is_ranked_on_capturing_early_and_a_thief_on_lasting() -> None:
    assert score_key("cop", "capture", 9) < score_key("cop", "capture", 30)
    assert score_key("cop", "capture", 30) < score_key("cop", "survival", 35)
    assert score_key("thief", "survival", 35) < score_key("thief", "capture", 30)
    assert score_key("thief", "capture", 30) < score_key("thief", "capture", 9)


def test_the_winner_is_the_best_window_per_role() -> None:
    rows = [
        {"side": "cop", "variant": "pursuit", "end_reason": "survival", "steps": 35},
        {"side": "cop", "variant": "seal", "end_reason": "capture", "steps": 22},
        {"side": "cop", "variant": "walls", "end_reason": "capture", "steps": 11},
        {"side": "thief", "variant": "safety", "end_reason": "capture", "steps": 14},
        {"side": "thief", "variant": "roomy", "end_reason": "survival", "steps": 35},
        {"side": "thief", "variant": "tight", "end_reason": "capture", "steps": 28},
    ]

    assert winners(rows) == {"cop": "walls", "thief": "roomy"}
    assert [row["variant"] for row in rank([r for r in rows if r["side"] == "cop"])] == [
        "walls", "seal", "pursuit"]


def test_the_choice_file_is_readable_by_a_person(tmp_path) -> None:
    """It is evidence about an opponent; an operator has to be able to check it."""
    path = save_choice(tmp_path, "them", {"cop": "seal"}, [{"sub_game": 2, "variant": "seal"}])

    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["them"]["picks"]["cop"] == "seal"
    assert body["them"]["evidence"][0]["sub_game"] == 2
