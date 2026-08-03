# PRD — Distributed Cops-and-Thieves over P2P (Team NajAmjad)

| | |
|---|---|
| **Document version** | 1.00 |
| **Date** | 2026-07-24 |
| **Team code** | `NajAmjad` |
| **Course** | Orchestration of AI Agents — Final Project |
| **Binding sources** | Project book v3.0.0 (`police_thief_p2p.pdf`, Appendix F is the sole numeric authority) · `software_submission_guidelines-V3.pdf` |
| **Research base** | `docs/research/project-book-digest.md`, `guidelines-digest.md`, `simulator-repo-digest.md`, `assignment6-retrospective.md` |
| **Deadline** | 2026-08-12 23:59 (hard — late = not submitted) |

---

## 1. Overview & Context

### 1.1 The product

Two autonomous AI agents — a **Cop** and a **Thief** — that play a hidden-information chase
game against other students' teams over a peer-to-peer network, with **no central server and no
referee**. Each agent is simultaneously an **MCP server and MCP client** (FastMCP over HTTP,
publicly exposed through a tunnel). Integrity is enforced by a **SHA-256 Commit-Reveal**
protocol with mandatory end-of-game mutual audit; results are reported by **each team
separately** via the Gmail API as machine-readable JSON attachments.

The game is formally a **Dec-POMDP**: neither agent ever observes the true world state. Each
side estimates the opponent's position from (a) the opponent's decaying **scent field** (cannot
be faked) and (b) a **free-natural-language verbal hint that may be a lie** (the only deception
channel). The intelligence of the product is a **Bayesian belief engine + deterministic move
policy**; the LLM produces *language only* (hints, bluffs, negotiation prose), never moves.

### 1.2 The users / stakeholders

| Stakeholder | Needs |
|---|---|
| **Team NajAmjad (operators)** | One-command match-day operation; live visibility into every negotiation turn, protocol step, email, and LLM call; zero "did it even send?" moments (A6 lesson). |
| **Opposing teams (peers)** | Frictionless interop: standard MCP tool surface, tolerant parsing, clear negotiation flow, byte-identical signed `config/game.json`, stable public URL. |
| **Lecturer + AI grader** | Two compliant repos (cop, thief), correct four lifecycle JSONs, valid signed reports to `rmisegal+uoh26finalgame@gmail.com`, full guidelines compliance (machine-checked). |

### 1.3 Why we will win (differentiation)

Most teams will ship the reference simulator's near-random brains and template dialogue. Our
edge, in priority order:

1. **Belief superiority** — calibrated Bayesian tracking fusing scent likelihood, opponent
   movement model, and a *learned hint-credibility coefficient* per opponent (updated after
   every scent-vs-claim consistency check).
2. **Barrier tactics (cop)** — area-denial planning: corner herding, corridor cutting,
   capture-by-barrier; barriers as information (forced detours sharpen belief).
3. **Deception craft (thief)** — credibility-managed lying: tell cheap truths early to buy trust,
   spend it on the lie that matters; never contradict own scent physics.
4. **Negotiation as strategy** — Appendix F minimums may be *raised*: negotiate terms that fit
   our strengths (e.g., board size, start positions, hint word limit) with a prepared playbook.
5. **Operational reliability** — the league rewards agents that simply *don't lose technically*:
   state machine, deadline tracker, watchdog, retries, stable tunnel URL. A technical loss
   scores 0 for both sides; opponents will prefer playing us because we are easy and safe to
   play against — which maximizes our counted matches and diversity rewards.

---

## 2. Goals, KPIs, Acceptance Criteria

### 2.1 Product goals (league)

| # | Goal | KPI / target |
|---|---|---|
| G1 | Place in the top 10% of the league | League points per counted match ≥ series win in ≥ 70% of matches |
| G2 | Play the maximum useful number of matches | ≥ 6 counted matches vs different teams (min required: 2; cap: 10) |
| G3 | Zero technical losses caused by our side | 0 timeouts / crashes / illegal moves / hash mismatches attributable to us |
| G4 | 100% audit integrity | Every mini-game replays "Verified OK"; zero TAMPERED events |
| G5 | Reporting correctness | 100% of matches: result JSON emailed by us, schema-valid, matching opponent's report; 0 voided matches |
| G6 | Token economy | ≤ 200,000 tokens/series (negotiated cap); template fallback keeps hard floor at 0 tokens |

