# NajAmjad — Thief Agent 🥷

The **thief side** of Team NajAmjad's final project for *Orchestration of AI Agents*:
a distributed cops-and-thieves game played peer-to-peer over MCP (FastMCP/HTTP) against other
teams' agents, with SHA-256 commit-reveal integrity and Gmail-API result reporting.

> **Companion repository (cop agent):** https://github.com/najikay/najamjad-thief
> The shared core package is byte-identical across both repos, enforced by
> `scripts/sync_core.py` in CI (see `docs/PLAN.md`, ADR-002).

[![ci](https://github.com/najikay/najamjad-thief/actions/workflows/ci.yml/badge.svg)](https://github.com/najikay/najamjad-thief/actions/workflows/ci.yml)

**Team:** Naji Kayal · Amjad Abed — group `najamjad`
**Status:** M5 — plays a full audited series, interoperates with the course reference
simulator, dashboard and replay viewer live. Remaining work is tracked in `docs/TODO.md`.

---

## Contents

- [Installation](#installation) · [Command line](#command-line) · [Match-day workflow](#match-day-workflow)
- [Configuration](#configuration) · [The dashboard](#the-dashboard) · [Replay viewer](#replay-viewer)
- [Academic report](#academic-report): [the model](#the-model-a-dec-pomdp-neither-side-can-see) ·
  [orchestration dilemmas](#orchestration-dilemmas) · [strategies](#strategies-and-why-not-rl) ·
  [what testing against a stranger taught us](#what-testing-against-a-stranger-taught-us)
- [Documentation index](#documentation) · [License & attribution](#license--attribution)

---

## Installation

**Requirements**

| | |
|---|---|
| Python | 3.12+ (managed by uv — you do not need it pre-installed) |
| [uv](https://docs.astral.sh/uv/) | the only package manager used here (guidelines §8.4) |
| OS | Linux, macOS, or Windows via WSL2 — developed on WSL2 |
| Optional | `cloudflared` for a public tunnel; a Google Cloud project for report email |

```bash
git clone https://github.com/najikay/najamjad-thief.git
cd najamjad-thief
uv sync                       # installs the locked dependency set
uv run python scripts/check_all.py   # every CI gate, one PASS/FAIL verdict
```

`check_all.py` passing means the install is sound: lint, file-size limits, repo
rules, type checking and the full test suite.

**Secrets** — copy `.env-example` to `.env` and fill in real values. Nothing secret is ever
committed; `.gitignore` covers `.env`, `secrets/`, `token.json` and `credentials.json`, and a
CI gate fails the build if one is ever tracked (book rules 39-40).

```bash
cp .env-example .env          # then edit: ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, …
```

**Troubleshooting**

| Symptom | Cause and fix |
|---|---|
| `port 8801 … already in use` | Another agent is running. Stop it, or change `network.my_port` in `config/thief/game.toml`. |
| `peer` takes ~15 s to answer | Normal: importing the MCP stack. It prints `Uvicorn running` when genuinely ready — start well before a match. |
| Opponent reports us unreachable | Check the tunnel: `uv run najamjad-thief preflight`. A `502` means the agent is not running; a JSON-RPC error such as *"Client must accept text/event-stream"* means it **is** healthy — that is a browser hitting an MCP endpoint. |
| `Failed to spawn: najamjad-thief` | Run from the repository root; the console script lives in this repo's `.venv`. |
| OAuth browser never opens (WSL) | Expected — WSL has no default browser. Use `uv run python scripts/authorise_gmail.py --manual` and paste the URL yourself. |
| Everything is slow on `/mnt/c` | Windows-mounted filesystems are slow in WSL. The event log holds its handle open for exactly this reason; if you can, keep the workspace on the Linux filesystem. |

---

## Command line

One console script per repo (`najamjad-thief` here, `najamjad-cop` in the companion). Every
verb is argument parsing plus a single SDK call — the CLI holds no game logic, and a
meta-test keeps it that way.

```bash
uv run najamjad-thief --help                     # every verb
uv run najamjad-thief version                    # code version (book rule 53)

uv run najamjad-thief preflight                  # match-day checklist
uv run najamjad-thief peer                       # serve: MCP server + tunnel + dashboard
uv run najamjad-thief match                      # serve, then play the agreed series
uv run najamjad-thief peer --no-tunnel --no-dashboard   # local play, nothing exposed

# Re-hash every step of a log and print the verdict. Paths are literal —
# `<log>` would be read by the shell as a redirect, so use a real one:
uv run najamjad-thief replay tests/goldens/artifacts/log_segal-police-team-vs-segal-thief-team_g01.json
uv run najamjad-thief replay path/to/log.json --serve   # open the viewer instead
uv run najamjad-thief archive match.zip                 # bundle evidence (secrets excluded)
```

**Exit codes**, because these run in scripts:

| Code | Meaning | Example |
|---|---|---|
| `0` | it worked | preflight ready, log verified |
| `1` | it ran, the answer was bad | not match-ready, log **TAMPERED** |
| `2` | it could not run | log file missing or unreadable |

A tampered log and a missing file are deliberately different codes: an audit result must
never be mistaken for a typo.

**Development commands**

```bash
uv run python scripts/check_all.py                  # all CI gates, one verdict
uv run python scripts/self_play.py --games 100      # measure our brains vs baselines
uv run python scripts/demo_dashboard.py             # dashboard over a played game
uv run python scripts/two_process_match.py          # both repos as real processes
uv run python scripts/sync_core.py ../najamjad-thief   # verify the mirrored core
```

---

## Match-day workflow

The full procedure with exact commands is `docs/RUNBOOK.md`. In outline:

1. **Warm up** — start the agent early; cold start is ~15 s.
2. **Preflight** — `uv run najamjad-thief preflight`; exit 0 or do not play.
3. **Exchange URLs** — set `network.opponent_url` in `config/thief/game.toml`.
4. **Play** — `uv run najamjad-thief match`, dashboard on http://127.0.0.1:8000/.
5. **Audit** — automatic per mini-game; every game must read `Verified OK`.
6. **Report** — reconcile with the opponent, then send (rule 30: `gmail.send` only).
7. **Archive** — `uv run najamjad-thief archive match.zip` (secrets excluded).

---

## Configuration

| File | Role |
|---|---|
| `config/game.json` | **Shared, signed terms.** Both peers must hold a byte-identical copy; the handshake refuses to play on any mismatch. Ours is the opening proposal — every value at or above the Appendix F minimum (rule 12: raise, never lower). |
| `config/thief/game.toml` | **Private, local.** Our port, opponent URL, tunnel hostname, LLM choices, belief tuning. Never crosses the network. |
| `config/rate_limits.json` | Per-service limiter settings, validated against the Appendix F ceilings at load. |
| `.env` | Secrets only. Never committed. |

Parameters worth knowing:

| Key | Effect |
|---|---|
| `network.my_port` | Our MCP port (8801 thief / 8802 cop, so both run locally). |
| `network.opponent_url` | The only thing we know about the opponent. Preflight fails while empty. |
| `tunnel.hostname` | Permanent public name. A *named* tunnel keeps its URL across restarts — the defect that cost Assignment 6 the most time (ADR-004). |
| `llm.every_n_steps` | Hint cadence. A quality dial, not a savings dial — see `docs/TOKEN_BUDGET.md`. |
| `belief.smell_trust_weight` | How far we trust scent against a possibly-lying hint. |
| `movement_and_barriers.*` | Agreed rules. Changing these unilaterally breaks the signature. |

---

## The dashboard

Belief heatmap, turn banner, dialogue with per-message model provenance, the negotiation
timeline, token budget, and report delivery status — pushed over a WebSocket, never polled.
It shows **local truth only** (book rules 8-9): the opponent's position has no field in the
read model, and a meta-test enforces that the UI can reach the agent only through the SDK.

![Live dashboard](assets/dashboard-live.png)

## Replay viewer

Every step is re-hashed from its revealed `(payload, nonce)` and compared with the stored
commitment (book rule 20). Below, the lecturer's own sample log replaying clean:

![Verified OK](assets/replay-verified-ok.png)

And the same log with one record edited after the fact — the forgery is localised to exactly
the step it was planted in, and rule 19 voids the game:

![Tampered](assets/replay-tampered.png)

See `assets/README.md` for how each image is reproduced.

---

## Academic report

### The model: a Dec-POMDP neither side can see

The game is a **decentralised, partially observable Markov decision process**. Neither agent
observes the true state: positions are sealed inside commitments until the end-of-game audit,
so each peer holds a *belief* over where the other might be and acts on that.

Two observation channels, with opposite trust properties:

- **Scent** — a decaying pheromone trail the opponent emits involuntarily and *cannot fake*
  (book PAGE 22). Unfakeable but blurry.
- **Hints** — free natural language, which the rules explicitly permit to be a lie
  (rules 26-27). Precise but untrustworthy.

Our belief engine fuses them: diffusion for movement, a scent-likelihood update, and a
credibility weight per opponent that rises and falls as their hints agree or disagree with the
trail. The full derivation is in `docs/PRD_belief_engine.md`.

Three findings from building it, each of which changed the design:

- **Scent decay had a fixed point.** Relative decay rounded to three decimals never reached
  zero, so dead trails polluted belief forever. Fixed with an explicit epsilon.
- **Multiplicative fusion double-counted** the cumulative scent field and left belief lagging a
  moving opponent by ~5 cells. Replaced with a robust mixture update.
- **A flat likelihood parked belief mid-trail.** Sharpening plus an *additive* floor fixed it;
  a clamp made faint scent indistinguishable from none.

### Orchestration dilemmas

**One gateway, or many callers?** Book rule 3 mandates an orchestrator, and we took it
literally: peripheral modules never call each other. The belief engine knows nothing of the
transport, strategy knows nothing of crypto, the transport knows nothing of the rules. That is
what makes the whole turn loop testable against fakes — the seam Assignment 6 never had.

**How much to trust a fake.** Our sharpest lesson. Three separate defects survived 1,500
passing tests because the fakes were *kinder than the wire*: a fake transport that wrapped an
audit payload the real one did not, an in-memory link that never blocked, and peers that only
ever played themselves. Interop can only be tested against something you did not write.

**Where to put the deadline.** A peer that answers forever must not hold us in a decided game,
and a peer that goes quiet must not become our technical loss. Every wait is bounded and every
ending is *announced* rather than assumed — see below.

**Rate limiting our own protocol.** The gatekeeper exists to be a good citizen towards
Anthropic and Gmail. Applying it to the opponent nearly cost us games: our own limiter could
have delayed a reply past their 30-second deadline.

### Strategies, and why not RL

**Cop** — belief-directed pursuit with lookahead diffusion, plus barrier placement scored by
how much freedom it denies the *likely* thief cells rather than by raw distance. Standing next
to a cell you cannot enter is worth nothing.

**Thief** — survival-horizon evasion, not greedy distance maximisation. The greedy move often
walks into a corner that is one barrier from a capture; we search the horizon for cells that
keep escape routes open.

**Hint policy** — bluffing is a strategic resource with a cost: a claim discloses the claimer's
cell, so a false capture claim hands the thief our exact position for nothing.

**No reinforcement learning**, deliberately:

- Only ~60 real games are available across the whole league — nowhere near enough to learn a
  policy over a state space this size.
- Opponent behaviour is non-stationary; every team ships something different.
- Non-determinism would break replay, and replay is a graded deliverable.
- The heuristics already beat the baseline decisively (below), so RL would be risk without
  measured upside.

Instead we do **online opponent modelling** sized to the ~210 observations a series actually
provides — hint credibility, move tendencies, barrier response.

**Measured** through the real match machinery on **held-out games** — seed 11,
never used while tuning, 60 games per matchup:

| matchup | captures | rate | 95 % Wilson CI |
|---|---|---|---|
| greedy cop vs our thief | 0/60 | **0 %** (100 % survival) | 0–6 % |
| our cop vs greedy thief | 60/60 | **100 %** | 94–100 % |
| greedy vs greedy (reference) | 4/60 | 6.7 % | 2.6–16 % |

Zero peer disagreements and zero audit failures across all 180 games.

![our brains vs the greedy baseline](assets/baseline-comparison.png)

**The caveat this repository is obliged to state.** Our thief's 100 % survival
is measured against the *greedy* cop. Against our own cop it survives about 4 %
of games, and sweeping `thief.horizon` across 1–5 does not move it — every value
is caught in 23 or 24 of 24 games, differences well inside the confidence
intervals. So this is not a tuning problem, and the headline number is a
statement about the opponent rather than about the evader. An opponent whose cop
is as good as ours should be expected to catch our thief. It is recorded as the
project's largest competitive risk in `docs/OPEN_ITEMS.md`.

For the cop side, one tunable decides the match:

![which knob decides the game](assets/sensitivity-tornado.png)

`barrier_threshold` swings the capture rate from **4 % to 100 %** across its
range, because a barrier is impassable for *both* sides — a cop that walls on
weak evidence fences itself away from the thief it is chasing.

Full derivations, confidence intervals, the token-cost table and the references
are in **`notebooks/analysis.ipynb`**. Reproduce with:

```bash
uv run python scripts/baselines.py --games 60 --seed 11   # held-out comparison
uv run python scripts/sweep.py --games 24 --seed 7        # sensitivity sweeps
uv run python scripts/measure_tokens.py                   # token census
```

### What testing against a stranger taught us

We cloned the course reference simulator and pointed it at us. **Nothing worked, in either
direction.** The reference names the MCP tool argument `message` on three tools and `payload`
on one; we sent `payload` to all four and accepted only `payload`. Every turn and every
proposal was rejected by argument binding *before a single byte of game logic ran* — against
any agent built on the reference, which is most of the class.

Four more incompatibilities followed: a required `timestamp` we never sent, a `claimed_cell`
field their parser rejects outright, and three claim fields whose types differed. Then the
audit reveal turned out to be sent as a bare list where the schema declares an envelope, so
both peers recorded **TAMPERED** for games nobody had cheated in.

Every one of those passed our own tests. The commit-reveal core, by contrast, survived contact
unchanged: our `commit_of` reproduces the reference's signature byte for byte.

The lesson we would carry to any distributed project: **a green test suite proves your code
agrees with your assumptions, not that your assumptions are right.**

---

## Documentation

| Document | Purpose |
|---|---|
| `docs/PRD.md` | Product requirements (FR-* ids, KPIs, milestones) |
| `docs/PLAN.md` | Architecture: C4 + FSM diagrams, ADR-001..014, module map |
| `docs/TODO.md` | 617-task build plan with traceability and progress |
| `docs/PROTOCOL.md` | What crosses the wire, and what never does |
| `docs/SECURITY.md` | Threat model, prompt-injection defences, secret handling |
| `docs/UX.md` | Nielsen heuristics mapped to dashboard decisions; accessibility |
| `docs/EXTENDING.md` | The four extension seams, with a worked plugin |
| `docs/CONFIG.md` | Every config key, its file, and its Appendix F negotiability |
| `docs/CI.md` | What each gate checks and how to reproduce a failure |
| `CONTRIBUTING.md` | Conventions: core sync, commits, tests, match-day freeze |
| `docs/ISO25010.md` | ISO/IEC 25010 quality characteristics mapped to evidence |
| `docs/edge-cases.md` | Every handled boundary condition, each linking its test |
| `docs/TOKEN_BUDGET.md` | Measured token consumption and the cost model |
| `docs/OPEN_ITEMS.md` | What is known to be incomplete, with the evidence |
| `notebooks/analysis.ipynb` | Sensitivity studies, baselines, cost table, references |
| `docs/PRD_belief_engine.md` · `PRD_commit_reveal.md` · `PRD_llm_router.md` | Mechanism designs |
| `docs/runbook-network.md` | Tunnel and connectivity procedures |
| `docs/research/` | Source digests (book, guidelines, reference simulator, A6 retrospective) |

---

## License & attribution

MIT (see `LICENSE`). Protocol shapes and artifact schemas interoperate with the course
reference simulator [`rmisegal/Game-P2P-Cop-Chase`](https://github.com/rmisegal/Game-P2P-Cop-Chase)
(educational license); where book and code conflict, the book governs.

Built with [FastMCP](https://github.com/jlowin/fastmcp), [FastAPI](https://fastapi.tiangolo.com/),
[pydantic](https://docs.pydantic.dev/), and [uv](https://docs.astral.sh/uv/).
