# Configuration reference

**Version 1.00 · 2026-07-27 · guidelines §7.2–7.4**

Every configurable value, where it lives, and whether it is ours to change.

The single most important distinction in this document is between the two
config files, because getting it wrong is a rule breach rather than a bug:

* **`config/game.json` is shared and signed.** Both peers must hold a
  byte-identical copy. The handshake hashes it and refuses to play on any
  mismatch. Editing it mid-match does not change the game — it ends it.
* **`config/<role>/game.toml` is private and local.** Our ports, our URLs, our
  model choices. It never crosses the network and the opponent never sees it.

Where the two overlap, **the signed JSON wins**. A private file cannot weaken a
term we agreed to; `test_config.py::test_the_signed_contract_overrides_private_values`
enforces the direction.

---

## 1. File layout

| File | Scope | Committed | Purpose |
|---|---|---|---|
| `config/game.json` | shared, signed | yes | The agreed terms. Byte-identical with the opponent. |
| `config/police/game.toml` | private | yes | This agent's own settings (thief repo: `config/thief/`). |
| `config/rate_limits.json` | private | yes | Per-service API ceilings, validated against Appendix F at load. |
| `config/logging_config.json` | private | yes | Python `dictConfig` for the diagnostic channel. |
| `config/model_prices.json` | private | yes | Published list prices for the cost table. Not measured by us. |
| `.env` | secret | **no** | API keys only. Git-ignored, CI-gated. |
| `.env-example` | template | yes | The same keys with dummy values. |

> **Deviation from the guidelines' example layout, stated deliberately.** §7.2
> shows `config/setup.json` for app-level tunables. Ours live in the `[network]`,
> `[tunnel]` and `[llm]` sections of the private TOML instead. A second
> app-level file would be a second source of truth for ports and paths, and the
> failure mode of two config files that disagree is worse than the failure mode
> of one file with sections. Everything §7.2 asks to be configurable *is*
> configurable and versioned; only the filename differs.

## 2. Shared, signed terms — `config/game.json`

Changing any of these requires the opponent's agreement. Rule 12: a term may be
**raised, never lowered**, and Appendix F sets the floor.

| Key | Ours | Appendix F | Negotiable |
|---|---|---|---|
| `board_and_agents.grid_size` | 7 | ≥ 7 | raise only |
| `board_and_agents.num_agents` | 2 | = 2 | fixed |
| `board_and_agents.thief_start` | `[3,3]` | — | yes |
| `board_and_agents.cop_start` | `[0,0]` | — | yes |
| `board_and_agents.axis_origin_corner` | `top-left` | — | yes, must match |
| `board_and_agents.axis_start_index` | 0 | — | yes, must match |
| `world.map_area` | `New York` | — | yes (hint flavour only) |
| `world.hint_max_words` | 15 | — | yes |
| `movement_and_barriers.move_set` | `N,S,E,W,STAY` | fixed | no |
| `movement_and_barriers.max_barriers` | 14 | ≥ 14 | raise only |
| `movement_and_barriers.max_moves` | 35 | ≥ 35 | raise only |
| `movement_and_barriers.survival_threshold` | 35 | ≥ 35 | raise only |
| `scoring.*` | 20/5/5/10/2/0 | fixed | no |
| `pheromones.pheromone_center_intensity` | 0.9 | — | yes, must match |
| `pheromones.pheromone_decay` | 0.10 | — | yes, must match |
| `pheromones.pheromone_grid_size` | 5 | — | yes, must match |
| `pheromones.pheromone_min_center_intensity` | 0.5 | — | yes, must match |
| `network_and_league.response_timeout_sec` | 30 | 30 | yes |
| `network_and_league.watchdog_timeout_sec` | 60 | 60 | yes |
| `network_and_league.num_games` | 6 | 6 | yes |
| `network_and_league.token_budget_per_series` | 200000 | ~200k | yes |

**The wire shape is not this shape.** The reference signs a *flat* 14-key
dictionary and compares it for equality; `negotiation/terms.py` is the
translation, and it is interop-critical — a key spelled differently is a refusal
to play. See that module before editing anything here.

