# Team NajAmjad — match terms and requirements

**Group id:** `najamjad` · **Members:** Naji Kayal, Amjad Abed
**Contact:** najikayal4@gmail.com
**Counted series played:** 4 (uoh-ay26, imreeyal, vibecode, MOAAMOHA)
**Last updated:** 2026-08-17

Send this whole document to any team that wants a series. It is both the opening
message and the specification: everything we run, everything we will not change,
and the exact information we need back from you.

**Read §1 first.** Our terms are fixed. Every value below is at or above the
Appendix F minimum, rule 12 permits raising a term but never lowering one, and
our configuration has been re-derived independently by another team and matched
byte for byte. We are not carrying a second convention, a second scent model or
a second report shape, because every one of those has cost somebody a match in
this league already. If your build disagrees with something here, the fix is on
your side — and §9 lists the failure modes we have actually hit, so you
can check yourself before we play rather than discovering it at sub-game 4.

---

## 1. The agreed terms — signed, and not negotiable

Exactly fourteen keys are signed and compared. Nothing else in our config file
participates, so your comments, notes and schema version can differ freely.

| Key | Value |
|---|---|
| `board_size` | `7` |
| `axis_origin_corner` | `"top-left"` |
| `axis_start_index` | `0` |
| `cop_start` | `[0, 0]` |
| `thief_start` | `[3, 3]` |
| `max_steps` | `35` |
| `barriers_max` | `14` |
| `num_games` | `6` |
| `smell_grid_size` | `5` |
| `decay_per_step` | `0.1` |
| `emit_intensity` | `0.9` |
| `min_center_intensity` | `0.5` |
| `hint_max_words` | `15` |
| `setting` | `"New York"` |

**The exact bytes to hash.** Sorted keys, no spaces, raw UTF-8:

```
{"axis_origin_corner":"top-left","axis_start_index":0,"barriers_max":14,"board_size":7,"cop_start":[0,0],"decay_per_step":0.1,"emit_intensity":0.9,"hint_max_words":15,"max_steps":35,"min_center_intensity":0.5,"num_games":6,"setting":"New York","smell_grid_size":5,"thief_start":[3,3]}
```

```
sha256 = a284082dfb1572236f1b614d29295a99625539c7d33a096f7f8921bafbc3d08d
```

Re-derive that through your own loader **before** you message us. If you get a
different digest, our handshake will refuse to play and neither of us will learn
anything from the attempt. Team imreeyal reproduced it byte for byte through
their own code, so it is reachable from an independent implementation.

### Starting cells, since this is the one people assume

`cop_start [0, 0]` and `thief_start [3, 3]`. **Not** opposite corners. The cop
begins in the top-left corner and the thief begins in the dead centre of the
7×7 board, with row 0 at the top and index origin 0. Every one of our archived
mini-games starts there and our handshake refuses anything else.

### Scoring

| Outcome | Cop | Thief |
|---|---|---|
| Capture | 20 | 5 |
| Survival to step 35 | 5 | 10 |
| Series tie | 2 each | |
| Technical ending | 0 | 0 |

### Series shape

Six sub-games. **The thief opens sub-game 1** and roles alternate. We do not
open as cop — that is the project's rule, not a preference of ours, and we will
not swap it to suit a build that only works one way round.

### The Barrier Law

A barrier goes on the cop's own cell or one orthogonal step from it, **never on
the cell the thief occupies**, and placing one costs the turn. No diagonals in
the move set: `N`, `S`, `E`, `W`, `STAY`.

---

## 2. Our endpoints

| Role | MCP endpoint |
|---|---|
| Cop (police) | `https://cop.4laboratory.com/mcp` |
| Thief | `https://thief.4laboratory.com/mcp` |

Named Cloudflare tunnels, so these are permanent. You never need to ask us for a
fresh URL mid-session and we never send you one.

