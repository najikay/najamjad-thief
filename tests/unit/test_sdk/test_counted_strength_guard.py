"""A counted match must refuse to start at less than full strength.

`shared/strength.guard_counted` was written, documented, unit-tested — and had
**zero callers anywhere in `src/` or `scripts/`**, so the refusal never ran.
Meanwhile `scripts/match_day.py warmup` writes `level = "sandbagged"` into a
config file nothing read. The dangerous direction is not choosing wrongly, it is
arming a warm-up and forgetting to re-arm before the counted series, and a
counted match cannot be replayed.
"""

from pathlib import Path

import pytest

from najamjad_agent.shared.strength import StrengthError, guard_counted


def test_a_counted_match_refuses_a_sandbagged_agent() -> None:
    with pytest.raises(StrengthError, match="must be played at 'full'"):
        guard_counted("sandbagged", counted=True)


def test_a_counted_match_accepts_full_strength() -> None:
    assert guard_counted("full", counted=True) == "full"


def test_a_practice_run_may_be_sandbagged() -> None:
    """The whole point of the level; warm-ups are uncounted by the book's design."""
    assert guard_counted("sandbagged", counted=False) == "sandbagged"


def test_the_guard_is_actually_wired_into_agent_construction() -> None:
    """The defect was never the logic — it was that nothing called it.

    Asserted against the source of the one place every entry point passes
    through, because a guard reachable only from a test guards nothing. This
    repo has found 20+ finished-but-unreferenced components; this is how one
    stops being another.
    """
    source = Path("src/najamjad_agent/sdk/bootstrap.py").read_text(encoding="utf-8")

    assert "_guard_counted_strength(manager)" in source
    assert "guard_counted" in source
