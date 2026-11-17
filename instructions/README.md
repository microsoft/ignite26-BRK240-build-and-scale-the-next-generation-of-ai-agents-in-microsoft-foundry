# Step-by-step guide

These guides rebuild the BRK240 demo in your own Azure subscription. Follow them in order. Each guide ends in a working state, so you can stop after any step.

| Step | Guide | Demo act | What you end up with |
|------|-------|----------|----------------------|
| 0 | [Set up your environment](00-setup.md) | | Tools installed and a Foundry project with model deployments |
| 1 | [Build the Deal Economics agent](01-build-deal-economics.md) | Build | A Microsoft Agent Framework agent running locally in Agent Inspector |
| 2 | [Deploy Deal Economics and control egress](02-deploy-deal-economics.md) | Deploy | A hosted agent in Foundry that can't reach hosts outside its allow-list |
| 3 | [Build the Deal Desk agent](03-build-deal-desk-agent.md) | Build | A Copilot harness agent with skills and a toolbox, connected to the Deal System |
| 4 | [Add human approval, a routine and a budget](04-approval-routine-budget.md) | Deploy | Escalated deals approved by a person, a scheduled sweep and a cost limit |
| 5 | [Evaluate and observe](05-evaluate-and-observe.md) | Operate | An evaluation run, traces and Insights for your agents |
| 6 | [Clean up](06-clean-up.md) | | Azure resources removed |

## Before you begin

- **Costs.** The guides create billable Azure resources: model deployments, hosted agent compute and evaluation runs. Step 6 shows how to remove them.
- **Preview features.** The Copilot harness, toolboxes, skills, routines, egress policies and cost controls are in preview. Commands and portal pages can change. If a command fails, check the linked Microsoft Learn page and `azd <command> --help`.
- **Fictional data.** Caldova, Northwind Pharmacy and every person, deal and number in this repository are fictional.
- **Shells.** Commands are shown for bash. Where PowerShell differs, both forms are shown.