**Reading a health check correctly.** A browser or plain `curl` gets `406` or a
JSON-RPC error — that means we are **healthy**, because an HTTP client is
talking to an MCP endpoint. `502` means nothing is listening and `530` means the
tunnel is down; either is worth a message. Do not read `406` as us being absent.

```bash
curl -sI https://cop.4laboratory.com/mcp
```

### Tools, and the argument name each expects

| Tool | Argument |
|---|---|
| `negotiate` | `message` |
| `receive_turn` | `message` |
| `receive_control` | `message` |
| `submit_audit` | `payload` |

---

## 3. Two processes — a requirement, not our topology preference

Appendix ה Table 7 rule 1 requires the cop's code and the thief's code to run in
**two completely separate processes**; §2.4.2 disqualifies a solution even when
the game works technically, and the sanction is `כישלון מוחלט`. We run two
processes out of two separate repositories, always, against every opponent.

**What that means for you.** Our cop dials your thief and our thief dials your
cop, and the target changes at every sub-game boundary. So:

- you must give us **both** of your endpoints, one per role (§8)
- your side must hold **both** of ours and retarget per sub-game

A peer that builds one client at start-up and never retargets will send three of
our six windows to a process that is not expecting them. If your build does that
today, fix it before we play; we will not play unsplit to accommodate it, and we
have declined to before.

---

## 4. Scent model — locked by rule 23

`scent_model:subtractive_chebyshev_v1`

```
sha256 = 81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4
```

5×5 grid, half-width 2:

```
weight = max(0, 1 - chebyshev(dr, dc) / 3)
value  = round(0.9 * weight, 2)          # rings 0.90 / 0.60 / 0.30
```

Rule 23 locks the model, so a Gaussian kernel is not an equivalent — it is a
different model and we will not play against one. Snapshot ordering does not
need settling: we deposit, send, then decay; a peer that decays, deposits, then
sends puts the same peak `0.9` on the wire.

**Emission is a disclosure dial, never a strategy one.** We may run a series
with scent on and hints off, or silent entirely. It changes what we publish
about ourselves and never changes a move. You are free to do the same, and we
will not read your silence as bad faith.

---

## 5. Commit–reveal, and how an audit passes

Every turn carries a commitment; the nonces are released at the end of the
mini-game and each step is re-hashed. If your construction differs, our audits
will disagree with each other for reasons neither side can see from the board.

**The sealed payload.** Sorted keys, raw UTF-8, **compact** separators
(`","` and `":"`) — this is the compact form, unlike the report signature in
§7.2, which is spaced. The two are deliberately different and must not be
swapped.

```
{"hint":"","intent":"probe east","move":"MOVE:E","position":[3,4],
 "role":"thief","state":"ok","step":1,"sub_game":1}
```

**The commitment.** A literal `|` joins the canonical payload and the nonce:

```
commit = sha256( canonical_json(payload) + "|" + nonce )
nonce  = 16 random bytes, hex (32 characters), never reused across steps or games
```

**A vector you can test offline.** Take the payload above, use the nonce
`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` (32 `a`s), and you must get:

```
4047830b8108320cbf48c1c1e1f09c6c0d47da51c225ce2cf40c7857cefc3030
```

If your implementation reproduces that digest, your commit–reveal is compatible
with ours and no audit between us can fail for a formatting reason. This takes a
minute to check and saves a whole series.

---

## 6. Identifiers both sides compute independently

Neither of us sends these; we each derive them and they must agree.

```
pair     = sorted([your_group_id, "najamjad"])
game_id  = f"{pair[0]}-vs-{pair[1]}"
seed     = canonical_json(the 14 terms) + "|" + "|".join(pair)
game_uid = UUID from the first 16 bytes of sha256(seed)
```

So the id is alphabetical, not "whoever spoke first" — with us that gives
`your-group-vs-najamjad` or `najamjad-vs-your-group` depending on your id.
Because the seed includes the terms, the same opponent on the same terms always
yields the same `game_uid`, which is what lets both reports name one series
without exchanging anything.

---

