# Opponent tracker

**Updated:** 2026-08-22 · Update this after **every** contact, not in batches.

Recruitment opens 2026-08-03. Target: ≥ 8 teams contacted by Aug 5, ≥ 4
confirmed by Aug 6 (below that, the contingency in `docs/LEAGUE_OPS.md` §4
trips), ≥ 6 counted matches by Aug 10.

Send everyone the full terms document — the complete terms, the conformance
requirements, and the block of details we need back. It is kept **outside both
repositories** (`opening-message-new-opponent.md` in the parent directory) and
sent over WhatsApp or email, deliberately: these repos are public under rule 49,
and a demand sheet naming other teams' defects is not something to publish at
them. `docs/HOW_TO_PLAY_US.md` is the public one-pager for a first approach.

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
| **ahk-yosi** | apexmediamind@gmail.com | trycloudflare quick tunnel, one door for both roles (rotates) | `counted-1` | 1 | Yosef Shanaa + partner (213314859, 325811255). One process alternating roles at each boundary. Sent the most thorough conformance audit any opponent has: both our vectors re-derived through their own code, five of their own defects volunteered, two real errors found in our terms document. Counted 2026-08-21: **tied 75-75, 3-3** — every window went to the cop, both sides, six captures out of six. Void warm-up 2026-08-02; they and we both treat 2026-08-21 as the first meeting |
| **vibecode** | — | — | `counted-1` | 1 | Counted 2026-08-14: **lost 30-90, 0-6**. Their cop converted every window; the loss that motivated the barrier work |
| **MOAAMOHA** | moaawiyah.haj@gmail.com | calm-lantern-322 / bright-harbor-604 (Cloudflare) | `counted-1` | 1 | Moaawiyah Hajajrah, Mohamed Selawe. Two processes. Counted 2026-08-17: **won 60-40, 4-2**. Their thief lies on every record and emits scent; their cop runs a column-3 seal. Fixed their `roles` keying at our request and the digests then matched first try |
| yanell11 | — | Cloudflare | `warmed` | 0 | Practice abandoned: their loop stopped at 25 moves against an agreed 35 and they did not want to check. Our logs were clean |
| rstabcde | — | — | `talking` | 0 | Owed a reply on receiver-side scent decay |
| **bestteam** | itay.malich2@gmail.com | reserved ngrok, one per role | `talking` | 0 | Itay Malich, Diana Koroblov. Answered the whole green-light block by re-deriving, not eyeballing: terms digest, commit-reveal vector and scent SHA all confirmed independently. **Both commits resolve publicly** — the first opponent where our rule-53 check does real work. Two repos, two processes. 0 counted so far. Their doors only answer while armed |
| **nis-yar1** | yardentziar@gmail.com | trycloudflare, churned 6x | `counted-1` | 1 | Nissim Deri, Yarden Tziar. Terms and both digests verified, but four endpoint changes in one evening and a regression back to the one-host/two-path setup that produced 21 `Session terminated` per side and never locked a handshake. Repos never resolved (404). Dropped 2026-08-17 after too much time spent; re-open only if they bring two named hostnames and public repos |
| **yamanagh** | yamandahle@gmail.com | ONE public endpoint, named tunnel (pending their wiring) | `counted-done` | 1 | Nagham Manasra, Yaman Dahle. The most rigorous reply yet: terms + commit-reveal re-derived through their own code; scent = our A2/book natively, kernel+decay+serve-order verified BY US from their public source; rule 47 implemented with thief self-concession. Their flag on §7.2 caught a real defect in our own terms document (tie_award is beside the totals, not inside them — fixed). Owed by them: push+resend of the thief commit (03c801e0 does not resolve), negotiate ceiling raised to ≥1000 s, and their one endpoint once wired. 4 counted (their declaration 2026-08-22), distinct |
| _amjad / najamjad-b_ | teammate | quick tunnel (rotates) | — | 0 | **Never countable** (rule 31, same team). Our only full-strength rehearsal partner |
| _(kit sparring peer)_ | — | local :8931 | `warmed` | 0 | `copthief-league-protocol`. Never counted |

