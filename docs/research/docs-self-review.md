# Docs Self-Review — Adversarial Findings (PRD.md / PLAN.md / TODO.md)

**Reviewed:** `docs/PRD.md` (v1.00), `docs/PLAN.md` (v1.00), `docs/TODO.md` (v1.00, 613 tasks)
**Against:** `docs/research/project-book-digest.md` (§15 55 rules, §16 Appendix F, §18 open questions),
`guidelines-digest.md` (§12, §15), `simulator-repo-digest.md`, `assignment6-retrospective.md`
**Date:** 2026-07-24 · **Scope:** verified failures only — no style nitpicks.

**Severity counts: Critical 3 · Major 7 · Minor 8**

---

## Verification summaries (checks that PASSED)

1. **Binding-rule coverage (55 rules):** all 55 book rules map to at least one PRD requirement
   or TODO task. Rules 1–2→FR-NET-6/T-1028; 3→T-0806/07; 4–5→T-0801; 6→FR-NET-4/T-1017;
   7→FR-NET-5/T-1020; 8–9→FR-UI-1/T-1809; 10→FR-NET-3/E11; 11→FR-NEG-1/T-1205; 12→T-1206;
   13–14→T-0507/T-0509; 15–16→T-0516; 17→FR-CRY-1/2; 18→FR-CRY-5/T-0711–13; 19→T-0716;
   20→E19; 21→T-0523/24; 22→partial (see Minor-2); 23→T-1207/08; 24→T-0720/21; 25→FR-STR-2;
   26→FR-LLM-4; 27→T-1320; 28→T-0310/ADR-009; 29→T-1721; 30→T-1714; 31→T-2313; 32→FR-REP-3;
   33–34→T-1716; 35→FR-REP-6/T-2416; 36→T-0717; 37–38→T-1209/T-2307; 39–40→T-0108/T-0208/T-2408;
   41→T-2410; 42→T-2204; 43→T-2412/14; 44–45→T-2415; 46→T-0519; 47→T-0521; 48→T-0527;
   49→T-0119/20/T-2405/06; 50→T-0122/T-0216; 51→T-1716; 52→T-2306/07; 53→T-0722/T-2325;
   54→T-1325; 55→T-2413. **No rule with zero coverage.** One partial (rule 22, Minor-2).
2. **Guidelines master checklist (§15):** every item maps to a TODO task (automated gates
   T-0104/05, T-0203–0216; review-checked T-2402, T-0417, T-0111, T-0428; content deliverables
   T-2212–2228, T-1825–27, T-0110, T-0121). **No unmapped checklist item found.** Two
   consistency defects inside the mapping (Major-1 footprint, Minor-4).
3. **Appendix F fidelity:** every numeric value cited in PRD/PLAN/TODO was checked against
   Appendix F tables 13–19: 7×7 (FR-ENG-1, T-0315), 14 barriers (FR-ENG-3, T-0315, T-1417),
   35/35 (FR-ENG-5, T-0315, T-0525), 0.9/0.10/5×5 + clamp [0,0.9] (FR-ENG-7, T-0315,
   T-0601/03), worked field 0.90/0.62/0.42 (T-0610), scoring 20/5/5/10/2/0 (FR-ENG-6, T-0315,
   T-0527/31), 6 mini-games (FR-ENG-6, T-0316), diversity 10 (referenced non-numerically),
   min 2 / max 10 (G2), 200k tokens (G6, T-1324), gatekeeper 30 rpm/2/5 s/3/100 (ADR-009,
   T-0310), 30 s response / 60 s watchdog (PRD §4, T-1022), hint 15 words (FR-LLM-4, T-0315).
   **Zero numeric mismatches found.**
4. **Submission mechanics:** two repos (T-0101), cross-links (T-0119/20, T-2406),
   `v1.0-submission` annotated tag (T-2410/11), Moodle PDF per member (T-2412–15, team code
   NajAmjad = 8 chars verified), self-grade code-quality-only (T-2413).
   `rmisegal+uoh26finalgame@gmail.com` used for reports everywhere it appears (PRD:38,244;
   PLAN:20; TODO:117,540); `rmisegal@gmail.com` used only for repo sharing (TODO:720).
   **Correct usage everywhere.**
