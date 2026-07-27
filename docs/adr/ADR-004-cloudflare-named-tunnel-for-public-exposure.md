# ADR-004 — Cloudflare named tunnel for public exposure

**Status:** accepted

Permanent hostname fixes A6's URL churn. Requires a domain on a (free) Cloudflare zone —
operator prerequisite. `tunnel.py` supervises cloudflared, and preflight performs a self-call
through the public URL. **Fallback:** ngrok static domain (config switch, no code change).

---

Extracted from `docs/PLAN.md`. See [the ADR index](README.md).
