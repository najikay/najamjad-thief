"""`--quiet`: match a peer who transmits nothing, and spend nothing doing it.

Several teams send no scent and no hints. `[emission]` could already describe
that, but only in a config file — so mirroring them meant hand-editing a TOML
before a match, which is the two-switch setup that has cost this project games
before.

And it would not have been deterministic. `EmissionPolicy.hint()` blanked the
text *after* `Speaker.compose` had already reached a vendor, so a run configured
to stay silent still paid the tokens and the latency and then sent nothing. We
spent 23,648 tokens against a peer who spent zero.
"""


from najamjad_agent.constants import Role
from najamjad_agent.domain.emission import EmissionPolicy, ScentEmission
from tests.fakes.orchestration import build_orchestrator


class _CountingSpeaker:
    """A speaker that records every time it would have called a vendor."""

    def __init__(self) -> None:
        self.calls = 0

    def compose(self, _facts):
        self.calls += 1
        return "I am near the bridge", "truth"


def _run_one_turn(policy: EmissionPolicy):
    """One thief turn under `policy`, returning the speaker and what we sent."""
    orchestrator, transport, _brain = build_orchestrator(Role.THIEF, emission=policy)
    speaker = _CountingSpeaker()
    orchestrator._speaker = speaker  # noqa: SLF001 - counting vendor calls
    orchestrator.take_turn()
    return speaker, transport.sent[-1]


def test_a_quiet_turn_never_reaches_the_vendor() -> None:
    """The whole point: silence must be free, not merely mute."""
    speaker, _ = _run_one_turn(
        EmissionPolicy(scent_mode=ScentEmission.NONE, hints=False, grid_size=7)
    )

    assert speaker.calls == 0, "composed a hint we had already decided not to send"


def test_a_talking_turn_still_composes() -> None:
    """The instrument must be able to fail; the default is unchanged."""
    speaker, _ = _run_one_turn(
        EmissionPolicy(scent_mode=ScentEmission.FULL, hints=True, grid_size=7)
    )

    assert speaker.calls == 1


def test_a_quiet_turn_sends_neither_scent_nor_hint() -> None:
    """`smell_grid` stays present-but-empty: the reference requires the key."""
    _, message = _run_one_turn(
        EmissionPolicy(scent_mode=ScentEmission.NONE, hints=False, grid_size=7)
    )

    assert message.get("hint", "") == ""
    assert message.get("smell_grid") == {}
    assert "smell_grid" in message, "the key is required even when empty"


def test_the_move_is_unaffected_by_going_quiet() -> None:
    """Moves are plain Python (rule 25); quiet must not change how we play.

    If this ever fails, `--quiet` has become a strategy switch rather than a
    disclosure switch, and a practice run would stop predicting a counted one.
    """
    loud, _, _ = build_orchestrator(
        Role.THIEF, emission=EmissionPolicy(scent_mode=ScentEmission.FULL, hints=True, grid_size=7)
    )
    quiet, _, _ = build_orchestrator(
        Role.THIEF, emission=EmissionPolicy(scent_mode=ScentEmission.NONE, hints=False, grid_size=7)
    )
    loud._speaker = _CountingSpeaker()  # noqa: SLF001
    quiet._speaker = _CountingSpeaker()  # noqa: SLF001

    loud.take_turn()
    quiet.take_turn()

    assert loud.state.own_position == quiet.state.own_position


def test_the_flag_reaches_the_config() -> None:
    """The seam. Every assertion above passes while `--quiet` is wired to nothing."""
    import ast
    import inspect

    from najamjad_agent.sdk import bootstrap, config_overrides

    source = inspect.getsource(bootstrap.build_sdk)

    assert "quiet" in inspect.signature(bootstrap.build_sdk).parameters
    assert "apply_overrides(" in source, "build_sdk no longer applies run overrides"
    assert "emission_overlay" in inspect.getsource(config_overrides), (
        "the override layer no longer resolves an emission policy"
    )
    ast.parse(source)


def test_the_two_dials_reach_a_built_mini_game_separately() -> None:
    """`--scent`/`--hints` down the real chain: overlay -> config -> mini-game.

    `emission_overlay` has its own unit tests and every one of them would pass
    in a world where nothing applied the result — which is exactly how
    `ui.host`, `step_zero`, `reconcile` and `attach_game` all shipped. So this
    runs the production `state_factory` over a real role config and reads the
    policy off a state the runner would actually play.

    The middle setting is asserted hardest: scent off, hints on — how uoh-ay26
    played all six mini-games against us, and the one combination
    `--quiet`/`--talk` could not express.
    """
    from najamjad_agent.constants import Role
    from najamjad_agent.domain.emission import emission_overlay
    from najamjad_agent.domain.params import GameParams
    from najamjad_agent.sdk.state_setup import state_factory
    from tests.role_config import load_role_config

    def policy_for(**flags):
        manager = load_role_config()
        if overlay := emission_overlay(**flags):
            manager.overlay(overlay)
        params = GameParams.from_config(manager.as_dict())
        return state_factory(manager)(params, Role.THIEF, 1).emission

    mirror = policy_for(scent="none", hints=True)
    assert mirror.scent_mode.value == "none"
    assert mirror.hints is True, "a peer who speaks but does not emit must be matchable"

    assert policy_for(hints=False).scent_mode.value == "full", "one dial must not move the other"
    assert policy_for(quiet=True).hints is False
    assert policy_for().scent_mode.value == "full", "a bare run must keep the shipped default"


def test_both_new_dials_are_actually_passed_on() -> None:
    """The seam again, for the two parameters added beside `quiet`.

    A parameter can be accepted and dropped on the floor; the signature alone
    proves nothing. This pins that `build_sdk` hands all three to the resolver.
    """
    import inspect

    from najamjad_agent.sdk import bootstrap, config_overrides

    params = inspect.signature(bootstrap.build_sdk).parameters

    assert {"quiet", "scent", "hints"} <= set(params)
    # Both links: build_sdk must hand all three on, and the override layer must
    # feed all three to the resolver. Either half alone passes while the other
    # drops them on the floor.
    assert "quiet, scent, hints" in inspect.getsource(bootstrap.build_sdk)
    assert "emission_overlay(quiet, scent, hints)" in inspect.getsource(config_overrides)
