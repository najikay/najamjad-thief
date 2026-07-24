# Assignment 6 Retrospective — `mcp-marl-cop-thief`

**Repo analyzed:** `reference/mcp-marl-cop-thief` (ex06, "MARL Cop & Thief — Dual AI Agents over MCP", team NajAmjad)
**Purpose:** root-cause the pain points reported after the inter-group runs, and turn them into design decisions for the final project.

---

## 1. Repo layout and architecture

### 1.1 File tree (with purposes)

```
mcp-marl-cop-thief/
├── pyproject.toml                  # uv-managed; ruff + pytest + 85% coverage gate config
├── .env-example                    # DEEPSEEK/ANTHROPIC keys, COP/THIEF MCP tokens, Gmail creds path
├── config/
│   ├── setup.json                  # ALL tunables: game rules, scoring, LLM routing, group/opponent
│   │                               #   identity, reporting emails, token budget, network URL matrix
│   ├── rate_limits.json            # gatekeeper FIFO queue depths
│   └── logging_config.json         # dictConfig payload — validated but NEVER applied (see §3.3)
├── docs/                           # PRD + 5 sub-PRDs, PLAN, TODO (731-line as-built log), STRATEGY,
│   ├── INTER_GROUP_TREATY_SPEC.md  #   the opponent-facing protocol contract (§A–§G, "honour exactly")
│   └── PRD_nl_protocol.md          # spec of the (never-built) "Machiavellian Diplomat" negotiator
├── src/cop_thief/
│   ├── app.py                      # MAIN entrypoint: one asyncio loop = 2 MCP servers + tunnels + UI
│   ├── serve.py / challenge.py / report.py / main.py / diagnostic_runner.py   # alt entrypoints
│   ├── config/                     # pydantic models + ConfigManager + .env autoloader + version guard
│   ├── domain/                     # immutable DecPomdpGameState, Grid, geometry, constants,
│   │   ├── move_language.py        #   deterministic [INTENT: …] + compass-word encode/parse
│   │   └── strategy/               # minimax (alpha-beta), evaluation/features, selfplay TD, qtable,
│   │                               #   heuristic fallback, opponent model, 3-variant roster
│   ├── sdk/                        # CopThiefSDK facade, MatchCoordinator, warfare (injection screen
│   │                               #   + RetaliationLadder counter-injection payloads)
│   ├── infra/
│   │   ├── gatekeeper/             # ApiGatekeeper: FIFO chokepoint, DeepSeek→Anthropic failover
│   │   │                           #   (raw httpx), TokenTracker economics
│   │   └── network/
│   │       ├── dual_mcp_host.py    # Cop :8001 + Thief :8002 as streamable-HTTP /mcp ASGI apps
│   │       ├── switchboard.py      # spawns 2 cloudflared QUICK tunnels, scrapes URLs from stderr,
│   │       │                       #   rewrites config/setup.json with them
│   │       └── move_client.py      # RemoteMoveClient: calls opponent request_move over fastmcp
│   ├── servers/                    # cop_server.py / thief_server.py (FastMCP tools), auth.py (bearer
│   │   ├── inbound_observer.py     #   tokens), tools/ (move_tool, strategy_resolver)
│   │   │                           # passive path: accrue opponent-driven moves, idle-timer auto-email
│   ├── orchestrator/               # controller (turn cycle), series (6 sub-games), challenge_runner
│   │                               #   (cross-host legs), treaty_runner, reconcile, encoder/parser
│   │                               #   (LLM prose), firewall, match, models
│   ├── reporting/                  # GmailApiReporter (OAuth2 send), bonus_report (§9.2 envelope),
│   │                               #   guard (examiner lockout), logger (jsonl audit), archive
│   ├── ui/                         # Starlette panel server :8800, NodeState, SSE broadcast bus,
│   │   └── static/panel.html       #   single-file control panel (vanilla JS)
│   └── gui/window.py               # vestigial tkinter observer (unused by the main flow)
└── tests/                          # 27 unit files + 1 integration file, 135 test functions
```

### 1.2 End-to-end flow (when WE initiate)

