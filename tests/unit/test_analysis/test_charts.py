"""The notebook's figures (T-2215, T-2216, T-2219, T-2221).

A chart cannot be asserted to be *readable*, so these tests guard the two things
that can be checked mechanically and that silently produce a wrong picture: that
every measured point is actually drawn, and that the intervals are drawn as
distances from the point rather than as absolute bounds — the second mistake
renders a plausible chart with the wrong error bars.
"""

import matplotlib
import pytest

matplotlib.use("Agg")

from najamjad_agent.analysis import charts  # noqa: E402
from najamjad_agent.analysis.datasets import Point, Sweep  # noqa: E402

SWEEP = Sweep(
    knob="cop.barrier_threshold",
    why="when to spend a barrier",
    points=(
        Point(value=0.05, played=24, successes=1, rate=0.0417, ci=(0.007, 0.202)),
        Point(value=0.40, played=24, successes=24, rate=1.0, ci=(0.862, 1.0)),
    ),
)
DEPTH = Sweep(
    knob="cop.lookahead",
    why="diffusion depth",
    points=tuple(
        Point(value=depth, played=24, successes=24, rate=1.0, ci=(0.862, 1.0))
        for depth in (1, 2, 3, 4)
    ),
)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    matplotlib.pyplot.close("all")


def test_every_measured_point_reaches_the_line():
    figure = charts.sensitivity(SWEEP)
    line = figure.axes[0].lines[0]

    assert len(line.get_xdata()) == len(SWEEP.points)


def test_the_error_bars_are_drawn_from_the_interval_not_the_rate():
    """The whisker must reach the CI bound; drawing the bound as a length puts
    the top of a 100 % bar at 2.0."""
    figure = charts.sensitivity(SWEEP)
    segments = figure.axes[0].collections[0].get_segments()

    tops = sorted(segment[:, 1].max() for segment in segments)
    assert tops[-1] == pytest.approx(1.0), "the 100 % point's whisker must stop at 1.0"
    assert tops[0] == pytest.approx(0.202)


def test_the_shipped_default_is_marked_when_given():
    figure = charts.sensitivity(SWEEP, default=0.40)

    verticals = [line for line in figure.axes[0].lines if line.get_linestyle() == "--"]
    assert verticals, "the reader must be able to see which value we ship"


def test_integer_knobs_do_not_get_fractional_ticks():
    """A lookahead of 1.5 is not a setting anyone could ship."""
    figure = charts.sensitivity(DEPTH)

    assert list(figure.axes[0].get_xticks()) == [1.0, 2.0, 3.0, 4.0]


def test_the_grid_draws_one_panel_per_knob():
    figure = charts.sensitivity_grid({"a": SWEEP, "b": DEPTH})

    assert len(figure.axes) == 2


def test_a_single_knob_grid_does_not_crash_on_the_axes_array():
    """matplotlib returns a bare Axes for one column, not a one-element array."""
    figure = charts.sensitivity_grid({"only": SWEEP})

    assert len(figure.axes) == 1


def test_the_tornado_ranks_knobs_by_swing_with_the_biggest_on_top():
    figure = charts.tornado({"cop.barrier_threshold": SWEEP, "cop.lookahead": DEPTH})
    labels = [text.get_text() for text in figure.axes[0].get_yticklabels()]

    assert labels[-1] == "cop.barrier_threshold", "the knob that matters reads first"


def test_a_zero_rate_bar_is_still_labelled():
    """A 0 % bar draws nothing; unlabelled it reads as a missing measurement."""
    figure = charts.comparison({
        "ours_thief_vs_greedy_cop": Point(value=0, played=60, successes=0, rate=0.0,
                                          ci=(0.0, 0.06)),
    })
    texts = [text.get_text() for text in figure.axes[0].texts]

    assert "0/60 = 0%" in texts
    assert "never captured" in texts


def test_the_comparison_distinguishes_baselines_without_relying_on_colour():
    """Greyscale printing and colour-blind readers both need the hatching."""
    figure = charts.comparison({
        "ours_cop_vs_greedy_thief": Point(0, 60, 60, 1.0, (0.94, 1.0)),
        "greedy_vs_greedy": Point(0, 60, 4, 0.067, (0.026, 0.159)),
    })
    hatches = [patch.get_hatch() for patch in figure.axes[0].patches]

    assert set(hatches) == {"", "//"}


def test_the_cost_curve_shows_the_cap_the_usage_is_measured_against():
    figure = charts.cost_curve(
        [{"every_n_steps": 1, "total_tokens": 8_509},
         {"every_n_steps": 2, "total_tokens": 4_577}], budget=200_000)

    assert figure.axes[0].get_yscale() == "log", "linear hides a 40x headroom"
    assert any("200,000" in text.get_text() for text in figure.axes[0].get_legend().get_texts())


def test_the_real_data_renders_every_figure_the_notebook_shows():
    """The end-to-end guard: if `results/` and the charts drift apart, this fails."""
    from najamjad_agent.analysis.datasets import load_baselines, load_sweeps, load_tokens

    sweeps = load_sweeps()
    assert charts.tornado(sweeps).axes
    assert charts.sensitivity_grid(sweeps).axes
    assert charts.comparison(load_baselines()).axes
    census = load_tokens()
    assert charts.cost_curve(census["measurements"], census["series_token_budget"]).axes
