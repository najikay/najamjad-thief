# Simulator Repo Digest — `reference/Game-P2P-Cop-Chase`

Analysis of the lecturer's official reference simulator (**Police-vs-Thief: Fully
Distributed AI Pursuit Simulation**, code v3.0.0, matching guidelines book v3.0.0).
Repo: <https://github.com/rmisegal/Game-P2P-Cop-Chase>. License: restrictive
Educational Use EULA (students may read/reuse parts inside the course; the graded
solution must implement its own strategy). **Where this repo differs from the book,
the book and its binding parameter table win** (README.md:27-31).

Analyzed on 2026-07-24. All paths below are relative to
`reference/Game-P2P-Cop-Chase/` unless absolute.

---

## 1. Repo layout (full tree, one-line purpose per file)

```
Game-P2P-Cop-Chase/
├── README.md                  # Full manual: run commands, GUI walkthrough, config split, architecture
├── LICENSE                    # Educational Use EULA (Dr. Yoram Segal / GTAI, all rights reserved)
├── pyproject.toml             # uv project; Python ≥3.13; single runtime dep: fastmcp≥3.4.3; ruff+pytest cfg
├── uv.lock                    # Locked dependency graph
├── .python-version            # "3.13"
├── .env-example               # Placeholder .env; ANTHROPIC_API_KEY deliberately left EMPTY (CLI login auth)
├── .gitignore                 # venv, caches, secrets, logs/
├── .githooks/pre-commit       # Runs scripts/sync_versions.py; re-stages README + book PDF
├── scripts/
│   ├── sync_versions.py       # Syncs CODE_VERSION/book version into README, copies book PDF (76 lines)
│   └── render_docs_images.py  # Pillow tool that renders README GUI screenshots from a saved log (166 lines)
├── config/
│   ├── police/game.toml       # Police peer's PRIVATE local config (identity, port 8802, LLM, GUI, email)
│   ├── police/game.json       # SHARED, signed game terms (board, world, movement, scoring, pheromones…)
│   ├── police/rate_limits.json# Per-service rate limits for the ApiGatekeeper (claude/email/default/queue)
│   └── thief/{game.toml, game.json, rate_limits.json}  # Same trio for the thief peer (port 8801)
├── docs/
│   ├── police_thief_p2p.pdf   # The bundled guidelines book (binding rules + parameter tables)
│   ├── STRATEGY.md            # Student guide: brain override hooks, config selector, trash-talk providers
│   ├── PLAN.md                # Original distributed-architecture build plan (protocol JSON sketch)
│   ├── PLAN-GUI-CONTROL-CHANNEL.md   # Design doc for the opt-in bidirectional control channel
│   ├── UPGRADE-4JSON-PLAN.md / UPGRADE-4JSON-TODO.md  # Plan/tasks that aligned engine to the book + 4 JSONs
│   ├── RESEARCH-REPORT-Performance-Analysis.md        # Token/latency analysis (why moves are Python-only)
│   ├── images/{gui-annotated.png, heatmap-progression.png}  # README figures
│   └── sample-run/            # A real localhost run: the 4 emitted artifacts sharing one game_uid
│       ├── declaration_segal-police-team-vs-segal-thief-team.json
│       ├── config_segal-police-team-vs-segal-thief-team_g01.json
│       ├── log_segal-police-team-vs-segal-thief-team_g01.json
│       └── result_segal-police-team-vs-segal-thief-team.json
├── src/police_thief/
│   ├── __init__.py            # Package docstring + __version__ = "3.0.0" (5 lines)
│   ├── __main__.py            # `python -m police_thief` → cli.main (10)  <!-- third-party-quote-ok: reference simulator's own command -->
│   ├── cli.py                 # argparse: `peer --role --config --stub-llm --no-gui` and `replay --log` (89)
│   ├── constants.py           # Role/MoveType/Direction StrEnums, DELTAS, ORTHOGONAL, move-set parser (83)
│   ├── exceptions.py          # SimulationError hierarchy + RestartSeries control-flow signal (52)
│   ├── py.typed               # PEP 561 marker
│   ├── shared/
│   │   ├── config.py          # ConfigManager: game.toml + rate_limits.json + game.json overlay (164)
│   │   ├── gatekeeper.py      # ApiGatekeeper: single doorway for external calls, retry + rate limit (59)
│   │   ├── rate_limiter.py    # Sliding-window token bucket w/ FIFO queue, injectable clock (73)
│   │   ├── sysinfo.py         # Host spec probe (CPU/GPU/RAM/OS; PowerShell + nvidia-smi), cached (81)
│   │   └── version.py         # CODE_VERSION/BOOK_VERSION/SUPPORTED_CONFIG_VERSIONS + license text (31)
│   ├── domain/                # Pure game logic, no I/O
│   │   ├── board.py           # NxN geometry: step/neighbors/legal_moves/distance under move_set (67)
│   │   ├── own_state.py       # OwnGameState: my position/visited/barriers/step log; apply_move (80)
│   │   ├── rules.py           # GameRules: survival check + honest capture answer (32)
│   │   ├── smell.py           # SmellField: radial deposit, absorb, decay, snapshot {"r,c": v} (72)
│   │   ├── belief.py          # BeliefGrid: probability heatmap; observe_smell/diffuse/exclude (81)
│   │   ├── brains.py          # BrainBase/ThiefBrain/PoliceBrain + Decision dataclass (student seam) (118)
│   │   ├── crypto.py          # CommitReveal: SHA256(canonical_json|nonce) seal/verify + audit_records (65)
│   │   ├── negotiation.py     # Mutual signed-terms handshake object (signed()/verify_peer()) (43)
│   │   ├── game_ids.py        # Deterministic shared game_id + game_uid derivation (32)
│   │   ├── protocol.py        # Wire dataclasses: TurnMessage, ControlMessage, AuditPayload (81)
│   │   └── scoring.py         # score_subgame + aggregate (book scoring + tie rule), pure functions (75)
│   ├── strategy/
│   │   ├── __init__.py        # resolve_brain factory + "pkg.mod:Class" selector loader (80)
│   │   ├── trash_talk.py      # TEMPLATE sentence-bank provider + LlmTrashTalk wrapper (143)
│   │   └── talk_providers.py  # resolve_trash_talk: template/claude_cli/claude_api/ollama askers (86)
│   ├── peer/                  # One standalone agent's lifecycle
│   │   ├── runtime.py         # PeerRuntime: negotiate → turn loop → audit; per-sub-game state (129)
│   │   ├── handshake.py       # negotiate(): exchange signed terms, derive game_id/uid (28)
│   │   ├── turn_handler.py    # TurnHandler: fold opponent TurnMessage into my belief/state (61)
│   │   ├── turn_sender.py     # take_turn/send/send_final: decide, seal, deposit scent, send (77)
│   │   ├── sealing.py         # terms_from_config, sealed step/spec records, validate_agreement (138)
│   │   ├── summary.py         # finish(): audit exchange + final summary dict; step token deltas (69)
│   │   ├── controls.py        # GameControls: thread-safe pause/play/stop/restart/quit/speed (93)
│   │   ├── control_link.py    # ControlLink: opt-in bidirectional channel state machine (113)
│   │   └── runtime_control.py # pump()/check(): drain control, broadcast status, raise RestartSeries (59)
│   ├── sdk/
│   │   ├── sdk.py             # SimulationSdk facade: run_peer(series) + StubLlm + GatedLlm (128)
│   │   └── series.py          # run_series: N sub-games, role alternation, restart loop (84)
│   ├── infra/
│   │   ├── mcp_server.py      # Per-peer FastMCP HTTP server: 4 receive tools → thread-safe inboxes (92)
│   │   ├── mcp_client.py      # McpTransport: fastmcp Client calls to opponent + inbox polling (108)
│   │   ├── llm_provider.py    # ClaudeCliProvider: `claude -p --output-format json`, env-stripped (127)
│   │   └── email_sender.py    # EmailSender: Gmail draft via external gg:email skill script (51)
│   ├── report/
│   │   ├── artifacts.py       # Pure builders for the 4 standardized JSON artifacts (126)
│   │   ├── artifact_helpers.py# Filenames, links block, canonical sha256, hardware/group blocks (84)
│   │   ├── artifact_schemas.py# The long self-documenting _schema strings + SCHEMA_VERSION 1.1 (18)
│   │   ├── emit.py            # emit_series: write declaration/config/log/result to logs/<group_id>/ (124)
│   │   └── report_writer.py   # Legacy Hebrew match report + consensus_signature (82)
│   └── gui/                   # Tkinter presentation only (excluded from coverage)
│       ├── __init__.py        # TCL_LIBRARY/TK_LIBRARY env fix for Windows+uv venvs (22)
│       ├── player.py          # LivePeerApp: worker thread + event queue → window (154)
│       ├── window.py          # PeerWindow chrome: banner, info panel, budget slider, menus (130)
│       ├── board_view.py      # Canvas: heatmap cells, visited dots, barriers, agent discs (78)
│       ├── live_controls.py   # Start/Pause/Play/Stop/Restart/Quit bar + sub-games dropdown (56)
│       ├── live_apply.py      # Event → window label dispatch, control-channel rendering (85)
│       ├── game_mode.py       # Maps trash_talk.provider → GUI "Game mode"/"Model" labels (46)
│       ├── replay.py          # ReplayApp: step through a log, rebuild belief, verify hashes (167)
│       ├── replay_controls.py # Replay control bar: Play/Pause/Step/Restart/Goto/sub-game (37)
│       └── replay_data.py     # Log normalization, sibling-opponent-log discovery, verify_record (124)
└── tests/
    ├── conftest.py            # Temp game.toml + rate_limits.json fixtures → ConfigManager (101)
    ├── integration/test_mcp_match.py  # Real two-server HTTP match + 4-artifact series test (190)
    └── unit/  (33 files)      # One test module per source module; 254 test functions total
```

