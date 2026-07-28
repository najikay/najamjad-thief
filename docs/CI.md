# CI — what each gate checks and how to reproduce it

**Version 1.00 · 2026-07-27 · ADR-010**

CI is the compliance robot: every guideline a machine can check runs on every
push, so a red `main` is impossible to miss. Nothing here is advisory — each
gate fails the build.

**Reproduce the whole pipeline in one command:**

```bash
uv run python scripts/check_all.py      # every gate, one PASS/FAIL verdict
```

That script exists because the gates used to be chained by hand and a scrolled-
past summary line got reported as "clean" when it was not. One command, one
verdict, no interpretation.

---

## The gates

| # | Gate | Reproduce locally | Fails when |
|---|---|---|---|
| 1 | Locked install | `uv sync --frozen` | `uv.lock` disagrees with `pyproject.toml` |
| 2 | Lint | `uv run ruff check .` | any violation — including inside `notebooks/*.ipynb` |
| 3 | File size | `uv run python scripts/check_file_sizes.py` | any file in `src/`, `tests/`, `scripts/` over **150** code lines (warns over 120) |
| 4 | Repo rules | `uv run python scripts/check_repo_rules.py` | `pip install`, a bare `python -m`, `except: pass`, a secret pattern, or a tracked secret file |
| 5 | Structure | shell loop in `ci.yml` | a mandated file is missing |
| 6 | Tests + coverage | `uv run pytest tests/` | any failure, or coverage below **85 %** (`fail_under`) |
| 7 | Types | `uv run pyright` | any error in basic mode |

Blank lines, comments and docstrings do **not** count toward the file-size cap.
That is deliberate: a cap that punished explanation would buy shorter files by
deleting the reasoning, which is the opposite of the intent.

## The gates are themselves tested

`tests/unit/test_scripts/test_gates_bite.py` builds a scratch tree containing
exactly one violation — an oversize file, a `pip install`, a swallowed
exception, a committed `credentials.json` — runs the real gate script over it,
and requires a non-zero exit. Each case is paired with a clean-tree run that
must pass, so a gate that simply failed everything could not satisfy the suite.

A gate that has only ever seen clean code is an assumption, not a control.

## Reading a failure

| Symptom | Almost always |
|---|---|
| Fails at *"Set up job"* | An action tag that does not resolve. `setup-uv` publishes **immutable** tags from v8, so it must be pinned exactly (`@v9.0.0`); a moving `@v9` fails before any gate runs. Verify with `curl -s -o /dev/null -w "%{http_code}" https://api.github.com/repos/<owner>/<repo>/git/ref/tags/<tag>`. |
| `uv sync --frozen` fails | `pyproject.toml` was hand-edited after `uv add`. Run `uv lock` and commit. |
| Coverage below the floor | Usually a new module with no test, not a lost test. `uv run pytest --cov-report=term-missing` names the lines. |
| Cross-repo drift test fails | The sibling repo is out of sync: `uv run python scripts/sync_core.py ../najamjad-thief --push`. It **skips** in CI, where no sibling is checked out. |
| Green locally, red in CI | The sibling repo and `results/` exist locally. Reproduce CI honestly with a clean export: `git archive HEAD \| tar -x -C "$(mktemp -d)"`, then run the gates there. |

## When the build goes red (T-0220)

A red `main` is the only thing being worked on. The triage is deliberately
short, because the failure mode we have actually hit is not misdiagnosis — it is
nobody noticing.

**Make sure you will notice.** Both members should have GitHub notifications on
for these repositories (*Watch → All Activity*, or at least *Actions* failures).
The README badge shows the state of `main` at a glance, so a red badge on the
front page is the second line of defence.

**Then, in order:**

1. **Read the failing step's name.** The job stops at the first failure, so the
   step name is the diagnosis: `Repo rules` is not `Tests`.
2. **Reproduce it locally with the one command** in that step's row above. If it
   reproduces, fix it and push.
3. **If it does not reproduce, reproduce CI honestly** — a clean export, with no
   sibling repo and no local `results/`:

   ```bash
   git archive HEAD | tar -x -C "$(mktemp -d)"    # then run the gates there
   ```

   This is not paranoia. A test file full of deliberately forbidden patterns
   passed locally and failed in CI because the repo-rules gate only scanned
   *tracked* files, and the file was not committed yet. Green locally and red in
   CI almost always means the gate is seeing something your working copy hides —
   or hiding something your working copy shows.
4. **If the job fails in seconds, before any gate ran**, it is the environment,
   not the code: an action tag that does not resolve, or a lockfile out of step
   with `pyproject.toml`. Check both before reading a single test.

**Never** disable a gate to go green. If a gate is wrong, change the gate
deliberately and say why in the commit — `tests/unit/test_scripts/test_gates_bite.py`
exists so that a weakened gate fails visibly rather than quietly.

## Why `pyright` when the guidelines do not ask for it

ADR-014. Basic mode costs ~20 s and catches the class of defect that survives
tests: a delegation to a method that does not exist. Two of those shipped before
it was added — `PeerServer.stop()` and `Negotiation.accept()`, neither of which
was a real method.

## What CI does not check

Stated so nobody mistakes a green tick for proof of readiness:

* **Interop.** No opponent exists in CI. `scripts/pre_match_smoke.py` and
  `scripts/rehearsal.py` cover that, and they run locally against the reference
  simulator.
* **That we win.** Strategy rates are measured by `scripts/baselines.py`, not
  gated — a flaky win-rate gate would train us to ignore red builds.
* **The dashboard's appearance.** Its logic is tested; how it looks is not.

## Nightly

`.github/workflows/nightly-selfplay.yml` runs the seeded self-play harness on a
schedule. It is separate from `ci` on purpose: a statistical result is a signal
to read, not a reason to block a push.
