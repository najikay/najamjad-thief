"""Tests for the three capture paths, the truth duty, and survival resolution."""

from najamjad_agent.constants import EndReason
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.capture import (
    answer_capture_claim,
    evaluate_barrier_capture,
    evaluate_capture,
    is_immobilised,
    resolve_survival,
)


def _boxed(board: Board, cell: tuple[int, int] = (3, 3)) -> Board:
    row, col = cell
    for neighbour in [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]:
        board = board.with_barrier(neighbour)
    return board


def test_cop_on_thief_cell_with_claim_captures(board: Board) -> None:
    verdict = evaluate_capture(board, (3, 3), (3, 3), capture_claim=True)
    assert verdict.captured
    assert verdict.reason == "claim"
    assert verdict.end_reason is EndReason.CAPTURE


def test_cop_on_thief_cell_without_claim_is_not_capture(board: Board) -> None:
    """Co-location alone never captures — the claim must be declared (FR-ENG-4)."""
    verdict = evaluate_capture(board, (3, 3), (3, 3), capture_claim=False)
    assert not verdict.captured
    assert verdict.reason == "unclaimed"
    assert verdict.end_reason is None


def test_claim_on_a_different_cell_does_not_capture(board: Board) -> None:
    assert not evaluate_capture(board, (2, 3), (3, 3), capture_claim=True).captured


def test_barrier_on_thief_cell_captures() -> None:
    assert evaluate_barrier_capture((3, 3), (3, 3)).captured
    assert evaluate_barrier_capture((3, 3), (3, 3)).reason == "barrier"


def test_barrier_elsewhere_does_not_capture() -> None:
    assert not evaluate_barrier_capture((2, 3), (3, 3)).captured


def test_walled_in_thief_is_immobilised(board: Board) -> None:
    assert is_immobilised(_boxed(board), (3, 3))
    assert not is_immobilised(board, (3, 3))


def test_corner_thief_needs_only_two_barriers(board: Board) -> None:
    """Board edges count toward immobilisation (book rule 47)."""
    trapped = board.with_barrier((1, 0)).with_barrier((0, 1))
    assert is_immobilised(trapped, (0, 0))


def test_immobilisation_captures_even_without_claim(board: Board) -> None:
    verdict = evaluate_capture(_boxed(board), (0, 0), (3, 3), capture_claim=False)
    assert verdict.captured
    assert verdict.reason == "immobilised"


def test_capture_answer_is_truthful_for_a_hit() -> None:
    assert answer_capture_claim((3, 3), (3, 3)) is True


def test_capture_answer_is_truthful_for_a_miss() -> None:
    assert answer_capture_claim((3, 3), (2, 3)) is False


def test_capture_answer_accepts_list_encodings_from_the_wire() -> None:
    assert answer_capture_claim((3, 3), [3, 3]) is True  # type: ignore[arg-type]


def test_survival_triggers_at_the_threshold() -> None:
    assert resolve_survival(35, 35, 35) is EndReason.SURVIVAL
    assert resolve_survival(36, 35, 35) is EndReason.SURVIVAL


def test_survival_does_not_trigger_early() -> None:
    assert resolve_survival(34, 35, 35) is None


def test_step_cap_resolves_as_survival_when_lower_than_threshold() -> None:
    """PRD A2 documented interpretation: reaching the cap = thief survived."""
    assert resolve_survival(35, 40, 35) is EndReason.SURVIVAL
