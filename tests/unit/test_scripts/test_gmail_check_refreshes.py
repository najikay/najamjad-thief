"""`--check` must try the refresh, not read the field next to it.

It printed `refreshable: True` for a token Google had already revoked, because
it reported whether a `refresh_token` *key was present*. The RUNBOOK tells an
operator to run this the evening before a match, so a dead token passed its own
check and the failure surfaced only when the report did not send — which rules
33-35 score as not having played at all. It cost us the mail path on 2026-08-12
and would have cost a counted report.

The refresh now goes through `load_credentials`, the function the agent itself
uses, so the check and the real send path cannot disagree again.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "authorise_gmail.py"
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _module() -> Any:
    """Load the script as a module without running its CLI."""
    spec = importlib.util.spec_from_file_location("authorise_gmail_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _token(tmp_path: Path, scopes: list[str]) -> Path:
    path = tmp_path / "token.json"
    path.write_text(json.dumps({
        "token": "x", "refresh_token": "y", "scopes": scopes,
        "client_id": "c", "client_secret": "s",
        "token_uri": "https://oauth2.googleapis.com/token",
    }), encoding="utf-8")
    return path


def test_a_token_whose_refresh_fails_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact defect: right scopes, present refresh_token, revoked upstream."""
    module = _module()

    def _dead(_path: Any) -> Any:
        raise RuntimeError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setitem(
        sys.modules, "najamjad_agent.reporting.gmail_auth",
        type(sys)("najamjad_agent.reporting.gmail_auth"),
    )
    sys.modules["najamjad_agent.reporting.gmail_auth"].load_credentials = _dead

    assert module.inspect(_token(tmp_path, SCOPES)) == 1


def test_a_working_token_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A live token must still be reported as usable, or the check is useless."""
    module = _module()
    monkeypatch.setitem(
        sys.modules, "najamjad_agent.reporting.gmail_auth",
        type(sys)("najamjad_agent.reporting.gmail_auth"),
    )
    sys.modules["najamjad_agent.reporting.gmail_auth"].load_credentials = (
        lambda _path: type("C", (), {"valid": True})()
    )

    assert module.inspect(_token(tmp_path, SCOPES)) == 0


def test_the_wrong_scope_still_fails_before_any_refresh(tmp_path: Path) -> None:
    """Rule 30 is least privilege; a modify-scoped token is wrong however live."""
    module = _module()
    wrong = _token(tmp_path, ["https://www.googleapis.com/auth/gmail.modify"])

    assert module.inspect(wrong) == 1


def test_a_missing_token_is_refused(tmp_path: Path) -> None:
    """Nothing to check is not a pass."""
    module = _module()

    assert module.inspect(tmp_path / "absent.json") == 1