1. `python -m cop_thief.app` (`app.py:49-58`) mints bearer tokens, builds both FastMCP servers
   (`dual_mcp_host.build_servers`), starts the Starlette panel on :8800, and opens two cloudflared
   quick tunnels (`switchboard.run_switchboard`), whose random `*.trycloudflare.com` URLs are scraped
   from stderr and written back into `config/setup.json`.
2. The human copies the opponent's URLs/tokens into the panel form; `POST /api/challenge`
   (`ui/server.py:96-100`) spawns a daemon worker thread running `ChallengeRunner.run()`.
3. `ChallengeRunner` (`orchestrator/challenge_runner.py`) plays 6 sub-games: home leg (our Cop local
   via `StrategyResolver`, their Thief fetched over MCP by `RemoteMoveClient`), away leg reversed.
   Every move is treaty prose (`[INTENT: MOVE] The thief edges north-east.`) applied deterministically
   by `domain/move_language.apply_prose`.
4. The result is wrapped in the ex06 §9.2 `bonus_game` envelope (`reporting/bonus_report.py`) and
   emailed by `GmailApiReporter` through the gatekeeper; the panel TV streams turns over SSE.

### 1.3 End-to-end flow (when the OPPONENT initiates)

Their client calls our `request_move` tool (`servers/cop_server.py:67-73`). We only see isolated
observations; `InboundGameObserver` (`servers/inbound_observer.py`) accumulates them, segments
sub-games by role-flip/turn-reset, and after a **45-second idle timer** guesses outcomes and
auto-emails a §9.2 report. This heuristic path is the epicenter of pain point #1 (see §2.2).

---

## 2. Email / communication layer — root causes per pain point

### 2.1 How email actually works

- **Sending only, via Gmail REST API** (`google-api-python-client`), OAuth2 Desktop flow with scope
  `gmail.modify` (`reporting/reporter.py:20`, `bootstrap_oauth` at `reporter.py:50-72`). Messages are
  MIME text with a JSON string body, base64-encoded, `users().messages().send` (`reporter.py:103-105`).
- **There is NO email receiving anywhere.** No `messages().list`, no IMAP, no polling. The opponent's
  report can never be read by the system, so the mutual-agreement handshake can never complete
  automatically (confirmed by grep: the only Gmail call in `src/` is `send` at `reporter.py:105`).
- Peer-to-peer game traffic is MCP streamable-HTTP (`fastmcp.Client` in `infra/network/move_client.py`),
  not email. Email is exclusively the end-of-game report channel.

### 2.2 Pain point: "Email failed when our agent was NOT the initiator"

Root causes, in order of impact:

1. **Silent swallow of every send failure.** `InboundGameObserver._send`
   (`servers/inbound_observer.py:90-99`) wraps the whole reporter in
   `except (OSError, RuntimeError, ValueError, GoogleAuthError): pass`. Any OAuth, network, or guard
   failure vanishes without a log line. You could not even tell it failed.
2. **Interactive OAuth on a background timer thread.** The passive flush runs on a daemon
   `threading.Timer` (`inbound_observer.py:52-56`). `bootstrap_oauth` may call
   `InstalledAppFlow.run_local_server(port=0)` (`reporter.py:68-69`) — an *interactive browser consent*
   — whenever `token.json` is missing/stale/revoked. On the receiving path nobody is at the console,
   the flow blocks or raises, and cause #1 eats the evidence. When WE initiate, a human just clicked
   START in the panel, so the consent window could be serviced; when THEY initiate, it could not.
3. **Fragile idle-timer game detection.** The passive path decides "the game is over" only when no
   `request_move` arrives for 45 s (`inbound_observer.py:22`, `_IDLE_SECONDS`). A slow opponent
   mid-game triggers a premature flush; a crash before idle means no email; there is no explicit
   game-start/game-end signal in the protocol at all.
4. **Guessed outcomes.** `_close_current` infers the winner from
   `max_turn >= max_moves - 2` (`inbound_observer.py:63-64`) — it never sees captures, so the passive
   report content is a heuristic reconstruction, not ground truth.
