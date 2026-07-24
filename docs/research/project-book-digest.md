# Project Book Digest — "Distributed Cops-and-Robbers over a Peer-to-Peer Network"

**Source:** `.extracted/project_book.txt` — full text extraction (160 PDF pages) of the final-project
rulebook, course "Orchestration of AI Agents", Dept. of Computer Science, University of Haifa,
Dr. Yoram Reuven Segal, 2026. **Book version 3.0.0 | reference-code version 3.0.0** (PAGE 1).

> **Page references** in this digest use the extraction markers `PAGE N` (PDF page numbers).
> The book's printed page numbers are offset by 16 (printed p.1 = PAGE 17).

This digest is intended as the single source of truth for building the project without re-reading
the book. It reproduces all binding rules, all JSON/TOML structures given in the book, and the
complete Appendix F parameter tables.

---

## 0. Meta-rules: what is binding vs. illustrative (PAGES 4–5)

- **Default: nothing is binding unless explicitly stated as a binding rule.** All figures,
  examples, code snippets and scenarios are illustrations only (PAGE 4).
- **The only binding source for quantitative values is the Mandatory Parameter Table (Appendix F /
  נספח ו).** Values there are a *binding minimum*: they may be raised by mutual agreement, never
  lowered (PAGE 4).
- **Code-name convention:** every quantitative value appears in the text as a Hebrew code name in
  square brackets, e.g. `[גודל הלוח]` (board size). The actual number lives only in Appendix F
  (PAGE 4).
- **Academic freedom on contradictions (PAGE 5):** if you find a contradiction in the book you may
  choose either interpretation, provided you document in your report where the contradiction was,
  what you chose, and why. A reasoned, documented choice is not held against you. Appendix F
  remains the sole binding source for numbers.
