"""Practice mode (T-2420).

The design choice under test: practice runs **really send**, because the send
is the step that failed in assignment 6 and a mode that skips it leaves the
riskiest code path untested. Mail goes to the operator instead of the lecturer.

That puts the whole safety story on one string rewrite, which is why `verify`
exists as a second, independent check at the point of no return. Most of these
tests are about that guard: not that the redirect works, but that a redirect
which *fails* is caught rather than delivered.
"""

import pytest

from najamjad_agent.shared.practice import (
    BANNER,
    PracticeError,
    PracticeMode,
    bare_address,
    load_practice,
)

LECTURER = "rmisegal@gmail.com"
MINE = "najikayal4@gmail.com"
ON = PracticeMode(enabled=True, redirect_to=MINE)
OFF = PracticeMode()


def test_a_real_run_is_untouched():
    """Off is the default and must change nothing at all."""
    assert OFF.route(LECTURER) == LECTURER
    assert OFF.subject("Result") == "Result"
    assert OFF.state()["enabled"] is False


def test_practice_redirects_to_the_operator():
    assert ON.route(LECTURER) == MINE


def test_the_guard_refuses_an_address_the_redirect_missed():
    """The test that matters.

    `route` and `verify` are deliberately redundant: if the rewrite is ever
    skipped, mis-ordered, or bypassed by a caller building its own recipient,
    this is what stands between a rehearsal and the grader's inbox.
    """
    with pytest.raises(PracticeError, match="refusing to send"):
        ON.verify(LECTURER)


def test_the_guard_is_silent_on_the_address_it_expects():
    ON.verify(MINE)


def test_a_display_name_cannot_smuggle_the_address_past_the_guard():
    """`"Dr Segal <rmisegal@gmail.com>"` is the lecturer, however it is spelled."""
    with pytest.raises(PracticeError):
        ON.verify(f"Dr Segal <{LECTURER}>")


def test_case_and_spacing_do_not_defeat_the_guard():
    ON.verify(f"  {MINE.upper()} ")


def test_practice_without_a_redirect_refuses_rather_than_falling_through():
    """The dangerous failure mode: a half-configured practice mode that quietly
    passes the lecturer's address straight through."""
    with pytest.raises(PracticeError, match="no redirect address"):
        PracticeMode(enabled=True).route(LECTURER)


def test_the_subject_is_marked_so_the_inbox_is_unambiguous():
    assert ON.subject("Result najamjad vs rival").startswith("[PRACTICE]")


def test_marking_is_not_applied_twice():
    assert ON.subject(ON.subject("Result")).count("[PRACTICE]") == 1


def test_the_state_carries_a_banner_only_while_on():
    assert ON.state() == {"enabled": True, "redirect_to": MINE, "banner": BANNER}
    assert OFF.state()["banner"] == ""


@pytest.mark.parametrize(
    "written,expected",
    [("A@B.C", "a@b.c"), (" x@y.z ", "x@y.z"), ("N <q@r.s>", "q@r.s")],
)
def test_addresses_reduce_to_the_thing_being_compared(written, expected):
    assert bare_address(written) == expected


def test_an_absent_config_means_off():
    """A config that failed to load must not leave us believing sending is safe."""
    assert load_practice({}).enabled is False


def test_the_shipped_config_is_off():
    """Nobody should discover practice mode was left on during a counted match."""
    from najamjad_agent.shared.app_config import load_setup

    assert load_practice(load_setup()).enabled is False


def test_loading_reads_both_fields():
    mode = load_practice({"practice": {"enabled": True, "redirect_to": MINE}})

    assert mode.enabled is True and mode.redirect_to == MINE


def test_practice_forces_a_real_send_even_when_the_config_says_draft():
    """One switch, not two.

    Practice mode exists to exercise delivery, so a draft would defeat it — and
    a silent draft reads exactly like a successful send until you look in the
    wrong folder. Before this, a practice run needed the toggle *and* a
    hand-edit of `email.mode`.
    """
    assert ON.mode_for("draft") == "send"


def test_a_counted_run_keeps_whatever_mode_was_configured():
    """Off must change nothing — including not arming a send that was drafted."""
    assert OFF.mode_for("draft") == "draft"
    assert OFF.mode_for("send") == "send"
