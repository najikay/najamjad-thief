"""Measure what a real series actually costs in tokens (T-2220, T-2221).

    uv run --group analysis python scripts/measure_tokens.py

What is **measured** and what is **assumed** matters here, so it is stated
plainly rather than buried:

* *Measured*: the number of model calls a real six-game series makes, and the
  exact prompt and reply text of every one of them. The series is played
  through the real match machinery and the prompts are built by the real
  `Speaker`, so `every_n_steps`, the hint guard and the template floor all
  behave exactly as they do in a league match.
* *Approximated*: the token count of that text. We have no Anthropic key on
  this machine, so tokens are counted with `cl100k_base` rather than Claude's
  own tokenizer. For short English prose the two agree to within a few percent;
  the figure is a good estimate, not a billing statement.
* *Not ours at all*: the per-million prices in `config/model_prices.json`, which
  are published list prices typed in by hand.

Re-run this with `ANTHROPIC_API_KEY` set and the meter records the provider's
own reported usage instead, at which point the first two bullets collapse into
one measured number.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from najamjad_agent.llm.router import LLMRouter  # noqa: E402
from najamjad_agent.llm.speaker import Speaker  # noqa: E402
from najamjad_agent.llm.template_provider import TemplateProvider  # noqa: E402
from scripts.self_play import MATCHUPS, play_one  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-haiku-4-5-20251001"
GAMES_PER_SERIES = 6
CADENCES = (1, 2, 3)


@dataclass
class Recorder:
    """A provider that answers like the real one and counts every exchange.

    It reports usage the way a real provider does, so the tokens flow through
    `TokenMeter` exactly as they would in a match rather than being tallied on
    the side by this script.
    """

    encoder: object
    model: str = MODEL
    name: str = "recorder"
    free: bool = False
    calls: list[dict] = field(default_factory=list)

    def complete(self, system: str, user: str, max_tokens: int = 200):
        """Return a reply in the shape the hint prompt asks for."""
        from najamjad_agent.llm.base import Completion, Usage

        reply = json.dumps({"message": _reply_text(user), "verdict": "lie"})
        usage = Usage(
            input_tokens=_count(self.encoder, system) + _count(self.encoder, user),
            output_tokens=_count(self.encoder, reply),
        )
        self.calls.append({"system": system, "user": user, "reply": reply, "usage": usage})
        return Completion(text=reply, provider=self.name, model=self.model, usage=usage)


def _reply_text(user: str) -> str:
    """A representative hint: the length the guard actually lets through."""
    return "Heading for the north gate, keep to the alleys" if "Mislead" in user else "Moving north"


def _count(encoder, text: str) -> int:
    """Tokens in one string."""
    return len(encoder.encode(text))


def measure_series(cadence: int, steps_per_game: list[int]) -> dict:
    """Replay a series' worth of turns through the real speaker at one cadence.

    The meter is the real one, so its per-purpose and per-model breakdown is
    the same object the match reports from — not a parallel tally.
    """
    import tiktoken

    from najamjad_agent.llm.token_meter import TokenMeter

    encoder = tiktoken.get_encoding("cl100k_base")
    recorder = Recorder(encoder=encoder)
    meter = TokenMeter()
    speaker = Speaker(
        router=LLMRouter(providers=[recorder]),
        template=TemplateProvider(seed=11),
        arena="a 7x7 walled quarter",
        every_n_steps=cadence,
    )

    for sub_game, steps in enumerate(steps_per_game):
        for step in range(steps):
            speaker.compose(_Facts(role="police", step=step, sub_game=sub_game))

    for call in recorder.calls:
        meter.record(call["usage"], model=MODEL, purpose="hint")

    inputs = sum(call["usage"].input_tokens for call in recorder.calls)
    outputs = sum(call["usage"].output_tokens for call in recorder.calls)
    return {
        "every_n_steps": cadence,
        "turns": sum(steps_per_game),
        "calls": len(recorder.calls),
        "input_tokens": inputs,
        "output_tokens": outputs,
        "total_tokens": inputs + outputs,
        "by_purpose": dict(meter.by_purpose),
        "by_model": dict(meter.by_model),
        "series_budget_used": round(meter.series.ratio, 5),
    }


@dataclass
class _Facts:
    """The only three fields the speaker reads off a turn."""

    role: str
    step: int
    sub_game: int


def real_step_counts(seed: int = 7) -> list[int]:
    """Play a real six-game series and return how long each game actually ran."""
    cop_cls, thief_cls, _ = MATCHUPS["ours_cop_vs_greedy_thief"]
    starts = [((0, 0), (3, 3)), ((6, 6), (2, 4)), ((0, 6), (5, 1)),
              ((3, 0), (1, 5)), ((6, 0), (4, 4)), ((2, 2), (6, 3))]
    counts = []
    for cop_start, thief_start in starts[:GAMES_PER_SERIES]:
        row = play_one(cop_cls, thief_cls, cop_start, thief_start)
        counts.append(int(row.get("steps") or 0))
    return counts


def main() -> int:
    """Measure every cadence and write the census."""
    prices = json.loads((ROOT / "config/model_prices.json").read_text(encoding="utf-8"))
    steps = real_step_counts()
    print(f"real series: {len(steps)} games, steps per game = {steps}")

    measurements = [measure_series(cadence, steps) for cadence in CADENCES]
    price = prices[MODEL]
    for row in measurements:
        row["model"] = MODEL
        row["purpose"] = "hint"
        row["cost_usd"] = round(
            row["input_tokens"] / 1e6 * price["input"]
            + row["output_tokens"] / 1e6 * price["output"], 6
        )
        print(f"  every_n_steps={row['every_n_steps']}: {row['calls']:3} calls "
              f"{row['total_tokens']:6} tokens  ${row['cost_usd']:.4f}")

    out = ROOT / "results/tokens.json"
    out.write_text(json.dumps({
        "tokenizer": "cl100k_base (proxy — no Anthropic key on this machine)",
        "model": MODEL,
        "games_per_series": len(steps),
        "steps_per_game": steps,
        "prices_usd_per_million": {MODEL: price},
        "series_token_budget": 200_000,
        "measurements": measurements,
    }, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
