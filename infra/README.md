# Governance

Two account-level controls for the Foundry resource that hosts both agents. azd doesn't deploy them, so you apply each one with `az rest`.

| File | Resource | What it does |
|---|---|---|
| [`guardrail.json`](guardrail.json) | RAI policy `caldova-agent-guardrail` | Applies content filters and Prompt Shields, both blocking. Jailbreak detection checks user input. Indirect attack detection checks user input and tool responses. Also enforces a network egress allow-list with a default of Deny. |
| [`budget.json`](budget.json) | Cost control `caldova-dealdesk-budget` (preview) | Sets a monthly USD limit for one project. Alerts at 80% and blocks at 100%. |
| [`budget-attach.json`](budget-attach.json) | Foundry account | Attaches the cost control to the account. |

All names and numbers are fictional sample values.

## Before you start

- **Azure CLI.** Install the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and run `az login`.
- **Permissions.** You need Owner or Contributor on the Foundry resource.
- **Placeholders.** Replace `<subscription-id>`, `<resource-group>`, `<foundry-account>` and `<project>` in the commands below. The egress allow-list in `guardrail.json` uses `<foundry-account>` for your Foundry resource host names. Rather than edit the tracked file, write a filled-in copy, which git ignores:

  ```
  sed "s/<foundry-account>/<your-foundry-account>/g" infra/guardrail.json > infra/guardrail.local.json
  ```

  In PowerShell: `(Get-Content infra/guardrail.json) -replace '<foundry-account>', '<your-foundry-account>' | Set-Content infra/guardrail.local.json`.
- **Shells.** Each command is one line and works in bash, zsh and PowerShell. Run the commands from the repository root. Keep the single quotes around `'@infra/...'`; PowerShell treats an unquoted `@` as splatting.

## Guardrail and egress policy

1. Create or replace the policy. A PUT replaces the whole policy, including `egressPolicy`.

   ```
   az rest --method put --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/raiPolicies/caldova-agent-guardrail?api-version=2026-05-15-preview" --body '@infra/guardrail.local.json'
   ```

2. Verify the policy:

   ```
   az rest --method get --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/raiPolicies/caldova-agent-guardrail?api-version=2026-05-15-preview" --query "{egress:properties.egressPolicy.mode, default:properties.egressPolicy.defaultAction, hosts:properties.egressPolicy.rules[].match.host, shields:properties.contentFilters[?name=='Jailbreak' || name=='Indirect Attack'].[name, source, blocking]}"
   ```

3. Both agents bind the policy by its full ARM ID through the `RAI_POLICY_ID` azd environment variable. Set it:

   ```
   azd env set RAI_POLICY_ID "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/raiPolicies/caldova-agent-guardrail"
   ```

   azd expands `${RAI_POLICY_ID}` for the Deal Desk prompt agent. It doesn't yet expand it in a hosted agent's `policies` block, so for Deal Economics write the full ID into `azure.yaml` for the deploy and then restore the file. [Step 2](../instructions/02-deploy-deal-economics.md#2-deploy-the-agent) shows the commands.

4. After `azd deploy`, run `azd ai agent show <agent> --output json`. Check that the output shows the same ID in `rai_config.rai_policy_name`.

Notes:

- **Matching policy body.** [`src/deal-economics/infra/egress-policy.json`](../src/deal-economics/infra/egress-policy.json) contains the same policy body as `guardrail.json`. Keep the two files identical so that one PUT doesn't strip the other file's rules.
- **Same resource.** The policy must live on the same Foundry resource as the project.
- **What egress covers.** Egress rules govern direct outbound traffic from the Copilot harness, such as shell `curl`, and from the hosted agent. Requests to any host that isn't on the list, including the link in the sample redline, get HTTP 403.
- **Policy changes.** A running harness session doesn't reload policy changes. Start a new conversation after a change.
- **Audit mode.** To discover which hosts an agent needs, set `egressPolicy.mode` to `Audit` first.

For more information, see [Control network egress](https://learn.microsoft.com/azure/foundry/agents/how-to/use-tools-skills-copilot-harness#control-network-egress) and [Prompt Shields](https://learn.microsoft.com/azure/ai-services/content-safety/concepts/jailbreak-detection).

## Budget (preview)

1. Create the cost control:

   ```
   az rest --method put --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/costControls/caldova-dealdesk-budget?api-version=2026-09-15-preview" --body '@infra/budget.json'
   ```

2. Attach the cost control to the account. It has no effect until you attach it.

   ```
   az rest --method patch --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>?api-version=2026-09-15-preview" --body '@infra/budget-attach.json'
   ```

3. Verify the cost control and the attachment:

   ```
   az rest --method get --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/costControls/caldova-dealdesk-budget?api-version=2026-09-15-preview" --query "properties.rules[0].{amount:amount, period:period, thresholds:thresholds}"
   az rest --method get --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>?api-version=2026-09-15-preview" --query "properties.costControlIds"
   ```

Notes:

- **Alert threshold.** If an attached cost control contains an `Alert` action, the attach fails with `Property 'costControlConnections.eventGridConnectionId' must be configured on account`. To fix it, either configure an Event Grid connection on the account, or delete the 80% `Alert` entry from `budget.json` and rerun steps 1 and 2. For email alerts, use an [Azure Cost Management budget](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets) instead.
- **Blocking.** At 100%, the project's requests are blocked. To unblock, either raise `amount` and rerun step 1, or set `"costControlIds": []` in `budget-attach.json` and rerun step 2 to detach the cost control.
- **Template redeploys.** If you redeploy the Foundry account from a template, rerun step 2. The redeploy can reset `costControlIds`.
- **Preview APIs.** Cost controls are in preview. The Azure CLI also has a preview [`az cognitiveservices account costcontrol`](https://learn.microsoft.com/cli/azure/cognitiveservices/account/costcontrol) command group, which uses a newer schema than `budget.json`.
