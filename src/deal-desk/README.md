# Caldova Deal Desk agent

`caldova-deal-desk` is a Foundry prompt agent that runs on the Microsoft Copilot harness (preview). It turns a seller's non-standard deal request into a governed decision:

- It reads the request from the user's message and the deal record from the Caldova Deal System.
- It gets all margin math from the hosted Deal Economics agent.
- It checks the result against the pricing playbook.
- It records the decision itself when the decision is within its authority.
- When the decision is outside its authority, it routes a decision-ready counter to a human approver.

All companies, people and numbers are fictional.

| Path | Purpose |
|---|---|
| `azure.yaml` | azd project with three services: the existing Foundry project, the toolbox (reused) and the harness agent. |
| `instructions.md` | Agent instructions. A copy is inlined in `azure.yaml`, and the two must stay identical. |
| `skills/<name>/` | Four skills: `deal-intake`, `pricing-policy`, `counterproposal` and `approval-routing`. Each folder has a `SKILL.md` and the playbook pages that the skill reads. |
| `toolbox.yaml` | Toolbox `deal-desk-toolbox`, built from the `deal-system` connection (the Deal System MCP server). |
| `routine-8am-sweep.yaml` | Routine `deal-desk-8am-sweep` that triages the open queue on weekdays at 8:00. |

## How it works

- **Deal System tools.** The agent reaches these through `deal-desk-toolbox`: `get_deal`, `list_queue`, `evaluate_deal`, `submit_decision`, `request_approval`, `get_approval`, `update_crm` and `generate_term_sheet`. The Deal System also exposes `record_approval`, but only humans can approve, so it always refuses the agent.
- **Deal Economics.** The OpenAPI tool `deal_economics` calls the hosted agent's Responses endpoint. The tool starts a request with `askDealEconomics` (`background=true`) and then polls `getDealEconomicsResult`.
- **Harness tools.** Shell and file access are on, so the agent can read the bundled skill files. Web access and subagents are off.
- **Guardrail.** The agent is bound to `caldova-agent-guardrail`, which applies Prompt Shields and enforces network egress. See [`../../infra`](../../infra).

## Prerequisites

