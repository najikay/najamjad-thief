"""SDK facade — the single business-logic entry point for UI, CLI, and integrations (guidelines §4.1)."""

from .sdk import AgentSdk

__all__ = ["AgentSdk"]
