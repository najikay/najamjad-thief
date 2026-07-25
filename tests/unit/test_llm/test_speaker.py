"""Tests for the Speaker — the single vetted exit from decision to spoken word."""

import json
from types import SimpleNamespace

import pytest

from najamjad_agent.llm.base import Completion, ProviderUnavailableError
from najamjad_agent.llm.router import LLMRouter
from najamjad_agent.llm.speaker import Speaker
from najamjad_agent.llm.template_provider import TemplateProvider
from najamjad_agent.llm.token_meter import Usage


class ScriptedProvider:
    """A model that says exactly what the test wants it to say."""

    name = "anthropic"
    free = False

    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls = 0

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return Completion(
            text=self.reply,
            provider=self.name,
            model="test-model",
            usage=Usage(input_tokens=50, output_tokens=10),
        )

    def healthy(self) -> bool:
        return True


def _facts(step: int = 2, role: str = "thief") -> SimpleNamespace:
    return SimpleNamespace(step=step, role=role, sub_game=1)


def _speaker(provider, events: list[dict] | None = None, **kwargs) -> Speaker:
    router = LLMRouter([provider, TemplateProvider(seed=1)], emit=(events.append if events is not None else None))
    return Speaker(
        router=router,
        template=TemplateProvider(map_area="New York", seed=1),
        arena="New York",
        emit=(events.append if events is not None else None),
        **kwargs,
    )


def test_a_model_hint_is_used_when_it_is_well_formed() -> None:
    reply = json.dumps({"message": "Slipping past the docks tonight", "verdict": "lie"})
    text, intent = _speaker(ScriptedProvider(reply)).compose(_facts())
    assert text == "Slipping past the docks tonight"
    assert intent == "lie"


def test_a_prose_reply_is_still_usable() -> None:
    """Models drift from JSON; that must cost quality, not the turn."""
    text, intent = _speaker(ScriptedProvider("Heading for the bridge.")).compose(_facts())
    assert text == "Heading for the bridge."
    assert intent in ("truth", "lie")


def test_a_coordinate_leak_from_the_model_is_stripped(events: list[dict] | None = None) -> None:
    """Book rule 27 — the model asked nicely, the guard enforces."""
    captured: list[dict] = []
    reply = json.dumps({"message": "I am at (3,4) by the park", "verdict": "truth"})
    text, _ = _speaker(ScriptedProvider(reply), captured).compose(_facts())
    assert "(3,4)" not in text
    assert any(event.get("event") == "hint.corrected" for event in captured)


def test_an_over_long_model_hint_is_trimmed() -> None:
    reply = json.dumps({"message": " ".join(["word"] * 40), "verdict": "truth"})
    text, _ = _speaker(ScriptedProvider(reply)).compose(_facts())
    assert len(text.split()) <= 15


def test_a_provider_outage_falls_back_to_a_template_line() -> None:
    captured: list[dict] = []
    speaker = Speaker(
        router=LLMRouter([ScriptedProvider(error=ProviderUnavailableError("down"))]),
        template=TemplateProvider(seed=3),
        arena="New York",
        emit=captured.append,
    )
    text, intent = speaker.compose(_facts())
    assert text
    assert intent in ("truth", "lie")
    assert any(event["event"] == "hint.fallback" for event in captured)


def test_an_empty_model_reply_falls_back_to_the_template() -> None:
    text, _ = _speaker(ScriptedProvider("")).compose(_facts())
    assert text.strip()


def test_off_cycle_turns_skip_the_model() -> None:
    """`every_n_steps` is a quality dial; off-cycle turns still speak."""
    captured: list[dict] = []
    provider = ScriptedProvider(json.dumps({"message": "from the model", "verdict": "truth"}))
    speaker = _speaker(provider, captured, every_n_steps=2)
    text, _ = speaker.compose(_facts(step=3))
    assert provider.calls == 0
    assert text and text != "from the model"
    assert any(event["event"] == "hint.offcycle" for event in captured)


def test_on_cycle_turns_do_call_the_model() -> None:
    provider = ScriptedProvider(json.dumps({"message": "from the model", "verdict": "truth"}))
    speaker = _speaker(provider, every_n_steps=2)
    text, _ = speaker.compose(_facts(step=4))
    assert provider.calls == 1
    assert text == "from the model"


def test_every_step_speaks_when_the_cadence_is_one() -> None:
    provider = ScriptedProvider(json.dumps({"message": "always", "verdict": "truth"}))
    speaker = _speaker(provider, every_n_steps=1)
    for step in range(1, 4):
        assert speaker.compose(_facts(step=step))[0] == "always"
    assert provider.calls == 3


@pytest.mark.parametrize("role", ["thief", "police"])
def test_both_roles_produce_a_vetted_hint(role: str) -> None:
    provider = ScriptedProvider(json.dumps({"message": "Circling the block", "verdict": "truth"}))
    text, intent = _speaker(provider).compose(_facts(role=role))
    assert text and intent in ("truth", "lie")


def test_template_and_model_hints_share_one_guard() -> None:
    """Meta: there must be no path to the wire that skips vetting."""
    from pathlib import Path

    source = Path(__file__).resolve().parents[3] / "src/najamjad_agent/llm/speaker.py"
    text = source.read_text(encoding="utf-8")
    assert text.count("guard_hint(") == 1, "vetting must happen in exactly one place"
    assert text.count("return self._vet(") + text.count("return self._vet") >= 3


def test_an_invalid_model_verdict_is_sealed_as_truth() -> None:
    reply = json.dumps({"message": "Heading out", "verdict": "maybe"})
    _, intent = _speaker(ScriptedProvider(reply)).compose(_facts())
    assert intent == "truth"
