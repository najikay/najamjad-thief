"""Our group identity, in the shape the opponent's declaration needs.

Identity travels beside the signed terms in the handshake and is deliberately
**not** covered by the signature: it differs per group, so it is not something
both peers can match on. What it *is* is load-bearing for the other side —
each peer builds the whole-series declaration from both identities, and only we
know our own hardware.

Every key here is required by the reference's `group_block()`, which indexes
them directly. Omitting one does not degrade their report; it raises `KeyError`
in their process *after* the games have been played, losing the series to a
missing dictionary key. We shipped `group_id`/`agent_name` at first and did
exactly that in a rehearsal.
"""

from __future__ import annotations

from typing import Any

from ..shared.sysinfo import collect_spec, git_commit


def identity_from_config(manager: Any) -> dict[str, Any]:
    """The static per-group block we hand the opponent during the handshake.

    Per *group*, not per role: roles alternate across mini-games, so an identity
    tied to a role would change halfway through a series.

    Carries the counted-match declaration, which rules 37-38 make mandatory and
    binding: each team states how many counted matches it has already played,
    the diversity weighting is computed from the two declarations, and a false
    one found at project review disqualifies the declaring team. It is read from
    the tracker rather than from config so that it cannot be typed — the figure
    changes after every counted match, and a hand-maintained counter across ten
    matches under time pressure is how an honest team declares a wrong number.
    """
    from .counted_games import tracker_for

    return {
        **tracker_for(manager).declaration(),
        "group_id": str(manager.get("game.group_id", "najamjad")),
        "group_name": str(manager.get("game.group_name", "NajAmjad")),
        "members": list(manager.get("game.members", []) or []),
        "repos": dict(manager.get("game.repos", {}) or {}),
        "mcp_servers": served_endpoints(manager),
        "llm_model": str(manager.get("llm.model", "") or "cli-default"),
        # The commit we are playing this match with (rule 53). We sealed it into
        # every step-0 record and wrote it into every result artifact, and never
        # once put it in the handshake — so a peer validating the *negotiated
        # identity* found ours empty and refused to file the series.
        #
        # uoh-ay26 blocked their own submission over exactly this on 2026-08-08:
        # "the opponent negotiated without providing a valid 40-character Git
        # commit SHA". They were right. It cost them a report and us nothing
        # visible, which is the worst shape a defect can have.
        #
        # Both spellings, deliberately. `git_commit_hash` is what the
        # reference-derived peers send us and therefore what their readers look
        # for; `github_commit` is the name the book gives the same value in the
        # result email (rule 53). Two keys carrying one value cost a few bytes
        # and remove a whole class of "which name did they use" failure.
        "git_commit_hash": git_commit(),
        "github_commit": git_commit(),
        "spec": spec_for_declaration(),
    }


def served_endpoints(manager: Any) -> dict[str, str]:
    """Both role keys pointing at the endpoint this process actually serves.

    We used to publish `config`'s `[game.mcp_servers]` verbatim — two permanent
    hostnames, one per role. But **one match is one process on one port**, so in
    the mini-games where we hold the other role we were naming a hostname with
    nothing behind it. An opponent that honours the label — which includes every
    fork of this repo — dials it and gets a 502 for half the series, and reads
    the silence as our bug, correctly.

    The reference has always done it this way: its shipped configs point both
    role keys at the same port. Declaring where we *are* is the honest answer;
    declaring where a differently-configured sibling would be is not.

    `tunnel.hostname` when a tunnel fronts us, the local port otherwise, so a
    `--no-tunnel` rehearsal advertises something a peer on the same host can
    actually reach.

    Note this is **only what we advertise**. `net/peer_endpoint.is_our_own` must
    keep recognising *both* hostnames as ours, or a peer running our own config
    could still send us to the sibling address — which is the defect this pairs
    with, not a duplicate of it.
    """
    hostname = str(manager.get("tunnel.hostname", "") or "").strip()
    port = int(manager.get("network.my_port", 8802))
    url = f"https://{hostname}/mcp" if hostname else f"http://127.0.0.1:{port}/mcp"
    if not str(manager.get("game.opening_role", "") or "").strip():
        return {"cop": url, "thief": url}
    # Split across two processes (book Appendix ה rule 1), so both doors are
    # genuinely live and the per-role declaration is true again — this is the
    # one condition under which naming an address we do not serve ourselves is
    # honest, because our sibling serves it. Anything the config leaves blank
    # still falls back to the door we personally answer.
    declared = dict(manager.get("game.mcp_servers", {}) or {})
    return {
        "cop": str(declared.get("cop") or url),
        "thief": str(declared.get("thief") or url),
    }


def spec_for_declaration() -> dict[str, Any]:
    """Our hardware, under the names the opponent's declaration reads.

    `collect_spec()` uses our own field names; the reference's `hardware_spec()`
    reads `cpu_model`, `cpu_freq_mhz`, `cpu_cores`, `ram_gb`, `gpu_type` and
    `vram_gb`. Both sets are provided rather than one translated into the other,
    because our artifacts consume ours and theirs consumes theirs, and a missing
    key on either side is a crash rather than a blank field.
    """
    spec = collect_spec()
    return {
        **spec,
        "cpu_model": spec.get("cpu_type"),
        "cpu_freq_mhz": spec.get("cpu_freq_mhz"),
        "gpu_model": spec.get("gpu_type"),
        "vram_gb": spec.get("vram_gb"),
    }
