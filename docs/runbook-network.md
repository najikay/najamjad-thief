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
| **Cloudflare named tunnel** (default) | a domain on a free Cloudflare zone | `https://cop.<domain>/mcp`, stable forever |
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
cloudflared tunnel route dns najamjad-cop   cop.<your-domain>
cloudflared tunnel route dns najamjad-thief thief.<your-domain>
```

Credentials land in `~/.cloudflared/<uuid>.json`. **They never enter the repo**
— `.gitignore` covers `*.json` credentials via `credentials.json` and the
secret-scan gate checks tracked files.

Then set, in `config/police/game.toml`:

```toml
[tunnel]
provider = "cloudflare"
hostname = "cop.<your-domain>"
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
| `tunnel` | our own MCP tool answered **through the public URL** — not localhost |
| `clock` | skew is inside tolerance, so deadlines fire when they should |
| `gmail-token` | the stored token refreshes without interactive consent (A6's silent killer) |
| `llm-providers` | Anthropic and DeepSeek answer through the gatekeeper |
| `tokens` | enough budget remains to finish a whole match |
| `contract` | the signed `game.json` hash matches what we agreed |

Every check runs even if an earlier one fails, so one run shows the whole
picture.

## 7. When the tunnel misbehaves mid-match

1. The supervisor restarts it automatically and emits `tunnel.restarted` — the
   URL is unchanged, so the opponent needs to do nothing.
2. If restarts repeat, the opponent's turns still queue; our deadline tracker
   bounds the wait and produces sealed timeout evidence rather than hanging.
3. Switch provider only between mini-games: edit `tunnel.provider`, restart,
   and send the opponent the new URL. Prefer finishing the series first.

## 8. Outstanding operator tasks

- [ ] **T-1101** — decide the Cloudflare domain (or formally switch to ngrok)
- [ ] **T-1109** — create both named tunnels + DNS routes; verify each public
      URL from a phone on mobile data (proves it is genuinely public, not just
      reachable on the LAN)
