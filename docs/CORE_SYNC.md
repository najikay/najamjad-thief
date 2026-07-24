# Core sync procedure (PLAN ADR-002)

The cop and thief repositories are standalone for graders, but their shared core must never
drift. `scripts/sync_core.py` owns this: its `MANIFEST` tuple lists every mirrored path, and
CI fails on any byte difference.

## Mirrored (in `MANIFEST`)

`src/najamjad_agent/` (whole package) · `tests/` · `scripts/` · `docs/` ·
`.github/workflows/` (all workflows) · `.gitignore` · `.env-example` · `LICENSE`

## Role-specific (NEVER mirrored)

`README.md` (role text + cross-link) · `pyproject.toml` (project name) ·
`config/` (`config/police/` vs `config/thief/`, plus per-match negotiated configs) ·
`matches/` archives · `.python-version` is mirrored implicitly by convention (keep equal).

Strategy note: both repos carry both brain modules (the package is symmetric, like the
reference simulator); which brain runs is decided by role configuration, not by which code
is present. This keeps the manifest simple and self-play testable in either repo.

## Procedure

1. Edit core files **in the cop repo only** (canonical side).
2. Mirror: `uv run python scripts/sync_core.py ../najamjad-thief --push`
3. Verify: `uv run python scripts/sync_core.py ../najamjad-thief` (exit 0 required)
4. Run the full gate suite in **both** repos before committing.
5. Commit both repos with matching messages (author: Naji Kayal).

CI runs step 3 as the cross-repo core-manifest job (T-0214) once remotes are wired.
