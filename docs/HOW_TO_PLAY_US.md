# How to play Team NajAmjad

**Group id:** `najamjad` · **Members:** Naji Kayal, Amjad Abed

Everything another team needs to schedule and play a series against us, on one
page. If something here does not work, it is our bug — tell us and we will fix
it rather than claim a technical win.

---

## 1. Our endpoints

| Role | MCP endpoint |
|---|---|
| Cop (police) | `https://cop.4laboratory.com/mcp` |
| Thief | `https://thief.4laboratory.com/mcp` |

Both are **named** Cloudflare tunnels, so these URLs are permanent — they
survive our restarts, and you never need to ask us for a new address
mid-session.

**Checking we are up.** A plain browser or `curl` will get a `406` or a JSON-RPC
error, and that means we are **healthy** — it is an HTTP client hitting an MCP
endpoint. A `502` means nothing is listening; message us.

```bash
curl -sI https://cop.4laboratory.com/mcp     # any HTTP response = alive
```

## 2. Tool surface

The four mandated tools, with the argument name each expects:

| Tool | Argument | Purpose |
|---|---|---|
| `negotiate` | `message` | terms proposal / counter / agreement |
| `receive_turn` | `message` | one turn: commit, hint, scent grid |
| `receive_control` | `message` | control messages (stop, forfeit, admin) |
| `submit_audit` | `payload` | end-of-game reveal: records + nonces |

**We accept either `message` or `payload` on all four tools.** This is
deliberate. The course reference names the argument `message` on three tools and
`payload` on one; we found the hard way that a mismatch causes every call to be
rejected by argument binding *before any game logic runs*, in both directions
and invisibly to both sides' test suites. If your client sends the other name,
we will still understand you.

Our audit reveal travels as `{"sender": ..., "records": [...]}` — an envelope,
not a bare list. We accept a bare list from you.

## 3. Our opening terms

Every value is at or above the Appendix F minimum. Rule 12 says a term may be
**raised but never lowered**, so treat these as a floor.

| Term | Our proposal |
|---|---|
| Grid | 7 × 7, top-left origin, 0-indexed |
| Starts | cop `[0,0]`, thief `[3,3]` |
| Moves | `N, S, E, W, STAY` |
| Barriers | 14 (cop only) |
| Max moves / survival threshold | 35 |
| Scoring | capture 20/5, survival 5/10, tie 2 |
| Mini-games per series | 6, roles swap each game |
| Response timeout | 30 s · watchdog 60 s |
| Token budget per series | 200,000 |
| Map area (for hint flavour) | New York · hints ≤ 15 words |
| Pheromone | centre 0.9, decay 0.10, grid 5 |

**We are flexible on all of it.** Send a counter-proposal and we will almost
certainly accept — the only things we will not move on are the Appendix F
minimums, because neither of us is allowed to.

Both peers must end up holding a **byte-identical** `config/game.json`; our
handshake verifies a SHA-256 over the terms and refuses to play on a mismatch,
which is a feature — it means neither of us can be playing a different game than
we think.

## 4. Turn order and protocol notes

* **The thief opens** each mini-game. This matches the reference implementation.
* Roles **swap every mini-game**: if you are cop in game 1, you are thief in game 2.
* Every turn carries a commit (SHA-256 over the canonicalised payload plus a
  secret nonce). Nonces are released only at the end-of-game audit.
* We send `timestamp` on every turn message.
* Our canonical JSON is `sort_keys=True, ensure_ascii=False,
  separators=(",", ":")` — the reference's exact encoding. Our `commit_of`
  reproduces the reference's signature byte for byte, so if your commits verify
  against the reference they will verify against us.

## 5. The warm-up offer

**We will always play you an uncounted warm-up game first, and we recommend you
insist on one with every opponent** (rule 52 — first contact should never be
counted).

It costs twenty minutes and it catches exactly the class of problem that
otherwise eats a counted game: argument-name mismatches, a field one side sends
and the other rejects, a tunnel that is not actually reachable from outside.
Every one of those has happened to us.

A warm-up costs you nothing in the league table and tells both of us whether the
counted match will be a game or a debugging session.

## 6. Free code we will give you

Both offers are open to any team, including ones we have already played.

**The scent / pheromone module.** The book recommends teams share this. Ours is
a decaying deposit field with an explicit epsilon floor — worth taking because
of a bug we hit and fixed: with *relative* decay and three-decimal rounding, a
trail never actually reaches zero, so dead scent pollutes belief forever. If you
wrote it the obvious way, you probably have that bug.

**Our replay verifier.** `uv run najamjad-cop replay <log.json>` re-hashes every
step of any artifact in the standard shape and prints `Verified OK` or names the
step that fails. Useful for checking your own logs before you file them, and for
settling a disagreement without either side having to be trusted.

Ask and we will send either, or just clone: https://github.com/najikay/najamjad-cop

## 7. Contact and scheduling

| | |
|---|---|
| Email | najikayal4@gmail.com |
| Repos | [najamjad-cop](https://github.com/najikay/najamjad-cop) · [najamjad-thief](https://github.com/najikay/najamjad-thief) |

**Availability:** flexible, including short notice. We can play either side, and
we can run both agents simultaneously if you want to play both of ours.

**What we need from you to schedule:** your MCP URL, your group id, and a window.
That is all — we will send our terms and you can counter.

## 8. What we will not do

So you know what to expect, and so you can hold us to it:

* We will not claim a technical win over a protocol problem we could have
  fixed. If our tooling rejects something you sent, we will tell you what and
  why, and try to accept it.
* We will not argue about an audit result live. If your revealed records do not
  re-hash, it is recorded and the rules decide; we keep the log and we do not
  make it a conversation mid-match.
* We will not hand-edit a log, config or artifact during a match. All of them
  are signed or hashed, and editing one turns a clean result into a provable
  forgery.
* We **will** file a result report for every match, promptly, whether we won or
  lost — rule 35 punishes not reporting as heavily as reporting falsely, and a
  match where only one side reports is bad for both of us.
