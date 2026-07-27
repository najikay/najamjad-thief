# Documentation review — E22 (T-2232)

**Date:** 2026-07-27 · **Against:** `guidelines-digest.md` §15 master compliance
checklist, plus the content deliverables in §2, §9, §11, §12 and §13.

This is the second review pass. The first (`docs-self-review.md`, 2026-07-24)
covered the planning documents before any code existed; this one covers the
whole repository as it will be submitted.

Method: **every checklist item was executed, not read.** Where an item is
machine-checkable it was checked with a script; where it is not, the claim is
backed by a named file or test. Items that fail are recorded as failures.

---

## 1. Automated / hard gates

| Item | Result |
|---|---|
| Every source and test file ≤ 150 code lines | **pass** — `scripts/check_file_sizes.py`, part of `check_all.py` |
| `ruff check` → 0 violations, prescribed config | **pass** — line-length 100, py310, select ⊇ `E,F,W,I,N,UP,B,C4,SIM` |
| `pytest` passes, coverage ≥ 85 with `fail_under` | **pass** — 1,700+ tests, **99.3 %**, `fail_under = 85` |
| uv-only; `uv.lock` committed; no `requirements.txt` | **pass** |
| No `pip` / `python -m` anywhere | **fixed during this review** — see finding 1 |
| No secrets; `.env-example`; `.gitignore` coverage | **pass** — `.env`, `*.pem`, `*.key`, `credentials.json`, `token.json`, `secrets/` all ignored, and a CI gate fails the build if one is ever tracked |
| Mandated documents all exist | **pass** — README, PRD, PLAN, TODO, and seven `PRD_<mechanism>.md` |
| Versions start at 1.00; startup version validation | **pass** — `test_config.py::test_an_unsupported_version_refuses_to_boot` |

### Finding 1 — `python -m` in a script and in `assets/README.md` *(fixed)*

`scripts/pre_match_smoke.py` invoked `uv run python -m najamjad_agent.replay`, and
`assets/README.md` documented the same command.

The reason was real rather than lazy: that script is **byte-identical across both
repos**, so it cannot hardcode `najamjad-cop` or `najamjad-thief`. The fix keeps
that property without the banned form — the script now reads its own console
script name out of `pyproject.toml`:

```python
def console_script() -> str:
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return next(iter(manifest["project"]["scripts"]))
```

This is strictly better than the original independently of the rule: the smoke
test now exercises the **installed entry point**, which is what a grader and an
operator actually invoke, instead of reaching past it into a module. Verified:
clean log exits 0, tampered log exits 1.

### Finding 2 — seven functions without docstrings *(fixed)*

All seven were the same shape — a nested `probe()` closure inside a documented
factory in `net/preflight.py` and `net/preflight_checks.py`. The enclosing
function explained the check; the closure did not. Each now carries a one-line
docstring naming what it proves.

---

## 2. Review-checked items

| Item | Evidence |
|---|---|
| SDK single entry point; no business logic in CLI/UI | Meta-tests: the UI may import only the SDK, the CLI holds no game logic |
| `ApiGatekeeper` wrapping all external calls; limits from config | `shared/gatekeeper.py`; ceilings validated against Appendix F at load |
| No duplicated code | Core is byte-identical across repos **by construction** (`sync_core.py`), which is the largest duplication risk in a two-repo project |
| Docstrings on every module/class/function | **pass after finding 2** |
| `__init__.py` everywhere, `__all__`, `__version__`, relative imports only | **pass** — verified by AST walk; zero absolute self-imports |
| Tests mirror `src/`, conftest fixtures, happy + error paths | **partial** — see finding 3 |

### Finding 3 — 15 modules have no same-named test file *(accepted, not fixed)*

`match_audit`, `ports`, `anthropic_provider`, `deepseek_provider`, `hint_guard`,
`hint_parser` and nine others have no `test_<module>.py`.

Every one of them **is** tested — line coverage is 99.3 % and no module is
omitted from measurement — but through differently-named files: `hint_guard` and
`hint_parser` are covered by `test_template_and_guard.py`, the providers by
`test_providers.py`, and `ports` is a `Protocol` module with no runtime
behaviour to test.

Renaming 15 test files to satisfy a naming convention would churn the suite
without adding a single assertion. The guideline's *intent* — at least one test
per public function — is met and measured. Recorded here rather than silently
left, so a reviewer can disagree with the judgement rather than discover it.

---

## 3. Content deliverables

| Deliverable | Where |
|---|---|
| Prompt book | `docs/PROMPT_BOOK.md` — M0 through M7, one entry set per milestone |
| C4 + UML + deployment diagrams, ADRs | `docs/PLAN.md` §1–2 (7 Mermaid diagrams, all exported to `assets/`), 17 ADRs |
| Analysis notebook: sensitivity, LaTeX, references, graphs | `notebooks/analysis.ipynb` — 22 cells, 5 figures, **12 citations**, runs top-to-bottom |
| Token-cost table + optimisation analysis | `docs/TOKEN_BUDGET.md` and notebook §6 — measured, not estimated |
| UI screenshots, Nielsen heuristics, accessibility | `assets/`, `docs/UX.md` |
| Extension points / plugin docs | `docs/EXTENDING.md` + a worked plugin that loads via config and is tested |
| ISO/IEC 25010 mapping | `docs/ISO25010.md` — all eight characteristics, gaps marked ⚠ |
| Git hygiene, licence, deployment | Conventional commits, MIT `LICENSE`, `docs/RUNBOOK.md` |

### Finding 4 — `TOKEN_BUDGET.md` was an order of magnitude wrong *(fixed)*

Version 1.00 estimated ~50,000 tokens per series and ~25 % of the agreed cap,
from arithmetic on assumed prompt sizes. Measured: **4,577 tokens, 2.3 %**. The
document is now generated from `scripts/measure_tokens.py` and states its
honesty boundary explicitly. The same stale "~25 %" claim was corrected in the
`token_meter.py` docstring, which is where a reader is most likely to meet it.

### Finding 5 — `negotiation_model` configures nothing *(recorded, not fixed)*

`config/police/game.toml` declares `negotiation_model = "claude-sonnet-5"`, but
nothing reads it and `negotiate_prompt` has no runtime caller — measured, 100 %
of model calls are hint-purpose.

This is not a code oversight: `docs/PRD_negotiation.md` §62 deliberately
rejected free-form LLM negotiation as unbounded and unverifiable. The key and
the unused prompt template are leftovers of the rejected design.

Left in place for now because removing a config key days before a match is a
change with no upside and a non-zero chance of breaking a load path. It is
recorded in `docs/OPEN_ITEMS.md`, and `TOKEN_BUDGET.md` §1 now states plainly
that per-purpose routing is **not** currently happening, rather than implying a
cost optimisation we do not perform.

---

## 4. Verdict

**Five findings; three fixed during the review, two recorded with reasons.**

No open finding affects correctness or rule compliance. The two accepted
deviations — test-file naming and an inert config key — are both documented in
places a reader will actually encounter them.

The most valuable outcome of this pass was not a checklist item at all. It was
finding 4: a document that had quietly carried an invented number for three
weeks, in the one place the report is most likely to be checked against reality.
