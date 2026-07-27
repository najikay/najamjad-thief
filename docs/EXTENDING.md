# Extending the agent

**Version 1.00 · 2026-07-27**

Four things can be replaced without editing the agent: the **brain** that picks
moves, the **LLM provider** that writes hints, the **adapter profile** that
decides how we speak to a particular opponent, and the **event subscribers** that
watch a match happen.

None of these are plugin systems bolted on afterwards. The architecture already
depends on protocols rather than classes (`domain/ports.py`, `llm/base.py`), and
book rule 3 forces every component to reach the rest of the system through the
orchestrator. Swapping an implementation is therefore a wiring change; this
document is about where the wiring is.

> **A caution about the boundary.** Everything here is loaded from *our own local
> config file*, which never crosses the network. Do not extend any of these
> mechanisms to accept a path, module name or class from the opponent — a
> `"module:Attribute"` string is an instruction to import and execute code, and
> the opponent is explicitly permitted to lie to us (rules 26–27).

---

## 1. Brain — replace the strategy

The seam is `Brain` in `domain/ports.py`:

```python
class Brain(Protocol):
    def pick_move(self, context: TurnContext) -> Move: ...
    def pick_barrier(self, context: TurnContext) -> Position | None: ...
```

A brain is constructed with `board_supplier=` — a zero-argument callable
returning the current board. It is a *supplier* rather than a board because
barriers appear mid-game, and a brain reasoning over a board it captured at
construction walks into walls it declared itself.

### A worked example

The complete example ships as **`plugins/wall_hugger.py`**, and
`tests/unit/test_sdk/test_plugins.py` loads it through the config path below and
asks it for a move — so this listing cannot drift from something that works:

```python
"""A worked example of a brain plugin (docs/EXTENDING.md §1)."""

from najamjad_agent.constants import Move
from najamjad_agent.domain.movement import apply_move, legal_moves


class WallHugger:
    """Moves to whichever reachable cell has the fewest exits."""

    def __init__(self, board_supplier=None, **_ignored):
        self._board = board_supplier

    def pick_move(self, facts):
        board = self._board() if self._board else facts.board
        legal = tuple(getattr(facts, "legal", ()) or ())
        if not legal:
            return Move.STAY
        here = getattr(facts, "own_position", (0, 0))

        def exits(move):
            return len(legal_moves(board, apply_move(board, here, move)))

        return min(legal, key=lambda move: (exits(move), move.value))

    def pick_barrier(self, facts):
        return None          # a thief has no barriers to spend
```

Two details in that listing are load-bearing rather than stylistic:

* **`**_ignored`** — the wiring may pass keyword arguments a plugin does not
  know about. A plugin that raises on an unexpected keyword breaks the moment
  the shipped brains gain a field.
* **`move.value` as a tie-break** — replay is a graded deliverable, and a brain
  that breaks ties arbitrarily makes a match unreplayable.

Point the config at it:

```toml
# config/police/game.toml  (or config/thief/game.toml)
[strategy]
thief_brain = "plugins.wall_hugger:WallHugger"
```

That is the whole procedure. `sdk/match_setup.py:brain_factory` resolves the
path through `sdk/plugins.py` **once, while wiring the match** — so a typo
fails at start-up with the offending string quoted, rather than on turn 14 of a
real game against a real opponent.

Leave the key unset and the shipped `CopBrain` / `ThiefBrain` are used.

### Before you replace a brain

`notebooks/analysis.ipynb` measures the ones that ship: the cop captures 60/60
against the greedy baseline and the thief is never caught by it. Any replacement
should be run through the same harness before it plays a counted game:

```bash
uv run python scripts/baselines.py --games 60 --seed 11
```

---

## 2. LLM provider — add a model vendor

The seam is `Provider` in `llm/base.py`:

```python
class Provider(Protocol):
    name: str
    def complete(self, system: str, user: str, max_tokens: int) -> Completion: ...
```

Three obligations, all of which the router relies on:

1. **Raise, never return empty.** `ProviderUnavailableError` for a transient
   failure (the router tries the next provider and may come back), and
   `ProviderRefusedError` for a permanent refusal of *this* request. Returning
   an empty completion instead is read as success and puts blank text on the
   wire.
2. **Report usage** in `Completion.usage`, or the token meter and the cost table
   both under-report — and reporting consumption is a rule, not a nicety
   (rule 54).
3. **Do not retry internally.** The router owns retry and fallback policy;
   a provider that retries under it turns one slow call into a missed deadline.

Register it in the chain in `sdk/bootstrap.py`, ahead of the `TemplateProvider`.
**Never remove the template floor** — it is what lets a full series be played at
zero tokens when every paid vendor is down, and `tests/integration/test_chaos_services.py`
asserts exactly that.

---

## 3. Adapter profile — speak to a specific opponent

Some teams' agents deviate from the reference in known ways. An adapter profile
records the deviation once instead of scattering `if opponent == ...` through
the transport (ADR-011).

The lesson that produced this seam is in `docs/PRD_negotiation.md`: the
reference names the MCP tool argument `message` on three tools and `payload` on
one. We sent `payload` to all four, and **every message was rejected by argument
binding before a byte of game logic ran** — in both directions. `net/mcp_server.py`
now accepts either name on all four tools, and `net/mcp_client.py` sends the
name each tool expects.

Add a profile when an opponent needs a *different shape*, not merely different
values. If the change is a value, it belongs in the negotiated terms.

---

## 4. Event subscribers — watch a match

Every meaningful thing the agent does is published to the `EventBus` as a JSON
line. A subscriber is any callable taking one dict:

```python
from najamjad_agent.shared.events import EventBus

bus = EventBus(path=Path("workspace/events.jsonl"))
bus.subscribe(lambda event: print(event["event"]))
```

This is how the dashboard receives updates — it is a subscriber and nothing
more, which is why a dashboard crash cannot affect a game (ADR-005).

Two constraints:

* **Never block.** Subscribers run on the publishing thread. Anything slow must
  hand off to its own queue; a subscriber that waits on the network holds up a
  turn.
* **Never raise.** An exception in a subscriber must not propagate into the game
  loop. Observability failing is an inconvenience; a forfeited game is not.

---

## 5. What is deliberately *not* extensible

| Not a seam | Why |
|---|---|
| Commit-reveal | Interoperability rests on hashing byte-identically to every other agent. A configurable digest is a configurable way to void every game (rule 19). |
| The canonical JSON encoding | Same reason: both peers must hash the same bytes. |
| The audit verdict | A tampered log must read `TAMPERED` for everyone. |
| Rate-limit ceilings | Bounded by Appendix F and validated at load. Raising them is a rule breach, not a tuning decision. |
| The Gmail scope | Rule 30 fixes it at `gmail.send`. |

The tests in `tests/unit/test_net/test_architecture_rules.py` enforce several of
these structurally, so an attempt to add a seam here fails the build rather than
the match.