### 2.2 Engineering goals (grading gates — machine-checked)

| # | Gate | Target |
|---|---|---|
| E1 | File size | Every source & test file ≤ **150 code lines** (blank/comment excluded); design budget 120 |
| E2 | Lint | `uv run ruff check` → **0 violations** with the prescribed config |
| E3 | Coverage | ≥ **90%** (guideline floor 85% with `fail_under = 85`), **no omit-list laundering** of integration seams (A6 lesson) |
| E4 | Tooling | **uv only** — `pyproject.toml` + committed `uv.lock`; zero `pip`/`python -m` anywhere incl. docs & CI |
| E5 | Secrets | 0 secrets in repos; `.env-example` committed; `.gitignore` covers `.env`, `*.pem`, `*.key`, `credentials.json`, `token.json` |
| E6 | Structure | README (user-manual grade) + `docs/PRD.md`, `PLAN.md`, `TODO.md` + per-mechanism PRDs + prompt book + notebook + diagrams + ADRs in **both** repos |
| E7 | Architecture | SDK single entry point; ApiGatekeeper on **all** external calls (MCP, LLM, Gmail); rate limits from config; versioning from 1.00 |

### 2.3 Definition of Done (project level)

- [ ] Two public/lecturer-shared repos (`najamjad-cop`, `najamjad-thief`), cross-linked READMEs, annotated tag `v1.0-submission` pushed.
- [ ] ≥ 2 (target ≥ 6) full counted matches vs different teams; per-match config committed; per-match `github_commit` recorded and emailed.
- [ ] All four lifecycle JSONs produced per match (`declaration_`, `config__gNN`, `log__gNN`, `result_`), shared `game_uid`, schema-validated **before egress** (A6 lesson: no nulls where booleans belong).
- [ ] Result JSON emailed as attachment by our side for every match; delivery confirmed and visible in UI/log.
- [ ] Replay Viewer shows "Verified OK" for every logged mini-game; screenshots (belief heatmap + Verified OK) in both READMEs.
- [ ] All E1–E7 gates green in CI on both repos.

---

## 3. Functional Requirements

Requirements are numbered `FR-<area>-<n>`. Priority: **M** (must — book/guidelines mandated),
**S** (should — competitive advantage), **C** (could — stretch).

### 3.1 Game engine (`FR-ENG`)

- **FR-ENG-1 (M)** Square grid board, side ≥ 7 (from signed config); cells `(row, col)`; axis
  origin corner and start index taken from config (defaults top-left, 0).
- **FR-ENG-2 (M)** Moves: exactly one of N/S/E/W/STAY per turn; diagonal rejected as illegal.
  The engine validates *both* our own and the opponent's moves (we enforce physics on them).
- **FR-ENG-3 (M)** Barrier Law (cop only): in lieu of moving, place a barrier on own cell or an
  orthogonally adjacent cell; barriers permanent and impassable to both; budget from config
  (≥ 14); every placement truthfully declared with exact location.
- **FR-ENG-4 (M)** Capture conditions: cop enters thief's cell **and declares Capture Claim**;
  barrier placed on thief's cell; thief with zero legal moves. Thief must answer capture
  queries truthfully (cryptographically auditable).