5. **History of account fragility.** `docs/TODO.md` #458 records that the original reporting Gmail
   account was **banned** by Google mid-project, forcing a credentials/`token.json` re-setup — another
   way the passive path silently broke while the active path (with a human watching) got fixed.

### 2.3 Pain point: "Adapting to other teams' interfaces was very costly"

1. **Take-it-or-leave-it treaty.** `docs/INTER_GROUP_TREATY_SPEC.md` demands a conforming client
   "honour Sections A–G **exactly**" — intent signposts, compass vocabulary, tool name, payload shape,
   SSE schema, anti-injection law. There is no version/capability negotiation.
2. **Hardcoded tool contract.** The tool name `request_move` and argument shape
   `{"observation": {...}, "auth_token": ...}` are frozen in `infra/network/move_client.py:17,39-41`;
   the observation dict shape is frozen in `SeriesRunner._observation`
   (`orchestrator/series.py:43-47`). A peer with `get_move(state=...)` requires code changes.
   `list_remote_tools` (`move_client.py:47-54`) exists as an interop probe but is never used to adapt.
3. **Documented real-world cost.** `docs/TODO.md` #459/#461: one candidate opponent negotiated
   barriers-off + fixed corners + deterministic replays, which required building three new engine
   knobs (`game.deterministic_moves`, `game.barriers_enabled`, `start_mode="fixed"`) — then the
   opponent withdrew. TODO #466: another opponent sent `variant: "standard"` (a string) and crashed
   `request_move` until `_variant_index` coercion was patched in
   (`servers/tools/strategy_resolver.py:51-63`). Every peer difference became an emergency code change.

### 2.4 Pain point: "Peer's URL kept changing"

1. **Ephemeral quick tunnels by design.** `switchboard.py:55-60` runs
   `cloudflared tunnel --url http://127.0.0.1:PORT` — a *quick* tunnel that gets a **new random**
   `*.trycloudflare.com` hostname on every process restart (`_URL_RE` at `switchboard.py:24`). Both
   sides' URLs were therefore unstable session artifacts.
2. **URLs persisted into a versioned config file.** `inject_urls` (`switchboard.py:33-39`) rewrites
   `config/setup.json → network.team_alpha_*` at runtime; the opponent's URLs are hand-pasted into
   `network.team_beta_*` and go stale immediately (`config/setup.json:165-170` still contains dead
   ngrok/trycloudflare hostnames; `servers.cop.url` at `setup.json:33` is a defunct
   `https://cop-mcp.prefect.run`). Report builders then read these stale values
   (`bonus_report.py:88-91`, `series.py:113-118`), so emailed reports could carry dead URLs.
3. **No discovery or refresh.** The only "update" mechanism is a human re-pasting fresh URLs into the
   panel form after each opponent restart. `treaty_runner.py:27-30` additionally hardcodes repos and
   emails (`_REPO_ALPHA/_REPO_BETA/_EXAMINER/_BURNER`) as module constants, and
   `series.py:27` hardcodes a *different*, obsolete burner (`mcp.marl.telemetry@gmail.com`) than the
   config one (`najikayal4@gmail.com`) — three sources of endpoint truth that drifted apart.

### 2.5 Pain point: "`agreement` field was NULL in sent emails"

The JSON key is `mutual_agreement`, and `null` was the *hardcoded default on every real send path*:

- `ChallengeRunner._report` — `"mutual_agreement": None` (`orchestrator/challenge_runner.py:110`).
- `InboundGameObserver.flush` — `{"sub_games": ..., "mutual_agreement": None}`
  (`servers/inbound_observer.py:79`).
- `build_bonus_report(..., mutual_agreement=None)` default parameter (`reporting/bonus_report.py:59`)
  passes `None` straight into the envelope (`bonus_report.py:73`), and `build_bonus_from_report`
  forwards `report.get("mutual_agreement")` — i.e. `None` — at `bonus_report.py:99`.

