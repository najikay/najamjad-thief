"""Everything one run may change about the configuration it just loaded.

Split out of `bootstrap` when that file reached its 150-line cap adding the
second emission dial. Coherent on its own: `bootstrap` decides *which* pieces
get built, this module decides *what settings they are built from* — and every
override here shares one property worth stating in a single place.

**None of them touch a tracked file.** Each is applied to the in-memory manager
for this process only, so a run stays reproducible from its command line and the
committed config keeps saying what we actually ship. That is not a style
preference: `--group-id` exists because two agents from one team both declaring
`najamjad` collapse every per-group dict in the report to a single key, and the
alternative was editing the shipped config and loosening the test that pins our
real identity — which is how a wrong group id reaches a submission.

Ordering is deliberate. The opponent card is applied **last and narrowest**: it
may only reach `network.opponent_*`, so a card can never move a signed game
term (see `shared/opponents.py`).
"""

from typing import Any

from ..domain.emission import emission_overlay
from ..shared.config import ConfigManager


def guard_counted_strength(manager: ConfigManager) -> None:
    """Refuse to build an agent for a counted match at less than full strength.

    `shared/strength.guard_counted` was written, documented, tested and then
    never called from anywhere, so the refusal it exists to perform did not
    happen. Meanwhile `scripts/match_day.py warmup` writes
    `level = "sandbagged"` into a file nothing read — the agent played full
    strength regardless, and the guard meant to catch the reverse mistake,
    arming a warm-up and forgetting to re-arm before the counted series, never
    ran once.

    Called from the loader rather than the CLI so every entry point that builds
    an agent is covered, rather than the one command someone remembered to
    edit. A counted match cannot be replayed.
    """
    from ..shared.practice import current
    from ..shared.strength import guard_counted

    guard_counted(manager.get("strength.level", "full"), counted=not current().enabled)


def apply_overrides(
    manager: ConfigManager,
    opponent: str | None = None,
    group_id: str | None = None,
    quiet: bool = False,
    scent: str = "",
    hints: bool | None = None,
    opens: str = "",
) -> None:
    """Layer this run's flags onto the loaded config, in dependency order."""
    if opens:
        # Our role in mini-game 1, which splits the six windows across our two
        # processes. A flag rather than an opponent-card key on purpose: the
        # card mapping may only reach `network.opponent_*`, and widening it to
        # `game.*` would give a per-opponent file a route into game settings.
        # It is also the safer ergonomics — the value must be *identical* in
        # both terminals, and typing it in each is harder to get silently wrong
        # than keeping two cards in agreement. `series.role_split` echoes it at
        # startup precisely so the two can be compared before dialling.
        manager.overlay({"game": {"opening_role": opens}})
    if group_id:
        # Practice-only. The committed config carries our real group id and a
        # test pins it; this is how a second agent from the same team plays
        # without either of those becoming negotiable.
        manager.overlay({"game": {"group_id": group_id}})
    _apply_emission(manager, quiet, scent, hints)
    if opponent:
        from ..shared.opponents import as_overlay, load_opponent

        manager.overlay(as_overlay(load_opponent(opponent)))


def _apply_emission(manager: ConfigManager, quiet: bool, scent: str, hints: bool | None) -> None:
    """How much of our own evidence goes on the wire, for this run only.

    Emitting less is a tactical choice the rules allow — the scent field is ours
    to publish or not — and `hint = false` skips the vendor call outright, so a
    silent run is genuinely free: zero tokens, no provider latency, and the same
    move either way, since moves have always been plain Python (rule 25).

    The shipped default stays `talk`, which is what a counted match against an
    unknown team should do. An empty overlay is not applied at all, so a bare
    command leaves `[emission]` in charge.
    """
    overlay: dict[str, Any] = emission_overlay(quiet, scent, hints)
    if overlay:
        manager.overlay(overlay)
