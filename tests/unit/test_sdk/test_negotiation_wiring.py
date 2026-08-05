"""The dashboard's negotiation buttons were wired to nothing.

`AgentActions.approve_terms` and `propose_terms` both dereference
`self._negotiation`, and `build_sdk` never passed one — so `_negotiation` was
`None` and either control raised `AttributeError` on click. The UI layer above
them (`ui/controls.py`) validates its inputs carefully and then calls into a
crash.

Wiring it also gives `negotiation/flow.py` and the playbook's red lines their
first production caller. A match itself is agreed take-it-or-leave-it by
`exchange_agreement`, which demands byte-identical terms (rule 11); this manual
path is where a human settles those terms with a *new* opponent beforehand,
which is the thing standing between us and a counted match.
"""

import pytest

from najamjad_agent.negotiation.flow import Negotiation, Stage
from najamjad_agent.sdk.actions import AgentActions

TERMS = {"grid_size": 7, "num_games": 6}


def test_an_unwired_actions_object_still_fails_loudly() -> None:
    """Pinning the defect, so a future refactor cannot quietly restore it."""
    bare = AgentActions()

    with pytest.raises(AttributeError):
        bare.approve_terms(TERMS)


def test_approving_works_from_a_cold_start() -> None:
    """The sequence production can actually perform, which is the only one.

    An earlier version of this test called `propose_terms()` first and passed
    because of it — but nothing in the UI routes to propose (there is an
    approve endpoint and no propose endpoint), so a fresh process can only ever
    reach `approve` from `IDLE`. `agree` refuses from `IDLE`, so supplying a
    `Negotiation` had merely turned an `AttributeError` into a
    `NegotiationError` at the same wall, and `ui/views.py` catches neither.
    """
    actions = AgentActions(negotiation=Negotiation(our_group="najamjad"))

    assert actions.approve_terms(TERMS)["terms"] == TERMS


def test_the_ui_layer_reaches_it_without_raising() -> None:
    """Through the real control, since that is what the button calls."""
    from najamjad_agent.ui.controls import approve_terms as ui_approve

    class Sdk:
        controls_enabled = True
        actions = AgentActions(negotiation=Negotiation(our_group="najamjad"))
        _negotiation = actions._negotiation  # noqa: SLF001

        @staticmethod
        def negotiation_timeline():
            return Sdk._negotiation.timeline

    state = ui_approve(Sdk(), TERMS)

    assert state["timeline"], "the approval left no record to render"


@pytest.mark.parametrize("constructed", ["AgentActions", "AgentSdk"])
def test_bootstrap_supplies_one_to_both_halves(constructed: str) -> None:
    """The seam. Every assertion above passes with `build_sdk` still unwired.

    Both halves, because they are separate attributes on separate classes:
    `AgentActions._negotiation` is the half that *acts* and `AgentSdk._negotiation`
    the half that *renders*. Wiring only the first left the timeline permanently
    empty while `flow.py`'s docstring promised the dashboard rendered it.

    Parsed rather than grepped. A string search for `negotiation=Negotiation(`
    passes on a comment and fails the moment someone hoists the object into a
    local — which is precisely the refactor this change makes, so the grep
    version broke on its own author. Reading the argument list survives that
    and still catches the argument going missing, which was the whole defect.
    """
    import ast
    import inspect

    from najamjad_agent.sdk import bootstrap

    tree = ast.parse(inspect.getsource(bootstrap))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == constructed
    ]

    assert calls, f"{constructed} is no longer constructed in bootstrap"
    assert any(
        keyword.arg == "negotiation" for call in calls for keyword in call.keywords
    ), f"{constructed} is built without a negotiation"


def test_a_ceiling_breach_is_countered_rather_than_walked_away_from() -> None:
    """`ABANDONED` is terminal, and one legal ask must not end the match.

    Our own bootstrap records a cold DeepSeek call taking 27-61 s against a
    30 s budget, so a conforming peer without a warm-up step genuinely needs
    longer than our 45 s ceiling and is not trying to cheat us. Rejecting would
    abandon the negotiation on a process-lifetime object — no reopening without
    a restart — and we have zero counted matches. Push back to our number
    instead.
    """
    talks = Negotiation(our_group="najamjad")

    talks.receive({"response_timeout_sec": 60})

    assert talks.stage is Stage.COUNTERED
    assert talks.stage is not Stage.ABANDONED


def test_lowering_a_book_minimum_still_ends_it() -> None:
    """Rule 12 is not a preference, so it is still not something we haggle."""
    talks = Negotiation(our_group="najamjad")

    talks.receive({"response_timeout_sec": 5})

    assert talks.stage is Stage.ABANDONED
