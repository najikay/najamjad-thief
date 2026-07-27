# ADR-014 — Static type checking beyond the guidelines

**Status:** accepted

A6 retrospective lesson 10: no type checker meant integration-seam bugs surfaced in the
field. Guidelines mandate only ruff; we additionally run `pyright` (basic mode) in CI on both
repos as a local, stricter, non-graded gate. Full type hints on all public interfaces.

---

---

Extracted from `docs/PLAN.md`. See [the ADR index](README.md).
