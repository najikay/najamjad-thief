# League operations

**Version 1.00 · 2026-07-27**

How we run the league window: recruiting opponents, scheduling, the discipline
during a match, and what happens after each one. The *mechanics* of playing are
in `docs/RUNBOOK.md`; this is the campaign around them.

The grade is a league ranking, so two things decide it and only one is technical:
how well the agent plays, and **how many counted matches we actually get**. An
agent that wins every game it plays and plays two of them loses to a worse agent
that played eight.

---

## 1. Targets and the calendar

| Date | Milestone |
|---|---|
| **Aug 3** | Recruitment opens: post URLs + `docs/HOW_TO_PLAY_US.md` |
| **Aug 5** | ≥ 8 teams contacted, responses tracked |
| **Aug 6** | ≥ 4 opponents confirmed, or the contingency in §4 trips. Warm-ups begin |
| **Aug 7–8** | ≥ 3 counted matches — **including match #2, which secures the pass** |
| **Aug 9–10** | ≥ 3 more counted matches (target: 6 total) |
| **Aug 12** | Submission |

Rule 31 / Appendix F: **2 counted matches is the pass threshold**, 10 per team is
the ceiling, and distinct opponents earn a diversity reward. Get to two early;
everything after is upside.

The tracker is `matches/opponents.md`. Update it **after every contact**, not in
batches — the point of it is to show, on Aug 6, whether the contingency has
tripped.

## 2. Recruiting

Send `docs/HOW_TO_PLAY_US.md`. It answers every question a team will ask, and it
offers two things that make people say yes:

* **A warm-up game.** Costs them nothing, protects them from the same
  protocol problems it protects us from.
* **Free code** — the scent module (which the book recommends teams share) and
  our replay verifier.

Contact more teams than you need. Some will not reply, some will drop out, and
the cost of an extra contact is one message.

## 3. The warm-up policy — non-negotiable

**Never count first contact with an opponent.** A warm-up game comes first,
every time, with every team (rule 52).

This is not politeness, it is self-interest measured in evidence. Every
interop defect we have hit — the MCP argument-name mismatch, four turn-message
incompatibilities, an audit reveal rejected on the wire, and our own step guard
killing game 2 — was invisible until two implementations that did not share
authorship met. Each would have cost a counted game.

The warm-up also fills in the opponent profile (`matches/<opponent>/profile.md`)
so nothing about their implementation is met for the first time in a game that
scores.

## 4. Recruitment contingency

**Trigger: fewer than 4 opponents confirmed by end of Aug 6.**

Escalate in this order, one step per day, keeping earlier steps running:

1. Post in the course forum with the one-pager and an explicit *"we will play
   any time, either side, and we will come to your schedule"*.
2. Message the lecturer asking for teams still looking for opponents.
3. Offer to play at genuinely inconvenient hours — a match at 23:00 counts the
   same as one at 14:00.
4. Offer to run **both** our agents so a team can play both sides in one sitting.
5. Re-contact the `stale` teams once more with a concrete proposed time rather
   than an open question. "Are you free Thursday 20:00?" gets answers that "let
   us know when suits" does not.

Two counted matches is the pass threshold. If Aug 8 arrives with fewer than two
confirmed, that becomes the only priority and everything else stops.

## 5. During a match — freeze discipline

**No code changes during a match. None.**

Book rule 53 requires the `github_commit` we declare at step zero to be the code
we actually played. A change mid-match makes that declaration false, and it is
recorded and checkable.

* Between matches, changes land as **commits**, so each match's declared hash is
  exact.
* Verify the working tree is clean before declaring: `git status` must be empty.
* Record the hash in `matches/<opponent>/profile.md` at declaration time, not
  from memory afterwards.

If something is broken mid-match, log it in `matches/<opponent>/incidents.md`
and fix it *after*. A match played with a known bug is a data point; a match
played with a hash we cannot prove is a rule breach.

## 6. After every match — the verification checklist

Run `uv run python scripts/post_match.py --opponent <name>`, which checks the
mechanical half. The rest is human.

| Check | How |
|---|---|
| All artifacts present and valid | the script |
| Every mini-game reads `Verified OK` | the script re-hashes each log |
| Our result matches theirs | compare reports before sending |
| Report emailed, message id recorded | the send returns it; paste it into the tracker |
| Match config committed | `git add config/ && git commit` |
| `github_commit` resolves | paste the declared hash into GitHub and check it opens |
| Archive written and stored off the laptop | `uv run najamjad-<role> archive` |
| Tracker and standings updated | `matches/opponents.md` |
| Incidents triaged | `matches/<opponent>/incidents.md` |

**Both teams must report** (rule 35). Not reporting is punished like reporting
falsely, so file promptly whether we won or lost — and if their report and ours
disagree, that voids the game for *both* of us, which is why reconciliation
happens before sending rather than after.

## 7. Post-mortem, after each of the first two matches

Half an hour, three questions:

1. What in `incidents.md` was a **defect** rather than a surprise? Ticket it.
2. What was a **protocol difference**? That becomes an adapter profile entry,
   not a one-off patch (`docs/EXTENDING.md` §3).
3. What did we learn about **this opponent** that changes how we play them next
   time? Into `profile.md`.

Post-mortems after matches 1 and 2 are mandatory because that is when the
unknown-unknowns surface. After that, only if something happened.

## 8. Backup host

A dead laptop during the league window is a recoverable problem only if it has
been rehearsed. The drill: run one agent on the second machine with its own
tunnel, and play a complete game from it.

The named tunnel makes this cheap — the hostname is permanent, so failing over
does not require telling the opponent a new URL.

## 9. Weekly interop regression

Once a week during the window, re-run the reference-simulator interop suite:

```bash
uv run python scripts/pre_match_smoke.py
```

The reference is the closest thing to a neutral referee we have, and most teams
build on it. A regression against it is a regression against the field.
