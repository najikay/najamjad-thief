# Security posture — an agent that plays strangers on the open internet

**Version 1.10 · 2026-08-05**

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
| Identity binding | After negotiation, only the peer holding the opposite **role** may send turns |
| Session token | HMAC over the signed contract hash + `game_uid`; both peers derive it independently, an outsider cannot, and it never crosses the wire |
| Inbound rate limit | 3000/min globally — far above honest play, far below a flood. It was 120, on the assumption turns are human-paced; they are not, and it rejected a legitimate turn mid-series and lost us that game |
| Order of checks | Identity is checked **before** the sequence guard, so a stranger cannot even advance our step counter |

The session token is **optional by design**: an opponent running the reference
implementation sends none, and refusing to play them would cost us a match
rather than protect us. Unauthenticated peers are logged, not rejected.

### The binding was dead, and then it was wrong (2026-08-05)

Worth recording in full, because both halves were invisible for months.

`SessionGuard.bind` had **no caller outside its own test file**, so `check()`
returned early on `not self.bound` for every message any opponent ever sent. The
identity half of this section described an intention, not a behaviour, for the
whole project — while our MCP endpoint sat public under rule 10 with its URL in a
repository the lecturer reads.

Wiring it then broke everything, for a reason the repo already contained. The
wire's `sender` field carries a **role** — `"police"` or `"thief"` — not a group
id: `docs/research/simulator-repo-digest.md` records that shape on the turn,
audit and control messages, and our own `turn_egress` sends `state.role.value`.
Binding `expected_sender` to `"uoh-sqak"` therefore compared it against
`"police"` and refused every inbound turn and every audit reveal from the first
handshake onward — against the reference *and* against our own twin. A review
caught it before a match did.

So the design settled where the protocol actually is:

* the **token** is the identity proof, because it is derived from a contract
  only the two of us hold and cannot be forged by a stranger;
* `expected_sender` is the **role** the opponent holds this mini-game, re-bound
  each game since roles alternate, because that is what their messages carry;
* a peer that declares no group id leaves us deliberately **unbound**, with an
  event — binding to the empty string would reject everything they send, which
  is losing a series to our own defence.

The lesson is not "check the wire format". It is that the safety test used
`sender = ""`, the one input that could not exhibit the bug, and the docstring
asserted the reference "does not set the field" while our own research digest
said it does.

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
| Binding actually reached, and the wire's real shape | `tests/unit/test_sdk/test_session_binding.py` |
| Step guard and the claim-answer exemption | `tests/unit/test_net/test_turn_sequence.py` |
| Opponent barrier budget | `tests/unit/test_domain/test_barrier_budget.py` |
| Canonical form and commit construction | `tests/unit/test_protocol/test_interop_vectors.py` |
| Prompt injection | `tests/unit/test_llm/test_injection_guard.py` |
| Outbound hint rules | `tests/unit/test_llm/test_template_and_guard.py` |
| Crypto checklist (source-scanning) | `tests/unit/test_domain/test_crypto_review.py` |
| Egress validation | `tests/unit/test_protocol/test_egress_*.py` |
| Hostile network input | `tests/integration/test_fault_*.py` |


## Fair-play monitoring (2026-08-03)

Commit-reveal proves an opponent did not **rewrite** what they did. Nothing
asked whether what they did was **allowed**, and that gap is not hypothetical:
replaying a real series turned up a peer whose cop moved to a new cell *and*
declared a barrier on the same turn, fourteen times, against a Barrier Law that
is explicitly *in lieu of moving* (FR-ENG-3). Fourteen free actions is a large
edge and nothing in our agent noticed.

`domain/fair_play.py` watches every declared opponent turn for:

| rule | what it catches |
|---|---|
| `barrier-and-move` | a wall placed on a turn they also moved |
| `barrier-out-of-reach` | a wall further than one orthogonal step from them |
| `barrier-budget` | more walls than the agreed `max_barriers` |
| `teleport` | a declared position more than one step from the last |
| `through-barrier` | a move onto a cell they themselves declared walled |
| `off-board` | a coordinate outside the agreed grid |
| `step-order` | a skipped step, hiding a turn no audit can reconstruct |
| `hint-length` | a hint beyond the negotiated word cap |

Three design rules, and the first two are the important ones:

* **Observe, never retaliate.** A finding is recorded and surfaced; it never
  changes our play and never forfeits their game. Deciding a match on our own
  accusation is exactly the contradiction rules 33-35 void *both* teams for, and
  an honest peer with an off-by-one bug is far more likely than a cheat.
* **Evidence, not verdicts.** Each finding carries the step and the two facts
  that conflict, so a human can settle it with the opponent in one message.
* **Silence is recorded too.** Every played record carries a `fair_play` block
  whether or not anything was found, because "we checked and found nothing" is
  what makes the finding credible on the one occasion there is something.

The monitor is pure and takes no I/O, so a stored log re-audits identically
offline — which is what makes a finding arguable after the fact.

## Replay, and the one exemption that had to exist (2026-08-05)

The monotonic step guard refuses a step it has already accepted. It carries a
single exemption, and that exemption has now been wrong in *both* directions,
which is worth writing down because the two failures look nothing alike.

**Too open.** Any message carrying `claim_response` skipped the sequence check
entirely — any step number, any number of times. One key was a complete bypass
of the guard, on an endpoint anyone can reach. The comment defending it argued
"an answer is idempotent, the game ends on the first one", which is true of an
answer to a claim we actually made and *not* true of a field the sender sets.

**Too closed.** Narrowing it to `last_step ± 1` assumed an answer is always a
final concession. It is not: the reference attaches `capture_claim` to every
police move, so the thief answers on ordinary move-carrying turns, many
consecutively. Replaying our own archived `events.jsonl` through that version
refused 10 of 35 turns in one mini-game and 14 of 35 in another — each a dropped
turn, a timed-out poll, and the peer's watchdog scoring it against us.

The rule now is the ordinary one plus a single exception: an answer arriving at
the step we last accepted is taken **once**; anything ahead of it is a normal
turn and advances the counter; anything behind it is stale and refused.

## The opponent's barrier budget (2026-08-05)

`movement.place_barrier` refuses *our* placement past `max_barriers`; nothing
checked theirs, so we banked every wall a peer cared to declare — a bare board
accepted 46 against an agreed 14. Honoured, enough walls seal the thief into a
pocket, and rule 47 scores immobilisation as a capture.

Refusing the excess is self-defence rather than an accusation, and it is the one
place in `turn_ingress` where we act on a declaration instead of merely recording
it. It is not free: a refused wall makes our board diverge from theirs, and a
move we compute as legal may be illegal on theirs, which is a rules 33-35
dispute. We take that trade because the alternative is losing the mini-game to a
peer who can simply keep declaring, and because divergence only begins after they
have broken the agreed quota. No opponent has actually done this — the archive's
per-mini-game maximum is exactly 14, never exceeded in 31 games.

