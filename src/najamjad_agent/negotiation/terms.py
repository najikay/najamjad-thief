"""The signed terms, in the shape every other team will send us.

The reference implementation signs a **flat dictionary of exactly these keys**
and refuses to play unless the opponent's dictionary is equal to its own — not
equivalent, *equal*. Our own `config/game.json` is grouped into sections
(`board_and_agents`, `pheromones`, …) because that is easier to read, and none
of those section names appear here.

So this module is the translation, and it is interop-critical: a key spelled
differently, an int where they send a float, or one extra field is a refusal to
play. It is deliberately a flat literal rather than anything clever, so that
comparing it against `reference-sim/src/police_thief/peer/sealing.py` is a
matter of reading two lists side by side.

Appendix F floors are checked against *our* configuration before translating,
because after translation the keys no longer carry the names the rule text uses.
"""

from __future__ import annotations

from typing import Any

from .contract import validate_terms

#: Exactly the keys the reference signs, in its order. Order does not affect the
#: signature — `canonical_json` sorts — but keeping it identical makes the two
#: files diffable by eye.
REFERENCE_TERM_KEYS = (
    "board_size",
    "smell_grid_size",
    "decay_per_step",
    "emit_intensity",
    "min_center_intensity",
    "max_steps",
    "barriers_max",
    "setting",
    "hint_max_words",
    "axis_origin_corner",
    "axis_start_index",
    "thief_start",
    "cop_start",
    "num_games",
)


def our_terms(manager: Any) -> dict[str, Any]:
    """Our configuration, as the Appendix F terms we would sign locally."""
    return {
        "grid_size": int(manager.get("board_and_agents.grid_size", 7)),
        "max_barriers": int(manager.get("movement_and_barriers.max_barriers", 14)),
        "max_moves": int(manager.get("movement_and_barriers.max_moves", 35)),
        "survival_threshold": int(manager.get("movement_and_barriers.survival_threshold", 35)),
        "num_agents": int(manager.get("board_and_agents.num_agents", 2)),
    }


def terms_from_config(manager: Any) -> dict[str, Any]:
    """The exact dictionary we sign and the opponent must match.

    Types matter as much as names. `thief_start` and `cop_start` are **lists**,
    not tuples — a tuple survives our own round-trip and arrives as a list
    through JSON, so signing a tuple would make our signature disagree with the
    bytes we actually sent.
    """
    validate_terms(our_terms(manager))
    return {
        "board_size": int(manager.get("board_and_agents.grid_size", 7)),
        "smell_grid_size": int(manager.get("pheromones.pheromone_grid_size", 5)),
        "decay_per_step": float(manager.get("pheromones.pheromone_decay", 0.10)),
        "emit_intensity": float(manager.get("pheromones.pheromone_center_intensity", 0.9)),
        "min_center_intensity": float(
            manager.get("pheromones.pheromone_min_center_intensity", 0.5)
        ),
        "max_steps": int(manager.get("movement_and_barriers.max_moves", 35)),
        "barriers_max": int(manager.get("movement_and_barriers.max_barriers", 14)),
        "setting": str(manager.get("world.map_area", "")),
        "hint_max_words": int(manager.get("world.hint_max_words", 15)),
        "axis_origin_corner": str(manager.get("board_and_agents.axis_origin_corner", "top-left")),
        "axis_start_index": int(manager.get("board_and_agents.axis_start_index", 0)),
        "thief_start": list(manager.get("board_and_agents.thief_start", [3, 3])),
        "cop_start": list(manager.get("board_and_agents.cop_start", [0, 0])),
        "num_games": int(manager.get("network_and_league.num_games", 6)),
    }


def describe_mismatch(ours: dict[str, Any], theirs: dict[str, Any]) -> str:
    """Which terms differ, for a human who has minutes to fix it.

    `verify_peer` only says the terms disagree. On match day the useful sentence
    names the key and both values, so the two teams can settle it in one message
    instead of diffing two config files under time pressure.
    """
    lines = []
    for key in sorted(set(ours) | set(theirs)):
        mine, yours = ours.get(key, "<absent>"), theirs.get(key, "<absent>")
        if mine != yours:
            lines.append(f"{key}: ours={mine!r} theirs={yours!r}")
    return "; ".join(lines) or "terms are identical"
