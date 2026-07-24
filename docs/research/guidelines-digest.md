# Guidelines Digest — "Guidelines for Writing Professional Software at the Highest Level of Excellence"

**Source:** `software_submission_guidelines-V3.pdf` (Dr. Yoram Segal, version 3.00, dated 2026-03-26, 39 pages, Hebrew).
Extraction: `.extracted/guidelines.txt`. Page references below are to the PDF page markers (`===== PAGE N =====`).

**Purpose of this digest:** exhaustive English compliance checklist. Grading is checked against the source document — the instructor states explicitly (p. 33, §19) that **AI agents may be used to perform the grading check**, so every concrete rule below is potentially machine-checked.

> **Meta-rule (p. 33, §19 "Important Note"):** *"This document presents an especially high level of excellence. Not every section is fully mandatory, but the more criteria are met, the higher the quality assessment will be."* Students are encouraged to use LLM tools and AI agents to complete the project. Some items ARE labeled explicitly mandatory (חובה / MANDATORY) — those are flagged below.

> **Items NOT found in this document** (despite being expected): no 120-line "soft" limit (only the 150-line rule appears, three times); no mypy/black as separate tools (ruff covers isort/pep8-naming/pyupgrade via rule codes); no PDF submission template, no `xxxxxxxx-exyy.pdf` file-naming rule, and no self-grading section. Those rules, if they exist, come from a different course document (e.g., the exercise/submission instructions), not this one. Do not assume compliance on them from this file alone.

---

## 1. File-Length Limit — Max 150 Lines (pp. 10, 15, 30, 33, 36, 39)

**Exact rule (p. 10, §3.2 "File Size Rule — Maximum 150 lines"):**
- "Every code file shall not exceed **150 lines of code** (**blank lines and comment lines are not counted**)."
- "When a file exceeds the limit, **split it into multiple files — never compress code to fit** the limit."

**What counts:** lines of code only. Blank lines and comment lines are excluded from the count. (Docstrings are not explicitly addressed; safest reading: docstrings are comments/documentation and likely excluded, but keep files small regardless.)

