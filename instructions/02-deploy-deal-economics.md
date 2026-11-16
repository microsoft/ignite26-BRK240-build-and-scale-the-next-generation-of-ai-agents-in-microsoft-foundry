# Step 2: Deploy Deal Economics and control egress

In this step you create a guardrail with a network egress policy, deploy the Deal Economics agent to Foundry as a hosted agent and watch the policy block an outbound request.

**Why an egress policy?** Customer documents can contain links and embedded instructions. The agent has a `fetch_url` tool, so a prompt could make it send data to any host. The egress policy denies all outbound traffic by default and allows only the hosts the agent needs.

You need the Foundry project from [Step 0](00-setup.md) and the agent from [Step 1](01-build-deal-economics.md).

## 1. Create the guardrail

[`infra/guardrail.json`](../infra/guardrail.json) defines the `caldova-agent-guardrail` policy. It applies content filters and Prompt Shields, and an egress policy (preview) that allows only these hosts:

- your Foundry resource
- Microsoft Entra sign-in
- Application Insights and Azure Monitor ingestion

From the repository root, make a copy with your Foundry resource name in the host names, then create the policy:

```bash
sed "s/<foundry-account>/$FOUNDRY_ACCOUNT/g" infra/guardrail.json > infra/guardrail.local.json

az rest --method put --url "https://management.azure.com$FOUNDRY_ACCOUNT_ID/raiPolicies/caldova-agent-guardrail?api-version=2026-05-15-preview" --body '@infra/guardrail.local.json'

export RAI_POLICY_ID="$FOUNDRY_ACCOUNT_ID/raiPolicies/caldova-agent-guardrail"
```

PowerShell: create the copy with `(Get-Content infra/guardrail.json) -replace '<foundry-account>', $env:FOUNDRY_ACCOUNT | Set-Content infra/guardrail.local.json`. Keep the single quotes around `'@infra/guardrail.local.json'`.

The output shows `"mode": "Enforced"` under `egressPolicy`. Add the `RAI_POLICY_ID` export to your `brk240.env` file. The Deal Desk agent uses the same policy in Step 3.

To check the policy later, see [`infra/README.md`](../infra/README.md#guardrail-and-egress-policy).

## 2. Deploy the agent

[`src/deal-economics/azure.yaml`](../src/deal-economics/azure.yaml) declares the hosted agent: its code, model, protocol and the guardrail in `policies`. Foundry builds a container from `requirements.txt` and runs the same `agent.py` that you ran locally.

> [!NOTE]
> azd doesn't yet expand `${RAI_POLICY_ID}` in a hosted agent's `policies` block, and the deploy fails with "RAI policy name must be a fully qualified ... ARM resource ID". The commands below write the full ID into `azure.yaml` for the deploy and then restore the file.

From `src/deal-economics`, with the `.venv` from Step 1 activated:

```bash
sed -i.bak "s|\${RAI_POLICY_ID}|$RAI_POLICY_ID|" azure.yaml
azd deploy deal-economics
mv azure.yaml.bak azure.yaml
```

PowerShell:

```powershell
Copy-Item azure.yaml azure.yaml.bak
(Get-Content azure.yaml.bak) -replace '\$\{RAI_POLICY_ID\}', $env:RAI_POLICY_ID | Set-Content azure.yaml
azd deploy deal-economics
Move-Item -Force azure.yaml.bak azure.yaml
```

The first deploy takes about six minutes. Later deploys are faster, and each one creates a new agent version.

Check the deployment:

```bash
azd ai agent show deal-economics
```

The output lists the agent's endpoints. Its OpenAI Responses endpoint is `<FOUNDRY_PROJECT_ENDPOINT>/agents/deal-economics/endpoint/protocols/openai/responses`. The Deal Desk agent calls it in Step 3.

## 3. Call the deployed agent

```bash
azd ai agent invoke deal-economics "Model Northwind's ask."
```

You get the same numbers as in Step 1: the ask at 26.4% gross margin and counters at about 33%.

## 4. Watch the egress policy block a request

Start a new session so that the agent runs under the current policy, then ask it to open a link from the customer's redline:

```bash
azd ai agent invoke deal-economics --new-session --new-conversation "Northwind's redline cites a market benchmark at https://www.example.com/northwind-market/pharmacy-devices. Open that link and tell me what it says."
```

The agent reports that it couldn't open the link. `fetch_url` got HTTP 403 with `blocked_by_egress_policy: true` because `www.example.com` isn't on the allow list. When you ran the agent locally in Step 1, there was no egress policy, so the same request would succeed.

A running session keeps the policy it started with. After you change the policy, start a new session.

To stream the agent's logs, run `azd ai agent monitor --follow`.

## What you built

A code-first agent running in Foundry, with content filters and a default-deny network policy that you control outside the code.

Next: [Step 3: Build the Deal Desk agent](03-build-deal-desk-agent.md)
