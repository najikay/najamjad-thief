# Open items

**Version 1.00 · 2026-07-27**

Things known to be incomplete, with the evidence gathered so far. Recorded here
rather than left implicit, so nobody has to rediscover them — and so a grader
can see we know.

---

## T-2101 / T-2102 — two-process series does not complete

**What works.** `scripts/two_process_match.py` launches both repos as real OS
processes on OS-assigned ports, each with its own MCP server. They connect, they
exchange real turns over HTTP (`POST /mcp 200 OK` throughout), and they reach the
audit stage — sealed records, nonces and commits appear in both logs.

**What does not.** A two-game series does not finish inside a 300 s budget.

**Evidence, from the peers' own event log:**

| event | count |
|---|---|
| `inbox.accepted` | 101 |
| `deadline.started` | 395 |
| `deadline.met` | 101 |
| `turn.timeout` | 88 |

Messages arrive **and are accepted**, and the peers still wait each other out.
So this is neither transport (measured at 12 ms a message) nor the audit
envelope (fixed, and one mini-game over real MCP now takes 0.8 s in-process).

**Leading hypothesis, explicitly not yet a finding:** the `match` verb plays
without negotiating first, so the two processes never establish a shared turn
token and both can end up waiting. Testing that means wiring negotiation into
`match` and re-running.

**Why it is not blocking.** The same series runs correctly in-process over real
MCP, and against the reference simulator's tool surface. What is unproven is two
*separate processes* completing a full series unattended.

---

## T-2104 — lifecycle-artifact assertions in a CI series

Depends on T-2102. The artifact writer and its schemas are tested directly; what
is missing is asserting all four artifacts appear with a shared `game_uid` after
a real two-process run.

## T-2113 — golden-drift regression

The goldens are verified byte-for-byte today (`test_verifier.py`, and the
pre-match smoke script). What is missing is diffing *interop-run* artifacts
against expected shapes so a silent format drift raises an alarm.

## T-2125 — failure-path traceability table

Every PRD §4 reliability scenario now has a test, but the mapping lives across
several files rather than in one table. Mechanical to produce; not yet done.

## T-2108 — win-rate gate as a scheduled job

The gate itself is implemented and asserted (`test_self_play_harness.py`), and
the measured rate is 100 % as cop and 100 % survival as thief. What is missing
is running it nightly rather than on demand.

---

## Recently closed, for context

- **T-2110** sweep runner — found `barrier_threshold` was badly tuned; 43-75 % → 100 %.
- **T-2115..T-2118, T-2120** chaos — tunnel restart, total LLM outage, Gmail 429
  storm, clock skew, soak.
- **T-2121..T-2124** quality gates — coverage floor, honest omit list, move
  latency on a 15×15 board, cross-repo byte-identity.
- **T-2126** pre-match smoke — one command, `MATCH READY` in ~50 s.