5. **Task arithmetic:** all 24 epic task counts and the 613 total re-counted and confirmed
   correct against the progress table.

---

## CRITICAL

### C-1 — Circular dependency: T-0217 ↔ T-2108
- **File/location:** `docs/TODO.md` lines 96 and 630.
- **Evidence:** T-0217 (nightly self-play workflow, E02) carries `[deps: T-2108]`;
  T-2108 (win-rate gate, E21) carries `[deps: T-0217]`. Neither can start first; T-1424
  (line 469) also depends on T-0217, propagating the cycle into E14 gate wiring.
- **Impact:** the task graph has no valid topological order; a pedantic grader checking
  dependency soundness fails it immediately. It also poisons the M4 exit criterion, which is
  measured by T-2108.
- **Fix:** make T-0217 create the *workflow shell* with no deps (cron file that tolerates a
  missing harness), and keep only T-2108 → `[deps: T-0217, T-2106]`. Remove `deps: T-2108`
  from T-0217.

### C-2 — Circular dependency: T-0610 ↔ T-1207
- **File/location:** `docs/TODO.md` lines 209 and 384.
- **Evidence:** T-0610 (pheromone numeric-example golden, E06) carries `[deps: T-1207]`;
  T-1207 (pheromone-model lock tests, E12) carries `[deps: T-0610]`. Also inverts milestones:
  E06 is M2 (Jul 30) yet depends on an E12/M5 (Aug 6) task.
- **Impact:** second unbuildable cycle; blocks both the M2 scent epic and the negotiation
  lock flow on paper.
- **Fix:** T-0610 has no dependency on E12 (it *produces* the lock example); delete
  `deps: T-1207` from T-0610 and keep `deps: T-0610` on T-1207 only. (The intended relation
  is already stated in T-0610's DoD: "file used later by contract lock".)

### C-3 — Cross-milestone dependency inversions break M2/M3/M5 exit criteria as scheduled
- **File/location:** `docs/TODO.md` lines 195, 256–257, 387, 648 vs. the phase table (lines 38–46).
- **Evidence (later-milestone tasks blocking earlier-milestone epics):**
  - T-0533 (E05, M2 Jul 30) `[deps: T-0901]` — T-0901 is E09, scheduled M3 (Aug 2).
  - T-0724/T-0725 (E07, M3 Aug 2) `[deps: T-1323]` — T-1323 (token meter) is E13, scheduled
    M4 (Aug 4). Contradicts its own DoD too: "tests green **with a meter fake**" needs no
    real meter.
  - T-1210 (E12, M5 Aug 6) `[deps: T-2307]` — T-2307 (counted-game tracker, a P0 *code* task)
    sits in E23, scheduled M6 (Aug 5–10), i.e. after/parallel to the milestone that needs it.
  - T-2126 (E21, M5) `[deps: T-2305]` — T-2305 (per-match runbook) is E23/M6; yet the
    pre-match smoke must exist before the first league match (Aug 5).
- **Impact:** as written, M2, M3 and M5 cannot be closed on their target dates without
  violating the plan's own phase table; the AI grader can detect this mechanically.
- **Fix:** (a) move T-0901/T-0902 (golden extraction — pure file copying) into E01 or E03 so
  every golden-dependent task is downstream; (b) drop `deps: T-1323` from T-0724 (fake-based)
  and add a later wiring task in E13; (c) move T-2307 and T-2305 out of E23 into E12/E22
  respectively (they are build tasks, not match-day operations); (d) re-run a dependency
  lint over the final TODO (a trivial script — consider adding it as a task).

---

## MAJOR

### M-1 — T-0807/T-0826 falsely claim orchestrator.py is missing from PLAN §1.3, and use a conflicting path
- **File/location:** `docs/TODO.md` lines 274, 293 vs. `docs/PLAN.md` line 88.
- **Evidence:** T-0807: "Implement `src/najamjad_agent/orchestrator.py` (… NOTE: file missing
  from PLAN §1.3 map — add it to PLAN and the core manifest)". PLAN §1.3 line 88 already
  contains `domain/orchestrator.py  # gateway conductor over all subsystems  ~120`. Two
  defects: the "missing" claim is false, and the TODO path (package root) contradicts the
  PLAN path (`domain/`).
