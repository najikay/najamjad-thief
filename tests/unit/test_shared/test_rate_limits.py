"""Tests for rate-limit configuration loading and Appendix F enforcement."""

import json
from pathlib import Path

import pytest

from najamjad_agent.shared.rate_limits import (
    RateLimitConfig,
    for_service,
    load_rate_limits,
)

REPO_CONFIG = Path(__file__).resolve().parents[3] / "config/rate_limits.json"


def _write(tmp_path: Path, services: dict, version: str = "1.00") -> Path:
    path = tmp_path / "rate_limits.json"
    path.write_text(
        json.dumps({"rate_limits": {"version": version, "services": services}}), encoding="utf-8"
    )
    return path


VALID = {
    "requests_per_minute": 30,
    "requests_per_hour": 500,
    "concurrent_max": 2,
    "retry_after_seconds": 5,
    "max_retries": 3,
    "queue_depth": 100,
}


def test_the_repository_config_loads_and_is_valid() -> None:
    """The shipped config must satisfy its own rules (guidelines §5.2)."""
    services = load_rate_limits(REPO_CONFIG)
    assert "default" in services
    assert "gmail" in services
    assert services["gmail"].requests_per_minute >= 30


def test_defaults_match_appendix_f_table_19() -> None:
    config = RateLimitConfig()
    assert config.requests_per_minute == 30
    assert config.concurrent_max == 2
    assert config.retry_after_seconds == 5
    assert config.max_retries == 3
    assert config.queue_depth == 100


def test_unsupported_version_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, {"default": VALID}, version="9.99")
    with pytest.raises(ValueError, match="not supported"):
        load_rate_limits(path)


def test_missing_default_service_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, {"gmail": VALID})
    with pytest.raises(ValueError, match="'default' service"):
        load_rate_limits(path)


def test_too_short_backoff_is_refused(tmp_path: Path) -> None:
    """Blind fast retries against Google get the account suspended (PAGE 95)."""
    path = _write(tmp_path, {"default": {**VALID, "retry_after_seconds": 1}})
    with pytest.raises(ValueError, match="below the Appendix F minimum"):
        load_rate_limits(path)


def test_too_much_concurrency_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, {"default": {**VALID, "concurrent_max": 8}})
    with pytest.raises(ValueError, match="exceeds the Appendix F ceiling"):
        load_rate_limits(path)


def test_shallow_queue_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, {"default": {**VALID, "queue_depth": 10}})
    with pytest.raises(ValueError, match="queue_depth"):
        load_rate_limits(path)


def test_non_positive_rate_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, {"default": {**VALID, "requests_per_minute": 0}})
    with pytest.raises(ValueError, match="must be positive"):
        load_rate_limits(path)


def test_unknown_service_falls_back_to_default(tmp_path: Path) -> None:
    services = load_rate_limits(_write(tmp_path, {"default": VALID}))
    assert for_service(services, "not-configured") is services["default"]


def test_known_service_uses_its_own_limits() -> None:
    services = load_rate_limits(REPO_CONFIG)
    assert for_service(services, "mcp_peer") is services["mcp_peer"]
