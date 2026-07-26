# NajAmjad — Thief Agent 🥷

The **thief side** of Team NajAmjad's final project for *Orchestration of AI Agents*:
a distributed cops-and-thieves game played peer-to-peer over MCP (FastMCP/HTTP) against other
teams' agents, with SHA-256 commit-reveal integrity and Gmail-API result reporting.

> **Companion repository (cop agent):** https://github.com/najikay/najamjad-cop
> The shared core package is byte-identical across both repos, enforced by
> `scripts/sync_core.py` in CI (see `docs/PLAN.md`, ADR-002).

**Status:** M1 walking skeleton — toolchain, compliance gates, and package scaffold.
This README grows into the full academic report + user manual as milestones land
(see `docs/TODO.md`, epic E22).

## Quickstart

```bash
uv sync                                   # install locked dependencies
uv run pytest tests/                      # run tests with coverage gate (>= 85%)
uv run ruff check .                       # lint — zero violations required
uv run python scripts/check_file_sizes.py # 150-code-line/file gate
uv run python scripts/check_all.py        # every CI gate, one PASS/FAIL verdict
```

## Command line

One console script per repo (`najamjad-thief` here, `najamjad-cop` in the
companion). Every verb is argument parsing plus a single SDK call — the CLI
holds no game logic, and a meta-test keeps it that way.

```bash
uv run najamjad-thief --help                     # every verb
uv run najamjad-thief version                    # code version (book rule 53)

uv run najamjad-thief preflight                  # match-day checklist
uv run najamjad-thief peer                       # go online: MCP server + tunnel + dashboard
uv run najamjad-thief peer --no-tunnel --no-dashboard   # local play, nothing exposed

# Re-hash every step of a log and print the verdict. Paths are literal —
# `<log>` would be read by the shell as a redirect, so use a real one:
uv run najamjad-thief replay tests/goldens/artifacts/log_segal-police-team-vs-segal-thief-team_g01.json
uv run najamjad-thief replay path/to/log.json --serve   # open the viewer instead
uv run najamjad-thief archive match.zip                 # bundle evidence (secrets excluded)
```

Run these from the repository root: the console script lives in this repo's
`.venv`, so `uv run` cannot find it from a parent directory.

**Cold start takes ~15 seconds** (importing the MCP stack) before `peer` is
accepting calls — it prints `Uvicorn running` when it is genuinely ready. Start
the agent well before a match rather than at the whistle.

**Exit codes**, because these run in scripts:

| Code | Meaning | Example |
|---|---|---|
| `0` | it worked | preflight ready, log verified |
| `1` | it ran, the answer was bad | not match-ready, log **TAMPERED** |
| `2` | it could not run | log file missing or unreadable |

A tampered log and a missing file are deliberately different codes: an audit
result must never be mistaken for a typo.

```bash
uv run python scripts/demo_dashboard.py            # dashboard over a played game
uv run python -m najamjad_agent.replay --log <log> # viewer without the CLI wrapper
```

## The dashboard

Belief heatmap, turn banner, dialogue with per-message model provenance, the
negotiation timeline, token budget, and report delivery status — pushed over a
WebSocket, never polled. It shows **local truth only** (book rules 8-9): the
opponent's position has no field in the read model, and a meta-test enforces
that the UI can reach the agent only through the SDK.

![Live dashboard](assets/dashboard-live.png)

## Replay viewer

Every step is re-hashed from its revealed `(payload, nonce)` and compared with
the stored commitment (book rule 20). Below, the lecturer's own sample log
replaying clean:

![Verified OK](assets/replay-verified-ok.png)

And the same log with one record edited after the fact — the forgery is
localised to exactly the step it was planted in, and rule 19 voids the game:

![Tampered](assets/replay-tampered.png)

See `assets/README.md` for how each image is reproduced.


## Documentation

| Document | Purpose |
|---|---|
| `docs/PRD.md` | Product requirements (FR-* ids, KPIs, milestones) |
| `docs/PLAN.md` | Architecture: C4 + FSM diagrams, ADR-001..014, module map |
| `docs/TODO.md` | 617-task build plan with traceability and progress |
| `docs/research/` | Source digests (project book, guidelines, reference simulator, retrospective) |

## Configuration & secrets

Copy `.env-example` to `.env` and fill in real values (never committed).
Rate limits live in `config/rate_limits.json`; the thief's game configs live under
`config/thief/` (kept strictly separate from the cop per book rules 1-2).

## License & attribution

MIT (see `LICENSE`). Protocol shapes and artifact schemas interoperate with the course
reference simulator [`rmisegal/Game-P2P-Cop-Chase`](https://github.com/rmisegal/Game-P2P-Cop-Chase)
(educational license); where book and code conflict, the book governs.