- **FR-ENG-5 (M)** Survival: thief wins mini-game after `survival_threshold` (≥ 35) valid steps
  without capture; step cap = `max_moves`; cap-reached resolves as thief survival (documented
  interpretation per the book's academic-freedom clause).
- **FR-ENG-6 (M)** Scoring exactly per fixed table: capture 20/5, survival 5/10, tie 2 (series
  level), technical loss 0/0. Series = 6 mini-games with role alternation as negotiated.
- **FR-ENG-7 (M)** Scent physics: 5×5 emission field, center 0.9 (fixed), radial falloff,
  decay `τ(t+1)=max(0,(1−ρ)τ+Δτ)` with ρ=0.10 after each full turn; values clamped [0, 0.9].
  Implementation must exactly match the pre-series cryptographically locked model.

### 3.2 P2P protocol & networking (`FR-NET`)

- **FR-NET-1 (M)** FastMCP server exposing the interop tool surface compatible with the
  reference simulator: `negotiate`, `receive_turn`, `submit_audit`, `receive_control` (names and
  shapes per `simulator-repo-digest.md`), plus tolerant extensions negotiated per opponent.
- **FR-NET-2 (M)** MCP client calling the opponent's server; **persistent client** (not
  per-call process spawn); retries with backoff; all calls through the ApiGatekeeper.
