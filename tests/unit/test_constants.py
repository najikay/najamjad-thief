"""Unit tests for najamjad_agent.constants (happy path + integrity checks)."""

from najamjad_agent.constants import MOVE_DELTAS, EndReason, Intent, Move, Phase, Role


def test_move_set_matches_binding_rule() -> None:
    """Appendix F Table 15 (fixed): exactly four orthogonal moves plus STAY."""
    assert {m.value for m in Move} == {"N", "S", "E", "W", "STAY"}


def test_move_deltas_cover_every_move_and_are_orthogonal() -> None:
    """Every move has a delta; no diagonal delta exists (book rules 13-14)."""
    assert set(MOVE_DELTAS) == set(Move)
    for row_delta, col_delta in MOVE_DELTAS.values():
        assert abs(row_delta) + abs(col_delta) <= 1


def test_stay_has_zero_delta() -> None:
    assert MOVE_DELTAS[Move.STAY] == (0, 0)


def test_roles_match_reference_wire_vocabulary() -> None:
    """Role strings must interoperate with the reference simulator (ADR-001)."""
    assert Role.COP.value == "police"
    assert Role.THIEF.value == "thief"


def test_intent_values() -> None:
    assert {i.value for i in Intent} == {"truth", "lie"}


def test_phase_set_matches_plan_fsm() -> None:
    """PLAN §2.1 state machine: all mandated states present, incl. terminal loss."""
    expected = {
        "negotiating",
        "waiting_for_opponent",
        "computing_move",
        "committing",
        "awaiting_reveal",
        "verifying",
        "game_end",
        "auditing",
        "reporting",
        "technical_loss",
    }
    assert {p.value for p in Phase} == expected


def test_end_reasons_are_reference_compatible() -> None:
    assert {e.value for e in EndReason} >= {"capture", "survival", "tamper_forfeit"}
