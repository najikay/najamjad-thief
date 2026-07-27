# Token budget — measured usage, limits, and how they are enforced

**Version 2.00 · 2026-07-27** — estimates replaced with measurements.

**Priority: the grade is a league ranking, so match quality outranks token
thrift every time.** This document exists because metering is a deliverable —
the book requires reporting consumption (rule 54) and the guidelines require a
cost table (§11) — not because spend is a design constraint.

The one number that is a genuine *rule* rather than an expense is the agreed
per-series cap (~200k, negotiable). We sign that term with each opponent, so
exceeding it would be a breach. Everything below shows why it never binds.

Version 1.00 of this document estimated a series at ~50,000 tokens and ~25 % of
the cap. **Both were roughly an order of magnitude too high.** The measured
figure is 4,577 tokens and 2.3 %. The estimates were wrong in the safe
direction, but they were wrong, and the table below is now generated from
`scripts/measure_tokens.py` rather than from arithmetic on guessed prompt sizes.

---

## 1. What actually consumes tokens

The LLM never picks moves (book rule 25), so it is **not** on the per-step
critical path.

| Purpose | Frequency | Model tier | Measured share of calls |
|---|---|---|---|
| Hint / bluff text | every `every_n_steps` turns (default 2) | cheap (Haiku-class) | **100 %** |
| Hint decoding | only when deterministic parsing fails | cheap | 0 % — `extract_json` handles every case seen so far |
| Negotiation prose | — | — | 0 % — see below |

**Negotiation makes no model calls at all.** `docs/PRD_negotiation.md`
deliberately rejected free-form LLM negotiation as unbounded and unverifiable
(rule 26 governs hints, not contracts), so the terms are exchanged as structured
data. The `negotiation_model` key in `config/police/game.toml` is therefore
inert; it is recorded in `docs/OPEN_ITEMS.md` as a documentation defect rather
than presented here as a per-purpose routing optimisation it is not performing.

Everything else — belief, movement, barriers, capture, scoring, crypto — is
deterministic Python and costs nothing.

## 2. Measured consumption

Produced by `uv run --group analysis python scripts/measure_tokens.py`, which
plays a real six-game series through `MatchRunner` and builds every prompt with
the real `Speaker`, so the hint cadence, the guard and the template floor all
behave as they do in a match.

| Hint cadence | Model calls | Input tokens | Output tokens | Total | USD | Share of 200k cap | Saving vs all-LLM |
|---|---:|---:|---:|---:|---:|---:|---:|
| every turn | 71 | 7,326 | 1,183 | 8,509 | $0.0132 | 4.3% | 0% |
| every 2 turns **(shipped)** | 38 | 3,928 | 649 | 4,577 | $0.0072 | 2.3% | 46% |
| every 3 turns | 27 | 2,798 | 477 | 3,275 | $0.0052 | 1.6% | 62% |

A hint call costs about **103 in / 17 out**. Version 1.00 assumed 260/40 — the
prompts are shorter than they were imagined to be, and the reply is capped at
120 tokens by `max_tokens` while the guard's 15-word limit keeps it far below
even that.

**Worst case.** The measured series runs 71 turns because our cop captures
quickly. A series where all six games run the full 35-step horizon is 210 turns:
**≈13,500 tokens, 6.8 % of the cap**. That is the number the budget must
survive, and it still leaves an order of magnitude of headroom.

### The honesty boundary

* **Measured** — the call count and the exact prompt and reply text.
* **Approximated** — the conversion of that text to tokens, using
  `cl100k_base`; there is no Anthropic key on the machine that produced these
  figures. Expect a few percent of error.
* **Not ours** — the per-million prices, which are published list prices in
  `config/model_prices.json`, dated and to be re-checked before submission.

Set `ANTHROPIC_API_KEY` and re-run and the meter records the provider's own
reported usage, collapsing the first two into a single measured number.

## 3. Project total

| Item | Count | Each | Total |
|---|---|---|---|
| Counted matches (target) | 6 | 13,500 (worst case) | 81,000 |
| Warm-up matches (uncounted) | 4 | 13,500 | 54,000 |
| Development & self-play runs | — | — | 60,000 |
| Tuning / prompt iteration | — | — | 40,000 |
| **Project total** | | | **≈ 235,000** |
| **Project ceiling in the meter** | | | **5,000,000** |

The ceiling is ~20× the projection on purpose. It is a backstop against a
runaway loop, not a budget we manage against, and at these volumes the entire
project's model spend is **well under one US dollar**.

## 4. Why consumption is this low

1. **Template mode is the default**, not the exception. A full series can be
   played at **zero tokens** (book PAGE 67) — the LLM is an enhancement.
2. **`every_n_steps` throttles calls**, measured at a 46 % reduction.
3. **Games end early.** Our cop's mean capture is 9.6 steps, not 35, so a real
   series is a third of its worst case.
4. **Degradation is automatic**: at 90 % of budget the router drops to
   templates, so the ceiling is enforced by behaviour rather than by hoping.

## 5. Enforcement

`llm/token_meter.py` warns at 70 %, degrades to the zero-token provider at 90 %,
and stops at 100 %. At 2.3 % measured utilisation **none of these thresholds can
trigger in a real match**; they exist to honour the signed term and to catch a
runaway loop.

`TokenMeter.report()` produces the per-purpose, per-model and per-mini-game
breakdown that feeds the `tokens_total` field in the result email (rule 54), the
dashboard's live budget panel, and the cost table in `notebooks/analysis.ipynb`.

## 6. Configuration

```toml
[llm]
series_token_budget = 200000    # the AGREED term (Appendix F Table 18)
project_token_budget = 5000000  # runaway-loop backstop, not a managed budget
every_n_steps = 2               # hint cadence — tune for QUALITY, not cost
```

`every_n_steps` is a gameplay dial, not a savings dial: lower it to 1 if richer
dialogue wins more games. Doing so costs 3,932 extra tokens per series — 2 % of
the cap and about one US cent. The budget has room.

Both budgets are config values, never literals in code (guidelines §7.2).
