"""What we declare alongside the signed terms, so a mismatch refuses early.

The signature covers the *terms*. It says nothing about which pheromone maths
either side runs, which sub-game we each think we are playing, or which role we
each hold — and every one of those can differ while both peers agree perfectly
on the contract hash and play a full series that only disagrees at audit time.

The league's guard for that is a set of declarations riding beside the terms.
Both sides declaring the same model is what matters; **undeclared differing
physics is the worst case**, because it plays cleanly and then the two audits
disagree with nothing to point at. Declaring is cheap and refuses at the
handshake instead.

The two model digests are doc hashes from the interop kit
(`github.com/Imreec/copthief-league-protocol`, `vectors/locked_model.json`):
SHA-256 over the registered model document, serialised
`sort_keys=True, ensure_ascii=False, separators=(",", ":")`. We reproduced both
from a fresh clone rather than copying an opponent's paste, and
`test_declarations.py` pins the values against our own scent implementation, so
a change to our maths that silently stops matching `subtractive_chebyshev_v1`
fails a test rather than a match.
"""

from __future__ import annotations

from typing import Any

from ..constants import Role
from .contract import derive_game_ids

#: `scent_model:subtractive_chebyshev_v1` — the reference implementation's own
#: model and the kit's CORE vector. Our `ScentModel.REFERENCE` reproduces its
#: published example field and its after-one-decay snapshot exactly.
SCENT_MODEL_SHA256 = "81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4"
#: `info_mode:belief` — we read our own state, the rival's scent and hints, and
#: never the rival's position. Structural rather than honour-based under the
#: reference wire shape, since their position never crosses the wire at all.
INFO_MODE_SHA256 = "020947daeeb3f73494af9b04201326791742c7184085456e3517d21981ee1202"
#: `wire_shape:reference-v3` — four tools, ONE message per half-turn, the smell
#: grid on the wire, and the move revealed at audit. That is what we implement,
#: and it is worth declaring because the kit registers a second shape that is
#: incompatible with it in ways no handshake would otherwise catch:
#: `bookletter-v3` sends TWO messages per half-turn, reveals per half-turn, and
#: keeps the grid off the wire entirely. Two peers on different shapes agree on
#: every term, lock cleanly, and then wait for messages the other will never
#: send.
#:
#: We were the only side of a pairing not declaring it — anrbj666 sent
#: `wire_shape_sha256` and we logged it as an unknown field. Omission never
#: refuses, so nothing was breaking; we were simply declining a guard that was
#: being offered to us.
WIRE_SHAPE_SHA256 = "229ae6487a418c3fcb6da9be404de2f2533c288ebc228811bff6dedc4164d6f7"


def negotiate_declarations(
    manager: Any, terms: dict[str, Any], role: str, sub_game: int
) -> dict[str, Any]:
    """The non-signed guards we send beside our signed terms.

    Input: the config manager, the terms we are signing, the role we hold this
        mini-game, and which mini-game it is.
    Output: a dict merged into the negotiate payload beside `terms`, `nonce`,
        `signature` and `identity`.
    Setup: `network.opponent_group_id`, which the opponent card supplies.

    `game_uid` is derived from the terms and the two group ids, exactly as
    `derive_game_ids` computes it after the exchange. It is worth declaring
    *before* play because the uid never crosses the wire during a series: two
    teams can play six sub-games under two different uids and discover it only
    when their reports fail to join. Declared, the whole class refuses at the
    handshake instead.

    Omission is not a refusal on either side, so a peer that sends none of this
    is played normally — we lose the guard, not the game.
    """
    their_group = str(manager.get("network.opponent_group_id", "") or "").strip()
    our_group = str(manager.get("game.group_id", "najamjad"))
    declarations: dict[str, Any] = {
        "sub_game_number": int(sub_game),
        "role": _role_value(role),
        "info_mode_sha256": INFO_MODE_SHA256,
        "wire_shape_sha256": WIRE_SHAPE_SHA256,
    }
    # Declare the emission model only when we are actually emitting. Under a
    # mutually-silent arrangement — both sides sending `{}`, which anrbj666
    # proposed on 2026-08-19 and the kit records as a convention — a declared
    # model is a claim about a field nobody is putting on the wire, and their
    # spec refuses on a declared *mismatch* while omission never refuses. So
    # declaring here would be both untrue and the thing most likely to refuse
    # an honest peer. Silence is symmetric or it is nothing (see the terms
    # document, section 4), and this is the handshake half of that rule.
    if str(manager.get("emission.scent", "full")).strip().lower() != "none":
        declarations["scent_model_sha256"] = SCENT_MODEL_SHA256
    # Without their group id the uid we would compute is keyed on a placeholder
    # and would refuse an honest peer. Better to send nothing than a wrong
    # value: their spec refuses on a declared *mismatch*, never on absence.
    if their_group and their_group != "them":
        _, game_uid = derive_game_ids(dict(terms), our_group, their_group)
        declarations["game_uid"] = game_uid
    return declarations


def _role_value(role: str) -> str:
    """Normalise our role to the two strings the wire uses.

    `Role.COP` is spelled `"police"` on the wire, and a role we cannot read is
    omitted rather than guessed: declaring the wrong one is a refusal, and both
    peers taking the same role is precisely what this field exists to catch.
    """
    text = str(role).strip().lower()
    if text in (Role.COP.value, Role.THIEF.value):
        return text
    return {"cop": Role.COP.value, "police": Role.COP.value,
            "thief": Role.THIEF.value}.get(text, "")