- **Impact:** a builder following TODO literally creates a second orchestrator at the wrong
  path and "fixes" a PLAN that isn't broken; the grader sees a PRD/PLAN/TODO contradiction.
- **Fix:** rewrite T-0807 to "Implement `src/najamjad_agent/domain/orchestrator.py` per PLAN
  §1.3"; delete the NOTE; reduce T-0826 to "docstrings + manifest entry".

### M-2 — PRD assumption A4 contradicts PLAN R10 / T-1712 on the Google OAuth setup
- **File/location:** `docs/PRD.md` line 301 vs. `docs/PLAN.md` §9 R10 (line 365) and
  `docs/TODO.md` line 536.
- **Evidence:** PRD A4: "the user can provide … **the existing Google OAuth client**".
  PLAN R10 and T-1712: "set up a **FRESH dedicated Google Cloud project** … create Desktop
  OAuth client" — explicitly motivated by the A6 account ban.
- **Impact:** direct PRD↔PLAN position contradiction on a submission-critical channel
  (reporting email); ambiguity over which credentials the preflight (T-1113) validates.
- **Fix:** change A4 to "a Google account able to create a fresh dedicated Cloud project
  (T-1712); the A6 client is NOT reused (risk R10)".

### M-3 — No task procures/validates the Anthropic and DeepSeek API keys (missing prerequisite)
- **File/location:** `docs/TODO.md` (whole file — only T-0109 line 60 mentions the keys, as
  `.env-example` dummies); `docs/PLAN.md` R5 (line 360).
- **Evidence:** PLAN R5 records "Anthropic key/billing issues (**seen today**)", yet no ops
  task exists to obtain keys, fund billing, set spend limits, and confirm a live completion
  on both providers — unlike the parallel prerequisites which do have tasks (Cloudflare
  domain T-1101, Google Cloud project T-1712, tunnels T-1109, second machine T-2324).
  T-1114 only *checks* provider health at preflight; it cannot create the prerequisite.
- **Impact:** the LLM chain (FR-LLM-1, M4) can be blocked by a known, already-observed risk
  with no owning task; grader cross-checking risks→tasks finds R5 unclosed.
- **Fix:** add an E11-or-E13 P0 ops task: "Provision + verify Anthropic and DeepSeek API keys
  (billing active, spend cap set, one live round-trip each, keys in `.env` only) by Jul 28 —
  DoD: preflight LLM check green against both real providers" (mirrors T-1101's deadline style).

### M-4 — E21 milestone assignment contradicts itself, undermining the M4 exit criterion
- **File/location:** `docs/TODO.md` phase table line 43 (E21 listed under M5, Aug 6) vs.
  progress table line 777 (E21 = "M4–M5"); PRD §7 M4 (line 338).
- **Evidence:** M4's exit criterion (Aug 4, "self-play: our brains beat reference brains
  ≥ 70% over 100 games") is measured by E21 tasks T-2106–T-2108, which the phase table
  schedules in M5 (Aug 6). The two tables inside TODO disagree with each other, and the
  phase table disagrees with PRD §7.
- **Impact:** M4 cannot be exited under the phase table's own schedule; internal
  inconsistency between the two authoritative tables.
- **Fix:** split E21: move T-2101–T-2110 (harness/self-play) into the M4 row of the phase
  table; keep interop/chaos/coverage tasks (T-2111+) in M5. Align the progress-table row(s).

### M-5 — League window (M6, from Aug 5) starts before its enabling M5 epics complete (Aug 6)
- **File/location:** `docs/PRD.md` §7 rows M5/M6 (lines 339–340); `docs/TODO.md` phase table
  lines 43–44; T-2309 (line 695) `[deps: T-2112]`.
