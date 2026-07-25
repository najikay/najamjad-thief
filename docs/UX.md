# Dashboard UX — the ten heuristics, and what each one changed

**Version 1.00 · 2026-07-25**

This is not a compliance checklist written after the fact. Every entry below
names a concrete decision in `src/najamjad_agent/ui/`, and most of them exist
because the Assignment 6 dashboard got the same thing wrong.

The constraint that shapes everything: **book rules 8-9 forbid showing the
objective board.** A dashboard that displays the opponent's true position is an
illegal information advantage and a disqualification. So the interesting design
question is not "how do we show the game" but "how do we make a *partially
observed* game legible" — and the answer is that uncertainty has to be visible
rather than hidden behind a confident-looking marker.

---

## 1. Visibility of system status

The A6 dashboard had one status: whatever it had last polled. When the agent
was waiting on the opponent, retrying an LLM call, or failing to send an email,
the screen looked identical.

* **Turn banner** — green `YOUR TURN` only during `COMPUTING_MOVE`; grey
  `LOCKED` in every other phase, with the phase name spelled out
  (`LOCKED — awaiting_reveal`), so "stuck" and "waiting on the peer" are
  distinguishable at a glance.
* **Connection badge** — `live` / `connecting…` / `reconnecting in Ns…`. The
  page never shows numbers without saying whether they are current.
* **Incident feed** — retries, timeouts, provider fallbacks and degradations
  scroll live. There is no "check the logs" state.
* **Match report panel** — reconciliation status, mutual agreement, and email
  delivery with its message id. See heuristic 9.

## 2. Match between system and the real world

Panels use the book's own vocabulary — *commit*, *reveal*, *audit*, *barrier*,
*scent*, *mini-game* — not internal class names. The FSM phase is shown as the
lowercase book phase (`awaiting_reveal`), which is also what appears in the
event stream and the JSON report, so what is on screen can be grepped for in
the artifacts without translation.

## 3. User control and freedom

Controls are **server-driven**: their enabled state comes from the FSM through
the SDK, not from an optimistic timer in the browser. A click cannot race the
state machine because the button is not offered in a phase where the action is
illegal. Nothing on the dashboard can affect the *game* — moves come from the
strategy layer (book rule 25) — so there is no destructive action to undo.

## 4. Consistency and standards

One renderer per panel, one CSS variable palette, one frame contract. Every
outbound WebSocket frame is validated against a pydantic model in
`ui/frames.py`; an unknown frame type raises rather than silently rendering
nothing. In A6 a renamed field failed silently in whichever JavaScript branch
happened to read it — this is the fix.

## 5. Error prevention

The strongest measure here is structural rather than visual: `assert_local_truth`
runs on every view model and every frame, and refuses any payload carrying
`opponent_position`, `their_position`, `true_position` or `nonce` at any depth.
The dashboard *cannot* leak the opponent's position, because the read model has
no field for it — a meta-test (`tests/unit/test_ui/test_boundaries.py`) enforces
that `ui/*` may import only the `sdk` package, so no panel can reach past the
boundary to a game object.

## 6. Recognition rather than recall

Nothing requires remembering a previous screen. Each dialogue line carries its
own provenance tag (`step 4 · us · claude-fable-5`), so which model said what is
readable in place instead of cross-referenced against a provider log. The
negotiation timeline shows every propose/counter/lock step — A6's negotiating
agent was invisible, which is exactly why its misbehaviour went unnoticed.

## 7. Flexibility and efficiency of use

The page pushes over one WebSocket and never polls. A viewer who joins
mid-match gets a full snapshot on connect (`/api/snapshot`) plus the recent
event tail (`/api/events`), so a late or reconnecting operator is never looking
at a blank screen waiting for the next turn.

## 8. Aesthetic and minimalist design

Panels show the decision-relevant quantity and put the rest in a tooltip: each
board cell's exact belief mass is on hover, not printed in the grid. The token
meter shows one bar and one ratio rather than a table of per-purpose counts.

## 9. Help users recognise, diagnose, and recover from errors

This is the A6 pain point that cost the most. The report was not sent when we
were not the initiating side, and **nothing on screen said so** — it was found
after the deadline.

* `report_view` distinguishes three states that A6 collapsed into one:
  *not yet reconciled* (`agreement: null`, no attention needed), *reconciled and
  sent* (message id quoted), and *reconciled but not sent* — which sets
  `needs_attention` and turns the panel red.
* `agreement` is `null` **only** while genuinely undecided. A6 filed
  `agreement: NULL` into the actual report; here a forgotten reconciliation is a
  red panel, and `bool(None)` is a `TypeError` in `reporting/agreement.py`
  rather than a plausible-looking `false`.
* A mismatch lists the specific differing fields (`result.winner: ours=cop
  theirs=thief`), not just "mismatch".

## 10. Help and documentation

Every panel heading states its own constraint where one applies — the board
panel is titled *"Board & belief — local truth only"*. Cell tooltips give the
exact belief value. The deeper explanations live in `docs/PROTOCOL.md` (what
crosses the wire and why) and `docs/SECURITY.md`.

---

## Accessibility

* **Heatmap ramp** — viridis-like (`#2a3d55 → #31688e → #21918c → #5ec962 →
  #addc30 → #fde725`), chosen because it is colour-blind safe *and* increases
  monotonically in lightness. It therefore survives grayscale printing and a
  bad projector, which a red-only ramp does not. Verify by desaturating a
  screenshot: the ordering must still read.
* **Never colour alone** — the turn banner carries the words `YOUR TURN` /
  `LOCKED`; the report panel prints `NOT SENT`; own position is marked with a
  `U` glyph as well as an outline; the belief peak has a white inset border, a
  shape cue independent of hue.
* **Contrast** — body text `#dbe3ec` on `#0f1216` is roughly 14:1, well past
  WCAG AA. Muted secondary text stays above 4.5:1.
* **Structure and keyboard** — semantic `header`/`main`/`section` with real
  `h1`/`h2` headings, so screen-reader landmark navigation works; every control
  is a native focusable element in DOM order, with no keyboard traps (the page
  adds no custom `tabindex`).
* **Responsive** — the grid reflows via `auto-fit`/`minmax(320px, 1fr)`, so the
  layout survives a projector at 1024px without horizontal scrolling.

## Screenshots

Captured to `assets/` per guidelines §10: the live belief heatmap mid-game, the
turn banner in both states, the negotiation timeline, the token meter at its 70%
warning, the report panel in its red *reconciled-but-not-sent* state, and the
Replay viewer's "Verified OK" banner.
