"""Meta-tests: the egress gate must be unavoidable, not merely available.

A choke point only works if every path goes through it. These scan the source
tree so the guarantee survives future modules — the failure they prevent is a
new send path quietly written around the gate, which is exactly how Assignment
6's null report reached the lecturer.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src/najamjad_agent"
GATE_MODULE = SRC / "protocol/egress.py"
# Modules allowed to serialise outbound artifacts/emails. Anything else writing
# JSON to a file or a network call must route through the gate instead.
SEND_MODULES = {"egress.py", "artifacts.py", "gmail_sender.py"}
# Internal state that never leaves this machine. The gate exists to stop an
# unvalidated *artifact* reaching the lecturer; a local bookkeeping file is a
# different thing and validating it against a wire schema would be theatre.
LOCAL_STATE_MODULES = {"counted_games.py", "events.py"}


def _sources() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_the_gate_module_exists_and_exports_one_entry_point() -> None:
    tree = ast.parse(GATE_MODULE.read_text(encoding="utf-8"))
    functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "validate_egress" in functions


def test_no_module_writes_json_to_disk_outside_the_sanctioned_ones() -> None:
    """An artifact written without validation is an unvalidated artifact."""
    offenders = []
    for path in _sources():
        if path.name in SEND_MODULES | LOCAL_STATE_MODULES:
            continue
        text = path.read_text(encoding="utf-8")
        if "json.dump(" in text or ".write_text(json" in text:
            offenders.append(path.name)
    assert offenders == [], f"{offenders} serialise JSON outside the egress path"


def test_required_boolean_paths_cover_the_agreement_flag() -> None:
    """The A6 regression guard must point at the agreement field.

    Scoped per artifact kind: only the log and result carry the block, so
    demanding it on a declaration would block a valid write — and a gate that
    cries wolf is a gate people switch off.
    """
    from najamjad_agent.protocol.egress import REQUIRED_BOOLEAN_PATHS

    for kind in ("result", "log"):
        assert ("mutual_agreement", "confirmed") in REQUIRED_BOOLEAN_PATHS[kind]
    assert "declaration" not in REQUIRED_BOOLEAN_PATHS
    assert "config" not in REQUIRED_BOOLEAN_PATHS


def test_result_schema_declares_confirmed_as_a_plain_bool() -> None:
    """No Optional, no default: an unagreed report cannot be constructed."""
    from najamjad_agent.protocol.schemas_artifacts import MutualAgreement

    field = MutualAgreement.model_fields["confirmed"]
    assert field.is_required(), "confirmed must have no default"
    assert field.annotation is bool, f"confirmed is {field.annotation}, expected bool"


def test_agreement_hash_is_length_constrained() -> None:
    from pydantic import ValidationError

    from najamjad_agent.protocol.schemas_artifacts import MutualAgreement

    with pytest.raises(ValidationError):
        MutualAgreement(sha256="short", confirmed=True)


def test_egress_error_is_never_suppressed_in_source() -> None:
    """Catching EgressBlockedError and continuing would defeat the whole gate."""
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        if "except EgressBlockedError" not in text:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            names = ast.dump(node.type) if node.type else ""
            if "EgressBlockedError" in names:
                body = node.body
                assert not (len(body) == 1 and isinstance(body[0], ast.Pass)), (
                    f"{path.name} swallows a blocked send"
                )
