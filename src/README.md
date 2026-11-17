# Source

| Folder | Component | Runs |
|--------|-----------|------|
| [`deal-economics/`](deal-economics/README.md) | Deal Economics agent (Microsoft Agent Framework, Python) | Locally with `azd ai agent run`, then as a Foundry hosted agent |
| [`deal-desk/`](deal-desk/README.md) | Caldova Deal Desk agent (prompt agent on the Microsoft Copilot harness) | In Foundry |
| [`deal-system/`](deal-system/README.md) | Deal System: system of record with a REST API, an MCP server and a human approval page | On your machine, exposed to Foundry through a dev tunnel |
| [`pricing/`](pricing/README.md) | `caldova_pricing`, the deterministic pricing engine shared by Deal Economics and the Deal System | As a library |

The step-by-step guide in [`instructions/`](../instructions/README.md) shows how the pieces fit together.