## Contact log
| 2026-08-23 | rstabcde | Pairing CLOSED late night after 5 friendly attempts, no completed series. Every failure was their per-sub-game process respawn on Windows (TIME_WAIT/zombie socket at rebind, series state lost, re-generated duplicates); full diagnosis + 7 questions sent, not acted on. Eleven windows played across attempts, every completed one Verified OK both sides — the wire was never the problem. No counted, nothing filed either way | Closed 2026-08-24 |
| 2026-08-23 | anrbj666 | COUNTED PLAYED AND FILED on attempt 4 — **77-77/75-75 TIE**, 3-3, all six Verified OK, digest a3645e1f matched with confirmed:true both sides; THE SEAM HELD (turn redelivery + fresh-session flag, new pair 2f3fca08/928ac029). Counted #8/#5, first meeting, no diversity (tie), tie_award 2 each. Ledgers 8/8, disarmed, archived anrbj666-COUNTED-20260823T175102Z | Done. One counted per pairing. Presentation delta (77 vs 75) flagged for the write-up |
| 2026-08-23 | anrbj666 | COUNTED CLOSED AS FRIENDLIES-ONLY after 4 voided attempts, all dying at the w3/w5 window-boundary seam (their per-window servers x our held-session client; final forensics contested — our client.sent on resolved responses vs their '318 call-less sessions'; POST-vs-GET check left for the post-deadline log exchange). All voids clean: nothing filed either side, ledger stays 7. Standing results: 3 clean friendly sixes (90-30 x2 + validation), tie-shaped counted (their cop takes our thief ~step 12, ours takes theirs ~30). Best engineering collaboration of the league, closed with mutual respect | Closed. Submit |
| 2026-08-23 | ali-ahm1 | Pairing ENDED after ~7 friendly attempts, no completed series; they walked. Best run banked 4 verified windows (g1-g4, ~1-min windows). Root causes fixed along the way: solo-game handshake, stale series numbering, missing sender, ngrok instability (moved to Cloudflare). UNFIXED: agreement-via-reoffer -> game loop never starts, in BOTH their processes (cop w5 twice, thief w2 last run). No counted, no filings, nothing owed either way. Scent flipped back to book, redirect back to us | Closed |
| 2026-08-23 | ali-ahm1 | CONTRACT reply received: terms/commit-reveal/step/rule-47 all confirmed, scent A1 (config flipped to reference — flip back before anrbj666 counted!), redirect set to them. Owed by them before play: thief commit, public repos (404 anonymously), explicit wire-shape reference-v3 + thief-first, exact counted list (their "+ one more" is a rules-37 hazard), fresh ngrok pair at T | Friendly on their word |
| 2026-08-22 | yamanagh | COUNTED REDO PLAYED AND FILED (the one that stands), **won 90-30, 6-0 + diversity**, 20:59-21:03 UTC on their scholars-wav tunnel; declarations correct after rollback (6 before / 7 including, theirs 4/5); report to lecturer 21:03:06 UTC id 1a02b48cd25e4d7d; ledgers reconciled 7/7; archived yamanagh-COUNTED-REDO | Done. Await their forwarded json to cross-check |
| 2026-08-22 | yamanagh | COUNTED PLAYED AND FILED, **won 90-30, 6-0 + diversity** (counted #7 us / #5 them, first meeting). Both reports to the lecturer as required; ledgers reconciled 7/7; disarmed; archived yamanagh-COUNTED. Their report files confirmed:false per the written option-2 record | Done. One counted per pairing — no rematch. REPOS STILL PRIVATE AT FILING — flip to public! |
| 2026-08-22 | yamanagh | Friendly #3 PLAYED, MATCHED, ARCHIVED (yamanagh-friendly-3-clean-20260822T194241Z): third identical clean six, both documents agree in the digest scope. COUNTED GATE SETTLED IN WRITING — Yaman chose to file confirmed:false/results_agreed:true with the email thread as the written record that the digests match by document comparison (keep that email). Counted scripts switched to --no-hints per our decision (supersedes the hints-on heads-up we gave them — say so when scheduling) | Counted at agreed start time; armed and ready |
| 2026-08-22 | yamanagh | Friendly #2 PLAYED AND ARCHIVED (yamanagh-friendly-2-clean-20260822T191357Z): identical clean six 90-30 6-0 on their rotated tunnel; their gpu "none" fix landed so OUR declaration filed this time (14/14 artifacts). Their consensus loop accepted ~10 more envelopes; we still do not echo. COUNTED ARMED (email.mode=send both repos) — would be counted #7, first meeting, diversity path | Counted on their written word re the confirmed flag + agreed start time |
| 2026-08-22 | yamanagh | Their consensus-false claim VERIFIED against our own log and the mechanism is an EXPECTATION UNIQUE TO THEIR BUILD (every other pairing confirms via mailed documents, never an in-band echo): their series-end audits carry `consensus_sha` (11 copies accepted 18:22:47-18:23:20 UTC, our inbox logged them as unknown fields), our envelope never sends the digest in-band. Replied with the mechanism + closure for a counted: they read peer_sha256 from our mailed result like every other team (default); post-freeze in-band echo only as fallback | Their pick; friendly #2 unaffected |
| 2026-08-22 | yamanagh | Friendly #1 PLAYED AND SETTLED: 90-30, 6-0 najamjad, all six audits verified, settlement sha 6fc49383... identical in both documents; archived matches/yamanagh-friendly-clean-20260822T183625Z. Two receive-side items raised with them: their consensus never captured our sha (sha_match:false/peer_sha256:null despite equal digests) and their greeting's gpu_model:null blocked OUR declaration artifact (asked for the string "none"). They want friendly #2 | Friendly #2 on their word; same commands |
| 2026-08-22 | yamanagh | They migrated off ngrok to a Cloudflare QUICK tunnel (sequence-burke-outlets-occur.trycloudflare.com — rotates on restart) and asked to retry. Cards + practice redirect updated; probed 18:02 UTC: their edge clean, origin 502 (not up yet), our doors open. Replied: fresh series from w1, we open thief, hints off declared, asked written confirmation of the three MCP-companion behaviours before play | Warm-up (no hints) once they spin up and confirm the 400 fix |

Newest first. One line per contact attempt **and** per reply.

| Date | Team | What was said | Next action |
|---|---|---|---|
| 2026-08-22 | yamanagh | Full green-light reply; we verified their scent physics from their public repos, answered the one-endpoint question (yes — same URL on both our cards, no per-sub-game retargeting needed on their side), corrected our §7.2 tie wording their flag exposed, and asked for a thief-repo push | Warm-up once their endpoint is wired |
| 2026-08-21 | ahk-yosi | Counted series played and filed, **tied 75-75, 3-3**. Digest `5bb96826…` confirmed both sides; all six audits verified | Done. One counted per pairing |
| 2026-08-21 | ahk-yosi | Two warm-ups (lost 30-90, then 30-90). Their scent model A2 adopted for the pairing; rule-47 confirmation and window re-offer both settled in writing | — |
| 2026-08-20 | ahk-yosi | Full conformance audit from them; two errors found in our terms document (a counted count that disagreed with itself, the stale scent table) and both fixed | — |
| 2026-08-17 | bestteam | Full green-light reply; we verified their commits resolve on GitHub and answered their two open items (nested `identity.group_id` binds fine; flat 3 s/120 s retry is fine) | Warm-up as soon as they are up |
| 2026-08-17 | nis-yar1 | Four endpoint changes, then back to the broken one-host topology | Dropped |
| 2026-08-17 | MOAAMOHA | Counted series played and filed, **won 60-40**. `sha256 23da6c3c…` matched theirs byte for byte; per-window commits correct both sides | Done. One counted per pairing |
| 2026-08-17 | MOAAMOHA | Two warm-ups. Diffed both reports: their `roles` was keyed by role name, which broke the symmetric digest — they fixed it in one pass. We fixed our per-window commit stamping and our peer-token reader | — |
| 2026-08-16 | MOAAMOHA | First warm-up, 60-40. Split-process play verified against a real peer for the first time | — |
| 2026-08-16 | yanell11 | Practice abandoned — they play 25 moves, not 35 | Dropped; no counted series |
| 2026-08-14 | vibecode | Counted series played and filed, **lost 30-90** | Done |
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
| 3 | vibecode | 2026-08-14 | **lost** 30-90, 0-6 | 30 | yes | `matches/vibecode-counted-20260814T190747Z` |
| 4 | MOAAMOHA | 2026-08-17 | won 60-40, 4-2 | 60 | yes | `matches/moaamoha-COUNTED-20260817T132317Z` |
| 5 | nis-yar1 | 2026-08-18 | **lost** 30-90, 0-6 | 30 | yes | `matches/nis-yar1-COUNTED-20260818T121645Z` |
| 6 | ahk-yosi | 2026-08-21 | **tied** 75-75, 3-3 | 75 | yes | `matches/ahk-yosi-COUNTED-20260821T183302Z` |

**Totals:** 6 counted · 6 distinct opponents · 375 points · **rule 31 pass threshold met**

**Counted #6 — the cop converted, three windows out of three.** Every one of the
six mini-games ended in a capture and every capture went to the side holding the
cop, so the series is a clean 3-3 and the score a dead 75-75. That is the first
counted series in which our cop took its own windows: counted #3 and #5 were
0-6 with the cop empty-handed, and the barrier work between #5 and here is what
changed. `mutual_agreement.sha256 5bb96826…` confirmed, all six audits
`log_verified: true`, `tampered: false`, per-window commits correct on both
sides. Nothing in this series is disputed.

Worth keeping in view: they played it as **one process alternating roles**,
which does not satisfy rule 1 (Appendix ה Table 7). We raised it, they offered
to split before anything counted, and the series was played anyway on the
understanding that we changed nothing on our side. If the rule is read strictly
against them the tie is theirs to lose, not ours to claim; we filed what
happened and claim nothing beyond it.

**Counted #5 — the emission asymmetry, not the strategy.** We transmitted a scent
grid with peak 0.9 on every turn of all six mini-games; they transmitted none. Peak
0.9 is our exact cell, so as thief we handed their cop our position each turn and
were captured at step 13 three times identically, while as cop we had no position
fix at all and their thief survived to 34 three times. `--no-hints` silences hints
only; `scent = "full"` stayed on from `[emission]`. Legal on their part and
self-inflicted on ours. Both reports agree exactly — `sha256 398452f3…`, all six
audits `log_verified`, per-window commits correct — so nothing here is disputed.

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