**Applies to test files too (p. 15, §6.1 testing rule #6):** "Test files also comply with the 150-line rule."

**Mandated splitting strategies (p. 10):**
| Strategy | When |
|---|---|
| Extract helper functions to a separate file | standalone functions |
| Extract a mixin | class has multiple responsibilities |
| 50/50 split | file has two logical halves (e.g., read/write) |
| Extract constants to `constants.py` | constants |
| Extract models to separate file | model definitions |

**Enforcement (Quick-reference card, p. 33, Table 5):** File size ≤ 150 lines — enforced by **automated check**.

Note: the appendix restates it slightly softer as "files up to ~150 lines of code" (p. 36, §20.2) and "files ≤ 150 lines" in the final checklist (p. 39, §20.9). Treat 150 as a hard cutoff.

---

## 2. Linting / Formatting — Ruff, Zero Violations (p. 17, §7.1)

**Rule:** "**Zero Ruff violations are permitted. All code must pass `ruff check` with no errors.**"

**Required `pyproject.toml` configuration (p. 17, verbatim):**
```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM"]
ignore = ["E501"]
```

**Active rule categories (p. 17):**
| Code | Tool/meaning |
|---|---|
| E | PEP 8 errors (indentation, whitespace, style) |
| F | Pyflakes (undefined names, unused imports) |
| W | PEP 8 warnings |
| I | isort (import ordering) |
| N | pep8-naming (naming conventions) |
| UP | pyupgrade (modernize to Python 3.10+) |
| B | flake8-bugbear (common bugs) |
| C4 | comprehension usage |
| SIM | expression simplification |

- No mention of black, mypy, or standalone isort — **ruff is the single linter**, with isort/naming handled via ruff rule codes. E501 (line-too-long) is ignored but `line-length = 100` is still configured.
- Enforcement (p. 33, Table 5): Linter — threshold **0 violations** — enforced via `ruff check`.

---

## 3. Testing Requirements (pp. 15–16, §6; p. 37, §20.4)

### 3.1 TDD — mandatory process (p. 15, §6.1)
- "**All development must follow Test-Driven Development**: RED — GREEN — REFACTOR."
- Every module must have a corresponding test file.
- **Every public function/method must have at least one test.**
- Tests cover both the happy path AND error cases.
- Tests are written **before or alongside** implementation, "not as an afterthought."

### 3.2 Required test directory structure (p. 15, verbatim)
```
tests/
    unit/
        test_<module>/        # Mirror src/ structure
            test_<file>.py
    integration/
        test_<feature>.py
    conftest.py               # Shared fixtures
```

### 3.3 Seven testing rules (p. 15, §6.1)
1. Every new module must have a matching test file.
2. Every public function must have at least one test.
3. Test happy path AND error cases.
4. Use fixtures from `conftest.py` for shared test data.
5. **Mock external dependencies** (database, files, API).
6. Test files also obey the 150-line rule.
7. **No tests that depend on external services.**

### 3.4 Coverage — minimum 85% (pp. 15–16, §6.2)
- "Global test coverage must be **85% or higher**. The test suite **must fail** if coverage drops below this threshold."
- Required `pyproject.toml` config (verbatim, pp. 15–16):
```toml
[tool.coverage.run]
source = ["src"]
omit = ["src/main.py", "*/tests/*", "src/**/gui/*"]

[tool.coverage.report]
fail_under = 85
```
- Required coverage types (p. 16): statement coverage, branch coverage, and path coverage for critical paths.
- Appendix (p. 37, §20.4): 85% minimum for new code; **increased coverage for critical code and business logic**; automation in a **CI/CD pipeline**; coverage reports required.
- Enforcement (p. 33, Table 5): coverage ≥ 85% via `pytest --cov`; TDD enforced as "work process".

### 3.5 Edge cases & expected results (p. 16, §6.3–6.4; p. 37)
- Systematically identify boundary conditions; document every edge case with detailed description (appendix: with expected input and response).
- Include **screenshots of failures** where relevant.
- Error-handling mechanisms must include: defensive programming (input validation), clear error messages, detailed logging, **graceful degradation**.
- Document expected run results for every test; produce automated test reports with pass/fail rates; keep logs of successful and failed runs.

Framework: pytest (implied throughout: `uv run pytest tests/`, `pytest --cov`, `conftest.py` fixtures).

---

## 4. Project / Repo Structure Requirements (pp. 7–9, §2; p. 10, §3.1)

**Opening rule (p. 7, §2):** "Every professional software project **must** include the minimal folder structure and documentation files. **Without these documents the project will not be considered as meeting minimum requirements.**"

### 4.1 README.md — MANDATORY, at project root (p. 7, §2.1; p. 36, §20.2)
Must serve as a **full user-manual-level guide** and include:
- [ ] Installation instructions — system requirements, step-by-step install, environment-variable setup, troubleshooting common problems
- [ ] Usage instructions — running in different modes, CLI/GUI flags and options, typical workflow
- [ ] Examples and demos — code examples, screenshots, common use scenarios (appendix adds: links to videos)
- [ ] Configuration guide — config files, parameters and their effects
- [ ] Contribution guidelines — code and style standards
- [ ] License & credits — usage license and attribution of third-party libraries

### 4.2 docs/ folder — MANDATORY documents (pp. 7–8, §2.2)
| File | Content |
|---|---|
| `docs/PRD.md` | Product Requirements Document: project overview & context, user problem, market analysis & target audience; measurable goals, KPIs, acceptance criteria; functional & non-functional requirements, user stories, use scenarios; assumptions, dependencies, constraints, out-of-scope items; timeline & milestones with expected deliverables |
| `docs/PLAN.md` | Architecture & technical planning: **C4 Model diagrams** (Context, Container, Component, Code); **UML diagrams** for complex processes + deployment diagrams; **ADRs** (architecture decision records) with rationale, trade-offs, alternatives; API/interface documentation, data schemas & contracts |
| `docs/TODO.md` | Detailed task list with priorities and status (not started / in progress / done); phase breakdown with milestones; responsibility assignment per task; definition-of-done per task |

### 4.3 Dedicated PRDs per algorithm/mechanism (p. 8, §2.3)
"**Important requirement:** for every specific algorithm, central mechanism, or complex technical component — a **dedicated, separate PRD document** must be created."
Naming pattern: `docs/PRD_<mechanism>.md` (examples given: `PRD_ml_algorithm.md`, `PRD_authentication.md`, `PRD_search_engine.md`, `PRD_caching.md`).
Each dedicated PRD includes: detailed description incl. theoretical background; specific requirements, expected input/output, performance metrics; constraints, alternatives considered and why this choice; success criteria and specific test scenarios.

### 4.4 Recommended project layout (pp. 8–9, §2.4, verbatim reconstruction)
```
project-root/
├── src/                      # Source code
│   ├── <package>/
│   │   ├── __init__.py
│   │   ├── sdk/              # SDK layer
│   │   │   └── sdk.py
│   │   ├── services/         # Business logic
│   │   ├── shared/           # Shared utilities
│   │   │   ├── gatekeeper.py # API gatekeeper
│   │   │   ├── config.py     # Configuration manager
│   │   │   └── version.py    # Version tracking
│   │   └── constants.py
│   └── main.py
├── tests/                    # Unit and integration tests
│   ├── unit/
│   └── integration/
├── docs/                     # Documentation (MANDATORY)
│   ├── PRD.md                # Product Requirements
│   ├── PLAN.md               # Architecture & Planning
│   ├── TODO.md               # Task tracking
│   └── PRD_<mechanism>.md    # Per-algorithm PRDs
├── config/                   # Configuration files
│   ├── setup.json
│   └── rate_limits.json
├── data/                     # Input data
├── results/                  # Experiment results
├── assets/                   # Images, graphs, resources
├── notebooks/                # Analysis notebooks
├── README.md                 # MANDATORY
├── pyproject.toml            # Build & dependencies
├── uv.lock                   # Locked dependencies
├── .env-example              # Secret placeholders
└── .gitignore
```

### 4.5 Mandatory work process (p. 9, §2.5) — order matters
1. Create `docs/PRD.md` — **and approve it before continuing**
2. Create `docs/PLAN.md` — architectural planning
3. Create `docs/TODO.md` — task list
4. Create dedicated PRDs for every central algorithm/mechanism
5. **Approve all documents before development starts**
6. Begin development — **update TODO.md with progress**
7. Save results, create visualizations, update README.md

### 4.6 Modular structure principles (p. 10, §3.1; p. 36)
- Logical folder split by role: source, tests, docs, data, results, config, assets.
- Feature-based or layered architecture; clear separation of code, data, results, docs.
- Descriptive, consistent folder and file names; clear separation of responsibilities.

---

## 5. Code Style & Design Rules

### 5.1 Comments & docstrings (p. 10, §3.3; p. 37, §20.2)
- Comments must explain the **"why," not just the "what."**
- **Every function, class, and module must include detailed docstrings.**
- Comments should explain complex design decisions, document assumptions and preconditions, and be updated together with code changes.
- Descriptive, precise variable and function names.
- Short, focused functions following **Single Responsibility**.
- **DRY** — no duplicated code.
- Consistent code style across the whole project.

### 5.2 OOP design — no code duplication (p. 11, §4.2; p. 12)
Mandatory refactoring triggers:
| Situation | Required action |
|---|---|
| Same function body in **2+ files** | extract to shared module |
| Same try/except pattern in **3+ files** | create a wrapper function |
| Identical method in **3+ classes** | create base class or mixin |
| Copied logic with slight variations | use **Template Method** pattern |

Mixin rules (p. 12): each mixin provides exactly **one concern**; mixins must not override each other's methods; mixins must be independently testable.
Enforcement (p. 33, Table 5): "extraction at 2+ copies" — checked by code review.

### 5.3 SDK architecture — MANDATORY (p. 11, §4.1)
- "Every function containing business logic **must** be accessible through an **SDK layer**. The SDK is the **single entry point** for all consumers: menus, GUI, CLI, third-party integrations and future services."
- Layering: External Consumers (GUI/CLI/REST/3rd party) → **SDK** → Domain Services (services, models, orchestrators) → Infrastructure (DB, file I/O, external APIs).
- Requirements:
  - [ ] Every business function exposed via an SDK class
  - [ ] **No business logic in GUI, CLI, or controller layers** — those layers delegate to the SDK
  - [ ] External consumers can import the SDK and run all operations **without access to internal modules**

### 5.4 Building-blocks design (p. 28, §16)
Every building block is defined by:
- **Input Data** — data types, valid domain, external dependencies, comprehensive validation
- **Output Data** — data types, format, edge-case behavior
- **Setup Data** — parameters with defaults, configuration, initialization
Principles: Single Responsibility, Separation of Concerns, Reusability (blocks independent of specific code), Testability via **dependency injection**.
The reference example (pp. 28–29, `DataProcessor`) shows the expected pattern: class docstring documenting Input/Output/Setup; `__init__` validates config (`_validate_config`) raising `ValueError`; public method validates input (`_validate_input`) raising `TypeError` before processing.

### 5.5 Package organization (p. 26, §14)
- Every package must have `pyproject.toml` (preferred) or `setup.py` with name, version, description, author, license, dependencies (dependencies pinned with versions).
- `__init__.py` **must exist in every sub-folder** of the package; recommended to export public interfaces via `__all__` and define `__version__`.
- **All imports must use relative paths or package names — never absolute paths.** File read/write is also done relative to the package path.
- Checklist (p. 26, §14.4): pyproject.toml exists with name/version/deps; `__init__.py` in main folder exporting public API with `__version__`; source in dedicated folder, tests in `tests/`, docs in `docs/`; all imports relative, no absolute paths.

### 5.6 Parallelism (p. 27, §15)
- Multiprocessing for **CPU-bound** work (math, image processing, model training); multithreading for **I/O-bound** (network, DB, file I/O).
- Thread safety: protect shared variables with locks, use `queue.Queue` for data passing, avoid deadlock, use context managers.
- Checklist (§15.3): identify CPU-/I/O-bound ops and pick the right tool; dynamic process/thread counts; safe data sharing and correct synchronization; proper resource closing, exception handling, no memory leaks; protect shared state, prevent race conditions and deadlocks.

### 5.7 Extensibility (p. 24, §12)
- Plugin architecture: clear extension interfaces, lifecycle hooks (e.g., `beforeCreate`, `afterUpdate`), middleware mechanisms, API-first design.
- Maintainability: modularity & separation of concerns, component reuse, analyzability, testability.

### 5.8 Quality standard (p. 25, §13)
Compliance with **ISO/IEC 25010**: functional suitability, performance efficiency, compatibility, usability, reliability, security, maintainability, portability. Listed again in final checklist (p. 31).

---

## 6. API Gatekeeper & Rate Limiting — MANDATORY (pp. 13–14, §5)

- "**All external API calls must pass through a central gatekeeper.**" It handles rate limiting, queues, retries, monitoring.
- Requirements (p. 13):
  - [ ] No direct API calls that bypass the gatekeeper
  - [ ] Rate limits enforced **before** every call
  - [ ] Overflow is **queued, not rejected**
  - [ ] All API calls are **logged for monitoring**
- Reference interface (p. 13, verbatim): `class ApiGatekeeper` with `__init__(self, config: RateLimitConfig)`, `execute(self, api_call, *args, **kwargs)` (check limits → queue if limit reached → retry on transient failures → log all calls), `get_queue_status(self) -> QueueStatus`.
- **Rate limits must be read from a config file, never hardcoded** (p. 13, §5.2). Reference `rate_limits.json` (pp. 13–14, verbatim):
```json
{
  "rate_limits": {
    "version": "1.00",
    "services": {
      "default": {
        "requests_per_minute": 30,
        "requests_per_hour": 500,
        "concurrent_max": 5,
        "retry_after_seconds": 30,
        "max_retries": 3
      }
    }
  }
}
```
- Queue management (p. 14, §5.3): **FIFO** queue for waiting requests; **max queue depth defined in config**; **backpressure** signal when queue is full; drain mechanism that processes requests when rate windows reset.
- Enforcement (p. 33, Table 5): gatekeeper — code review + test; rate limits from config — configuration check; overflow handling "queue, not crash" — integration test.

---

## 7. Configuration & Secrets (pp. 17–18, §7.2–7.4; p. 37, §20.3)

### 7.1 No hardcoded values (p. 17, §7.2)
"All configurable values must come from configuration files, not source code."

Table 1 (p. 17) — wrong vs. right:
| Category | Wrong | Right |
|---|---|---|
| API URLs | `"https://api.example.com"` | `cfg.get("api_url")` |
| Rate limits | `rate_limit = 10` | `cfg.get("rate_limit", 10)` |
| Timeouts | `timeout=60` | `cfg.get("timeout", 60)` |
| Secrets | `api_key = "abc123"` | `os.environ.get("API_KEY")` |

**Allowed in code (pp. 17–18):** physical/mathematical constants, parameter default values, constants in `constants.py`, and Enum values.
Enforcement (p. 33): hardcoded values — threshold **0 in source code** — code review.

### 7.2 Configuration architecture (p. 18, §7.3) — versioned config hierarchy
```
config/
    setup.json            # Main app config (versioned)
    rate_limits.json      # API rate limits (versioned)
    logging_config.json   # Logging configuration
.env                      # Secrets (git-ignored)
.env-example              # Secret placeholders (committed)
pyproject.toml            # Build, lint, test settings
src/<package>/constants.py  # Immutable project constants
```
Config formats allowed (p. 37): `.json`, `.yaml`, or `.env`; template files for different environments.

### 7.3 Secrets — MANDATORY (p. 18, §7.4; p. 37)
- "**No secret data in the project.** When pushing to GitHub, you **must** create `.env-example` with dummy values."
- [ ] Absolute prohibition on API keys, passwords, or tokens in source code
- [ ] Use environment variables only: `os.environ.get("API_KEY")`
- [ ] `.gitignore` **must include**: `.env`, `*.pem`, `*.key`, `credentials.json`
- [ ] `.env-example` must exist with dummy values
- [ ] Production: dedicated secret-management tools
- [ ] Periodic key rotation, usage monitoring, least-privilege permissions
- Enforcement (p. 33): secrets — threshold **0 + `.env-example`** — **automated scan**.

---

## 8. Versioning, Git, Prompt Book, uv (pp. 19–20, §8)

### 8.1 Version tracking (p. 19, §8.1)
- Both code and config files must carry explicit versions. **Version starts at `1.00`** and increments on significant changes.
- Table 2 — required version locations:
| Item | Location | Initial value |
|---|---|---|
| Code version | `src/<pkg>/shared/version.py` | 1.00 |
| Config version | `"version"` key in JSON | 1.00 |
| Rate-limit version | `"rate_limits.version"` | 1.00 |
- The application **should validate config-version compatibility at startup**.

### 8.2 Git practices (p. 19, §8.2; p. 38, §20.7)
- Clear commit history with **meaningful messages**
- Separate **branches** for new features
- Code reviews via **Pull Requests**
- **Tagging** for major versions
- Final checklist (p. 31): "orderly Git history, license, attribution, deployment instructions."

### 8.3 Prompt Book (ספר הפרומפטים) — AI workflow documentation (p. 19, §8.3; checklists pp. 30, 38, 39)
A **Prompt Engineering Log** documenting the AI-assisted development process:
- [ ] List of **all significant prompts** used to build the project
- [ ] Context and goal of each prompt
- [ ] Examples of outputs received
- [ ] Iterative improvements
- [ ] Best practices derived from the experience
It appears in the final checklist twice ("documented prompt book", pp. 30 & 38–39) — treat as required.

### 8.4 uv package manager — MANDATORY (pp. 19–20, §8.4)
"All projects **must** use `uv` as package manager and task runner. **Forbidden:** `pip`, `pip install`, `python -m`, `venv`, `virtualenv` directly."

Table 3 — required commands:
| Task | Correct (uv) | Forbidden |
|---|---|---|
| Install dependencies | `uv sync` | `pip install` |
| Add dependency | `uv add <pkg>` | `pip install <pkg>` |
| Run script | `uv run python script.py` | `python script.py` |
| Run tests | `uv run pytest tests/` | `python -m pytest` |
| Lock dependencies | `uv lock` | `pip freeze` |

Requirements (p. 20):
- [ ] `pyproject.toml` is the **single source of truth** for dependencies (**no `requirements.txt`**)
- [ ] `uv.lock` exists and is **committed to version control**
- [ ] **No direct `pip` / `python -m` calls in code, scripts, CI/CD, or documentation**
- [ ] All tools invoked through `uv run`
- Enforcement (p. 33): package manager — "everything through uv" — **automated check**.

---

## 9. Research, Analysis & Visualization (p. 21, §9; p. 38, §20.5)

- **Parameter study / sensitivity analysis:** systematic experiments with controlled parameter variation; precise documentation of each parameter's effect; analysis methods such as partial derivatives, variance-based analysis, or one-at-a-time (OAT). Appendix adds: experiments table, illustrative graphs, statistical analysis.
- **Results analysis notebook:** Jupyter Notebook (or similar) with methodical analysis of experiment results; comparison between algorithms/configurations/approaches; mathematical proofs or theoretical analyses; **LaTeX for equations**; **references to academic literature**.
- **Visualization:** bar charts (comparisons), line charts (trends), scatter plots (correlations), heatmaps (parameter sensitivity), box plots (distributions), waterfall charts (change analysis). Quality criteria: clear labels, consistent & accessible colors, detailed captions and clear legend, high resolution. Tools cited (p. 38): Matplotlib, Seaborn, Plotly, Tableau, D3.js.

---

## 10. UI/UX (p. 22, §10; p. 38, §20.6)

- Usability criteria: learnability, efficiency, memorability, error prevention, satisfaction.
- **Nielsen's 10 heuristics** referenced as the standard (system status visibility, match with real world, user control & freedom, consistency & standards, error prevention, recognition over recall, flexibility & efficiency, aesthetic & minimalist design, error recovery help, help & documentation).
- Interface documentation: **screenshots of every screen and state**, typical user workflow description, interaction/feedback explanations, accessibility considerations.

---

## 11. Costs & Budget (p. 23, §11; p. 38, §20.7)

- **API token cost breakdown:** exact input/output token counts, cost per million tokens per model/service, total cost estimation. Table 4 (p. 23) shows the expected report format: rows per model (e.g., GPT-4, Claude 3) with input tokens, output tokens, total cost, and a totals row.
- Optimization strategies: reduce token usage, batch processing, model choice by cost-benefit.
- Budget management: cost forecasting at scale, real-time usage monitoring, budget-overrun alerts.
- Final checklist (p. 39): "Costs: token table, detailed analysis, optimization."

---

## 12. Final Submission Checklist (pp. 30–31, §17) — reproduce fully

### 17.1 Structure & documentation (mandatory)
- [ ] Comprehensive README.md at project root, at user-manual level
- [ ] `docs/` with PRD.md, PLAN.md, TODO.md
- [ ] Dedicated PRDs for every central algorithm/mechanism
- [ ] Architecture documentation with clear diagrams
- [ ] Documented prompt book

### 17.2 Architecture & code
- [ ] SDK architecture — all business logic through the SDK layer
- [ ] OOP design — no code duplication; use of inheritance and mixins
- [ ] API gatekeeper — all external calls through the Gatekeeper
- [ ] Rate limits from configuration; queue management for overflow
- [ ] Files up to 150 lines of code; comments and docstrings
- [ ] Consistent code style, descriptive names

### 17.3 Tests & quality
- [ ] TDD — tests written before/with the code
- [ ] Test coverage 85%+
- [ ] Zero Ruff violations
- [ ] Edge cases documented; error handling
- [ ] Automated test reports

### 17.4 Configuration & security
- [ ] Config files separate from code, versioned
- [ ] `.env-example` with dummy values
- [ ] No API keys or secrets in code
- [ ] `.gitignore` up to date
- [ ] uv as the sole package manager
- [ ] `pyproject.toml` and `uv.lock` present

### 17.5 Research & visualization
- [ ] Systematic experiments with parameter variation
- [ ] Documented sensitivity analysis; analysis notebook with graphs
- [ ] Quality graphs, screenshots, architecture diagrams
- [ ] Token cost analysis and optimization strategies

### 17.6 Extensibility & standards
- [ ] Documented extension points
- [ ] Organized as a professional Python package
- [ ] Parallel processing with thread safety
- [ ] Building-blocks-based design
- [ ] ISO/IEC 25010 compliance
- [ ] Orderly Git history, license, attribution, deployment instructions

### Appendix final checklist (p. 39, §20.9) — the 9-point grader summary
1. **Documentation:** PRD, architecture, README, API docs, prompt book
2. **Code:** modular structure, files ≤ 150 lines, comments & docstrings, style consistency
3. **Configuration:** separate files, `.env-example`, no secrets, `.gitignore`
4. **Tests:** 85%+ coverage, edge cases, error handling, automated reports
5. **Research:** parameter study, sensitivity analysis, analysis notebook, graphs
6. **Visualization:** quality graphs, screenshots, architecture diagrams
7. **Costs:** token table, detailed analysis, optimization
8. **Extensibility:** extension points, plugin examples, interfaces
9. **General:** Git history, license, attribution, deployment

---

## 13. Quick-Reference Enforcement Card (p. 33, Table 5) — verbatim reconstruction

| Rule | Threshold | Enforcement method |
|---|---|---|
| SDK architecture | all logic through SDK | code review |
| OOP / no duplication | extraction at 2+ copies | code review |
| API gatekeeper | all calls through it | code review + test |
| Rate limits | from config, not code | configuration check |
| Overflow management | queue, not crash | integration test |
| Version control | starts at 1.00 | version module |
| TDD | red-green-refactor | work process |
| File size | ≤ 150 lines | automated check |
| Linter | 0 violations | `ruff check` |
| Test coverage | ≥ 85% | `pytest --cov` |
| Hardcoded values | 0 in source code | code review |
| Secrets | 0 + `.env-example` | automated scan |
| Package manager | everything through uv | automated check |

---

## 14. Grading Meta-Notes

- **AI graders (p. 33, §19):** "It is clarified that as part of the checking, AI agents may be used to perform the check." → Assume every automatable rule above (150 lines, ruff 0, coverage ≥85 with `fail_under=85`, secrets scan, uv-only, presence of README/PRD/PLAN/TODO/`.env-example`/`uv.lock`) WILL be machine-checked.
- **Scoring is criterion-count based (p. 33):** not every section is fully mandatory; more criteria met → higher assessment. Prioritize depth, professionalism, and demonstrating high-level development capability.
- **Referenced external standards (p. 32, §18; p. 39):** MIT SQA plan, ISO/IEC 25010, Google Engineering Practices, Microsoft REST API Guidelines, Nielsen heuristics. Citing/aligning with these earns quality credit.
- **Explicitly mandatory ("חובה") items:** README.md, docs/ with PRD/PLAN/TODO, per-mechanism PRDs, work-process order (docs approved before code), SDK layer, API gatekeeper, TDD, 85% coverage w/ fail_under, zero Ruff, no hardcoded values, `.env-example` + `.gitignore` secret rules, versioning from 1.00, **uv only**.
- **AI-agent workflow expectations:** students act as "senior software architects orchestrating AI agents" (Vibe Coding, p. 6, §1.4). First rule of professional AI coding: **define full documentation/requirements before any line of code** (p. 6). The prompt book (§8.3) is the required record of this workflow.

---

## 15. Master Compliance Checklist (condensed, machine-checkable first)

**Automated / hard gates**
- [ ] Every source AND test file ≤ 150 code lines (blank/comment lines excluded)
- [ ] `ruff check` → 0 violations, with prescribed `[tool.ruff]` config (line-length 100, py310, select E,F,W,I,N,UP,B,C4,SIM; ignore E501)
- [ ] `uv run pytest tests/` passes; coverage ≥ 85% with `fail_under = 85` in pyproject
- [ ] uv-only: `pyproject.toml` + committed `uv.lock`; no requirements.txt; no pip/python -m anywhere (code, scripts, CI, docs)
- [ ] No secrets anywhere; `.env-example` committed; `.gitignore` covers `.env`, `*.pem`, `*.key`, `credentials.json`
- [ ] `README.md`, `docs/PRD.md`, `docs/PLAN.md`, `docs/TODO.md`, `docs/PRD_<mechanism>.md` all exist
- [ ] Versions start at 1.00 in `version.py` and every JSON config; startup config-version validation

**Review-checked**
- [ ] SDK single-entry-point layer; zero business logic in GUI/CLI/controllers
- [ ] ApiGatekeeper wrapping ALL external API calls; rate limits + queue depth from `config/rate_limits.json`; FIFO queue + backpressure + drain
- [ ] No duplicated code (2+ copies → extract); mixin rules; Template Method for variations
- [ ] Docstrings on every module/class/function; "why" comments; descriptive names; SRP; DRY
- [ ] Package: `__init__.py` everywhere, `__all__`, `__version__`, relative imports only
- [ ] Tests mirror src/, conftest.py fixtures, mocks for external deps, happy+error paths, 1+ test per public function

**Content deliverables**
- [ ] Prompt book (all significant prompts, context, outputs, iterations, lessons)
- [ ] C4 + UML + deployment diagrams, ADRs
- [ ] Analysis notebook with sensitivity study, LaTeX math, academic references, quality graphs
- [ ] Token-cost table + budget/optimization analysis
- [ ] UI screenshots of every screen/state, Nielsen-heuristics discussion, accessibility notes
- [ ] Extension points/plugin docs; ISO/IEC 25010 mapping
- [ ] Git: meaningful commits, feature branches, PRs, tags; license & attribution; deployment instructions
