# ADR-016 — Conservative in what we send, liberal in what we accept

**Status:** accepted (build-time, E21)

**Context:** We cloned the course reference simulator and pointed it at us.
Nothing worked, in either direction. It names the MCP tool argument `message` on
three tools and `payload` on one; we sent `payload` to all four and accepted only
`payload`, so every turn and proposal was rejected by *argument binding* before
any game logic ran — against any agent built on the reference, which is most of
the class. Four more incompatibilities followed in the turn message, and the
audit reveal was sent as a bare list where the schema declares an envelope.

**Decision:** send exactly what the reference declares, accept either
convention.

- The client sends the argument name the reference expects, per tool.
- Our server accepts `message` or `payload` on all four tools, and answers a
  call with neither with a structured refusal rather than a stack trace.
- Our wire vocabulary is a **subset** of the fields the reference declares —
  its parser rejects unknown keys outright, so one extra field makes every
  message unreadable.
- Claim fields carry the reference's richer shapes, and our readers accept both
  those and our earlier simpler ones.

**Trade-off:** slightly more permissive parsing than a single-implementation
protocol would need. That is the correct trade in a league where the other
implementations are strangers' code.

**Consequence for testing:** contract tests transcribe the reference's field
list rather than importing it, so they run in CI where the simulator is absent.