- **Book structure:** 11 chapters + 6 appendices: A = Gmail API/OAuth guide; B = unified config
  file; C = GitHub submission requirements; D = public example-code repo (learning only);
  E = mapping of all binding rules (do / don't / recommended); F = mandatory parameter table
  (PAGE 5).

---

## 1. Game concept & objective

### 1.1 High-level concept (PAGES 1–2, 17–23)

- Two **symmetric autonomous agents — a cop (שוטר, "COP"/"police") and a thief (גנב, "THIEF")** —
  race/chase on a discrete grid board, **with no central server and no referee** (PAGE 2).
- **Neither agent ever sees the true world state.** Each agent symmetrically builds a *belief* about
  the opponent's position from (a) the opponent's **decaying scent map** and (b) a **verbal hint
  that may be a lie** (PAGES 2, 21–22).
- Formally modeled as a **Dec-POMDP** — an 8-tuple ⟨n, S, {Ai}, P, R, {Ωi}, O, γ⟩ (PAGE 20):
  - `n = 2` agents (cop, thief).
  - `S` — full world state: exact coordinates of both agents, static barrier layout, dynamic scent
    field. Too large for brute force.
  - `{Ai}` — actions: physical movement, construction (barrier placement — cop only), and
    communicative actions (natural-language hints that may be false).
  - `P` — transition function; since there is no central server, **both sides must agree on the
    same transition function — it is encoded in the shared config file** (PAGE 21).
  - `R` — reward, translated directly from the scoring table (Ch. 3).
  - `{Ωi}, O` — observations: scent traces + verbal statements only; hence each side keeps a
    Bayesian belief map.
  - `γ ∈ [0,1)` — discount factor.
- **Uncertainty is a resource, not just an obstacle** (PAGE 22): the *only* deception channel is
  the verbal hint. **Scent cannot be faked** — it is emitted by mere presence/movement; an agent
  cannot plant a fake trail, it can only strengthen scent where it actually is (which helps the
  opponent locate it).
- Communication runs over a **P2P network where every agent is simultaneously an MCP server and an
  MCP client**, using the **FastMCP** Python library (PAGES 2, 25–26).
- Integrity without a judge is guaranteed by a **Commit-Reveal cryptographic protocol over
  SHA-256**, with automatic disqualification for forgery (Ch. 5).

### 1.2 Board, coordinates, start positions (PAGES 34–36)

- Board: square grid of side `[גודל הלוח]` (board size), **default 7×7** (upgraded from earlier 5×5
  versions to blow up the state space). Appendix F: 7×7 is a *minimum*.
  - Note: some illustrations (Ch. 6 belief map) use 10×10 as "for example" — illustration only;
    the binding default/minimum is 7×7 (see Open Questions).
- Cells are `(row, col)` pairs. Two negotiated conventions must be *identical* on both sides:
  - `[ראשית מערכת הצירים]` — corner holding cell (0,0): default **top-left**, vertical axis grows
    downward (negotiable).
  - `[אינדקס התחלת הצירים]` — first index of each axis: default **0** (negotiable).
  - With defaults, center of 7×7 board is `[3,3]`, corner `[0,0]`.
- **Start positions are strategic, not random, and not fixed:** they are set in the pre-game
  negotiation; any legal layout agreed by both sides is allowed. The example layout — thief at
  center `[3,3]`, cop at corner `[0,0]` — is *example only*. Parameters:
  `[עמדת פתיחה – גנב]` (thief start), `[עמדת פתיחה – שוטר]` (cop start); loaded from
  `config/game.json` (PAGE 35).

### 1.3 Movement rules (PAGES 36–38)

- **Each turn an agent makes exactly one move:** step one cell in one of the 4 orthogonal
  directions (up/down/left/right = N/S/E/W) **or stay in place**. **Diagonal movement is illegal**;
  an attempted diagonal move is rejected by the opponent (who enforces physics) → technical loss
  (rules 13–14, Appendix E).
- Move set in shared config: `"move_set": ["N", "S", "E", "W", "STAY"]`.

### 1.4 Barriers — cop's asymmetric power (PAGE 37, "חוק המחסום" — binding Barrier Law)

- On a turn where the **cop forgoes movement**, it may place a **barrier** in any cell within one
  step of itself — the cell it stands on or one of the 4 orthogonally adjacent cells.
- A barrier cell becomes **impassable for both players until the end of the game.
  Barriers are irreversible.**
- **Placement can capture:** if the cop places a barrier on the cell where the thief currently
  stands — the thief is captured (rule 46). Likewise, a thief locked with no legal move at all
  (all adjacent cells blocked by barriers and/or board edges) is considered captured (rule 47).
- **Declaration duty:** the cop must truthfully announce every barrier placement and its exact
  location; no hidden barriers, no lying about barrier location (rules 15–16; violation = severe
  disqualification).
- Barrier budget: `[מכסת המחסומים]` = **max 14** (minimum status; resource-management dilemma).

### 1.5 Win/lose conditions & scoring (PAGES 38–39, Table 2; Appendix F Table 17)

| End event | Decision condition | Cop points | Thief points |
|---|---|---|---|
| Successful capture | Cop lands on thief's cell **and declares a Capture Claim** (or barrier-capture / thief immobilized) | `[ניקוד לכידה – שוטר]` = **20** | `[ניקוד לכידה – גנב]` = **5** |
| Long survival | Thief survives `[סף ההישרדות]` = **35** valid steps without capture | `[ניקוד הישרדות – שוטר]` = **5** | `[ניקוד הישרדות – גנב]` = **10** |
| Technical loss | A side crashes, exceeds time, or commits cryptographic forgery | **0** | **0** |

- Also `[תקרת הצעדים]` (max moves per mini-game) = **35** (minimum status).
- Tie rule (PAGE 87): if the **cumulative score of all mini-games between a pair of teams is
  equal**, each team receives `[ציון תיקו]` = **2** (fixed).
- **Truth duty on capture:** when the cop declares a Capture Claim, the thief is cryptographically
  obligated to answer truthfully; a lie is necessarily discovered in log audit → total systemic
  disqualification (PAGE 38, rules 21–22).
- Technical loss zeroes *both* sides' points for that game — incentivizing both to keep the
  protocol alive rather than win "on a timeout" (PAGE 38).

### 1.6 Turn structure & timing

- Turn flow is asynchronous but strictly alternating, enforced by a state machine (Ch. 8) and the
  GUI turn banner (Ch. 7): a side acts only when the opponent's MCP server signals the turn has
  passed to it; after Commit is sent, the UI locks (PAGES 71–72).
- A **full turn** = cop's move + thief's move; scent decay is applied after each full turn
  (PAGE 43).
- Timing values (Appendix F Table 19 + Appendix B TOML): `[מגבלת זמן התגובה]` response timeout per
  network request = **30 s** (negotiable); `[סף כלב השמירה]` watchdog freeze threshold = **60 s**
  (negotiable); private TOML example `turn_timeout_seconds = 180` and LLM
  `step_deadline_seconds = 30`; watchdog code example uses `timeout_sec=180` (illustrative).
- **Missed deadline = failure, not patience** (PAGE 81): every MCP request must carry a timestamp
  and expiry deadline; on expiry perform a controlled Retry or declare a technical loss and close
  the turn cleanly.

---

## 2. The P2P protocol & transport

### 2.1 Transport stack (PAGES 25–31)

- **Game communication transport: Model Context Protocol (MCP), implemented with the FastMCP
  Python library, over HTTP.** Each agent runs its **own FastMCP server** (exposing tools with
  `@mcp.tool`) and an **MCP client** that calls the opponent's server. Both peers are fully
  symmetric — no "strong"/"weak" side (PAGES 25–26).
- Minimal server example (PAGE 28, illustrative):

```python
from fastmcp import FastMCP
mcp = FastMCP("police_thief_peer")

@mcp.tool
def receive_move(signed_move: str, signature: str) -> dict:
    is_valid = verify_signature(signed_move, signature)
    return {"accepted": is_valid, "move": signed_move if is_valid else None}

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
```

- **MCP is a project requirement and may not be replaced.** A2A (Google) and ACP are "highly
  recommended to know" complementary protocols only (PAGE 26).
- **Public exposure via tunneling is mandatory for league play:** `localhost` is allowed *only*
  during early development; each team must expose its FastMCP server to the public internet via a
  tunneling tool such as **ngrok** or **Localtonet** (NAT traversal) (PAGES 29–30; rule 10).
  If a tunnel drops, the opponent cannot verify moves → deadlock risk; tunnel robustness is part of
  game robustness (PAGE 30).
- **How peers find each other:** the book defines no discovery service. Each peer's private
  `config/game.toml` holds `opponent_url` — "the only thing I know about the opponent"
  (example: `http://127.0.0.1:8801/mcp`; own server `my_port = 8802`) (PAGE 131). Teams exchange
  public tunnel URLs out-of-band during negotiation; the URLs of both MCP servers are recorded in
  the pre-game declaration JSON (PAGE 94).
- **Pre-game handshake:** both peers load a **byte-identical `config/game.json`**; the pre-game
  signature exchange **refuses to play on any mismatch** (PAGE 128, rule 11). The pheromone
  emission/decay model must be exchanged with a concrete numeric example and **locked with a
  SHA-256 hash before the series starts**; it is allowed and recommended that one team supply the
  shared scent-mechanism code to the other (PAGE 47, rule 23).
- **Environment separation (binding, PAGE 31):** cop code and thief code must run in two entirely
  separate processes with separate config directories (`config/police/` vs `config/thief/`).
  Sharing memory / live-state modules / variables between the two sides is an architecture
  violation (breaks Zero-Trust) and **disqualifies the solution even if it "works"** (rules 1–2).

### 2.2 Reporting transport (separate channel)

- **End-of-game reporting is via Gmail API with OAuth 2.0** (send-only scope) — see §8 and
  Appendix A digest below. Game moves do NOT go over email; email is only for reports to the
  lecturer.

### 2.3 Error handling, timeouts, retries (PAGES 81–83, 89–93; Appendix F Table 19)

- **Deadline Tracker:** every FastMCP request carries a timestamp + expiry; on expiry → retry or
  technical-loss message (rule 6).
- **Watchdog:** background process monitoring the main loop heartbeat; on freeze → persist state +
  controlled shutdown (rule 7).
- **Gatekeeper** (for outgoing Gmail traffic; recommended pattern, rules 28–29 make rate limiter
  and DOS detector mandatory): Quota Manager (daily cap) → Token-Bucket rate limiter
  (`tokens ← min(C, tokens + r·Δt)`, allow iff `tokens ≥ 1`) → DOS detector (locks API access on
  anomalous send patterns).
- Rate-limiter parameters (Appendix F Table 19, all minimum unless noted):
  `[בקשות לדקה]` requests/min = 30; `[בקשות מקבילות]` concurrent = 2;
  `[השהיה לאחר שגיאה]` retry backoff = 5 s; `[ניסיונות חוזרים]` max retries = 3;
  `[עומק התור]` queue depth = 100; response timeout 30 s (negotiable);
  watchdog threshold 60 s (negotiable).
- **HTTP 429 (Too Many Requests)** from Google must be honored: back off and wait for the next
  window; blind resends can get the account suspended (PAGE 95).

---

## 3. Cryptographic protocol: Commit-Reveal over SHA-256 (Ch. 5)

### 3.1 Four mandatory steps per game move (PAGES 50–52)

1. **Commit:** agent picks physical move + hint (incl. an **Intent flag**: hint is `truth` or
   `lie`), draws a fresh cryptographic **Nonce** (`secrets.token_hex(16)`), concatenates and
   hashes: `Hcommit = SHA256(State ∥ Move ∥ Intent ∥ Nonce)`. Only `Hcommit` is sent.
   - Concatenation is byte-level; **reference implementation uses canonical JSON serialization
     (sorted keys, fixed separators)** so both peers hash identical bytes. The actually signed
     record is richer than the 4 fields: it also includes the verbal hint, intent classification,
     step number, role (and `sub_game` in the code comment) (PAGE 50, 53).
2. **Acknowledge:** opponent confirms it received and is locked on the commitment; reveal happens
   only after both sides fixed their moves.
3. **Reveal:** agent sends Move + the verbal sentence. **Nonce remains hidden** at this stage (to
   prevent premature reverse engineering).
4. **Audit / Final Reveal:** only at the end of the whole game are **all Nonces revealed** for full
   mutual audit.

- Nonce purpose: uniqueness of repeated identical actions + defeat of dictionary attacks over the
  tiny move space (PAGE 50). **Nonce must be kept absolutely secret until game end** (rule 18).
- `verify()` recomputes the hash from revealed data and compares with `secrets.compare_digest`
  (PAGE 53 code).

### 3.2 Mutual audit & log integrity (PAGE 55)

- Post-game, each side submits its full log incl. all Nonces; each side re-hashes the opponent's
  (State, Move, Intent, Nonce) per step and compares with the declared commitments.
- **Any mismatch = proven tampering → heavy technical loss (total loss of that game regardless of
  board result). Cryptography, not human judgment, decides** (rule 19: iron law, score 0 for the
  forging team).
- Mutual log audit at the end of each game is mandatory and is a precondition to agreeing on the
  shared JSON result (rule 36).

### 3.3 Step-0 (צעד-אפס) & computational fairness (PAGES 55–56)

- **Before the first move**, each agent collects its machine spec: OS, CPU cores + frequency, RAM,
  GPU/VRAM presence, and the **LLM model name**. The Step-0 declaration also records **code
  version, team name, and mini-game number**. All packed as a JSON string and **cryptographically
  signed with a pre-supplied key** (PAGE 55).
- **All LLM token consumption is metered and cryptographically locked** to prevent denial of
  resources actually consumed (PAGE 56).
- **Mandatory: the Step-0 declaration must include the GitHub commit hash the code runs on for
  that game.** Code may change between games, but each game's exact commit must be recorded; the
  same id goes into the end-of-game JSON email (field `github_commit`) (PAGE 56, rule 53).
- The lecturer applies a **normalization formula** in league scoring that grants bonuses to
  algorithmically efficient solutions (good results with minimal resources). Missing the hardware
  declaration forfeits eligibility for the computational-fairness bonus (rule 24).

---

## 4. Scent / pheromone mechanics (Ch. 4)

- Bio-inspired **stigmergy**: both agents (symmetric) emit virtual pheromones by moving *or
  staying*. Each side reads only the *opponent's* scent field (PAGES 41–43).
- **Emission:** each turn a scent field of size `[גודל שדה הריח]` = **5×5** (fixed) forms around
  the agent; center intensity `[עוצמת הריח במוקד]` = **0.9** (fixed); intensity falls off
  radially (example field: 0.90 center; 0.62 orthogonal neighbors; 0.42 diagonal; edge ring
  0.20/0.14/0.04) (PAGE 44).
- **Decay:** after each full turn (cop + thief both moved) all scent decays:
  `τij(t+1) = max(0, (1−ρ)·τij(t) + Δτij)`, with `ρ` = `[קצב דעיכת הריח]` = **0.10** (fixed),
  Δτ = new emission (0.9 at the center, 0 far away), values clamped to `[0, 0.9]` (PAGE 43).
- Practical effect: a single deposit stays "readable" ~6–7 turns (half-peak around turn 7)
  (PAGE 45).
- **Tactical use / lie detection** (PAGE 46 worked example): if thief claims "I moved north" but
  north cells have τ = 0.00 while the south-east corner shows τ = 0.81 (≈ 0.9·0.9 expected fresh
  trail), the claim is exposed; lower the trust coefficient of the opponent's verbal statements and
  re-weight the belief map toward the scent mass. Symmetric for both sides.
- **Pre-series cryptographic lock (binding, PAGE 47):** both teams must exchange the full
  emission+decay model incl. a numeric example, verify identical interpretation, then lock the
  agreement via SHA-256 hash of formula + example. Sharing the actual scent-mechanism code between
  teams is allowed and recommended.

---

## 5. Strategy module & LLM usage (Ch. 6)

- **A separate strategy module is a development requirement**; it plugs into the `PeerRuntime`
  layer exactly between decoding the incoming hint and packing the outgoing Commit (PAGE 58).
- Pipeline (Fig. 7, PAGE 59): incoming hint + scent → hint decode → **belief update (Bayes rule)**
  → move policy picks a legal move → LLM composes bluff text → Commit pack.
- **Never let the LLM decide the movement** (spatial hallucination risk). LLM role is verbal only:
  bluff generation, bluff classification, behavioral profiling (PAGE 65; rule 25 — recommendation,
  no mandatory sanction, but blind reliance risks illegal moves → technical loss).
  - **Sole exception (PAGE 66):** both sides may explicitly agree in pre-game negotiation to allow
    LLM-based move tactics. Never unilaterally. Even then the local algorithm must still enforce
    move legality and reject illegal LLM suggestions.
- **Three equal, interchangeable movement-policy tracks** (PAGES 59–61): (1) pure heuristics —
  Bayesian belief map + Manhattan-distance minimization (cop) / maximization (thief); this is the
  reference default; (2) your own heuristic algorithm (belief + scent + barriers + lookahead, e.g.
  minimax/expectimax); (3) **Reinforcement learning (Q-Learning/Bellman + epsilon-greedy) is
  strictly optional** — the course did not teach RL.
- Belief map: matrix sized like the board with P(opponent at cell); updated by Bayes with a
  reliability coefficient on verbal text. Manhattan distance
  `D = |x_cop − x_target| + |y_cop − y_target|` toward `argmax b(s)` (PAGES 63–64).
- Reference implementation extension points: private TOML `[strategy]` keys `thief_class` /
  `police_class` pointing to a class (`package.module:Class`) inheriting `BrainBase`, overriding
  `_pick_move` (and for the cop also `_decide_move`, which chooses barrier placement). Empty
  section = shipped combined heuristic brain (PAGES 58, 139, Appendix F Table 22,
  `docs/STRATEGY.md` in the reference repo).

### 5.1 Bluff-text production — four LLM modes (PAGES 66–67; Appendix F Table 21)

Chosen privately per peer in `[trash_talk] provider` (NOT negotiated, not part of shared config):

| Mode | Where it runs / token cost | Rate limit | Account/setup |
|---|---|---|---|
| `template` (default, recommended) | in-process canned sentences chosen by Python — **0 tokens**, offline | none | free |
| `ollama` | local model at `localhost:11434` — 0 API tokens | none | install Ollama + pull model |
| `claude_api` | small cloud model (e.g., Haiku) via API — real consumption counted against `[אומדן טוקנים לסדרה]` | per account | Anthropic API key (paid) |
| `claude_cli` | `claude -p` via Claude Code CLI — highest cost | per subscription | Claude CLI login |

- `every_n_steps` parameter invokes the model only every N turns to cut consumption. A team can
  play the entire series at **zero tokens** (template/ollama) (PAGE 67).
- **Location-flavored hints:** `[זירת המשחק]` (map area) — an agreed real-world region (e.g.,
  "New York", "London", "Paris") whose real landmarks are woven into hints ("slipping past Times
  Square"); empty "" = generic landmarks. `[מגבלת מילים ברמז]` caps every hint at **15 words**
  (default; negotiable), applied to both template and LLM (put into the LLM system prompt). Both
  are agreed & signed conditions (PAGE 67; Appendix F Table 14).

### 5.2 Natural-language requirement (Appendix E rules 26–27)

- **Rule 26 (obligation): agents must communicate in free natural language only.**
- **Rule 27 (prohibition): a direct numeric-coordinates protocol is forbidden** — it would nullify
  the game's psychological character. (Numeric geometry is allowed only in early dev stages 2–3 of
  the recommended plan; the final game speaks free language, PAGES 102–103.)

---

## 6. GUI & Replay Viewer (Ch. 7)

- **Local Truth principle (binding):** each side's GUI shows only what that agent can know — its
  own position, the opponent's scent map it senses, hints received, and its belief heatmap. **No
  bird's-eye view showing both true positions** (rules 8–9; violation = disqualification for
  illegal information advantage) (PAGE 70).
