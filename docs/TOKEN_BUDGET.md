# Token budget — estimates, limits, and how they are enforced

**Version 1.00 · 2026-07-25**

**Priority: the grade is a league ranking, so match quality outranks token
thrift every time.** This document exists because metering is a deliverable —
the book requires reporting consumption (rule 54) and the guidelines require a
cost table (§11) — not because spend is a design constraint.

The one number that is a genuine *rule* rather than an expense is the agreed
per-series cap (~200k, negotiable). We sign that term with each opponent, so
exceeding it would be a breach. Everything below shows why it never binds.

Estimates here lean **low** deliberately: measured usage in this workload is
consistently far under the intuitive guess, because most turns need no model
call at all.

Enforcement lives in `llm/token_meter.py` (warn 70%, degrade to the zero-token
provider at 90%, stop at 100%) and is a runaway-loop backstop — at ~25%
utilisation it should never trigger in a real match.

---

## 1. What actually consumes tokens

The LLM never picks moves (book rule 25), so it is **not** on the per-step
critical path. It has exactly three jobs:

| Purpose | Frequency | Model tier | Why not free |
|---|---|---|---|
| Hint / bluff text | every `every_n_steps` turns (default 2) | cheap (Haiku-class) | free-language dialogue is mandatory (rule 26) |
| Hint decoding | only when the opponent's text is not parseable deterministically | cheap | a deterministic parser handles the common cases |
| Negotiation prose | ~6–12 messages per opponent, once | stronger (Sonnet-class) | terms are agreed once and reused for 6 mini-games |

Everything else — belief, movement, barriers, capture, scoring, crypto — is
deterministic Python and costs nothing.

## 2. Per-run estimates (leaning low)

Assumptions, taken from the reference log's actual prompt sizes:
hint call ≈ **260 in / 40 out** ≈ 300 tokens; negotiation message ≈
**700 in / 250 out** ≈ 950 tokens.

| Scope | Calculation | Estimate |
|---|---|---|
| One mini-game (35 steps, call every 2nd step, ~17 calls) | 17 × 300 | **≈ 5,000** |
| Hint decoding fallback (~20% of turns) | 7 × 300 | **≈ 2,000** |
| One mini-game total | | **≈ 7,000** |
| One series (6 mini-games) | 6 × 7,000 | **≈ 42,000** |
| Negotiation for that opponent (once) | 10 × 950 | **≈ 9,500** |
| **One full match (series + negotiation)** | | **≈ 50,000** |

Against the book's ~200,000 per-series cap that is **~25% utilisation** — a
comfortable margin, and the reason the cap is not a constraint on our design.

## 3. Project estimate

| Item | Count | Each | Total |
|---|---|---|---|
| Counted matches (target) | 6 | 50,000 | 300,000 |
| Warm-up matches (uncounted, shorter) | 4 | 20,000 | 80,000 |
| Development & self-play smoke runs | — | — | 60,000 |
| Tuning / prompt iteration | — | — | 40,000 |
| **Project estimate** | | | **≈ 480,000** |
| **Project ceiling in the meter** | | | **5,000,000** |

The ceiling is ~10× the estimate on purpose. It is a backstop against a runaway
loop, not a budget we manage against: it must never be the thing that decides a
match, and there is no scenario in normal play where it is reached.

### Cost at that volume

Order of magnitude only — the meter records the real split per model and the
analysis notebook renders the final table from measured data (guidelines §11).
With cheap-tier pricing for the bulk of calls and a stronger model only for
negotiation, ~480k mixed tokens lands in the **low single-digit dollars**.
DeepSeek as the fallback tier is cheaper still, which is why it carries the
testing load.

## 4. Why the estimates lean low with confidence

1. **Template mode is the default**, not the exception. A full series can be
   played at **zero tokens** (book PAGE 67) — the LLM is an enhancement.
2. **`every_n_steps` throttles calls**; hints do not need to change every turn
   to be effective.
3. **Negotiation is amortised**: agreed once, reused across all 6 mini-games.
4. **Degradation is automatic**: at 90% of budget the router drops to templates,
   so the ceiling is enforced by behaviour, not by hoping.

## 5. Where the numbers are recorded

`TokenMeter.report()` produces the per-purpose, per-model and per-mini-game
breakdown that feeds three places: the `tokens_total` field in the result email
(book rule 54), the dashboard's live budget panel, and the cost table in the
analysis notebook. Every figure in the final report is measured, never assumed.

## 6. Configuration

```toml
[llm]
series_token_budget = 200000    # the AGREED term (Appendix F Table 18)
project_token_budget = 5000000  # runaway-loop backstop, not a managed budget
every_n_steps = 2               # hint cadence — tune for QUALITY, not cost
```

`every_n_steps` is a gameplay dial, not a savings dial: lower it if richer
dialogue wins more games. The budget has room.

Both budgets are config values, never literals in code (guidelines §7.2).