- **Foundry project.** You need a Foundry project in a region that supports both the [Copilot harness](https://learn.microsoft.com/azure/foundry/agents/concepts/limits-quotas-regions#microsoft-copilot-harness-preview) and [hosted agents](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents#region-availability), for example East US, Sweden Central or West US 3. East US 2 supports hosted agents but not the harness.
- **Model deployment.** The project needs a model that supports reasoning and tool calling. This sample defaults to `gpt-6.1-sol`. Check that the model is available in your region.
- **Deal Economics.** The Deal Economics hosted agent must be deployed in the same project. See [`../deal-economics`](../deal-economics).
- **Deal System.** The Deal System must be running, with `DEAL_SYSTEM_API_KEY` set, and exposed through a dev tunnel. See [`../deal-system`](../deal-system). Set `DEAL_SYSTEM_PUBLIC_URL` and `DEAL_SYSTEM_API_KEY` in your shell.
- **Tooling.** You need azd 1.37.0 or later and the Foundry extensions. `microsoft.foundry` installs the agents, connections, toolboxes, skills, routines and Agent Inspector extensions:

  ```
  azd extension install microsoft.foundry azure.ai.evaluations
  ```

- **Roles.** You need the **Foundry User** and **Foundry Project Manager** roles on the project. Creating connections and toolbox connections requires Foundry Project Manager.

## Set up and run

Run every command from this folder (`src/deal-desk`). The commands work in bash and PowerShell unless a step shows both forms.

1. **Create an azd environment and set its values**. In these commands, `<foundry-account>`, `<project>` and the IDs are yours.

   ```
   azd env new deal-desk
   azd env set FOUNDRY_PROJECT_ENDPOINT "https://<foundry-account>.services.ai.azure.com/api/projects/<project>"
   azd ai project add --project-id "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/projects/<project>"
   azd env set DEAL_DESK_MODEL_DEPLOYMENT_NAME "gpt-6.1-sol"
   azd env set DEAL_ECONOMICS_RESPONSES_URL "https://<foundry-account>.services.ai.azure.com/api/projects/<project>/agents/deal-economics/endpoint/protocols/openai"
   azd env set RAI_POLICY_ID "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/raiPolicies/caldova-agent-guardrail"
   ```

   `azd ai project add` links the environment to your project and sets `AZURE_AI_PROJECT_ID`, the subscription, resource group and location. `FOUNDRY_PROJECT_ENDPOINT` must point to the same project.

2. **Apply the guardrail**. Create `caldova-agent-guardrail` as described in [`../../infra/README.md`](../../infra/README.md). Deployment fails if `RAI_POLICY_ID` points to a policy that doesn't exist.

3. **Create the Deal System connection**.

   bash:

   ```bash
   azd ai connection create deal-system --kind remote-tool --target "$DEAL_SYSTEM_PUBLIC_URL/mcp" --auth-type custom-keys --custom-key "x-api-key=$DEAL_SYSTEM_API_KEY"
   ```

   PowerShell:

   ```powershell
   azd ai connection create deal-system --kind remote-tool --target "$env:DEAL_SYSTEM_PUBLIC_URL/mcp" --auth-type custom-keys --custom-key "x-api-key=$env:DEAL_SYSTEM_API_KEY"
   ```

4. **Create the skills**. Each folder is uploaded as one package. The first version is `1`, which is the version that `azure.yaml` pins. To replace a skill, add `--force`.

   ```
   azd ai skill create deal-intake --file ./skills/deal-intake/
   azd ai skill create pricing-policy --file ./skills/pricing-policy/
   azd ai skill create counterproposal --file ./skills/counterproposal/
   azd ai skill create approval-routing --file ./skills/approval-routing/
   ```

5. **Create the toolbox**.

   ```
   azd ai toolbox create deal-desk-toolbox --from-file toolbox.yaml
   azd ai toolbox show deal-desk-toolbox --output json
   ```

   - **Endpoint variable.** The create command writes `TOOLBOX_DEAL_DESK_TOOLBOX_MCP_ENDPOINT` to the azd environment. If the variable is missing, set it from the `show` output with `azd env set`. The value has the form `https://.../api/projects/<project>/toolboxes/deal-desk-toolbox/versions/<n>/mcp?api-version=v1`.
   - **Approval mode.** In the `show` output, check that the Deal System tool has `require_approval: never`.

6. **Deploy the agent**. The Copilot harness is behind an azd alpha flag.

   bash:

   ```bash
   AZD_ALPHA_ENABLE_AGENTS_MANAGED_HARNESS=true azd deploy --all --no-prompt
   ```

   PowerShell:

   ```powershell
   $env:AZD_ALPHA_ENABLE_AGENTS_MANAGED_HARNESS = "true"; azd deploy --all --no-prompt
   ```

   The deploy creates the agent version. It also creates a project connection that lets the agent call the toolbox. It doesn't create a new toolbox version.

   Before you deploy, you can check the project locally with `azd ai agent doctor --local-only`. It reports whether the agent definition is valid once the environment values are set.

7. **Grant roles**.

   1. Get the agent's identity. Run this command and copy the ID it prints:

      ```
      az rest --method get --url "https://<foundry-account>.services.ai.azure.com/api/projects/<project>/agents/caldova-deal-desk?api-version=v1" --resource "https://ai.azure.com" --query "instance_identity.principal_id" --output tsv
      ```

   2. Assign the roles to that identity:
      - **Foundry User** (`53ca6127-db72-4b80-b1b0-d745d6d5456d`) lets the agent call the toolbox.
      - **Foundry Agent Consumer** (`eed3b665-ab3a-47b6-8f48-c9382fb1dad6`) lets the agent call Deal Economics.

      ```
      az role assignment create --assignee-object-id "<agent-principal-id>" --assignee-principal-type ServicePrincipal --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope "<AZURE_AI_PROJECT_ID>"
      az role assignment create --assignee-object-id "<agent-principal-id>" --assignee-principal-type ServicePrincipal --role "eed3b665-ab3a-47b6-8f48-c9382fb1dad6" --scope "<AZURE_AI_PROJECT_ID>"
      ```

   3. If `deal_economics` still returns 401 or 403, assign Foundry Agent Consumer to the project's managed identity as well. Get that identity's ID with:

      ```
      az resource show --ids "<AZURE_AI_PROJECT_ID>" --query identity.principalId --output tsv
      ```

   Allow up to five minutes for role assignments to take effect.

8. **Check the deployed definition**.

   ```
   azd ai agent show caldova-deal-desk --output json
   ```

   Check two things in the output:
   - `rai_config.rai_policy_name` equals `RAI_POLICY_ID`.
   - The tools include the toolbox MCP endpoint, `deal_economics` and the Copilot toolset.

9. **Try it**.

   ```
   azd ai agent invoke caldova-deal-desk --new-conversation "Review Priya's Northwind request."
   ```

   The agent should report the following:
   - Northwind's ask on `DEAL-NW-001` is at about 26.4% gross margin, below the 32% floor.
   - Its best counter keeps about 85% of the asked value at about 33.1% gross margin.
   - The counter's effective rebate (14%) is above the agent's authority, so it has requested VP Finance approval and gives the local approval link.

   You can paste the contents of [`../../data/seed/priya_email.md`](../../data/seed/priya_email.md) or [`../../data/seed/northwind_redline.md`](../../data/seed/northwind_redline.md) into the message. The redline contains an embedded instruction and a link. The agent must ignore the instruction and must not open the link.

10. **Approve and continue**.
    1. Open `http://localhost:8080/` on the machine that runs the Deal System.
    2. Approve as Dana (VP Finance).
    3. Run `azd ai agent invoke caldova-deal-desk "Dana approved it. Finish the Northwind deal."` The agent confirms the approval with the Deal System, then generates the term sheet and updates the CRM stage.

    For a within-authority case, run `azd ai agent invoke caldova-deal-desk --new-conversation "Approve Lakeshore DEAL-RT-001."`

11. **Create the 8am routine**. The routine runs as you (`authorization.identity: creator`) on weekdays at 8:00 Pacific time. Edit `timeZone` in the file to change the time zone.

    ```
    azd ai routine create deal-desk-8am-sweep --file routine-8am-sweep.yaml --force
    ```

## Troubleshooting

- **Long runs.** `azd ai agent invoke` waits up to 1,800 seconds by default. Change the wait with `--timeout <seconds>`. If a long run fails with a server error, start a new conversation and ask for one deal at a time.
- **Tool approval prompts.** If the agent stops to ask for tool approval, the toolbox's Deal System tool isn't set to `require_approval: never`. Check `azd ai toolbox show deal-desk-toolbox --output json`.
- **Guardrail changes.** A running harness session doesn't reload changes to the guardrail. Use `--new-conversation` after you change it.
- **Skill changes.** After you edit a skill, re-create it with `--force` and redeploy the agent.
