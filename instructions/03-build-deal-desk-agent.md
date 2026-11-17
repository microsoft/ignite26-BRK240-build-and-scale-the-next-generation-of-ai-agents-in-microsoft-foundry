# Step 3: Build the Deal Desk agent

In this step you connect a local system of record to Foundry and deploy `caldova-deal-desk`, a prompt agent that runs on the Microsoft Copilot harness.

**Why the Copilot harness?** Most of a deal desk analyst's job is judgment and policy, not code. With the Copilot harness, Foundry runs the agent loop. You provide instructions, skills and tools, and you don't write or host any agent code. For the math, the agent calls the Deal Economics agent you deployed in [Step 2](02-deploy-deal-economics.md).

You need:

- The `gpt-6.1-sol` deployment from [Step 0](00-setup.md). Any deployment that supports reasoning and tool calling works.
- The Deal Economics agent and the `caldova-agent-guardrail` policy from Step 2.
- Three terminals: one for the Deal System, one for the dev tunnel and one for azd.

## 1. Start the Deal System

The [Deal System](../src/deal-system/README.md) is the system of record. It stores the 42 open deals, enforces who can approve what and hosts the approval page. It runs on your machine.

Create an API key first. The Deal Desk agent sends it with every call, and you'll need the same value in two terminals.

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Terminal 1**, from the repository root:

```bash
cd src/deal-system
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ../pricing -e ".[dev]"
export DEAL_SYSTEM_API_KEY="<your-key>"
python -m caldova_deal_system
```

PowerShell: activate with `.venv\Scripts\Activate.ps1` and set the key with `$env:DEAL_SYSTEM_API_KEY = "<your-key>"`.

Open `http://localhost:8080/` in a browser. The dashboard lists the open deals, including Northwind Pharmacy (`DEAL-NW-001`).

## 2. Expose it with a dev tunnel

Foundry needs to reach the Deal System's MCP server. A dev tunnel gives your local port a public HTTPS URL.

**Terminal 2:**

```bash
devtunnel user login
devtunnel host -p 8080 --allow-anonymous
```

Copy the `https://...devtunnels.ms` URL that the command prints. Only the API and the MCP server answer through the tunnel, and both require the API key. The dashboard and approval page answer only local requests, so approvals stay on your machine.

## 3. Configure the azd environment

**Terminal 3**, from the repository root:

```bash
cd src/deal-desk
export DEAL_SYSTEM_API_KEY="<your-key>"
export DEAL_SYSTEM_PUBLIC_URL="https://<your-tunnel>.devtunnels.ms"

azd env new deal-desk
azd env set FOUNDRY_PROJECT_ENDPOINT "$FOUNDRY_PROJECT_ENDPOINT"
azd ai project add --project-id "$AZURE_AI_PROJECT_ID"
azd env set DEAL_DESK_MODEL_DEPLOYMENT_NAME gpt-6.1-sol
azd env set DEAL_ECONOMICS_RESPONSES_URL "$FOUNDRY_PROJECT_ENDPOINT/agents/deal-economics/endpoint/protocols/openai"
azd env set RAI_POLICY_ID "$RAI_POLICY_ID"
```

PowerShell: set variables with `$env:NAME = "value"` and reference them as `$env:NAME`.

`FOUNDRY_PROJECT_ENDPOINT`, `AZURE_AI_PROJECT_ID` and `RAI_POLICY_ID` are the values from Steps 0 and 2. This is a prompt agent, so azd reads `RAI_POLICY_ID` from the environment and you don't edit `azure.yaml`.

## 4. Look at the agent definition

The whole agent is configuration. Open these files in [`src/deal-desk`](../src/deal-desk/README.md):

