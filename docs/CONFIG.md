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
| `config/setup.json` | private | yes | App-level tunables: paths, the local UI port, feature flags. |
| `config/police/game.toml` | private | yes | This agent's own match settings (thief repo: `config/thief/`). |
| `config/rate_limits.json` | private | yes | Per-service API ceilings, validated against Appendix F at load. |
| `config/logging_config.json` | private | yes | Python `dictConfig` for the diagnostic channel. |
| `config/model_prices.json` | private | yes | Published list prices for the cost table. Not measured by us. |
| `.env` | secret | **no** | API keys only. Git-ignored, CI-gated. |
| `.env-example` | template | yes | The same keys with dummy values. |
| `data/map_areas.json` | private | yes | Landmark vocabulary for hints. **Content, not configuration** — adding a city should not mean editing a module. |

> **Three files, three scopes, no overlap.** `game.json` is *agreed with the
> opponent*; `<role>/game.toml` is *private but about the match*; `setup.json` is
> about the *application* and would be the same whoever we played. Keeping them
> apart is what stops a second source of truth for the same value.
>
> An earlier version of this document argued we did not need `setup.json` and
> that the TOML covered it. That was wrong in a way worth recording: nothing
> declared `[ui]` or `[paths]`, so every `manager.get("ui.port", 8000)` returned
> its own default — a hardcoded tunable wearing a config lookup's clothes, which
> the guidelines put at threshold zero.

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
| `[strategy.cop]` | `barrier_threshold` 0.40, `lookahead` 2, `claim_threshold` 0.12 | The dials the sweep varies. `barrier_threshold` decides matches: 0.05 captured 4 % of games, 0.40 captured 100 %. |
| `[strategy.thief]` | `horizon` 3, `stall_trigger` 3 | `stall_trigger` is how close to the survival horizon the thief stops taking chances. |

> **Scalars before sub-tables.** TOML assigns a bare key to the most recent
> table header, so writing `cop_class` *after* `[strategy.thief]` silently makes
> it a thief tunable — which handed `ThiefBrain` a `cop_class` argument and
> killed a live match at the first mini-game. The wiring now validates every
> dial against the brain's fields and fails at startup.

## 3b. Practice mode — `config/setup.json` → `practice`

| Key | Default | Effect |
|---|---|---|
| `practice.enabled` | `false` | When true, every report is **redirected** to `redirect_to` and its subject prefixed `[PRACTICE]`. |
| `practice.redirect_to` | the operator's address | Where practice reports actually go. |

Practice mode does **not** disable sending. The send is the step assignment 6
lost matches to, so a testing mode that skipped it would leave the riskiest path
untested; instead the mail is delivered for real, to us.

That puts the whole safety story on one string rewrite, which is why
`shared/practice.py` also enforces a second, independent invariant at the point
of no return:

> While practice mode is on, the outgoing recipient must **equal** the redirect
> address — anything else raises instead of sending.

So a rewrite that silently does not happen is a loud failure rather than mail to
the lecturer. A half-configured practice mode (enabled, no `redirect_to`)
refuses to send at all rather than falling through to the configured recipient.

The flag is read **fresh from disk** every time a sender is built, not cached at
boot. That is what lets the dashboard toggle take effect without a restart, and
it means the panel and the send path cannot disagree about which mode we are in.

Toggling it off through the UI is gated exactly like toggling it on: turning
practice *off* re-arms the lecturer's address, which is the graver direction.

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

## 6. Changing a config version (T-0323)

Every shipped config carries `version` / `_config_version`, and
`shared/version.py:SUPPORTED_CONFIG_VERSIONS` is the single place a new schema
is admitted.

**The order is the procedure:**

1. Add the new version to `SUPPORTED_CONFIG_VERSIONS`. Commit.
2. Bump the `version` field in the config files. Commit.
3. `uv run python scripts/check_all.py` — the config tests boot on the shipped
   files, so a mismatch fails here rather than at a match.

Doing it the other way round means the agent **refuses to boot on its own
configuration**. That refusal is correct and it is tested
(`test_config_version_bump.py::test_widening_the_supported_set_is_what_admits_a_new_version`),
so if you meet it, the fix is step 1 — not loosening the check.

**Why the check is strict.** A config the code does not understand is one that
will be *partly* understood, and partly-understood settings are how an agent
plays a game under terms it never agreed to. An absent version is refused the
same way as a wrong one: absent is not "probably current".

The error names both the offending version and the accepted ones, because the
person reading it is usually short of time.

## 7. Where a value should live

| If it is… | It goes in |
|---|---|
| agreed with the opponent | `config/game.json` (and `negotiation/terms.py`) |
| ours alone, tunable | `config/<role>/game.toml` |
| an API ceiling | `config/rate_limits.json` |
| a secret | `.env` |
| a physical or mathematical constant | `constants.py` |
| anything else | still not a literal in the source — the hardcoded-value gate is at threshold zero |
