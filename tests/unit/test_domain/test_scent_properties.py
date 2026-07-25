"""Property-based invariants for scent physics (guidelines §6.3 edge coverage)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from najamjad_agent.domain.scent import ScentField
from najamjad_agent.domain.scent_models import ScentModel, decay_value

BOARD = 7
cells = st.tuples(st.integers(0, BOARD - 1), st.integers(0, BOARD - 1))
models = st.sampled_from(list(ScentModel))


@given(centres=st.lists(cells, min_size=1, max_size=12), model=models)
@settings(max_examples=150, deadline=None)
def test_intensities_stay_within_bounds_after_any_deposit_sequence(centres, model) -> None:
    """Invariant: every intensity lies in [0, ceiling] no matter the history."""
    field = ScentField(board_size=BOARD, model=model)
    for centre in centres:
        field.deposit(centre)
    values = field.snapshot().values()
    assert all(0.0 < value <= field.ceiling for value in values)


@given(
    centres=st.lists(cells, min_size=1, max_size=8),
    decays=st.integers(0, 12),
    model=models,
)
@settings(max_examples=150, deadline=None)
def test_decay_is_monotone_without_new_emission(centres, decays, model) -> None:
    """Invariant: with no new deposits, no cell can ever gain intensity."""
    field = ScentField(board_size=BOARD, model=model)
    for centre in centres:
        field.deposit(centre)
    before = field.snapshot()
    for _ in range(decays):
        field.decay_all()
    after = field.snapshot()
    assert all(value <= before[key] for key, value in after.items())


@given(value=st.floats(0.0, 0.9), decay=st.floats(0.01, 0.5), model=models)
@settings(max_examples=200, deadline=None)
def test_single_decay_step_never_leaves_the_valid_range(value, decay, model) -> None:
    result = decay_value(value, decay, model)
    assert 0.0 <= result <= max(value, 0.0)


@given(payload=st.dictionaries(st.text(max_size=8), st.floats(-5, 5), max_size=15))
@settings(max_examples=200, deadline=None)
def test_absorb_never_raises_on_arbitrary_untrusted_input(payload) -> None:
    """Zero-trust ingress: any peer payload is survivable (A6 lesson)."""
    field = ScentField(board_size=BOARD)
    problems = field.absorb(payload)
    assert isinstance(problems, list)
    assert all(0.0 < value <= field.ceiling for value in field.snapshot().values())


@given(deposits=st.lists(cells, min_size=1, max_size=5))
@settings(max_examples=100, deadline=None)
def test_book_deposit_is_readable_for_several_turns(deposits) -> None:
    """Book PAGE 45: a fresh deposit stays informative for roughly 6-7 turns."""
    field = ScentField(board_size=BOARD, model=ScentModel.BOOK)
    for centre in deposits:
        field.deposit(centre)
    for _ in range(6):
        field.decay_all()
    assert field.strongest_cell() is not None
