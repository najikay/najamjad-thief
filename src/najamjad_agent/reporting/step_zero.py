"""Step-0: the signed declaration that opens every mini-game.

Before the first move each side seals a record of what it is running on —
hardware, LLM model, code version, team, mini-game number and the **git commit
hash** the match is played with (book rule 53, mandatory). Sealing it under the
same commit-reveal scheme means neither side can retroactively claim different
hardware or a different code version once results are known.

Token metering starts here, so the sealed record also carries the running totals
that end up in the result email (rule 54).
"""

from typing import Any

from ..domain.crypto import SealedRecord, seal
from ..shared.sysinfo import collect_spec, git_commit
from ..shared.version import CODE_VERSION

STEP_ZERO = 0
RECORD_TYPE = "system_spec"


def build_declaration(
    group_name: str,
    role: str,
    sub_game: int,
    model: str,
    opponent_group: str = "",
    spec: dict | None = None,
    commit: str | None = None,
    tokens_total: int = 0,
) -> dict[str, Any]:
    """Assemble the Step-0 payload in the reference field shape."""
    return {
        "step": STEP_ZERO,
        "type": RECORD_TYPE,
        "spec": spec if spec is not None else collect_spec(),
        "model": model,
        "code_version": CODE_VERSION,
        "github_commit": commit if commit is not None else git_commit(),
        "group_name": group_name,
        "opponent_group_id": opponent_group,
        "role": role,
        "sub_game": sub_game,
        "tokens_total": tokens_total,
    }


def seal_declaration(declaration: dict[str, Any]) -> SealedRecord:
    """Seal the declaration so it can never be revised after the fact."""
    return seal(declaration)


def declaration_is_complete(declaration: dict[str, Any]) -> list[str]:
    """List missing or placeholder fields that would forfeit the bonus.

    Returned rather than raised: a missing GPU probe should warn the operator,
    not block a match that is about to start.
    """
    problems: list[str] = []
    for field in ("model", "code_version", "github_commit", "group_name", "role"):
        if not declaration.get(field):
            problems.append(f"{field} is empty")
    if declaration.get("github_commit") == "unknown":
        problems.append("github_commit could not be resolved (rule 53 requires it)")
    spec = declaration.get("spec") or {}
    for field in ("os", "cpu_type", "cpu_cores", "ram_gb"):
        if not spec.get(field) or spec.get(field) == "unknown":
            problems.append(f"spec.{field} unavailable (computational-fairness bonus at risk)")
    return problems
