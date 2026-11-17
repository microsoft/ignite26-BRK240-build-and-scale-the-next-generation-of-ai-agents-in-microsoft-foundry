<a name="start-building"></a>

<p align="center">
<img src="img/banner-ignite-26.png" alt="Microsoft Ignite 2026" width="100%"/>
</p>

# [Microsoft Ignite 2026](https://ignite.microsoft.com)

## 🔥BRK240: Build and scale the next generation of AI agents in Microsoft Foundry

### Session description

Agents are moving from prototypes to production. This session follows one agent journey through Microsoft Foundry: build, deploy, operate. You build a deal desk agent with your choice of framework and the Microsoft Copilot harness, connect it to tools through a toolbox, and deploy it with network egress, budget and approval controls. Then you evaluate it and improve it from its traces. This repository contains the sample from the demo so you can run each step yourself.

### The scenario

Caldova, a fictional consumer-health device maker, gets a non-standard request from its biggest retail prospect, Northwind Pharmacy: an 18% volume rebate, Net-90 payment terms, 24 months of price protection and $1.2M of co-marketing on a $48M, three-year deal. Today a deal desk analyst spends days rebuilding the P&L in a spreadsheet. In this sample, two agents produce a decision in minutes:

- **Deal Economics** is a hosted agent built with Microsoft Agent Framework. A deterministic Python pricing engine does the math: P&L waterfall, margin-floor check and a search over thousands of counter-offer term combinations. The ask lands at 26.4% gross margin, below the 32% floor, and the agent proposes counters near 33%.
- **Caldova Deal Desk** is a Foundry prompt agent that runs on the Microsoft Copilot harness. Instructions, four skills and a toolbox make it a deal desk analyst. It reads the deal, asks Deal Economics for the numbers, recommends a counter and routes approval.
- **Deal System** is a small local system of record exposed over MCP. It enforces approval authority. When the agent tries to approve terms beyond its authority, the call returns `REQUIRES_HUMAN_APPROVAL`, and a person (Dana, VP Finance) approves the deal in a browser page before the record changes.

All companies, people, deals and numbers in this repository are fictional.

```text
             ┌───────────────────────── Microsoft Foundry project ─────────────────────────┐
  "Review    │  caldova-deal-desk (prompt agent, Microsoft Copilot harness)                │
   Priya's   │    instructions + skills: deal-intake, pricing-policy,                      │
   Northwind │    counterproposal, approval-routing                                        │
   request." │      │ OpenAPI tool                      │ deal-desk-toolbox (MCP)          │
  ──────────▶│      ▼                                   ▼                                  │
             │  deal-economics (hosted agent,       deal-system connection ───────────────┼──▶ Deal System (your machine,
             │  Microsoft Agent Framework)                                                 │     via dev tunnel): MCP + approval page
             │                                                                             │
             │  Controls: egress allow-list, Prompt Shields, budget, evals, traces         │
             └─────────────────────────────────────────────────────────────────────────────┘
```

### What's in this repository

| Path | What it is |
|------|------------|
| [`instructions/`](instructions/README.md) | Step-by-step guide: build, deploy, operate |
| [`src/deal-economics/`](src/deal-economics/README.md) | Deal Economics hosted agent (Microsoft Agent Framework, Python), evals and egress policy |
| [`src/deal-desk/`](src/deal-desk/README.md) | Caldova Deal Desk harness agent: instructions, skills, toolbox and routine |
| [`src/deal-system/`](src/deal-system/README.md) | Local Deal System: REST API, MCP server and human approval page |
| [`src/pricing/`](src/pricing/README.md) | `caldova_pricing`, the deterministic pricing engine |
| [`infra/`](infra/README.md) | Guardrail (Prompt Shields and network egress) and budget definitions |
| [`data/`](data/README.md) | Synthetic deal data, the seller email and the customer redline |
| [`docs/`](docs/README.md) | Architecture and design notes |

### 🚀 Getting started

#### In a guided session

If you're following along during a live session:

1. Watch the Build, Deploy and Operate demos.
2. Clone this repository and open [`instructions/`](instructions/README.md) to repeat each step in your own Foundry project.

#### On your own

If you're learning at your own pace:

1. Clone this repository.
2. Complete the prerequisites in [`instructions/00-setup.md`](instructions/00-setup.md).
3. Follow the guides in order, starting with [`instructions/01-build-deal-economics.md`](instructions/01-build-deal-economics.md).

You can stop after the first guide: running Deal Economics locally needs only a Foundry project with a model deployment.

### 🎯 Learning outcomes

By the end of this session, you will be able to:

- Build an agent with Microsoft Agent Framework, debug it locally in Agent Inspector and deploy it as a Foundry hosted agent with the Azure Developer CLI.
- Create a Microsoft Copilot harness agent from instructions, skills and a toolbox that connects MCP tools and other agents.
- Govern agents in production with network egress rules, budgets, guardrails and human approval enforced by your system of record, and measure them with evaluations and traces.

### 💻 Technologies used

- Microsoft Foundry Agent Service: hosted agents, prompt agents with the Microsoft Copilot harness, toolboxes, skills, routines, guardrails and cost controls
- Microsoft Agent Framework (Python)
- Azure Developer CLI (`azd`) with the `azure.ai.*` extensions
- Model Context Protocol (MCP)
- Foundry evaluations and tracing (OpenTelemetry and Application Insights)
- Microsoft Dev Tunnels

### 📚 Continue your learning

Pick your next step based on your learning style:

| Resource | What you'll get |
|----------|-----------------|
| **[Ignite 2026 Next Steps](https://aka.ms/ignite26-next-steps)** | Additional session repos and materials from Microsoft Ignite 2026 |
| **[Microsoft AI Skills Navigator](https://aka.ms/ignite26-asn)** | Discover AI skills, learning paths, and resources for your next step |
| **[Microsoft Learn](https://aka.ms/ignite26-learn)** | Official documentation and guided learning paths on these topics |
| **[Microsoft Foundry Community](https://aka.ms/MicrosoftFoundryDiscord-Ignite26)** | Connect with other learners and experts in our Discord community |

### 🌟 Microsoft Learn MCP Server

The Microsoft Learn MCP Server gives your AI agent direct access to Microsoft's official documentation — grounded, up-to-date answers about the topics in this session.

**GitHub Copilot CLI** — Install with:

```shell
copilot plugin install microsoftdocs/mcp
```

**VS Code** — One-click install:  
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Microsoft_Learn_MCP-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=microsoft-learn&config=%7B%22type%22%3A%22http%22%2C%22url%22%3A%22https%3A%2F%2Flearn.microsoft.com%2Fapi%2Fmcp%22%7D)

For more information, visit the [Learn MCP Server repo](https://aka.ms/learnmcp).

### 👥 Content owners

<table>
<tr>
    <td align="center"><a href="http://github.com/jeffhollan">
        <img src="https://github.com/jeffhollan.png" width="100px;" alt="Jeff Hollan"/><br />
        <sub><b>Jeff Hollan</b></sub></a><br />
            <a href="https://github.com/jeffhollan" title="talk">📢</a>
    </td>
</tr></table>

### ⚖️ Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft trademarks or logos is subject to and must follow [Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general). Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.

Any use of third-party trademarks or logos are subject to those third-party's policies.
