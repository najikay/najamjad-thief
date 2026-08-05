"""What we chose to transmit belongs in the record, not only in our config.

`EmissionPolicy.as_declaration` was written, documented and called by nothing —
the eleventh finished-but-unreferenced component found in this project. Its own
docstring gives the reason it should exist: emitting less than the maximum is a
tactical choice and not a secret one, rule 49 means the lecturer reads these
repositories, and a documented setting reads as the choice it is where the same
behaviour undeclared reads as something we were hiding.

It rides in the **declaration artifact**, deliberately not in the handshake
identity. A peer's strict declaration model once rejected an entire group block
over unexpected keys — six played mini-games with no artifacts written, which
rule 35 scores as not having played. Adding keys to something another
implementation parses is a risk we take only when the rules require it.
"""

import json

import pytest

from najamjad_agent.domain.emission import EmissionPolicy, ScentEmission
from najamjad_agent.reporting.filing import MatchFiler


@pytest.fixture()
def filer(tmp_path):
    return MatchFiler(tmp_path, "najamjad-vs-rival", "uid-1", ("najamjad", "rival"))


def _declaration(tmp_path):
    """`MatchFiler` writes into the directory it is given, not a subfolder."""
    path = next(tmp_path.glob("declaration_*.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_declaration_records_what_we_emitted(filer, tmp_path) -> None:
    """The whole point: our choice is on the record we file."""
    policy = EmissionPolicy(scent_mode=ScentEmission.NONE, hints=False, grid_size=7)

    filer.file_match(
        [], [], None, {}, "sha", groups_block={}, emission=policy.as_declaration()
    )

    assert _declaration(tmp_path)["emission"] == {"scent": "none", "hint": "silent"}


def test_full_emission_is_declared_too(filer, tmp_path) -> None:
    """Silence is not the only choice worth recording — so is not being silent."""
    policy = EmissionPolicy(scent_mode=ScentEmission.FULL, hints=True, grid_size=7)

    filer.file_match(
        [], [], None, {}, "sha", groups_block={}, emission=policy.as_declaration()
    )

    assert _declaration(tmp_path)["emission"] == {"scent": "full", "hint": "spoken"}


def test_no_emission_leaves_the_key_out_entirely(filer, tmp_path) -> None:
    """An absent key beats `emission: null`.

    The A6 report went out with `agreement: null` and that is the shape this
    project has spent real effort removing from its artifacts.
    """
    filer.file_match([], [], None, {}, "sha", groups_block={})

    assert "emission" not in _declaration(tmp_path)


def test_the_filer_is_actually_given_one(tmp_path) -> None:
    """The seam, since the defect was a missing call rather than broken code.

    Every assertion above passes while `build_filer` never supplies `emission`,
    which is exactly how this component stayed dead through eleven predecessors.
    """
    import inspect

    from najamjad_agent.sdk import match_filing

    source = inspect.getsource(match_filing.build_filer)

    assert "as_declaration()" in source, "build_filer no longer declares our emission"