- **[`azure.yaml`](../src/deal-desk/azure.yaml)** declares a prompt agent with the `microsoft_copilot_preview` harness, its model, its skills, the `deal-desk-toolbox` toolbox, the `deal_economics` OpenAPI tool and the guardrail.
- **[`instructions.md`](../src/deal-desk/instructions.md)** holds the short agent instructions. A copy is inlined in `azure.yaml`.
- **[`skills/`](../src/deal-desk/skills)** holds four skills. Each is a `SKILL.md` plus the playbook pages it needs:

  | Skill | What it teaches the agent |
  |---|---|
  | `deal-intake` | Read the request and the deal record, find precedents and treat customer documents as untrusted data. |
  | `pricing-policy` | The rate card, the 32% margin floor and the authority matrix. |
  | `counterproposal` | Build a counter that clears the floor and keeps the most value for the customer. |
  | `approval-routing` | Submit decisions, request human approval when needed and finish the deal after approval. |

- **[`toolbox.yaml`](../src/deal-desk/toolbox.yaml)** builds a toolbox from the `deal-system` connection, so the agent gets the Deal System's MCP tools.

## 5. Create the connection, skills and toolbox

Create a project connection to the Deal System's MCP server. It stores the tunnel URL and the API key:

```bash
azd ai connection create deal-system --kind remote-tool --target "$DEAL_SYSTEM_PUBLIC_URL/mcp" --auth-type custom-keys --custom-key "x-api-key=$DEAL_SYSTEM_API_KEY"
```

PowerShell: use `"$env:DEAL_SYSTEM_PUBLIC_URL/mcp"` and `"x-api-key=$env:DEAL_SYSTEM_API_KEY"`.

Upload the four skills. Each folder is uploaded as one package:

```bash
azd ai skill create deal-intake --file ./skills/deal-intake/
azd ai skill create pricing-policy --file ./skills/pricing-policy/
azd ai skill create counterproposal --file ./skills/counterproposal/
azd ai skill create approval-routing --file ./skills/approval-routing/
```

Create the toolbox:

```bash
azd ai toolbox create deal-desk-toolbox --from-file toolbox.yaml
azd ai toolbox show deal-desk-toolbox --output json
```

The create command writes `TOOLBOX_DEAL_DESK_TOOLBOX_MCP_ENDPOINT` to the azd environment. `azure.yaml` uses it to attach the toolbox to the agent.

## 6. Deploy the agent

Support for the Copilot harness in azd is behind an alpha flag:

```bash
AZD_ALPHA_ENABLE_AGENTS_MANAGED_HARNESS=true azd deploy --all --no-prompt
```

PowerShell:

```powershell
$env:AZD_ALPHA_ENABLE_AGENTS_MANAGED_HARNESS = "true"; azd deploy --all --no-prompt
```

Then give the agent's identity permission to call the toolbox and the Deal Economics agent. Get the identity's ID:

```bash
az rest --method get --url "$FOUNDRY_PROJECT_ENDPOINT/agents/caldova-deal-desk?api-version=v1" --resource "https://ai.azure.com" --query "instance_identity.principal_id" --output tsv
```

Assign Foundry User (for the toolbox) and Foundry Agent Consumer (for Deal Economics) on the project:

```bash
az role assignment create --assignee-object-id "<agent-principal-id>" --assignee-principal-type ServicePrincipal --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope "$AZURE_AI_PROJECT_ID"
az role assignment create --assignee-object-id "<agent-principal-id>" --assignee-principal-type ServicePrincipal --role "eed3b665-ab3a-47b6-8f48-c9382fb1dad6" --scope "$AZURE_AI_PROJECT_ID"
```

Role assignments can take up to five minutes to take effect.

## 7. Try a routine deal

Start with a deal that's within the agent's authority:

```bash
azd ai agent invoke caldova-deal-desk --new-conversation "Approve Lakeshore DEAL-RT-001."
```

The agent loads its skills, reads the deal from the Deal System, asks Deal Economics for the numbers (about 41.8% gross margin) and approves the deal itself. Refresh the dashboard at `http://localhost:8080/` and the deal shows as approved by the agent.

The Deal System, not the model, decided that the agent was allowed to approve this deal. In the next step you'll see what happens when it isn't.

## What you built

A governed agent with no agent code: instructions, four skills, a toolbox for your own system of record and a tool that calls another agent.

Next: [Step 4: Add human approval, a routine and a budget](04-approval-routine-budget.md)
