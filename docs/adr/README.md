# Architecture decision records

Each decision that shaped this project, with its context, the choice, and
what it cost. Extracted from `PLAN.md` §ADR so each can be cited and
amended on its own (guidelines §2.2).

| ADR | Decision | Status |
|---|---|---|
| [ADR-001](ADR-001-mcp-fastmcp-transport.md) | MCP/FastMCP transport | imposed |
| [ADR-002](ADR-002-two-self-contained-repos-mirrored-core-no-shared.md) | Two self-contained repos, mirrored core, no shared runtime | accepted |
| [ADR-003](ADR-003-llm-provider-chain-anthropic-deepseek-template.md) | LLM provider chain Anthropic → DeepSeek → template | accepted |
| [ADR-004](ADR-004-cloudflare-named-tunnel-for-public-exposure.md) | Cloudflare named tunnel for public exposure | accepted |
| [ADR-005](ADR-005-fastapi-websocket-dashboard-ui-is-logic-free.md) | FastAPI + WebSocket dashboard; UI is logic-free | accepted |
| [ADR-006](ADR-006-pydantic-schema-gates-on-every-ingress-and-egres.md) | pydantic schema gates on every ingress AND egress | accepted |
| [ADR-007](ADR-007-heuristic-expectimax-strategy-no-rl.md) | Heuristic/expectimax strategy; no RL | accepted |
| [ADR-008](ADR-008-event-sourced-observability.md) | Event-sourced observability | accepted |
| [ADR-009](ADR-009-one-apigatekeeper-class-per-service-instances.md) | One ApiGatekeeper class, per-service instances | accepted |
| [ADR-010](ADR-010-uv-ruff-pytest-toolchain-ci-as-compliance-robot.md) | uv + ruff + pytest toolchain, CI as compliance robot | imposed/accepted |
| [ADR-011](ADR-011-negotiation-playbook-adapter-profiles.md) | Negotiation playbook + adapter profiles | accepted |
| [ADR-012](ADR-012-golden-file-interop-tests-against-the-reference-.md) | Golden-file interop tests against the reference simulator | accepted |
| [ADR-013](ADR-013-no-email-receive-path-agreement-lives-on-mcp.md) | No email *receive* path; agreement lives on MCP | accepted |
| [ADR-014](ADR-014-static-type-checking-beyond-the-guidelines.md) | Static type checking beyond the guidelines | accepted |
| [ADR-015](ADR-015-announce-endings-rather-than-infer-them.md) | A peer announces an ending rather than letting the other infer it | accepted |
| [ADR-016](ADR-016-conservative-out-liberal-in-on-the-wire.md) | Conservative in what we send, liberal in what we accept | accepted |
| [ADR-017](ADR-017-fakes-must-not-be-kinder-than-the-wire.md) | A fake must not be kinder than the thing it stands in for | accepted |

ADR-015 onward were taken during construction; 001-014 were taken in the
design phase and are mirrored from `PLAN.md`.