---

## 2. How to run it, configuration, environment variables

### Two terminals (README.md:66-88)

```powershell
uv sync                                                               # one-time install

# Headless, deterministic, zero LLM:
uv run python -m police_thief peer --role police --stub-llm --no-gui  # Terminal 1  <!-- third-party-quote-ok: reference simulator's own command -->
uv run python -m police_thief peer --role thief  --stub-llm --no-gui  # Terminal 2  <!-- third-party-quote-ok: reference simulator's own command -->

# With Tkinter GUI (window opens idle → pick sub-games 1–6 → press Start):
uv run python -m police_thief peer --role police                      # Terminal 1  <!-- third-party-quote-ok: reference simulator's own command -->
uv run python -m police_thief peer --role thief                       # Terminal 2  <!-- third-party-quote-ok: reference simulator's own command -->

# Visual replay of a saved log with live hash re-verification:
uv run python -m police_thief replay --log logs/<group_id>/log_<game_id>_g01.json  <!-- third-party-quote-ok: reference simulator's own command -->
```

- **Ports:** thief serves MCP at `http://127.0.0.1:8801/mcp`, police at
  `http://127.0.0.1:8802/mcp`. **Start order doesn't matter** — every outbound call
  retries until the opponent's server responds (`mcp_client.py:42-55`,
  `connect_timeout_seconds=60`, `retry_interval_seconds=1.0`).
