# Deal Economics agent

A hosted agent built with Microsoft Agent Framework (Python) and deployed to Microsoft Foundry. It answers
deal-economics questions for Caldova's deal desk: P&L waterfall, gross margin (GM) against the 32% floor,
ranked counter-offers and the cost of price protection.

The model never does the math. Every figure comes from the deterministic `caldova_pricing` engine
([../pricing](../pricing)) through the tools below. The model picks the tools and explains the results. The
agent serves the Responses protocol, so the Deal Desk agent ([../deal-desk](../deal-desk)) or any other
client can call it.

All companies, people and numbers in this sample are fictional.

## Tools

| Tool | What it returns |
|---|---|
| `model_deal` | Runs the next three tools concurrently for one deal and set of terms. |
| `deal_pnl_waterfall` | Contract P&L waterfall: list revenue, rebates, MDF, COGS, financing, deal margin and GM. |
| `check_margin_floor` | GM vs the 32% floor, the GM cost of each concession and the required approver. |
| `search_counter_scenarios` | The top 3 counter-offers that clear the floor, with P10 GM and the share of customer value kept. |
| `price_protection_cost` | The component-cost increase that N months of price protection leaves unrecovered. |
| `fetch_url` | Fetches a link from a customer document as untrusted content. Hosted, the egress policy governs it. |

## Files

| Path | Purpose |
|---|---|
| `agent.py` | The agent, its tools and the Responses host. |
| `.agent_configs/baseline/` | Instructions, tool descriptions and the default model (`metadata.yaml`). |
| `caldova_pricing/`, `deal_register.json` | Copies of the pricing engine and the deal inputs. A deploy packages only this folder, so these copies ship with it. |
| `sync_vendor.py` | Refreshes those copies from `../pricing` and `../../data/generated`. |
| `azure.yaml` | azd project: the Foundry project, the hosted agent and the eval. |
| `eval.yaml`, `datasets/` | Eval `deal-economics-golden`. |
| `infra/egress-policy.json` | Guardrail with the network egress policy. |
| `tests/` | Tool tests. They make no model calls. |

## Prerequisites

- Python 3.12 or later. The hosted runtime is Python 3.13.
- Azure CLI, signed in with `az login`.
- Azure Developer CLI (azd) 1.37.0 or later with the Foundry extensions: `azd extension install microsoft.foundry azure.ai.evaluations`.
- A Foundry project with a model deployment, `gpt-5.5` by default, plus a `gpt-5.4-mini` deployment for the
  eval judge. You need the Foundry User role (formerly Azure AI User) on the Foundry account or project.

## Set up

The commands are the same in bash and PowerShell, except where a PowerShell line is shown in a comment.

```bash
cd src/deal-economics
python -m venv .venv
source .venv/bin/activate              # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cp .env.example .env                   # PowerShell: Copy-Item .env.example .env
```

In `.env`, set `FOUNDRY_PROJECT_ENDPOINT` to your project endpoint
(`https://<foundry-account>.services.ai.azure.com/api/projects/<project>`). Set
`AZURE_AI_MODEL_DEPLOYMENT_NAME` to your model deployment name.

Create an azd environment with the same values:

```bash
azd env new deal-economics
azd env set FOUNDRY_PROJECT_ENDPOINT https://<foundry-account>.services.ai.azure.com/api/projects/<project>
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-5.5
azd ai project add --project-id /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/projects/<project>
```

`azd ai project add` links the environment to your existing project and sets `AZURE_AI_PROJECT_ID`,
`AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP` and `AZURE_LOCATION`. Without it, `azd deploy` fails with
"infrastructure has not been provisioned". To get the project ID, run
`az cognitiveservices account project show -n <foundry-account> -g <resource-group> --project-name <project> --query id -o tsv`.

## Run locally

Run the agent in Agent Inspector:

```bash
azd ai agent run
```

Run it with the `.venv` from Set up activated. This starts the agent on http://localhost:8088 and opens Agent Inspector. Type `Model Northwind's ask.`.
The answer should show:

- The ask at 26.4% GM, below the 32% floor, so Morgan (CFO) must approve it.
- The waterfall and the GM bridge.
- Three counter-offers at about 33% GM, which Dana (VP Finance) can approve.

The Traces tab shows `model_deal` and the three tool calls it runs.

To run without the Inspector, start the agent in one terminal and invoke it from a second terminal:

```bash
azd ai agent run --no-client
azd ai agent invoke --local "Model Northwind's ask."
```

If port 8088 is in use, pass `-p <port>` to `run` and `--port <port>` to `invoke` (for `invoke`, `-p` is the
protocol).

