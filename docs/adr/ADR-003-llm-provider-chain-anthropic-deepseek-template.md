# ADR-003 — LLM provider chain Anthropic → DeepSeek → template

**Status:** accepted

User requirement. Anthropic for best negotiation/bluff quality; DeepSeek (OpenAI-compatible,
cheap, stable) for testing and as fallback; template bank as terminal 0-token floor (book
default). Health-based degradation and recovery; **active provider always visible** (log
event + UI badge + per-message provenance). LLM never selects moves (book rule 25).

---

Extracted from `docs/PLAN.md`. See [the ADR index](README.md).