- `--stub-llm` swaps `ClaudeCliProvider` for `StubLlm` (deterministic template banter,
  no CLI needed); `--no-gui` runs headless (series starts immediately using config
  `num_games`). Flags are independent (cli.py:35-37, sdk.py:58-66).
- Default config dir is `config/<role>/` (cli.py:19-21), overridable via `--config`.
- Startup fail-fast: `sealing.validate_agreement` (sealing.py:114-126) aborts before
  any port is opened if a required shared term is missing from `game.json`;
  `_ensure_port_free` (mcp_server.py:19-34) aborts with PowerShell instructions if
  the port is taken.

### Configuration files (per peer, under `config/<role>/`)

The split rule (README.md:344-354): **anything both sides must AGREE on → shared,
signed `game.json`; anything private-local → `game.toml`.**

1. **`game.json`** (shared, byte-identical on both peers; schema_version 1.3; book
   Appendix F). Sections: `board_and_agents` (grid_size 7, thief_start [3,3],
   cop_start [0,0], axis_origin_corner "top-left", axis_start_index 0), `world`
   (map_area "New York", hint_max_words 15), `movement_and_barriers` (move_set
   ["N","S","E","W","STAY"], max_barriers 14, max_moves 35, survival_threshold 35),
   `scoring` (capture_cop 20, capture_thief 5, survival_cop 5, survival_thief 10,
   tie_score 2, technical_loss 0), `pheromones` (center 0.9, decay 0.10, grid 5, min
   center 0.5), `network_and_league` (num_games 1 — book mandates 6;
   token_budget_per_series 200000; response/watchdog timeouts), and
   `rate_limiter_gatekeeper`. It is loaded by `ConfigManager` and **overlaid** on the
   TOML via `_translate_shared` → `_deep_merge` (config.py:20-113), mapping e.g.
   `board_and_agents.grid_size` → dotted `board.size`, `world.map_area` →
   `play.setting`, `movement_and_barriers.survival_threshold` → `rules.max_steps`.
2. **`game.toml`** (private; version "1.10" must be in `SUPPORTED_CONFIG_VERSIONS`).
   Blocks: `[game]` group identity (group_id/group_name/members/repos/mcp_servers),
   `[belief]` smell_trust_weight 4.0, optional `[strategy]` brain selectors, optional
   `[trash_talk]` provider block, `[gui]`, `[paths]` (logs_dir, legacy log_filename),
   `[play]` (step_speed_seconds, seed), `[network]` (my_port, opponent_url,
   turn_timeout_seconds 180, poll_interval_seconds 0.5, connect/retry/audit
   timeouts), `[llm]` (executable "claude", model, args, timeout_seconds 120,
   response_field "result", step_deadline_seconds 30), `[email]` (recipient
   `rmisegal+uoh26finalgame@gmail.com`, mode "draft", **enabled=false**, gg:email
   script paths).
3. **`rate_limits.json`** — per-service `requests_per_minute` / retries plus a
   `queue` block (max_depth 100, drain 0.1s, timeout 300s), consumed by
   `RateLimiter`/`ApiGatekeeper`.

### Environment variables

- `.env-example`: **`ANTHROPIC_API_KEY` must stay empty** — the design uses the
  Claude CLI browser login (subscription), not API-key billing.
- `llm_provider.py:25-31` strips `ANTHROPIC_API_KEY`, `CLAUDECODE`,
  `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `API_TIMEOUT_MS` from the subprocess
  env before invoking `claude -p`.
- `gui/__init__.py:14-23` sets `TCL_LIBRARY`/`TK_LIBRARY` on Windows+uv venvs.
- No other env vars are read; everything else comes from config files.

---

## 3. Architecture: modules, responsibilities, data flow, inter-process comms

### Layering (README.md:389-402)

```
CLI / Tkinter GUI (LivePeerApp, ReplayApp, PeerWindow)     ← presentation only
        │ events via queue.Queue + listener callback
   SimulationSdk.run_peer  ── N-sub-game series loop        ← single business entry (sdk/sdk.py)
        │
 PeerRuntime (one per sub-game) ── negotiate → turn loop → audit   (peer/runtime.py)
   ├─ strategy/  resolve_brain (move = pure Python), trash_talk (banter)
   ├─ domain/    board, own_state, rules, smell, belief, brains, crypto,
   │             negotiation, game_ids, protocol, scoring
   ├─ peer/      handshake, turn_handler, turn_sender, sealing, summary,
   │             controls, control_link, runtime_control
   ├─ report/    artifacts (4 JSON builders), emit, report_writer (Hebrew legacy)
   ├─ infra/     mcp_server (my FastMCP), mcp_client (McpTransport), llm_provider, email_sender
   └─ shared/    ConfigManager, ApiGatekeeper + RateLimiter, sysinfo, version
