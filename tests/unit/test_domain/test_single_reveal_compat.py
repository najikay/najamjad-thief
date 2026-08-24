"""NAJAMJAD_SINGLE_REVEAL=1: one reveal copy, full-window wait (compat dial).

The three copies exist because a relay once lost accepted reveals; they also
fail the audit of any peer whose reader neither drains between windows nor
filters by sub_game — our duplicates become their "wrong sub_game, every
step" (bestteam, 2026-08-24). One dial, set per launch script, so both
classes of peer get the wire they can survive. Default off.
"""

from __future__ import annotations

from najamjad_agent.domain import match_audit


def _run(monkeypatch, single: bool):
    if single:
        monkeypatch.setenv("NAJAMJAD_SINGLE_REVEAL", "1")
    else:
        monkeypatch.delenv("NAJAMJAD_SINGLE_REVEAL", raising=False)
    sends: list[int] = []
    waits: list[float] = []
    monkeypatch.setattr(match_audit, "send_reveal", lambda *a, **k: sends.append(1))

    def fake_receive(transport, timeout, sub_game=None):
        waits.append(timeout)
        return match_audit.AuditReport(passed=True)

    monkeypatch.setattr(match_audit, "receive_reveal", fake_receive)
    report = match_audit.exchange_audit(ledger=None, transport=None, timeout=90.0)
    return sends, waits, report


def test_single_reveal_sends_one_copy_and_waits_the_full_window(monkeypatch) -> None:
    sends, waits, report = _run(monkeypatch, single=True)
    assert len(sends) == 1, "compat mode must send exactly one copy"
    assert waits == [90.0], "and spend the whole window listening for theirs"
    assert not report.disputed


def test_default_still_sends_three_copies(monkeypatch) -> None:
    sends, waits, _ = _run(monkeypatch, single=False)
    assert len(sends) == 3, "the resend guarantee stays the default"
    assert waits == [30.0, 30.0, 30.0], "thirds of the window apart, as documented"
