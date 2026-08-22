"""The strength guard, after the collapse to one mode (2026-08-22).

The original defect was never the logic — it was that nothing called it, the
project's recurring finished-but-unwired shape. That wiring assertion is the
part still worth pinning: a guard reachable only from a test guards nothing,
and it is now the place a *typo* in `strength.level` surfaces before a
counted match rather than during one. The refusal tests it used to carry are
gone with the levels themselves — every recognised spelling now resolves to
full, which `test_shared/test_strength.py` pins.
"""

from pathlib import Path

import pytest

from najamjad_agent.shared.strength import StrengthError, guard_counted


def test_a_counted_match_accepts_full_strength() -> None:
    assert guard_counted("full", counted=True) == "full"


def test_a_stale_config_cannot_stop_a_counted_match() -> None:
    """Legacy spellings resolve instead of raising — match day is not the
    moment to crash over a word that no longer changes anything."""
    assert guard_counted("sandbagged", counted=True) == "full"
    assert guard_counted("practice", counted=True) == "full"


def test_a_typo_still_refuses_before_the_match() -> None:
    with pytest.raises(StrengthError, match="not one of"):
        guard_counted("ful", counted=True)


def test_the_guard_is_actually_wired_into_agent_construction() -> None:
    """Asserted against the source of the one place every entry point passes
    through. This repo has found 20+ finished-but-unreferenced components;
    this is how one stops being another."""
    root = Path("src/najamjad_agent/sdk")
    bootstrap = (root / "bootstrap.py").read_text(encoding="utf-8")
    overrides = (root / "config_overrides.py").read_text(encoding="utf-8")

    assert "guard_counted_strength(manager)" in bootstrap
    assert "def guard_counted_strength" in overrides
    assert "guard_counted(" in overrides