Or start the agent with plain Python and call its Responses endpoint:

```bash
python agent.py
curl -s http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Model the Northwind ask."}'
```

The PowerShell equivalent of the `curl` call:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8088/responses -ContentType "application/json" -Body '{"input": "Model the Northwind ask."}'
```

The model is `AZURE_AI_MODEL_DEPLOYMENT_NAME` if it is set, otherwise the one in
`.agent_configs/baseline/metadata.yaml`. Reasoning effort is set to low to keep answers fast.

## Network egress policy

The hosted agent runs under the guardrail `caldova-agent-guardrail`. It is defined in
[infra/egress-policy.json](infra/egress-policy.json). The guardrail applies the default content filters and
an egress policy (preview) that denies all outbound traffic by default. It allows only these hosts:

- your Foundry account
- Microsoft Entra sign-in
- Application Insights and Azure Monitor ingestion

The same body is in [../../infra/guardrail.json](../../infra/guardrail.json).

Apply the guardrail before you deploy. The agent references it, so the first deploy fails without it.

1. Make a copy of the JSON with `<foundry-account>` replaced by your Foundry account name, for example
   `sed 's/<foundry-account>/<your-account>/' infra/egress-policy.json > egress-policy.local.json`.
2. Create or update the guardrail:

   ```bash
   az rest --method put --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/raiPolicies/caldova-agent-guardrail?api-version=2026-05-15-preview" --body "@egress-policy.local.json"
   ```

3. Point the agent at it:

   ```bash
   azd env set RAI_POLICY_ID /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/raiPolicies/caldova-agent-guardrail
   ```

To see the policy work, start a new session with the deployed agent (`azd ai agent invoke deal-economics
--new-session --new-conversation "..."`) and ask:

> Northwind's redline cites a market benchmark at https://www.example.com/northwind-market/pharmacy-devices.
> Open that link and tell me what it says.

`fetch_url` gets HTTP 403 with an `x-deny-reason` header and reports `blocked_by_egress_policy: true`. The
trace includes the platform's egress decision. When you run locally there is no egress policy, so the same
fetch succeeds. A running session keeps its old policy; only a new session picks up a change.

## Deploy

Set `RAI_POLICY_ID` first (see [Network egress policy](#network-egress-policy)).

> [!NOTE]
> With `azure.ai.agents` 1.1.0, azd does not expand `${RAI_POLICY_ID}` in the hosted agent's `policies`
> block, and the deploy fails with "RAI policy name must be a fully qualified ... raiPolicies ARM resource ID".
> Until that is fixed, replace `${RAI_POLICY_ID}` in `azure.yaml` with the full guardrail ID before you
> deploy, and don't commit the change.

```bash
azd deploy deal-economics
azd ai agent invoke deal-economics "Model Northwind's ask."
azd ai agent monitor --follow
```

Each deploy creates a new agent version. Foundry builds the code package remotely from `requirements.txt`.
`azd ai agent show deal-economics` shows the agent's endpoints.

The Deal Desk agent calls this agent through its Responses endpoint,
`<FOUNDRY_PROJECT_ENDPOINT>/agents/deal-economics/endpoint/protocols/openai/responses?api-version=v1`. For
[../deal-desk](../deal-desk), set `DEAL_ECONOMICS_RESPONSES_URL` to the base URL without `/responses` and
without the query: `<FOUNDRY_PROJECT_ENDPOINT>/agents/deal-economics/endpoint/protocols/openai`. The caller
needs a token for `https://ai.azure.com`. To test it:

```bash
curl -s "<FOUNDRY_PROJECT_ENDPOINT>/agents/deal-economics/endpoint/protocols/openai/responses?api-version=v1" \
  -H "Authorization: Bearer $(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)" \
  -H "Content-Type: application/json" -d '{"input": "Model Northwind'\''s ask."}'
```

## Evaluate

[eval.yaml](eval.yaml) defines the eval `deal-economics-golden`. It covers 16 questions in
[datasets/deal-economics-eval.jsonl](datasets/deal-economics-eval.jsonl):

- Northwind
- price protection
- a routine deal
- historical cases, including price-protection and MDF traps
- a prompt-injection refusal

The pricing engine computed the ground truth. The evaluators are task completion and task adherence. They use a `gpt-5.4-mini` judge deployment.

```bash
azd deploy deal-economics-evals
azd ai eval run start --eval deal-economics-golden
```

## Test

```bash
python -m pytest tests -q
python sync_vendor.py --check
```

After you change `../pricing/caldova_pricing` or regenerate `../../data/generated`, run
`python sync_vendor.py` to refresh the copies.
