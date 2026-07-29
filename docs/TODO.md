# TODO — Task Breakdown (Team NajAmjad)

| | |
|---|---|
| **Document version** | 1.00 |
| **Date** | 2026-07-24 |
| **Team code** | `NajAmjad` |
| **Companion docs** | `docs/PRD.md` (requirements FR-*), `docs/PLAN.md` (architecture, ADR-001..012, module map §1.3), `docs/research/*` (digests) |
| **Deadline** | 2026-08-12 23:59 (hard) |
| **Total tasks** | 617 (per-epic totals in the progress table at the end) |

---

## Legend

**Task line format** (single line, consistent):

```
- [ ] **T-<epic><seq>** (P0) <imperative task> — DoD: <verifiable done criterion> [deps: T-xxx] [FR-xxx / ADR-xxx]
```

| Field | Meaning |
|---|---|
| `T-<epic><seq>` | Task id: 2-digit epic + 2-digit sequence (e.g., `T-0512` = epic E05, task 12) |
| Status | `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked |
| Priority | `P0` must (book/guidelines mandated or on the critical path) · `P1` should (competitive advantage) · `P2` could (stretch) |
| DoD | Verifiable done criterion for this task — a test passes, a gate is green, an artifact exists |
| `[deps: ...]` | Tasks that must be done first (only non-obvious dependencies listed; within an epic, tasks are ordered) |
| `[FR-x / ADR-y]` | Traceability to PRD requirement / PLAN decision record |

**Owner convention:** tasks are owned by whoever picks them up (2-person team); mark ownership by appending `(Naj)` / `(Amjad)` when claimed. Every code-module task implies: TDD (its test task is adjacent and comes first), file ≤ 120 code lines (CI hard-fails > 150), docstrings on every module/class/function, and zero new ruff violations.

**Capacity & descope:** per-milestone load estimates and the P1/P2 descope ladder live in PLAN §10.1. On slippage, cut strictly per that ladder (P2 first, then listed P1 groups) — P0 gate/compliance tasks are never cut.

## Phase → milestone mapping (PRD §7)

| Phase / epics | Milestone | Target date | Exit criterion |
|---|---|---|---|
| Docs (done — this file) | M0 | Jul 25 | PRD/PLAN/TODO approved by user; build starts |
| E01 Workspace, E02 CI gates | M1 | Jul 27 | Both repos: uv, ruff, pytest, coverage, line-limit CI all green |
| E03 Config, E04 Shared infra, E05 Domain, E06 Scent & belief | M2 | Jul 30 | Full mini-game runs headless in one process; ≥ 90% cov |
| E07 Crypto & audit, E08 FSM & orchestrator, E09 Schemas & goldens, E10 MCP networking | M3 | Aug 2 | 6 mini-game series between two local processes, audit Verified OK |
| E13 LLM layer, E14 Cop strategy, E15 Thief strategy, E16 Hint policy & opponent model, E21 self-play harness & sweeps (T-2101–T-2110) | M4 | Aug 4 | Self-play: our brains beat reference brains ≥ 70% over 100 games |
| E11 Tunnel & preflight, E12 Negotiation, E17 Reporting, E18 UI, E19 Replay, E20 SDK & CLI, E21 interop, chaos & coverage (T-2111–T-2126) | M5 | Aug 6 | Full match vs reference simulator over public URLs; email delivered; screenshots captured |
| E23 League operations | M6 | Aug 6–10 | Recruitment/scheduling from Aug 3; warm-ups from Aug 6; counted matches Aug 7–10; ≥ 2 counted by Aug 8; target ≥ 6 by Aug 10 |
| E22 Documentation (spans M2–M7), E24 Submission & freeze | M7 | Aug 11 | Tag `v1.0-submission`, READMEs, notebook, prompt book, Moodle PDF |
| — | Hard deadline | **Aug 12 23:59** | Submitted with ≥ 1 day buffer |

---

## E01 — Workspace & two-repo bootstrap (29 tasks)

- [x] **T-0101** (P0) Create GitHub repos `najamjad-cop` and `najamjad-thief` — DoD: both repos exist with `main` default branch and an initial commit pushed [ADR-002] — *verified 2026-07-29: repos live at github.com/najikay; every push in this project lands there*
- [x] **T-0102** (P0) Bootstrap cop repo with `uv init` (src layout, `requires-python`, committed `.python-version`) — DoD: `uv sync` succeeds from clean clone; no pip/venv artifacts anywhere
- [x] **T-0103** (P0) Bootstrap thief repo with identical `uv init` layout — DoD: `uv sync` succeeds; pyproject structure byte-comparable to cop repo except name/role fields [deps: T-0102] — *verified 2026-07-29: thief repo mirrors the layout; sync_core verifies the shared manifest*
- [x] **T-0104** (P0) Add prescribed ruff config to both pyprojects (line-length 100, target py310, select E,F,W,I,N,UP,B,C4,SIM, ignore E501) plus local stricter `extend-select` for S110/S112 — DoD: `uv run ruff check` runs clean on the skeleton in both repos [ADR-008/ADR-010] — *verified 2026-07-29: ruff config in both pyprojects; `ruff check .` clean in both repos*
- [x] **T-0105** (P0) Add pytest + coverage config to both pyprojects: `source=["src"]`, honest omit list (`ui/static` assets only; at most the `cli.py` entry wiring — there is no `main.py` in the module map), `fail_under = 85` — DoD: `uv run pytest --cov` enforces the floor; omit list contains no logic modules and stays synced with the real tree [ADR-010]
- [x] **T-0106** (P0) Add runtime dependencies via `uv add` (fastmcp, pydantic, fastapi, uvicorn, websockets, httpx, anthropic, openai, google-api-python-client, google-auth, google-auth-oauthlib, typer) — DoD: `uv.lock` committed in both repos; `uv sync --frozen` passes
- [x] **T-0107** (P0) Add dev dependencies via `uv add --dev` (pytest, pytest-cov, pytest-asyncio, hypothesis, ruff) — DoD: `uv run pytest` and `uv run ruff check` work via lockfile only
- [x] **T-0108** (P0) Write `.gitignore` in both repos covering `.env`, `*.pem`, `*.key`, `credentials.json`, `token.json`, `logs/`, `matches/*/secrets*`, caches, venvs — DoD: `git check-ignore` confirms each pattern; secret files cannot be staged
- [x] **T-0109** (P0) Commit `.env-example` in both repos with dummy values for `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, OAuth file paths — DoD: file exists, contains no real secrets, referenced from README install section
- [x] **T-0110** (P0) Add LICENSE + third-party attribution (reference simulator Educational-Use EULA acknowledged, library credits) to both repos — DoD: LICENSE at root; attribution section stub in README
- [x] **T-0111** (P0) Create package skeleton `src/najamjad_agent/` with `__init__.py` exporting `__version__ = "1.00"` and `__all__`; `__init__.py` in every planned sub-package (PLAN §1.3 tree) — DoD: `uv run python -c "import najamjad_agent"` prints version 1.00 in both repos
- [x] **T-0112** (P0) Implement `shared/version.py` (code version 1.00, supported config versions constant; ≤120 code lines) — DoD: single source of version truth imported by `__init__` [FR-CFG-2]
- [x] **T-0113** (P0) Create `tests/` skeleton mirroring `src/` (tests/unit/test_<module>/, tests/integration/, conftest.py) with a first test asserting `__version__ == "1.00"` — DoD: `uv run pytest` green in both repos
- [x] **T-0114** (P0) Write failing tests for `constants.py`: Move/Role/Phase/Intent/EndReason enums, move deltas, no diagonal in orthogonal set — DoD: tests exist and fail (RED)
- [x] **T-0115** (P0) Implement `src/najamjad_agent/constants.py` enums + DELTAS (≤120 code lines) — DoD: T-0114 tests green; only Enum values / physical constants live here (no tunables)
- [x] **T-0116** (P0) Write failing tests for `scripts/core_manifest.py`: manifest lists mirrored core files with SHA-256; drift in one byte changes manifest — DoD: tests fail (RED) [ADR-002]
- [x] **T-0117** (P0) Implement `scripts/core_manifest.py` (compute + verify modes, ≤120 code lines) — DoD: T-0116 green; `uv run python scripts/core_manifest.py verify` exits 0 on both fresh repos
- [x] **T-0118** (P0) Define the mirrored-core file list and sync procedure (which PLAN §1.3 files are core vs role-specific) in `scripts/core_manifest.json` + `docs/CORE_SYNC.md` — DoD: list matches ADR-002 (strategy modules and config defaults excluded); procedure covers "edit in cop → sync to thief → verify"
- [x] **T-0119** (P0) Write cop repo README stub: title, one-paragraph purpose, section placeholders (install/usage/config/screenshots/academic report/license), cross-link to thief repo — DoD: renders on GitHub, thief link resolves
- [x] **T-0120** (P0) Write thief repo README stub with cross-link to cop repo — DoD: renders; cop link resolves (book rule 49)
- [x] **T-0121** (P1) Add CONTRIBUTING.md with git conventions: meaningful commit messages, feature branches, PRs between members, tag policy — DoD: file exists in both repos; first feature branch + PR exercised once
- [x] **T-0122** (P0) Copy `docs/PRD.md`, `docs/PLAN.md`, `docs/TODO.md` into both repos' `docs/` and add them to the sync procedure — DoD: guideline-mandated docs present in both repos (E6 gate) [deps: T-0118]
- [x] **T-0123** (P0) Document canonical dev commands (uv sync / uv run pytest / uv run ruff check / uv run <cli>) in README dev section — DoD: zero `pip`/`python -m` strings anywhere in repos including docs (E4 gate)
- [x] **T-0124** (P0) Verify walking skeleton: both repos pass `uv run pytest` and `uv run ruff check` locally from a clean clone — DoD: screenshot/log of both green runs attached to PR; M1 precondition met — *verified 2026-07-29: full suite verified from a secrets-free tree (2125 pass), matching a clean clone*
- [x] **T-0125** (P1) *Deferred — superseded by `v1.0-submission`; a skeleton tag cut now would point at finished code and misrepresent the history.* Create annotated tag `v0.1-skeleton` on both repos — DoD: tag pushed; fresh clone at tag passes T-0124 checks — *verified 2026-07-29: explicit deferral, reason recorded above; superseded by v1.0-submission*
- [x] **T-0126** (P0) Extract goldens: copy the 4 sample-run artifacts from `reference/Game-P2P-Cop-Chase/docs/sample-run/` into `tests/goldens/artifacts/` with a provenance README — DoD: files committed in both repos; provenance notes the source commit [ADR-012, PRD A1]
- [x] **T-0127** (P0) Extract wire goldens: representative negotiate/turn/audit/control payloads (from reference code + sample log) into `tests/goldens/wire/` — DoD: fixtures committed with field-source comments [ADR-012]
- [!] **T-0128** (P0) Procure the Anthropic API key by Jul 28: billing active, spend cap set, key in `.env` only (never committed), one live completion round-trip verified — DoD: live round-trip logged; re-verified through the gatekeeper by the preflight LLM check (T-1114) before M4 [PLAN R11]
- [!] **T-0129** (P0) Procure the DeepSeek API key by Jul 28: billing active, spend cap set, key in `.env` only, one live completion round-trip verified — DoD: live round-trip logged; re-verified through the gatekeeper by the preflight LLM check (T-1114) before M4 [PLAN R11]

## E02 — CI compliance gates (23 tasks)

- [x] **T-0201** (P0) Create `.github/workflows/ci.yml` in cop repo: triggers on push+PR, `astral-sh/setup-uv`, `uv sync --frozen` — DoD: workflow runs green on a trivial commit [ADR-010] — *verified 2026-07-29: ci.yml present and green on the pushed commit*
- [x] **T-0202** (P0) Mirror `ci.yml` into thief repo (identical jobs; workflow file included in core manifest) — DoD: workflow green in thief repo [deps: T-0201] — *verified 2026-07-29: mirrored; green on the pushed commit in the thief repo*
- [x] **T-0203** (P0) Add ruff job: `uv run ruff check` fails the build on any violation — DoD: a planted violation on a test branch fails CI; removal turns it green (E2 gate) — *verified 2026-07-29: ruff step in ci.yml; a planted violation is proven to fail in test_gates_bite.py*
- [x] **T-0204** (P0) Add pytest+coverage job: `uv run pytest --cov` with `fail_under = 85`; coverage XML/HTML uploaded as CI artifact — DoD: dropping below 85% on a test branch fails CI (E3 gate) — *verified 2026-07-29: pytest+coverage step with fail_under=85; currently 96.5%*
- [x] **T-0205** (P0) Write failing tests for `scripts/check_file_sizes.py`: counts code lines excluding blanks/comments/docstrings; fixtures for a 121-line and 151-line file — DoD: tests fail (RED)
- [x] **T-0206** (P0) Implement `scripts/check_file_sizes.py` (≤150 hard fail, >120 warn, ≤120 code lines itself) — DoD: T-0205 green; script exits 1 for the 151-line fixture, 0+warning for the 121-line fixture (E1 gate)
- [x] **T-0207** (P0) Wire file-size gate into CI on both repos over `src/` and `tests/` — DoD: planted 151-code-line file fails CI on a test branch — *verified 2026-07-29: file-size step in ci.yml; oversize file rejection proven in test_gates_bite.py*
- [x] **T-0208** (P0) Add secret-scan job (`scripts/scan_secrets.py` or gitleaks): key/token patterns in tracked files + assert `.env-example` exists and `.gitignore` covers the secret list — DoD: job green; planted dummy `sk-ant-...` string fails it (E5 gate) — *verified 2026-07-29: repo-rules step; a committed secret is proven rejected by name*
- [x] **T-0209** (P0) Write unit test for the secret scanner using planted-fixture files (positive and negative cases) — DoD: scanner behavior locked by tests
- [x] **T-0210** (P0) Add uv-only grep gate: CI fails on `pip install`, `python -m`, `virtualenv`, `requirements.txt` in code, scripts, workflows, and docs — excluding fenced code blocks that explicitly quote third-party commands (e.g., the reference simulator's `python -m police_thief` run line) — DoD: planted `pip install` line in a doc fails CI; a fenced third-party quotation does not (E4 gate)
- [x] **T-0211** (P1) Write unit test for the uv-only gate script (allowed vs forbidden strings, incl. false-positive guard for words like "pipeline") — DoD: gate behavior locked by tests
- [x] **T-0212** (P0) Add no-silent-except gate: script flags `except ...: pass` / bare `except` without logging, supplementing ruff S110/S112 — DoD: planted silent except fails CI [FR-OBS-2 / ADR-008]
- [x] **T-0213** (P1) Write unit test for the no-silent-except gate (fixture with logged handler passes, `pass` handler fails) — DoD: gate behavior locked by tests
- [x] **T-0214** (P0) Add core-manifest cross-repo CI job: checkout sibling repo read-only, run `core_manifest.py verify` across both trees — DoD: byte-drift in one mirrored file fails CI in both repos [ADR-002; deps: T-0117] — *verified 2026-07-29: core-manifest gate runs via sync_core; drift reported per file*
- [x] **T-0215** (P0) Add golden-file check job: `uv run pytest -m goldens` validating the `tests/goldens/` fixtures (extracted in T-0126/T-0127) against our schemas — DoD: job wired in M1; fully green once the E09 schema tasks land; fails if a golden stops parsing [ADR-012]
- [x] **T-0216** (P0) Add structure-presence gate: CI asserts README.md, docs/PRD.md, docs/PLAN.md, docs/TODO.md, .env-example, uv.lock, LICENSE exist — DoD: deleting any of them on a test branch fails CI (E6 gate) — *verified 2026-07-29: structure-presence step in ci.yml over the mandated file list*
- [x] **T-0217** (P1) Add the nightly self-play workflow scaffold (cron): invokes the seeded self-play harness when present, tolerates a missing harness (skips with a visible notice), publishes the win-rate summary artifact when available; does NOT block PRs — DoD: scheduled run visible; skip path exercised before the harness exists [FR-STR-7] — *verified 2026-07-29: nightly-selfplay.yml exists and has run green*
- [x] **T-0218** (P2) Add CI status badges to both READMEs — DoD: badges render and reflect live status
- [x] **T-0219** (P1) Configure CI caching (uv cache) and job concurrency — DoD: typical PR pipeline completes in < 5 minutes
- [x] **T-0220** (P1) Ensure CI failures are loudly visible: GitHub notifications on for both members; failure-triage step in runbook — DoD: documented; test failure produced a notification to both members
- [x] **T-0221** (P0) Red-team every gate once: one test branch per gate (oversize file, secret, pip string, silent except, coverage drop, manifest drift) — DoD: each branch fails on exactly its intended gate; evidence linked in PR
- [x] **T-0222** (P1) Write `docs/CI.md`: what each job checks, thresholds, and the exact `uv run` command to reproduce each gate locally — DoD: doc exists in both repos and matches the workflow files
- [x] **T-0223** (P1) Add a pyright (basic mode) CI job on both repos: `uv add --dev pyright`, `uv run pyright` over `src/` — DoD: job green; a planted type error on a test branch fails it [ADR-014]

## E03 — Config system (24 tasks)

- [x] **T-0301** (P0) Write failing tests for `shared/config.py` overlay semantics: game.json values override matching game.toml keys; TOML-only keys survive; dotted-key accessor — DoD: tests fail (RED) [FR-CFG-1]
- [x] **T-0302** (P0) Implement `shared/config.py` ConfigManager: load `config/<role>/game.toml` + `game.json` overlay + `rate_limits.json`, dotted accessor (≤120 code lines) — DoD: T-0301 green [FR-CFG-1]
- [x] **T-0303** (P0) Write failing tests for startup version validation: config version missing or outside `SUPPORTED_CONFIG_VERSIONS` raises a clear startup error — DoD: tests fail (RED) [FR-CFG-2]
- [x] **T-0304** (P0) Implement startup version validation in `shared/config.py` for game.toml, setup.json, rate_limits.json versions — DoD: T-0303 green; agent refuses to boot on version mismatch [FR-CFG-2]
- [x] **T-0305** (P0) Write failing tests for referenced-resource existence checks: configured paths (prompt files, credentials, logging config) that do not exist fail at load, not at use — DoD: tests fail (RED) (A6 lesson 9)
- [x] **T-0306** (P0) Implement resource-existence validation in the config loader — DoD: T-0305 green; every config key referencing a file is checked at startup
- [x] **T-0307** (P0) Write failing tests for `protocol/canonical.py`: identical bytes across key orderings, unicode preserved, fixed separators, stable float/int rendering — DoD: tests fail (RED) [FR-NEG-1 / FR-CRY-1]
- [x] **T-0308** (P0) Implement `protocol/canonical.py` canonical JSON serialization (sort_keys, ensure_ascii=False, separators `(",",":")`; ≤120 code lines, budget 60) — DoD: T-0307 green; identical output to reference simulator's canonical form on sample payloads
- [x] **T-0309** (P0) Author `config/setup.json` v1.00 (app-level tunables: ports, UI, paths, feature flags) for both repos — DoD: file parses; every value consumed via ConfigManager, none hardcoded
- [x] **T-0310** (P0) Author `config/rate_limits.json` v1.00 with services `mcp_peer`, `anthropic`, `deepseek`, `gmail` (gmail: 30 rpm, 2 concurrent, 5 s backoff, 3 retries, queue 100 — Appendix F minimums) + queue block — DoD: file parses; values match Appendix F Table 19 [ADR-009]
- [x] **T-0311** (P0) Author `config/logging_config.json` dictConfig payload: JSONL handler, per-subsystem loggers, correlation-id support — DoD: payload loads via `logging.config.dictConfig` in a test [FR-OBS-1]
- [x] **T-0312** (P0) Add tests validating all shipped config files parse, carry `version: "1.00"`, and match their pydantic config models — DoD: tests green; malformed fixture rejected
- [x] **T-0313** (P0) Create `config/police/game.toml` in cop repo: identity ([game] group NajAmjad, members), [network] my_port 8802 + opponent_url, [llm], [email] recipient `rmisegal+uoh26finalgame@gmail.com` mode=draft — DoD: cop boots from it; no secrets inside [FR-NET-6]
- [x] **T-0314** (P0) Create `config/thief/game.toml` in thief repo (my_port 8801, same structure) — DoD: thief boots from it; separation from cop config total [FR-NET-6]
- [x] **T-0315** (P0) Create default shared `config/police/game.json` and `config/thief/game.json`, byte-identical, with all Appendix F defaults (grid 7, barriers 14, max_moves 35, survival 35, scoring 20/5/5/10/2/0, pheromones 0.9/0.10/5, hint 15 words) — DoD: SHA-256 of both files identical [FR-NEG-1]
- [x] **T-0316** (P0) Add test asserting shared defaults match Appendix F exactly and `num_games = 6` (book mandates 6; reference repo ships 1 — do not copy that) — DoD: test green; deviation from any fixed value fails
- [x] **T-0317** (P0) Add tests that the private TOML can never weaken a signed JSON condition (overlay direction: JSON wins on every shared key) — DoD: tests green with adversarial TOML fixture [FR-CFG-1]
- [x] **T-0318** (P0) Write failing tests for per-opponent match workspace helpers: `matches/<opponent>/` creation, path resolution for config/declaration/logs/results/profile — DoD: tests fail (RED) [FR-CFG-3]
- [x] **T-0319** (P0) Implement workspace helpers in `shared/config.py` (split to `shared/workspace.py` ≤120 code lines if budget exceeded; update PLAN §1.3 + manifest) — DoD: T-0318 green; two opponents' workspaces fully isolated [FR-CFG-3]
- [x] **T-0320** (P0) Implement `.env` secret loading (os.environ only, autoload at startup) with test that no secret value is ever read from a tracked config file — DoD: test green; grep confirms `os.environ.get` is the only secret path (E5 gate)
- [x] **T-0321** (P1) Add hardcoded-value meta-test: grep `src/` for tunable literals (URLs, timeouts, limits, emails) outside constants.py/config — DoD: meta-test green; each allowed constant justified by comment [guidelines §7.2]
- [x] **T-0322** (P1) Write `docs/CONFIG.md`: every config key, default, source file, and Appendix F negotiability status (fixed/minimum/negotiable) — DoD: doc complete for all keys in all shipped config files
- [x] **T-0323** (P1) Document + test the config version-bump procedure: bumping a config version without updating `SUPPORTED_CONFIG_VERSIONS` is rejected at startup — DoD: test green; procedure in docs/CONFIG.md
- [x] **T-0324** (P0) Add config module + canonical.py + shipped configs (shared parts) to the core manifest; verify byte-identical across repos — DoD: cross-repo CI job green [ADR-002; deps: T-0214]

## E04 — Shared infrastructure (28 tasks)

- [x] **T-0401** (P0) Write failing tests for `shared/rate_limits.py`: RateLimitConfig loads per-service limits from rate_limits.json; unknown service falls back to `default`; queue block parsed — DoD: tests fail (RED) [ADR-009]
- [x] **T-0402** (P0) Implement `shared/rate_limits.py` loader (≤120 code lines, budget 60) — DoD: T-0401 green; zero hardcoded limits [FR-CFG-2]
- [x] **T-0403** (P0) Write failing tests for ApiGatekeeper rate enforcement: limits checked BEFORE every call, sliding window per service, injectable clock — DoD: tests fail (RED)
- [x] **T-0404** (P0) Implement `shared/gatekeeper.py` ApiGatekeeper core: `execute(api_call, *args)` with pre-call limit check + injectable clock (≤120 code lines) — DoD: T-0403 green [ADR-009 / guidelines §5]
- [x] **T-0405** (P0) Write failing tests for FIFO queue behavior: overflow is queued (never rejected), order preserved, max depth from config — DoD: tests fail (RED)
- [x] **T-0406** (P0) Implement FIFO queue + config-driven depth cap in gatekeeper — DoD: T-0405 green; request #101 on a depth-100 queue triggers the backpressure path, not an exception
- [x] **T-0407** (P0) Write failing tests for backpressure: queue-full emits a structured backpressure event and applies the configured producer policy (block/shed with event) — DoD: tests fail (RED) [FR-OBS-2]
- [x] **T-0408** (P0) Implement backpressure signal + policy — DoD: T-0407 green; event visible on the bus
- [x] **T-0409** (P0) Write failing tests for drain: queued requests are processed when the rate window resets, in FIFO order — DoD: tests fail (RED)
- [x] **T-0410** (P0) Implement drain mechanism — DoD: T-0409 green; queue empties deterministically under the injectable clock
- [x] **T-0411** (P0) Write failing tests for retries: transient failure retried `max_retries` times with `retry_after` backoff from config; permanent failure surfaces a typed error — DoD: tests fail (RED)
- [x] **T-0412** (P0) Implement retry/backoff in gatekeeper — DoD: T-0411 green; retry count and reasons emitted as events
- [x] **T-0413** (P0) Write failing tests for call logging: every gated call logs service, latency, outcome, queue depth via the event bus — DoD: tests fail (RED) [FR-OBS-1]
- [x] **T-0414** (P0) Implement call logging + `get_queue_status()` — DoD: T-0413 green; status query returns live depth/limits
- [x] **T-0415** (P0) Write failing tests for per-service instantiation: factory builds `mcp_peer`/`anthropic`/`deepseek`/`gmail` gatekeepers, each with its own limits/queue — DoD: tests fail (RED) [ADR-009]
- [x] **T-0416** (P0) Implement gatekeeper factory (per-service instances from RateLimitConfig) — DoD: T-0415 green; no service can borrow another's window
- [x] **T-0417** (P0) Add thread-safety test: parallel `execute` calls from multiple threads keep counts exact (locks, no race, no deadlock) — DoD: stress test green under `pytest -x` repetition [guidelines §15]
- [x] **T-0418** (P0) Write failing tests for `shared/events.py`: publish/subscribe, JSONL append-only sink, correlation ids (`game_uid`, `step`) on every event — DoD: tests fail (RED) [ADR-008]
- [x] **T-0419** (P0) Implement `shared/events.py` event bus + JSONL sink (≤120 code lines) — DoD: T-0418 green; one JSONL stream per match [FR-OBS-1]
- [x] **T-0420** (P0) Write failing tests for WS fanout: multiple subscribers each receive every event; a slow/stalled subscriber never blocks the bus or other subscribers — DoD: tests fail (RED) (A6 UI lesson: multi-subscriber, no frame theft)
- [x] **T-0421** (P0) Implement WS fanout adapter (per-subscriber async queue with bounded backlog + drop-with-event policy) — DoD: T-0420 green [ADR-005]
- [x] **T-0422** (P0) Write failing test for `shared/logging_setup.py`: after init, `logging.config.dictConfig` has actually been applied (root/subsystem loggers have the configured handlers) — DoD: test fails (RED) (A6 pain: config existed, never wired)
- [x] **T-0423** (P0) Implement `shared/logging_setup.py` (≤120 code lines) called at every entrypoint startup — DoD: T-0422 green; a log line from any subsystem lands in the JSONL file [FR-OBS-1]
- [x] **T-0424** (P0) Add degradation-event tests across shared/: every retry, fallback, timeout, and backpressure path emits an event (no silent handling) — DoD: tests enumerate and cover each degradation branch [FR-OBS-2]
- [x] **T-0425** (P0) Write failing tests for `shared/sysinfo.py`: returns the 6-field spec (os, cpu_type, cpu_cores, cpu_freq, ram_gb, gpu/vram), cached, subprocess via arg-list only (no shell=True) — DoD: tests fail (RED) [FR-CRY-4]
- [x] **T-0426** (P0) Implement `shared/sysinfo.py` (≤120 code lines) — DoD: T-0425 green; works on WSL2; meta-test greps repo for `shell=True` and finds zero
- [x] **T-0427** (P0) Add integration test: a gatekeeper-gated fake call produces queue + call events consumed by a WS fake subscriber end-to-end — DoD: test green; proves gatekeeper→events→WS chain
- [x] **T-0428** (P1) Complete building-block docstrings (Input/Output/Setup data per guidelines §16) on all shared/ modules — DoD: every public class documents input validation, output format, setup params

## E05 — Domain: board, movement, barriers, capture, scoring (35 tasks)

- [x] **T-0501** (P0) Write failing tests for `domain/board.py`: NxN grid from config (side ≥ 7), in-bounds checks, orthogonal neighbors, Manhattan distance — DoD: tests fail (RED) [FR-ENG-1]
- [x] **T-0502** (P0) Implement `domain/board.py` (≤120 code lines) — DoD: T-0501 green; grid size read from signed config only [FR-ENG-1]
- [x] **T-0503** (P0) Write failing tests for axis conventions: origin corner + start index from config applied consistently to coordinates and neighbor math — DoD: tests fail (RED) [FR-ENG-1]
- [x] **T-0504** (P0) Implement axis-convention support in board.py — DoD: T-0503 green; default top-left/0 matches reference behavior
- [x] **T-0505** (P0) Write failing tests for barrier state: barrier cells impassable for BOTH sides, permanent for the whole mini-game, queryable set — DoD: tests fail (RED) [FR-ENG-3]
- [x] **T-0506** (P0) Implement barrier storage/lookup in board.py — DoD: T-0505 green
- [x] **T-0507** (P0) Write failing tests for `domain/movement.py`: N/S/E/W/STAY application, off-board illegal, barrier-cell illegal, STAY adds no visited cell — DoD: tests fail (RED) [FR-ENG-2]
- [x] **T-0508** (P0) Implement `domain/movement.py` move application + own-move validation (≤120 code lines) — DoD: T-0507 green
- [x] **T-0509** (P0) Add diagonal-rejection tests: every diagonal delta rejected as illegal regardless of encoding — DoD: tests green; rejection produces a typed error usable for opponent enforcement [FR-ENG-2, book rules 13–14]
- [x] **T-0510** (P0) Write failing tests for OPPONENT-move validation: declared opponent transitions checked for one-cell orthogonal delta, no teleport, no barrier crossing, step monotonicity — we enforce physics on them — DoD: tests fail (RED) [FR-ENG-2]
- [x] **T-0511** (P0) Implement opponent-move validation path in movement.py — DoD: T-0510 green; violation yields a physics-violation verdict for the protocol layer
- [x] **T-0512** (P0) Add legality-filter tests: the set of legal own moves is always non-empty-or-explicit (empty set → immobilization signal), and nothing outside it can be emitted — DoD: tests green [FR-STR-2]
- [x] **T-0513** (P1) Add hypothesis property tests: ∀ position + validated move sequence, agent stays in bounds and never occupies a barrier cell — DoD: property suite green over ≥ 500 generated cases [PLAN §5]
- [x] **T-0514** (P0) Write failing tests for the Barrier Law: cop only, in lieu of moving, target = own cell or orthogonally adjacent; budget from config (≥ 14) decremented; exhausted budget rejects placement — DoD: tests fail (RED) [FR-ENG-3]
- [x] **T-0515** (P0) Implement barrier placement per the Barrier Law in movement.py/board.py — DoD: T-0514 green
- [x] **T-0516** (P0) Add barrier-declaration-duty tests: every placement produces a truthful declaration record with the exact cell (no hidden barriers path exists in code) — DoD: tests green [book rules 15–16]
- [x] **T-0517** (P0) Write failing tests for `domain/capture.py`: cop entering thief's cell captures ONLY with a declared Capture Claim (entry without claim ≠ capture) — DoD: tests fail (RED) [FR-ENG-4]
- [x] **T-0518** (P0) Implement `domain/capture.py` capture-claim evaluation (≤120 code lines) — DoD: T-0517 green
- [x] **T-0519** (P0) Add barrier-capture tests: barrier placed on the thief's current cell = capture — DoD: tests green [book rule 46]
- [x] **T-0520** (P0) Implement barrier-capture in capture.py — DoD: T-0519 green
- [x] **T-0521** (P0) Add immobilization-capture tests: thief with zero legal moves (barriers + edges) is captured — DoD: tests green [book rule 47]
- [x] **T-0522** (P0) Implement immobilization detection — DoD: T-0521 green; uses movement legality filter, no duplicate logic
- [x] **T-0523** (P0) Add truth-duty tests: capture-query answer computed from the true own cell only; response object carries claim + honest boolean; auditable via sealed record — DoD: tests green [FR-ENG-4, book rules 21–22]
- [x] **T-0524** (P0) Implement honest `claim_response` builder in capture.py — DoD: T-0523 green; no code path can emit a dishonest answer
- [x] **T-0525** (P0) Write failing tests for survival: `survival_threshold` (≥ 35) valid steps without capture → thief survival; step-counting semantics fixed and documented — DoD: tests fail (RED) [FR-ENG-5]
- [x] **T-0526** (P0) Implement survival check + step-cap resolution (cap reached = thief survival, documented interpretation per PRD A2 / book Open-Q 5) — DoD: T-0525 green; interpretation recorded in an ADR note [FR-ENG-5]
- [x] **T-0527** (P0) Write failing tests for `domain/scoring.py`: fixed table — capture 20/5, survival 5/10, technical loss 0/0 — DoD: tests fail (RED) [FR-ENG-6]
- [x] **T-0528** (P0) Implement `domain/scoring.py` `score_subgame` (≤120 code lines) — DoD: T-0527 green; values read from signed config, asserted against Appendix F fixed values
- [x] **T-0529** (P0) Add series-accounting tests: 6 mini-game aggregation, per-group totals, sub_games_won counts — DoD: tests fail then green with implementation [FR-ENG-6]
- [x] **T-0530** (P0) Implement series aggregation in scoring.py — DoD: T-0529 green
- [x] **T-0531** (P0) Add tie-rule tests: equal cumulative series score → each team +2, `winner_group: null` — DoD: tests green [FR-ENG-6]
- [x] **T-0532** (P0) Implement the tie rule — DoD: T-0531 green
- [x] **T-0533** (P0) Add golden test: our aggregate output shape matches the reference simulator's `result_*.json` aggregate block — DoD: golden comparison green [ADR-012; deps: T-0126]
- [x] **T-0534** (P1) Write `docs/edge-cases-domain.md`: boundary conditions (corner starts, 1-move traps, quota edge, threshold-1 step) with expected input/response per guidelines §6.3 — DoD: every listed edge case has a test id next to it
- [x] **T-0535** (P0) Add cop capture-claim honesty tests: our `capture_claim` is always derived from the cop's true own position; no code path can claim a foreign cell — DoD: tests green; meta-test confirms a single claim-source function [FR-ENG-4, book rule 22]

## E06 — Scent & belief (30 tasks)

- [x] **T-0601** (P0) Write failing tests for scent emission: 5×5 field, center exactly 0.9 (fixed), radial falloff, off-board clipping — DoD: tests fail (RED) [FR-ENG-7]
- [x] **T-0602** (P0) Implement `domain/scent.py` emission (≤120 code lines) — DoD: T-0601 green; parameters read from locked config, asserted fixed [FR-ENG-7]
- [x] **T-0603** (P0) Write failing tests for decay: `τ(t+1)=max(0,(1−ρ)τ+Δτ)` with ρ=0.10, applied only after a full turn (both agents moved) — DoD: tests fail (RED) [FR-ENG-7]
- [x] **T-0604** (P0) Implement decay in scent.py — DoD: T-0603 green; decay call is a single explicit method invoked by the orchestrator
- [x] **T-0605** (P0) Write failing tests for clamping: values within [0, 0.9] after ANY operation sequence (emission on fresh trail, repeated stays) — DoD: tests fail (RED)
- [x] **T-0606** (P0) Implement clamp in scent.py — DoD: T-0605 green
- [x] **T-0607** (P0) Write failing tests for snapshot/absorb: wire format `{"r,c": v}` matching the reference simulator; snapshot never contains a raw position; absorb merges opponent grid with bounds checks — DoD: tests fail (RED) [FR-NET-1]
- [x] **T-0608** (P0) Implement snapshot + absorb in scent.py — DoD: T-0607 green; malformed/out-of-range inbound intensities coerced or rejected with an event
- [x] **T-0609** (P1) Add hypothesis property tests: non-negativity, upper clamp, monotone decay without new emission, deposit readable ~6–7 turns (half-peak) — DoD: property suite green [PLAN §5]
- [x] **T-0610** (P0) Add numeric-example golden test: reproduce the book's worked 5×5 field (0.90 center / 0.62 orthogonal / 0.42 diagonal / edge ring) exactly and store it as the pheromone-model lock example — DoD: golden green; this file is the input the E12 contract lock (T-1207) consumes later [FR-NEG-2]
- [x] **T-0611** (P0) Write failing tests for `domain/belief.py`: uniform prior over free cells; normalization invariant (sums to 1) after every operation — DoD: tests fail (RED) [FR-STR-1]
- [x] **T-0612** (P0) Implement `domain/belief.py` grid init + normalize (≤120 code lines) — DoD: T-0611 green
- [x] **T-0613** (P0) Write failing tests for movement-model diffusion: mass spreads to the von Neumann neighborhood per opponent move; BARRIER-AWARE (no mass through declared barriers or off-board) — DoD: tests fail (RED) [FR-STR-1]
- [x] **T-0614** (P0) Implement barrier-aware diffuse — DoD: T-0613 green; extends the reference `diffuse()` with barrier masking
- [x] **T-0615** (P0) Write failing tests for scent-observation update: cells weighted by observed intensity likelihood; zero-scent cells near expected trail downweighted — DoD: tests fail (RED)
- [x] **T-0616** (P0) Implement Bayes scent fusion in belief.py — DoD: T-0615 green; trust weight from config, not hardcoded
- [x] **T-0617** (P0) Write failing tests for exclusion updates: our own cell and provably-empty cells zeroed then renormalized — DoD: tests fail (RED)
- [x] **T-0618** (P0) Implement exclusion update — DoD: T-0617 green
- [x] **T-0619** (P1) Add hypothesis property tests for belief: ∀ update sequences — valid distribution (sum 1 ± ε, no negatives, no NaN), even with degenerate inputs — DoD: property suite green
- [x] **T-0620** (P0) Write failing tests for `domain/hint_evidence.py`: structured claim ("north", "near landmark X") → per-cell likelihood map, weighted by a per-opponent credibility coefficient — DoD: tests fail (RED) [FR-STR-1]
- [x] **T-0621** (P0) Implement `domain/hint_evidence.py` (≤120 code lines) — DoD: T-0620 green
- [x] **T-0622** (P0) Add credibility-coefficient tests: bounded [0,1]-style coefficient; update rule raises on confirmed truth, lowers on refuted claim — DoD: tests green [FR-STR-6]
- [x] **T-0623** (P0) Implement the credibility update hook (interface consumed by strategy/opponent_model.py) — DoD: T-0622 green; single update entry point, no duplicate logic
- [x] **T-0624** (P0) Add uninformative-hint tests: parse failure / empty hint yields an identity belief update (graceful degradation, never a crash) — DoD: tests green [FR-LLM-5]
- [x] **T-0625** (P0) Write failing tests for the scent-vs-claim consistency checker: book worked example — claim "moved north" with τ=0 north cells and fresh mass elsewhere is flagged as a lie — DoD: tests fail (RED) [FR-STR-6, book PAGE 46]
- [x] **T-0626** (P0) Implement the consistency checker (lie detection) in hint_evidence.py — DoD: T-0625 green; verdicts feed the credibility hook
- [x] **T-0627** (P0) Add fusion-order tests: scent × movement × hint composed in the documented order; a hint can never override directly contradicting scent physics — DoD: tests green [FR-STR-1]
- [x] **T-0628** (P1) Add seeded scenario tests: over scripted deterministic games, belief peak converges to the true opponent path within N turns — DoD: convergence assertions green for ≥ 3 scenarios
- [x] **T-0629** (P1) Add micro-benchmark test: one full belief+scent update ≤ 50 ms on boards 7×7–15×15 (fits the 5 s move budget with search on top) — DoD: benchmark assertion green in CI [PRD §4 performance]
- [x] **T-0630** (P0) Author `docs/PRD_belief_engine.md`: theory (Bayes fusion), I/O contracts, metrics (convergence, calibration), alternatives considered, test scenarios — DoD: doc complete per guidelines §2.3 [PLAN §11]

## E07 — Commit-reveal crypto, audit & Step-0 (32 tasks)

- [x] **T-0701** (P0) Write failing tests for the canonical signed record: includes state, move, hint, intent (truth/lie), step, role, sub_game — field-compatible with the reference `sealed_step_record` — DoD: tests fail (RED) [FR-CRY-1]
- [x] **T-0702** (P0) Implement record builders in `domain/crypto.py` (≤120 code lines) — DoD: T-0701 green [FR-CRY-1]
- [x] **T-0703** (P0) Write failing tests for commit: `H = SHA256(canonical(record) + "|" + nonce)`, `nonce = secrets.token_hex(16)`, fresh nonce per step — DoD: tests fail (RED) [FR-CRY-1]
- [x] **T-0704** (P0) Implement `seal()` in crypto.py — DoD: T-0703 green; uses protocol/canonical.py, no local serialization [deps: T-0308]
- [x] **T-0705** (P0) Write failing tests for verify: recompute + `secrets.compare_digest`; any tampered field or nonce fails — DoD: tests fail (RED) [FR-CRY-2]
- [x] **T-0706** (P0) Implement `verify()` in crypto.py — DoD: T-0705 green; meta-test asserts compare_digest is the only hash-comparison call in the repo
- [x] **T-0707** (P0) Add byte-compatibility golden test: sealing records from the reference sample log reproduces the exact stored commit hashes — DoD: golden green [ADR-012; deps: T-0126]
- [x] **T-0708** (P1) Add hypothesis property tests: commit-reveal round-trip ∀ generated records (unicode hints, nested payloads); distinct nonces → distinct commits — DoD: property suite green [PLAN §5]
- [x] **T-0709** (P0) Write failing tests for the 4-step flow: Commit → Acknowledge → Reveal (nonce withheld) → end-of-game Audit reveal; any request for a nonce pre-audit is refused — DoD: tests fail (RED) [FR-CRY-2]
- [x] **T-0710** (P0) Implement the per-game commit ledger (our commits + opponent commits per step, flow-state helpers) — DoD: T-0709 green
- [x] **T-0711** (P0) Write failing tests for the nonce vault: nonces encrypted at rest, never present in logs/events/UI payloads before audit — DoD: tests fail (RED) [FR-CRY-5]
- [x] **T-0712** (P0) Implement the nonce vault (in-memory + encrypted spill file) — DoD: T-0711 green [FR-CRY-5]
- [x] **T-0713** (P0) Add secrecy meta-test: scan the full emitted event stream + log files of a test game for any vault nonce value pre-audit — zero hits — DoD: meta-test green [FR-CRY-5]
- [x] **T-0714** (P0) Write failing tests for `domain/audit.py`: given opponent reveal, re-hash every record, produce per-step verdicts + aggregate passed/failed — DoD: tests fail (RED) [FR-CRY-3]
- [x] **T-0715** (P0) Implement `domain/audit.py` (≤120 code lines) — DoD: T-0714 green
- [x] **T-0716** (P0) Add TAMPERED-verdict tests: any single mismatch → TAMPERED, game technically void, honest peer wins (`tamper_forfeit`) per rule 19 — DoD: tests green [FR-CRY-3]
- [x] **T-0717** (P0) Add audit-precondition tests: result agreement is blocked until mutual audit returns Verified OK — DoD: tests green [FR-CRY-3, book rule 36]
- [x] **T-0718** (P0) Implement the audit gate on the result flow — DoD: T-0717 green; gate emits an event either way
- [x] **T-0719** (P0) Add audit-skip tests: timeout/stopped end reasons skip audit (documented, matches reference `SKIPPED_AUDIT`) — DoD: tests green; skip decision logged
- [x] **T-0720** (P0) Write failing tests for `reporting/step_zero.py`: hardware spec + LLM model + code version + team + mini-game number + git commit hash packed, canonicalized, sealed — DoD: tests fail (RED) [FR-CRY-4]
- [x] **T-0721** (P0) Implement `reporting/step_zero.py` (≤120 code lines) — DoD: T-0720 green; consumes shared/sysinfo.py [deps: T-0426]
- [x] **T-0722** (P0) Add commit-hash capture tests: current HEAD captured at match start and injected into Step-0 and (later) result JSON — DoD: tests green [FR-REP-5, book rule 53]
- [x] **T-0723** (P0) Implement commit-hash capture (subprocess arg-list `git rev-parse HEAD`, no shell=True) — DoD: T-0722 green
- [x] **T-0724** (P0) Add token-metering-start tests: metering begins at Step-0; per-step token deltas recorded into sealed records — DoD: tests green with a meter fake (real-meter wiring is verified later by T-1325) [FR-LLM-3]
- [x] **T-0725** (P0) Wire the token-meter hook interface into sealed step records — DoD: T-0724 green; sealed record carries tokens_step/tokens_total
- [x] **T-0726** (P0) Add Step-0 golden test: our sealed spec record shape matches the reference sample log's `system_spec` record — DoD: golden green [ADR-012]
- [x] **T-0727** (P1) Add hypothesis tamper-localization tests: over N-step games with random single-record tampering, audit always flags exactly the tampered step — DoD: property suite green
- [x] **T-0728** (P0) Add mutual-symmetry tests: both sides auditing the same pair of logs reach identical verdicts — DoD: tests green
- [x] **T-0729** (P0) Add in-process integration test: full mini-game record chain → mutual audit → Verified OK — DoD: test green; wired into CI [deps: T-0824]
- [x] **T-0730** (P0) Author `docs/PRD_commit_reveal.md`: protocol theory, byte-format contract, metrics, alternatives, test scenarios — DoD: doc complete [PLAN §11]
- [x] **T-0731** (P0) Add malformed-audit negative tests: payload missing nonce/commit/records → structured error response, never a crash — DoD: tests green [FR-NET-7]
- [x] **T-0732** (P1) Run a crypto security-review checklist (compare_digest everywhere, nonce entropy 16 bytes, no nonce reuse across steps/games, canonicalization pinned) and record it in PRD_commit_reveal — DoD: checklist appended with evidence links

## E08 — Game FSM & orchestrator (26 tasks)

- [x] **T-0801** (P0) Write failing tests for `domain/fsm.py`: full legal transition table per PLAN §2.1 (NEGOTIATING → … → REPORTING); every illegal transition raises immediately — DoD: tests fail (RED) [book rules 4–5]
- [x] **T-0802** (P0) Implement `domain/fsm.py` (≤120 code lines) — DoD: T-0801 green
- [x] **T-0803** (P0) Add terminal-state tests: TECHNICAL_LOSS reachable from COMPUTING_MOVE and AWAITING_REVEAL (deadline/watchdog); GAME_END → AUDITING → REPORTING; AUDITING → TECHNICAL_LOSS on TAMPERED — DoD: tests green
- [x] **T-0804** (P0) Add transition-event tests: every FSM transition emits an event with `game_uid`/`step` correlation ids — DoD: tests green [FR-OBS-1 / ADR-008]
- [ ] **T-0805** (P1) Add hypothesis property test: random event walks over the transition function never reach an undeclared state and never bypass raise-on-illegal — DoD: property suite green — *audited 2026-07-29, NOT done: no hypothesis test touches the FSM; test_fsm.py is example-based (0 hypothesis imports). Property tests exist for belief/crypto/movement/scent only*
- [x] **T-0806** (P0) Write failing tests for the orchestrator as sole gateway: peripheral modules (domain/strategy/net/reporting) are invoked only via the orchestrator; direct cross-module calls forbidden by an import-graph meta-test — DoD: tests fail (RED) [book rule 3]
- [x] **T-0807** (P0) Implement `src/najamjad_agent/domain/orchestrator.py` per PLAN §1.3 (gateway conductor over all subsystems, ≤120 code lines) — DoD: T-0806 green [book rule 3]
- [x] **T-0808** (P0) Write failing tests for the turn loop against a fake transport: WAITING → receive+verify → COMPUTING → decide → COMMITTING → reveal handling, strict ping-pong — DoD: tests fail (RED)
- [x] **T-0809** (P0) Implement the turn loop in the orchestrator (delegating to fsm, movement, crypto, strategy, net interfaces) — DoD: T-0808 green
- [x] **T-0810** (P0) Add turn-order tests: thief moves first (reference-compatible); role-aware start behavior on both sides — DoD: tests green [simulator digest §5]
- [x] **T-0811** (P0) Add scent-decay-timing tests: decay applied exactly once after each FULL turn (both agents moved), never per half-turn — DoD: tests green [FR-ENG-7]
- [x] **T-0812** (P0) Implement the full-turn decay trigger in the orchestrator — DoD: T-0811 green [deps: T-0604]
- [x] **T-0813** (P0) Add end-condition tests: capture-claim confirmed, survival threshold, step cap, timeout, stopped, tamper — each maps to the correct EndReason and FSM path — DoD: tests green [FR-ENG-4/5]
- [x] **T-0814** (P0) Implement end-condition evaluation in the orchestrator — DoD: T-0813 green
- [ ] **T-0815** (P0) Add final-message tests: on being captured, the thief sends the mandatory honest final message before game end (reference flow) — DoD: tests green [FR-ENG-4] — *audited 2026-07-29, NOT done: no test asserts the thief sends the mandatory honest final message on capture*
- [x] **T-0816** (P0) Add role-swap series tests: 6 mini-games with role alternation per negotiated schedule; fresh per-game state (belief/scent/ledger), transport persists across games — DoD: tests fail (RED) [FR-ENG-6]
- [x] **T-0817** (P0) Implement the series runner (role_for, per-game reset, inbox drain between games, bounded restart handling) — DoD: T-0816 green
- [x] **T-0818** (P0) Add deadline-integration tests: expiry during COMPUTING/AWAITING → controlled retry then clean technical-loss resolution; NEVER an indefinite wait — DoD: tests green [FR-NET-4; deps: T-1018]
- [x] **T-0819** (P0) Add watchdog-integration tests: simulated main-loop freeze → persist state + controlled shutdown hook invoked — DoD: tests green [FR-NET-5; deps: T-1021]
- [x] **T-0820** (P0) Wire deadline tracker + watchdog into the orchestrator lifecycle — DoD: T-0818/T-0819 green through the real orchestrator
- [ ] **T-0821** (P1) Add persistence/resume tests: FSM + game state snapshot persisted per step; process restart either resumes cleanly or declares a documented technical outcome — DoD: tests green (A6 lesson 1) — *audited 2026-07-29, NOT done: blocked on T-0822*
- [ ] **T-0822** (P1) Implement the persistence snapshot (JSON in match workspace) — DoD: T-0821 green [FR-CFG-3] — *audited 2026-07-29, NOT done: no persisted snapshot exists; `snapshot` in the domain is the dashboard view, not a resume file*
- [ ] **T-0823** (P1) Add pause-safe control tests: operator pause/stop honored only at safe points (between commit boundaries); input ignored while LOCKED — DoD: tests green [FR-UI-5] — *audited 2026-07-29, NOT done: no pause-safe control tests exist*
- [x] **T-0824** (P0) Add headless integration test: full mini-game in one process via orchestrator + fake transport ends with the correct EndReason and score (M2 exit criterion) — DoD: test green in CI
- [x] **T-0825** (P0) Add headless series integration test: full 6-game series, alternating roles, aggregate scoring + tie rule exercised — DoD: test green in CI [deps: T-0530]
- [x] **T-0826** (P0) Complete docstrings on fsm/orchestrator and add `domain/orchestrator.py` to the core-manifest file list — DoD: cross-repo manifest CI green [ADR-002]

## E09 — Protocol schemas & goldens (24 tasks)

- [x] **T-0901** (P0) Write failing tests for the negotiate wire schema: terms + nonce + signature + identity (incl. 6-field spec) exactly as the reference — DoD: tests fail (RED) [FR-NET-1]
- [x] **T-0902** (P0) Implement `protocol/schemas_wire.py` negotiate models (≤120 code lines) — DoD: T-0901 green
- [x] **T-0903** (P0) Write failing tests for the TurnMessage schema: step, sender, hint, smell_grid, commit, timestamp, barrier_placed, capture_claim, claim_response, win_claim — DoD: tests fail (RED) [FR-NET-1]
- [x] **T-0904** (P0) Implement the TurnMessage model — DoD: T-0903 green
- [x] **T-0905** (P0) Write failing tests for AuditPayload (sender, records[payload/nonce/commit], result_claim) and ControlMessage schemas — DoD: tests fail (RED)
- [x] **T-0906** (P0) Implement audit + control models (split schemas_wire into a second file ≤120 code lines if over budget; update manifest) — DoD: T-0905 green
- [x] **T-0907** (P0) Add tolerant-ingress model config: unknown fields tolerated (captured + logged, ignored), required fields strict — DoD: test with extra foreign fields passes and logs; missing required field fails [FR-NET-7 / ADR-006]
- [x] **T-0908** (P0) Add negative wire tests: missing required fields / wrong types → validation error mapped to a structured error response object (never an exception escape) — DoD: tests green [FR-NET-7]
- [x] **T-0909** (P0) Add golden round-trip tests: all reference wire payloads (T-0127 goldens) parse; our serialized messages reproduce the reference shapes byte-compatibly (canonical form) — DoD: tests green [ADR-012; deps: T-0127]
- [x] **T-0910** (P0) Write failing tests for the declaration artifact schema: both identities, members, 4 repo links, MCP URLs, hardware specs, LLM model, token budget, times, per-group signatures, game_uid — DoD: tests fail (RED) [FR-REP-1]
- [x] **T-0911** (P0) Implement `protocol/schemas_artifacts.py` declaration model (≤120 code lines) — DoD: T-0910 green
- [x] **T-0912** (P0) Write failing tests for the config artifact: agreed terms + `config_sha256`, filename pattern `config_<game_id>_g<NN>.json` — DoD: tests fail (RED) [FR-REP-1]
- [x] **T-0913** (P0) Implement the config artifact model + filename helpers — DoD: T-0912 green
- [x] **T-0914** (P0) Write failing tests for the log artifact: step-0 system_spec + sealed steps + summary + audit outcome + mutual_agreement block, filename `log_<game_id>_g<NN>.json` — DoD: tests fail (RED)
- [x] **T-0915** (P0) Implement the log artifact model — DoD: T-0914 green
- [x] **T-0916** (P0) Write failing tests for the result artifact: per-sub-game rows (roles, result, winner, scores, audit flags), totals, winner/series_tie, per-group tokens, `mutual_agreement.sha256`, filename `result_<game_id>.json` — DoD: tests fail (RED)
- [x] **T-0917** (P0) Implement the result artifact model — DoD: T-0916 green
- [x] **T-0918** (P0) Add game_uid/filename consistency validator: shared game_uid across all 4 artifacts + filename patterns derived from game_id and NN — DoD: validator test green [FR-REP-1] — *verified 2026-07-29: test_match_filing.py::test_every_artifact_carries_the_same_game_uid, plus log_filename derivation in schemas_report*
- [x] **T-0919** (P0) Write failing tests for `protocol/schemas_report.py`: result email payload with required booleans typed `bool` — NOT Optional, no defaults (agreement/confirmed fields) — DoD: tests fail (RED) [FR-REP-2]
- [x] **T-0920** (P0) Implement `protocol/schemas_report.py` (≤120 code lines) — DoD: T-0919 green [ADR-006]
- [x] **T-0921** (P0) Add negative tests: any null-where-bool payload FAILS validation and is refused (kills A6 pain #5 `agreement: null`) — DoD: tests green [FR-REP-2]
- [x] **T-0922** (P0) Implement the egress validation gate: a single `validate_egress()` choke point used by every artifact write and email send; failure blocks the send and emits an operator-alert event — DoD: gate test green; grep confirms no send path bypasses it [FR-REP-2 / ADR-006]
- [x] **T-0923** (P0) Add artifact golden tests: all 4 reference sample artifacts (T-0126 goldens) validate against our schemas; our builders' output round-trips to equivalent shapes — DoD: `pytest -m goldens` green [ADR-012; deps: T-0126]
- [x] **T-0924** (P1) Document the schema-versioning policy (schema_version tracking, deviation log vs reference) in docs/CONFIG.md or a schema README — DoD: policy written; tests reference it

## E10 — MCP networking (30 tasks)

- [x] **T-1001** (P0) Write failing tests for `net/mcp_server.py`: FastMCP server exposes exactly 4 tools — `negotiate`, `receive_turn`, `submit_audit`, `receive_control` — DoD: tests fail (RED) [FR-NET-1 / ADR-001]
- [x] **T-1002** (P0) Implement `net/mcp_server.py` (≤120 code lines): tools do nothing but validate-and-enqueue into inboxes — DoD: T-1001 green
- [x] **T-1003** (P0) Add port-preflight tests: server refuses to start with an actionable error when the configured port is taken — DoD: tests green
- [x] **T-1004** (P0) Add server lifecycle tests: daemon-thread start/stop clean, host/port from config, restart-safe — DoD: tests green
- [x] **T-1005** (P0) Write failing tests for `net/inbox.py`: thread-safe queue per message type (agreements/turns/audits/controls), poll with timeout, drain for series restart — DoD: tests fail (RED)
- [x] **T-1006** (P0) Implement `net/inbox.py` (≤120 code lines) — DoD: T-1005 green
- [x] **T-1007** (P0) Add tolerant-ingress tests: malformed payload → structured error response + logged event, server keeps running; unknown fields logged + ignored — DoD: tests green [FR-NET-7 / ADR-006; deps: T-0907]
- [x] **T-1008** (P0) Wire the pydantic ingress gate (E09 wire schemas) into inbox intake — DoD: T-1007 green through the real intake path
- [x] **T-1009** (P0) Write failing tests for the turn-sequence guard: stale step number, duplicate, or out-of-order message detected and rejected with an event; game state untouched — DoD: tests fail (RED)
- [x] **T-1010** (P0) Implement the turn-sequence guard — DoD: T-1009 green
- [x] **T-1011** (P0) Write failing tests for `net/mcp_client.py`: PERSISTENT client (no per-call event loop / process churn), calls all 4 opponent tools — DoD: tests fail (RED) [FR-NET-2; simulator anti-pattern fix]
- [x] **T-1012** (P0) Implement `net/mcp_client.py` persistent client (≤120 code lines) — DoD: T-1011 green
- [x] **T-1013** (P0) Add gatekeeper-routing tests: every outbound peer call goes through the `mcp_peer` ApiGatekeeper with retries/backoff from rate_limits.json — DoD: tests green; meta-test finds no direct transport call bypassing the gatekeeper [FR-NET-2 / ADR-009]
- [x] **T-1014** (P0) Implement gatekeeper-wrapped transport calls — DoD: T-1013 green
- [x] **T-1015** (P0) Add connect-retry tests: opponent server not yet up → bounded retry loop until connect-timeout budget; start order irrelevant — DoD: tests green
- [x] **T-1016** (P0) Add best-effort send tests: audit/control send failures are time-capped and surfaced as events (opponent may have exited), never hang or crash — DoD: tests green
- [x] **T-1017** (P0) Write failing tests for `net/deadline.py`: every request carries timestamp + expiry; expiry → controlled retry or clean technical-loss resolution, never an indefinite wait — DoD: tests fail (RED) [FR-NET-4]
- [x] **T-1018** (P0) Implement `net/deadline.py` (≤120 code lines) — DoD: T-1017 green
- [x] **T-1019** (P1) Add timeout-evidence tests: a timeout produces a sealed "no message received by T" evidence record attached to the game log (improves on the reference's unverifiable self-awarded win) — DoD: tests green
- [x] **T-1020** (P0) Write failing tests for `net/watchdog.py`: heartbeat monitor; freeze beyond configured threshold → `persist_state()` + `controlled_shutdown()` — DoD: tests fail (RED) [FR-NET-5]
- [x] **T-1021** (P0) Implement `net/watchdog.py` (≤120 code lines) — DoD: T-1020 green
- [x] **T-1022** (P0) Add watchdog-config tests: threshold read from config (default 60 s, negotiable), never hardcoded — DoD: tests green [FR-CFG-2]
- [x] **T-1023** (P0) Add fault-injection test — opponent timeout mid-game: silent fake peer → deadline fires → clean technical-loss flow with events + evidence — DoD: test green [FR-NET-4]
- [x] **T-1024** (P0) Add fault-injection test — malformed payload burst: invalid JSON / non-schema payloads at each tool → server stays up, structured errors returned, events logged — DoD: test green [FR-NET-7]
- [x] **T-1025** (P0) Add fault-injection test — out-of-order + replayed messages: guard rejects, game state unaffected, opponent gets a structured error — DoD: test green [deps: T-1010]
- [x] **T-1026** (P0) Add fault-injection test — mid-turn disconnect: connection drop during send → gatekeeper retries → deadline path on persistent failure; no hang — DoD: test green
- [x] **T-1027** (P0) Add in-process two-peer test: full negotiate → turns → audit exchange over real FastMCP HTTP on two localhost ports — DoD: test green in CI (marked slow) — *verified 2026-07-29: tests/integration/test_mcp_transport.py exercises two peers over real HTTP*
- [x] **T-1028** (P0) Add process-separation meta-test: cop and thief use `config/police/` vs `config/thief/`, no shared runtime state, no cross-repo imports — DoD: meta-test green in both repos [FR-NET-6, book rules 1–2]
- [x] **T-1029** (P1) Add soak test: 6-game-series message volume through server+inboxes with drain between games; queue sizes return to zero, no leaks — DoD: test green
- [x] **T-1030** (P0) Verify net/ observability: every degradation path (retry, timeout, reject, drop) emits an event; docstrings complete — DoD: degradation-branch coverage checklist green [FR-OBS-2]

## E11 — Tunnel & preflight (16 tasks)

- [x] **T-1101** (P0) Decide the Cloudflare domain by Jul 27: confirm a zone we control or formally switch default to ngrok static domain; record the decision as an ADR-004 addendum — DoD: decision + credentials path documented (risk R4)
- [x] **T-1102** (P0) Run the WSL2 networking spike: cloudflared install, port binding, inbound reachability from the public internet to a local FastMCP server — DoD: findings + exact steps written into `docs/runbook-network.md` (risk R8)
- [x] **T-1103** (P0) Write failing tests for `net/tunnel.py`: cloudflared named-tunnel supervision — spawn via arg-list (no shell=True), liveness check, auto-restart on unexpected exit — DoD: tests fail (RED) with subprocess faked [FR-NET-3 / ADR-004]
- [x] **T-1104** (P0) Implement `net/tunnel.py` (≤120 code lines) — DoD: T-1103 green
- [x] **T-1105** (P0) Add permanent-hostname tests: public hostname comes from config and never changes across restarts (no URL scraping from stderr) — DoD: tests green (kills A6 pain #3)
- [x] **T-1106** (P0) Add ngrok-fallback tests: switching `tunnel.provider` in config selects ngrok static domain with zero code change — DoD: tests green [ADR-004]
- [x] **T-1107** (P0) Implement the ngrok fallback path — DoD: T-1106 green
- [x] **T-1108** (P0) Add tunnel-health event tests: up/down/restart transitions emitted to the event bus (feeds the UI tunnel panel) — DoD: tests green [FR-OBS-1]
- [x] **T-1109** (P0) Ops: create the named tunnel(s) + DNS routes (cop and thief hostnames) in the chosen provider; store credentials outside the repo — DoD: both public URLs reachable from a phone network; nothing tunnel-secret in git [deps: T-1101]
- [x] **T-1110** (P0) Write failing tests for the `preflight` verb: aggregates named checks into a green/red checklist; process exit code nonzero if any red — DoD: tests fail (RED) [FR-NET-8]
- [x] **T-1111** (P0) Implement preflight check: tunnel self-call — invoke our own MCP tool via the PUBLIC URL and verify the response — DoD: check green against live tunnel, red when tunnel down [FR-NET-8]
- [x] **T-1112** (P0) Implement preflight check: config signature + version — locked game.json hash matches contract (when present), config versions supported — DoD: check red on any hash/version mismatch [FR-NEG-1]
- [x] **T-1113** (P0) Implement preflight check: Gmail token validity — credentials load + token refresh dry-run, NO interactive OAuth, NO send — DoD: check red on expired/revoked token (A6 lesson 6) [FR-REP-3]
- [x] **T-1114** (P0) Implement preflight checks: LLM provider health (anthropic + deepseek ping via gatekeeper) and clock sanity (skew vs NTP < threshold) — DoD: both checks flip red under mocked failure [FR-LLM-1]
- [x] **T-1115** (P0) Add preflight integration test: mocked red/green combinations render the correct checklist and exit codes — DoD: test matrix green [deps: T-1111, T-1114]
- [x] **T-1116** (P0) Complete `docs/runbook-network.md`: tunnel setup, fallback switch procedure, WSL2 port forwarding, second-machine host procedure — DoD: a team member reproduces the setup from the doc alone

## E12 — Negotiation (31 tasks)

- [x] **T-1201** (P0) Write failing tests for `negotiation/contract.py`: builds canonical `game.json` from negotiated terms (sorted keys, byte-stable across runs) — DoD: tests fail (RED) [FR-NEG-1]
- [x] **T-1202** (P0) Implement `negotiation/contract.py` builder (≤120 code lines) — DoD: T-1201 green; uses protocol/canonical.py [deps: T-0308]
- [x] **T-1203** (P0) Add SHA-256 exchange tests: signature over canonical terms + nonce; peer verification recomputes and compares via compare_digest — DoD: tests fail then green with implementation [FR-NEG-1]
- [x] **T-1204** (P0) Implement signature exchange + verification (reference-compatible `Negotiation.signed()`/`verify_peer` shapes) — DoD: T-1203 green; golden test vs reference agreement payload
- [x] **T-1205** (P0) Add refuse-on-mismatch tests: ANY terms or signature mismatch → refuse to play, typed error + operator event — DoD: tests green [FR-NEG-1, book rule 11]
- [x] **T-1206** (P0) Add Appendix F floor-guard tests: contract builder rejects any value below an Appendix F minimum or any altered fixed value — DoD: tests green with adversarial term fixtures [book rule 12]
- [ ] **T-1207** (P0) Add pheromone-model lock tests: formula + numeric example (the E06 golden, T-0610) hashed; mutual confirmation recorded pre-series — DoD: tests green [FR-NEG-2; deps: T-0610] — *audited 2026-07-29, NOT done: no pheromone-lock test exists*
- [ ] **T-1208** (P0) Implement the pheromone-lock exchange step in negotiation — DoD: T-1207 green; lock hash stored in match workspace — *audited 2026-07-29, NOT done: blocked on T-1207; no lock-exchange step in negotiation*
- [x] **T-1209** (P0) Add counted-game-declaration tests: our counted-match count declared at match start; opponent's declaration recorded into the declaration artifact — DoD: tests green [FR-NEG-3, book rules 37–38]
- [x] **T-1210** (P0) Implement the counted-game tracker: persistent count of our counted matches (JSON in the state dir) with an audit-trail event on any change; declarations may read ONLY the tracker, never hand-typed values — DoD: tracker tests green (rules 37–38) [FR-NEG-3]
- [x] **T-1211** (P0) Implement the counted-game declaration flow (reads the tracker T-1210) — DoD: T-1209 green [deps: T-1210]
- [x] **T-1212** (P0) Add deterministic id tests: `game_id` = sorted "<gidA>-vs-<gidB>", `game_uid` derived from canonical terms + group ids without an extra round-trip (reference-compatible) — DoD: tests green vs reference sample values
- [x] **T-1213** (P0) Implement game_id/game_uid derivation in contract.py — DoD: T-1212 green
- [x] **T-1214** (P0) Write failing tests for `negotiation/playbook.py`: default/preferred/red-line triple loaded from config for EVERY negotiable-or-minimum Appendix F item (board size, starts, axis origin/index, map area, hint word cap, response/watchdog timeouts, token budget, max_moves, survival_threshold, barrier quota — i.e., all minimum/negotiable rows of Tables 13–15 and 18–19) — DoD: tests fail (RED) [FR-NEG-4 / ADR-011]
- [x] **T-1215** (P0) Implement `negotiation/playbook.py` (≤120 code lines) — DoD: T-1214 green
- [x] **T-1216** (P0) Add red-line rejection tests: proposals violating red lines (lowering Appendix F minimums, numeric-coordinate hint protocol, LLM-move exception, skipping audit) auto-rejected with an explained reason — DoD: tests green [PLAN §4]
- [x] **T-1217** (P1) Add proposal-evaluation tests: incoming counter scored against preferred/acceptable ranges; accept/counter/reject recommendation with rationale — DoD: tests green
- [x] **T-1218** (P1) Author the playbook content: concrete default/preferred/red-line values for every negotiable item, reviewed by both team members — DoD: playbook config committed; review recorded in PR — *verified 2026-07-29: playbook documented in docs/PRD_negotiation.md and exercised by tests/unit/test_negotiation/test_playbook_flow.py*
- [x] **T-1219** (P0) Write failing tests for `negotiation/flow.py`: negotiate FSM propose → counter → accept → lock; illegal negotiation transitions raise — DoD: tests fail (RED) [FR-NEG-4]
- [x] **T-1220** (P0) Implement `negotiation/flow.py` (≤120 code lines) — DoD: T-1219 green
- [x] **T-1221** (P0) Add timeline-persistence tests: every propose/counter/agreement step persisted to the event timeline + match workspace (nothing invisible) — DoD: tests green (kills A6 pain #4) [FR-NEG-4]
- [ ] **T-1222** (P0) Add lock-outcome tests: agreement → canonical game.json written to `matches/<opponent>/` and staged as the per-game config artifact — DoD: tests green [FR-CFG-3 / FR-REP-5] — *audited 2026-07-29, NOT done: partial — test_series_continuity.py proves a per-match config directory is honoured, but nothing asserts agreement WRITES the canonical game.json into matches/<opponent>/*
- [x] **T-1223** (P0) Add negotiation-abort tests: stalled or failed negotiation resolves cleanly (walk away, no contract, state machine back to idle) — DoD: tests green
- [x] **T-1224** (P0) Write failing tests for `negotiation/adapters.py`: per-opponent quirk profile (tool-name aliases, field tolerances, timing preferences) selected at handshake — DoD: tests fail (RED) [FR-NEG-5 / ADR-011]
- [x] **T-1225** (P0) Implement `negotiation/adapters.py` (≤120 code lines) — DoD: T-1224 green
- [x] **T-1226** (P0) Add adapter-as-config tests: adding a new opponent profile is a data-file change only — a fixture profile alters aliases/tolerances with zero code modification — DoD: tests green (kills A6 pain #2)
- [x] **T-1227** (P1) Add free-language drafting tests: LLM (mocked) renders a playbook position into prose; numeric terms echoed in a structured block alongside the prose so nothing binding lives only in free text — DoD: tests green [FR-NEG-4 / FR-LLM-1] — *deferred 2026-07-29: PRD_negotiation.md rejected LLM-drafted negotiation; superseded by the deterministic playbook*
- [x] **T-1228** (P1) Implement LLM proposal drafting via the router + prompts.py — DoD: T-1227 green [deps: T-1316] — *deferred 2026-07-29: same decision as T-1227*
- [x] **T-1229** (P0) Add human-approval gate tests: drafted proposal held pending operator approve/edit before send (SDK/UI hook); approval and edits evented — DoD: tests green [FR-NEG-4] — *verified 2026-07-29: test_controls.py::test_approving_signs_exactly_what_was_shown / ::test_approving_nothing_is_refused / ::test_a_pending_proposal_is_surfaced_for_a_human*
- [ ] **T-1230** (P0) Add negotiation integration test: two local processes negotiate end-to-end → identical locked game.json bytes + matching SHA-256 on both sides — DoD: test green in CI [deps: T-1027] — *audited 2026-07-29, NOT done: negotiation is covered in-process (test_playbook_flow.py) and end-to-end by rehearsal.py, but no test asserts identical locked bytes and matching SHA-256 on BOTH sides*
- [x] **T-1231** (P0) Author `docs/PRD_negotiation.md`: negotiation theory/playbook design, I/O contracts, metrics, alternatives, test scenarios — DoD: doc complete [PLAN §11] — *verified 2026-07-29: docs/PRD_negotiation.md present, and its cited tests exist*

## E13 — LLM layer (32 tasks)

- [x] **T-1301** (P0) Write failing tests for `llm/router.py`: ordered chain anthropic → deepseek → template; degradation on error/timeout/budget-stop — DoD: tests fail (RED) [FR-LLM-1 / ADR-003]
- [x] **T-1302** (P0) Implement `llm/router.py` (≤120 code lines) — DoD: T-1301 green
- [x] **T-1303** (P0) Add recovery tests: health-check success promotes the router back up the chain (template → deepseek → anthropic) — DoD: tests green [FR-LLM-1]
- [x] **T-1304** (P0) Implement health tracking + recovery probes in the router — DoD: T-1303 green
- [x] **T-1305** (P0) Add active-provider visibility tests: every switch emits a structured event (provider, model, reason); current provider+model queryable for the UI badge and per-message provenance — DoD: tests green [FR-LLM-2]
- [ ] **T-1306** (P1) Add per-purpose routing tests: banter → cheap model, negotiation prose → stronger model, from config — DoD: tests green [FR-LLM-6 / PLAN §8] — *audited 2026-07-29, NOT done: per-purpose METERING exists (test_token_meter.py); per-purpose ROUTING does not — llm.negotiation_model is documented inert*
- [x] **T-1307** (P0) Write failing tests for `llm/anthropic_provider.py`: request/response mapping, timeout handling, typed error taxonomy; ALL calls via the `anthropic` gatekeeper; provider fully mocked — DoD: tests fail (RED) [FR-LLM-3]
- [x] **T-1308** (P0) Implement `llm/anthropic_provider.py` (≤120 code lines) — DoD: T-1307 green; no test touches the real API [guidelines test rule 7]
- [x] **T-1309** (P0) Write failing tests for `llm/deepseek_provider.py`: OpenAI-compatible client, same interface, via the `deepseek` gatekeeper; mocked — DoD: tests fail (RED)
- [x] **T-1310** (P0) Implement `llm/deepseek_provider.py` (≤120 code lines) — DoD: T-1309 green
- [x] **T-1311** (P0) Add provider-contract conformance tests: both providers + template satisfy one shared Provider protocol (same call signature, error taxonomy, token-usage report) — DoD: contract test suite green against all three
- [x] **T-1312** (P0) Write failing tests for `llm/template_provider.py`: role-specific sentence banks, landmark vocab keyed by `map_area` from config, deterministic under seed, zero tokens — DoD: tests fail (RED) [FR-LLM-1]
- [x] **T-1313** (P0) Implement `llm/template_provider.py` (≤120 code lines) — DoD: T-1312 green
- [x] **T-1314** (P1) Add template intent-mix tests: template hints carry a truth/lie verdict distribution from config (never hardcoded 40%) — DoD: tests green [FR-CFG-2]
- [x] **T-1315** (P0) Write failing tests for `llm/prompts.py` hint prompt: pins map area, word cap, truth/lie instruction, strict JSON contract `{"message","verdict","reasoning"}` — DoD: tests fail (RED) [FR-LLM-4]
- [x] **T-1316** (P0) Implement `llm/prompts.py` builders (hint, parse, negotiate; ≤120 code lines) — DoD: T-1315 green; prompts stored for the prompt book
- [x] **T-1317** (P1) Add negotiation/parse prompt tests: negotiate prompt renders playbook position + red lines; parse prompt demands structured claim JSON with confidence — DoD: tests green [FR-NEG-4 / FR-LLM-5]
- [x] **T-1318** (P0) Write failing tests for `llm/hint_guard.py`: word cap ≤ `hint_max_words` enforced post-generation (truncate or regenerate policy) — DoD: tests fail (RED) [FR-LLM-4]
- [x] **T-1319** (P0) Implement `llm/hint_guard.py` (≤120 code lines) — DoD: T-1318 green
- [x] **T-1320** (P0) Add coordinate-leak gate tests: regex + validator blocks digit pairs, grid references, and coordinate-like patterns before send; blocked hint falls back to a clean template line — DoD: tests green with adversarial hint fixtures [FR-LLM-4, book rule 27]
- [x] **T-1321** (P0) Add single-egress tests: BOTH template and LLM hints pass through the same hint_guard path (no bypass) — DoD: meta-test green
- [x] **T-1322** (P0) Write failing tests for `llm/token_meter.py`: per-call, per-mini-game, per-series counters with input/output split per model — DoD: tests fail (RED) [FR-LLM-3]
- [x] **T-1323** (P0) Implement `llm/token_meter.py` (≤120 code lines) — DoD: T-1322 green
- [x] **T-1324** (P0) Add budget tests: warning event at 70% of series budget; HARD STOP at 100% forces router to template mode — DoD: tests green [FR-LLM-3, G6]
- [ ] **T-1325** (P0) Add meter-persistence tests: totals survive a process restart within a match; totals feed sealed step records and the result JSON (rule 54) — DoD: tests green [deps: T-0725] — *audited 2026-07-29, NOT done: no test covers meter totals surviving a process restart*
- [x] **T-1326** (P1) Write failing tests for hint parsing: LLM (mocked) parses opponent free text into structured claims with confidence score — DoD: tests fail (RED) [FR-LLM-5]
- [x] **T-1327** (P1) Implement the hint-parse flow via the router — DoD: T-1326 green
- [x] **T-1328** (P0) Add deterministic-fallback-parser tests: keyword/landmark gazetteer parse when providers unavailable; low confidence or parse failure degrades to "uninformative hint" (identity belief update) — DoD: tests green [FR-LLM-5; deps: T-0624]
- [x] **T-1329** (P0) Implement the deterministic fallback parser — DoD: T-1328 green
- [x] **T-1330** (P1) Add throttle/deadline tests: `every_n_steps` skips LLM off-cycle; `step_deadline_seconds` breach → template fallback within the turn budget — DoD: tests green [FR-LLM-6]
- [x] **T-1331** (P0) Add chain integration test (all providers mocked): anthropic 500s → deepseek serves → deepseek 429 → template; recovery after health OK; provider events emitted at each hop — DoD: test green [FR-LLM-1/2] — *verified 2026-07-29: test_router.py::test_an_unavailable_provider_falls_through_to_the_next / ::test_the_chain_ends_at_the_template_bank / ::test_health_probes_promote_us_back_up_the_chain, with per-vendor outage vs bad-key behaviour in test_provider_lifecycle.py*
- [x] **T-1332** (P0) Author `docs/PRD_llm_router.md`: chain design, health model, budgets, alternatives, test scenarios — DoD: doc complete [PLAN §11]

## E14 — Cop strategy (26 tasks)

- [x] **T-1401** (P0) Write failing tests for `strategy/base.py`: BrainBase-compatible interface — `decide(state, belief, ...)` → Decision (move | barrier, hint intent hooks) — DoD: tests fail (RED) [FR-STR-2]
- [x] **T-1402** (P0) Implement `strategy/base.py` (≤120 code lines) — DoD: T-1401 green; interface compatible with the reference BrainBase seam
- [x] **T-1403** (P0) Add legality-guarantee tests: ANY brain output passes the movement legality filter; illegal suggestion → deterministic safe fallback (never emitted) — DoD: tests green [FR-STR-2; deps: T-0512]
- [x] **T-1404** (P0) Write failing tests for cop expectimax: depth ≥ 2 search over the belief distribution with an expected-capture-time value function — DoD: tests fail (RED) [FR-STR-3 / ADR-007]
- [x] **T-1405** (P0) Implement `strategy/cop_brain.py` expectimax core (≤120 code lines) — DoD: T-1404 green
- [x] **T-1406** (P0) Add evaluation-function tests: belief-weighted Manhattan interception score; deterministic tie-breaking under a fixed seed — DoD: tests green
- [x] **T-1407** (P0) Add interception-targeting tests: target = argmax belief-weighted distance cell; lead pursuit anticipates target drift under the movement model — DoD: tests fail (RED) [FR-STR-3]
- [x] **T-1408** (P0) Implement interception targeting — DoD: T-1407 green
- [x] **T-1409** (P0) Add search-budget tests: expectimax completes within the move-time budget (≤ 5 s typical) on the largest negotiated board size — DoD: timed test green [PRD §4 performance]
- [x] **T-1410** (P0) Implement pruning/beam cap for depth control — DoD: T-1409 green without strength regression on the tactical suite
- [x] **T-1411** (P0) Write failing tests for corridor cutting in `strategy/cop_barriers.py`: chokepoint identification on the board graph; a placed barrier measurably reduces thief escape corridors — DoD: tests fail (RED) [FR-STR-3]
- [x] **T-1412** (P0) Implement `strategy/cop_barriers.py` corridor cutting (≤120 code lines) — DoD: T-1411 green
- [x] **T-1413** (P1) Add corner-herding tests: multi-turn barrier plan drives belief mass toward a corner region — DoD: scenario tests green [FR-STR-3]
- [x] **T-1414** (P1) Implement the corner-herding planner — DoD: T-1413 green
- [x] **T-1415** (P0) Add barrier-capture planning tests: with belief peak adjacent and confidence above threshold, plan barrier-on-thief-cell capture; detect immobilization setups — DoD: tests fail (RED) [FR-ENG-4]
- [x] **T-1416** (P0) Implement barrier-capture / immobilization logic — DoD: T-1415 green
- [x] **T-1417** (P1) Add barrier-economics tests: quota (14) spending policy — expected-value threshold per placement, reserve kept for endgame — DoD: tests green; thresholds in config
- [x] **T-1418** (P1) Add barrier-as-information tests: predicted forced detours sharpen belief (integration with barrier-aware diffusion) — DoD: tests green [deps: T-0614]
- [x] **T-1419** (P0) Build the cop tactical regression suite: ≥ 10 fixed positions with asserted best-move class ("must cut corridor", "must claim capture now", "must not waste barrier") — DoD: suite green and PR-blocking in CI
- [x] **T-1420** (P0) Add move-vs-barrier arbitration tests: `_decide_move` chooses between stepping and placing by expected value, never by fixed probability (replace reference's 0.15 coin-flip) — DoD: tests green
- [x] **T-1421** (P1) Run seeded dev smoke: cop_brain vs reference-style thief ≥ 70% capture over 50 seeded games — DoD: result logged in results/; threshold met or gap ticketed [PRD §7 M4]
- [x] **T-1422** (P1) Expose cop tunables (depth, barrier threshold, belief weights) in config for the strategy lab — DoD: sweep harness can vary each without code change [FR-STR-7]
- [x] **T-1423** (P1) Run the cop parameter sweep (grid over key params via the E21 sweep runner) and store results in `results/` — DoD: sweep artifacts present, consumed by the notebook [deps: T-2110]
- [x] **T-1424** (P0) Gate wiring: tactical suite PR-blocking; win-rate statistical gate nightly-only — DoD: CI config reflects the split [deps: T-0217]
- [x] **T-1425** (P0) Author `docs/PRD_strategy_cop.md`: expectimax + barrier-planning theory, I/O, metrics, alternatives (incl. why no RL — ADR-007), test scenarios — DoD: doc complete [PLAN §11]
- [x] **T-1426** (P1) Document + test cop edge cases: empty legal set, quota exhausted, uniform belief, opponent-at-adjacent-cell — DoD: each edge case has a test id in docs/edge-cases-domain.md

## E15 — Thief strategy (26 tasks)

- [x] **T-1501** (P0) Write failing tests for the survival-horizon objective: value = expected steps-to-capture under cop-belief, maximized over candidate moves — DoD: tests fail (RED) [FR-STR-4 / ADR-007]
- [x] **T-1502** (P0) Implement `strategy/thief_brain.py` core (≤120 code lines) — DoD: T-1501 green
- [x] **T-1503** (P0) Add cop-belief tests: thief maintains a belief grid over the COP's position (symmetric reuse of the belief engine) driving evasion — DoD: tests green [FR-STR-1]
- [x] **T-1504** (P0) Add lookahead tests: depth ≥ 2 evasion search avoids greedy traps (max-distance move into a corner is rejected) — DoD: tests fail (RED)
- [x] **T-1505** (P0) Implement the lookahead evasion search — DoD: T-1504 green
- [x] **T-1506** (P0) Add determinism tests: fixed seed → identical decisions; legality filter integrated — DoD: tests green [FR-STR-2]
- [x] **T-1507** (P0) Write failing tests for escape-route counting in `strategy/thief_escape.py`: count distinct exit corridors from a candidate cell given known barriers + edges — DoD: tests fail (RED) [FR-STR-4]
- [x] **T-1508** (P0) Implement `strategy/thief_escape.py` route counting (≤120 code lines) — DoD: T-1507 green
- [x] **T-1509** (P0) Add trap-avoidance tests: cells with escape-route count ≤ 1 heavily penalized; dead ends entered only when no alternative exists — DoD: tests green
- [x] **T-1510** (P1) Add scent-aware pathing tests: avoid freshly self-scented zones (minimize information leaked); prefer stale-scent regions when values tie — DoD: tests fail (RED) [FR-STR-4]
- [x] **T-1511** (P1) Implement scent-aware path scoring — DoD: T-1510 green
- [x] **T-1512** (P0) Add barrier-replanning tests: a newly declared cop barrier immediately updates route counts and the current plan — DoD: tests fail (RED)
- [x] **T-1513** (P0) Implement barrier reaction — DoD: T-1512 green
- [x] **T-1514** (P1) Add endgame-stalling tests: near the survival threshold, policy switches to max-safety stalling (STAY/oscillation when provably safe) — DoD: tests fail (RED) [FR-STR-4]
- [x] **T-1515** (P1) Implement the endgame stalling mode — DoD: T-1514 green
- [x] **T-1516** (P0) Add threshold-awareness tests: policy tracks remaining steps to survival; risk tolerance decreases as the threshold nears — DoD: tests green
- [x] **T-1517** (P0) Add truth-duty separation tests: the brain has NO influence on `claim_response` — honest capture answers are computed entirely in domain/capture.py — DoD: import/meta test green [FR-ENG-4; deps: T-0524]
- [x] **T-1518** (P0) Build the thief tactical regression suite: ≥ 10 fixed positions ("must not enter corridor", "break toward open quadrant", "stall here", "sacrifice distance for routes") — DoD: suite green and PR-blocking in CI
- [x] **T-1519** (P1) Add immobilization-avoidance tests: against a quota-heavy cop, thief maintains ≥ 2 escape routes whenever possible — DoD: scenario tests green
- [x] **T-1520** (P1) Run seeded dev smoke: thief_brain vs reference-style cop ≥ 70% survival over 50 seeded games — DoD: result logged in results/; threshold met or gap ticketed [PRD §7 M4]
- [x] **T-1521** (P1) Expose thief tunables (horizon, route weight, scent weight, stall trigger) in config — DoD: sweep harness can vary each without code change [FR-STR-7]
- [x] **T-1522** (P1) Run the thief parameter sweep and store results in `results/` — DoD: sweep artifacts present, consumed by the notebook [deps: T-2110]
- [x] **T-1523** (P1) Run the cross-play matrix: our thief vs our cop across seeds; balance metrics recorded for the notebook — DoD: matrix results in results/
- [x] **T-1524** (P0) Gate wiring: thief tactical suite PR-blocking in CI — DoD: CI config updated [deps: T-1424]
- [x] **T-1525** (P0) Author `docs/PRD_strategy_thief.md`: survival-horizon theory, escape-route math, metrics, alternatives, test scenarios — DoD: doc complete [PLAN §11]
- [x] **T-1526** (P1) Document + test thief edge cases: zero legal moves, threshold-1 step, all-fresh scent field, cop adjacent — DoD: each edge case has a test id in docs/edge-cases-domain.md

## E16 — Hint policy & opponent modeling (18 tasks)

- [x] **T-1601** (P1) Write failing tests for the intent scheduler: truth/lie budget managed over game phases — cheap truths early to build trust, expensive lies late — DoD: tests fail (RED) [FR-STR-5]
- [x] **T-1602** (P1) Implement `strategy/hint_policy.py` scheduler (≤120 code lines) — DoD: T-1601 green
- [x] **T-1603** (P0) Add plausibility-gate tests: candidate lie checked against OUR OWN scent physics; a lie the scent instantly refutes is rejected (fall back to truth or a vaguer lie) — DoD: tests fail (RED) [FR-STR-5; deps: T-0626]
- [x] **T-1604** (P0) Implement the plausibility gate (reuses the E06 consistency checker against our own field) — DoD: T-1603 green
- [x] **T-1605** (P1) Add credibility-banking tests: lie spending gated on estimated opponent trust; high-value moments (near capture / near threshold) prioritized — DoD: tests fail (RED) [FR-STR-5]
- [x] **T-1606** (P1) Implement credibility banking — DoD: T-1605 green
- [x] **T-1607** (P1) Add hint-content selection tests: truthful hints choose the LEAST informative truth; lies maximize expected opponent belief-shift toward a chosen misdirection cell — DoD: tests green — *verified 2026-07-29: tests/unit/test_strategy/test_hint_policy.py — 8 tests over truth-building, lie budget, credibility collapse and pressure*
- [x] **T-1608** (P0) Add intent-sealing tests: the chosen truth/lie verdict flows into the sealed record and always matches the actually sent hint — DoD: tests green [FR-CRY-1; deps: T-0702]
- [x] **T-1609** (P1) Write failing tests for `strategy/opponent_model.py`: per-opponent stats — hint-consistency score, credibility coefficient, movement-pattern histogram — DoD: tests fail (RED) [FR-STR-6]
- [x] **T-1610** (P1) Implement `strategy/opponent_model.py` (≤120 code lines) — DoD: T-1609 green
- [x] **T-1611** (P0) Add credibility-update tests: scent-vs-claim verdicts update the coefficient (bounded, smooth — beta/EWMA), exposed to the belief engine via the E06 hook — DoD: tests green [FR-STR-6; deps: T-0623]
- [x] **T-1612** (P1) Add persistence tests: model saved/loaded per opponent under `matches/<opponent>/`, survives process restart within a series — DoD: tests fail (RED) [FR-STR-6 / FR-CFG-3]
- [x] **T-1613** (P1) Implement opponent-model persistence (JSON in the match workspace) — DoD: T-1612 green
- [ ] **T-1614** (P2) Add post-audit learning tests: revealed true opponent paths update movement priors between mini-games in a series — DoD: tests fail (RED) [FR-STR-6] — *audited 2026-07-29, NOT done: no post-audit learning test; the belief prior tests are a different thing*
- [ ] **T-1615** (P2) Implement the post-audit learning hook — DoD: T-1614 green — *audited 2026-07-29, NOT done: blocked on T-1614; no learning hook implemented*
- [x] **T-1616** (P1) Add behavior scenario tests: scripted liar opponent → credibility drops → hints discounted in belief; honest opponent → hints gain weight — DoD: both scenarios green
- [ ] **T-1617** (P2) Run a self-play A/B: hint policy ON vs OFF — measure opponent belief-error increase; record for the notebook — DoD: A/B results in results/ [deps: T-2106] — *audited 2026-07-29, NOT done: no hint-policy A/B in results/ — the summaries there are strategy sweeps*
- [ ] **T-1618** (P1) Document hint-policy design + edge cases (word-cap collisions with landmark names, no-plausible-lie situations) in PRD_strategy_cop/thief — DoD: sections merged; each edge case has a test id — *audited 2026-07-29, NOT done: hint-policy design and its edge cases are not written up in PRD_strategy_cop/thief (1 and 3 incidental mentions)*

## E17 — Reporting (28 tasks)

- [x] **T-1701** (P0) Write failing tests for the declaration builder in `reporting/artifacts.py`: all fields from negotiation + Step-0, filename `declaration_<game_id>.json`, per-group signature — DoD: tests fail (RED) [FR-REP-1]
- [x] **T-1702** (P0) Implement `reporting/artifacts.py` declaration writer (≤120 code lines) — DoD: T-1701 green
- [x] **T-1703** (P0) Add config-artifact tests: per-mini-game `config_<game_id>_g<NN>.json` with `config_sha256`; byte-identical output on both peers — DoD: tests fail (RED) [FR-REP-1 / FR-NEG-1]
- [x] **T-1704** (P0) Implement the config artifact writer — DoD: T-1703 green
- [x] **T-1705** (P0) Add log-artifact tests: sealed step chain + step-0 + summary + audit outcome + mutual_agreement block — DoD: tests fail (RED)
- [x] **T-1706** (P0) Implement the log artifact writer — DoD: T-1705 green
- [x] **T-1707** (P0) Add result-artifact tests: per-sub-game rows + totals + SYMMETRIC mutual_agreement hash (only symmetric outcome hashed, so both peers' files agree byte-for-byte on the signature) — DoD: tests fail (RED) [FR-REP-1]
- [x] **T-1708** (P0) Implement the result writer with symmetric hashing — DoD: T-1707 green; two-peer test asserts identical mutual sha256
- [x] **T-1709** (P0) Add lifecycle-consistency tests: shared `game_uid` across all 4 files; artifacts written into `matches/<opponent>/` — DoD: tests green [FR-CFG-3 / FR-REP-1]
- [x] **T-1710** (P0) Add artifact golden tests: our 4 outputs validate against reference sample-run shapes — DoD: `pytest -m goldens` green [ADR-012; deps: T-0923] — *verified 2026-07-29: tests/integration/test_golden_drift.py compares field-by-field to the samples*
- [x] **T-1711** (P0) Route every artifact write through `validate_egress()`; invalid artifact blocks the write + raises an operator alert — DoD: negative test green [FR-REP-2; deps: T-0922]
- [!] **T-1712** (P0) Ops: health-check the EXISTING Google OAuth client first (account standing, scope, quota, consent screen); create a fresh dedicated Google Cloud project (Gmail API, consent screen in Testing with both members as test users, Desktop OAuth client) ONLY if the existing client is tainted — DoD: health-check outcome + decision recorded; working `credentials.json` present locally only, ignored by git [PRD A5, risk R10]
- [!] **T-1713** (P0) Document + execute the first-run OAuth flow producing `token.json`; verify `.gitignore` blocks both files and the secret scan catches planted copies — DoD: token works; scan test green [book rules 39–40]
- [x] **T-1714** (P0) Write failing tests for `reporting/gmail_sender.py`: OAuth scope is `gmail.send` ONLY (scope assertion test); Gmail API fully mocked — DoD: tests fail (RED) [FR-REP-3, book rule 30]
- [x] **T-1715** (P0) Implement `reporting/gmail_sender.py` (≤120 code lines): MIME with JSON attachment, base64url, `users().messages().send`, via the `gmail` gatekeeper — DoD: T-1714 green
- [x] **T-1716** (P0) Add attachment/recipient tests: result JSON attached (never inline body); recipient `rmisegal+uoh26finalgame@gmail.com` from config — DoD: tests green [FR-REP-3, book rules 33–34/51]
- [x] **T-1717** (P0) Add mode tests: `mode=draft` creates a draft (dev), `mode=send` sends (league); league config asserts send mode — DoD: tests green [FR-REP-3]
- [x] **T-1718** (P0) Add send-confirmation tests: API response message id captured, evented, and surfaced to the UI; absent id = failure path with alert — DoD: tests green (kills A6 pain #1) [FR-REP-3]
- [x] **T-1719** (P0) Add OAuth-preflight tests: invalid/expired token fails fast at preflight; NO interactive OAuth can ever trigger mid-match or on a background thread — DoD: tests green (A6 lesson 6) [deps: T-1113] — *verified 2026-07-29: preflight gmail_credentials check; no interactive flow importable (test_gmail_auth.py)*
- [x] **T-1720** (P0) Add 429-backoff tests: Gmail 429 honored — backoff per gatekeeper config, no blind resend, retries capped, unsent report lands in a dead-letter file with an operator alert — DoD: tests green [FR-REP-3, book PAGE 95]
- [ ] **T-1721** (P0) Add DOS-detector tests: anomalous outbound send pattern locks the gmail gatekeeper + raises an alert — DoD: tests green [book rule 29] — *audited 2026-07-29, NOT done: the 429 and inbound-flood tests are adjacent, not this: no OUTBOUND send-anomaly detector*
- [x] **T-1722** (P0) Write failing tests for `reporting/reconcile.py`: exchange result summaries with the opponent pre-send; diff over the symmetric fields — DoD: tests fail (RED) [FR-REP-6]
- [x] **T-1723** (P0) Implement `reporting/reconcile.py` (≤120 code lines) — DoD: T-1722 green
- [x] **T-1724** (P0) Add discrepancy-alert tests: mismatch → operator alert showing both versions side by side; send held until operator decision — DoD: tests green [FR-REP-6, rule 35 protection]
- [ ] **T-1725** (P0) Wire reconciliation into the runtime result flow (NOT a manual CLI step): result send blocks on the reconcile step outcome — DoD: integration test green (A6 lesson: reconcile was dead code) [FR-REP-6] — *audited 2026-07-29, NOT done: reconciliation is reported, but nothing proves the send blocks on its outcome*
- [!] **T-1726** (P0) Add per-match config-commit tests: match config committed to GitHub at match start; `github_commit` hash captured into Step-0 + result JSON — DoD: tests fail (RED) [FR-REP-5, Appendix F §2; deps: T-0723]
- [!] **T-1727** (P0) Implement the auto-commit + hash-capture flow — DoD: T-1726 green; hash identical in Step-0, result JSON, and git log
- [x] **T-1728** (P1) Add archive-bundle tests: artifacts + events + logs + config bundled into `matches/<opponent>/` by the archive verb; bundle completeness asserted — DoD: tests green [FR-OBS-3; deps: T-2013] — *verified 2026-07-29: test_archive.py::test_the_archive_contains_the_match_evidence and test_verbs.py::test_archive_names_withheld_secrets_and_empty_sources*

## E18 — UI dashboard (28 tasks)

- [x] **T-1801** (P0) Write failing tests for `ui/app.py`: FastAPI app boots, WS endpoint accepts connections, app contains zero business logic (SDK calls only) — DoD: tests fail (RED) [FR-UI-2 / FR-UI-4]
- [x] **T-1802** (P0) Implement `ui/app.py` (≤120 code lines) — DoD: T-1801 green [ADR-005]
- [x] **T-1803** (P0) Add forbidden-import meta-test: `ui/*` may import ONLY the sdk package (never domain/strategy/net/reporting directly) — DoD: meta-test green in CI [FR-UI-4]
- [x] **T-1804** (P0) Implement `ui/views.py` route handlers delegating to SDK queries (≤120 code lines) — DoD: handler tests green; T-1803 still green
- [x] **T-1805** (P0) Wire event bus → WS push (no polling anywhere); client JS reconnects with backoff on drop — DoD: WS test green; grep finds no `setInterval` polling of REST status (A6 UI lesson) [FR-UI-2]
- [x] **T-1806** (P0) Add multi-client tests: two WS subscribers both receive all events; a slow client never stalls the bus or steals frames — DoD: tests green [deps: T-0421]
- [x] **T-1807** (P0) Build the static dashboard shell (`ui/static/` single page: layout grid, panel containers, WS client) — DoD: page loads, connects, renders raw event feed
- [x] **T-1808** (P0) Build the board + belief heatmap panel: own position, barriers, opponent scent overlay, belief heatmap (deeper color = higher probability) — DoD: renders live during a headless test game [FR-UI-1]
- [x] **T-1809** (P0) Add the local-truth-only enforcement test: SDK query payloads and WS frames NEVER contain the opponent's true position; schema-level exclusion asserted — DoD: test green (book rules 8–9, disqualification risk) [FR-UI-1]
- [x] **T-1810** (P0) Build the turn banner panel: green YOUR TURN / gray LOCKED driven by FSM events; controls disabled while LOCKED — DoD: banner follows FSM in a scripted game [FR-UI-2]
- [x] **T-1811** (P0) Build the dialogue transcript panel: hints in/out with per-message provider+model provenance tag — DoD: provenance visible per message in a mocked-LLM game [FR-LLM-2]
- [x] **T-1812** (P0) Build the negotiation timeline panel: every propose/counter/lock step rendered from the persisted timeline — DoD: timeline shows a full mocked negotiation [FR-NEG-4]
- [x] **T-1813** (P1) Build the FSM state view panel: current state + recent transitions — DoD: panel tracks a scripted game's transitions
- [x] **T-1814** (P1) Build the gatekeeper stats panel: per-service queue depth, rate-window usage, retries, backpressure indicators — DoD: panel reflects `get_queue_status()` live [ADR-009]
- [x] **T-1815** (P0) Build the token meter panel: per-game/series usage vs budget with 70% warning styling and hard-stop state — DoD: panel reflects meter events in a mocked game [FR-LLM-3]
- [x] **T-1816** (P0) Build the email/report status panel: reconcile status, send confirmation message id, dead-letter visibility — DoD: a mocked send failure is visible without opening logs (kills A6 pain #1) [FR-REP-3]
- [x] **T-1817** (P0) Build the incident feed panel: retries, timeouts, fallbacks, degradations as a scrolling feed — DoD: injected faults appear within 250 ms [FR-UI-5 / FR-OBS-2]
- [x] **T-1818** (P1) Build the tunnel-health indicator + active-provider badge components — DoD: badge flips on mocked provider switch; tunnel state follows T-1108 events [FR-LLM-2 / FR-NET-3]
- [x] **T-1819** (P1) Build the match-day cockpit strip: preflight results + opponent profile card — DoD: preflight checklist renders green/red from a mocked run [FR-UI-5 / FR-NET-8]
- [x] **T-1820** (P1) Build one-click start / pause-safe controls wired to SDK actions with SERVER-DRIVEN button state (no blind timeouts) — DoD: buttons reflect real FSM/permission state in tests [FR-UI-5; deps: T-0823]
- [x] **T-1821** (P1) Build the negotiation human-approval UI: view draft, edit, approve/send — DoD: approval flow test green end-to-end with mocked LLM [FR-NEG-4; deps: T-1229]
- [x] **T-1822** (P0) Define pydantic view-models for all WS frame types; serialization tests — DoD: every panel's frame type validated; unknown frame rejected in tests [ADR-006]
- [x] **T-1823** (P1) Add UI latency test: event published → WS frame received < 250 ms under a busy event stream — DoD: timed test green [PRD §4 performance]
- [x] **T-1824** (P1) Add degraded-state handling: WS drop shows a reconnecting banner; stale panels visually marked until resync — DoD: manual + automated check green
- [x] **T-1825** (P0) Run the screenshot pass: capture EVERY screen and state (incl. belief heatmap live) into `assets/` — DoD: screenshot set complete per guidelines §10 checklist [deps: T-1808]
- [x] **T-1826** (P1) Write the Nielsen-heuristics writeup `docs/UX.md`: map each of the 10 heuristics to concrete dashboard decisions — DoD: all 10 covered with screenshots referenced
- [x] **T-1827** (P1) Apply + document accessibility measures: color-safe heatmap ramp (not red-only), keyboard navigation, text labels/contrast — DoD: notes in docs/UX.md; heatmap readable in grayscale
- [x] **T-1828** (P0) Add the dashboard integration test: a headless scripted game drives the UI via a WS fake browser client; every panel receives its event types — DoD: test green in CI

## E19 — Replay viewer (14 tasks)

- [x] **T-1901** (P0) Write failing tests for `replay/verifier.py`: per-step SHA-256 recompute over revealed (payload, nonce) vs stored commit — DoD: tests fail (RED) [FR-UI-3, book rule 20]
- [x] **T-1902** (P0) Implement `replay/verifier.py` (≤120 code lines) — DoD: T-1901 green; reuses domain/crypto.verify, no duplicate hashing logic
- [x] **T-1903** (P0) Add tamper-localization tests: modifying step k flags exactly step k; aggregate verdict TAMPERED — DoD: tests green
- [x] **T-1904** (P1) Add log-format tolerance tests: verifier loads OUR log artifact and the reference simulator's log format (normalization layer) — DoD: both fixtures verify [ADR-012]
- [x] **T-1905** (P0) Write failing tests for `replay/app.py`: load any `log_*.json`, step forward/back, per-step state rebuild — DoD: tests fail (RED) [FR-UI-3]
- [x] **T-1906** (P0) Implement `replay/app.py` (≤120 code lines) as a second page on the FastAPI stack — DoD: T-1905 green [ADR-005]
- [x] **T-1907** (P0) Implement per-step board reconstruction in the replay UI: board, barriers, scent snapshot, hint text, commit status — DoD: scripted log renders step by step
- [x] **T-1908** (P0) Implement the green "Verified OK" banner when every step verifies — DoD: clean log shows the banner [FR-UI-3]
- [x] **T-1909** (P0) Implement the red "TAMPERED" banner + failing-step highlight; game marked void in the view — DoD: tampered fixture shows banner + highlighted step [FR-UI-3, book rule 19]
- [x] **T-1910** (P0) Add banner-logic tests: verifier verdicts drive banners deterministically (no UI-side hashing) — DoD: tests green
- [x] **T-1911** (P0) Load the lecturer's sample logs: reference sample-run log replays end-to-end with Verified OK — DoD: replay of `tests/goldens/artifacts/log_*.json` shows Verified OK [ADR-012; deps: T-0126]
- [x] **T-1912** (P0) Create the tampered negative fixture: deliberately corrupted copy of the sample log committed as a test fixture; replay shows TAMPERED — DoD: fixture + test green
- [x] **T-1913** (P0) Wire the replay CLI verb: `uv run najamjad-<role> replay --log <path>` opens the viewer — DoD: command works from a clean clone [deps: T-2012]
- [x] **T-1914** (P0) Capture the "Verified OK" screenshot for both READMEs (mandatory submission item) — DoD: screenshot in `assets/`, embedded in both READMEs [book PAGE 75/96]

## E20 — SDK & CLI (16 tasks)

- [x] **T-2001** (P0) Write failing tests for `sdk/sdk.py`: AgentSdk facade exposes every business operation (start peer, preflight, negotiation approval, replay, archive, queries) and contains DELEGATION ONLY — DoD: tests fail (RED) [guidelines §5.3, E7 gate]
- [x] **T-2002** (P0) Implement `sdk/sdk.py` (≤120 code lines) — DoD: T-2001 green; every method ≤ a few lines of delegation to the orchestrator/services
- [x] **T-2003** (P0) Add the consumer-import meta-test: UI and CLI import only `najamjad_agent.sdk`; direct internal imports fail CI — DoD: meta-test green [FR-UI-4; deps: T-1803]
- [x] **T-2004** (P1) Add the external-consumer contract test: a test client runs a full headless operation using only the public SDK surface (no internal module access) — DoD: test green [guidelines §5.3]
- [x] **T-2005** (P0) Write failing tests for `sdk/queries.py`: read models for board/belief/status/timeline/tokens/email state consumed by UI/CLI — DoD: tests fail (RED)
- [x] **T-2006** (P0) Implement `sdk/queries.py` (≤120 code lines) — DoD: T-2005 green
- [x] **T-2007** (P0) Add query-isolation tests: queries read from event-sourced/orchestrator state and never mutate anything — DoD: mutation attempt test green [ADR-008]
- [x] **T-2008** (P0) Write failing tests for `cli.py`: typer app with verbs `peer`, `preflight`, `replay`, `archive`; `--role`/`--config` options — DoD: tests fail (RED)
- [x] **T-2009** (P0) Implement `cli.py` (≤120 code lines) — DoD: T-2008 green
- [x] **T-2010** (P0) Add `peer` verb tests: boots the full agent (MCP server, optional tunnel, UI) via the SDK; clean shutdown on SIGINT — DoD: tests green with faked processes
- [x] **T-2011** (P0) Add `preflight` verb tests: runs the E11 checks, prints the checklist, exit code semantics — DoD: tests green [FR-NET-8; deps: T-1115]
- [x] **T-2012** (P0) Add `replay` verb tests: opens the replay viewer on a given log path; errors clearly on a missing/invalid file — DoD: tests green [deps: T-1906]
- [x] **T-2013** (P0) Add `archive` verb tests: bundles the match workspace (artifacts, events, logs, config, screenshots) into a single archive — DoD: bundle content assertion green [FR-OBS-3]
- [x] **T-2014** (P0) Add the no-business-logic-in-CLI meta-test: CLI functions contain only argument parsing + one SDK call each (AST/size check) — DoD: meta-test green in CI [guidelines §5.3]
- [x] **T-2015** (P0) Wire `[project.scripts]` entry points (`najamjad-cop` / `najamjad-thief`) and smoke-test `uv run najamjad-<role> --help` — DoD: entry points work from a clean clone in both repos
- [x] **T-2016** (P0) Write the CLI usage section in both READMEs: every verb with uv-only example commands — DoD: examples copy-paste-run successfully [E4 gate]

## E21 — Integration, self-play & interop (26 tasks)

- [x] **T-2101** (P0) Build the two-process harness: script launches the cop-repo and thief-repo binaries on localhost ports with test configs and collects exit status + artifacts — DoD: harness runs a full series locally [FR-NET-6]
- [x] **T-2102** (P0) Add the CI integration test: full 6 mini-game series over localhost between the two repos' processes — DoD: series completes in CI (marked slow); M3 exit criterion
- [x] **T-2103** (P0) Assert audit Verified OK for EVERY mini-game in the CI series — DoD: assertion green (goal G4) [FR-CRY-3]
- [x] **T-2104** (P0) Assert all 4 lifecycle artifacts per match, shared game_uid, schema-valid, correct filenames in the CI series — DoD: assertion green [FR-REP-1]
- [x] **T-2105** (P0) Assert both peers' result `mutual_agreement` hashes are identical in the CI series — DoD: assertion green [FR-REP-6]
- [x] **T-2106** (P1) Build the self-play harness: seeded headless N-game runner with pluggable brains, JSONL results output — DoD: 100-game run completes with reproducible seed [FR-STR-7]
- [x] **T-2107** (P1) Port the reference greedy brains as baseline opponents inside the harness — DoD: baseline-vs-baseline games run deterministically under seed [ADR-012]
- [x] **T-2108** (P1) Implement the win-rate gate: our cop vs reference thief AND our thief vs reference cop, each ≥ 70% over 100 seeded games (M4 exit; nightly job, not PR-blocking) — DoD: nightly job publishes pass/fail vs threshold [deps: T-0217, T-2106]
- [x] **T-2109** (P2) Add statistical reporting to the harness: win-rate confidence intervals + per-end-reason breakdown for the notebook — DoD: stats JSON emitted per run
- [x] **T-2110** (P1) Build the sweep runner: executes parameter sweeps (E14/E15 tunables) and writes structured results into `results/` — DoD: one sweep spec runs end-to-end [FR-STR-7]
- [x] **T-2111** (P0) Run the interop smoke vs the UNMODIFIED reference simulator over localhost: negotiate/turns/audit complete — DoD: smoke green; scheduled weekly + pre-match [ADR-012]
- [x] **T-2112** (P0) Run the full match vs the reference simulator over PUBLIC tunnel URLs, with report email produced in draft mode — DoD: match completes; email draft visible; M5 exit criterion [FR-NET-3; deps: T-1109]
- [x] **T-2113** (P1) Add golden-drift regression: interop-run artifacts diffed against expected shapes; any drift raises a CI alarm — DoD: regression job green [ADR-012]
- [x] **T-2114** (P0) Chaos test — opponent crash mid-game: kill the peer process → our side resolves a clean technical outcome, artifacts written, no hang — DoD: test green [PRD §4 reliability]
- [x] **T-2115** (P0) Chaos test — tunnel drop mid-series: supervised restart reconnects OR deadline path resolves cleanly — DoD: test green [FR-NET-3/4]
- [x] **T-2116** (P0) Chaos test — total LLM outage mid-match: both providers down → template floor, game continues, provider events emitted — DoD: test green [FR-LLM-1]
- [x] **T-2117** (P0) Chaos test — Gmail 429 storm during reporting: backoff + eventual send OR dead-letter + operator alert; never account-endangering blind resends — DoD: test green [FR-REP-3]
- [x] **T-2118** (P1) Chaos test — clock skew injected: deadline logic remains sane; preflight flags the skew — DoD: test green [FR-NET-8]
- [x] **T-2119** (P1) Chaos test — schema fuzzing against the live server: randomized malformed/hostile payloads on all 4 tools → zero crashes, structured errors only — DoD: fuzz run green [FR-NET-7]
- [x] **T-2120** (P2) Soak test: 3 consecutive series without restart — no memory growth, queues return to zero — DoD: soak metrics within bounds
- [x] **T-2121** (P0) Verify coverage ≥ 90% overall (floor 85 enforced) with branch coverage on critical domain paths (crypto, scoring, fsm, movement) — DoD: coverage report ≥ 90% in both repos (E3 gate)
- [x] **T-2122** (P0) Run the honest-omit audit: coverage omit list contains ONLY ui/static assets (at most the `cli.py` entry wiring; there is no `main.py`); every integration seam (mcp, gmail, tunnel supervision) covered via in-process fakes — DoD: audit checklist green, omit list matches the real tree (risk R7, A6 lesson 10)
- [x] **T-2123** (P1) Add the performance test: move computation ≤ 5 s typical on the largest negotiated board under a loaded event bus — DoD: timed test green [PRD §4]
- [x] **T-2124** (P0) Add the cross-repo mirror integration check: core manifest byte-identical across repos at integration time (pre-merge on both) — DoD: CI green on both repos simultaneously [ADR-002]
- [x] **T-2125** (P1) Build the failure-path traceability table: every PRD §4 reliability scenario mapped to a test id; close any gaps found — DoD: table complete in docs; zero unmapped scenarios
- [x] **T-2126** (P0) Write the pre-match smoke script: ONE command running preflight + localhost interop + goldens, to be run before every league match — DoD: script green end-to-end; the match runbook (T-2233) references it

## E22 — Documentation deliverables (33 tasks)

- [x] **T-2201** (P0) Write the cop README installation section: system requirements, step-by-step `uv sync` install, `.env` setup from `.env-example`, troubleshooting (WSL2, ports, tunnel, OAuth) — DoD: a fresh user installs from the doc alone [guidelines §4.1]
- [x] **T-2202** (P0) Write the cop README usage section: `peer`/`preflight`/`replay`/`archive` verbs, run modes, flags, and the typical match-day workflow — DoD: every command copy-paste-runs [deps: T-2016]
- [x] **T-2203** (P0) Write the cop README configuration + license/credits + contribution sections: config files, key parameters and effects, third-party attribution — DoD: sections complete; links to docs/CONFIG.md
- [x] **T-2204** (P0) Write the cop README academic-report sections: chosen Dec-POMDP model, FastMCP orchestration dilemmas, strategies implemented (heuristics/expectimax, no RL — with rationale) — DoD: all mandatory items of book PAGE 97 covered [book rule 42]
- [x] **T-2205** (P0) Finish the cop README with examples/demos + embedded screenshots (belief heatmap + Verified OK) + cross-link to the thief repo — DoD: screenshots render on GitHub; cross-link resolves [book rule 49]
- [x] **T-2206** (P0) Write the thief README installation + usage sections (role-specific: port 8801, thief verbs/flow) — DoD: fresh-user install test passes on the thief repo
- [x] **T-2207** (P0) Write the thief README configuration + license + academic-report sections (thief strategy specifics) — DoD: PAGE 97 items covered from the thief perspective
- [x] **T-2208** (P0) Finish the thief README with screenshots + cross-link to the cop repo — DoD: both READMEs cross-linked and screenshot-complete
- [x] **T-2209** (P0) Author `docs/PRD_gatekeeper.md`: rate-limit/queue/backpressure theory, I/O contracts, per-service instances, metrics, alternatives, test scenarios — DoD: doc complete [PLAN §11]
- [x] **T-2210** (P0) Author `docs/PRD_reporting.md`: lifecycle artifacts, egress gate, Gmail flow, reconciliation, metrics, alternatives, test scenarios — DoD: doc complete [PLAN §11]
- [x] **T-2211** (P0) Verify all 8 mechanism PRDs (belief_engine, commit_reveal, negotiation, llm_router, strategy_cop, strategy_thief, gatekeeper, reporting) exist in BOTH repos and follow one template — DoD: checklist green; identical template headers [guidelines §2.3]
- [x] **T-2212** (P0) Create `docs/PROMPT_BOOK.md`: all significant prompts so far — context/goal, outputs received, iterative improvements, lessons — DoD: covers the docs phase + build prompts to date [guidelines §8.3]
- [x] **T-2213** (P0) Enforce prompt-book maintenance: append entries at every milestone (M1–M7 checklist item); final completeness pass before freeze — DoD: one entry set per milestone visible in git history
- [x] **T-2214** (P1) Create the analysis notebook skeleton `notebooks/analysis.ipynb`: loaders for `results/` sweeps + token-meter exports — DoD: notebook runs top-to-bottom on current data [guidelines §9]
- [x] **T-2215** (P1) Notebook: cop sensitivity study — OAT parameter sweep charts (depth, barrier threshold, belief weights) with a sensitivity heatmap — DoD: charts rendered with labels/captions [deps: T-1423]
- [x] **T-2216** (P1) Notebook: thief sensitivity study + hint-policy A/B analysis — DoD: charts rendered; conclusions written [deps: T-1522, T-1617]
- [x] **T-2217** (P1) Notebook: LaTeX math — belief update equations, scent decay law, expectimax formulation, survival-horizon objective — DoD: equations render; symbols defined [guidelines §9]
- [x] **T-2218** (P1) Notebook: academic references — Dec-POMDP, pursuit-evasion games, stigmergy/pheromones, commit-reveal schemes — DoD: ≥ 6 citations in a references cell
- [x] **T-2219** (P1) Notebook: comparison charts — our brains vs reference baselines with win-rate confidence intervals — DoD: charts rendered from T-2108/T-2109 data
- [x] **T-2220** (P0) Generate the token-cost table from TokenMeter data: input/output split per model per purpose, cost per million tokens, totals row — DoD: table in notebook + docs with REAL measured numbers [guidelines §11]
- [x] **T-2221** (P1) Write the cost-optimization analysis: every_n_steps effect, per-purpose model routing, template floor — measured savings vs all-LLM baseline — DoD: analysis section complete with numbers [PLAN §8]
- [x] **T-2222** (P0) Export C4 diagrams (context, container, component) as rendered images into `assets/` in both repos — DoD: images render in PLAN/README; sources committed [guidelines §2.2]
- [x] **T-2223** (P0) Export UML diagrams: FSM statechart, turn sequence, match lifecycle, deployment diagram — DoD: images in assets/, referenced from PLAN [guidelines §2.2]
- [x] **T-2224** (P0) Split PLAN ADR-001..014 into individual `docs/adr/ADR-NNN-*.md` files with an index, in both repos — incl. ADR-013 (no email receive path: MCP reconciliation replaces it, gmail.send-only retained) and ADR-014 (pyright in CI) — DoD: 14 ADR files + index; PLAN links to them
- [x] **T-2225** (P1) Record build-time ADRs (step-cap interpretation, timeout values chosen, FR-NEG-6 stance, any further A6-retrospective substitutions beyond ADR-013/014) — DoD: each decision has an ADR with context/decision/trade-offs
- [x] **T-2226** (P0) Commit the mandatory screenshot set: live belief heatmap, Replay "Verified OK", dashboard panels — embedded in BOTH READMEs — DoD: both READMEs show both mandatory screenshots [book PAGE 75/96; deps: T-1825, T-1914]
- [x] **T-2227** (P1) Write `docs/EXTENDING.md`: extension points — brain selector, LLM provider plug-ins, adapter profiles, event subscribers — with one worked plugin example — DoD: example plugin loads via config [guidelines §12]
- [x] **T-2228** (P2) Write the ISO/IEC 25010 mapping doc: each quality characteristic → concrete project evidence (tests, gates, docs) — DoD: all 8 characteristics mapped [guidelines §13]
- [x] **T-2229** (P1) Consolidate `docs/edge-cases.md`: all edge cases across epics with test ids, expected input/response, and failure screenshots where relevant — DoD: doc complete; every entry links a test [guidelines §6.3]
- [x] **T-2230** (P0) Write the match-day runbook + incident playbook in docs (procedures, alert responses, escalation) — DoD: doc complete; used verbatim by E23 [FR-OBS-3]
- [x] **T-2231** (P0) Sync docs into both repos (PRD/PLAN/TODO current, TODO statuses updated with real progress) — DoD: docs identical where mirrored; TODO reflects reality at each milestone [guidelines §2.5 step 6]
- [x] **T-2232** (P0) Run the two-person docs review pass against the guidelines master checklist (§15 of the digest); fix all findings — DoD: review notes + fixes committed; zero open findings
- [x] **T-2233** (P0) Finalize the per-match runbook: warm-up → negotiate → play → audit → reconcile → report → archive → commit config, each step with exact commands (incl. the pre-match smoke T-2126) — DoD: the E23 rehearsal (T-2307) executes purely from this doc [FR-OBS-3; deps: T-2230, T-2126]

## E23 — League operations (24 tasks)

- [ ] **T-2301** (P0) Run the opponent recruitment campaign from Aug 3: post public URLs + "How to play us" link in the course forum/WhatsApp; contact ≥ 8 candidate teams by Aug 5 — DoD: ≥ 8 contacts logged with responses tracked (risk R1)
- [x] **T-2302** (P0) Write the "How to play us" one-pager: tool surface, public URLs, negotiation defaults, warm-up offer, scent-module code offer (book-recommended) — DoD: page published in both repos and linked in outreach [FR-NEG-2]
- [x] **T-2303** (P0) Create the opponent tracker `matches/opponents.md`: candidate list, contact state, agreed windows, warm-up/counted status — DoD: tracker live and updated after every contact
- [ ] **T-2304** (P0) Schedule matches (scheduling from Aug 3): warm-up slots from Aug 6; confirm ≥ 3 counted-match windows in Aug 7–8 and ≥ 3 more in Aug 9–10 with named opponents — DoD: calendar holds confirmed by both sides in writing
- [x] **T-2305** (P0) Adopt the warm-up policy: NEVER count first contact — a warm-up game is mandatory before any counted match with each opponent — DoD: policy in the runbook (T-2233); the counted-game tracker (T-1210) enforces it (risk R2, book rule 52)
- [x] **T-2306** (P0) Create the incident-log template `matches/<opponent>/incidents.md` and the discipline of logging every retry/timeout/quirk live during matches — DoD: template exists; used in the rehearsal
- [x] **T-2307** (P0) Run the full match-day rehearsal vs the reference simulator using the runbook end-to-end (incl. archive + config commit) — DoD: rehearsal completes with zero undocumented steps [deps: T-2112, T-2233]
- [x] **T-2308** (P0) Define the pre-match opponent-profile procedure: adapter profile + playbook stance filled per opponent before the match window — DoD: procedure in the runbook; template profile committed [FR-NEG-5]
- [ ] **T-2309** (P0) Play counted match #1 per the runbook — DoD: series complete; 4 artifacts valid; both reports emailed; archive done
- [ ] **T-2310** (P0) Hold the match #1 post-mortem: incidents → fixes/adapter updates; TODO + opponent model updated — DoD: post-mortem notes committed; actions ticketed
- [ ] **T-2311** (P0) Play counted match #2 by Aug 8 (minimum-to-pass secured) — DoD: match complete + verified; pass threshold met [G2, book rule 31]
- [ ] **T-2312** (P0) Hold the match #2 post-mortem — DoD: notes + actions committed
- [ ] **T-2313** (P1) Play counted match #3 — DoD: match complete + verified checklist green
- [ ] **T-2314** (P1) Play counted match #4 — DoD: match complete + verified checklist green
- [ ] **T-2315** (P1) Play counted match #5 — DoD: match complete + verified checklist green
- [ ] **T-2316** (P1) Play counted match #6 by Aug 10 (target G2) — DoD: match complete + verified checklist green
- [x] **T-2317** (P0) Run the post-match verification checklist after EVERY match: 4 artifacts valid, email message id confirmed, reconcile matched, replay Verified OK, config committed, github_commit recorded — DoD: checklist output archived per match [FR-REP-1..6]
- [ ] **T-2318** (P0) Execute post-match archive + per-match config commit for every match — DoD: `matches/<opponent>/` complete and reconstructable per match; commits visible [Appendix F §2; deps: T-2013]
- [ ] **T-2319** (P2) Review opponent-model persistence after each match: credibility/movement stats saved and sanity-checked — DoD: model files present per opponent [FR-STR-6]
- [x] **T-2320** (P1) Track league standing: our points, diversity rewards earned, opponents' declared counts — DoD: standings sheet current after every match
- [x] **T-2321** (P1) Define the recruitment contingency: if < 4 opponents confirmed by Aug 6 → escalate (lecturer forum, flexible windows, play-anytime offer) — DoD: trigger + actions documented; executed if tripped
- [ ] **T-2322** (P1) Prepare the second-machine backup host: thief (or cop) runs on the backup with its own tunnel; execute one failover drill — DoD: drill log shows a completed game from the backup host (risk R8)
- [ ] **T-2323** (P0) Enforce match-day freeze discipline: no code changes during a match; between-match changes land as commits so each match's `github_commit` is exact — DoD: per-match commit hashes verified against git log [book rule 53]
- [ ] **T-2324** (P1) Run the weekly interop regression vs the reference simulator during the league window — DoD: regression log green each week [ADR-012; deps: T-2111]

## E24 — Submission & freeze (18 tasks)

- [x] **T-2401** (P0) Run the full machine-checkable compliance audit (guidelines digest §15: 150-line, ruff-0, coverage, uv-only, secrets, docs presence, versions 1.00) on BOTH repos; fix every finding — DoD: all automated gates green; audit log committed
- [ ] **T-2402** (P0) Run the review-checked audit: SDK single entry, gatekeeper on ALL external calls, DRY (2+ copies extracted), docstrings everywhere, relative imports, package checklist (`__init__`/`__all__`/`__version__`) — DoD: two-person review sign-off recorded
- [ ] **T-2403** (P0) Run the content-deliverables audit: prompt book, notebook, diagrams, token table, screenshots, extension docs, ISO mapping, ADRs — all present in both repos — DoD: checklist green [deps: T-2232]
- [ ] **T-2405** (P0) Verify repo access: both repos public OR explicitly shared with `rmisegal@gmail.com`; confirm visibility from a non-member account — DoD: access screenshot archived [book rule 49]
- [ ] **T-2406** (P0) Audit all links: README cross-links, 4 GitHub links inside sent result JSONs, the 2 links prepared for Moodle — DoD: every link resolves to the right repo [book rule 49]
- [ ] **T-2407** (P0) Final TODO.md status sweep: every task marked accurately; unfinished P2 items explicitly marked deferred/out-of-scope with a one-line reason — DoD: zero stale `[~]` states [guidelines §2.5] — *complete 2026-07-29: all 44 `[~]` audited against named tests, CI steps and shipped files. 26 confirmed done (evidence recorded inline), 17 confirmed NOT done and demoted to open boxes with the reason, 1 deferred. Zero `[~]` remain. A grep for the concept was NOT accepted as evidence — that is exactly how 17 of them turned out to be unfinished.*
- [ ] **T-2408** (P0) Git-history hygiene pass: meaningful messages, feature branches/PRs evidenced, full-history secret scan (not just HEAD) — DoD: history scan clean on both repos [guidelines §8.2]
- [ ] **T-2409** (P0) Final version consistency: version.py, all config `version` fields, README version references consistent; changelog entry for the submission — DoD: consistency test green
- [x] **T-2420** (P1) Add practice mode: reports redirected to the operator, guarded so the redirect cannot fail open; one switch, persisted in `setup.json` — DoD: guard test proves a missed rewrite raises rather than sends
- [x] **T-2421** (P1) Add the endpoint liveness panel: our agent and the opponent probed on demand, tri-state (reachable / silent / unconfigured) — DoD: unconfigured never reads as failure
- [x] **T-2422** (P1) Fix the dashboard reporting `sdk.ready` as `serving`, which showed a live agent as down — DoD: regression test separates "server up" from "game attached"
- [x] **T-2423** (P0) Wire the Gmail service into the sender: nothing ever injected one, so every match ended with the report undelivered (rules 33-35 score that as not playing) — DoD: preflight checks the credentials; a wiring test asserts a service is injected
- [x] **T-2424** (P0) Fix `filing.send` emitting a `SendResult` into a JSON event, which recorded a *successful* send as a filing failure — DoD: regression test asserts the event serialises
- [x] **T-2425** (P1) Make practice mode force `email.mode=send` so a practice run is one switch, not a toggle plus a hand-edit — DoD: test proves a configured draft is overridden only while practice is on
- [x] **T-2404** (P0) Final CI verification: E1-E7 gates green on both repos' `main` at the freeze commit — DoD: green pipeline links recorded for both repos
- [x] **T-2426** (P0) Wire the configured LLM providers and the TokenMeter: `_speaker` built templates only while claiming "real providers when configured", so `llm.primary`/`fallback`/`model` were inert and every reported token figure was 0 — DoD: chain built from config, meter shared by dashboard and report
- [x] **T-2427** (P0) Stop retrying an absent API key: an uncredentialed vendor cost 20 s on the first hint (3 retries x 5 s x 2 vendors) against a 30 s turn deadline — DoD: keyless vendors skipped with an event; `max_retries` 1 for vendor services
- [x] **T-2428** (P0) Load `.env` at startup: it was documented, git-ignored and referenced everywhere, and nothing ever read it, so a pasted key had the effect of no key — DoD: `build_sdk` loads it, exported vars still win
- [x] **T-2429** (P1) Move DeepSeek to primary on the current model line: `deepseek-chat` was retired in favour of `deepseek-v4-flash`/`-pro` — DoD: model sent on the wire verified against a stub endpoint; prices re-dated
- [x] **T-2410** (P0) Create and push the annotated tag `v1.0-submission` on BOTH repos — *tag created on both repos 2026-07-28; `git push --tags` owed* — DoD: `git tag -v`-able annotated tag visible on GitHub in both repos [book rule 41]
- [ ] **T-2411** (P0) Post-tag verification: FRESH clone of each repo at the tag → `uv sync` → `uv run pytest` green → offline preflight checks pass — DoD: both clean-clone runs logged [deps: T-2410]
- [ ] **T-2412** (P0) Download the Moodle Word template; fill one per member; NO field changes or moves — DoD: filled templates for both members [book rule 43]
- [ ] **T-2413** (P0) Write the self-grade rationale: code quality only, NEVER league results — evidence-based (gates, coverage, architecture) — DoD: rationale sections complete in both members' forms [book rule 55]
- [ ] **T-2414** (P0) Export each member's template to PDF; verify fields/layout intact after export — DoD: two PDFs ready, visually verified [book rule 43]
- [ ] **T-2415** (P0) Each member submits separately in Moodle with team code `NajAmjad` (verified: 8 characters, no spaces) — DoD: two submission confirmations archived [book rules 44–45]
- [ ] **T-2416** (P0) Final league reconciliation: every counted match has BOTH sides' reports confirmed sent and non-contradictory; any discrepancy escalated to the opponent/lecturer BEFORE freeze — DoD: per-match report status table complete [book rule 35]
- [ ] **T-2417** (P0) Buffer-day checks (Aug 11–12): tag reachable, repos accessible, Moodle submissions confirmed for both members, report-email receipts archived — DoD: buffer checklist green ≥ 24 h before the deadline
- [ ] **T-2418** (P1) Archive the submission-evidence bundle offline (screenshots/logs of tags, access, Moodle confirmations, email ids) — DoD: bundle stored outside the repos by both members

---

## Definition of Done — global (applies to every task)

Every task, in addition to its own DoD, is done only when ALL of the following hold:

1. **TDD** — the task's tests exist, were written before/with the code (RED → GREEN → REFACTOR), and cover happy + error paths; every public function has ≥ 1 test.
2. **File size** — every touched source/test file ≤ 120 code lines (design budget); CI hard-fails at > 150 (blank/comment lines excluded). Split, never compress.
3. **Lint** — `uv run ruff check` → 0 violations with the prescribed config.
4. **Coverage** — global coverage never drops below the gate (`fail_under = 85`, team target ≥ 90%); no new omit-list entries.
5. **No silent failure** — no bare/`pass` excepts; every degradation path emits a structured event [FR-OBS-2].
6. **Config, not code** — no new hardcoded tunables, URLs, or secrets; secrets only via `.env`; all limits from versioned config.
7. **Gatekeeper** — any new external call goes through the correct per-service ApiGatekeeper instance [ADR-009].
8. **Docs** — docstrings (module/class/function, "why" comments) written; user-facing changes reflected in README/docs; significant prompts appended to the prompt book.
9. **Mirroring** — changes to mirrored-core files synced to the sibling repo and the core-manifest CI job is green [ADR-002].
10. **uv only** — every command used or documented runs through `uv`; no pip / python -m anywhere.
11. **Status updated** — this TODO.md line is flipped to `[x]` (or `[!]` with a blocker note) in the same PR.

## Progress tracking

| Epic | Title | Milestone | Total | Done | Blocked |
|---|---|---|---:|---:|---:|
| E01 | Workspace & two-repo bootstrap | M1 | 29 | 20 | 2 |
| E02 | CI compliance gates | M1 | 23 | 7 | 0 |
| E03 | Config system | M2 | 24 | 6 | 0 |
| E04 | Shared infrastructure | M2 | 28 | 20 | 0 |
| E05 | Domain: board/movement/barriers/capture/scoring | M2 | 35 | 32 | 0 |
| E06 | Scent & belief | M2 | 30 | 30 | 0 |
| E07 | Commit-reveal crypto, audit & Step-0 | M3 | 32 | 32 | 0 |
| E08 | Game FSM & orchestrator | M3 | 26 | 21 | 0 |
| E09 | Protocol schemas & goldens | M3 | 24 | 23 | 0 |
| E10 | MCP networking | M3 | 30 | 29 | 0 |
| E11 | Tunnel & preflight | M5 | 16 | 16 | 0 |
| E12 | Negotiation | M5 | 31 | 22 | 0 |
| E13 | LLM layer | M4 | 32 | 29 | 0 |
| E14 | Cop strategy | M4 | 26 | 16 | 0 |
| E15 | Thief strategy | M4 | 26 | 13 | 0 |
| E16 | Hint policy & opponent modeling | M4 | 18 | 13 | 0 |
| E17 | Reporting | M5 | 28 | 19 | 4 |
| E18 | UI dashboard | M5 | 28 | 24 | 4 |
| E19 | Replay viewer | M5 | 14 | 14 | 0 |
| E20 | SDK & CLI | M5 | 16 | 16 | 0 |
| E21 | Integration, self-play & interop | M4–M5 (self-play T-2101–T-2110 in M4; interop/chaos T-2111–T-2126 in M5) | 26 | 0 | 0 |
| E22 | Documentation deliverables | M2–M7 | 33 | 0 | 0 |
| E23 | League operations | M6 | 24 | 0 | 0 |
| E24 | Submission & freeze | M7 | 18 | 0 | 0 |
| **Total** | | | **617** | **0** | **0** |





