# ADR-007 — Heuristic/expectimax strategy; no RL

**Status:** accepted

RL is explicitly optional and untaught; 19 days favor a strong deterministic policy stack:
Bayesian belief + expectimax with barrier planning (cop) / survival-horizon maximization
(thief) + credibility-managed hint policy. The strategy lab (self-play sweeps) supplies the
guidelines-required sensitivity analysis instead of learning curves.

---

Extracted from `docs/PLAN.md`. See [the ADR index](README.md).
