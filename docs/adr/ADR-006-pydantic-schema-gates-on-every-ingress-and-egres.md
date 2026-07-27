# ADR-006 — pydantic schema gates on every ingress AND egress

**Status:** accepted

All wire messages, lifecycle artifacts, and the result email are validated against strict
models (required booleans non-nullable) — egress failure blocks the send and alerts the
operator. Ingress is tolerant: unknown fields logged and ignored; malformed input → structured
error, never a crash. Directly kills A6 pains #5/#6.

---

Extracted from `docs/PLAN.md`. See [the ADR index](README.md).
