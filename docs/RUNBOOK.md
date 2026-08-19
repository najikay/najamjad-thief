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
| Pre-match smoke | `uv run python scripts/pre_match_smoke.py` | `MATCH READY` (~50 s) |
| Tunnel resolves | `curl -sI https://cop.4laboratory.com/mcp` | any HTTP response, not DNS failure |
| Gmail token valid | `uv run python scripts/authorise_gmail.py --check` | scope is `gmail.send` only |

A `406` or a JSON-RPC error from the tunnel means the agent is **healthy** — that
is a plain HTTP client hitting an MCP endpoint. A `502` means nothing is
listening.

## 0.5 The warm-up game — MANDATORY, and never counted

**Never count first contact with an opponent** (rule 52). Play them an uncounted
warm-up game first, every time, with every team.

Every interop defect this project has hit was invisible until two
implementations that did not share authorship met: the MCP argument-name
mismatch, four turn-message incompatibilities, an audit reveal rejected on the
wire, and our own step guard silently ending the series after game 1. Each would
have cost a counted game.

Before the warm-up, fill in `matches/<opponent>/profile.md` — copy it from
`matches/_template/`. After the warm-up, complete the protocol section from what
you observed. **Anything still unknown there is a reason to run a second
warm-up, not to start counting.**

| Step | Command |
|---|---|
| Create the match folder | `cp -r matches/_template matches/<opponent>` |
| Fill the profile before playing | edit `matches/<opponent>/profile.md` |
| Play the warm-up | as §6, with `num_games` lowered if they prefer |
| Log everything live | `matches/<opponent>/incidents.md` |
| Mark them `warmed` | `matches/opponents.md` |

## 0.7 Freeze discipline

**No code changes during a match.** Rule 53 requires the `github_commit` declared
at step zero to be the code actually played, and that is checkable.

```bash
git status          # MUST be empty before you declare the hash
git rev-parse HEAD  # this is what you declare — paste it into profile.md now
```

Between matches, changes land as commits so each match's declared hash is exact.
Something broken mid-match goes in `incidents.md` and gets fixed afterwards.

## 1. Warm up — 5 minutes before

Cold start takes ~15 seconds (importing the MCP stack). Start early.

```bash
uv run najamjad-cop peer          # serves; prints the URL peers should use
```

Wait for `Uvicorn running`. That, not the first log line, is readiness.

## 2. Write the opponent card

Their URL and `group_id` go in a card, not in a tracked config file. One command
writes it into **both** repos:

```bash
uv run python scripts/match_day.py card --team <name> \
    --url https://their.host/mcp --group-id <id-their-handshake-declares>
```

A wrong `group_id` is survivable — the filer renames it to whatever their
identity actually declares — but a wrong URL is not. Quick-tunnel addresses
rotate, so re-ask before every match.

## 3. Arm the run

```bash
uv run python scripts/match_day.py practice   # draft email + FULL strength
uv run python scripts/match_day.py warmup     # draft email + SANDBAGGED
uv run python scripts/match_day.py counted    # send email + FULL strength
```

These write `strength.level` and `email.mode` into **both** repos' private
config, and the level now reaches **both brains**. The cop had no strength dial
at all until 2026-08-13, so a sandbagged warm-up played our real cop policy in
three of six sub-games; at reduced strength the cop now walks the belief peak
instead of intercepting, lays no barriers and demands 3x the belief before it
claims. Note what sandbagging still cannot hide: on a 7x7 board every sane
pursuit walks toward the peak, so the reduced cop picks a different *move* in
only about 3 of 49 positions. The weakening is in barriers and claims, which is
where a cop's strength actually lives.

After a `warmup` you are sandbagged until you say otherwise — that has
already cost one series, played at the deliberately weak brain without noticing.

## 4. Preflight — do not play on a red line

```bash
uv run najamjad-cop preflight --opponent <name> --practice
```

Exit `0` means ready. Exit `1` prints which check failed:

| Failing check | Fix |
|---|---|
| `opponent_url` | No card, or a mistyped `--opponent`. The error names the cards that exist. |
| `opponent_tools` | Their agent is not up. `502` = tunnel alive, origin down; wait and re-run. |
| `port` | Another agent is running; stop it or change `network.my_port`. |
| `config` | Version mismatch — do not hand-edit `game.json` mid-match. |
| `email_recipient` | Must be the address in Appendix F Table 20. |
| `tunnel` | Not applicable for local play; red only if a hostname is configured and wrong. |

Drop `--practice` for a counted run; the guard refuses a counted match unless
`email.mode` reads `send` and `strength.level` reads `full`.

## 5. Exchange URLs and agree roles

1. Send the opponent the URL **the repo you will run** serves:
   `https://cop.4laboratory.com/mcp` from `najamjad-cop`,
   `https://thief.4laboratory.com/mcp` from `najamjad-thief`.
2. **Agree who opens as cop.** Roles are *not* negotiated — each side picks
   `first_role` locally from its config directory, and we bind
   `expected_sender` to the opposite. If both sides open as cop, every inbound
   turn and audit reveal is refused and neither side can move. Run the thief
   repo to open as thief.
3. Re-run preflight — it must now be **exit 0**.
4. Both peers must hold a **byte-identical** `config/game.json`. The handshake
   verifies a SHA-256 signature over the terms and refuses to play on mismatch.
   Terms may be raised, never lowered (rule 12).

## 6. Play

```bash
uv run najamjad-cop match --opponent <name> --tunnel --dashboard \
    --dashboard-host 0.0.0.0 --practice --talk
```

`--tunnel` and `--dashboard` default **off** on `match` (they default on for
`peer`), and a run is **counted** unless `--practice` is passed. A bare
`uv run najamjad-cop match` is therefore a counted, tunnel-less, blind run.

