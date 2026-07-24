"""Shared pytest fixtures for the NajAmjad agent test suite.

Fixtures accumulate here as modules land (guidelines §6.1 rule 4); external
dependencies (network, LLM providers, Gmail) are always mocked — tests never
touch external services (guidelines §6.1 rule 7).
"""