- Live GUI (e.g., Tkinter or PyQt): dynamic **belief heatmap** (deeper red = higher probability of
  opponent presence) + **turn banner** — green "YOUR TURN" when opponent's MCP signals your turn;
  gray "LOCKED" after your Commit is transmitted; input ignored while locked (PAGES 70–72).
- **Replay Viewer is a mandatory submission requirement** (rule 20): loads the final log file
  (e.g., `logs/police_match.json`), steps forward/backward, and at every step recomputes
  SHA-256 over the revealed (Nonce, move, …) and compares with the stored commitment:
  match → green **"Verified OK"**; any mismatch → red **"TAMPERED"** banner and the game is
  **immediately void — no appeal** (PAGES 72–75).
- Screenshots of the Live GUI belief map and of the Replay app showing "Verified OK" are
  **mandatory** parts of the README/submission (PAGE 75, 96).

---

## 7. Agent architecture & reliability (Ch. 8)

- **Separation of Concerns is the master principle**; an agent is a distributed system, not a
  linear script (PAGE 77).
- **Orchestrator pattern (mandatory, rule 3):** a single Gateway component is the only entry point
  to the five subsystems: MCP Connector, Decision Module, Log Manager, Deadline Tracker, Watchdog.
  Peripheral modules never talk to each other directly (PAGES 78, 82).
