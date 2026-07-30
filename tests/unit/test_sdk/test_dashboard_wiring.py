"""The dashboard panels a real match must actually fill (T-2441, T-2443).

Six mini-games were played across two machines while the board said "Waiting
for a game to start…", the Dialogue panel stayed empty, and the report panel
said "waiting for the match to end" after the mail had already gone.

None of it was broken. `attach_game`, `record_message` and `record_report` had
existed on the SDK since the beginning with **no production callers** — the
same defect class as `ArtifactWriter` having no caller and `GmailSender` never
receiving a service. Correct code that nothing invokes.

So these tests assert the *wiring*, not the rendering: a panel that renders
perfectly from data nobody supplies is worth nothing.
"""

import inspect

from najamjad_agent.sdk.sdk import AgentSdk


class Fsm:
    phase = type("P", (), {"value": "AWAITING_TURN"})()
    history: list = []


def test_attaching_a_game_makes_the_sdk_ready():
    sdk = AgentSdk()

    assert sdk.ready is False

    sdk.attach_game(state=object(), fsm=Fsm())

    assert sdk.ready is True, "the board panel keys off this"


def test_the_match_runner_hands_each_mini_game_to_its_observer():
    """The wiring that was missing. Asserted on the source because the
    alternative is standing up a whole match to observe one call."""
    from najamjad_agent.domain.match import MatchRunner

    source = inspect.getsource(MatchRunner.play_sub_game)

    assert "self._observer.attach_game(state, fsm)" in source


def test_bootstrap_passes_the_sdk_as_the_observer():
    """Nothing downstream can attach a game if this link is missing."""
    from najamjad_agent.sdk import bootstrap

    assert "_attach_match(actions, manager, chosen, bus, inboxes, meter, sdk)" in inspect.getsource(
        bootstrap.build_sdk
    )


def test_the_speaker_records_every_hint_it_clears():
    """Recorded in `_vet`, the single egress every return path passes through,
    so a new early return cannot silently stop appearing in the transcript."""
    from najamjad_agent.llm.speaker import Speaker

    assert "self._record(" in inspect.getsource(Speaker._vet)


def test_a_dashboard_failure_cannot_cost_us_a_turn():
    """ADR-005: the dashboard is a subscriber. An observer that raises must be
    swallowed, because a panel is never worth a forfeited move."""
    from najamjad_agent.llm.speaker import Speaker

    assert "contextlib.suppress" in inspect.getsource(Speaker._record)


def test_recording_a_message_reaches_the_transcript():
    sdk = AgentSdk()

    sdk.record_message("out", "Heading north past the bridge.", step=3, provider="deepseek")

    line = sdk.transcript()[0]
    assert line["direction"] == "out"
    assert line["provider"] == "deepseek", "the panel shows which model spoke"


def test_attaching_a_new_game_clears_the_previous_dialogue():
    """Six mini-games in a series: game 2 must not show game 1's hints."""
    sdk = AgentSdk()
    sdk.record_message("out", "from game one", step=1)

    sdk.attach_game(state=object(), fsm=Fsm())

    assert sdk.transcript() == []


def test_the_filer_tells_the_observer_what_happened_to_the_mail():
    from najamjad_agent.sdk import match_filing

    assert "observer.record_report(" in inspect.getsource(match_filing.build_filer)