Why it never became `true`/`false`: the reconciliation function that would set it,
`reconcile_agreement` (`orchestrator/reconcile.py:28-49`), is **only called from tests**
(`tests/unit/test_bonus_report.py:82`, `tests/unit/test_transport_reconcile.py:105,118`). Since the
system cannot *receive* email (§2.1), it never obtains the partner's digest, so no production code
path ever flips the flag. The intended fix was a manual CLI (`report.py:44` passes
`mutual_agreement=True` after a human confirms digests over chat) — which nobody ran under match
pressure. There is also **no outbound schema validation**: the report is a plain dict, so nothing
enforces "must be a boolean" before send (the only pydantic models are for *config*, not messages).

### 2.6 Pain point: "Message format barely met the standard"

- The wire format is prose with a one-token contract: `[INTENT: MOVE|BARRIER|HOLD]` + a compass word
  (`domain/move_language.py:21-31`). Parsing is substring search — `parse_target` takes the first
  (longest) direction word found *anywhere* in the text (`move_language.py:34-41`), and anything
  unparseable silently degrades to HOLD (`move_language.py:57-69`). Legal-but-degenerate.
- The project emits **four different report shapes**: `SeriesRunner._report` (`report_type:
  "game_report"`, `series.py:112-121`), `ChallengeRunner._report` (`groups: {ours, opponent}`,
  `challenge_runner.py:103-110`), `treaty_runner.build_bonus_report` (`treaty_runner.py:83-94`), and
  the canonical §9.2 `bonus_report.build_bonus_report`. Field names drift (`totals` vs
  `totals_by_group`; `groups.ours` vs `groups.group_1`), and `reconcile.py:14` even has to probe both
  key spellings. No JSON Schema, no shared pydantic message model, no validation before send.

---

## 3. Negotiation agent

### 3.1 What was implemented vs. what was designed

- **Designed:** `docs/PRD_nl_protocol.md` §3 specifies a "Tier-3 Machiavellian Diplomat" — an active
  negotiation persona for end-game reconciliation (concede-the-frame/hold-the-facts, up to
  `nl.diplomat.max_rounds` retries, then file `mutual_agreement=false` with logs).
- **Configured:** `config/setup.json:74-77` has an `nl.diplomat` block pointing at
  `prompts/diplomat_default.txt`.
- **Implemented: nothing.** There is no diplomat module in `src/` (grep for "diplomat" hits only docs
  and config). The `prompts/` directory **does not exist** at all — every `prompt_template` path in
  config is dangling. `docs/TODO.md` #441 admits it: "*Multi-round Diplomat negotiation still
  optional*". The closest runtime artifact, `CopThiefSDK.resolve_prose` (`sdk/facade.py:85-95`), is an
  explicit placeholder returning the canned string "Acknowledged your message; holding position…".

So the "actively negotiating agent" could not work: it was config + documentation without code.

### 3.2 Why the failure was silent

- Nothing at startup verifies that configured artifacts (prompt files) exist — `ConfigManager`
  validates JSON shape, not referenced resources.
- No negotiation state was ever logged, because there was no negotiation loop to log.
- Every place that *would* have surfaced trouble suppresses it: `inbound_observer._send` swallows all
  exceptions (`inbound_observer.py:98-99`); the panel's `_email` reduces failures to a one-line banner
  "Email skipped (TypeName)" with no traceback (`ui/server.py:92-93`).

### 3.3 Missing observability (systemic)

- `config/logging_config.json` defines a JSON telemetry handler using
  `cop_thief.infra.logger.JsonFormatter` (`logging_config.json:9`) — **that class does not exist**
  (`src/cop_thief/infra/` contains only `gatekeeper/` and `network/`), and
  `logging.config.dictConfig` is **never called anywhere** in `src/`. The entire structured-logging
  design is validated by `ConfigManager.load_logging` (`config/manager.py:59-60`) and then dropped.
- Actual observability = `print()` banners, the SSE TV, and the per-turn `GameTelemetryLogger` JSONL
  (`reporting/logger.py`) — which covers board turns, not email delivery, OAuth, reconciliation, or
  the passive observer's timer decisions. There was literally no artifact that could answer "did the
  agreement round happen?".

---

## 4. LLM usage