```

### How the two processes communicate (transport)

- **Transport = MCP over HTTP (FastMCP), symmetric mailbox pattern.** Each peer runs
  its **own FastMCP HTTP server** on its own localhost port in a **daemon thread**
  (`mcp_server.py:78-93`, `server.run(transport="http", host, port)`); there is no
  central server. The server exposes exactly **four MCP tools** that do nothing but
  enqueue the received dict into thread-safe `queue.Queue` inboxes
  (`PeerInboxes.agreements/turns/audits/controls`, mcp_server.py:37-75):
  - `negotiate(message: dict)` — signed game agreement
  - `receive_turn(message: dict)` — a TurnMessage (carries the turn token)
  - `submit_audit(payload: dict)` — end-of-game reveal
  - `receive_control(message: dict)` — optional control-channel signal
- **Outbound**: `McpTransport` (mcp_client.py) opens a fresh fastmcp `Client(url)`
  per call inside `asyncio.run` (`_call`, lines 34-40) and invokes the opponent's
  tool; `_call_with_retry` loops until the opponent's server is up. **Inbound**: the
  runtime polls its own inboxes (`poll_turn(timeout)`, `poll_control()` non-blocking).
- Transport API consumed by the runtime (and mimicked by test fakes):
  `exchange_agreement(signed) -> dict`, `send_turn(msg)`, `poll_turn(t) -> dict|None`,
  `exchange_audit(payload) -> dict|None` (best-effort send; the winner may already
  have exited — mcp_client.py:99-107), `send_control` (best-effort, 2s cap,
  suppressed errors), `poll_control`, `drain_inboxes` (series restart hygiene).
- The transport + servers are built **once per process** and reused across the whole
  series (sdk.py:94-95); each sub-game gets a fresh `PeerRuntime`.
- Message payloads are plain JSON dicts as MCP tool arguments
  (`{"message": {...}}` or `{"payload": {...}}`, mcp_client.py:37-38).

### Data flow of one turn

1. Waiting peer sits in `PeerRuntime._turn_loop` (runtime.py:101-129), polling
   `poll_turn` every 0.5s with a 180s deadline.
2. A `TurnMessage` arrives → `TurnHandler.process` (turn_handler.py:41-61): record
   history; note declared barrier; `belief.diffuse()` then
   `belief.observe_smell(smell_grid)`; `smell_field.absorb` + `decay_all`; evaluate
   claims (capture / claim_response / win_claim).
3. If the game did not end, `turn_sender.take_turn` (turn_sender.py:17-56): pump the
   control channel, honor pause/stop; `brain.decide(...)` picks the **move in pure
   Python** and asks the trash-talk provider for the hint; `state.apply_move`
   (illegal → forced HOLD); seal the true step (`sealed_step_record`), deposit my
   scent, build and `send_turn` the wire message (with the police's `capture_claim`
   attached automatically after every MOVE, turn_sender.py:46-49).
4. GUI, if present, is a pure mirror: runtime emits listener events
   (`negotiated`/`incoming`/`moved`/`game_over`/`control_*`/`series_restart`/`error`)
   into a queue drained by Tk `after()` polling (player.py:120-145).

---

## 4. The complete message protocol as implemented

All wire structures live in `domain/protocol.py`, `domain/negotiation.py`, and
`peer/sealing.py`.

### 4.1 Agreement message (MCP tool `negotiate`)

Built by `Negotiation.signed()` (negotiation.py:24-33):

```json
{
  "terms": { ... },                 // see terms table below — must be IDENTICAL on both sides
  "nonce": "<32-hex>",              // fresh 16-byte hex
  "signature": "<sha256hex>",       // SHA256(canonical_json(terms) + "|" + nonce)
  "identity": {                     // NOT covered by the signature (differs per group)
    "group_id": "...", "group_name": "...", "members": [...],
    "repos": {...}, "mcp_servers": {...}, "llm_model": "...",
    "spec": { os, cpu_type, cpu_cores, cpu_freq_mhz, ram_gb, gpu_type, gpu_cores_or_cuda, vram_gb }
  }
}
```

`terms` (sealing.py:94-111): `board_size`, `smell_grid_size`, `decay_per_step`,
`emit_intensity`, `min_center_intensity`, `max_steps`, `barriers_max`, `setting`,
`hint_max_words`, `axis_origin_corner`, `axis_start_index`, `thief_start`,
`cop_start`, `num_games`. Verification (`verify_peer`, negotiation.py:35-43): terms
dict equality + signature recompute; any mismatch raises `CryptoError` and the game
refuses to start. Both peers then **derive identical ids without another
round-trip**: `game_id = "<gidA>-vs-<gidB>"` (sorted) and `game_uid =
UUID(sha256(canonical(terms)|sorted gids)[:16])` (game_ids.py:21-32).

### 4.2 TurnMessage (MCP tool `receive_turn`) — protocol.py:12-40

```json
{
  "step": 7,
  "sender": "thief" | "police",
  "hint": "<free NL taunt, ≤ hint_max_words, MAY LIE>",
  "smell_grid": {"r,c": 0.73, ...},          // decaying scent intensities; NEVER a position
  "commit": "<sha256hex>",                    // seal of the true step; nonce withheld
  "timestamp": "<ISO-8601 UTC>",
  "barrier_placed": null | [r, c],            // public declaration, impassable for both
  "capture_claim": null | [r, c],             // police only: sent after EVERY MOVE (own cell)
  "claim_response": null | {"claim": [r,c], "caught": true|false},  // thief's honest answer
  "win_claim": null | {"type": "survival"}    // thief's victory claim
}
```

Notes: the **turn token travels with the message** — receiving one makes it your
turn. `from_dict` validates required fields (protocol.py:34-40). True
position/move/verdict are never in the clear; only inside `commit`.

### 4.3 Sealed records (revealed only at audit) — sealing.py

- **Step 0, host-spec declaration** (`sealed_spec_record`, sealing.py:28-41):
  payload `{step: 0, type: "system_spec", spec: {...}, model, code_version,
  group_name, sub_game_number}` + `{nonce, commit}`.
- **Per-step record** (`sealed_step_record`, sealing.py:66-91): payload
  `{step, state: "grid=7x7;self=[r, c];barriers=[...]", position, move
  ("MOVE:S"/"BARRIER:E"/"HOLD:-"), intent, verdict ("truth"|"lie"), hint,
  prompt_discussion: {llm_prompt, llm_reasoning, bluff_classification}, model,
  tokens_step, tokens_total, response_seconds, random_move}` + `{nonce, commit}`.
- Commit formula (crypto.py:20-37): `SHA256(canonical_json(payload) + "|" + nonce)`
  with canonical = `json.dumps(sort_keys=True, ensure_ascii=False,
  separators=(",",":"))`; nonce = `secrets.token_hex(16)`.

### 4.4 AuditPayload (MCP tool `submit_audit`) — protocol.py:68-81

```json
{
  "sender": "thief" | "police",
  "records": [ {"payload": {...}, "nonce": "...", "commit": "..."}, ... ],
  "result_claim": "capture" | "survival" | "timeout"
}
```

Each side runs `audit_records` (crypto.py:49-65) over the opponent's reveal →
`{passed, verified_steps, failed_steps}`. **Any failed hash ⇒ the honest peer wins
by `tamper_forfeit`** (summary.py:49-57). Audit is skipped for `timeout`/`stopped`
results (`SKIPPED_AUDIT`, summary.py:10-11).

### 4.5 ControlMessage (MCP tool `receive_control`; opt-in channel) — protocol.py:43-65

```json
{
  "kind": "enable" | "status" | "restart" | "quit",
  "sender": "thief" | "police",
  "sub_game_number": 1,
  "status": "WAITING|THINKING|PLAYING|PAUSED|STOPPED|GAME_OVER|QUIT",
  "step_budget": 30.0,
  "payload": null
}
```

Semantics (control_link.py): channel is ACTIVE only after **both** sides send
`enable`; `status` is broadcast on change only; `restart` is auto-approved when
active and raises `RestartSeries` (whole series restarts from sub-game 1, inboxes
drained first, max 10 restarts — series.py:21,61-84); `quit` ends the opponent's
game as `opponent_quit`. Not part of the sealed record and never written to
`game.json`.

### 4.6 Game state machine (one sub-game, per peer)

```
IDLE (GUI: READY)
  └─ Start → validate_agreement → MCP server up → NEGOTIATE
