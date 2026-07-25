"""Rate-limit configuration, loaded from file — never hardcoded.

Guidelines §5.2 require limits to come from `config/rate_limits.json`, and
Appendix F Table 19 sets the binding minimums. Values below those minimums are
refused at load time: a too-permissive limiter is how an account gets
suspended mid-league (book PAGE 95).
"""

import json
from dataclasses import dataclass
from pathlib import Path

# Appendix F Table 19 minimums — a config may be stricter, never looser.
MIN_RETRY_BACKOFF_SEC = 5
MAX_CONCURRENT_ALLOWED = 2
MIN_QUEUE_DEPTH = 100
SUPPORTED_VERSIONS = ("1.00",)


@dataclass(frozen=True)
class RateLimitConfig:
    """Limits for one external service."""

    requests_per_minute: int = 30
    requests_per_hour: int = 500
    concurrent_max: int = 2
    retry_after_seconds: int = 5
    max_retries: int = 3
    queue_depth: int = 100

    def validate(self, service: str) -> None:
        """Reject a configuration that would breach the binding minimums."""
        if self.requests_per_minute < 1:
            raise ValueError(f"{service}: requests_per_minute must be positive")
        if self.concurrent_max > MAX_CONCURRENT_ALLOWED:
            raise ValueError(
                f"{service}: concurrent_max {self.concurrent_max} exceeds the "
                f"Appendix F ceiling of {MAX_CONCURRENT_ALLOWED}"
            )
        if self.retry_after_seconds < MIN_RETRY_BACKOFF_SEC:
            raise ValueError(
                f"{service}: retry_after_seconds {self.retry_after_seconds} is below the "
                f"Appendix F minimum of {MIN_RETRY_BACKOFF_SEC}"
            )
        if self.queue_depth < MIN_QUEUE_DEPTH:
            raise ValueError(f"{service}: queue_depth must be at least {MIN_QUEUE_DEPTH}")


def load_rate_limits(path: Path) -> dict[str, RateLimitConfig]:
    """Load every service's limits, validating the file version and values."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    section = raw.get("rate_limits", {})
    version = str(section.get("version", ""))
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"rate_limits version {version!r} is not supported {SUPPORTED_VERSIONS}")
    services: dict[str, RateLimitConfig] = {}
    for name, values in section.get("services", {}).items():
        config = RateLimitConfig(**values)
        config.validate(name)
        services[name] = config
    if "default" not in services:
        raise ValueError("rate_limits must define a 'default' service")
    return services


def for_service(services: dict[str, RateLimitConfig], name: str) -> RateLimitConfig:
    """Limits for `name`, falling back to the mandatory default entry."""
    return services.get(name, services["default"])
