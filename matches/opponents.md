# Opponent tracker

**Updated:** 2026-07-27 · Update this after **every** contact, not in batches.

Recruitment opens 2026-08-03. Target: ≥ 8 teams contacted by Aug 5, ≥ 4
confirmed by Aug 6 (below that, the contingency in `docs/LEAGUE_OPS.md` §4
trips), ≥ 6 counted matches by Aug 10.

Send everyone `docs/HOW_TO_PLAY_US.md`.

## Status key

| Code | Meaning |
|---|---|
| `contacted` | We sent the one-pager; no reply yet |
| `talking` | They replied; scheduling or negotiating |
| `scheduled` | Window agreed **in writing** by both sides |
| `warmed` | Warm-up game played (mandatory before any counted match) |
| `counted-N` | N counted matches played against them |
| `declined` | Not playing us |
| `stale` | No reply after two contacts — do not spend more time |

## Candidates

| Team / group id | Contact | Their URL | Status | Counted | Notes |
|---|---|---|---|---|---|
| **imreeyal** | imreeyal.copthief@gmail.com | cop/thief.imreeyal.com/mcp | `counted-1` | 1 | Imree Cohen, Eyal Shtinmetz. No LLM, pure Python. Fresh process per sub-game. Maintain the interop kit. Two friendlies then the counted; their review found four real defects in ours |
| **uoh-ay26** | — | — | `counted-1` | 1 | Aisha Dahesh et al. Hint every turn, no scent at all. Our first counted series. **Agreement digests differ — see the open item below** |
| uoh-sqak | — | ngrok (rotates) | `warmed` | 0 | Beat us 15-60 on 2026-08-02, emitting nothing. The loss that motivated the emission dials |
| ahk-yosi | — | — | `warmed` | 0 | Void warm-up 2026-08-02 |
| _amjad / najamjad-b_ | teammate | quick tunnel (rotates) | — | 0 | **Never countable** (rule 31, same team). Our only full-strength rehearsal partner |
| _(kit sparring peer)_ | — | local :8931 | `warmed` | 0 | `copthief-league-protocol`. Never counted |

## Contact log

Newest first. One line per contact attempt **and** per reply.

| Date | Team | What was said | Next action |
|---|---|---|---|
| 2026-08-13 | imreeyal | Counted series played and filed, 90-30 | Done. No rematch — one counted per pairing |
| 2026-08-13 | imreeyal | Two verification friendlies, three fixes adopted from their review | — |
| 2026-08-12 | imreeyal | Long protocol exchange; they sent a 17-point interop spec | — |
| 2026-08-08 | uoh-ay26 | Counted series played and filed, 90-30 | **Owed: raise the agreement-digest mismatch with them** |

## Counted-game ledger

Rule 31 / Appendix F: minimum 2 counted matches to pass, maximum 10 per team,
diversity reward for distinct opponents. **A warm-up is never counted.**

| # | Opponent | Date | Result | Points | Reported | Archived |
|---|---|---|---|---|---|---|
| 1 | uoh-ay26 | 2026-08-08 | won 90-30, 6-0 | 90 | yes | `matches/uoh-ay26-counted-20260812T111029Z` |
| 2 | imreeyal | 2026-08-13 | won 90-30, 6-0 | 90 | yes | `matches/imreeyal-COUNTED-20260813T164811Z` |

**Totals:** 2 counted · 2 distinct opponents · 180 points · **rule 31 pass threshold met**

The tracker's count is *derived*, never typed: `workspace/counted_games.json` is
written at settlement and the handshake declaration reads from it, so the number
we declare to an opponent cannot drift from the number we have played (rule 37).

## Open item — the uoh-ay26 agreement digest

Both teams' reports for the counted series **agree on every game fact**: all six
sub-games' roles, results, winners and scores, `total_score` 90-30,
`sub_games_won` 6-0, `winner_group` najamjad, one shared `game_uid`, and
`mutual_agreement.confirmed: true` on both sides.

The `mutual_agreement.sha256` values differ, because the two files were built by
different constructions — and theirs reproduces **neither ours nor the
reference's**, so three implementations produced three answers. Ours has since
been corrected to the reference construction (`{game_id, aggregate, sub_games}`,
spaced separators), proven byte-equal against imreeyal.

Rule 35 voids a match for *contradictory reports*. These do not contradict on
any outcome; the digest is the mechanism for proving agreement, and the
mechanism differed while the agreement held. **The book defines no remediation
procedure** — no amendment path, no re-file protocol. Mitigation is therefore a
third counted match against a different team, which keeps us above the rule-31
threshold whichever way this is read.
