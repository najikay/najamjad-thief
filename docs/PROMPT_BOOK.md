# Prompt book

**Version 1.00 · 2026-07-26 · guidelines §8.3**

How this project was actually built with an AI assistant: what was asked, what
came back, what had to be corrected, and what we would do differently. Kept
honest — the failures are the useful part.

Entries are appended per milestone. Where a prompt is quoted it is the real one.

---

## M0 — Framing the work

**Goal:** turn a book, a guidelines document and a reference repo into a plan we
could execute.

**Prompt shape:** *"go over everything and if we're missing info or something let
me know"* — plus the hard constraints up front: 120/150 line files, ruff clean,
90 %+ coverage, docs-first with a 500-800 task todo list, and a self-review pass
before any code.

**What worked:** demanding the *research digests first* (`docs/research/`).
Digesting the book, the guidelines and the reference simulator into separate
documents meant every later decision could cite a source instead of a memory.

**What we corrected:** the first plan under-specified the *mechanisms*. We added
a per-mechanism PRD template so belief, commit-reveal, negotiation, routing,
strategy, gatekeeper and reporting each got their own design document rather
than a paragraph inside one big plan.

**Lesson:** an AI will happily produce a plausible plan at any level of detail
you accept. Asking for the level *below* the one you think you need is cheap.

---

## M1-M2 — Domain and the turn loop

**Goal:** the rules, the belief engine, commit-reveal, and one mini-game
end-to-end against fakes.

**Prompt shape:** epic-by-epic, with the same closing instruction each time:
tests first, then implementation, then run every gate.

**What the assistant got wrong, and how we caught it:**

- **Scent decay had a fixed point.** Relative decay rounded to three decimals
  never reached zero. Caught by asking "what does this look like after 40 steps?"
  rather than by a test — the tests all asserted decay *direction*, not its limit.
- **Belief lagged a moving opponent by ~5 cells.** Multiplicative fusion
  double-counted the cumulative field. Caught by plotting belief against truth.
- **The lie detector was fooled by lateral spread.** An eastward trail
  "confirmed" a southward claim. Fixed by comparing against fresh-mass centroid
  displacement.

**Lesson:** for anything numeric, ask for the *behaviour over time*, not a unit
test. Every one of those passed its tests.

---

## M3 — Transport, and the first real scare

**Goal:** MCP server and client, deadlines, watchdog, inbox validation.

**The prompt that mattered:** after the transport was "done", we asked what
*"local truth only"* (book rules 8-9) implies for the **wire**, then compared our
outbound message with the reference's `TurnMessage`.

**Finding:** we were transmitting the entire sealed payload every turn —
position, move and intent. All 1,000 tests passed, because they had been written
against the same wrong assumption. The opponent would have known our exact cell
every turn, making scent, belief and bluffing decorative.

**Lesson, and the single most valuable prompt pattern in this project:** *"what
would this look like to the other side?"* Applied to the wire, the dashboard, the
audit and the report, it found something every time.

---

## M4-M5 — UI, replay, SDK, and interop

**Goal:** dashboard, replay viewer, CLI, and playing a real opponent.

**What worked:** asking for *meta-tests* — tests that read the source tree and
enforce architecture. "The UI may import only the SDK" and "the CLI holds no
business logic" are now machine-checked, not aspirational.

**What we corrected repeatedly:** the assistant's instinct to trust its own
fakes. Three defects survived a green suite because the doubles were kinder than
reality (see ADR-017). The correction that finally worked was procedural: clone
the reference simulator, run it, and point it at us.

**Findings from that one session:** the MCP argument-name mismatch (nothing
worked in either direction), four turn-message incompatibilities, and an audit
reveal rejected on the wire. All invisible to 1,500 passing tests.

**Lesson:** ask the assistant to test against something it did not write. It will
not suggest this on its own.

---

## What we would tell the next team

1. **Make the AI write the digest before the plan.** Sourced decisions survive
   review; remembered ones do not.
2. **Ask for the failure mode, not the feature.** "What happens when the opponent
   goes silent?" produced better code than "handle timeouts".
3. **Never accept "all tests pass" as evidence of interop.** It means your code
   agrees with your assumptions.
4. **Demand the measurement.** Every performance claim in this repo has a number
   next to it because we asked for one; the first three guesses at a bottleneck
   were all wrong.
5. **Keep the commit messages honest.** Ours record what broke and why, including
   the times the assistant reported a gate as passing when it had not looked. That
   history is what made later work trustworthy.
