# PRD — LLM Layer: provider chain, prompts, guards

| | |
|---|---|
| **Version** | 1.00 |
| **Date** | 2026-07-25 |
| **Mechanism** | `llm/router.py`, `base.py`, `anthropic_provider.py`, `deepseek_provider.py`, `template_provider.py`, `prompts.py`, `hint_guard.py`, `hint_parser.py`, `speaker.py`, `token_meter.py` |
| **Parent docs** | `PRD.md` (FR-LLM-1..6), `PLAN.md` (ADR-003), `TOKEN_BUDGET.md` |

---

## 1. What the LLM is and is not for

The LLM produces **language only**: bluffs, taunts, negotiation prose, and
best-effort decoding of the opponent's words. It never selects a move (book rule
25), and the architecture enforces that rather than trusting it — a meta-test
asserts no module under `domain/` may import an LLM SDK at all.

This matters competitively. A team that lets a model pick moves inherits its
spatial hallucinations, and an illegal move is a technical loss. Our moves are
deterministic Python; the model only decides how to *describe* them.

## 2. The chain (ADR-003)

```
Anthropic (primary)  →  DeepSeek (fallback)  →  Template bank (floor)
```

| Tier | Role | Fails when |
|---|---|---|
| Anthropic | best prose for hints and negotiation | outage, rate limit, budget exhausted |
| DeepSeek | independent failure domain; carries dev traffic | outage, rate limit |
| Template | offline sentence bank, 0 tokens | never — it is the floor |

**Never fail the turn.** The chain terminates in a provider that cannot fail, so
a dead API costs quality, not a game. The book explicitly permits a full series
at zero tokens (PAGE 67), which is what makes this honest rather than a hack.

**Recover upward.** A failed provider gets a cooldown, then a health probe
promotes it back. Without this, a thirty-second blip would demote us to
templates for an entire six-game series.

**Distinguish outage from refusal.** `ProviderUnavailableError` marks a provider
unwell (cooldown); `ProviderRefusedError` does not, because a content refusal or
a malformed request says nothing about the service's health.

### 2.1 A defect worth recording

The gatekeeper wraps failures in its own `failed after N attempts` error, so the
original cause was invisible to the classifier — a **bad API key looked like a
transient outage**, and we would have spent retries and a cooldown on something
no retry can fix. `classify_error` now walks the `__cause__` chain. It lives in
`base.py` because both providers had identical copies, which the guidelines
forbid at two sites.

## 3. Visibility (FR-LLM-2)

Assignment 6 could not answer "which model said that?". Now:

* every provider switch emits `llm.provider_changed` / `llm.degraded` /
  `llm.recovered`;
* every completion carries `provenance` (provider, model, tokens) attached to
  the message in the dialogue transcript;
* `router.active` and `router.status()` feed the dashboard badge and panel.

## 4. Guards — asked in the prompt, enforced after generation

A prompt instruction is a request; a guard is a guarantee. `hint_guard` runs on
**every** outgoing hint, from the model or the template bank alike:

| Guard | Why |
|---|---|
| Coordinate stripping | Book rule 27 forbids numeric-position protocols, and a helpful model will write "I'm at (3,4)" while sounding cooperative |
| Word cap | The limit is an agreed term, so exceeding it is a contract breach, not a style issue |
| Intent validation | The intent is cryptographically sealed with the move; an invalid value would be unauditable |
| Empty-hint fallback | Silence breaks the free-language dialogue requirement (rule 26) |

`Speaker` is the single exit to the wire: a meta-test asserts `guard_hint` is
called in exactly one place, so no path reaches an opponent unvetted.

## 5. Parsing the opponent — deterministic first

Order is deliberate and not the obvious one: a **keyword pass runs before any
model call**. Most hints are plainly worded, and a local parse is free, instant,
and cannot hallucinate a direction the opponent never claimed. The model is the
fallback for genuinely ambiguous prose.

Failure is first-class: an unparseable hint returns **zero confidence**, which
the belief engine treats as an identity update. A fabricated direction would be
worse than silence — it poisons the belief map with false certainty. Negated
phrasing ("I did *not* go north") deliberately lowers local confidence, because
the keyword reading is exactly backwards there.

## 6. Economy — a quality dial, not a savings dial

`every_n_steps` skips the model on off-cycle turns (the opponent does not need
fresh prose every step to be misled), and the token meter degrades to templates
at 90% of the agreed series cap. Both exist to respect the **agreed** term
(Appendix F Table 18), not to save money: measured usage is ~25% of the cap, and
the grade is a league ranking. If richer dialogue wins more games, we spend more.

## 7. Metrics & acceptance

| Metric | Target | Test |
|---|---|---|
| Turn never fails on provider outage | 100% | `test_the_chain_ends_at_the_template_bank` |
| Recovery after cooldown | promoted on healthy probe | `test_health_probes_promote_us_back_up_the_chain` |
| Auth failure classified permanent | not retried as an outage | `test_a_bad_key_is_permanent_not_transient` |
| Coordinate leak blocked | 0 reach the wire | `test_a_coordinate_leak_from_the_model_is_stripped` |
| Single egress | `guard_hint` called once | `test_template_and_model_hints_share_one_guard` |
| No test touches a real API | 100% mocked | provider suites (guidelines §6.1 rule 7) |
| Parse never invents | unparseable → 0.0 confidence | `test_unparseable_model_output_yields_zero_confidence` |

## 8. Alternatives considered

| Alternative | Why not |
|---|---|
| Single provider | One outage would silence us mid-series; the book's own reference ships four modes for this reason. |
| LLM picks moves | Forbidden by default (rule 25); hallucination → illegal move → technical loss. We also decline it in negotiation (PLAN §4). |
| LLM-first parsing | Slower, costlier, and capable of inventing a direction; the keyword pass handles the common case for free. |
| Streaming responses | No benefit inside a 30 s turn budget; adds failure modes mid-parse. |
| Prompt-only rule enforcement | A prompt is a request. Rule 27 is not optional, so it needs a guard. |

## 9. Open items

* Per-purpose model routing (cheap for banter, stronger for negotiation) is
  wired through `purpose=` but not yet config-driven — T-1306.
* Meter persistence across a process restart within a match — T-1325.
* The prompt book (guidelines §8.3) draws its content from
  `prompts.prompt_catalogue()`; assembling the document is an E22 task.
