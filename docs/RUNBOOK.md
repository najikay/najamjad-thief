# Match-day runbook

**Version 1.00 · 2026-07-26**

Every step with the exact command. Written to be followed literally under time
pressure with an opponent waiting — not to be read for understanding. The
reasoning lives in `PLAN.md`; this is the checklist.

Roles: `najamjad-cop` on port 8802, `najamjad-thief` on port 8801, so both can
run on one machine. Substitute the verb for whichever side you are running.

---

## 0. The evening before

| Step | Command | Expected |
|---|---|---|
| Both repos current | `git pull && uv sync` | no changes pending |
| All gates green | `uv run python scripts/check_all.py` | `ALL GATES PASSED` |
| Tunnel resolves | `curl -sI https://cop.4laboratory.com/mcp` | any HTTP response, not DNS failure |
| Gmail token valid | `uv run python scripts/authorise_gmail.py --check` | scope is `gmail.send` only |

A `406` or a JSON-RPC error from the tunnel means the agent is **healthy** — that
is a plain HTTP client hitting an MCP endpoint. A `502` means nothing is
listening.

## 1. Warm up — 5 minutes before

Cold start takes ~15 seconds (importing the MCP stack). Start early.

```bash
uv run najamjad-cop peer          # serves; prints the URL peers should use
```

Wait for `Uvicorn running`. That, not the first log line, is readiness.

## 2. Preflight — do not play on a red line

```bash
uv run najamjad-cop preflight
```

Exit `0` means ready. Exit `1` prints which check failed:

| Failing check | Fix |
|---|---|
| `opponent_url` | Not yet exchanged. Set it in `config/police/game.toml`. |
| `port` | Another agent is running; stop it or change `network.my_port`. |
| `config` | Version mismatch — do not hand-edit `game.json` mid-match. |
| `email_recipient` | Must be the address in Appendix F Table 20. |
| `tunnel` | Not applicable for local play; red only if a hostname is configured and wrong. |

## 3. Exchange URLs and agree terms

1. Send the opponent our public URL: `https://cop.4laboratory.com/mcp`.
2. Put theirs into `network.opponent_url`.
3. Re-run preflight — it must now be **exit 0**.
4. Both peers must hold a **byte-identical** `config/game.json`. The handshake
   verifies a SHA-256 signature over the terms and refuses to play on mismatch.
   Terms may be raised, never lowered (rule 12).

## 4. Play

```bash
uv run najamjad-cop match         # serves, then plays the agreed series
```

Watch the dashboard at http://127.0.0.1:8000/ — turn banner, belief heatmap,
dialogue, token budget, and the report panel.

Per mini-game the console prints role, end reason and the audit banner. **Every
game must read `Verified OK`.**

## 5. If something goes wrong mid-match

| Symptom | What it means | Action |
|---|---|---|
| Repeated `turn.timeout` | Opponent is slow or gone | The deadline path resolves it; do not restart. Their silence becomes their forfeit, not ours. |
| `TAMPERED` on a game | Their revealed records do not re-hash | Do **not** argue live. It is recorded; rule 19 voids the game for them. Keep the log. |
| Dashboard blank / red banner | Our UI only | Ignore during play. It cannot affect the game. |
| `llm.fallback` events | Provider down | Expected: the chain falls back to templates. The game continues. |
| Tunnel dies | Public name unreachable | The supervisor restarts it; the hostname is permanent so their saved URL still works. |
| We must stop | | Ctrl-C. It stops the tunnel cleanly — an unstopped tunnel points a public name at a dead port. |

**Never** hand-edit a log, a config, or an artifact mid-match. Every one of them
is signed or hashed, and editing turns a clean result into a provable forgery.

## 6. Audit

Automatic after each mini-game: we reveal our records, they reveal theirs, and
each side re-hashes the other's. To re-check afterwards:

```bash
uv run najamjad-cop replay workspace/artifacts/log_<game_id>_g01.json
```

Exit `0` = `Verified OK`. Exit `1` = `TAMPERED`, with the failing step named.

## 7. Reconcile and report

1. Compare our result with theirs; the dashboard's report panel shows the state.
2. `agreement` is `null` only while genuinely undecided — never as a stand-in for
   "we forgot" (the Assignment 6 defect).
3. Send the report. Rule 30: `gmail.send` scope only, to the Appendix F address.
4. **Both peers report** — rule 35 punishes not reporting as well as reporting
   falsely. Contradictory reports void the game for both.

If sending fails, the report panel turns red and names the reason. The artifact
is written regardless; a dead letter is recoverable, a missing artifact is not.

## 8. Archive and commit

```bash
uv run najamjad-cop archive workspace/match-<opponent>-<date>.zip
```

Bundles artifacts, event log and config; **refuses to include secrets** and says
which it withheld. Then commit the per-match config so the `github_commit`
recorded in step zero resolves (rule 53).

```bash
git add config/ && git commit -m "match vs <opponent>: agreed config" && git push
```

## 9. After the match

- [ ] All six mini-games audited `Verified OK`
- [ ] Result email sent, message id recorded
- [ ] Archive written and stored off the laptop
- [ ] Config commit pushed
- [ ] `docs/TODO.md` league table updated with the opponent and outcome
