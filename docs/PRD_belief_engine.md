# PRD — Belief Engine (scent + Bayesian opponent tracking)

| | |
|---|---|
| **Version** | 1.00 |
| **Date** | 2026-07-25 |
| **Mechanism** | `domain/scent_models.py`, `domain/scent.py`, `domain/belief.py`, `domain/hint_evidence.py` |
| **Parent docs** | `PRD.md` (FR-ENG-7, FR-STR-1, FR-STR-5/6, FR-LLM-5), `PLAN.md` (ADR-007) |

---

## 1. Problem & theoretical background

The game is a **Dec-POMDP**: the true state (both positions, barriers, scent
field) is never observable to either agent. Each side sees only

* the opponent's **decaying pheromone field** — emitted involuntarily by
  presence, therefore *unfakeable* (book PAGE 22), and
* a **free-language hint** that the opponent may deliberately falsify — the only
  deception channel in the game.

We must maintain a posterior `b(s) = P(opponent at cell s)` and act on it. The
engine is deliberately deterministic: the LLM never touches it (book rule 25),
so hallucination cannot cause an illegal move or a lost game.

### 1.1 Scent physics (binding)

Emission is a 5×5 field, centre intensity 0.9, both *fixed* by Appendix F
Table 16. Decay per full turn follows

```
τ_ij(t+1) = max(0, (1 − ρ) · τ_ij(t) + Δτ_ij),   ρ = 0.10
```

with values clamped to `[0, 0.9]`. The book's binding worked example (PAGE 44)
is reproduced **exactly** by our implementation:

```
0.04 0.14 0.20 0.14 0.04
0.14 0.42 0.62 0.42 0.14
0.20 0.62 0.90 0.62 0.20
0.14 0.42 0.62 0.42 0.14
0.04 0.14 0.20 0.14 0.04
```

We generate it as `0.9 · exp(−k·d²)` rounded to 2 dp with `k = 0.378`, a
constant calibrated to that table and locked by
`test_book_numeric_example_matches_exactly`.

### 1.2 Book vs. reference-simulator conflict (resolved)

| aspect | book (binding) | lecturer's simulator |
|---|---|---|
| falloff | radial (Euclidean) | Chebyshev, linear |
| decay | relative `τ·(1−ρ)` | absolute `τ − ρ` |

The book governs, so `ScentModel.BOOK` is our default. Because rule 23 requires
the emission+decay model to be exchanged with a numeric example and SHA-256
locked per opponent — and most teams start from the simulator — the model is a
**negotiable term** (`ScentModel.REFERENCE` implements the simulator's variant).
`model_fingerprint()` produces the hash both sides compare. Matching an
opponent is therefore configuration, never a code change (kills A6 pain #2).

## 2. Inputs / outputs / setup

| Building block | Input | Output | Setup |
|---|---|---|---|
| `ScentField` | own cell (deposit); peer `{"r,c": v}` map (absorb) | intensity queries; `snapshot()` wire map; rejection reasons | board size, grid size, decay, centre intensity, model |
| `BeliefGrid` | scent intensities, likelihood maps, excluded cells | `probability_at`, `peak`, `as_dict` (UI heatmap) | board (incl. declared barriers) |
| `hint_evidence` | decoded `HintClaim`, reference cell, credibility | per-cell likelihood; `"consistent"/"refuted"/"unknown"` verdict | boost/penalty, tolerance, learning rate |

**Contracts.** `snapshot()` never contains a coordinate field — only intensities,
so absorbing it cannot leak a position. `absorb()` never raises on hostile input;
it returns reasons for the caller to log (zero-trust ingress). `BeliefGrid` is a
valid probability distribution after *every* operation.

## 3. Fusion order (normative)

```
diffuse (motion model, barrier-aware)
  → update_scent (physical evidence, sharpened)
    → apply_likelihood (hint testimony × credibility)
      → exclude (cells provably empty, e.g. our own)
```

Testimony is fused **last and weakest**: it can only re-weight mass that physics
still permits. `test_hint_cannot_override_contradicting_scent` and
`test_a_lying_hint_does_not_derail_a_locked_belief` enforce that a maximally
confident lie cannot move the peak off the scent mass.

## 4. Design decisions found by testing

Three defects were caught by scenario/property tests, not by review — each fix
is documented in code with the reason:

1. **Decay fixed point.** Relative decay rounded to 3 dp is self-sustaining at
   0.005, so dead trails never disappeared and polluted belief forever. Fixed
   with `SCENT_EPSILON`, plus removing all mid-computation rounding (rounding can
   nudge a value *up*); intensities are now rounded once, at the wire boundary.
2. **Belief lagged a moving opponent by ~5 cells.** Multiplying the cumulative
   scent field into belief every turn double-counts history, so an early leader
   keeps an unearned advantage. Fixed with a robust mixture update
   (`OBSERVATION_WEIGHT`): the fresh observation always gets to speak.
3. **Nearly-flat likelihood.** At ρ=0.10 the head of a trail is only ~11%
   stronger than the cell behind it, so diffusion parked belief mid-trail. The
   opponent is at the *freshest* scent, so the likelihood is sharpened
   (`SCENT_SHARPNESS = 8`, an observation-temperature choice) with an **additive**
   floor that keeps faint scent strictly above no scent.

## 5. Metrics & acceptance

| Metric | Target | Test |
|---|---|---|
| Book numeric example | exact match | `test_book_numeric_example_matches_exactly` |
| Distribution validity | sum 1 ± 1e-6, no negatives/NaN, ∀ update sequences | `test_belief_properties.py` (hypothesis) |
| Convergence | peak within 1 cell of truth after ≤ 6 turns | `test_belief_peak_locks_onto_the_true_position` (3 paths) |
| Concentration | P(true cell) > 10× uniform prior | `test_belief_concentrates_far_above_the_uniform_prior` |
| Lie detection | book PAGE 46 example refuted; perpendicular claim → `unknown` | `test_hint_evidence.py`, `test_belief_convergence.py` |
| Latency | one full update < 50 ms on 7×7 and 15×15 | `test_full_update_fits_the_move_budget` |
| Robustness | arbitrary hostile peer payloads never raise | `test_absorb_never_raises_on_arbitrary_untrusted_input` |

## 6. Alternatives considered

| Alternative | Why not |
|---|---|
| Particle filter | Overkill for ≤ 225 cells; exact grid inference is cheaper and deterministic (replay-friendly). |
| Pure multiplicative Bayes | Double-counts the cumulative scent field; measured to lag a moving target (defect 2). |
| Q-learning / RL belief | Book marks RL optional and the course did not teach it; 19-day budget (ADR-007). |
| LLM-estimated position | Forbidden as a move source (rule 25) and unauditable; LLM stays on language only. |
| Trusting hints at face value | Free lying is legal; unweighted testimony is exactly how a good bluffer beats a naive tracker. |

## 7. Open items

* `SCENT_SHARPNESS`, `OBSERVATION_WEIGHT`, and hint boost/penalty become the
  sensitivity-study parameters for the analysis notebook (E22) — currently set
  from reasoning plus scenario tests, not yet swept.
* Landmark→cell gazetteer is supplied by the map-area layer (E13); the domain
  accepts the cells but does not own the vocabulary.
* Credibility currently starts neutral (0.5) each opponent; carrying priors
  across a series is wired (`CredibilityTracker(coefficient=…)`) and consumed by
  `strategy/opponent_model.py` in E16.