- **FR-NET-3 (M)** Public exposure via **Cloudflare named tunnel** → a permanent hostname that
  never changes across restarts (kills A6 pain #3). Fallback: ngrok static domain. `localhost`
  only for development.
- **FR-NET-4 (M)** Deadline Tracker: every request carries timestamp + expiry; expiry ⇒
  controlled retry or clean technical-loss declaration — never an indefinite wait.
- **FR-NET-5 (M)** Watchdog: heartbeat monitor; on freeze → persist state + controlled shutdown.
- **FR-NET-6 (M)** Strict process separation: cop and thief run as separate processes from
  separate repos with `config/police/` vs `config/thief/`; zero shared runtime state.
- **FR-NET-7 (S)** Defensive ingress: every inbound payload validated against pydantic schemas;
  unknown fields tolerated (log + ignore); malformed messages answered with structured errors,
  never crashes (A6 pain #2: interop robustness).
- **FR-NET-8 (S)** Preflight command: one CLI verb verifying tunnel reachability (self-call via
  public URL), config signature, Gmail token validity, LLM provider health, clock sanity —
  green/red checklist before any match. The checklist must return the *same verdict* from the
  CLI and from the dashboard: `/api/cockpit` is an async route, so any probe that assumed no
  running event loop failed there while passing in the terminal (T-2453).
- **FR-NET-9 (M)** **One match at a time.** A handshake is accepted only at a mini-game
  boundary; mid-game it is refused **retriably**, never fatally, because the opponent's retry
  at the boundary is what resynchronises two drifted clocks. Added after a peer retrying on a
  loop opened 58 concurrent negotiations over one game state and voided a whole series
  (ADR-015).
- **FR-NET-10 (S)** The opponent's *playable surface* is verified before a match, not just its
  reachability: a tunnel edge answers while the agent behind it is dead, and an agent answers
  while exposing tools we cannot call. Preflight lists their tools and insists on all four
  mandated ones (T-2444).
- **FR-NET-11 (S)** Every failed external call records the exception's **message**, not only
  its type, and the asyncio task it ran in. Transport libraries collapse unrelated faults into
  one exception type, so a type name alone cannot tell an operator which machine to fix
  (ADR-018).

### 3.3 Negotiation & match contract (`FR-NEG`)

- **FR-NEG-1 (M)** Produce, exchange, and verify a **byte-identical** `config/game.json`
  (canonical JSON, sorted keys); SHA-256 signature exchange; refuse play on any mismatch.
- **FR-NEG-2 (M)** Pheromone model locked pre-series: formula + numeric example hashed and
  mutually confirmed; we offer our scent module code to opponents (book-recommended).
- **FR-NEG-3 (M)** Counted-game-count declaration at match start; recorded in declaration JSON.
- **FR-NEG-4 (S)** **Negotiation playbook**: prepared parameter proposals (defaults, preferred,
  red lines) for every negotiable Appendix F item; LLM-drafted, human-approved free-language
  negotiation messages; every proposal/counter/agreement step persisted and visible in the UI
  timeline (kills A6 pain #4: invisible negotiation).
- **FR-NEG-5 (S)** Interop adapter layer: per-opponent quirk profile (tool-name aliases, field
  tolerances, timing preferences) selected at handshake — adapting to a team is a config entry,
  not a code change (kills A6 pain #2).
- **FR-NEG-6 (M)** LLM-move exception requests from opponents are **politely declined** (team
  red line — our edge is deterministic strategy; see PLAN §4). The decline path is a tested
  negotiation flow, and the stance is recorded in an ADR.

### 3.4 Commit-Reveal integrity (`FR-CRY`)

- **FR-CRY-1 (M)** Per move: Commit `H=SHA256(canonical(record) ∥ nonce)` with
  `nonce = secrets.token_hex(16)`; record includes state, move, hint, intent (truth/lie), step,
  role, sub_game — byte-compatible with the reference implementation.
- **FR-CRY-2 (M)** Four-step flow: Commit → Acknowledge → Reveal (nonce withheld) → end-of-game
  Audit revealing all nonces; `secrets.compare_digest` for all comparisons.
- **FR-CRY-3 (M)** Mutual audit at every mini-game end; any mismatch ⇒ TAMPERED ⇒ technical
  void per rule 19. Audit is a precondition to result agreement.
- **FR-CRY-4 (M)** Step-0 declaration before first move: hardware spec (OS, CPU, RAM, GPU), LLM
  model, code version, team, mini-game number, **git commit hash**; signed; token metering
  starts here.
- **FR-CRY-5 (M)** Nonces stored encrypted-at-rest until audit; never logged, never in UI, never
  transmitted before audit phase.

### 3.5 Strategy & intelligence (`FR-STR`)

- **FR-STR-1 (M)** Belief engine: probability grid over opponent position; Bayes update fusing
  scent observation likelihood, opponent movement model, and hint likelihood weighted by a
  per-opponent credibility coefficient.
- **FR-STR-2 (M)** Move policy is **pure deterministic Python** (LLM never chooses moves);
  legality filter guarantees no illegal move can ever be emitted.
- **FR-STR-3 (S)** Cop brain: expectimax over belief map (depth ≥ 2) with barrier planning —
  corridor cutting, corner herding, barrier-capture; interception targeting
  argmax-belief-weighted Manhattan distance.
- **FR-STR-4 (S)** Thief brain: survival-horizon maximization — maximize expected distance and
  escape-route count under cop-belief; scent-aware pathing (avoid freshly scented zones);
  endgame stalling patterns.
- **FR-STR-5 (S)** Hint strategy: intent scheduler managing the truth/lie budget; lie
  plausibility check against own scent physics (never tell a lie the scent instantly refutes);
  credibility banking (early cheap truths, late expensive lies).
- **FR-STR-6 (S)** Opponent modeling across mini-games: hint-consistency scoring updates
  credibility priors; movement-pattern stats inform the movement model between games in a series.
- **FR-STR-7 (C)** Strategy lab: headless self-play harness (cop brain vs thief brain over
  localhost MCP) with parameter sweeps feeding the analysis notebook (sensitivity study).

### 3.6 LLM layer (`FR-LLM`)

- **FR-LLM-1 (M)** Provider router with ordered fallback: **Anthropic API (primary) → DeepSeek
  (secondary, OpenAI-compatible) → template bank (terminal, 0 tokens)**. Router degrades on
  error/timeout/budget and recovers upward on health-check success.
- **FR-LLM-2 (M)** The **active provider+model is always visible**: structured log event on
  every switch, UI badge, and per-message provenance tag in the dialogue transcript (user
  requirement; A6 pain #4 observability).
- **FR-LLM-3 (M)** All LLM calls through ApiGatekeeper (rate limits from config) with token
  metering per call, per mini-game, per series; hard budget stop → template mode.
- **FR-LLM-4 (M)** Hint constraints enforced post-generation: ≤ `hint_max_words` (default 15),
  free natural language, no coordinate leakage (regex + validator gate before send); map-area
  landmark vocabulary from config.
- **FR-LLM-5 (S)** Hint decoding: LLM-assisted parse of opponent free-text into structured
  claims with confidence; deterministic fallback parser (keyword/landmark gazetteer) when
  provider unavailable — parse failure degrades gracefully to "uninformative hint".
- **FR-LLM-6 (S)** `every_n_steps` throttle + per-purpose model choice (cheap model for banter,
  stronger model for negotiation prose) — cost/quality routing documented in token-cost table.

### 3.7 UI & Replay (`FR-UI`)

- **FR-UI-1 (M)** **Local truth only**: UI shows own position, opponent scent map, received
  hints, own belief heatmap, barriers; never the opponent's true position (rule 8–9).
- **FR-UI-2 (M)** FastAPI + WebSocket dashboard (no polling): board + belief heatmap, turn
  banner (YOUR TURN / LOCKED), dialogue transcript with per-message LLM provenance, negotiation
  timeline, protocol state machine view, gatekeeper/queue stats, email/report status, token
  meter, active-provider badge.
- **FR-UI-3 (M)** Replay Viewer: load any `log_*.json`, step forward/back, recompute SHA-256
  per step → green "Verified OK" / red "TAMPERED"; screenshot-ready.
- **FR-UI-4 (M)** Zero business logic in UI layer — all reads/actions via the SDK (guidelines).
- **FR-UI-5 (S)** Match-day cockpit: preflight results, opponent profile card, one-click start /
  pause-safe controls, incident feed (retries, timeouts, fallbacks) — "never wonder what the
  agent is doing" (A6 pains #4, #7).

### 3.8 Reporting & lifecycle artifacts (`FR-REP`)

- **FR-REP-1 (M)** Generate the four lifecycle JSONs with shared `game_uid`, filenames
  `declaration_<game_id>.json`, `config_<game_id>_g<NN>.json`, `log_<game_id>_g<NN>.json`,
  `result_<game_id>.json`, schema-compatible with the reference implementation's artifacts
  (validated against the simulator's sample-run goldens).
- **FR-REP-2 (M)** **Egress schema gate**: every artifact and email is validated against strict
  pydantic schemas (required booleans are `bool`, not nullable) before send — a schema failure
  blocks the send and raises an operator alert (kills A6 pain #5 `agreement: null`).
- **FR-REP-3 (M)** Result email: Gmail API, OAuth `gmail.send` scope only, JSON **as
  attachment** (mode=send for league; draft mode only in dev), to
  `rmisegal+uoh26finalgame@gmail.com`, through Gatekeeper (token bucket, 429-aware backoff, DOS
  detector); send confirmed via API response id, surfaced in UI + log (kills A6 pain #1).
- **FR-REP-4 (M)** Report content: both teams' identities, 4 GitHub links, MCP URLs, signed
  hardware declarations, timestamps, SHA-256-backed mutual agreement confirmations, per-game
  `github_commit`, token totals.
- **FR-REP-5 (M)** Per-match config committed to GitHub; commit hash captured automatically at
  match start and injected into Step-0 + result JSON.
- **FR-REP-6 (S)** Result reconciliation: before sending, exchange result summaries with the
  opponent and diff them; discrepancy → operator alert with both versions (rule 35 protection:
  contradictory reports void the match for both).
- **FR-REP-7 (M)** **No single artifact may suppress the others.** Each write is independent;
  a failure is recorded as `artifact.skipped` and the remaining artifacts still go out, with
  the gaps named in `artifacts.incomplete`. Rule 35 scores a missing report as not having
  played, so a partial report that names its own gaps beats a clean failure — one schema
  refusal on one mini-game's log previously filed zero artifacts for a six-game series
  (ADR-016).
- **FR-REP-8 (M)** **A mini-game that played and then died is reported as played**, with the
  steps it actually reached and `end_reason: timeout` — the verdict the opponent's watchdog
  reaches when we go silent. Reporting it as never-played while the opponent holds our sealed
  turns is a rules 33-35 contradiction that voids the match for both teams (ADR-017).
- **FR-REP-9 (S)** A match's artifacts are archived under `matches/<team>-<stamp>/` before a
  rerun. `game_id` is derived from the two group ids and the terms, so the same pair on the
  same terms produces identical filenames and a warm-up silently overwrites the counted match
  that follows it (T-2318).

### 3.9 Configuration (`FR-CFG`)

- **FR-CFG-1 (M)** Shared signed `config/game.json` (canonical, hashed) + private
  `config/game.toml` overlay semantics per the book: JSON overrides TOML; private file can
  never weaken a signed condition.
- **FR-CFG-2 (M)** All tunables from config files (versioned from 1.00, startup version
  validation); zero hardcoded values; secrets only via `.env`; `rate_limits.json` per service
  (mcp, anthropic, deepseek, gmail).
- **FR-CFG-3 (M)** Per-opponent match workspace: `matches/<opponent>/` holding negotiated
  config, declaration, logs, results, opponent profile — fully reconstructable per match.

### 3.10 Observability & ops (`FR-OBS`)

- **FR-OBS-1 (M)** Structured JSON logging (actually wired — dictConfig applied at startup, A6
  lesson), per-subsystem loggers, correlation ids (`game_uid`, step); append-only JSONL event
  stream that also feeds the UI via WebSocket.
- **FR-OBS-2 (M)** No silent excepts anywhere; every degradation emits an event (retry,
  fallback, timeout, queue backpressure).
- **FR-OBS-3 (S)** Match-day runbook + incident playbook in docs; post-match archive command
  bundling all artifacts + logs.

---

## 4. Non-Functional Requirements

| Area | Requirement |
|---|---|
| **Compliance** | All gates E1–E7 (§2.2). TDD workflow; tests mirror `src/`; every public function tested; mocks for all external deps; no tests depending on external services. |
| **Reliability** | Survive: opponent crash mid-game, tunnel drop, LLM outage, Gmail 429, malformed inbound payloads, clock skew. Every failure path has a test. Missed deadline ⇒ clean protocol resolution, never a hang. |
| **Performance** | Move computation ≤ 5 s typical (30 s response timeout); LLM step deadline ≤ 30 s with template fallback on breach; UI updates < 250 ms after event. |
| **Security** | Zero-trust toward peers: validate everything inbound; nonce secrecy until audit; least-privilege Gmail scope; secrets in `.env` only; DOS detector on outbound mail; no `shell=True` subprocess patterns (simulator anti-pattern). |
| **Cost** | Series ≤ 200k tokens; template floor = $0; token-cost table maintained per model with input/output split (guidelines §11). |
| **Portability** | Runs on user's WSL2 + a second machine/peer for real matches; no absolute paths; uv-managed env. |
| **Usability** | Nielsen heuristics documented; every screen/state screenshotted; single-command flows for: preflight, start match, replay, archive. |

---

## 5. Assumptions, Dependencies, Constraints, Out of Scope

**Assumptions**
- A1: The 4 sample lifecycle JSONs in the reference repo are the authoritative schemas (book
  attaches but does not reproduce them); goldens extracted from `reference/Game-P2P-Cop-Chase`.
- A2: Step cap reached = thief survival (documented interpretation, book §Open-Q 5).
- A3: Opponents run implementations compatible with the reference tool surface; deviations are
  absorbed by the adapter layer (FR-NEG-5) or resolved in negotiation.
- A4: The user can provide: Anthropic API key, DeepSeek API key (both procured and
  billing-verified as an explicit M1 task), and a domain on Cloudflare (or we fall back to
  ngrok static domain).
- A5: The existing Google OAuth client is used **only after a health check** (project alive,
  `gmail.send` scope grantable, sending account not the one restricted during Assignment 6);
  if tainted, a fresh dedicated Google Cloud project is created instead (PLAN R10).

**Dependencies** — FastMCP, pydantic, FastAPI+uvicorn+websockets, httpx, anthropic SDK,
openai-compatible client (DeepSeek), google-api-python-client + google-auth, cloudflared binary,
uv, ruff, pytest(+cov, +asyncio), hypothesis (property tests for crypto/scent).

**Constraints** — MCP is mandated and non-replaceable; LLM never picks moves (unless mutually
negotiated exception — off by default); free natural language only, numeric-coordinate protocol
forbidden; fixed Appendix F values immutable; minimums raisable only.

**Out of scope** — Reinforcement learning (explicitly optional in book; heuristic/expectimax
chosen — documented in ADR); A2A/ACP protocols (know-only); matchmaking service (out-of-band by
design); mobile UI; multi-language hints beyond English.

---

## 6. Risks (top-level; full register in PLAN §9)

| Risk | Mitigation |
|---|---|
| Opponent interop failures burn match days (A6 #2) | Adapter layer + warm-up games (free per book) + interop smoke test vs reference simulator in CI |
| Contradictory results void matches (rule 35) | Pre-send reconciliation diff (FR-REP-6) + shared schemas |
| LLM provider outage mid-match | 3-tier router with health-based recovery; template floor |
| Tunnel instability | Named tunnel + preflight self-call + auto-restart supervision; ngrok fallback ready |
| 150-line limit forces late refactors | Per-file line budget (120) tracked by CI gate from day 1 |
| Time: 19 days incl. league window | Opponent recruitment from Aug 3; league play Aug 6–10; descope ladder in PLAN §10 protects the critical path |

---

## 7. Milestones

| # | Milestone | Target date | Exit criterion |
|---|---|---|---|
| M0 | Docs approved (PRD/PLAN/TODO + self-review) | Jul 25 | User approves; build starts |
| M1 | Repos + toolchain + CI gates green (empty walking skeleton) | Jul 27 | Both repos: uv, ruff, pytest, coverage, line-limit CI all green |
| M2 | Core engine + scent + scoring (offline, tested) | Jul 30 | Full mini-game runs headless in one process; ≥ 90% cov |
| M3 | MCP peer loop + commit-reveal + audit over localhost | Aug 2 | 6 mini-game series completed between two local processes, audit Verified OK |
| M4 | Strategy v1 + LLM router + hints | Aug 4 | Self-play: our brains beat reference brains ≥ 70% over 100 games |
| M5 | Tunnel + negotiation + reporting + UI + replay | Aug 6 | Full match vs reference simulator over public URLs; email delivered; screenshots captured |
| M6 | League matches | Aug 6–10 (recruitment/scheduling from Aug 3) | Warm-ups from Aug 6 (after M5); ≥ 2 counted matches done by Aug 8; target ≥ 6 by Aug 10 |
| M7 | Submission freeze | Aug 11 | Tag `v1.0-submission`, READMEs, notebook, prompt book, Moodle PDF |
| — | Hard deadline | **Aug 12 23:59** | Submitted with ≥ 1 day buffer |

---

## 8. Traceability — Assignment 6 pain → requirement

| A6 pain | Killed by |
|---|---|
| #1 Passive email path failed silently | FR-REP-3 (send confirmation surfaced), FR-OBS-2 (no silent excepts), FR-NET-8 (preflight incl. Gmail token) |
| #2 Costly adaptation to other teams | FR-NEG-4/5 (playbook + adapter profiles), FR-NET-7 (tolerant ingress), warm-up games |
| #3 Peer URL churn | FR-NET-3 (permanent named-tunnel hostname), preflight self-call |
| #4 Negotiation invisible | FR-NEG-4 (persisted timeline in UI), FR-LLM-2 (provenance), FR-OBS-1 (wired structured logging) |
| #5 `agreement: null` | FR-REP-2 (egress schema gate, non-nullable booleans), FR-REP-6 (reconciliation) |
| #6 Format barely standard | FR-REP-1 (golden-file schema tests vs reference artifacts), FR-NET-1 (reference-compatible tool surface) |
| #7 Clunky UI | FR-UI-2 (WebSocket push, no polling), FR-UI-5 (cockpit), FR-NET-3 (no manual URL pasting) |