- **State machine (mandatory, rules 4–5):** legal cycle
  `WAITING_FOR_OPPONENT → COMPUTING_MOVE → COMMITTING → AWAITING_REVEAL → VERIFYING →
  WAITING_FOR_OPPONENT`, plus terminal `TECHNICAL_LOSS` reachable via dashed error transitions from
  communication states (`COMPUTING_MOVE` and `AWAITING_REVEAL` in the sample transition table).
  Illegal transitions must raise immediately (PAGES 79–80).
- **Deadline Tracker** (rule 6) and **Watchdog** (rule 7) as described in §2.3. Watchdog example:
  heartbeat check, `timeout_sec=180`, then `persist_state()` + `controlled_shutdown()` (PAGE 83).
- Both sides run identical (symmetric) orchestrator + state machine structure (PAGE 84).

---

## 8. League, scoring, reporting (Ch. 9)

### 8.1 League structure (PAGES 85–87)

- No closed lab test: agents must survive against unknown opponents in a live academic league.
- **Diversity incentive:** a win against a team you have not yet played grants the full
  `[תגמול גיוון]` diversity reward = **10** (fixed).
- **One counted match per opposing team — no repeats for points.** Warm-up games (not counted) are
  allowed and encouraged. Once the counted match ends and both teams agree on the result and send
  the end-of-game message, that pairing is sealed (PAGE 86, rule 52).
- **Game-count declaration (binding):** at the start of every match, each team declares to the
  opponent how many *counted* matches it has already played; the diversity weighting is set from
  the mutual declarations. The lecturer can verify (he receives all reports); **a false
  declaration discovered at project review disqualifies the declaring team** (PAGE 86,
  rules 37–38).
- **Minimum to pass:** proper operation of at least `[מינימום משחקים למעבר]` = **2** matches
  against *different* teams (fixed). **Maximum counted matches per team:**
  `[מספר המשחקים המרבי לכל קבוצה]` = **10** (fixed) (PAGE 86; Appendix F Table 18; rule 31).
- **A match (series) against one opponent consists of `[מספר המשחקונים]` = 6 mini-games (fixed)**
  (Appendix F Table 18). Shared-config field `num_games` defaults to 1 as a single example
  mini-game; a full league series requires `[מספר המשחקונים]` mini-games (PAGE 130).
- **Computational fairness:** league scoring reduces the advantage of extreme cloud resources and
  rewards efficient algorithms on modest machines (normalization + bonuses) (PAGES 86, 56).
- **Tie rule:** equal cumulative series score → each team gets `[ציון תיקו]` = 2 (PAGE 87).
- Token budget: `[אומדן טוקנים לסדרה]` ≈ **200,000** tokens per series (negotiable status);
  actual consumption is reported in the end-of-game email (Appendix F Table 18, rule 54).

### 8.2 Gmail reporting (PAGES 87–95)

- **After every legal match, each of the two teams sends automatically, itself and separately, a
  summary email to the lecturer via Gmail API.** One-sided reporting is insufficient (PAGE 87).
- **Mandatory recipient:** `[כתובת דיווחי הסוכן]` = **`rmisegal+uoh26finalgame@gmail.com`** — the
  only allowed report destination, hardcoded as the fixed target in both agents' mail code
  (PAGE 87; Appendix F Table 20; rule 51). (General lecturer address for GitHub sharing / general
  mail: `[כתובת המרצה]` = **`rmisegal@gmail.com`**.)
- **Binding: result agreement + two separate reports.** Both teams must agree on the result; each
  sends its own report in the mandatory format. A side that does not send a report gets **no
  points for that match even if it won on the board**. Per rule 35: non-report by one team **or
  contradictory reports → match voided, score 0 for both teams**.
- **Report format is an iron rule:** structured, uniform, machine-readable **JSON sent as an email
  attachment**. Free-text (plaintext) reports are rejected → potential loss of that round's league
  points (PAGE 95; rules 33–34).
- Report content includes: team identity details, both teams' GitHub URLs (4 links total: cop+thief
  of team A and of team B), FastMCP server addresses, cryptographically signed hardware
  declarations, match timestamp, **mutual-agreement confirmations backed by SHA-256**, the
  per-mini-game `github_commit` id, and total tokens consumed (PAGES 94–95, 56).

### 8.3 The four game-lifecycle JSON files (PAGES 94–95; Appendix F Table 20)

Four example JSON files accompany the book (attachments — their full schemas are NOT reproduced in
the book text; only their roles and names are). All four share a common id `game_uid`; filenames
derive from `game_id` and mini-game number `<NN>` so files from different games never mix:

| Code name | Role / content | Filename pattern |
|---|---|---|
| `[קובץ ההצהרה]` (declaration file) | Pre-game declaration: all fixed data of the whole match (all mini-games): both teams' identity and members, cop+thief repo URLs, MCP server URLs, hardware specs, LLM model, agreed token cap, match start/end times. Cryptographically signed. | `declaration_<game_id>.json` |
| `[קובץ התצורה]` (config file) | The agreed configuration: all quantitative mini-game parameters (Appendix F), cryptographically locked, identical on both sides. | `config_<game_id>_g<NN>.json` |
| `[קובץ היומן]` (log file) | Mini-game log: step-by-step Commit-Reveal commitments, moves, hints, LLM-dialogue fields, Nonces and hashes — enables full replay verification. | `log_<game_id>_g<NN>.json` |
| `[קובץ התוצאות]` (results file) | Final results report: per-mini-game scores of each team + cumulative result, for league grading. **This is the binding report emailed to `[כתובת דיווחי הסוכן]`.** | `result_<game_id>.json` |

- Mandatory rules attached to configs (Appendix F §2, PAGE 156):
  1. Every team must define all Appendix F values in its config; both teams' values must be
     identical and **cryptographically locked**.
  2. Settings may change per new match, as long as they match the agreement with that opponent.
  3. Each match's config file gets a distinct name for easy reconstruction.
  4. **Each match's config file must be committed to the GitHub repo.**
  5. Code may change between matches; therefore **every match's email to the lecturer must include
     the GitHub commit number used in that match**.

### 8.4 Shared config `config/game.json` — full reproduced example (PAGES 128–130)

The "signed constitution", loaded byte-identical by both peers; pre-game signature exchange refuses
to play on any mismatch. Sections: `board_and_agents`, `world`, `movement_and_barriers`, `scoring`,
`pheromones`, `network_and_league`, `rate_limiter_gatekeeper`. Field names are fixed and binding;
values negotiable only in the stricter direction for "minimum" parameters.

```json
{
  "schema_version": "1.2",
  "agreed_between": ["group-a", "group-b"],
  "board_and_agents": {
    "grid_size": 7,
    "num_agents": 2,
    "thief_start": [3, 3],
    "cop_start": [0, 0],
    "axis_origin_corner": "top-left",
    "axis_start_index": 0
  },
  "world": {
    "map_area": "New York",
    "hint_max_words": 15
  },
  "movement_and_barriers": {
    "move_set": ["N", "S", "E", "W", "STAY"],
    "max_barriers": 14,
    "max_moves": 35,
    "survival_threshold": 35
  },
  "scoring": {
    "capture_cop": 20, "capture_thief": 5,
    "survival_cop": 5, "survival_thief": 10,
    "tie_score": 2, "technical_loss": 0
  },
  "pheromones": {
    "pheromone_center_intensity": 0.9,
    "pheromone_decay": 0.10,
    "pheromone_grid_size": 5
  },
  "network_and_league": {
    "response_timeout_sec": 30, "watchdog_timeout_sec": 60,
    "num_games": 1, "diversity_reward": 10,
    "min_games_to_pass": 2, "max_games_per_team": 10,
    "token_budget_per_series": 200000
  },
  "rate_limiter_gatekeeper": {
    "requests_per_minute": 30, "concurrent_requests": 2,
    "retry_backoff_sec": 5, "max_retries": 3, "queue_depth": 100
  }
}
```