NEGOTIATE: send signed terms → wait opponent's → verify (mismatch ⇒ refuse/CryptoError)
  └─ derive game_id/game_uid; clock starts            (handshake.py)
PLAYING:
  thief: take_turn immediately (thief moves first)     (runtime.py:92-94)
  both:  loop { WAITING → poll_turn ─ timeout 180s ⇒ result=timeout (I win technically)
                incoming → process → THINKING → decide → seal → send }
END CONDITIONS (runtime.py:106-129, turn_sender.py:45-56):
  capture        — police's capture_claim matched thief's true cell; thief sends the
                   mandatory final "You got me." message, winner=police
  survival       — thief reached max_steps (survival_threshold); win_claim sent, winner=thief
  timeout        — opponent silent > turn_timeout_seconds; winner = the waiting peer
  stopped        — local Stop button; winner "-", audit skipped
  quit / opponent_quit — control channel clean shutdown
  tamper_forfeit — post-audit hash mismatch; honest peer wins
AUDIT (unless timeout/stopped): exchange_audit both ways, verify all records
GAME_OVER → summary → next sub-game (roles swap) or series end → emit 4 artifacts → email
```

Broadcast status overlay (control_link.py:13-14): `WAITING, THINKING, PLAYING,
PAUSED, STOPPED, GAME_OVER, QUIT`.

---

## 5. Game logic as implemented

- **Board** (domain/board.py): NxN grid (default 7×7) of `(row, col)` tuples, row 0
  at top (row grows south). Allowed directions are configured by the agreed
  `move_set`; default `["N","S","E","W","STAY"]` → 4-orthogonal + HOLD; empty
  move_set falls back to legacy 8-direction king moves (constants.py:56-71).
  Distance is Manhattan for orthogonal sets, Chebyshev if any diagonal is allowed
  (board.py:32-36). A step is illegal if off-board or onto a barrier.
- **Own state only** (domain/own_state.py): there is **no shared board**. Each peer
  is authoritative for its own position, visited set, and barrier quota; opponent
  barriers are only known when declared on the wire. `apply_move` returns False on
  an illegal move (caller then forces HOLD, turn_sender.py:41-43). HOLD does not add
  a visited cell.
- **Barriers** (police only): `_place_barrier` (own_state.py:63-73) walls the
  adjacent cell in the chosen direction instead of moving, capped by
  `barriers_max` (14). Barriers block both agents and are publicly declared via
  `barrier_placed`.
- **Turn order**: thief moves first (runtime.py:92-94); strict ping-pong via the
  turn token.
- **Capture (no referee)**: after every police MOVE the message carries
  `capture_claim = police's own new cell` (turn_sender.py:46-49). The thief must
  answer honestly (`GameRules.is_captured` compares to its true cell,
  rules.py:25-32) — lying is pointless because the audit reveals the sealed true
  position and a false answer forfeits.
- **Thief win**: surviving `max_steps` (= `survival_threshold`, 35) steps ⇒
  `win_claim {"type": "survival"}` (rules.py:19-23, turn_sender.py:45).
- **Smell/pheromones** (domain/smell.py): every step the mover deposits a radial
  5×5 scent around its true cell (center intensity 0.9, linear falloff by Chebyshev
  distance, min center 0.5 enforced), max-merged into its trail, then decayed by
  0.1/step; only the **intensity field snapshot** (`{"r,c": v}`) is transmitted —
  never a coordinate.
