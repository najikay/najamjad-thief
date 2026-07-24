"""Unit tests for the version module (guidelines §8.1)."""

import najamjad_agent
from najamjad_agent.shared.version import CODE_VERSION


def test_version_starts_at_1_00() -> None:
    """Guidelines Table 2: initial code version is exactly '1.00'."""
    assert CODE_VERSION == "1.00"


def test_package_dunder_version_reexports_code_version() -> None:
    assert najamjad_agent.__version__ == CODE_VERSION


def test_version_is_two_decimal_string() -> None:
    """Format guard: '<major>.<two digits>' so config compatibility checks parse it."""
    major, minor = CODE_VERSION.split(".")
    assert major.isdigit() and minor.isdigit() and len(minor) == 2
