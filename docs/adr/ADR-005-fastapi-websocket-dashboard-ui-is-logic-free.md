# ADR-005 — FastAPI + WebSocket dashboard; UI is logic-free

**Status:** accepted

Push-based updates from the event bus (no polling — A6 clunkiness), single-page dashboard;
strictly local-truth rendering (book rules 8–9); all data via SDK queries. Replay viewer as a
second page over the same stack; screenshots for README come from these two pages.

---

Extracted from `docs/PLAN.md`. See [the ADR index](README.md).
