# ADR-012 — Golden-file interop tests against the reference simulator

**Status:** accepted

The simulator's artifacts and sample-run outputs are checked into `tests/goldens/`. CI
validates our schemas parse them and our artifacts round-trip to the same shapes. A weekly
(and pre-match) smoke: full series vs the unmodified reference simulator over localhost — our
definitive interop regression (A6 pain #6).

---

Extracted from `docs/PLAN.md`. See [the ADR index](README.md).
