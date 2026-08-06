"""Tests for breeding strategies: the rules, and the honesty of the result.

The selection rule is the user's, implemented literally — winner stays, loser
mutates, repeated loser is redrawn. The tests that matter most are the ones
about *not fooling ourselves*: the incumbent must compete, the run must replay
from its seed, and a saturated fitness landscape must be reported as saturated
rather than dressed up as a discovery.
"""

import random

from najamjad_agent.strategy import genome as genes
from najamjad_agent.strategy import tournament
from najamjad_agent.strategy.genome import BOUNDS, Genome


def constant_arena(score: int):
    """An arena that pays every genome the same, to isolate selection logic."""
    return lambda _genome: score


def horizon_arena():
    """An arena that rewards a larger `horizon`, so there is a gradient to find."""
    return lambda genome: int(genome.horizon * 10)


def test_the_shipped_configuration_is_always_in_the_population() -> None:
    """Otherwise "we found something better" is a claim about nothing."""
    _, results = tournament.run([horizon_arena()], rounds=1, size=4, seed=1)

    assert genes.shipped().name in results[0].scores


def test_the_winner_survives_unchanged() -> None:
    """"The winner stays" has to mean untouched, or a champion is bred away."""
    champion = tournament.Contender(Genome(horizon=5.0))
    loser = tournament.Contender(Genome(horizon=1.0))
    before = champion.genome

    tournament.run_round([champion, loser], [horizon_arena()], random.Random(1), 1)

    assert champion.genome == before


def test_a_loser_is_mutated_rather_than_left_alone() -> None:
    champion = tournament.Contender(Genome(horizon=5.0))
    loser = tournament.Contender(Genome(horizon=1.0))
    before = loser.genome

    tournament.run_round([champion, loser], [horizon_arena()], random.Random(1), 1)

    assert loser.genome != before


def test_repeated_losses_redraw_the_lineage_instead_of_nudging_it() -> None:
    """Repeated losses say the neighbourhood is wrong, not the step size."""
    champion = tournament.Contender(Genome(horizon=5.0))
    loser = tournament.Contender(Genome(horizon=1.0))
    rng = random.Random(1)

    for number in range(tournament.PATIENCE + 1):
        tournament.run_round([champion, loser], [horizon_arena()], rng, number)

    assert loser.losses == 0, "the lineage should have been redrawn and its count reset"


def test_a_whole_run_replays_exactly_from_its_seed() -> None:
    """Rule 49: a grader can re-run this, so it must give the same answer."""
    first, _ = tournament.run([horizon_arena()], rounds=5, size=5, seed=99)
    second, _ = tournament.run([horizon_arena()], rounds=5, size=5, seed=99)

    assert first == second


def test_a_different_seed_explores_differently() -> None:
    """A search that ignores its seed is not searching."""
    runs = {tournament.run([horizon_arena()], rounds=4, size=5, seed=s)[0] for s in range(6)}

    assert len(runs) > 1


def test_a_gradient_is_actually_climbed() -> None:
    """The instrument must be able to find something, or it measures nothing."""
    best, _ = tournament.run([horizon_arena()], rounds=15, size=8, seed=3)

    assert best.horizon > genes.shipped().horizon


def test_a_saturated_landscape_reports_no_improvement() -> None:
    """The result the real arenas actually produce, and it must not be dressed up.

    Every arena pays the same, so nothing can beat the incumbent. `beats_incumbent`
    has to say so — a search that always claims a winner is a random genome
    generator with a ceremony attached.
    """
    arenas = [constant_arena(35)]
    _, results = tournament.run(arenas, rounds=5, size=5, seed=2)

    assert tournament.beats_incumbent(results, arenas) is False


def test_ties_do_not_depend_on_population_order() -> None:
    """Otherwise a rerun with the list built differently gives another answer."""
    arenas = [constant_arena(35)]
    forward = [tournament.Contender(Genome(horizon=h)) for h in (1.0, 3.0, 5.0)]
    backward = list(reversed([tournament.Contender(Genome(horizon=h)) for h in (1.0, 3.0, 5.0)]))

    first = tournament.run_round(forward, arenas, random.Random(1), 1)
    second = tournament.run_round(backward, arenas, random.Random(1), 1)

    assert first.champion == second.champion


def test_mutation_stays_inside_the_declared_bounds() -> None:
    """A dial outside its range is not a strategy, it is a crash waiting."""
    rng = random.Random(5)
    current = genes.shipped()

    for _ in range(200):
        current = genes.mutate(current, rng)
        for field, (low, high) in BOUNDS.items():
            assert low <= getattr(current, field) <= high, f"{field} escaped its bounds"


def test_turn_counting_dials_stay_whole_numbers() -> None:
    """`horizon` and `stall_trigger` count turns; 3.4 turns is not a thing."""
    rng = random.Random(11)
    mutated = genes.mutate(genes.shipped(), rng)

    assert mutated.horizon == int(mutated.horizon)
    assert mutated.stall_trigger == int(mutated.stall_trigger)


def test_a_random_genome_is_also_inside_the_bounds() -> None:
    drawn = genes.random_genome(random.Random(4))

    for field, (low, high) in BOUNDS.items():
        assert low <= getattr(drawn, field) <= high


def test_a_genome_name_is_stable_and_distinguishing() -> None:
    """The results table has to be readable and re-runnable."""
    assert Genome(horizon=3.0).name == Genome(horizon=3.0).name
    assert Genome(horizon=3.0).name != Genome(horizon=4.0).name


def test_the_brain_only_receives_dials_it_accepts() -> None:
    """A key the brain does not take kills a live match at the first mini-game."""
    from dataclasses import fields

    from najamjad_agent.strategy.thief_brain import ThiefBrain

    accepted = {each.name for each in fields(ThiefBrain)}

    assert set(genes.shipped().as_brain_kwargs()) <= accepted