- **Providers:** DeepSeek `deepseek-chat` primary, Anthropic `claude-3-5-sonnet-20241022` failover,
  configured in `config/setup.json:43-59`; called via **raw httpx** (no vendor SDKs — deliberate, see
  `pyproject.toml:16-18`) through `ApiGatekeeper` (`infra/gatekeeper/engine.py:84-118`) with FIFO
  backpressure, failover on transport errors, and `TokenTracker` cost accounting to
  `data/token_usage.json` (budget ceiling $0.50, `setup.json:134-152`).
- **Prompts:** inline string constants, not files. Encoder system prompt at
  `orchestrator/encoder.py:11-19` ("qualitative prose, coordinates ABSOLUTELY FORBIDDEN"); parser
  system prompt at `orchestrator/parser.py:23-29` demanding strict JSON
  (`estimated_direction/distance_band/inferred_barriers/confidence_score`) with a hardening wrapper
  (`domain/agent.harden`). Low confidence (< `nl.parser.min_confidence` = 0.6) or any parse error
  falls back to a safe exploratory belief (`parser.py:40-47,72-76`) — a good fail-safe pattern.
- **Reality check:** the live challenge path never calls an LLM — `StrategyResolver.resolve` returns
  deterministic `encode_move`/`encode_barrier` prose (`strategy_resolver.py:72-84`), and moves are
  minimax. The LLM encoder/parser only runs in `GameLoopController`'s simulated cycle. Total spend
  ≈ $0.01 (README). Lesson: the LLM layer was ornamental in production; the deterministic contract did
  all the work.

---

## 5. UI

- **Stack:** single-file vanilla-JS panel (`ui/static/panel.html`, 173 lines) served by a 4-route
  Starlette app (`ui/server.py`): `/` panel, `/stream` SSE TV, `/api/status`, `POST /api/challenge`.
  Plus two dead ends: a tkinter observer (`gui/window.py`) and an unused `streamlit` optional dep
  (`pyproject.toml:33`).
- **What made it clunky:**
  - Status is **2-second polling** (`panel.html:137`) layered on top of an SSE channel that already
    exists — two transports for one page.
  - The SSE stream has **no reconnect/backoff**; on error it just prints "● stream closed"
    (`panel.html:170`) and the TV dies until manual refresh.
  - The challenge workflow is manual copy-paste of 4 URLs + 2 tokens per opponent restart
    (`panel.html:66-69`), directly downstream of the ephemeral-tunnel problem (§2.4).
  - START is re-enabled by a blind 4-second `setTimeout` (`panel.html:164`), not by server state; no
    progress, cancellation, or per-sub-game scoreboard; errors arrive only as comms-feed banners.
  - The broadcast bus **drops frames when full** (`ui/broadcast.py:21-22`,
    `suppress(asyncio.QueueFull)`) and supports effectively one subscriber (a single shared queue), so
    a second browser tab steals/loses events.
  - No email/report visibility: after a game you cannot see the JSON that was (or was not) sent —
    which is exactly where pain points #1 and #5 hid.

---

## 6. Code quality

- **File length:** excellent. Largest source file is 122 lines (`sdk/facade.py`,
  `reporting/reporter.py`); everything is under the 150-line limit and nearly everything under 120.
  The cost was fragmentation pressure: 4 report builders, 6 entrypoints, and near-duplicate loops
  (`SeriesRunner.run_series` vs `ChallengeRunner.run`, `series.py:92-110` vs
  `challenge_runner.py:75-101`).
- **Ruff:** configured for zero violations (`pyproject.toml:55-73`, rules E/F/W/I/N/UP/B/C4/SIM,
  line-length 100, E501 ignored) with 3 documented per-file `BLE001` escapes — but note those escapes
  legitimize the broad `except` blocks that caused silent email failure.
