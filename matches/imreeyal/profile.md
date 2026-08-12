# Opponent profile — imreeyal

Filled in **before** the match window opens, updated after. The point is that no
protocol surprise should be met for the first time during a counted game.

Unusually complete before first contact: they sent a written protocol
specification covering seventeen interop points, and we answered each one. Most
of the "How we know" column below is therefore *their written statement*, not
observation — and that distinction is the whole reason the friendly exists.

## Identity

| | |
|---|---|
| Group id | `imreeyal` (ImreEyal-Police) |
| Contact | imreeyal.copthief@gmail.com, imree.c@gmail.com — Imree Cohen, Eyal Shtinmetz |
| Their cop URL | https://cop.imreeyal.com/mcp |
| Their thief URL | https://thief.imreeyal.com/mcp |
| Their repo (if shared) | github.com/Imreec/copthief-p2p-cop · copthief-p2p-thief |

Both their hostnames terminate on **one process**, so either dials for either
role. Their peer accepts a handshake only from the team it is configured to
play, and only inside a window agreed in writing — a refusal outside one is
expected behaviour, not a fault on either side.

They also maintain the league interop kit (`Imreec/copthief-league-protocol`).

## Protocol expectations

| Question | Answer | How we know |
|---|---|---|
| Tool argument name (`message` / `payload` / both) | `payload` on `submit_audit`, `message` on the other three | Their §3.7, and the kit pins it; we accept either way round |
| Audit reveal shape (envelope / bare list) | `sender` + `result_claim` + `records[]`, each record `{payload, nonce, commit}` | Their §3.10 |
| Sends `timestamp`? | Yes, non-empty ISO-8601, and **refuses an empty one at validation** | Their §3.3 |
| Extra fields they send | `sub_game_number`, `role`, `scent_model_sha256`, `info_mode_sha256`, `game_uid` on negotiate | Their §3.8; we now send these too |
| Fields they reject | Unset optionals **absent** rather than explicit `null` may be refused | Their §3.9 — we changed to always send all ten keys |
| Built on the reference simulator? | Conformant to it; no LLM at all, pure Python moves (rule 25 declined) | Their §2 |

Two more worth carrying:

* **Fresh MCP session per sub-game** — a client holding one session across the
  series dies at the first boundary (§3.4). Ours already resets per mini-game.
* **Step numbering is per-sender from 1**, not a global interleaved counter
  (§3.6). Ours restarts at 1 each mini-game.
* **Per-call timeout under the signed deadline** (§3.5). This one we did *not*
  satisfy — our cap was 30 s, equal to the deadline. Fixed 2026-08-12.

## Negotiation stance

| | |
|---|---|
| Their opening terms | Identical to ours in all 14 signed keys |
| Where they differ from ours | Nowhere that is signed. `schema_version` "1.2" vs our "1.3"; they carry `rate_limiter_gatekeeper`, we carry `_note` — all outside the signature |
| What we will concede | Everything on their §3 list; all of it is either the kit's position or cheap |
| Our red lines (never below Appendix F) | Rule 12 floors; no LLM-decided moves; no hand-edited artifact |
| Agreed terms hash | `a284082dfb1572236f1b614d29295a99625539c7d33a096f7f8921bafbc3d08d` |

They re-derived that hash independently through their own loader, including
both branches of the `min_center_intensity` question, and it matched byte for
byte. Derived pair, confirmed identical on both sides:

```
game_id  : imreeyal-vs-najamjad
game_uid : 0109494f-4e63-cb2d-d402-741e1468bdbf
```

**Emission:** they send full scent (every strictly-positive cell, 3 decimals,
after-one-decay 0.8-peak form) and a hint on every turn. We match both — NOT the
5×5 window, which their receiver would read as physically impossible frame over
frame and refuse. Fixed text when caught: `You got me.`

**Roles:** they play police in sub-games 1/3/5. We open as thief, so we run the
**thief repo**, one process serving all six sub-games from
`https://thief.4laboratory.com/mcp`. The cop tunnel stays down; a 502 there is
expected.

## Open question before anything counted

`tokens_total_series` does not join across the two report sets: each side can
only know its own spend, and the report auto-fires at settlement, so there is no
moment to reconcile. The kit's `check_artifacts.py` cross-team join fails on it
(everything else passes, `mutual_agreement.sha256` included). Proposed to them
as a §3.17 declare-not-align convention. **Await their answer before a counted
series.** They also require our live auto-send mail path proven before counted.

## Playing stance

| | |
|---|---|
| Do they bluff in hints? | Their sparring peer defaults to a 25% declared-bluff rate; unknown for the live agent |
| Do their hints correlate with their scent? | Unknown — check during the friendly |
| Barrier behaviour (aggressive / conservative) | Unknown |
| Observed capture / survival tendencies | Unknown |
| Adjustment for the next series | — |

They have completed two counted series (anrbj666, uoh-sqak) and we have one
(uoh-ay26), so this is a genuine first meeting for both. Their engine is
deterministic pure Python: assume our lines are reproducible offline from any
log we hand over, and keep the friendly sandbagged.

## After the series

| Game | Our role | End reason | Audit | Notes |
|---|---|---|---|---|
| g01 | thief | | | |
| g02 | police | | | |
| g03 | thief | | | |
| g04 | police | | | |
| g05 | thief | | | |
| g06 | police | | | |