Mapping: `grid_size` = `[גודל הלוח]`, `max_barriers` = `[מכסת המחסומים]`,
`scoring.capture_cop` = `[ניקוד לכידה – שוטר]`, etc. (PAGE 130).

### 8.5 Private per-peer config `config/game.toml` (PAGES 130–132)

Private, local, **not negotiated, need not match the opponent's**. When `config/game.json` exists,
its values **override (overlay)** matching keys in the TOML — the private file can never weaken a
signed condition. Reproduced skeleton (PAGE 131):

```toml
version = "1.10"

[game]
group_name = "My-Team"
group_id   = "my-team"
sub_game_number = 1
members = ["id-1001", "id-1002"]
repos = { cop = "https://github.com/you/repo", thief = "https://github.com/you/repo" }

[network]
my_port = 8802                                # MY MCP server port
opponent_url = "http://127.0.0.1:8801/mcp"    # the only thing I know about the opponent
turn_timeout_seconds = 180

# [strategy]  -- optional: point at YOUR brain subclass (else the shipped heuristic runs)
# thief_class  = "my_team.strategy:MyThiefBrain"
# police_class = "my_team.strategy:MyPoliceBrain"

# [trash_talk] -- optional: HOW the banter is produced. The MOVE is always pure Python.
# provider = "template"   # template(0 tokens, default) | ollama | claude_api | claude_cli

[llm]
model = "claude-opus-4-8[1m]"     # MY choice; the opponent may differ
step_deadline_seconds = 30        # hard cap on LLM thinking per step

[email]
recipient = "rmisegal+uoh26finalgame@gmail.com"
mode = "draft"
```

- JSON vs TOML rule of thumb (PAGE 127): anything the opponent must agree to / rely on → shared
  JSON (canonically serializable, hashable → `config_sha256`); anything private/local (port,
  opponent URL, strategy class, trash-talk mode, LLM settings, email target, team identity) → TOML
  (hand-edited, supports comments, never crosses the network, never signed).
- JSON is also used for: the four standard lifecycle files, and `rate_limits.json` (rate-limiter
  configuration) (PAGE 127).

---

## 9. Negotiation rules (consolidated)

- **The game contract is not imposed top-down: it is set by negotiation between each pair of teams
  and may differ from pair to pair.** It must be mutually agreed; it may not weaken/dilute the
  book's provisions (**"the agreed contract is a floor, not a ceiling"**). Teams may upgrade rules
  and are encouraged to legally exploit any loophole not defined by the book, for mutual benefit or
  competitive advantage, as long as everything is legal and agreed (PAGE 34, boxed rule).
- Negotiable items explicitly named: board size (upward), axis origin corner, axis start index,
  start positions (any legal agreed layout), map area (`map_area`), hint word limit, max moves /
  survival threshold / barrier quota (upward), response & watchdog timeouts, token budget per
  series, and — as the single exception — permission for LLM-based move tactics (mutual, explicit,
  documented consent only) (PAGES 34–35, 66–67; Appendix F status column).
- **Not negotiable (private per peer):** trash-talk provider mode, strategy module selection, LLM
  model, ports/URLs, email settings (Appendix F Tables 21–22 headers).
- **Fixed (non-negotiable) parameters:** number of agents (2), move set (4 orthogonal + stay),
  pheromone values (0.9 / 0.10 / 5×5), all scoring values (20/5, 5/10, tie 2, technical 0),
  mini-games per series (6), diversity reward (10), min games to pass (2), max games per team (10).
- Agreement is **recorded and locked cryptographically**: identical byte-for-byte
  `config/game.json` on both sides, SHA-256 signature exchange before play (refusal on mismatch),
  SHA-256 lock of the pheromone model + numeric example, and mutual-agreement confirmations backed
  by SHA-256 inside the emailed report (PAGES 47, 94, 128; Appendix F §2).
- The reference `PeerRuntime` models one peer's lifecycle as: **negotiation → turn loop → audit**
  (PAGE 139).
- In-game dialogue itself (hints/trash-talk) must be **free natural language** (rule 26); direct
  numeric-position protocols are forbidden (rule 27).

---

## 10. Game phases end-to-end (assembled from Chs. 2–9)

1. **Setup:** two repos (cop/thief), config dirs `config/police/` + `config/thief/`, separate
   processes; FastMCP servers up; tunnels (ngrok/Localtonet) expose public URLs; Gmail OAuth
   configured (send-only).
2. **Match agreement / negotiation:** teams exchange public MCP URLs; negotiate contract (board,
   starts, axis, map area, hint limit, timeouts, token cap, optional LLM-move exception); produce
   byte-identical `config/game.json`; exchange + verify SHA-256 signatures (refuse on mismatch);
   lock pheromone model hash; declare counted-game counts; create signed
   `declaration_<game_id>.json`.
3. **Step-0:** each side emits its signed hardware + LLM + code-version + team + mini-game-number +
   commit-hash declaration; token metering starts.
4. **Gameplay loop (per step, per state machine):** WAITING_FOR_OPPONENT → COMPUTING_MOVE (belief
   update via Bayes on scent+hint; strategy picks legal move; LLM/template composes ≤15-word hint
   with truth/lie Intent) → COMMITTING (send `Hcommit`) → opponent Acknowledge → Reveal (move +
   hint; Nonce withheld) → VERIFYING → next turn. Scent decay after each full turn. Barriers per
   Barrier Law. GUI banner enforces turn locks. Deadline Tracker/Watchdog guard the loop; failures
   → TECHNICAL_LOSS.
5. **End of mini-game:** capture (Capture Claim / barrier capture / immobilization — thief must
   answer truthfully) or survival threshold reached (35 steps) or technical loss. Repeat for the
   series (6 mini-games).
6. **Audit:** both sides exchange full logs incl. all Nonces; mutual SHA-256 re-verification;
   any mismatch → TAMPERED → match void, score 0 for cheater; Replay Viewer must show
   "Verified OK".
7. **Result agreement & reporting:** both teams agree the result; **each team separately** emails
   `result_<game_id>.json` (machine-readable JSON attachment) via Gmail API through the Gatekeeper
   (quota/token-bucket/DOS) to `rmisegal+uoh26finalgame@gmail.com`; report includes 4 GitHub links,
   commit hashes, token totals, signed declarations. Missing/contradictory report → 0 points
   (per rule 35, for both teams).
8. **League accounting by lecturer:** diversity reward, computational-fairness normalization, tie
   rule, min-2/max-10 counted matches.

---

## 11. Recommended 7-stage development plan (Ch. 10 — recommendation only)

One PRD file per stage; each stage must run end-to-end before the next (Incremental Delivery):

| Stage (PRD) | Build | Book chapter |
|---|---|---|
| 1. Base Logic | grid `[גודל הלוח]`, movement rules, `[מכסת המחסומים]`, coordinate-overlap capture; single process | Ch. 3 |
| 2. Basic MCP Infrastructure | separate processes, FastMCP servers/tools, pure numeric geometry over localhost | Ch. 2 |
| 3. "Blind" Strategy | initial decision module under full information (heuristic / LLM-mapped / optional Q-learning) | Ch. 6 |
| 4. Language + Scent | free-language reporting, pheromone emission/decay equations, LLM for inference & lies | Chs. 4, 6 |
| 5. Cloud + Tunneling | public URLs via ngrok/Localtonet, remote machines | Ch. 2 |
| 6. Security & Cryptography | Commit-Reveal, Nonce generator, Step-0 hardware declarations | Ch. 5 |
| 7. Reporting & Visualization Shell | Gmail API over OAuth 2.0, GUI completion, Replay App polish | Chs. 9, 7, App. A |