Choose what we transmit to match the opponent:

| They send | Use | Measured on |
|---|---|---|
| scent and hints | `--talk` (the shipped default) | |
| **scent, no hints** | `--no-hints` | **vibecode** — 68 frames, 0 carried hint text |
| hints, no scent | `--scent none --hints` | uoh-ay26 — a hint on all 135 records, not one scent cell |
| nothing | `--quiet` | uoh-sqak |

Read the column on the right before choosing: each of those is a measurement
from `workspace/events.jsonl`, not a recollection. `scripts/scent_parity.py`
prints both sides' profile for any window, and it exists because "they send no
hints" was asserted about one opponent from their *sealed records*, which
structurally cannot carry a hint in their build.

`--quiet` also skips the vendor call, so it costs zero tokens. None of these
change the move: emission is a disclosure dial, never a strategy one.

Watch the dashboard at http://127.0.0.1:8000/ — turn banner, belief heatmap,
dialogue, token budget, and the report panel. On WSL2, pass
`--dashboard-host 0.0.0.0` and open it on the WSL address if a Windows browser
cannot reach loopback. Put it back to loopback for a counted match (rules 8-9).

`--dashboard-host` takes `HOST`, `HOST:PORT`, or `:PORT`. **In a split match
give the second process `--dashboard-host :8010`**, or it is refused the port
and runs blind. Whichever panel you open, read the role tag beside the title in
the header: it says `thief` or `police`, and it is the difference between our
thief at the agreed [3,3] and our cop at [0,0]. Mistaking one for the other is
what sent us hunting a starting-position bug that the engine never had.

**Ctrl+C when you have finished reading the panels.** The process keeps serving
after the series ends, and a forgotten run holds the port against the next one.

Per mini-game the console prints role, end reason and the audit banner. **Every
game must read `Verified OK`.**

## 7. If something goes wrong mid-match

| Symptom | What it means | Action |
|---|---|---|
| Long silence *between* sub-games | Their next process is binding | **Expected. Do not Ctrl-C.** A peer that runs each sub-game as a fresh process leaves its door 502 for a minute or two at every boundary. `network.handshake_retries = 8` gives ~6 minutes of patience against a gap measured at 131 s, so quiet here is the fix working. |
| `client.session_dropped` at a boundary | Our own session being replaced | Expected, once per sub-game, before the handshake. A peer's fresh process makes the socket we held a corpse; reusing it hangs every call to the cap while a bare `curl` reads a healthy 406. |
| `Session termination failed: 502` | The far process was already gone | Harmless SDK warning from that same drop. We are closing a session to a peer that has already torn down, which is why we are closing it. |
| Repeated `turn.timeout` | Opponent is slow or gone | The deadline path resolves it; do not restart. Their silence becomes their forfeit, not ours. |
| `TAMPERED` on a game | Their revealed records do not re-hash | Do **not** argue live. It is recorded; rule 19 voids the game for them. Keep the log. |
| Dashboard blank / red banner | Our UI only | Ignore during play. It cannot affect the game. |
| `llm.fallback` events | Provider down | Expected: the chain falls back to templates. The game continues. |
| Tunnel dies | Public name unreachable | The supervisor restarts it; the hostname is permanent so their saved URL still works. |
| We must stop | | Ctrl-C. It stops the tunnel cleanly — an unstopped tunnel points a public name at a dead port. |

**Never** hand-edit a log, a config, or an artifact mid-match. Every one of them
is signed or hashed, and editing turns a clean result into a provable forgery.

## 8. Audit

Automatic after each mini-game: we reveal our records, they reveal theirs, and
each side re-hashes the other's. To re-check afterwards:

```bash
uv run najamjad-cop replay workspace/artifacts/log_<game_id>_g01.json
```

Exit `0` = `Verified OK`. Exit `1` = `TAMPERED`, with the failing step named.

## 9. Reconcile and report

1. Compare our result with theirs; the dashboard's report panel shows the state.
2. `agreement` is `null` only while genuinely undecided — never as a stand-in for
   "we forgot" (the Assignment 6 defect).
3. Send the report. Rule 30: `gmail.send` scope only, to the Appendix F address.
4. **Both peers report** — rule 35 punishes not reporting as well as reporting
   falsely. Contradictory reports void the game for both.

If sending fails, the report panel turns red and names the reason. The artifact
is written regardless; a dead letter is recoverable, a missing artifact is not.

## 10. Archive and commit

```bash
uv run najamjad-cop archive workspace/match-<opponent>-<date>.zip
```

Bundles artifacts, event log and config; **refuses to include secrets** and says
which it withheld. Then commit the per-match config so the `github_commit`
recorded in step zero resolves (rule 53).

```bash
git add config/ && git commit -m "match vs <opponent>: agreed config" && git push
```

## 11. After the match

Run the mechanical half first — it re-hashes every log, checks the games share a
`game_uid`, and refuses if the working tree is dirty:

```bash
uv run python scripts/post_match.py --opponent <name>
```

Then the half no script can do:

- [ ] Our result compared with theirs **before sending** — a disagreement voids
      the game for both of us (rules 33-35)
- [ ] Result email sent, message id recorded in `matches/opponents.md`
- [ ] Archive written and stored off the laptop
- [ ] Config commit pushed; the declared `github_commit` opens on GitHub
- [ ] `matches/<opponent>/incidents.md` triaged: defect / adapter profile / accept
- [ ] `matches/opponents.md` counted-game ledger and standings updated

The campaign around all of this — recruiting, scheduling, the contingency if too
few opponents confirm — is `docs/LEAGUE_OPS.md`.