- **Tests:** 135 test functions across 27 unit + 1 integration file; coverage gate ≥ 85 %
  (`pyproject.toml:105-107`). **However**, the omit list (`pyproject.toml:89-103`) excludes precisely
  the modules that failed in the field: `ui/server.py`, `switchboard.py`, `dual_mcp_host.py`,
  `treaty_runner.py`, `app.py`, `challenge.py`, `report.py`. The passive-path test
  (`tests/unit/test_inbound_observer.py`, 35 lines) injects a fake emailer, so the real
  OAuth-on-a-timer-thread failure mode was never exercised. Coverage measured the domain, not the
  integration seams.
- **Typing:** pervasive but shallow — most public params are bare `dict`/`tuple`, observations and
  reports are untyped dicts end to end, and **no type checker is configured** (no mypy/pyright in
  `pyproject.toml`). Pydantic is used for config only, never for wire messages.

---

## 7. Keep / Fix / Drop

| Item | Verdict | Rationale / action for the final project |
|---|---|---|
| Config-driven everything + pydantic `ConfigManager` + `.env` autoloader (`src/cop_thief/config/`) | **Keep** | Solid pattern; add existence checks for referenced files (prompts, credentials). |
| `ApiGatekeeper` + `TokenTracker` (raw-httpx failover, budget ceiling) | **Keep** | Provider-agnostic, cheap, testable. Port nearly as-is. |
| Deterministic move/message contract with an LLM-optional layer | **Keep** | "Thin deterministic core, prose on top" is the single best architectural call of ex06. |
| Fail-safe defensive parser (low confidence → safe default, never crash) | **Keep** | Reuse the pattern for all inbound content, including emails. |
| `SubmissionSafetyGuard` (examiner lockout until production unlock) | **Keep** | Saved them from mis-sends; keep, but log every block loudly. |
| Immutable domain state + 135-test discipline + ≤150-line files | **Keep** | Keep the discipline; extend coverage to the seams (see Fix). |
| SSE live board concept | **Keep** | Rebuild on a multi-subscriber bus with reconnect. |
| Email layer (send-only Gmail, interactive OAuth, no inbox reading) | **Fix** | Add inbox polling/state-machine processing; pre-flight OAuth at startup (fail fast, never mid-game on a timer thread); retry queue + dead-letter file for unsent reports. |
| `mutual_agreement`/report schema | **Fix** | One pydantic wire schema, `agreement: bool` **required** (no None), validated before send; reconciliation wired into the runtime, not a manual CLI. |
| Passive/receiving flow (`InboundGameObserver` idle timer) | **Fix** | Replace idle-timer guessing with explicit protocol events (game_start/turn/game_end) driving a persistent state machine; both peers email from recorded ground truth. |
| Endpoint management (quick tunnels + URLs frozen in setup.json) | **Fix** | Named/stable tunnels or a config-exchange handshake message (peer publishes current URLs at session start); runtime peer registry separate from versioned config; single source of truth for emails/repos. |
| Protocol rigidity (treaty "exactly", hardcoded tool name/args) | **Fix** | Version + capability handshake; tolerant adapter layer (tool discovery via `list_remote_tools`, alias maps for tool/field names); coerce-and-log instead of crash for foreign fields. |
| Observability (dictConfig never applied, silent excepts) | **Fix** | Actually call `logging.config.dictConfig` at startup; structured JSONL events for every send/receive/negotiation step; ban bare `pass` on exception — minimum is a logged event + UI surface. |
| Control panel UX | **Fix** | Keep the one-command boot; add SSE reconnect, server-driven button state, per-sub-game scoreboard, and an outbox view showing exactly what was emailed (or why not). |
| "Machiavellian Diplomat" as spec-only vaporware | **Drop** | Either build a real, observable negotiation state machine or delete the config/docs for it. No more configured-but-unimplemented features. |
| Warfare/RetaliationLadder counter-injection payloads (`sdk/warfare.py`) | **Drop** | Detection/logging of hostile input is worth keeping; emitting our own injection payloads is risk without reward for the final project. |
| tkinter GUI + streamlit optional dep | **Drop** | Dead weight; one UI stack only. |
| 4 divergent report builders / 6 entrypoints | **Drop (consolidate)** | One report module, one schema, ≤2 entrypoints. |
| Coverage omit-list covering all integration seams | **Drop** | Replace with integration tests that fake the network/Gmail boundary, not the module. |

