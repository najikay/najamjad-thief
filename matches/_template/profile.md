# Opponent profile — <opponent>

Filled in **before** the match window opens, updated after. The point is that no
protocol surprise should be met for the first time during a counted game.

## Identity

| | |
|---|---|
| Group id | |
| Contact | |
| Their cop URL | |
| Their thief URL | |
| Their repo (if shared) | |
| Armed commit — their cop | |
| Armed commit — their thief | |

Full 40 characters, and copied into `opponents/<name>.toml` under
`[armed_commits]` so `scripts/audit_opponent.py` can compare them against the
`github_commit` their step-0 declares on the wire. A role-split opponent may
have two different ones — vibecode did.

## Protocol expectations

| Question | Answer | How we know |
|---|---|---|
| Tool argument name (`message` / `payload` / both) | | |
| Audit reveal shape (envelope / bare list) | | |
| Sends `timestamp`? | | |
| Extra fields they send | | |
| Fields they reject | | |
| Built on the reference simulator? | | |

Anything unknown here is a reason to insist on the warm-up, not a reason to
guess.

## Negotiation stance

| | |
|---|---|
| Their opening terms | |
| Where they differ from ours | |
| What we will concede | |
| Our red lines (never below Appendix F) | |
| Agreed terms hash | |

## Playing stance

| | |
|---|---|
| Do they bluff in hints? | |
| Do their hints correlate with their scent? | |
| Barrier behaviour (aggressive / conservative) | |
| Observed capture / survival tendencies | |
| Adjustment for the next series | |

## After the series

| Game | Our role | End reason | Audit | Notes |
|---|---|---|---|---|
| g01 | | | | |
| g02 | | | | |
| g03 | | | | |
| g04 | | | | |
| g05 | | | | |
| g06 | | | | |
