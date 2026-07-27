# Contributing

**Team NajAmjad — Naji Kayal, Amjad Abed**

Two people, two repositories, one shared core. These are the conventions that
keep that from becoming three codebases.

---

## The one rule that is not negotiable

**The core package is byte-identical across `najamjad-cop` and
`najamjad-thief`.** Never edit the same file in both by hand — edit it in one,
then:

```bash
uv run python scripts/sync_core.py ../najamjad-thief --push   # copy
uv run python scripts/sync_core.py ../najamjad-thief          # verify
```

A test enforces this, and it has already caught two files that a commit had not
synced. Drift means one repo is running code the other's tests never saw.

## Before you push

```bash
uv run python scripts/check_all.py     # every CI gate, one verdict
```

If it does not say `ALL GATES PASSED`, do not push. `docs/CI.md` explains each
gate and how to reproduce a failure.

## Commits

Conventional prefixes: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`,
scoped by epic where it helps (`fix(E23): …`).

**Write the message for whoever reads it in three weeks.** Ours record what
broke, why, and what the fix assumes — including the times a gate was reported
as passing when it had not been looked at. That history is what makes the rest
of the repository trustworthy, and a grader reads it.

Specifically, a message should say:

* what was wrong, in terms of consequence rather than symptom;
* why the obvious fix was not the one taken, if it was not;
* what is still not right, if anything.

A commit that fixes a defect found by a test should say which test and what it
was doing that the previous tests were not.

## Branches

Work on a branch, open a PR, and let the other member read it. For a two-person
team the PR is not ceremony — it is the only place a second pair of eyes exists.

`main` is always green. If it is not, that is the only thing being worked on.

## Tests

Tests come first, and they are written to fail for the right reason before they
pass.

* **Name the behaviour, not the function.**
  `test_a_barrier_on_the_believed_thief_does_not_end_the_game_by_itself`, not
  `test_barrier_capture`.
* **The docstring says why the test exists**, especially when it encodes a
  defect we hit. Several tests in this repository are the only record of a bug
  that cost a day.
* **A failing test is not evidence the code is wrong.** Three times here the
  *test's* expectation was the false one. Establish which of the two is making
  the wrong claim before changing either.
* **Fakes must not be kinder than the wire.** Four separate defects survived a
  green suite because a double accepted something the real transport rejected.
  When you write a double, give it the constraint the real thing has.

## Code

* **≤ 120 code lines per file** (hard cap 150). Blank lines, comments and
  docstrings do not count — explain freely.
* **Docstrings on every module, class and public function**, and comments that
  say *why*. A comment restating the code is noise; a comment recording the
  reason a line is unusual is the point.
* **No hardcoded tunables.** Ports, timeouts, URLs, limits and addresses belong
  in config — `docs/CONFIG.md` says which file. The gate for this is at
  threshold zero.
* **Peripheral modules never call each other**, only the orchestrator (book rule
  3). It is what makes every component testable against a fake.

## Anything that crosses the wire

Read `docs/EXTENDING.md` §3 and `negotiation/terms.py` first. The opponent's
parser is stricter than ours: it builds messages with `cls(**data)`, so **an
extra field raises in their process and a missing one does too**. Adding a field
to a wire message is not a backward-compatible change.

## Match days

`docs/RUNBOOK.md` is the procedure and `docs/LEAGUE_OPS.md` is the campaign
around it. During a match: **no code changes**. Rule 53 requires the commit hash
we declare to be the code we played, and that is checkable. Log the problem in
`matches/<opponent>/incidents.md` and fix it afterwards.

## Secrets

Never commit one. `.env` is git-ignored, `.env-example` carries dummy values,
and a gate fails the build if a secret file is ever tracked. If you think you
have committed one: say so immediately — rotating a key is cheap, and a key in
git history is forever.
