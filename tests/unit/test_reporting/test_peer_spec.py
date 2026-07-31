"""An opponent's hardware declaration must never block our filing (T-2446).

The match against `uoh-sqak` filed **zero artifacts**. Their handshake identity
declared `spec: {"os": …, "cpu": "arm", "cpu_count": 8, …}`, our `HardwareSpec`
requires `cpu_type` and `cpu_cores`, and `validate_egress` rejected the whole
declaration:

    EgressBlockedError: declaration blocked before sending:
      groups.uoh-sqak.hardware_spec.cpu_type: Field required
      groups.uoh-sqak.hardware_spec.cpu_cores: Field required

Six games played, nothing written, nothing emailed. Under rule 35 a missing
report scores as not having played — a guaranteed zero from a match we had
already played correctly.

Their declaration is *their* claim. We record it, normalise the obvious aliases,
and never let its shape fail our artifacts. Ours stays strictly validated,
because a blank in our own spec forfeits the fairness bonus (rule 24).
"""

from najamjad_agent.protocol.schemas_artifacts import DeclarationArtifact
from najamjad_agent.reporting.result_blocks import declaration_group

# The exact payload that cost us the match.
UOH_SQAK = {
    "group_id": "uoh-sqak",
    "group_name": "uoh-sqak",
    "members": ["a", "b"],
    "repos": {"cop": "https://github.com/x/cop", "thief": "https://github.com/x/thief"},
    "spec": {"os": "Darwin 25.2.0", "cpu": "arm", "cpu_count": 8, "ram_gb": 16.0},
}
OURS = {
    "group_id": "najamjad",
    "group_name": "NajAmjad",
    "members": ["Naji Kayal", "Amjad Abed"],
    "repos": {"cop": "https://github.com/najikay/najamjad-cop", "thief": "https://x/t"},
    "spec": {"cpu_type": "Intel64 Family 6", "cpu_cores": 4, "ram_gb": 7.9},
}


def _declaration(*groups: dict) -> dict:
    """A declaration payload shaped exactly as the filer builds it."""
    return {
        "game_id": "najamjad-vs-uoh-sqak",
        "game_uid": "uid-1",
        "groups": {str(g["group_id"]): declaration_group(g) for g in groups},
    }


def test_their_alias_spec_does_not_block_the_declaration() -> None:
    """The regression: this raised EgressBlockedError and filed nothing."""
    DeclarationArtifact.model_validate(_declaration(OURS, UOH_SQAK))


def test_their_aliases_are_normalised_not_discarded() -> None:
    """`cpu` and `cpu_count` are the same claim under different names."""
    block = declaration_group(UOH_SQAK)

    assert block["hardware_spec"]["cpu_type"] == "arm"
    assert block["hardware_spec"]["cpu_cores"] == 8
    assert block["hardware_spec"]["ram_gb"] == 16.0


def test_what_they_sent_is_recorded_verbatim() -> None:
    """Their raw claim survives normalisation, so an audit can see it."""
    block = declaration_group(UOH_SQAK)

    assert block["spec"] == UOH_SQAK["spec"]


def test_an_unusable_spec_still_files() -> None:
    """A spec we cannot map at all must cost the hardware block, never the match."""
    theirs = {**UOH_SQAK, "spec": {"machine": "something we have never seen"}}

    block = declaration_group(theirs)

    assert block.get("hardware_spec") is None
    assert block["spec"] == theirs["spec"]
    DeclarationArtifact.model_validate(_declaration(OURS, theirs))


def test_a_missing_spec_files_too() -> None:
    """An opponent that declares no hardware at all is not our failure."""
    theirs = {k: v for k, v in UOH_SQAK.items() if k != "spec"}

    DeclarationArtifact.model_validate(_declaration(OURS, theirs))


def test_our_own_spec_is_unchanged() -> None:
    """Ours already uses the schema's names; normalisation must not touch it."""
    block = declaration_group(OURS)

    assert block["hardware_spec"]["cpu_type"] == "Intel64 Family 6"
    assert block["hardware_spec"]["cpu_cores"] == 4
