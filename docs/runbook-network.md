# Runbook — public exposure, tunnels, and match-day preflight

**Version 1.00 · 2026-07-25**

The book requires each agent's MCP server to be reachable from the public
internet (rule 10). This runbook is the procedure for getting there and for
proving it works *before* a match rather than during one.

> **The one rule that matters:** the public hostname must be **permanent**.
> Quick tunnels mint a new random hostname on every restart — that single fact
> cost Assignment 6 more time than any code defect. Our hostname comes from
> config and is never scraped from process output.

---

## 1. Choose a provider (operator decision — risk R4)

| Provider | What it needs | Result |
|---|---|---|
| **Cloudflare named tunnel** (default, CHOSEN) | `4laboratory.com`, registered via Cloudflare 2026-07-25 | `https://cop.4laboratory.com/mcp`, stable forever |
| **ngrok reserved domain** (fallback) | free ngrok account (1 static domain) | `https://<name>.ngrok.app/mcp`, stable |

Switching between them is a **config change only** — `tunnel.provider` — with no
code change (ADR-004, proven by `test_switching_provider_needs_no_code_change`).

Two agents need two hostnames (cop and thief). On ngrok's free tier that means
two accounts or one paid plan; on Cloudflare, two DNS routes on one tunnel.

## 2. Cloudflare setup (once)

```bash
# 1. install
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared && sudo mv cloudflared /usr/local/bin/

# 2. authenticate (opens a browser; pick the zone you control)
cloudflared tunnel login

# 3. create one named tunnel per agent
cloudflared tunnel create najamjad-cop
cloudflared tunnel create najamjad-thief

# 4. route a stable hostname to each
cloudflared tunnel route dns najamjad-cop   cop.4laboratory.com
cloudflared tunnel route dns najamjad-thief thief.4laboratory.com
```

Credentials land in `~/.cloudflared/<uuid>.json`. **They never enter the repo**
— `.gitignore` covers `*.json` credentials via `credentials.json` and the
secret-scan gate checks tracked files.

Then set, in `config/police/game.toml`:

```toml
[tunnel]
provider = "cloudflare"
hostname = "cop.4laboratory.com"
name     = "najamjad-cop"
```

The agent supervises the tunnel process itself: it restarts it on unexpected
exit and emits `tunnel.up` / `tunnel.down` / `tunnel.restarted` events to the
dashboard.

## 3. ngrok fallback

```bash
ngrok config add-authtoken <token>
```

```toml
[tunnel]
provider = "ngrok"
hostname = "najamjad-cop.ngrok.app"   # the RESERVED domain, not a random one
```

Nothing else changes.

## 4. WSL2 notes

- The FastMCP server binds `127.0.0.1` and the tunnel connects **outbound**, so
  no Windows port-forwarding or firewall rule is required. This is the main
  reason to prefer a tunnel over exposing a port directly.
- Run `cloudflared` inside the same WSL distro as the agent; a tunnel started on
  the Windows side cannot see `127.0.0.1` in WSL.
- If the WSL clock drifts after a laptop sleep (it does), fix it before a match:
  `sudo hwclock -s`. Preflight's clock check catches this.

## 5. Second machine / two agents

Cop and thief **must** run as separate processes with separate config
directories (book rules 1-2 — sharing state disqualifies the solution). Two
options:

1. **Two shells on one machine**: ports 8802 (cop) and 8801 (thief), two
   tunnels. Simplest, and what CI exercises.
2. **Two machines**: identical setup per machine; only `tunnel.hostname`,
   `network.my_port` and the role config directory differ.

## 6. Match-day preflight (always run this)

```bash
uv run najamjad-cop preflight
```

It prints one checklist and exits nonzero if anything is red:

