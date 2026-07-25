# Security posture — an agent that plays strangers on the open internet

**Version 1.00 · 2026-07-25**

This project has an unusual threat model for a course assignment: our MCP server
is **publicly reachable by requirement** (book rule 10), its URL is published in
this repository, and our opponents are competitors with a direct incentive to
make us lose. Everything below is defence against that, and every item is
enforced by a test rather than by intention.

---

## 1. Who can move in our game

**Threat.** Commit-reveal protects against the *opponent* rewriting history.
Nothing in the book's protocol stops a *third party* who knows our URL from
calling `receive_turn` and injecting a move into a live match, or flooding us
into a technical loss.

**Defence** (`net/session_guard.py`):

| Control | Effect |
|---|---|
| Identity binding | After negotiation, only the agreed opponent id may send turns |
| Session token | HMAC over the signed contract hash + `game_uid`; both peers derive it independently, an outsider cannot, and it never crosses the wire |
| Inbound rate limit | 120/min globally — far above honest play, far below a flood |
| Order of checks | Identity is checked **before** the sequence guard, so a stranger cannot even advance our step counter |

The session token is **optional by design**: an opponent running the reference
implementation sends none, and refusing to play them would cost us a match
rather than protect us. Unauthenticated peers are logged, not rejected.

## 2. Prompt injection from the opponent

**Threat.** Every hint we receive is attacker-controlled text that we feed to a
model to decode. A team reading this repository knows exactly what our parse
prompt looks like. The payoff is concrete: make our parser report a confident
wrong direction and our belief map chases a ghost for the rest of the game.

**Defence** (`llm/injection_guard.py`), layered so no single control is load-bearing:

1. **Contractual truncation** — the hint word cap is an *agreed term*, so a
   500-word "hint" is already a protocol violation. Cutting to the cap removes
   most payload room before anything is interpreted. A character cap catches the
   single-enormous-word case.
2. **Delimiting** — the text is fenced in `<opponent_message>` tags with angle
   brackets escaped, and the system prompt states that the block is data and
   never an instruction.
3. **Detection** — instruction-injection phrasing ("ignore previous
   instructions", role assignment, JSON-shaped payloads, code fences) is
   flagged. We still parse, but the extracted confidence is discounted to 25%
   and an event is emitted: an opponent attempting this is itself information.
4. **Whitelist output** — and this is the layer that actually makes it robust:
   `parse_model_reply` accepts only five known direction words, landmarks that
   exist in our own gazetteer, and a confidence clamped to [0, 1]. **Even a
   fully subverted model cannot inject an arbitrary claim** — the blast radius
   is bounded by a five-value enum.

Beyond that, `belief.py`'s fusion order means testimony is applied *after*
physical evidence and can only re-weight mass that scent still permits, so a
believed lie cannot move the peak onto a cell the scent has ruled out.

**False positives matter too**: honest hints mentioning directions or landmarks
must not be discounted, so the detector is tested against genuine phrasings.

## 3. Our own output

| Control | Why |
|---|---|
| Coordinate stripping | Book rule 27 forbids numeric-position protocols; a helpful model will write "I'm at (3,4)" while sounding cooperative |
| Word cap | An agreed term — exceeding it is a contract breach, not a style issue |
| Single egress | A meta-test asserts `guard_hint` is called in exactly one place, so no hint reaches the wire unvetted |
| Egress schema gate | Every artifact and email is validated before sending; a null where a boolean belongs blocks the send and alerts the operator |

## 4. Secrets and process integrity

* Nonces live behind an audit gate, are XOR-encrypted at rest under an
  in-memory key, and are scrubbed from every event before it is logged or
  broadcast.
* `.env` only for API keys; `.gitignore` covers `.env`, `*.pem`, `*.key`,
  `credentials.json`, `token.json`, and a CI secret-scan checks tracked files.
* Gmail uses the send-only scope (rule 30). Cloudflare tunnel credentials live
  in `~/.cloudflared/`, never the repo.
* No `shell=True` anywhere; subprocesses (git, cloudflared, nvidia-smi) are
  argument lists, so a hostname from config cannot become a command.
* `random` is banned outside the template bank; nonces come from `secrets`.

## 5. Zero-trust ingress generally

Every inbound payload is validated by pydantic and **never raises**: malformed
input returns a structured error to the peer and an event to us. A hostile or
buggy opponent must not be able to end our match by sending nonsense. Fault
tests cover garbage floods, replays, out-of-order turns, teleports, diagonal
moves, and mid-turn disconnects.

## 6. What we deliberately do *not* do

* **No counter-attacks.** Assignment 6 experimented with injection payloads
  aimed at opponents; that is dropped. It risks disqualification, and our edge
  is a better engine rather than a dirtier one.
* **No blocking of unauthenticated peers.** Interop is worth more than the
  marginal security, given layer 4 bounds the damage anyway.

## 7. Test map

| Concern | Tests |
|---|---|
| Session binding, rate limit | `tests/unit/test_net/test_session_guard.py` |
| Prompt injection | `tests/unit/test_llm/test_injection_guard.py` |
| Outbound hint rules | `tests/unit/test_llm/test_template_and_guard.py` |
| Crypto checklist (source-scanning) | `tests/unit/test_domain/test_crypto_review.py` |
| Egress validation | `tests/unit/test_protocol/test_egress_*.py` |
| Hostile network input | `tests/integration/test_fault_*.py` |
