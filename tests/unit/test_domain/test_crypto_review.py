"""Meta-tests enforcing the crypto security checklist across the whole package.

These assert properties of the *source tree*, not of one function: they are how
the checklist in `docs/PRD_commit_reveal.md` stays true as code is added.
"""

from pathlib import Path

import pytest

from najamjad_agent.domain import crypto

SRC = Path(__file__).resolve().parents[3] / "src/najamjad_agent"
SOURCES = sorted(SRC.rglob("*.py"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sources_were_found() -> None:
    assert len(SOURCES) > 10, "sanity: the meta-tests must actually scan the package"


def test_sha256_is_only_computed_in_designated_modules() -> None:
    """One hashing implementation means one place to get the byte format right."""
    allowed = {"crypto.py", "scent_models.py", "nonce_vault.py"}
    offenders = [p.name for p in SOURCES if "hashlib.sha256" in _read(p) and p.name not in allowed]
    assert offenders == []


def test_commit_comparison_uses_constant_time_compare() -> None:
    """Timing-safe comparison is the only way commits are checked."""
    source = _read(SRC / "domain/crypto.py")
    assert "secrets.compare_digest" in source
    assert "commit_of(payload, nonce) == commit" not in source


def test_no_module_compares_a_commit_with_plain_equality() -> None:
    for path in SOURCES:
        text = _read(path)
        assert "== commit" not in text, f"{path.name} compares a commit unsafely"


def test_nonces_come_from_the_secrets_module_only() -> None:
    """`random` is predictable; a guessable nonce would break every commitment."""
    for path in SOURCES:
        text = _read(path)
        assert "import random" not in text, f"{path.name} imports the predictable random module"


def test_nonce_entropy_is_sixteen_bytes() -> None:
    assert crypto.NONCE_BYTES == 16
    assert len(crypto.new_nonce()) == 32


def test_canonicalisation_is_pinned_in_one_module() -> None:
    """A second json.dumps with different flags would silently break audits."""
    offenders = [
        path.name
        for path in SOURCES
        if "json.dumps" in _read(path) and path.name not in {"canonical.py", "nonce_vault.py"}
    ]
    assert offenders == []


def test_canonical_encoding_flags_are_exactly_the_interop_contract() -> None:
    source = _read(SRC / "protocol/canonical.py")
    assert "sort_keys=True" in source
    assert "ensure_ascii=False" in source
    assert 'SEPARATORS = (",", ":")' in source


def test_no_subprocess_uses_a_shell() -> None:
    """shell=True with any interpolated value is a command-injection path.

    Scans code lines only — prose in a docstring may name the anti-pattern it
    is explaining without being a violation.
    """
    for path in SOURCES:
        for line in _read(path).splitlines():
            code = line.split("#", 1)[0]
            assert "shell=True" not in code, f"{path.name} spawns a shell: {line.strip()[:60]}"


@pytest.mark.parametrize("secret", ["nonce", "api_key", "token"])
def test_secrets_are_never_formatted_into_log_calls(secret: str) -> None:
    for path in SOURCES:
        for line in _read(path).splitlines():
            stripped = line.strip()
            if stripped.startswith(("logger.", "log.", "print(")):
                assert secret not in stripped, f"{path.name}: {stripped[:60]}"
