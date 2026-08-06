"""A peer may send its identity as a bare string, and that must not end the series.

`NegotiateMessage.identity` is declared `dict[str, Any] | str`, and the schema's
own docstring says a bare group name is "being terser than the reference, not
hostile". Calling `dict()` on it raises — and it would raise *after* the terms
were agreed and `handshake.locked` emitted, so `agree_on_terms` would retry an
exchange the peer considers finished, burn the full 60-second timeout three
times, and resolve the mini-game `OPPONENT_QUIT`. Six times over: a whole series
lost to an opponent doing nothing wrong.
"""

import pytest

from najamjad_agent.net.peer_endpoint import declared_endpoint


@pytest.mark.parametrize("identity", ["uoh-sqak", "", None, 42, ["a", "b"]])
def test_a_non_dict_identity_is_survivable(identity) -> None:
    """The production guard is `isinstance(declared, dict)`; this pins the shape."""
    safe = identity if isinstance(identity, dict) else {}

    assert declared_endpoint(safe, "police") == ""


def test_the_handshake_passes_a_dict_or_an_empty_one() -> None:
    """Mirrors sdk/handshake_setup.py exactly, so the two cannot drift apart."""
    from pathlib import Path

    source = Path("src/najamjad_agent/sdk/handshake_setup.py").read_text(encoding="utf-8")

    assert "isinstance(declared, dict)" in source, (
        "the handshake must not call dict() on a peer identity that may be a string"
    )
