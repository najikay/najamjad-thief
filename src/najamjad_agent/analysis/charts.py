"""Figures for the analysis notebook (T-2215, T-2216, T-2219, T-2221).

Each function returns a matplotlib `Figure` so the notebook stays four lines
long and the drawing itself can be tested. Two conventions are deliberate:

* **Confidence intervals are always drawn.** Every rate here comes from a few
  dozen games. A bare bar at 0.96 invites a reader to believe three digits we
  did not measure; the interval shows what the sample can actually support.
* **Never colour alone.** Markers and hatching carry the same distinction, so
  the charts survive greyscale printing and colour-blind readers (`docs/UX.md`).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # a notebook renders to file, never to a window
import matplotlib.pyplot as plt  # noqa: E402

from .datasets import Point, Sweep  # noqa: E402

OURS = "#1f4e79"
BASELINE = "#a03030"


def sensitivity(sweep: Sweep, default: float | None = None, ax=None):
    """One knob's capture rate against its value, with 95 % Wilson bars."""
    own_figure = ax is None
    if own_figure:
        _, ax = plt.subplots(figsize=(5.2, 3.4))
    values = [point.value for point in sweep.points]
    rates = [point.rate for point in sweep.points]
    lower = [point.error[0] for point in sweep.points]
    upper = [point.error[1] for point in sweep.points]

    ax.errorbar(values, rates, yerr=[lower, upper], marker="o", capsize=4,
                color=OURS, linewidth=1.8, label="capture rate")
    if default is not None:
        ax.axvline(default, linestyle="--", color="#666666", linewidth=1)
        ax.annotate("shipped default", xy=(default, 0.04), fontsize=8, color="#666666",
                    rotation=90, va="bottom", ha="right")
    if all(float(value).is_integer() for value in values):
        ax.set_xticks(values)  # a depth of 1.5 is not a setting anyone can ship
    ax.set_xlabel(sweep.knob)
    ax.set_ylabel("capture rate")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(alpha=0.25)
    ax.set_title(f"{sweep.knob} — swing {sweep.span:.0%}", fontsize=10)
    return ax.figure if own_figure else ax


def sensitivity_grid(sweeps: dict[str, Sweep], defaults: dict[str, float] | None = None):
    """Every knob side by side, so their relative importance is visible."""
    defaults = defaults or {}
    figure, axes = plt.subplots(1, len(sweeps), figsize=(5.0 * len(sweeps), 3.4))
    axes = [axes] if len(sweeps) == 1 else list(axes)
    for ax, (knob, sweep) in zip(axes, sweeps.items(), strict=True):
        sensitivity(sweep, default=defaults.get(knob), ax=ax)
    figure.tight_layout()
    return figure


def tornado(sweeps: dict[str, Sweep]):
    """Rank the knobs by how much outcome they move — the sensitivity summary.

    A tornado rather than a heatmap: the knobs share no common axis (a
    threshold in [0,1] against a depth in steps), so a grid of coloured cells
    would imply a comparison between values that does not exist. The bar length
    is the one number that *is* comparable.
    """
    ordered = sorted(sweeps.values(), key=lambda sweep: sweep.span)
    figure, ax = plt.subplots(figsize=(6.4, 0.7 * len(ordered) + 1.4))
    ax.barh([sweep.knob for sweep in ordered], [sweep.span for sweep in ordered],
            color=OURS, height=0.55)
    for index, sweep in enumerate(ordered):
        ax.text(sweep.span + 0.015, index, f"{sweep.span:.0%}", va="center", fontsize=9)
    ax.set_xlabel("swing in capture rate across the swept range")
    ax.set_xlim(0, max(sweep.span for sweep in ordered) * 1.22)
    ax.grid(axis="x", alpha=0.25)
    ax.set_title("Which knob actually decides the game", fontsize=11)
    figure.tight_layout()
    return figure


def comparison(baselines: dict[str, Point], labels: dict[str, str] | None = None):
    """Our brains against the greedy reference, with intervals (T-2219)."""
    labels = labels or {}
    names = list(baselines)
    rates = [baselines[name].rate for name in names]
    errors = [[baselines[name].error[side] for name in names] for side in (0, 1)]
    colours = [BASELINE if name.startswith("greedy") else OURS for name in names]
    hatches = ["//" if name.startswith("greedy") else "" for name in names]

    figure, ax = plt.subplots(figsize=(7.6, 4.2))
    bars = ax.bar(range(len(names)), rates, yerr=errors, capsize=5, color=colours, width=0.55)
    for bar, hatch in zip(bars, hatches, strict=True):
        bar.set_hatch(hatch)
    for index, name in enumerate(names):
        point = baselines[name]
        # Both labels clear the interval's upper whisker, or they are drawn
        # through it — worst of all on the 0 % bar, where the whisker is the
        # only mark on the axis.
        top = point.rate + point.error[1]
        ax.text(index, top + 0.09, f"{point.successes}/{point.played} = {point.rate:.0%}",
                ha="center", fontsize=9)
        if point.rate == 0.0:
            # A zero bar draws nothing; without this the strongest thief result
            # in the project looks like a missing measurement.
            ax.text(index, top + 0.015, "never captured", ha="center", fontsize=8,
                    style="italic", color=OURS)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([labels.get(name, name.replace("_", " ")) for name in names], fontsize=8)
    ax.set_ylabel("cop capture rate\n(the cop's success, whichever side is ours)")
    ax.set_ylim(0, 1.22)
    ax.grid(axis="y", alpha=0.25)
    ax.set_title("Our brains vs the greedy baseline (95 % Wilson intervals)", fontsize=11)
    figure.tight_layout()
    return figure


def cost_curve(measurements: list[dict], budget: int):
    """Tokens per series against hint cadence, with the agreed cap for scale."""
    cadences = [row["every_n_steps"] for row in measurements]
    totals = [row["total_tokens"] for row in measurements]

    figure, ax = plt.subplots(figsize=(6.0, 3.6))
    ax.plot(cadences, totals, marker="s", color=OURS, linewidth=1.8, label="measured usage")
    ax.axhline(budget, linestyle=":", color=BASELINE, label=f"agreed cap ({budget:,})")
    for cadence, total in zip(cadences, totals, strict=True):
        ax.annotate(f"{total:,}", xy=(cadence, total), xytext=(0, 7),
                    textcoords="offset points", ha="center", fontsize=8)
    ax.set_xlabel("every_n_steps (hint cadence)")
    ax.set_ylabel("tokens per 6-game series")
    ax.set_xticks(cadences)
    ax.set_yscale("log")
    ax.grid(alpha=0.25, which="both")
    ax.legend(fontsize=8)
    ax.set_title("Cost is never the binding constraint", fontsize=11)
    figure.tight_layout()
    return figure