- **Evidence:** M6 ("warm-ups then counted", ≥2 counted by Aug 8) opens Aug 5, but tunnel
  (E11), negotiation (E12), reporting (E17), CLI (E20) and the public-URL reference match
  (T-2112) — all mandatory for even a warm-up — are M5 deliverables dated Aug 6. The
  match-day rehearsal T-2309 depends on T-2112, i.e. on the M5 exit criterion itself, yet
  T-2304 books match windows starting Aug 5. PRD risk R9 acknowledges the squeeze but the
  milestone tables still contradict each other.
- **Impact:** the first league day is unplayable per the plan's own dependency chain; a
  grader checking "milestones consistent and feasible" flags it.
- **Fix:** either move M5 to Aug 4 (pulling E11 earlier — T-1101/T-1109 already target
  Jul 27) and hold M6 warm-ups at Aug 5, or move the M6 warm-up start to Aug 6–7 and the
  ≥2-counted checkpoint to Aug 9, keeping ≥1 day of buffer to the Aug 10 target.

### M-6 — Throughput infeasibility: ~613 tasks (~85% P0) in ~12 build days for 2 people, with no capacity analysis or cut line
- **File/location:** `docs/TODO.md` header (line 10) + progress table (lines 755–781);
  `docs/PRD.md` §7.
- **Evidence:** M1–M5 (Jul 25 → Aug 6) must absorb E01–E22's ~569 tasks — ≈ 47 tasks/day
  across two people (≈ 24/person/day) including TDD, mirroring to a second repo, and CI
  gates; no doc contains a load estimate, a P1/P2 deferral trigger, or a "minimum compliant
  subset" definition (the only prioritization device is the P0/P1/P2 tag itself).
- **Impact:** the schedule is not credible as written; when slippage hits, there is no
  pre-agreed cut line protecting the binding-rule/guidelines core.
- **Fix:** add to TODO a "descope ladder" (e.g., at M3+1day slip: drop E16 P1s, T-1413/14,
  E18 P1 panels…) and a one-line capacity note per milestone; mark which P0s are gate-vs-nice
  so the AI grader sees deliberate scope control.

