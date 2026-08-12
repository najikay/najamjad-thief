# Incidents — <opponent> — <date>

Log **live, during the match**, not from memory afterwards. Every retry,
timeout, rejected message, odd field and human decision. The value of this file
is that it is written while nobody yet knows which detail mattered.

One line per event. Timestamps from the console are fine.

| Time | What happened | Our reading | What we did | Follow-up |
|---|---|---|---|---|
| | | | | |

## Protocol quirks observed

Anything about *their* implementation that differs from the reference. These
become adapter-profile entries (`docs/EXTENDING.md` §3) rather than one-off
patches.

| Quirk | Evidence | Handled by |
|---|---|---|
| | | |

## Decisions taken under time pressure

Things a human chose during the match, with the reasoning available at the time.
Written so the post-mortem can judge the decision rather than the outcome.

| Decision | Why, at the time | Was it right |
|---|---|---|
| | | |

## Post-match

- [ ] Every incident above triaged: fix / adapter profile / accept
- [ ] Fixes ticketed in `docs/TODO.md`
- [ ] Opponent profile updated (`profile.md`)
- [ ] Anything reusable folded into the runbook
