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
| What we transmit | scent and hints by default — **may be either or neither** |

### What we put on the wire, declared rather than sprung

The agreed pheromone maths is fixed and hashed into the handshake; how much of
our own field we *transmit* is not a term, and teams in this league differ. Some
send a full scent map every turn, one sent us a truthful hint on every record
and no scent at all, and one sent nothing whatever.

So we match what you send: `--scent full|window|none` and `--hints/--no-hints`
move independently. A silent series from us is legal — the book forbids planting
a *fake* trail, not declining to publish a real one (p. 22) — and we would
rather say so here than have you read an empty `smell_grid` as a bug. The key is
always present; only its contents change. None of this touches the move: our
moves are plain Python either way, and we decline the rule 25 LLM-move
exception.

**Which snapshot crosses the wire — ask us, and here is our answer.** The locked
model doc carries two fields for the same example, `emit_field` (0.9 peak) and
`after_one_decay` (0.8 peak), and it never pins which one is transmitted. Two
teams in this league sit on opposite sides of that, so it is worth settling in
writing rather than discovering at settlement.

**We transmit the pre-decay emission snapshot: 0.9 peak, 0.6/0.3 rings.** Our
field is deposited and only decays once both agents have moved, so the grid we
send is the field as it stands at send time.

If your receiver decays an arriving grid once — the model doc's
`receiver_side_decay: true` — then our trail nets exactly one decay in your
field, which is what the physics asks for. If your receiver instead takes frames
as-is, tell us and we will send the decayed form, because then the one decay has
to come from our side. A peer that transmits post-decay *and* decays on receipt
ages a trail twice; that is worth checking on both sides before a series rather
than after.

### The exact object we sign

`verify_peer` compares the peer's `terms` against ours for **byte-identical**
equality (rule 11), so the table above is the human summary and this is the
thing that actually has to match. Fourteen keys, these names, these types:

```json
{
  "board_size": 7,
  "smell_grid_size": 5,
  "decay_per_step": 0.1,
  "emit_intensity": 0.9,
  "min_center_intensity": 0.5,
  "max_steps": 35,
  "barriers_max": 14,
  "setting": "New York",
  "hint_max_words": 15,
  "axis_origin_corner": "top-left",
  "axis_start_index": 0,
  "thief_start": [3, 3],
  "cop_start": [0, 0],
  "num_games": 6
}
```

Canonical form is `json.dumps(payload, sort_keys=True, ensure_ascii=False,
separators=(",", ":"))` over UTF-8, and the contract hash is SHA-256 of that.
For the object above that is:

```
a284082dfb1572236f1b614d29295a99625539c7d33a096f7f8921bafbc3d08d
```

If you compute the same digest from your own config, our handshake will lock on
the first try. If you do not, `describe_mismatch` names the key and both values
in the refusal, so it is one message to settle rather than two configs to diff
under time pressure.

**Please settle this before match day, not during it.** We are genuinely
flexible about the *values* — raise anything you like, subject to rule 12, and
we will change our config to match. What we cannot do is negotiate at the
handshake: our match path sends our terms and requires yours to be identical, so
a counter-proposal arriving mid-handshake is a refusal rather than a discussion.
An earlier version of this page said "send a counter-proposal and we will almost
certainly accept", which described an intention rather than the code.

### Four things worth checking before we play

* **`ensure_ascii`.** Python's default is `True`, which renders a non-ASCII hint
  as `\uXXXX` and changes every hash that carries one. We use `False`. Hints are
  free text and this cohort writes Hebrew, so this is one hint away from voiding
  a game for both of us at audit time.
* **`separators`.** `json.dumps` defaults to `", "` and `": "`. Any payload
  serialized that way hashes differently from ours, on every single step.

* **The settlement signature is the *spaced* form**, not the compact one —
  sorted keys, raw UTF-8, default `", "` / `": "` separators, signed before the
  `חתימת_קונסנזוס_משותפת` key is inserted. Signing compact here produces a digest
  that never matches, at the exact moment both reports must agree.
* **The pheromone model is subtractive Chebyshev**, not the book's radial
  variant. Nothing crashes if we disagree — the grid is not hashed — but both of
  us would read each other's field wrongly for the whole series.

All four are settled in the same direction by the interop kit at
`github.com/Imreec/copthief-league-protocol`, which we cross-checked our
implementation against on 2026-08-05 and agreed with on every point. Our own
known-answer vectors live in `tests/unit/test_protocol/test_interop_vectors.py`
if you want to diff against something concrete.

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
