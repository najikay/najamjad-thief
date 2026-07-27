# ADR-010 — uv + ruff + pytest toolchain, CI as compliance robot

**Status:** imposed/accepted

Guidelines-prescribed ruff config; uv-only. GitHub Actions on both repos run: ruff, pytest
with `--cov` (`fail_under = 85`, team target 90), file-size gate (code lines ≤ 150 hard /
120 warn), secret scan, core-manifest cross-repo check, uv-only grep gate (no pip/python -m).

---

Extracted from `docs/PLAN.md`. See [the ADR index](README.md).