## 7. The report — where series actually get voided

Rules 33–35 void a series **for both teams** when the two reports contradict
each other. Three requirements, all of them learned from real failures.

### 7.1 `roles` is keyed by group id

```json
"roles": {"najamjad": "thief", "your-group-id": "police"}
```

**Not** keyed by role name. The lecturer's golden result artifact writes
`{"segal-thief-team": "thief", "segal-police-team": "police"}`, and keying by
group is what makes the mapping identical on both machines regardless of which
side builds it. This one field is the single most common cause of a mismatched
signature we have seen: it silently changes the digest in §5.2 while every
visible outcome still agrees.

### 7.2 `mutual_agreement.sha256`

Signed over exactly three keys — `game_id`, `aggregate`, `sub_games` — and
nothing else. Not `game_uid`, not `groups`, not timestamps, not token spend, not
file paths, not `steps`.

Serialisation: **sorted keys, raw UTF-8 (`ensure_ascii=False`), and the
interpreter's default separators `", "` and `": "`** — the spaced form, not the
compact one. A team signing the compact form fails settlement against a team
signing the spaced form and neither can see why from the outcomes.

Each row carries `sub_game_number`, `result`, `winner_group`, `roles` and
`score`, with `roles` and `score` keyed by group id and rows sorted by number.
The aggregate is derived from those same rows, and a series tie adds `tie_score`
to both totals **inside** the signed aggregate.

### 7.3 Per-repo commit hashes

Because we run two processes, `github_commit` differs per sub-game: our thief
repo's HEAD on 1/3/5 and our cop repo's HEAD on 2/4/6. If you run two
processes, yours does too. A single commit stamped across all six rows is wrong
in half of them, and rule 53 is exactly the rule that asks which code played a
given game.

### 7.4 Where reports go

Counted series go to `rmisegal+uoh26finalgame@gmail.com`, from each team
separately. Friendlies go to the two teams only — never to the lecturer.

---

## 8. What we need from you

Copy this block, fill it in, send it back. Every line is used by our tooling;
none of it is curiosity.

```
group_id            (exactly as your handshake declares it — case sensitive)
group_name
members
agent email

cop endpoint        https://.../mcp        # your police process
thief endpoint      https://.../mcp        # your thief process

cop repo            https://github.com/...
cop commit          (full 40 hex, the commit you will play from)
thief repo          https://github.com/...
thief commit        (full 40 hex)

terms hash          a284082dfb1572236f1b614d29295a99625539c7d33a096f7f8921bafbc3d08d
                    -> confirm you re-derived this yourself, or say what differs
scent model         confirm subtractive_chebyshev_v1, sha 81ebee59...
roles keying        confirm keyed by group id (§7.1)
two processes       yes / no  — if no, see §3
watchdog / retries  your per-turn deadline and retry policy, in seconds
step convention     does step 1 mean before or after the first move?
schedule            when you want the warm-up, and when the counted series
```

**Commit hashes matter.** We cross-check the pair you send against the
`github_commit` your own step-0 declares, per role. A mismatch is a rule-53
finding we report as evidence — and the overwhelmingly likely cause is an honest
push you forgot to resend, so resend it if you push again before we play.

**Ours, for the same reason:**

| Repo | Commit |
|---|---|
| `github.com/najikay/najamjad-thief` | `02edbe107b68d4927c8bc10de6ac1e4a6d9c289d` |
| `github.com/najikay/najamjad-cop` | `634eb08b7fd714d9d042dec06ef6803808eac0f8` |

---

## 9. Before we play

Every one is a real defect from a real series in this league. None is
hypothetical and none is a criticism — finding them in a warm-up is the whole
point of having one.

1. **`roles` keyed by role name instead of group id.** Breaks
   `mutual_agreement.sha256` while every outcome still agrees, so it looks like
   a contradiction when it is a keying difference. One team hit this against us
   and fixed it in a single pass (§7.1).