- **Belief** (domain/belief.py): each peer keeps a probability grid over the board
  for the opponent's cell: `diffuse()` spreads mass to the movement neighbourhood
  (von Neumann for orthogonal play) each opponent move, `observe_smell` multiplies
  each cell by `(1 + smell_trust * intensity)` then normalizes. `most_likely()`
  drives both shipped brains.
- **Shipped brains** (domain/brains.py — deliberately basic; the student's job is to
  replace them): ThiefBrain maximizes distance from the belief peak, preferring
  unvisited cells; PoliceBrain minimizes distance to the belief peak and, with
  probability 0.15, places a barrier on the cell it would have stepped onto.
- **Scoring** (domain/scoring.py, config `scoring`): per sub-game — capture: cop
  group 20 / thief group 5; survival: cop 5 / thief 10; anything else (timeout,
  stopped, tamper_forfeit) scores 0/0. `aggregate` sums a series: per-group totals,
  sub_games_won, tie count; a two-group equal total is a `series_tie` and grants
  each group `tie_score` (2) extra, `winner_group: null`.
- **Series** (sdk/series.py): one invocation plays `num_games` sub-games (default 1;
  book mandates 6) over the same live transport; `role_for` alternates roles (natural
  role on odd sub-games). Fresh `PeerRuntime` (state/belief/smell/commit chain) per
  sub-game.

---

## 6. TEMPLATE mode (non-LLM sentence bank) and LLM hook points

### Template mode — the shipped default (strategy/trash_talk.py)

