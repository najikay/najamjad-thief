# Mechanism PRD — API gatekeeper

**Version 1.00 · 2026-07-26 · ADR-009**

## Problem

Three external services sit behind this agent — Anthropic, DeepSeek, Gmail — and
one peer. Each has a quota, a temper, and a way of punishing a client that
hammers it. Assignment 6 had no limiter at all: a retry loop against a failing
provider produced a burst that looked, from the far end, indistinguishable from
abuse.

The gatekeeper exists to make us a good citizen towards services we do not own,
and to make retry policy a *configuration* rather than something each caller
reinvents slightly differently.

## Contract

```python
gatekeeper.execute(callable, *args, **kwargs) -> result
```

One method. The caller does not know it is rate-limited; it hands over a call and
gets a result or an exception. That is deliberate — a caller that can see the
limiter will eventually work around it.

| Input | Meaning |
|---|---|
| `service` | Which config block applies (`anthropic`, `gmail`, `mcp_peer`, `default`) |
| `config` | `RateLimitConfig` — validated against Appendix F ceilings at load |
| `emit` | Event hook, so queueing and backpressure are visible on the dashboard |

## Design

**Token bucket** for the rate, refilled continuously rather than in windows: a
window boundary lets a caller fire a full quota twice in two seconds and still
claim compliance.

**Bounded concurrency** (`concurrent_max`, ceiling 2 per Appendix F) so a burst
cannot open more sockets than the service expects.

**FIFO queue** with a depth limit. Beyond it, `QueueFullError` — refusing work is
honest; queueing without bound just moves the failure somewhere harder to see.

**Bounded retries** with `retry_after_seconds` (floor 5 per Appendix F), and —
critically — retries only what is *transient*. `classify_error` walks the
`__cause__` chain, because a bad API key wrapped in a provider exception looked
transient and burned three retries plus a cooldown on a problem no amount of
waiting fixes.

## What it must NOT do

Rate-limit the opponent as though they were a metered API. We did exactly that by
accident — `build_transport` asked for service `"peer"` while the config declared
`"mcp_peer"`, so peer traffic fell through to `default`: one message every two
seconds. The danger is not slowness. **Our own limiter could delay a reply past
the opponent's 30-second deadline and forfeit a game we were winning.**

`mcp_peer` is now rated so it never shapes a legitimate match, while staying
inside the Appendix F ceilings for concurrency and retry delay.

## Metrics

`status()` reports `waiting`, `in_flight`, `calls_made` per service — rendered
live in the dashboard's gatekeeper panel, so backpressure is visible before it
becomes a timeout.

## Alternatives considered

| Option | Why not |
|---|---|
| No limiter (A6) | Retry storms; the failure mode we are here to prevent. |
| Per-call `sleep` | Unmeasurable, untestable, and wrong under concurrency. |
| Library (`ratelimit`, `tenacity`) | Neither validates against Appendix F ceilings, and the book's limits are the actual requirement. |
| One global limiter | A slow Gmail send would throttle LLM calls that share nothing with it. |

## Test scenarios

| Scenario | Expectation | Test |
|---|---|---|
| Burst above the rate | Queued, not dropped | `test_gatekeeper.py` |
| Queue depth exceeded | `QueueFullError`, backpressure event | `test_gatekeeper.py` |
| Transient failure | Retried within `max_retries` | `test_gatekeeper.py` |
| Permanent failure (bad key) | Fails fast, no retry burn | `test_provider_lifecycle.py` |
| Config outside Appendix F | Rejected at load | `test_rate_limits.py` |
| Peer service | Never throttles a legitimate match | `test_match_setup` / measured |
