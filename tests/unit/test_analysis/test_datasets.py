"""The notebook's loaders (T-2214).

A chart is only as trustworthy as the reader beneath it, and the failure mode
that matters is the quiet one: a truncated or hand-edited results file that
still parses and produces a plausible-looking figure. These tests are mostly
about making that impossible.
"""

import json

import pytest

from najamjad_agent.analysis.datasets import (
    MissingDataError,
    Point,
    Sweep,
    load_baselines,
    load_sweeps,
    load_tokens,
)

SWEEP_FILE = {
    "sweeps": {
        "cop.barrier_threshold": {
            "why": "when to spend a barrier",
            "points": [
                {"value": 0.4, "played": 24, "captures": 24, "capture_rate": 1.0,
                 "capture_rate_ci95": [0.86, 1.0]},
                {"value": 0.05, "played": 24, "captures": 1, "capture_rate": 0.0417,
                 "capture_rate_ci95": [0.007, 0.2]},
            ],
        }
    }
}


@pytest.fixture
def sweep_path(tmp_path):
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(SWEEP_FILE), encoding="utf-8")
    return path


def test_points_are_sorted_by_value_not_by_the_order_they_were_run(sweep_path):
    """The sweep runs the shipped value first; a line chart needs them in order."""
    sweep = load_sweeps(sweep_path)["cop.barrier_threshold"]

    assert [point.value for point in sweep.points] == [0.05, 0.4]


def test_the_best_point_and_the_swing_are_computed_from_the_data(sweep_path):
    sweep = load_sweeps(sweep_path)["cop.barrier_threshold"]

    assert sweep.best.value == 0.4
    assert sweep.span == pytest.approx(1.0 - 0.0417)


def test_error_bars_are_lengths_from_the_point_not_absolute_bounds():
    """matplotlib wants distances; handing it the bounds silently mis-draws."""
    point = Point(value=0.4, played=24, successes=16, rate=0.667, ci=(0.47, 0.82))

    low, high = point.error

    assert low == pytest.approx(0.197)
    assert high == pytest.approx(0.153)


def test_an_interval_that_does_not_bracket_the_rate_cannot_make_a_negative_bar():
    """Rounding in the writer can put the rate a hair outside its own interval."""
    point = Point(value=1, played=10, successes=10, rate=1.0, ci=(0.72, 0.999))

    assert point.error == (pytest.approx(0.28), 0.0)


def test_a_missing_file_names_the_script_that_makes_it(tmp_path):
    """The notebook is read by someone who did not build the pipeline."""
    with pytest.raises(MissingDataError, match="measure_tokens.py"):
        load_tokens(tmp_path / "nope.json")

    with pytest.raises(MissingDataError, match="sweep.py"):
        load_sweeps(tmp_path / "nope.json")


def test_baselines_load_with_their_intervals(tmp_path):
    path = tmp_path / "baselines.json"
    path.write_text(json.dumps({"matchups": {
        "ours_cop_vs_greedy_thief": {"played": 60, "captures": 60, "capture_rate": 1.0,
                                     "capture_rate_ci95": [0.9398, 1.0]},
    }}), encoding="utf-8")

    point = load_baselines(path)["ours_cop_vs_greedy_thief"]

    assert (point.played, point.rate) == (60, 1.0)
    assert point.ci == (0.9398, 1.0)


def test_the_real_results_files_load():
    """The files committed in `results/` are the ones the notebook plots."""
    sweeps = load_sweeps()
    baselines = load_baselines()
    tokens = load_tokens()

    assert sweeps and all(isinstance(sweep, Sweep) for sweep in sweeps.values())
    assert baselines["ours_cop_vs_greedy_thief"].played > 0
    assert tokens["measurements"], "the census must contain at least one cadence"


def test_a_point_with_no_interval_draws_no_bar_rather_than_a_full_height_one(tmp_path):
    """Older sweep files predate the CI column.

    The tempting fallback is `(0.0, 0.0)`, which is not "no interval" — against
    a rate of 1.0 it renders a whisker running the entire height of the axis,
    inventing a huge uncertainty for a measurement that recorded none. Absent
    and zero-width have to stay distinguishable.
    """
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"sweeps": {"k": {"why": "", "points": [
        {"value": 1, "played": 5, "captures": 5, "capture_rate": 1.0}]}}}), encoding="utf-8")

    point = load_sweeps(path)["k"].points[0]

    assert point.ci is None
    assert point.error == (0.0, 0.0)