---

## 8. Top 10 lessons learned → design decisions for the final project

1. **Never guess the end of a conversation — model it.** The 45 s idle timer
   (`inbound_observer.py:22`) is why the passive path was unreliable. *Decision:* a persistent,
   event-driven **state machine per peer/game** (e.g. `IDLE → HANDSHAKE → PLAYING → RECONCILING →
   REPORTED`), advanced only by explicit protocol messages, persisted to disk so a restart resumes.
2. **Required booleans, validated at the boundary.** `mutual_agreement: None` shipped because reports
   were plain dicts with `None` defaults (`challenge_runner.py:110`, `bonus_report.py:59`).
   *Decision:* pydantic models for every outbound message with `agreement: bool` (and friends)
   **required, no default**; `model_validate` before send; refuse to send invalid payloads and alarm.
3. **A receive path is half of every protocol.** ex06 could send email but never read it, so
   reconciliation (`reconcile.py`) was dead code outside tests. *Decision:* inbox polling (Gmail
   `messages.list` + `historyId`, or IMAP) feeding the state machine; every inbound email is parsed,
   validated, logged, and answered — including when we did not initiate.
4. **Endpoints are runtime data, not configuration.** trycloudflare URLs rot per restart and were
   baked into `config/setup.json:165-170`. *Decision:* a `peers.json`/registry updated by a
   **config-exchange handshake** (first message of a session carries current URLs, tool names,
   schema version, email address); versioned config holds only identity and defaults; one single
   source of truth for examiner/burner addresses (kill the `series.py:27` style duplicates).
5. **Negotiate capabilities, then adapt — don't legislate.** The treaty's "honour §A–§G exactly" plus
   frozen `request_move(observation, auth_token)` made every peer difference a code change
   (TODO #459/#461/#466). *Decision:* version/capability handshake + an adapter layer keyed by peer
   (tool-name aliases, field mapping, lenient coercion with logged warnings), with tool discovery
   (`list_tools`) at connect time.
6. **Fail fast on credentials, at startup, on the main thread.** Interactive OAuth buried in a timer
   thread (`reporter.py:68-69` via `inbound_observer.py:96-97`) is unrunnable exactly when needed.
   *Decision:* a `doctor`/preflight step that validates Gmail token, LLM keys, tunnel binaries, and
   prompt files before the agent goes online; refuse to start "healthy" otherwise.
7. **Silent `except: pass` is how features die invisibly.** (`inbound_observer.py:98-99`,
   `ui/server.py:92-93`.) *Decision:* every exception on a communication path produces a structured
   log event **and** a UI-visible status; unsent reports go to a retry queue + dead-letter file, never
   to `/dev/null`.
8. **Observability is a feature with an acceptance test.** The logging dictConfig was validated but
   never applied, and its formatter class doesn't exist (`logging_config.json:9`). *Decision:*
   structured JSONL event log (send/receive/negotiation-round/state-transition) wired at startup,
   asserted by a test ("negotiation emits ≥1 event per round"), and surfaced in the UI as a timeline —
   so "did the negotiator run?" is answerable in one glance.
9. **If it's configured, it must exist.** `nl.diplomat` + `prompts/*.txt` pointed at nothing;
   the Diplomat was documentation-ware. *Decision:* config loader verifies referenced resources;
   feature flags map 1:1 to implemented modules; PRD sections for unbuilt features are marked
   `NOT IMPLEMENTED` or deleted.
10. **Test the seams you fear, not the domain you trust.** 135 tests and an 85 % gate coexisted with
    every field failure living in coverage-omitted modules (`pyproject.toml:89-103`). *Decision:*
    integration tests for the full passive flow (fake peer drives our server → state machine →
    validated report → fake mailer asserts `agreement` is boolean), URL-rotation drills, and a
    two-node self-play smoke test in CI; keep the ≤150-line and ruff gates, add mypy/pyright.

---

*Compiled 2026-07-24 from full source review of `reference/mcp-marl-cop-thief` (README, all `src/`,
`config/`, `docs/`, `tests/`).*