| Check | What a red line means |
|---|---|
| `tunnel` | the public hostname could not be reached at all — a missing DNS route |
| `clock` | skew is inside tolerance, so deadlines fire when they should |
| `gmail-token` | the stored token **refreshed for real**, not merely parsed (A6's silent killer) |
| `llm-providers` | Anthropic and DeepSeek answer through the gatekeeper |
| `tokens` | enough budget remains to finish a whole match |
| `contract` | the signed `game.json` hash matches what we agreed |

Every check runs even if an earlier one fails, so one run shows the whole
picture.

### What the `tunnel` line does and does not prove

Read this one carefully, because until 2026-08-12 it lied: the check returned
the configured hostname unchanged, so it printed `PASS` for a name with nothing
behind it while this page claimed it performed a self-call.

It now probes the hostname and reports one of three things:

| Line | Meaning |
|---|---|
| `our server answered through … (HTTP 406)` | **Proof.** Our agent replied through the public name. |
| `… resolves but nothing is serving it (HTTP 502/530)` | DNS and the tunnel edge exist; nothing is behind them. **Not a failure** — it is the normal state before you start the agent, which is when preflight is designed to run (`port` passes only while the port is still *free*). |
| `could not be reached` | **Red.** No such host or no DNS route. Starting the agent will not fix it. |

So a green preflight is *not* a promise that an opponent can reach you. Bring
the agent and the tunnel up, then curl the public URL yourself before the T —
which is what the agreed T protocol has both sides do anyway.

## 7. When the tunnel misbehaves mid-match

1. The supervisor restarts it automatically and emits `tunnel.restarted` — the
   URL is unchanged, so the opponent needs to do nothing.
2. If restarts repeat, the opponent's turns still queue; our deadline tracker
   bounds the wait and produces sealed timeout evidence rather than hanging.
3. Switch provider only between mini-games: edit `tunnel.provider`, restart,
   and send the opponent the new URL. Prefer finishing the series first.

## 8. Outstanding operator tasks

- [x] **T-1101** — domain decided: **`4laboratory.com`** on Cloudflare
      (registrar + DNS), recorded as the ADR-004 addendum below.
- [x] **T-1109 (cop side verified 2026-07-25)** — both named tunnels created
      (`najamjad-cop`, `najamjad-thief`) with DNS routes. A real MCP call was
      made through `https://cop.4laboratory.com/mcp` from outside: all four
      tools listed, `receive_turn` returned `{"accepted": true}`, and the
      server logged `inbox.accepted` — the message reached the game queue, not
      merely the HTTP layer.
- [x] **T-1109 complete (2026-07-25)** — both hostnames verified from an
      external device. A real MCP call succeeded through each public URL (all
      four tools listed, `receive_turn` accepted, `inbox.accepted` logged), and
      a browser on a separate device received our server's own JSON-RPC error:
      `{"error":{"code":-32600,"message":"Not Acceptable: Client must accept
      text/event-stream"}}` — a Cloudflare error page would look nothing like
      that, so this is proof the request reached *our agent*.

### Reading the response (match-day triage)

| What you see | Meaning |
|---|---|
| JSON-RPC `-32600 … must accept text/event-stream` | **Healthy.** Our MCP server answered. |
| HTTP 406 (bare) | Healthy — same thing without a JSON body. |
| **502 Bad Gateway** | The tunnel is up but **the agent is not running**. Start the server. |
| DNS failure / no such host | The DNS route is missing; re-run `cloudflared tunnel route dns`. |

**The trap we hit twice:** the tunnel and the agent are independent processes.
A running tunnel proves nothing about the agent — cloudflared happily stays up
and returns 502 for every request. This is exactly why preflight performs a
**self-call through the public URL** instead of checking that cloudflared is
alive.

### Verified startup sequence (cop)

```bash
# terminal 1 — the agent's MCP server
uv run python -c "from najamjad_agent.net.inbox import Inboxes; \
from najamjad_agent.net.mcp_server import PeerServer; import time; \
s=PeerServer(Inboxes(), port=8802); s.start(); time.sleep(3600)"

# terminal 2 — the tunnel (URL never changes)
cloudflared tunnel run --url http://127.0.0.1:8802 najamjad-cop
```

A bare `curl https://cop.4laboratory.com/mcp` returns **HTTP 406**, and that is
the healthy answer: MCP requires specific headers, so 406 proves our server —
not Cloudflare — replied.

## 9. ADR-004 addendum — provider decision (2026-07-25)

**Decision:** Cloudflare named tunnels on `4laboratory.com`, registered through
Cloudflare Registrar (at-cost, no markup, and the zone is already there).

**Hostnames:** `cop.4laboratory.com` and `thief.4laboratory.com`, one named
tunnel each, set in `config/<role>/game.toml` under `[tunnel]`.

**Why not ngrok:** the free tier gives one reserved domain per account, and we
need two simultaneous public hostnames. It stays wired as the fallback — a
`tunnel.provider` change, no code — if Cloudflare is unavailable on match day.

**Why a paid domain at all:** a hostname that can change (quick tunnels) or
disappear (free TLDs) is the exact failure that cost Assignment 6 the most
time. The domain outlives the course and is reusable for other projects.

---

## The stall: what it actually was (2026-08-04)

Three separate defects wore the same costume — "our cop stops sending after
~20 steps". None of them was DNS, which is what we told the opponent it was.

### 1. We dialled an address they had already left

Their handshake identity carries `mcp_servers` and always has. We logged it and
kept dialling `network.opponent_url`, typed in before the match.

uoh-sqak run **ngrok free, whose hostname re-mints every session** — written on
their own opponent card. The moment they restart an agent mid-series, the
address we hold is dead and stays dead for the rest of the match. Every symptom
follows from that one cached string:

| symptom | why |
|---|---|
| their access log shows zero errors | our requests never reached their server |
| a TCP probe says they are reachable | the ngrok **edge** answers on any hostname, tunnel or not |
| it starts mid-game, not at the start | it starts when *they* restart |
| the whole series does not fail | only the role whose endpoint went stale fails |

Fixed in `net/peer_endpoint.py`. A peer may move us only to an address they
declared inside a signed, hash-locked handshake.

### 2. We announced an endpoint before it could answer

`PeerServer.start()` returned in **0.4 ms**; the socket did not accept for
**314 ms** on a cold start; and `running` meant "the thread is alive". So
`server.started` fired, the tunnel was started, and `agent.online` published a
URL that answered `connection refused`. This is the source of the
`dial tcp 127.0.0.1:8802: connect: connection refused` lines that fill our own
`cloudflared` terminal.

Fixed: `start()` blocks until a real connection succeeds, and raises if it never
does. `net/readiness.py` keeps "can I bind here" and "will a connection
complete" as the two different questions they are.

### 3. We asked the wrong layer who failed

`accepts_tcp` asks whether the tunnel edge is up. For a hosted tunnel that is
close to a constant: the edge terminates TLS and serves **HTTP 502** when the
laptop half is gone. We read the completed handshake as "their endpoint is
reachable; the fault is not connectivity" and stopped one layer above the
answer.

`net/http_probe.py` asks at the HTTP layer, and is decisive both ways — a
provider error page names the far side, a `200`/`405`/`406` while our client
cannot connect names **us**, and `attribute()` now returns `our-network` for it.

### Reading the cloudflared log

`Unable to reach the origin service ... dial tcp 127.0.0.1:8802: connection
refused` means **our** agent is not listening. Harmless when no match is
running — a named tunnel stays up while the agent does not. During a match it is
the fault, and it is ours.
