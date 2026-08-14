"""Time to think is a floor: an agreement may grant more, never less.

Appendix F Table 19 sets a 30 s response timeout and a 60 s watchdog, and rule 12
makes every Appendix F minimum raisable by agreement and lowerable by nobody.
`validate_terms` enforced that for the board and the move budget and **not for
the clock** — it signed `response_timeout_sec: 1` without complaint until
2026-08-14.

That is not a cosmetic omission. A turn we cannot answer inside the agreed
timeout resolves as `EndReason.TIMEOUT`, so a peer proposing a one-second clock
wins every mini-game of the series without playing a move, and our own report
would record the losses as ours.

The negotiation playbook already held these lines — `response_timeout_sec` sits
at 30 with a ceiling of 45, `watchdog_timeout_sec` at 60 with a ceiling of 90.
The gap was that the playbook governs terms we *argue about* and `validate_terms`
governs terms we *sign*, and a peer whose opening proposal we accept never goes
through the playbook at all.
"""

from __future__ import annotations

import pytest

from najamjad_agent.negotiation.contract import ContractError, validate_terms


@pytest.mark.parametrize("seconds", [1, 5, 29])
def test_a_shorter_turn_clock_is_refused(seconds: int) -> None:
    """The attack: win on the clock rather than on the board."""
    with pytest.raises(ContractError) as caught:
        validate_terms({"response_timeout_sec": seconds})

    assert "minimum of 30" in str(caught.value)


@pytest.mark.parametrize("seconds", [30, 45, 120])
def test_a_longer_turn_clock_is_accepted(seconds: int) -> None:
    """Raising a minimum is explicitly legal (rule 12), and costs us nothing.

    Our moves are deterministic Python and take milliseconds; the only thing a
    longer clock buys is resilience against a slow link. The *ceiling* on how
    much we will grant is a negotiation position, not a contract rule, and lives
    in `playbook.POSITIONS` — conflating the two would have this gate refuse
    terms the playbook is entitled to concede.
    """
    validate_terms({"response_timeout_sec": seconds})


@pytest.mark.parametrize("seconds", [2, 59])
def test_a_shorter_watchdog_is_refused(seconds: int) -> None:
    """The watchdog is what finally ends a stalled game; shortening it ends live ones."""
    with pytest.raises(ContractError) as caught:
        validate_terms({"watchdog_timeout_sec": seconds})

    assert "minimum of 60" in str(caught.value)


def test_the_agreed_defaults_still_sign() -> None:
    """Table 19's own values must pass, or every honest match is refused."""
    validate_terms({"response_timeout_sec": 30, "watchdog_timeout_sec": 60})