2. **A series that stops early.** One opponent played 25 moves against an agreed
   `max_steps` of 35 and filed the result as complete. Confirm your loop runs to
   35 and that survival is judged at 35.
3. **One commit stamped on all six sub-games** while running two processes
   (§7.3). We shipped this ourselves and fixed it on 2026-08-17.
4. **`tamper_forfeit` with `tampered: false`.** A report that awards a forfeit
   for tampering while its own audit block says nothing was tampered with is
   self-contradictory, and rule 35 voids both teams' reports on a
   contradiction.
5. **Token counts only at step 0.** If your per-step records carry the counts,
   say so, and make sure your reader looks there — we found our own reader
   taking peer tokens from step-0 only and filing zeros for a peer who had
   published them all along.
6. **`game_started_at` overwritten by the last sub-game.** Cosmetic, outside the
   signature, but it makes a report look careless in a document the lecturer
   reads.


### Where a series usually goes wrong, in our experience

Not accusations — these are the things that have actually cost somebody a
mini-game against us, ours included, and each is cheap to check in advance.

**Your busy-peer timeout has to tolerate a whole mini-game.** If either side runs
a single process, it is inside its own game and cannot answer yours for minutes at
a stretch. Ours waits up to six minutes before it calls a peer absent; 40 seconds
of patience scored a technical outcome against a completely healthy opponent
earlier in this league. If your budget is tight, raise it before we play.

**Quick tunnels rotate.** Free ngrok URLs change on every restart. If that is your
setup, re-send the URL immediately before we dial — or use a named tunnel and stop
having the problem. We have had a whole session fail on a URL that had moved.

**Hints are capped at 15 words** and may be lies; that is an intended mechanic, not
bad faith on either side. A hint over the cap is a term breach rather than a
clever play.

**Survival is judged at step 35, and 35 means 35.** A loop that stops at 25 and
files the result as complete disagrees with our log for every remaining step.

**Tell us your step convention.** Ours counts step 1 as the state after the first
move. If yours differs, our `steps` figures will differ by one all series — it is
outside the signature so it cannot void anything, but we would both rather know
than argue about it afterwards.

**We will send you our replay verifier if you want it.**
`uv run najamjad-cop replay <log.json>` re-hashes every step of any artifact in the
standard shape and either prints `Verified OK` or names the step that fails. It is
useful for checking your own logs before you file them, and for settling a
disagreement without either of us having to be trusted. Our scent module is on
offer too — the book recommends sharing it, and ours has an explicit epsilon floor
that fixes a bug you probably have if you wrote the decay the obvious way: with
relative decay and three-decimal rounding a trail never reaches zero, so dead
scent pollutes belief forever.


---

## 10. How a series with us runs

1. **Terms.** You confirm §1 by hash. Nothing else is discussed, because there
   is nothing else to discuss.
2. **Warm-up, uncounted.** One or two, as many as you like. Reports go to the
   two of us only. Expect us to play a warm-up at reduced strength — that is
   ordinary competitive practice in a game where deception is an intended
   mechanic, and it is a clearly named, documented setting in our repository
   rather than something hidden.
3. **Counted.** Full strength, one series, both teams email the lecturer
   separately. We compare `mutual_agreement.sha256` before either of us sends,
   and if it differs we find out why first — a contradiction costs us both more
   than a loss does.

We do not accept a technical win we did not earn on the board. If our endpoint
is down, our tunnel dropped or our process crashed, tell us and we will replay
the sub-game. We ask the same of you, and we have given opponents our own
diagnostic findings when their side was at fault.

---

## 11. What we will not do

- Change any of the fourteen signed terms, in either direction.
- Carry a second scent model, a second report shape or a second digest recipe.
- Open as cop, or play the six sub-games in any other role order.
- Run one process instead of two, whatever your topology.
- Weaken our agent to match an opponent's level in a counted series.
- Edit a log, a config or an artifact once a series has started.
- Accept or claim a technical result where the board result is recoverable.
