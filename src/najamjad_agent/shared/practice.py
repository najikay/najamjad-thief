"""Practice mode — a run that cannot reach the lecturer.

Manual testing needs the *whole* pipeline: play a series, file the artifacts,
build the report, send it, and read the mail that arrives. Stopping short of the
send leaves the one step that failed in assignment 6 untested.

So practice mode does not disable sending. It **redirects** it: every report
goes to the operator's own inbox, delivered for real, so what lands in the
mailbox is the same message a counted match would produce.

That makes the redirect the only thing between a rehearsal and a graded
mailbox, which is too much weight for a string substitution to carry alone. The
invariant here is deliberately stronger than "rewrite the address":

    while practice mode is on, the outgoing recipient must equal the
    redirect address — anything else raises instead of sending.

A rewrite that silently does not happen is then a loud failure rather than mail
to the lecturer. The guard costs one comparison and removes the entire class of
"the redirect had a bug" from the risk register.

One switch, not four. A testing mode that can be half-enabled — mail redirected
but artifacts still filed as counted, or the banner off — is how a practice run
gets mistaken for a real one, so everything hangs off `enabled`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .app_config import DEFAULT_PATH, load_setup, save_setup, setting

BANNER = "PRACTICE RUN — not a counted match"
SEND = "send"
#: Per-process practice override; see `current`.
PRACTICE_ENV = "NAJAMJAD_PRACTICE"
SUBJECT_PREFIX = "[PRACTICE] "
ADDRESS = re.compile(r"<([^>]+)>")


class PracticeError(RuntimeError):
    """Raised when a practice run is about to send somewhere it must not."""


def bare_address(recipient: str) -> str:
    """Reduce a recipient to the address inside it, lowercased and stripped.

    A display-name form wraps the address in angle brackets, so comparing
    recipients as written would let `Dr Segal <the-address>` slip past a check
    against `the-address` — precisely the recipient the guard exists to catch.
    Case and surrounding spaces are normalised for the same reason.

    Input: a recipient as written, with or without a display name.
    Output: the bare address, lowercased and stripped.
    Setup: none.
    """
    match = ADDRESS.search(recipient)
    return (match.group(1) if match else recipient).strip().lower()


@dataclass(frozen=True)
class PracticeMode:
    """Whether this run is practice, and where its mail goes instead.

    Input: `enabled`, and the address practice reports are redirected to.
    Output: `route` gives the recipient to send to, `verify` refuses anything
        else while practice is on, `subject` marks the mail, and `state`
        renders the pair for the dashboard.
    Setup: built by `load_practice` from the `practice` block of
        `config/setup.json`; frozen, so switching modes replaces the instance
        rather than mutating one another caller may be holding.
    """

    enabled: bool = False
    redirect_to: str = ""

    def route(self, recipient: str) -> str:
        """The address mail should actually go to.

        In practice mode a missing redirect is an error rather than a
        pass-through: falling back to the configured recipient would deliver to
        the lecturer precisely when the operator asked us not to.
        """
        if not self.enabled:
            return recipient
        if not self.redirect_to:
            raise PracticeError(
                "practice mode is on but no redirect address is configured; "
                "set practice.redirect_to in config/setup.json"
            )
        return self.redirect_to

    def verify(self, recipient: str) -> None:
        """Refuse to send anywhere but the redirect while practice mode is on.

        This is the belt to `route`'s braces. It does not trust that `route`
        was called, or called correctly — it checks the address at the point of
        no return, where being wrong costs an email to the lecturer.
        """
        if not self.enabled:
            return
        if bare_address(recipient) != bare_address(self.redirect_to):
            raise PracticeError(
                f"practice mode would have sent to {recipient!r}, not the "
                f"redirect address {self.redirect_to!r}; refusing to send"
            )

    def mode_for(self, configured: str) -> str:
        """The send mode a practice run needs, or the configured one.

        Practice mode forces a real send. That looks like the unsafe direction
        and is the opposite: the entire design is that a practice run exercises
        delivery for real — to *us* — because the send is the step assignment 6
        lost matches to, and a draft would leave it untested.

        Without this, "practice" was two switches: the toggle, and a hand-edit
        of `email.mode`. Getting the pair half-right meant a practice run that
        silently drafted, which reads exactly like a successful send until you
        look in the wrong folder. One switch, as promised.
        """
        return SEND if self.enabled else configured

    def subject(self, subject: str) -> str:
        """Mark the mail so a practice report is never mistaken in the inbox."""
        if not self.enabled or subject.startswith(SUBJECT_PREFIX):
            return subject
        return f"{SUBJECT_PREFIX}{subject}"

    def state(self) -> dict[str, Any]:
        """What the dashboard shows the operator."""
        return {
            "enabled": self.enabled,
            "redirect_to": self.redirect_to if self.enabled else "",
            "banner": BANNER if self.enabled else "",
        }


def guard_counted_delivery(mode: str, counted: bool) -> str:
    """Refuse to start a counted match that would only draft its report.

    Rules 33-34 require the report to be **sent**; a draft sits in a folder and
    is never delivered, which rule 35 scores as not having played. So a counted
    series run in `draft` plays six real mini-games and files nothing that
    counts — and nothing about the run looks wrong, because drafting succeeds.

    `strength.guard_counted` says it is "modelled on the `email.mode` draft
    trap", and the trap it was modelled on had no guard of its own. This is it.
    Raising rather than flipping the default on purpose: silently switching to
    `send` would mail the grader from every development run, which is the
    mistake in the other direction and much harder to take back.

    Practice runs are unaffected — `mode_for` already forces a real send to our
    own address, so `counted` is false for them and this never fires.
    """
    resolved = str(mode or "").strip().lower()
    if counted and resolved != SEND:
        raise PracticeError(
            f"a counted match must deliver its report, but email.mode is "
            f"{resolved or 'unset'!r}. Rules 33-34 require the JSON to be sent and rule 35 "
            f"scores an undelivered report as not having played — set email.mode = \"{SEND}\" "
            f"in your role config, or enable practice mode to rehearse safely."
        )
    return resolved


def load_practice(setup: dict[str, Any]) -> PracticeMode:
    """Build the mode from `setup.json`; absent means off.

    Off is the only safe default: a config that fails to load must not leave
    the agent believing it is in a mode where sending is harmless.
    """
    return PracticeMode(
        enabled=bool(setting(setup, "practice.enabled", False)),
        redirect_to=str(setting(setup, "practice.redirect_to", "")),
    )


def save_practice(enabled: bool, path: Path | str = DEFAULT_PATH) -> PracticeMode:
    """Persist the switch, and return the mode now in force.

    Written to `setup.json` rather than held in memory so the file stays the
    single source of truth. Everything that builds a sender re-reads it at the
    moment it needs it, which is what lets a toggle take effect without a
    restart — and, more importantly, means the dashboard and the send path can
    never disagree about which mode we are in.

    The rest of the file is preserved key-for-key: this rewrites one flag, not
    the operator's configuration.
    """
    target = Path(path)
    setup = load_setup(target)
    block = dict(setup.get("practice") or {})
    block["enabled"] = bool(enabled)
    setup["practice"] = block
    save_setup(setup, target)
    return load_practice(setup)


def current() -> PracticeMode:
    """The mode in force right now: the environment first, then disk.

    Deliberately not cached. A stale "practice is on" is the one belief that
    must never outlive the config that justified it.

    `NAJAMJAD_PRACTICE` exists because toggling the *file* to run a practice
    match dirties a tracked config and trips the test that pins the shipped
    default to off — which happened four times in one afternoon, each time
    needing the flag flipped back before a commit. A per-process override runs
    a practice match without touching the repository, and expires with the
    process, which is the correct lifetime for "this run is not counted".
    """
    override = os.environ.get(PRACTICE_ENV, "")
    if override:
        setup = load_setup()
        return PracticeMode(
            enabled=override.strip().lower() not in ("", "0", "false", "no"),
            redirect_to=str(setting(setup, "practice.redirect_to", "")),
        )
    return load_practice(load_setup())
