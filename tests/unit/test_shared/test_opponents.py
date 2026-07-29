"""Opponent cards (T-2432).

Two settings decide who we play — their MCP endpoint and their `group_id` —
and both were hand-edited into a tracked config before every match. That
overwrote the previous opponent's settings and dirtied the repo to prepare for
a game.

`opponent_group_id` is the one people get wrong: it must equal what their
handshake declares, or the filer's rename never fires and the emitted result is
keyed by a placeholder instead of their name. A card makes it reviewable the day
before rather than discoverable at the handshake.
"""

import pytest

from najamjad_agent.shared.config import ConfigManager
from najamjad_agent.shared.opponents import (
    OpponentError,
    as_overlay,
    available,
    load_opponent,
)

CARD = 'url = "https://rival.invalid/mcp"\ngroup_id = "rival"\nname = "Rival"\n'


def cards(tmp_path, **files):
    root = tmp_path / "opponents"
    root.mkdir()
    for name, body in files.items():
        (root / f"{name}.toml").write_text(body, encoding="utf-8")
    return root


def test_a_card_supplies_both_facts_a_match_needs(tmp_path):
    card = load_opponent("rival", cards(tmp_path, rival=CARD))

    assert card["url"] == "https://rival.invalid/mcp"
    assert card["group_id"] == "rival"


def test_a_missing_card_names_the_ones_that_exist(tmp_path):
    """The reader is usually minutes from a match and has mistyped a name."""
    root = cards(tmp_path, rival=CARD, other=CARD)

    with pytest.raises(OpponentError, match="other, rival"):
        load_opponent("rivel", root)


def test_a_card_without_a_group_id_is_refused(tmp_path):
    """Half a card is worse than none: the URL would connect and the report
    would be keyed by a placeholder."""
    root = cards(tmp_path, half='url = "https://rival.invalid/mcp"\n')

    with pytest.raises(OpponentError, match="group_id"):
        load_opponent("half", root)


def test_a_blank_value_counts_as_missing(tmp_path):
    """The template ships with empty strings, so an uncopied template must
    fail here rather than at the handshake."""
    root = cards(tmp_path, blank='url = ""\ngroup_id = ""\n')

    with pytest.raises(OpponentError, match="url"):
        load_opponent("blank", root)


def test_the_template_is_not_offered_as_an_opponent(tmp_path):
    root = cards(tmp_path, rival=CARD)
    (root / "_template.toml").write_text(CARD, encoding="utf-8")

    assert available(root) == ["rival"]


def test_no_cards_is_an_empty_list_not_an_error(tmp_path):
    assert available(tmp_path / "absent") == []


def test_the_overlay_touches_only_the_opponent_settings():
    """The guarantee that matters: a card cannot reach a signed game term.

    Terms are agreed in `config/game.json` and hashed; a per-opponent override
    of one would be a rule breach that looked like convenience.
    """
    overlay = as_overlay({"url": "https://rival.invalid/mcp", "group_id": "rival"})

    assert set(overlay) == {"network"}
    assert set(overlay["network"]) == {"opponent_url", "opponent_group_id"}


def test_the_overlay_reaches_the_loaded_config(tmp_path):
    """End to end: card in, config out."""
    role = tmp_path / "police"
    role.mkdir()
    (role / "game.toml").write_text(
        'version = "1.00"\n[network]\nmy_port = 8802\nopponent_url = ""\n', encoding="utf-8"
    )
    (tmp_path / "game.json").write_text("{}", encoding="utf-8")
    manager = ConfigManager.load(role, shared_config=tmp_path / "game.json")

    manager.overlay(as_overlay(load_opponent("rival", cards(tmp_path, rival=CARD))))

    assert manager.get("network.opponent_url") == "https://rival.invalid/mcp"
    assert manager.get("network.opponent_group_id") == "rival"
    assert manager.get("network.my_port") == 8802, "the merge must not drop siblings"