## 3. Private settings — `config/police/game.toml`

| Key | Default | Effect |
|---|---|---|
| `version` | `1.00` | Refuses to boot on an unsupported version. |
| `game.group_name` / `group_id` | `NajAmjad` / `najamjad` | Identity sent in the handshake; the opponent's declaration indexes both. |
| `game.members` | two names | Required by the opponent's declaration builder. |
| `game.repos.cop` / `.thief` | GitHub URLs | Cross-linked in the report (rule 49). |
| `network.my_port` | 8802 (thief: 8801) | Our MCP port. Both agents run locally on different ports. |
| `network.opponent_url` | `""` | **Set per match.** Preflight fails while empty. |
| `network.response_timeout_seconds` | 30 | How long we wait for their turn. |
| `network.watchdog_threshold_seconds` | 60 | Series-level stall detection. |
| `network.max_retries` | 3 | Retries before we call a turn timed out. |
| `tunnel.provider` / `hostname` / `name` | cloudflare / `cop.4laboratory.com` | A **named** tunnel: the hostname survives restarts, so the opponent's saved URL keeps working (ADR-004). |
| `llm.primary` / `fallback` | anthropic / deepseek | Provider chain; templates are the floor beneath both. |
| `llm.model` | `claude-haiku-4-5-20251001` | Hint model. |
| `llm.negotiation_model` | `claude-sonnet-5` | **Inert.** `PRD_negotiation.md` rejected LLM negotiation; see `docs/OPEN_ITEMS.md`. |
| `llm.every_n_steps` | 2 | Hint cadence. A **quality** dial, not a savings dial — measured at 46 % fewer tokens, but the budget has room either way. |
| `llm.series_token_budget` | 200000 | The agreed term. Exceeding it is a breach, not an expense. |
| `llm.project_token_budget` | 5000000 | Runaway-loop backstop, ~20× the projection. |
| `email.recipient` | Appendix F address | Rule 30 fixes the scope at `gmail.send`. |
| `email.mode` | `draft` | **Change to `send` for a counted match.** `draft` is the safe default while testing. |
| `strategy.cop_class` / `thief_class` | `""` | Empty means the shipped brains; a `"module:Attribute"` path loads a plugin (`docs/EXTENDING.md`). |

## 4. Rate limits — `config/rate_limits.json`

Validated against the Appendix F ceilings at load; a config above them refuses
to boot rather than quietly breaking a rule.

| Service | rpm | Why |
|---|---|---|
| `default` | 30 | Conservative for anything unnamed. |
| `gmail` | 30 | Protects the account (rule 30). |
| `mcp_peer` | 600 | **Outbound to the opponent.** They are our protocol partner, not a metered API; throttling here only risks missing their 30 s deadline. |
| `inbound_peer` | 3000 | **Inbound from the opponent.** A flood backstop, not a throttle — the bounded inbox queue is the real protection. At 120 we rejected a legitimate turn mid-series and lost the game to our own guard. |

## 5. Secrets

Never in code, never in a committed file, `os.environ` only.

`.gitignore` covers `.env`, `*.pem`, `*.key`, `credentials.json`, `token.json`
and `secrets/`, and `scripts/check_repo_rules.py` fails the build if one is ever
tracked — red-teamed in `tests/unit/test_scripts/test_gates_bite.py`, which
commits each forbidden file into a scratch tree and requires the gate to reject
it.

## 6. Changing a config version

Every shipped config carries `version` / `_config_version`. Bumping one without
adding it to `SUPPORTED_CONFIG_VERSIONS` makes the agent refuse to boot — which
is the intended behaviour, and is tested. The procedure is: add the new version
to the supported set **first**, ship the config second.

## 7. Where a value should live

| If it is… | It goes in |
|---|---|
| agreed with the opponent | `config/game.json` (and `negotiation/terms.py`) |
| ours alone, tunable | `config/<role>/game.toml` |
| an API ceiling | `config/rate_limits.json` |
| a secret | `.env` |
| a physical or mathematical constant | `constants.py` |
| anything else | still not a literal in the source — the hardcoded-value gate is at threshold zero |
