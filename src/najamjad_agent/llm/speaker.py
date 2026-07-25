"""The Speaker — the only path from a decision to words on the wire.

This is where the LLM layer meets the game loop, and it is deliberately the
*single* exit: template lines and model output pass through exactly the same
guard, so there is no path by which a hint reaches an opponent unvetted.

Two economies live here. `every_n_steps` skips the model on off-cycle turns
(the opponent does not need fresh prose every step to be misled), and a model
failure silently becomes a template line rather than a lost turn. Both are
quality decisions rather than cost decisions: the budget has room.
"""

from collections.abc import Callable
from typing import Any

from .base import ProviderError
from .hint_guard import guard_hint
from .hint_parser import extract_json
from .prompts import hint_prompt
from .router import LLMRouter
from .template_provider import TemplateProvider


class Speaker:
    """Produces the free-language hint and the intent sealed alongside it."""

    def __init__(
        self,
        router: LLMRouter,
        template: TemplateProvider,
        arena: str = "",
        hint_max_words: int = 15,
        every_n_steps: int = 1,
        emit: Callable[[dict], None] | None = None,
    ) -> None:
        """Wire the speaker to its router and its offline floor."""
        self._router = router
        self._template = template
        self._arena = arena
        self._word_cap = hint_max_words
        self._every_n = max(1, every_n_steps)
        self._emit = emit or (lambda _event: None)

    def compose(self, facts: Any) -> tuple[str, str]:
        """Return (hint_text, intent) for this turn, never raising."""
        role = getattr(facts, "role", "police")
        step = int(getattr(facts, "step", 0) or 0)
        offline = self._template.compose(role, self._word_cap)
        intent = offline["verdict"]

        if step % self._every_n != 0:
            self._emit({"event": "hint.offcycle", "step": step})
            return self._vet(offline["message"], intent, step)

        try:
            system, user = hint_prompt(role, self._arena, self._word_cap, intent)
            completion = self._router.complete(
                system, user, max_tokens=120, purpose="hint", sub_game=int(
                    getattr(facts, "sub_game", 0) or 0
                )
            )
        except ProviderError as error:
            self._emit({"event": "hint.fallback", "reason": type(error).__name__})
            return self._vet(offline["message"], intent, step)
        text, model_intent = _read_hint(completion.text, offline["message"], intent)
        return self._vet(text, model_intent, step)

    def _vet(self, text: str, intent: str, step: int) -> tuple[str, str]:
        """The single egress: everything we say passes the same guard."""
        result = guard_hint(text, intent, self._word_cap)
        if result.problems:
            self._emit({"event": "hint.corrected", "step": step, "problems": list(result.problems)})
        return result.text, result.intent


def _read_hint(reply: str, fallback: str, fallback_intent: str) -> tuple[str, str]:
    """Pull message and verdict from a model reply, tolerating loose JSON."""
    payload = extract_json(reply)
    if not payload:
        # The model answered in prose rather than JSON: usable as the message,
        # with our own intent preserved since it was ours to choose.
        return (reply.strip() or fallback), fallback_intent
    message = str(payload.get("message") or "").strip() or fallback
    verdict = str(payload.get("verdict") or fallback_intent)
    return message, verdict
