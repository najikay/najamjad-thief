# Screenshots

Every image here is a capture of the real software driven by real data — the
belief heatmap comes from the Bayesian engine tracking an actual opponent
through scent, and the replay verdicts come from re-hashing actual logs. None
of it is mocked up, because a mocked-up screenshot is worth nothing as evidence
that any of it works.

| File | What it shows | How to reproduce |
|---|---|---|
| `replay-verified-ok.png` | The mandatory **Verified OK** banner (book rule 20), replaying the lecturer's own sample log — all 19 records re-hash to their stored commits. Step 9 is selected so the reconstructed board is visible. | `uv run python -m najamjad_agent.replay --log tests/goldens/artifacts/log_segal-police-team-vs-segal-thief-team_g01.json` then open `/replay?step=9` |
| `replay-tampered.png` | The **TAMPERED — GAME VOID (rule 19)** banner on a deliberately corrupted copy of that same log. Record 7's revealed move and position were edited while its commit was left intact; the viewer localises the forgery to exactly that step and shows the stored and recomputed hashes side by side. | `uv run python -m najamjad_agent.replay --log tests/goldens/artifacts/log_tampered_step7.json` then open `/replay?step=7` |
| `dashboard-live.png` | The live dashboard after a real five-turn mini-game: belief heatmap with its halo around the peak, turn banner, dialogue with per-message model provenance, the full negotiation timeline, token budget, the red *reconciled-but-not-sent* report alert, and the event feed. | `uv run python scripts/demo_dashboard.py --port 8200` then open `/` |

## One artifact worth explaining

In `dashboard-live.png` the connection badge reads **connecting…** rather than
**live**. That is a limitation of headless capture, not of the dashboard:
Chrome takes the screenshot at the load event, before the WebSocket handshake
completes. The socket itself is exercised by the test suite
(`tests/unit/test_ui/test_websocket.py`, `tests/integration/test_dashboard.py`)
and by connecting a real client to a running server, where the badge flips to
`live` and the server reports the viewer. Open the page in a browser and it
reads `live`.

Capturing it any other way would have meant faking the state for the camera,
which is the one thing a screenshot must never do.
