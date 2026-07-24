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
```

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