- Class `TrashTalk` (lines 47-75): zero tokens, instant, offline. Each turn it picks
  a random line from a role-specific sentence bank and formats in a landmark:
  - `_THIEF_LINES` (4 lines, e.g. `"Catch me if you can - I'm slipping past
    {landmark}!"`) and `_POLICE_LINES` (4 lines) — lines 33-44.
  - `LANDMARKS` keyed by the negotiated `world.map_area` ("New York", "London",
    "Paris"); unknown settings use `_DEFAULT_LANDMARKS` ("downtown", "the old
    market", …) — lines 25-31.
- **Bluffing is built in**: the thief's template line is declared a lie ~40% of the
  time (`_template`, lines 68-75); the truth/lie **verdict is sealed** into the
  commit and audited later.
- Every hint (template or LLM) is hard-capped to `hint_max_words` (15) before it
  goes on the wire (`_cap`, lines 59-62).
- Fixed protocol strings (constants.py:80-83): `FALLBACK_HINT`, final caught hint
  `"You got me."`, `NO_HINT_PLACEHOLDER "(silence)"`.
- GUI reports this as game mode **"Python (template)"** with model "None"
  (gui/game_mode.py, book Table 22).

### LLM hook points

1. **Trash-talk providers** (`[trash_talk]` block; strategy/talk_providers.py):
   - `template` (default) — as above.
   - `claude_cli` — reuses the peer's `ClaudeCliProvider` (`claude -p`); system
     prompt is prepended to the user prompt (no separate channel).
   - `claude_api` — Anthropic Messages API, lazily imported `anthropic`, default
     model `claude-haiku-4-5`, max_tokens 200, native `system` param.
   - `ollama` — local HTTP call to `http://localhost:11434/api/generate` with
     `format:"json"` and native `system` field, stdlib urllib only.
   `LlmTrashTalk` (trash_talk.py:78-137) calls the model only every
   `every_n_steps` turns, enforces the step deadline via a ThreadPoolExecutor
   future timeout, and **falls back to the template on any error/timeout**. The
   system prompt pins the agreed map area + word cap and demands strict JSON
   `{"message", "verdict": "truth|lie", "reasoning"}`; `_extract_json` tolerates
   fences/prose. The full system+user prompt is sealed into the log
   (`prompt_discussion`) for the audit.
2. **The move brain** (`[strategy]` selector; strategy/__init__.py): `resolve_brain`
   loads `"package.module:ClassName"` (must subclass `BrainBase`) or defaults to the
   shipped heuristics. Students override `_pick_move(moves, state, belief)` and/or
   `_decide_move(state, belief, barriers_max)`. **The move is never LLM-driven** in
   this repo; the README allows LLM-driven tactics only by explicit mutual pre-game
   agreement (README.md:165-173).
3. **`ClaudeCliProvider`** (infra/llm_provider.py): pipes a temp prompt file into
   `claude -p --output-format json` with auth-hijacking env vars stripped; parses the
   JSON wrapper, extracts `result`, strips code fences, and accumulates token usage
   (input + cache creation + cache read + output) into `tokens_consumed` for the
   sealed per-step token accounting (summary.py:28-38). Wrapped by `GatedLlm` through
   the `ApiGatekeeper` (sdk.py:32-48). `StubLlm` returns unparseable text on purpose
   to force deterministic behavior in dev runs.

---

## 7. End-of-game JSON signing / reporting to the lecturer

### The four standardized artifacts (book Appendix F; report/artifacts.py + emit.py)

Written by `emit_series` into **`logs/<own group_id>/`** (so two peers on one
machine never collide), all named from the shared `game_id` and carrying the shared
`game_uid`; schema_version "1.1"; real examples in `docs/sample-run/`:

| File | Content | Signing |
|---|---|---|
| `declaration_<game_id>.json` | Pre-game declaration: both groups' identity, members, repos, MCP URLs, LLM model, 6-field hardware spec, timezone, token budget, num_sub_games, start/end times | per-group `signature` = SHA-256 over the canonical group block (artifact_helpers.py:68-80) |
| `config_<game_id>_g<NN>.json` | The agreed shared terms actually played in sub-game NN | `config_sha256` = canonical SHA-256 of the shared terms |
| `log_<game_id>_g<NN>.json` | Full sealed log: step-0 system_spec + every commit-revealed step (state, move, verdict, hint, prompt_discussion, tokens), summary, audit outcome | `mutual_agreement.sha256` = consensus signature over the records; `confirmed` = audit passed |
| `result_<game_id>.json` | Aggregated series result: per-sub-game rows (roles, result, winner_group, per-group score, audit flags), final totals, winner/series_tie, tokens per group | `mutual_agreement.sha256` = SHA-256 over the **symmetric** outcome only (game_id, aggregate, per-sub-game roles/result/winner/score — never per-peer tokens or timestamps, emit.py:111-120) so both peers' files hash identically |

`consensus_signature(data)` = SHA-256 over `json.dumps(data, sort_keys=True,
ensure_ascii=False)` (report_writer.py:22-25). The integration test asserts both
peers produce the **same** mutual sha256 and one shared game_uid across all four
files (tests/integration/test_mcp_match.py:180-190).

### Email to the lecturer (infra/email_sender.py)

`SimulationSdk.run_peer` emails the **result JSON** with subject
`"Police-Thief series result: winner <group> (reported by <role>)"` (sdk.py:106-108).
Safety defaults: `email.enabled = false` and `mode = "draft"` (creates a Gmail draft
via an **external `gg:email` skill script** invoked with `uv run`; the shipped paths
point at the lecturer's machine, so students must replace or keep it disabled). All
sends pass through the ApiGatekeeper (service "email"). Recipient in the shipped
config: `rmisegal+uoh26finalgame@gmail.com`.

### Legacy Hebrew report (report/report_writer.py)

`build_report` also writes a per-role `logs/{role}_match.json` (`{"summary":…,
"report":…}`) with Hebrew keys per book section 8 (`"סוג_דוח": "משחק_ליגה_רשמי"`,
result mapping capture→"לכידה", survival→"הישרדות", timeout→"תוצאה_טכנית",
tamper→"פסילת_זיוף"), the sealed spec declaration, the verified step log, and a
`"חתימת_קונסנזוס_משותפת"` consensus hash. Kept for back-compat; the replay player
accepts both formats (gui/replay_data.py:26-52).

---

## 8. Code quality observations

### File sizes (total lines incl. comments/license header; the repo's own rule is ≤150 *code* lines)

- **Over 150 total lines:** `gui/replay.py` (167), `shared/config.py` (164),
  `gui/player.py` (154). All pass the repo's own rule only because the 2-line
  copyright header + docstrings/comments are excluded; by raw wc they exceed 150.
- **Over 120 total lines (watch list):** `strategy/trash_talk.py` (143),
  `peer/sealing.py` (138), `gui/window.py` (130), `peer/runtime.py` (129),
  `sdk/sdk.py` (128), `infra/llm_provider.py` (127), `report/artifacts.py` (126),
  `report/emit.py` (124), `gui/replay_data.py` (124), `peer/control_link.py` (113 —
  under). Everything else is well under 120. The discipline is real: `runtime.py`
  was actively split into `handshake/turn_sender/summary/runtime_control` to stay
  small (comments say so explicitly, e.g. turn_sender.py:19-20).
- Total: ~4,400 lines of source across 46 files; ~3,400 lines of tests.

### Tests

- **254 test functions** (README claims 253) across 33 unit modules — essentially
  one test module per source module — plus a real two-server HTTP integration match
  and a 4-artifact series test (marked `slow`). Coverage gate: **fail_under = 85**
  with `gui/*`, `mcp_server.py`, `mcp_client.py`, `__main__.py` omitted
  (pyproject.toml:40-51). Fixtures build temp configs (tests/conftest.py); the
  transport protocol is duck-typed so unit tests use in-memory fakes.
- Ruff configured (E,F,W,I,N,UP,B,C4,SIM; line length 100).

### Patterns worth reusing

- **Mailbox transport abstraction**: MCP tools that only enqueue + a transport with
  a 5-method duck-typed API (`exchange_agreement/send_turn/poll_turn/
  exchange_audit/send_control`). Makes the entire game engine unit-testable without
  sockets, and makes the transport swappable.
- **Commit-reveal integrity** (crypto.py): canonical-JSON hashing, nonce reveal at
  audit, `tamper_forfeit` rule. Small, correct, fully tested.
- **Deterministic shared IDs** (game_ids.py): both peers derive `game_id`/`game_uid`
  from data they already share — no extra agreement round-trip.
- **Symmetric mutual signature** (emit.py:111-120): hashing only the symmetric
  outcome so both peers' result files agree byte-for-byte on the signature.
- **Shared-signed JSON vs private TOML config split**, plus the fail-fast
  `validate_agreement` before any port opens.
- **Injectable seams everywhere**: brain class selector, trash-talk provider,
  transport, listener callback, controls object, injectable clock in the rate
  limiter. GUI is a pure mirror over a listener/event queue.
- **Graceful shutdown races handled**: best-effort audit/control sends with
  timeouts, inbox draining on restart, port-in-use pre-flight with actionable error.
- Pure, I/O-free `domain/` and `report/artifacts.py` builders.

### Patterns to avoid / weaknesses

- **`shell=True` subprocess with string interpolation** in llm_provider.py:52,68
  (`type "file" | claude …`) — quoting/injection-fragile and Windows-flavored;
  prefer `subprocess.run([...], stdin=...)`.
- **New HTTP client + `asyncio.run` per message** (mcp_client.py:34-40) — a fresh
  event loop and connection for every turn/control send; fine at this scale, but a
  persistent client/session is cleaner and faster.
- **Busy-wait polling loops** (0.5s turn poll, 0.2s pause poll, 0.1s queue drain)
  instead of blocking waits/conditions — acceptable here, but wasteful.
- **`private` attribute reach-ins across modules**: `turn_sender`/`summary`/
  `runtime_control`/GUI freely touch `rt._config`, `rt._result`, `app._window` —
  the 150-line rule pushed cohesive code apart, trading encapsulation for file size.
- **Trust-based protocol outside the audit**: nothing prevents a peer from sending a
  malformed smell grid, absurd intensities (absorb only bounds-checks coordinates),
  or skipping its capture-claim duty; honesty is only enforced where the audit can
  catch it. Also `claim_response.caught` is trusted immediately at runtime
  (turn_handler.py:52-53) — the audit catches lies only post-game.
- **Timeout self-award**: on a silent opponent the waiting peer records itself the
  winner (runtime.py:115-117) with the audit skipped — unverifiable by the other
  side's artifacts.
- **Email path coupling** to the lecturer's local machine
  (`C:\Users\gal-t\.claude\skills\gg\email\...` in shipped TOML).
- Minor inconsistencies: `game.toml` `[game].sub_game_number` is unused by the
  series loop (live index wins); sample log's `code_version` "1.12" predates v3.0.0;
  `mcp_servers` values in each TOML point both roles at the same port; README says
  253 tests, repo has 254 test functions; `Decision.fallback/random_move` are
  vestigial ("reserved") but still surface in GUI labels.

---

## 9. Reuse recommendations (for a production-quality student project)

### Adopt (as-is or with light adaptation)

1. **`domain/crypto.py`** — commit-reveal sealing + `audit_records`. Small, pure,
   canonical-JSON based; this is the game's integrity backbone and matches the book.
2. **`domain/protocol.py` message shapes** and the **four MCP tool names**
   (`negotiate`, `receive_turn`, `submit_audit`, `receive_control`) — this is the
   de-facto interoperability contract if we ever need to play against another
   team's peer or the reference simulator.
3. **`domain/game_ids.py`** — deterministic `game_id`/`game_uid` derivation; zero
   protocol cost.
4. **`report/` package** (artifacts, artifact_helpers, artifact_schemas, emit) —
   the exact filenames, `links` block, `_schema` strings, canonical `config_sha256`
   and symmetric `mutual_agreement` hashing the lecturer's tooling expects. Copy the
   schemas verbatim; verify against `docs/sample-run/`.
5. **`domain/scoring.py`** — book scoring + tie rule as pure functions; keep and
   unit-test against the book's parameter table.
6. **Config philosophy**: shared-signed `game.json` overlaying a private `game.toml`
   (`_translate_shared` mapping) + `validate_agreement` fail-fast. Also the
   `ConfigManager` dotted-key accessor itself.
7. **The mailbox/inbox transport pattern** (queues behind MCP tools; duck-typed
   transport for tests) and the transport-kept-alive-across-sub-games series design
   with role alternation (`sdk/series.py:role_for`).
8. **Smell/belief math** (`smell.py`, `belief.py`) — correct, book-parameterized,
   and the foundation any better strategy builds on. Keep, then extend (e.g.
   barrier-aware diffusion, hint fusion).
9. **`shared/rate_limiter.py` + gatekeeper** pattern with injectable clock.
10. **ClaudeCliProvider's env-stripping idea** (STRIP_KEYS) and token-usage
    delta accounting — keep the idea even if the subprocess invocation is rewritten.

### Rewrite / replace

1. **The brains (`domain/brains.py`)** — mandatory: the greedy heuristics are
   explicitly the placeholder the assignment asks us to beat. Keep the
   `BrainBase`/`Decision`/`resolve_brain` seam, replace the policy (belief-aware
   pursuit/evasion, barrier planning, deception planning).
2. **`infra/mcp_client.py`** — keep the API, rewrite internals: persistent client,
   one event loop (or async runtime), structured retry/backoff, explicit message
   validation on receipt.
3. **`infra/llm_provider.py` subprocess layer** — drop `shell=True` string
   pipelines; pass the prompt via stdin with an argument list.
4. **`infra/email_sender.py`** — the gg:email skill dependency is
   lecturer-machine-specific; replace with our own submission mechanism (or plain
   SMTP/Gmail API) while keeping the draft-by-default safety posture.
5. **GUI** — Tkinter code is serviceable but tightly coupled via private-attribute
   reach-ins and excluded from tests; if a GUI is required, keep the
   listener/event-queue boundary and the replay hash re-verification idea, rebuild
   the widgets. The replay player's "verify every commit live" feature is worth
   re-implementing regardless of toolkit.
6. **Runtime decomposition** — keep the phases (handshake → turn loop → audit) but
   consider a single cohesive state-machine class instead of four helper modules
   mutating `rt._*`; enforce validation of inbound `TurnMessage` values (bounds,
   step monotonicity, smell-intensity sanity) which the reference skips.
7. **Timeout/technical-loss handling** — design a verifiable record for timeouts
   (e.g. sealed "no message by T" evidence) rather than the self-awarded win.

### Book-vs-code deltas to double-check against the book before reuse

- `num_games`: repo ships 1, book mandates 6 (must set in both `game.json`s).
- Movement default is 4-orthogonal + STAY per book; king moves are a legacy option —
  do not enable without agreement.
- The repo's `capture_claim`-every-MOVE and thief-answers-honestly flow, the 0/0
  technical-loss scoring, and the `tie_score` handling should each be re-verified
  against the book's binding parameter table, since **the book wins on conflict**.
