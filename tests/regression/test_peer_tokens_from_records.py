"""Their token spend lives on the move records, not on step 0 (T-2712).

We read peer tokens only from step-0 declarations, as a gap between two mini-games'
running totals. MOAAMOHA publish nothing about tokens at step 0 — their meter is on
the move records — so all six counted mini-games filed their spend as `0` while the
figures sat in our own log, on records we had already re-hashed at the audit.

Recovered from the 2026-08-17 counted logs afterwards: 6,350 in g01 (35 steps at
187) and 20,719 in g02 (35 at ~590), 73,517 for the series. Self-consistent three
ways in their data — `sum(tokens_step)`, `sum(tokens)` and `max(tokens_total)` all
agree — which is what makes any one of them safe to read.

Excluded from `mutual_agreement`, so this never voided anything. It is a factual
error in a binding report, the same class as the per-window commit.
"""

from najamjad_agent.reporting.peer_declaration import peer_facts


def records(rows: list[dict]) -> list[dict]:
    """Their revealed records, in the envelope shape the audit hands us."""
    return [{"payload": row} for row in rows]


def test_a_peer_that_meters_per_step_is_read_from_its_move_records() -> None:
    """MOAAMOHA's shape: no tokens at step 0, a per-step cost on every move."""
    games = [{
        "sub_game": 1,
        "their_records": records([
            {"type": "system_spec", "step": 0, "github_commit": "a" * 40},
            *({"step": n, "tokens_step": 187, "tokens_total": 187 * n} for n in range(1, 36)),
        ]),
    }]

    assert peer_facts(games)[1]["tokens"] == 187 * 35
    assert peer_facts(games)[1]["commit"] == "a" * 40


def test_a_meter_that_resets_each_mini_game_is_not_summed_across_them() -> None:
    """Two games at the same cost must report that cost twice, not once."""
    games = [
        {"sub_game": n, "their_records": records([
            {"type": "system_spec", "step": 0, "github_commit": "b" * 40},
            *({"step": s, "tokens_step": 100, "tokens_total": 100 * s} for s in range(1, 11)),
        ])}
        for n in (1, 2)
    ]

    facts = peer_facts(games)
    assert facts[1]["tokens"] == 1000
    assert facts[2]["tokens"] == 1000


def test_a_series_long_running_total_is_read_as_a_gap() -> None:
    """A peer whose meter never resets: the cost is the growth, not the height."""
    games = [
        {"sub_game": 1, "their_records": records([
            {"type": "system_spec", "step": 0}, {"step": 1, "tokens_total": 500}])},
        {"sub_game": 2, "their_records": records([
            {"type": "system_spec", "step": 0}, {"step": 1, "tokens_total": 900}])},
    ]

    facts = peer_facts(games)
    assert facts[1]["tokens"] == 500
    assert facts[2]["tokens"] == 400


def test_the_old_step_zero_path_still_works_for_peers_who_use_it() -> None:
    """A peer declaring a running total at step 0 must keep being understood."""
    games = [
        {"sub_game": n, "their_records": records([
            {"type": "system_spec", "step": 0, "tokens_total": total, "github_commit": "c" * 40}])}
        for n, total in ((1, 1000), (2, 2500))
    ]

    assert peer_facts(games)[1]["tokens"] == 1500


def test_a_peer_that_publishes_nothing_reports_zero_rather_than_guessing() -> None:
    """An honest zero. Tokens are outside the signature precisely for this."""
    games = [{"sub_game": 1, "their_records": records([{"type": "system_spec", "step": 0}])}]

    assert peer_facts(games)[1]["tokens"] == 0


def test_a_backwards_meter_never_produces_a_negative_cost() -> None:
    """Subtracting a reset from a series total would be worse than a gap."""
    games = [
        {"sub_game": 1, "their_records": records([{"step": 1, "tokens_total": 5000}])},
        {"sub_game": 2, "their_records": records([{"step": 1, "tokens_total": 40}])},
    ]

    facts = peer_facts(games)
    assert facts[1]["tokens"] == 5000
    assert facts[2]["tokens"] == 40
    assert all(row["tokens"] >= 0 for row in facts.values())


def test_junk_in_a_token_field_is_stepped_over_not_raised() -> None:
    """Filing is the step rule 35 scores as not having played; it may not throw."""
    games = [{"sub_game": 1, "their_records": records([
        {"step": 1, "tokens_step": "many"}, {"step": 2, "tokens_step": 60, "tokens_total": 60}])}]

    assert peer_facts(games)[1]["tokens"] == 60