### M-7 — A6 retrospective "Fix/Keep" decisions silently dropped without a recorded decision
- **File/location:** `docs/research/assignment6-retrospective.md` §7 ("Email layer — Fix:
  add inbox polling…", lesson 3, lesson 10 "add mypy/pyright") vs. PRD FR-REP-3/FR-REP-6 and
  the whole TODO.
- **Evidence:** All 7 A6 *pains* have implementing tasks (verified: #1→T-1718/19/20, T-1113,
  T-1816; #2→T-1223–25, T-0909, T-2310; #3→T-1103–05/09; #4→T-1220, T-1812, T-1305;
  #5→T-0921–24, T-1722–25; #6→T-0901/02/11/25, T-2111; #7→T-1805/06/20/24). However two
  explicit retrospective *decisions* are neither implemented nor explicitly declined:
  (a) "a receive path is half of every protocol — inbox polling (Gmail `messages.list`/IMAP)
  feeding the state machine" — the final design keeps send-only scope (FR-REP-3) and
  reconciles over MCP (FR-REP-6) instead, which is defensible, but no ADR records the
  substitution; (b) "add mypy/pyright" (lesson 10) — absent from PRD/PLAN/TODO and from
  T-2225's build-time-ADR list.
- **Impact:** the retrospective is cited as a research base; a grader diffing its decisions
  against the plan finds two unclosed items with no rationale.
- **Fix:** add an ADR (or a line in ADR-006/T-2225) — "MCP reconciliation replaces email
  receive path; gmail.send-only retained per book rule 30" — and either add a `ty`/mypy CI
  task or record "no type checker: not guidelines-mandated, ruff+pydantic suffice" as a
  deliberate decision.

---

## MINOR

### m-1 — Nonexistent identifier `[G-M4]` in two tasks
- `docs/TODO.md` lines 466, 494 (T-1421, T-1520) cite `[G-M4]`; PRD defines only G1–G6 and
  M0–M7. **Fix:** change to `[PRD §7 M4]`.

### m-2 — Book rule 22 (no false capture claims) covered only on the thief side
- T-0523/T-0524 (TODO lines 185–186) guarantee the *thief's* honest `claim_response`;
  no test asserts the *cop's* `capture_claim` always equals its true own cell (the reference
  auto-sends own-cell claims; our re-implementation has no task locking that invariant).
  **Fix:** add a test task in E05/E08: "cop capture_claim is derived from true own position
  only; no code path can claim a foreign cell [book rule 22]".

### m-3 — Playbook task claims "EVERY negotiable Appendix F item" but its list omits three
- T-1213 (TODO line 390) and ADR-011 (PLAN lines 276–282) enumerate "board size, starts,
  axis, map area, hint cap, timeouts, token budget" — omitting `max_moves`,
  `survival_threshold`, and barrier quota, all negotiable-upward per book digest §9/§16
  (Table 15 "minimum" status). **Fix:** extend both lists (or say "all minimum+negotiable
  rows of Tables 13–15, 18–19").

### m-4 — Coverage omit references an entry file `main` that does not exist in the module map
- T-0105 (line 56), T-2122 (line 644) and PLAN ADR-009 note (lines 267–269) exempt "entry
  `main`", but PLAN §1.3 has no `main.py`; the entry point is `cli.py` +
  `[project.scripts]`. **Fix:** change the omit wording to "`cli.py` entry wiring only (or
  nothing)" and keep the omit list synced with the real tree.

### m-5 — Legend/sub-task convention contradicts actual usage
- TODO legend (lines 30–31) defines indented `- [ ]` bullets as *sub-tasks of the parent*,
  but indented items T-0406–T-0410 (lines 137–141) and T-1111–T-1114 (lines 369–372) carry
  full task IDs and are counted in the epic totals. **Fix:** un-indent them (they are
  ordinary tasks) or drop the sub-task clause from the legend.

### m-6 — T-0724 DoD vs. dependency contradiction (fake vs. real meter)
- TODO line 256: DoD says "tests green **with a meter fake**" while deps demand the real
  T-1323 implementation. Subsumed by C-3 but worth its own one-line fix: delete the dep.

### m-7 — PLAN ADR-009 hosts the coverage-omit policy, unrelated to its subject
- PLAN lines 267–269: the coverage-omit note lives inside ADR-009 (ApiGatekeeper). A grader
  hunting for the coverage policy via ADR titles will miss it. **Fix:** move the note to
  ADR-010 (toolchain/CI) where coverage is decided.

### m-8 — E4 gate ("zero `python -m` anywhere incl. docs") can be tripped by quoting the reference simulator
- PRD E1 table row E4 (line 81) + T-0210 (line 89) ban `python -m` strings in docs, but the
  reference simulator's canonical run command is `uv run python -m police_thief …`
  (simulator digest §2), which match runbooks/interop docs (T-2111/T-2309, docs/CI.md) may
  legitimately need to quote. **Fix:** scope the grep gate to exclude fenced quotations of
  third-party commands, or standardize on describing the reference runs without verbatim
  commands.

---

## Explicit "no finding" declarations (checked, clean)

- **Appendix F numerics:** no mismatch anywhere in PRD/PLAN/TODO (see summary 3).
- **55 binding rules:** no uncovered rule (one partial, m-2).
- **Guidelines §15 master checklist:** no unmapped item.
- **FR-*/ADR-* referential integrity:** every FR-ENG/NET/NEG/CRY/STR/LLM/UI/REP/CFG/OBS and
  ADR-001..012 cited in TODO exists in PRD/PLAN and is used consistently (single exception:
  `[G-M4]`, m-1; single false cross-claim: T-0807, M-1).
- **Module map:** all TODO file paths match PLAN §1.3 (single exception: orchestrator, M-1).
- **Email addresses:** report vs. lecturer address used correctly at every occurrence.
- **Ports:** cop 8802 / thief 8801 consistent across PLAN §1.4, T-0313/T-0314, reference repo.
- **Task arithmetic:** 613 total and all 24 per-epic counts are correct.
