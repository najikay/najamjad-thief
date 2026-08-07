"""Rule 53: every mini-game opens with a sealed declaration, and now one does.

`reporting/step_zero.py` built this payload from the first week and nothing
called it, so all six logs of every match we have filed opened at step 1. The
tests it had covered the builder in isolation and could not notice that no
production path reached it.

The load-bearing test here is `test_a_peer_can_still_audit_records_that_open_at_step_zero`.
Adding a record to the stream every audit re-hashes is the one change in this
project that can void a match for *both* teams under rules 33-35, so it is
pinned rather than reasoned about.
"""

from najamjad_agent.constants import Role
from najamjad_agent.domain.audit import audit_records
from najamjad_agent.domain.params import GameParams
from najamjad_agent.reporting.step_zero import RECORD_TYPE, STEP_ZERO
from najamjad_agent.sdk.state_setup import state_factory
from najamjad_agent.sdk.step_zero_setup import declaration_sealer

PARAMS = GameParams(
    grid_size=7,
    thief_start=(5, 5),
    cop_start=(0, 0),
    max_barriers=3,
    max_moves=30,
    survival_threshold=30,
)


class FakeManager:
    """Config the way the real manager is read: dotted keys with defaults."""

    def __init__(self, values: dict | None = None) -> None:
        self._values = values or {
            "game.group_name": "najamjad",
            "llm.model": "claude-opus-5",
            "network.opponent_group_id": "rival",
        }

    def get(self, key: str, default=None):
        return self._values.get(key, default)


class FakeMeter:
    """Only the attribute the sealer reads: the running series spend."""

    def __init__(self, spent: int) -> None:
        self.series = type("Series", (), {"spent": spent})()


def _state(sub_game: int = 1, meter=None, events: list | None = None):
    """A mini-game state built through the real factory, declaration and all."""
    emit = events.append if events is not None else None
    build = state_factory(FakeManager(), meter, emit)
    return build(PARAMS, Role.THIEF, sub_game)


def test_the_declaration_is_sealed_before_the_first_move() -> None:
    """The whole defect: step 0 existed as a function nobody called."""
    state = _state()
    state.ledger.open_audit()
    records = state.ledger.audit_payload()

    assert records, "a fresh mini-game sealed nothing at all"
    payload = records[0]["payload"]
    assert payload["step"] == STEP_ZERO
    assert payload["type"] == RECORD_TYPE
    assert payload["group_name"] == "najamjad"
    assert payload["model"] == "claude-opus-5"
    assert payload["opponent_group_id"] == "rival"
    assert payload["role"] == "thief"


def test_a_peer_can_still_audit_records_that_open_at_step_zero() -> None:
    """The risk this change carries, pinned.

    Every mini-game ends with the opponent re-hashing our revealed records. A
    record they cannot verify is read as forgery, and rules 33-35 then void the
    game for both of us — the cheapest way in this league to score zero while
    playing perfectly. `audit_records` is the same function the peer runs.
    """
    state = _state()
    state.ledger.open_audit()

    report = audit_records(state.ledger.audit_payload())

    assert report.passed, report.errors
    assert STEP_ZERO in report.verified_steps


def test_the_declaration_carries_the_series_total_so_far() -> None:
    """Token metering runs across the series, so step 0 is an opening balance.

    Reported as a running total rather than a per-game figure because that is
    what the reference declares, and because the per-game cost is then the gap
    between two consecutive declarations — see `reporting/peer_declaration`.
    """
    state = _state(sub_game=4, meter=FakeMeter(23648))
    state.ledger.open_audit()

    assert state.ledger.audit_payload()[0]["payload"]["tokens_total"] == 23648


def test_step_numbering_is_untouched_by_the_new_record() -> None:
    """Step 0 must not consume the number the first move uses.

    `GameState.step` starts at 0 and the orchestrator increments *before* it
    commits, so the first move is step 1 and the slot is free. If that ever
    changes, the first commit of every mini-game raises `ProtocolOrderError`
    and the match dies on move one.
    """
    state = _state()
    state.ledger.commit(1, {"step": 1, "move": "STAY"})
    state.ledger.open_audit()

    assert [record["payload"]["step"] for record in state.ledger.audit_payload()] == [0, 1]


def test_each_mini_game_declares_its_own_number() -> None:
    """Six games, six declarations — the sub-game number is part of the claim."""
    for number in (1, 6):
        state = _state(sub_game=number)
        state.ledger.open_audit()

        assert state.ledger.audit_payload()[0]["payload"]["sub_game"] == number


def test_an_unprobeable_host_still_plays_the_match() -> None:
    """A record is never a reason not to play.

    `EmissionPolicy.from_config` raising inside an argument list is why four
    artifacts once went unwritten; the same mistake here would kill a series
    over a `git` binary that is not on PATH.
    """
    events: list = []
    seal = declaration_sealer(FakeManager(), meter=object(), emit=events.append)
    state = _state()

    seal(state, Role.COP, 1)  # step 0 is already taken — the sealer must absorb it

    assert any(event["event"] == "step_zero.failed" for event in events)


def test_a_missing_manager_does_not_stop_the_seal() -> None:
    """Tests and bare wiring pass no manager, and still get a valid record."""
    state_without_config = state_factory()(PARAMS, Role.COP, 2)
    state_without_config.ledger.open_audit()

    assert state_without_config.ledger.audit_payload()[0]["payload"]["type"] == RECORD_TYPE


def test_the_production_runner_is_the_thing_that_seals_it() -> None:
    """The wiring, not the helper — which is the whole lesson of this defect.

    `step_zero.py` was complete, correct and covered by unit tests for weeks
    while no production path called it, exactly as `reconcile` and
    `attach_game` were before it. A test that exercises `state_factory`
    directly would have passed just as happily in that world, so this one goes
    through `build_match` and asks the runner's own state builder.
    """
    from najamjad_agent.sdk.match_setup import build_match
    from najamjad_agent.shared.events import EventBus
    from tests.role_config import load_role_config

    manager = load_role_config()
    runner = build_match(
        manager=manager,
        role=Role.COP,
        transport=object(),
        speaker=object(),
        bus=EventBus(),
        meter=FakeMeter(1200),
    )
    state = runner._build_state(GameParams.from_config(manager.as_dict()), Role.COP, 1)  # noqa: SLF001
    state.ledger.open_audit()
    payload = state.ledger.audit_payload()[0]["payload"]

    assert payload["type"] == RECORD_TYPE
    assert payload["tokens_total"] == 1200, "the runner's meter must reach the declaration"
    assert payload["github_commit"] != "", "rule 53 requires the commit we play with"