Milestone checklist per stage (PAGE 105) — each is a binary observed-end-to-end criterion (e.g.,
stage 6: "a move is committed then revealed with a valid Nonce; Step-0 verifies hardware").
Do not skip ahead to crypto/cloud before base + localhost MCP work (PAGE 106).

---

## 12. Submission requirements

### 12.1 GitHub (Ch. 9 §9.4 + Appendix C)

- **Two separate repos per team: cop repo and thief repo**, each accessible to the lecturer —
  public, or private shared explicitly with `[כתובת המרצה]` = `rmisegal@gmail.com` (rule 49).
- **Cross-link mandatory:** each repo's `README.md` links to the team's other repo. The Moodle
  submission file contains both links; the end-of-game JSON contains all four links (team A + B).
- **Mandatory repo contents (rule 50):** `README.md` (academic report), `config/` files
  (incl. each match's config), the **PRD files** used to build the code, a **PLAN** file, and
  **TODO** files.
- **Annotated Git tag** freezes the submission: `git tag -a v1.0-submission -m "..."` + push
  (rule 41, PAGE 134).
- **README academic report — mandatory contents (PAGE 97):**
  1. chosen Dec-POMDP model (states, observations, uncertainty);
  2. FastMCP orchestration dilemmas (turn management, network failures, Gatekeeper/Orchestrator);
  3. strategies implemented (heuristics / LLM strategy / optional Q-learning);
  4. learning curves **if** RL was used;
  5. **screenshots — absolute must:** Live GUI belief map + Replay App "Verified OK";
  6. link to the companion repo.
- **Secrets:** never commit `credentials.json` / `token.json` / any key — even to a private repo
  shared only with the lecturer. `.gitignore` must exclude them; a leaked secret is compromised
  forever (rotate credentials) (rules 39–40; PAGES 121–122, 135).
- Submission checklist (Table 6, PAGE 136): two accessible repos; cross-links + two links in
  submission; pushed `v1.0-submission` tag; complete README in both repos; belief-map screenshots;
  Replay "Verified OK" screenshot; **≥ 2 matches vs different teams**; end-of-match email from each
  team separately; no secrets in repo.

### 12.2 Moodle & administrative (PAGE 114, rules 43–45, 55)

- Part of the assignment is authoring the PRDs for the AI coding agent; a markdown/PRD folder must
  be in the repo; grading follows the course-intro document "Recommendations for writing and
  submitting software with AI agents".
- Submit code via GitHub shared with the lecturer; **each team member submits separately in
  Moodle**.
- **Team code name: unique 8-character identifier, no spaces** (rule 45).
- Moodle provides a Word template → fill, save as PDF, submit; **do not alter or move fields**.
- **Self-grade code quality only — not league results** (rule 55).

---

## 13. Appendix A digest — Gmail API & OAuth 2.0 (PAGES 120–125)

Five setup steps: (1) Google Cloud Console project + enable Gmail API; (2) OAuth consent screen
(External/Internal; add student emails as Test Users while app is in Testing); (3) **restrict scope
to `https://www.googleapis.com/auth/gmail.send` only** (least privilege — never request read);
(4) create OAuth Client ID of type Desktop Application, download `credentials.json`, add to
`.gitignore` **before** any push; (5) first run opens browser consent → creates `token.json`
(short-lived Access Token + long-lived Refresh Token → months of autonomous sending).
Python flow shown: `Credentials.from_authorized_user_file("token.json", SCOPES)` → `build("gmail",
"v1", ...)` → MIME text → base64url → `users().messages().send(userId="me", body={"raw": raw})`;
first run uses `InstalledAppFlow.from_client_secrets_file(...)`. Both files are secrets (Table 5).
Note: the reference repo sends the JSON report as a **Gmail draft** by default
(`mode = "draft"` in TOML; PAGE 139 "דוחJSON הנשלח כטיוטתGmail").

---

## 14. Appendix D digest — reference/example repo (PAGES 138–141)

- Public repo: `[מאגר הקוד לדוגמה]` = **https://github.com/rmisegal/Game-P2P-Cop-Chase**
  (version 3.0.0, two-way version-linked with the book).
- **Learning only — not a submission skeleton.** It demonstrates end-to-end flow with deliberately
  minimal strategy: board movement, barriers, scent + belief, full Commit-Reveal + audit, token
  meter, JSON report as Gmail draft, CLI/Tkinter GUI + Replay.
- Layout: Interface (CLI/Tkinter GUI + Replay) / `SimulationSdk` (single business entry point) /
  `PeerRuntime` (one independent peer: negotiation → turn loop → audit) / `domain` (board, scent,
  belief, state, rules, crypto, negotiation, protocol, decision "brain") / `infra` (LLM providers,
  MCP transport to opponent server, email sender) / `shared` (config manager, rate limiter,
  system-info, version). Files ≤ ~150 LOC, pytest coverage, config fully external
  (`config/police/` vs `config/thief/`).
- Run: `uv sync`; `uv run python -m police_thief peer --role police` / `--role thief`;
  replay: `uv run python -m police_thief replay --log logs/police_match.json`.
- Extension points: `[strategy] thief_class/police_class` (inherit `BrainBase`/`ThiefBrain`,
  override `_pick_move`, cop also `_decide_move` for barrier choice) — "this is where the grade
  lives"; `[trash_talk]` provider. Move is always computed in Python.
- Usage terms: may reuse/modify parts (educational license, see LICENSE); where the repo deviates
  from the book, **the book + Appendix F win**.
- `docs/RESEARCH-REPORT-Performance-Analysis.md` in the repo analyzes LLM call counts per series vs
  provider rate limits (Ollama/Gemini/ChatGPT/Claude/Grok, free vs paid) and the fallback
  mechanism; strongly recommended as a planning template.
- Tip: convert repo files to .txt and load into NotebookLM as a code chatbot.

---

## 15. Appendix E — all 55 binding rules (do / don't / recommended) (PAGES 142–150)

**Network, decentralization, local epistemology (Table 7):**
1. (Must) Run thief & cop code in two fully separate processes — else total failure, Zero-Trust broken.
2. (Forbidden) No shared memory or variables between sides — immediate disqualification (information leak).
3. (Must) Orchestrator is the single entry point to subsystems.
4. (Must) Manage game states with a proper state machine (else deadlock → technical loss).
5. (Must) Reject every illegal state transition.
6. (Must) Implement deadline tracking to prevent freeze while waiting for opponent (Timeout loss).
7. (Must) Run a watchdog for crash monitoring and controlled data rescue.
8. (Must) Live UI shows local truth only.
9. (Forbidden) Never display the full objective board in the live UI — disqualification (illegal advantage).
10. (Must) Use a tunneling tool to expose the local server to the public internet.

**Spatial mechanics & board constraints (Table 8):**
11. (Must) Config file byte-identical on both sides — else match void (symmetry broken).
12. (Must) Minimum parameters raised only by agreement; never lowered.
13. (Must) Orthogonal movement only.
14. (Forbidden) No diagonal moves — rejected by opponent, loss.
15. (Must) Openly declare every barrier placement.
16. (Forbidden) Never lie about barrier location — severe disqualification.

**Cryptography, log integrity, zero-knowledge (Table 9):**
17. (Must) Use SHA-256 Commit-Reveal.
18. (Must) Keep the Nonce absolutely secret until game end.
19. (Must) Technically void a game on any hash mismatch at audit — iron law, score 0 to the forger.
20. (Must) Build the replay/verification viewer app — submission threshold.
21. (Must) Tell only the truth on thief-capture queries.
22. (Forbidden) No false capture claims — immediate disqualification, score zero, no appeal.
23. (Must) Cryptographically lock the scent emission model before the game starts.
24. (Must) Make the cryptographic hardware declaration before the game (else no computational-fairness bonus).

**Strategy, language, public network (Table 10):**
25. (Recommendation) Don't give the LLM the movement decision; use it for text & profiling only
    (no mandatory sanction; hallucination → illegal moves → technical loss risk).
26. (Must) Communicate in free natural language only.
27. (Forbidden) No direct numeric-position protocol.
28. (Must) Token-bucket rate limiter on Gmail report sending (prevents 429 lockout).
29. (Must) DOS detector to hard-protect network resources / prevent account suspension.
30. (Must) Send-only Gmail scope.

**League fairness, admin, competition purity (Table 11):**
31. (Must) Play the minimum number of counted matches vs different teams (else no passing grade).
32. (Must) Auto-report results via Gmail API (no report → no points for that match).
33. (Must) Report as standard JSON structure.
34. (Forbidden) No free-text final report — only attached JSON (else rejected, score zero).
35. (Must) Agree with the opponent on the result; each team sends its own report; non-report or
    contradictory reports → match void, **score 0 for both teams**.
36. (Must) Comprehensive mutual log audit at the end of every match (precondition to the shared JSON result).
37. (Must) Accurately declare the number of matches played at the start of every match.
38. (Forbidden) No false game-count declaration — full project disqualification.
39. (Forbidden) Never push secrets/credentials to the repo (even private + lecturer-shared).
40. (Must) Add credentials/secret files to `.gitignore`.
41. (Must) Tag the submission version with an annotated Git tag.
42. (Must) Include a comprehensive academic report (model, dilemmas, strategy, images, RL curves) in the repo.
43. (Must) Download the Moodle form, fill, save as PDF; don't change/move fields.
44. (Must) Each team member submits separately in Moodle.
45. (Must) Enter a unique 8-character team code (no spaces).

**Additions found by cross-checking (Table 12):**
46. (Must) Barrier placed on the thief's current cell = capture (cop wins). [Ch. 3]
47. (Must) A thief locked with no legal move is captured. [Ch. 3]
48. (Must) Score every end scenario per the scoring table (capture 20/5, survival 5/10, technical 0/0). [Ch. 3 + App. F]
49. (Must) Two separate repos (cop, thief) + README cross-link + two links in Moodle + four links in the JSON. [Ch. 9]
50. (Must) Each repo contains at least README, `config/`, PRD files, PLAN, TODO files. [Ch. 9]
51. (Must) Send automatic end reports to `[כתובת דיווחי הסוכן]`. [Ch. 9]
52. (Must) One counted match per opponent (no repeats for points); warm-ups allowed. [Ch. 9]
53. (Must) Record the commit hash in the Step-0 declaration; update it every match. [Ch. 5]
54. (Must) Report total tokens consumed per mini-game (and series) in the final JSON. [Chs. 5, 9]
55. (Must) Self-grade code quality only — not league results. [Ch. 11]

---

## 16. Appendix F (נספח ו) — the Mandatory Parameter Table, complete (PAGES 151–159)

**Status semantics (PAGE 155):**
- **Minimum (מינימום):** negotiable only in the direction that makes the game harder (usually
  raising); never below the sample value; sample value is the code's default absent explicit
  agreement.
- **Fixed (קבוע):** not changeable at all; deviation disqualifies the team.
- **Negotiable (משא ומתן):** any agreed value; sample value is the default absent agreement.

### Table 13 — Board, axes, start positions
| # | Parameter (code name) | Meaning | Sample value | Status |
|---|---|---|---|---|
| 1 | `[גודל הלוח]` board size | side of the square grid | **7×7** | minimum |
| 2 | `[מספר הסוכנים]` number of agents | players in the race | **2** | fixed |
| 3 | `[ראשית מערכת הצירים]` axis origin corner | corner of cell (0,0) | **top-left** | negotiable |
| 4 | `[אינדקס התחלת הצירים]` axis start index | first index of each axis | **0** | negotiable |
| 5 | `[עמדת פתיחה – גנב]` thief start | thief's opening cell | **center (3,3)** | negotiable |
| 6 | `[עמדת פתיחה – שוטר]` cop start | cop's opening cell | **corner (0,0)** | negotiable |

### Table 14 — Arena & verbal hints
| # | Parameter | Meaning | Sample value | Status |
|---|---|---|---|---|
| 1 | `[זירת המשחק]` map area | real-world region feeding real landmarks into hints; empty "" = generic | **New York** | negotiable |
| 2 | `[מגבלת מילים ברמז]` hint word limit | max words per verbal hint (applies to template AND LLM, via system prompt) | **15** | negotiable |

### Table 15 — Movement & barriers
| # | Parameter | Meaning | Sample value | Status |
|---|---|---|---|---|
| 1 | `[מערך התנועה]` move set | single orthogonal step or stay; no diagonals | **4 + stay** | fixed |
| 2 | `[מכסת המחסומים]` barrier quota | max barriers the cop may place | **14** | minimum |
| 3 | `[תקרת הצעדים]` step cap | max moves per mini-game | **35** | minimum |
| 4 | `[סף ההישרדות]` survival threshold | steps the thief must survive to win | **35** | minimum |

### Table 16 — Dynamic pheromones
| # | Parameter | Meaning | Sample value | Status |
|---|---|---|---|---|
| 1 | `[עוצמת הריח במוקד]` center intensity | pheromone strength at emitting cell | **0.9** | fixed |
| 2 | `[קצב דעיכת הריח]` decay rate | decay proportion per full turn | **0.10** | fixed |
| 3 | `[גודל שדה הריח]` scent field size | emission window side around agent | **5×5** | fixed |

### Table 17 — Scoring
| # | Parameter | Meaning | Sample value | Status |
|---|---|---|---|---|
| 1 | `[ניקוד לכידה – שוטר]` capture-cop | cop's points on successful capture | **20** | fixed |
| 2 | `[ניקוד לכידה – גנב]` capture-thief | thief's points when captured | **5** | fixed |
| 3 | `[ניקוד הישרדות – שוטר]` survival-cop | cop's points when thief survives | **5** | fixed |
| 4 | `[ניקוד הישרדות – גנב]` survival-thief | thief's points on successful survival | **10** | fixed |
| 5 | `[ציון תיקו]` tie score | each side's points when the cumulative series score vs an opponent ties | **2** | fixed |

### Table 18 — Network & league
| # | Parameter | Meaning | Sample value | Status |
|---|---|---|---|---|
| 1 | `[מספר המשחקונים]` mini-games per series | mini-games in a series vs one opponent | **6** | fixed |
| 2 | `[תגמול גיוון]` diversity reward | points for a win vs a new opponent | **10** | fixed |
| 3 | `[מינימום משחקים למעבר]` min games to pass | minimum matches per team for a passing grade | **2** | fixed |
| 4 | `[אומדן טוקנים לסדרה]` token budget/series | total LLM tokens a team may consume; actual usage reported by email | **~200,000** | negotiable |
| 5 | `[מספר המשחקים המרבי לכל קבוצה]` max games per team | maximum counted matches a team may play | **10** | fixed |

### Table 19 — Network, rate limiter & protection (Gatekeeper)
| # | Parameter | Meaning | Sample value | Status |
|---|---|---|---|---|
| 1 | `[בקשות לדקה]` requests/min | max outgoing API request rate | **30** | minimum |
| 2 | `[בקשות מקבילות]` concurrent requests | max parallel requests | **2** | minimum |
| 3 | `[השהיה לאחר שגיאה]` retry backoff | wait before retry | **5 s** | minimum |
| 4 | `[ניסיונות חוזרים]` retries | attempts before failure | **3** | minimum |
| 5 | `[עומק התור]` queue depth | request queue size under load | **100** | minimum |
| 6 | `[מגבלת זמן התגובה]` response timeout | timeout per network request | **30 s** | negotiable |
| 7 | `[סף כלב השמירה]` watchdog threshold | freeze time before Watchdog intervenes | **60 s** | negotiable |

### Table 20 — Attached-file variables, repo & lecturer addresses (reference only; NOT negotiable, not part of shared config)
| Variable | Role | Value |
|---|---|---|
| `[קובץ ההצהרה]` declaration file | pre-game declaration (teams, members, repos, hardware, model, tokens, times) | `declaration_<game_id>.json` |
| `[קובץ התצורה]` config file | agreed, cryptographically locked mini-game parameters | `config_<game_id>_g<NN>.json` |
| `[קובץ היומן]` log file | mini-game log for replay verification | `log_<game_id>_g<NN>.json` |
| `[קובץ התוצאות]` results file | final results report for league grading | `result_<game_id>.json` |
| `[מאגר הקוד לדוגמה]` example repo | reference implementation | `https://github.com/rmisegal/Game-P2P-Cop-Chase` |
| `[כתובת המרצה]` lecturer address | general mail & GitHub repo sharing | `rmisegal@gmail.com` |
| `[כתובת דיווחי הסוכן]` agent-report address | destination of automatic JSON reports | `rmisegal+uoh26finalgame@gmail.com` |

### Table 21 — LLM modes for the verbal game (private per peer; reference only)
See §5.1 above: `template` (default, 0 tokens) / `ollama` (local, 0 API tokens) /
`claude_api` (small cloud model, counted vs token budget) / `claude_cli` (highest cost).
`every_n_steps` reduces invocation frequency.

### Table 22 — Strategy module selection keys (private per peer; reference only)
| Key (`[strategy]`) | Role | How to override |
|---|---|---|
| `thief_class` | your thief brain, `package.module:Class` | inherit `ThiefBrain`, override `_pick_move` and/or `_decide_move` |
| `police_class` | your cop brain | same; cop's `_decide_move` also chooses the barrier |

### Appendix F §2 — Mandatory configuration rules (PAGE 156)
1. Define all values in the config; ensure identical on both teams; lock cryptographically.
2. Values may change each new match if consistent with the opponent agreement.
3. Distinct config filename per match (easy reconstruction).
4. Commit every match's config file to GitHub.
5. Code may change between matches → each match's email to the lecturer must include the GitHub
   commit number used.

---

## 17. Success metrics & grading signals (Ch. 11)

- Four success metrics (Table 4, PAGE 110): **Coordination** (turn management, P2P over FastMCP,
  no referee — Ch. 2); **Adaptation** (symmetric handling of uncertainty, belief maps — Chs. 4, 6);
  **Integrity** (Commit-Reveal + SHA-256, full audit pass — Ch. 5); **Architecture**
  (Gatekeeper/Orchestrator patterns, failure-resistant code — Chs. 8, 10).
- **Submission criterion:** the whole project (code, structure, submission) is graded per the
  course-intro document "Recommendations for writing and submitting software with AI agents".
- Final pre-submission checklist (PAGE 113): base logic runs a full race; FastMCP over a public
  URL (not just localhost); Commit-Reveal + audit passes; scent map + belief map actually drive
  decisions; Live GUI + Replay with Verified OK; Gmail JSON report from both sides; GitHub repo
  with Git tag + academic README; ≥ `[מינימום משחקים למעבר]` (=2) matches vs different teams.

---

## 18. Open questions / ambiguities (explicit list)

1. **No "agreement: true/false" boolean field exists anywhere in the book text.** The task brief
   mentioned agreement booleans in the end-of-game JSON; the book only says the report contains
   "mutual-agreement confirmations backed by SHA-256" (PAGE 94) without a field-level schema. The
   actual field names must be taken from the four sample JSON files attached to the book / the
   reference repo (`Game-P2P-Cop-Chase`) — **the schemas of declaration/config/log/result files
   are NOT reproduced verbatim in the book**, only their roles, naming pattern
   (`declaration_<game_id>.json` etc.), shared `game_uid`, and required fields mentioned in prose
   (4 GitHub links, `github_commit`, total tokens, hardware declarations, timestamps, MCP URLs).
2. **No "league ranking 75–100" appears in the book.** The brief's "75-100" range is absent from
   the extraction; the book only defines pass threshold (≥2 matches), max 10 counted matches,
   diversity reward 10, tie score 2, computational-fairness normalization "by the lecturer", and
   self-grade rules. Exact league-to-course-grade mapping is not specified.
3. **Report destination:** binding automatic-report address is
   `rmisegal+uoh26finalgame@gmail.com`, not `rmisegal@gmail.com` (which is for repo sharing /
   general mail). The brief said "sent to rmisegal@gmail.com" — follow the book.
4. **Board size inconsistency:** default/minimum is 7×7 (Appendix F, Ch. 3), but the abstract says
   "e.g. 10×10" and Ch. 6's belief-map figure/text uses 10×10 "for example". Resolution per the
   book's own rule: Appendix F wins → 7×7 minimum, larger negotiable.
5. **`max_moves` vs `survival_threshold` are both 35:** the thief wins by surviving 35 valid
   steps and the mini-game cap is 35 moves; the book does not define an outcome for a mini-game
   that ends at the cap other than survival — implicitly cap-reached = thief survival, but this is
   an inference. Also ambiguous whether "35 steps" counts full turns or individual agent moves.
6. **Turn timing values differ across sources:** Appendix F: response timeout 30 s, watchdog 60 s
   (both negotiable); private TOML example: `turn_timeout_seconds = 180`; watchdog code example:
   180 s. Teams must pick and document (academic-freedom clause).
7. **Commit hash input mismatch (simplification acknowledged by the book):** the replay sketch
   hashes only `nonce|move`, while the protocol hashes State∥Move∥Intent∥Nonce and the reference
   record is "richer" (hint, verdict, step, role, sub_game). The real signed-record field list is
   only in the reference repo.
8. **Turn order is never explicitly stated** (who moves first, cop or thief); the scent decay is
   defined "after cop and thief both completed their move". Ordering is presumably part of
   negotiation / reference implementation.
9. **Capture Claim protocol details** ("Capture protocol") are referenced but the message format
   for claim/response is not specified in the book text.
10. **`num_games` field vs `[מספר המשחקונים]`:** shared config ships `num_games: 1` (single
    example mini-game) while a full league series requires 6; teams must set 6 for real matches.
11. **Discovery/matchmaking is out-of-band:** no protocol for finding opponents; only
    `opponent_url` exchange. The mechanism for scheduling league matches with other teams is left
    to the teams/lecturer.
12. **"Signed" mechanics for the Step-0 declaration** use "a key supplied in advance"
    (PAGE 55) — who supplies the key (lecturer? mutual?) is not specified.
13. **`tie_score` scope:** defined at series level (cumulative equal score vs one opponent), yet it
    sits inside the per-mini-game `scoring` config block; per-mini-game tie handling is not
    defined.
14. **Rule 35 vs PAGE 87 sanction discrepancy:** PAGE 87 says a non-reporting side loses *its*
    points ("that side is not credited even if it won"); rule 35 (Appendix E) says non-report or
    contradictory reports void the match with **0 to both teams**. Choose conservatively: always
    send both reports and agree on results.
15. **Email attachment vs draft:** binding rules demand the JSON be *sent* as an attachment to the
    report address, while the reference repo defaults to `mode = "draft"`. For the league, send
    mode must be used (draft presumably for development).
16. **LLM model string in TOML example** (`claude-opus-4-8[1m]`) contains an extraction artifact
    (`8[1m]`); treat as illustrative only.
17. **GUI toolkit, hint language (Hebrew/English), and exact belief-update formula** are left to
    the teams (the book gives Bayes + reliability coefficient as the approach, not a formula).
18. **Extraction quality note:** the source text is RTL-garbled in places but no pages were
    unreadable; PAGE 67 contains one garbled default-value sentence for `map_area` (empty string ""
    ⇒ generic landmarks — reconstructed from context and Table 14).
