# PRD — Commit-Reveal Integrity, Audit & Step-0

| | |
|---|---|
| **Version** | 1.00 |
| **Date** | 2026-07-25 |
| **Mechanism** | `protocol/canonical.py`, `domain/crypto.py`, `domain/nonce_vault.py`, `domain/ledger.py`, `domain/audit.py`, `reporting/step_zero.py`, `shared/sysinfo.py` |
| **Parent docs** | `PRD.md` (FR-CRY-1..5, FR-REP-5), `PLAN.md` (ADR-006, ADR-012) |

---

## 1. Problem

The game has **no referee**. Two competing agents exchange moves over the open
internet, and each has an obvious incentive to rewrite history once it sees how
a mini-game turned out. The book's answer is cryptographic rather than social:
every move is committed to before it is revealed, and every claim is re-verified
at the end (Ch. 5). A proven mismatch voids the game for the forger — "iron law",
no appeal (rule 19).

Two failure modes matter equally:

* **Being cheated** — an opponent alters a move after the fact. Caught by audit.
* **Appearing to cheat** — our bytes differ from theirs for an innocent reason
  (key order, unicode escaping, a stray rounding), and our honest log fails their
  audit. This costs us the match just as thoroughly, which is why byte-format
  compatibility is golden-tested against the lecturer's own sample log.

## 2. Protocol

```
1. Commit      seal(payload) -> commit = SHA256(canonical(payload) + "|" + nonce)
               send commit only; nonce enters the vault
2. Acknowledge opponent confirms it is locked on our commitment
3. Reveal      send payload (move, hint, intent) — nonce still withheld
4. Audit       mini-game ends -> vault opens -> exchange all nonces
               each side re-hashes every opponent record
```

Ordering is enforced by `CommitLedger`, not by convention: revealing before an
acknowledgement raises `ProtocolOrderError` (an unlocked opponent could still
adapt), and the nonce vault physically refuses reveal while sealed.

### 2.1 Byte-format contract (interop-critical)

| Element | Value |
|---|---|
| Canonical JSON | `sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")` |
| Hash input | `canonical_json(payload) + "|" + nonce`, UTF-8 encoded |
| Digest | SHA-256, lowercase hex |
| Nonce | `secrets.token_hex(16)` — 16 bytes / 32 hex chars, fresh per step |
| Comparison | `secrets.compare_digest` only |

**Verified against reality:** all 19 records of
`tests/goldens/artifacts/log_segal-police-team-vs-segal-thief-team_g01.json`
re-hash to their stored commits with this exact format
(`test_golden_log_records_all_verify`). `ensure_ascii=False` matters — a Hebrew
or emoji hint would otherwise hash differently on the two peers.

### 2.2 Sealed payload shape

`step, role, sub_game, position, move, intent, hint, state` plus optional
extras (`tokens_step`, `capture_claim`, …). Sealing the **intent** (truth/lie)
is what makes bluffing auditable: a thief who claims afterwards that a lie was
truth cannot produce a matching hash.

## 3. Nonce custody

A leaked nonce is a lost game — with this payload space an opponent holding our
nonce could brute-force our exact position from a commit. So:

* nonces live in `NonceVault` behind an explicit audit gate (`NonceSealedError`
  before it opens — book rule 18);
* spilled state is XOR-encrypted under a key that exists only in memory, so a
  crash dump or stray file read reveals nothing (`test_spill_file_does_not_contain_plaintext_nonces`);
* `SealedRecord.public_view()` structurally cannot contain a nonce, and an
  integration meta-test scans everything transmitted mid-game for vault values
  (`test_no_nonce_is_observable_before_the_audit_opens`).

Crash recovery matters for a different reason: losing the vault means we cannot
produce an audit, which is a forfeit even though we were honest — hence
`spill`/`restore`.

## 4. Audit

`audit_records` returns an `AuditReport` (`passed`, `verified_steps`,
`failed_steps`, `errors`, `banner`). Design decisions:

* **Never raises on hostile input.** Malformed audit payloads return a failing
  verdict, because a peer must not be able to crash us into a technical loss
  (8 malformed shapes covered).
* **Localises tampering.** Property tests over random single-record corruption
  (payload / nonce / commit) assert the report names *exactly* that step.
* **Symmetric.** Both peers reach identical verdicts from identical evidence.
* **Gates the result.** `may_agree_result` requires both audits to pass before a
  shared result may be agreed (rule 36) — this is also our protection against
  rule 35, which voids the match for *both* teams on contradictory reports.
