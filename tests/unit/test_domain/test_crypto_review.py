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
    """One hashing implementation means one place to get the byte format right.

    Each allowed module hashes for a *different* purpose, and none of them
    computes a commit: crypto.py owns commit-reveal, scent_models.py fingerprints
    the pheromone model for the pre-series lock, nonce_vault.py derives its
    at-rest keystream, and session_guard.py derives the HMAC session token that
    keeps strangers out of a live match.
    """
    allowed = {
        "crypto.py",  # commit-reveal, the one byte format that must match a peer
        "scent_models.py",  # pheromone-model fingerprint for the pre-series lock
        "nonce_vault.py",  # at-rest keystream for spilled nonces
        "session_guard.py",  # HMAC session token binding a match to one opponent
        "contract.py",  # config_sha256 + the derived game_uid both peers compute
        "agreement.py",  # the symmetric result signature both peers must match
    }
    offenders = [p.name for p in SOURCES if "hashlib.sha256" in _read(p) and p.name not in allowed]
    assert offenders == []


def test_only_crypto_computes_commit_hashes() -> None:
    """The rule that actually matters: one byte format for commitments."""
    offenders = [p.name for p in SOURCES if "def commit_of" in _read(p) and p.name != "crypto.py"]
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
    """`random` is predictable; a guessable nonce would break every commitment.

    Two exceptions, both deliberate, both offline, both proved harmless below.

    The template bank uses seeded `random` to vary hint wording, because
    reproducible dialogue makes a lost game debuggable and a replay faithful.

    `strategy/tournament.py` breeds strategy parameters, and there `secrets`
    would be actively *wrong*: it cannot be seeded, and an unreproducible tuning
    run is an opinion with a number attached. Rule 49 means a grader can re-run
    it, which requires the same seed to give the same answer.

    Neither touches cryptographic material, and the two tests below prove it
    rather than asserting it.
    """
    allowed = {"template_provider.py", "tournament.py"}
    for path in SOURCES:
        if path.name in allowed:
            continue
        text = _read(path)
        assert "import random" not in text, f"{path.name} imports the predictable random module"


def test_the_template_bank_never_produces_cryptographic_material() -> None:
    """The one module allowed weak randomness must not reach the crypto layer."""
    source = _read(SRC / "llm/template_provider.py")
    for forbidden in ("nonce", "token_hex", "commit", "seal(", "hashlib"):
        assert forbidden not in source, f"template_provider.py touches {forbidden!r}"


def test_seeded_randomness_is_confined_to_the_llm_layer() -> None:
    """Nothing in domain/ or net/ may depend on a predictable RNG."""
    for folder in ("domain", "net", "protocol", "negotiation"):
        for path in (SRC / folder).rglob("*.py"):
            assert "import random" not in _read(path), f"{folder}/{path.name} imports random"


def test_nonce_entropy_is_sixteen_bytes() -> None:
    assert crypto.NONCE_BYTES == 16
    assert len(crypto.new_nonce()) == 32


def test_canonicalisation_is_pinned_in_one_module() -> None:
    """A second json.dumps with different flags would silently break audits.

    The rule is about anything a peer hashes, replays, or grades. `app_config`
    is the deliberate counter-example: it writes the operator's own
    `config/setup.json` indented and human-readable, which is the *opposite* of
    the canonical encoding and must stay that way — a config file compacted to
    audit separators would be unreadable to the person who edits it. It never
    touches a payload anyone verifies.
    """
    allowed = {"canonical.py", "nonce_vault.py", "app_config.py"}
    offenders = [
        path.name for path in SOURCES if "json.dumps" in _read(path) and path.name not in allowed
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


def test_the_strategy_search_never_produces_cryptographic_material() -> None:
    """The second module allowed weak randomness must not reach the crypto layer.

    Same discipline as the template bank: the exception is only defensible while
    the module provably cannot influence a nonce or a commitment.
    """
    source = _read(SRC / "strategy/tournament.py")
    for forbidden in ("nonce", "token_hex", "commit", "seal(", "hashlib"):
        assert forbidden not in source, f"tournament.py touches {forbidden!r}"
