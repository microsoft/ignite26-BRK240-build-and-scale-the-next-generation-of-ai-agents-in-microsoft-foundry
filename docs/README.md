# Architecture

This page explains how the sample fits together and why it is built this way. For step-by-step setup, see [`instructions/`](../instructions/README.md).

All companies, people, deals and numbers in this sample are fictional.

## Components

```text
                    Microsoft Foundry project (one region that supports hosted agents and the harness)
                   ┌──────────────────────────────────────────────────────────────────────────────────────┐
  Seller request   │  caldova-deal-desk                          deal-economics                           │
  ───────────────▶ │  prompt agent, Microsoft Copilot harness    hosted agent, Microsoft Agent Framework  │
                   │  - instructions.md                          - agent.py + caldova_pricing             │
                   │  - skills: deal-intake, pricing-policy,     - tools: model_deal, deal_pnl_waterfall, │
                   │    counterproposal, approval-routing          check_margin_floor,                    │
                   │  - shell and file tools                       search_counter_scenarios,              │
                   │                                               price_protection_cost, fetch_url       │
                   │                                                                                      │
                   │  │ deal_economics (OpenAPI tool) ───────────▶ Responses endpoint                     │
                   │  │                                                                                   │
                   │  │ deal-desk-toolbox (MCP) ── deal-system connection (x-api-key) ──┐                 │
                   │                                                                    │                 │
                   │  Guardrail: Prompt Shields and a network egress allow-list         │                 │
                   │  Cost control: monthly budget, alert at 80%, block at 100%         │                 │
                   │  Evaluations and traces                                            │                 │
                   └────────────────────────────────────────────────────────────────────┼─────────────────┘
                                                                                        │ dev tunnel
                                                                                        ▼
                                                                    Deal System on your machine (http://localhost:8080)
                                                                    - MCP server at /mcp and REST API at /api
                                                                    - authority checks with caldova_pricing
                                                                    - approval page for Dana (VP Finance) and Morgan (CFO)
```

| Component | Type | Responsibility |
|---|---|---|
| [`caldova-deal-desk`](../src/deal-desk/README.md) | Foundry prompt agent on the Microsoft Copilot harness | Acts as the deal desk analyst. It reads the request, gathers the deal record, asks for the numbers, applies policy, proposes a counter and routes approval. |
| [`deal-economics`](../src/deal-economics/README.md) | Foundry hosted agent, Microsoft Agent Framework (Python) | Does all of the deal math with deterministic code: P&L waterfall, margin floor, scenario search and price protection cost. |
| [Deal System](../src/deal-system/README.md) | Local FastAPI app with an MCP server | System of record. It stores deals, enforces approval authority and hosts the human approval page. |
| [`caldova_pricing`](../src/pricing/README.md) | Python library | The pricing engine. Deal Economics and the Deal System both use it, so they always agree on the numbers. |
| [Guardrail and budget](../infra/README.md) | Foundry account settings | Prompt Shields, the egress allow-list and the cost control. |

## Two kinds of agent

The sample uses both agent types in Foundry Agent Service on purpose.

- **Copilot harness for judgment work.** Most of a deal desk analyst's job is policy, judgment and tool use. That can be written as instructions and skills, so Foundry runs the agent loop. You don't write or host agent code, and you can change the model or add a skill without a code change.
- **Hosted agent for code you own.** Finance-grade math must be deterministic, tested and versioned. Deal Economics is ordinary Python that you can unit test, run locally and debug in Agent Inspector, then deploy to the same runtime and governance with `azd deploy`.

The Deal Desk agent calls Deal Economics through its Responses endpoint, so the harness agent never computes margins itself.

## Authority is enforced by the system of record

The model doesn't decide whether a deal is approved. The Deal System does.

1. The Deal Desk agent calls `submit_decision` with the terms it wants to approve.
2. The Deal System recomputes the economics with `caldova_pricing` and checks the caller's authority. The agent can approve an effective rebate of up to 10%, payment terms up to Net-60, up to 12 months of price protection and co-marketing of up to 2% of contract value, and only if deal-life gross margin stays at or above 32%.
3. If the terms exceed that authority, the call returns `REQUIRES_HUMAN_APPROVAL` and names the approver: Dana (VP Finance) or Morgan (CFO).
4. The agent calls `request_approval`. The approver opens the approval page on the Deal System machine and approves or rejects.
5. The decision is written to the deal record. The approval token never reaches the agent, and `record_approval` always refuses agent callers, so the agent can't approve on a person's behalf.

## Governance controls

| Control | Where it's defined | What you see |
|---|---|---|
| Network egress | [`infra/guardrail.json`](../infra/guardrail.json) | The default action is Deny. A request from the hosted agent to a host that isn't on the allow-list, such as the benchmark link in the customer redline, gets HTTP 403. |
| Prompt Shields | [`infra/guardrail.json`](../infra/guardrail.json) | Jailbreak and indirect attack detection on user input and tool responses. |
| Budget | [`infra/budget.json`](../infra/budget.json) | A monthly USD limit on the project that alerts at 80% and blocks at 100%. |
| Human approval | [Deal System](../src/deal-system/README.md) | Terms beyond the agent's authority wait for a person. |
| Untrusted content | Agent instructions and skills | Customer documents are treated as data. The agents ignore instructions embedded in them and don't open links in them. |

## Data

[`data/generate.py`](../data/generate.py) builds every number in the sample from the pricing engine with a fixed seed, so results are repeatable. Northwind's ask (18% rebate, Net-90, 24 months of price protection and $1.2M of co-marketing) lands at 26.4% deal-life gross margin. The 24-month price freeze stops Caldova from passing on a forecast sensor-component cost increase, and that pushes the deal below the 32% floor. The top counter-offer is a 12% rebate plus a 2% growth kicker, Net-60, 12 months of price protection with a CPI cap and $900K of co-marketing tied to sell-through. It reaches 33.07% gross margin and keeps about 85% of the value Northwind asked for.

## What the sample simplifies

The sample is meant for learning, not production. In particular:

- **Local Deal System.** The Deal System is a local app with a JSON file for storage, exposed through a dev tunnel and protected by one shared API key. A production system of record would run as a managed service with Microsoft Entra authentication.
- **Simulated approvers.** Whoever uses the approval page chooses whether to act as Dana or Morgan. A real system would authenticate the approver.
- **Planning figures only.** The term sheet is an illustrative document, and nothing is sent to a customer.