* **Skips honestly.** Timeout/stopped/quit endings never closed the protocol, so
  audit is skipped and reported as such (matches the reference `SKIPPED_AUDIT`),
  rather than faking a pass.

## 5. Step-0 declaration

Before the first move each side seals hardware spec, LLM model, code version,
team identity, mini-game number, token totals and the **git commit hash** of the
running code (rule 53, mandatory; feeds the computational-fairness bonus, rule
24). Because it is sealed, a team cannot claim weaker hardware after losing
(`test_sealed_declaration_cannot_be_revised_afterwards`).

`declaration_is_complete()` returns problems instead of raising: a missing GPU
probe should warn the operator, not block a match that is about to start. The
commit hash is captured with an argument-list subprocess call (never a shell).

**Sealed in `sdk/state_setup.state_factory`**, which is the one place holding
both the configuration the declaration describes and the ledger it goes into; a
state handed back from there has not moved yet, so "before the first move" is
structural rather than a matter of call order. Step 0 is free because
`GameState.step` starts at 0 and the orchestrator increments *before* it
commits. Hardware and `git rev-parse` are resolved **once at wiring time**: both
shell out, and a subprocess between mini-games sits on the path of a watchdog we
have already agreed to. Nothing in the sealer may raise — a record describes a
match and is never a reason not to play one.

Until T-2532 this section described a component that existed and was never
called. Every log we filed opened at step 1, and E07 was marked complete on unit
tests that could not observe the absence of a caller.

**Reading the other side's.** A peer's `github_commit` (rules 49, 53) and token
total (rule 54) cannot be computed from anything we hold — they are only in
*their* step-0 record, which arrives with the rest of their reveals at the audit
and is carried on every played record as `their_records`.
`reporting/peer_declaration.py` reads it, matching on `type` rather than
position so a peer who orders their reveal differently is not treated as having
lied. Token totals are **running**, so a mini-game's cost is the gap between
consecutive declarations; the last game has no successor and is reported as 0
rather than guessed. A peer who declares nothing — most of them today — still
produces a filable report.

## 6. Metrics & acceptance

| Metric | Target | Test |
|---|---|---|
| Reference byte-compatibility | 19/19 golden records verify | `test_golden_log_records_all_verify` |
| Round-trip | seal→verify holds ∀ payloads (unicode, nested) | `test_crypto_properties.py` |
| Nonce uniqueness | 10/10 distinct commits per payload | property test |
| Tamper localisation | exactly the corrupted step flagged | property test (150 examples) |
| Pre-audit secrecy | 0 nonce occurrences in transmitted data | integration meta-test |
| Hostile input | 8 malformed shapes → verdict, no exception | `test_audit.py` |
| Crash recovery | vault restores, audit still passes | integration test |

## 7. Alternatives considered

| Alternative | Why not |
|---|---|
| Digital signatures (asymmetric) | Needs key distribution the book does not define; commit-reveal is the mandated scheme (rule 17). |
| Hash without nonce | The move space is tiny — a rainbow table over (state, move) inverts commits instantly. |
| Revealing nonces per step | Lets the opponent verify sooner but destroys hidden information mid-game; the book mandates end-of-game reveal (rule 18). |
| Trusting the opponent's own audit result | A cheater would simply report "passed"; each side must re-verify independently. |

## 8. Security checklist (T-0732) — enforced by meta-tests

Each item is a test in `tests/unit/test_domain/test_crypto_review.py`, so the
checklist cannot silently rot as the codebase grows:

- [x] `secrets.compare_digest` is the only commit comparison; no `== commit` anywhere
- [x] SHA-256 computed only in designated modules (crypto, scent_models, nonce_vault)
- [x] Canonical JSON pinned in one module with the exact interop flags
- [x] Nonce entropy 16 bytes; `random` never imported anywhere in the package
- [x] Fresh nonce per step; re-storing a step is refused
- [x] Nonces never reachable before audit (vault gate + public_view + wire scan)
- [x] No `shell=True` anywhere (git and nvidia-smi use argument lists)
- [x] No secret (`nonce`, `api_key`, `token`) interpolated into a log/print call

**Open item:** nonce uniqueness *across* mini-games relies on 128-bit entropy
rather than a persisted registry — a collision is ~2⁻¹²⁸ and a registry would
itself become a secret at rest. Revisit only if a game ever replays a vault.
