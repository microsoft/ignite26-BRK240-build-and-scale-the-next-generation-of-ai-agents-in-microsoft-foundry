# Step 0: Set up your environment

In this step you install the tools, create a Foundry project with three model deployments and save the values that later steps use.

## Prerequisites

- **Azure subscription.** You need permission to create a resource group and assign roles, such as Owner, or Contributor plus User Access Administrator.
- **Python 3.12 or later.**
- **Azure CLI.** [Install the Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
- **Azure Developer CLI (azd) 1.37.0 or later**, with the Foundry extensions. [Install azd](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd), then run:

  ```bash
  azd extension install microsoft.foundry azure.ai.evaluations
  ```

  `microsoft.foundry` installs the agents, connections, toolboxes, skills, routines and Agent Inspector extensions. If you already have them, run `azd extension update --all`.
- **Dev Tunnels CLI**, for Step 3. [Install dev tunnels](https://learn.microsoft.com/azure/developer/dev-tunnels/get-started).

Clone the repository and sign in:

```bash
git clone https://github.com/microsoft/ignite26-BRK240-build-and-scale-the-next-generation-of-ai-agents-in-microsoft-foundry.git brk240
cd brk240
az login
azd auth login
```

## 1. Choose names and a region

The Microsoft Copilot harness and hosted agents must both be available in your region. Use East US (`eastus`), Sweden Central (`swedencentral`) or West US 3 (`westus3`). East US 2 supports hosted agents but not the harness. For the current list, see [harness regions](https://learn.microsoft.com/azure/foundry/agents/concepts/limits-quotas-regions#microsoft-copilot-harness-preview).

```bash
export LOCATION=westus3
export RESOURCE_GROUP=rg-brk240-sample
export FOUNDRY_ACCOUNT=<unique-name>
export FOUNDRY_PROJECT=dealdesk
```

`FOUNDRY_ACCOUNT` must be globally unique. It becomes the host name `<unique-name>.services.ai.azure.com`.

PowerShell: set each variable with `$env:LOCATION = "westus3"` and reference it as `$env:LOCATION`. The rest of this guide uses bash syntax.

## 2. Create the Foundry resource and project

```bash
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

az cognitiveservices account create --name "$FOUNDRY_ACCOUNT" --resource-group "$RESOURCE_GROUP" --location "$LOCATION" --kind AIServices --sku S0 --custom-domain "$FOUNDRY_ACCOUNT" --allow-project-management --assign-identity --yes

az cognitiveservices account project create --name "$FOUNDRY_ACCOUNT" --resource-group "$RESOURCE_GROUP" --project-name "$FOUNDRY_PROJECT" --location "$LOCATION"
```

## 3. Deploy the models

| Deployment | Used by |
|---|---|
| `gpt-5.5` | The Deal Economics agent (Steps 1 and 2) |
| `gpt-5.4-mini` | The evaluation judge (Step 5) |
| `gpt-6.1-sol` | The Deal Desk agent (Steps 3 and 4) |

```bash
az cognitiveservices account deployment create --name "$FOUNDRY_ACCOUNT" --resource-group "$RESOURCE_GROUP" --deployment-name gpt-5.5 --model-name gpt-5.5 --model-version 2026-04-24 --model-format OpenAI --sku-name GlobalStandard --sku-capacity 50

az cognitiveservices account deployment create --name "$FOUNDRY_ACCOUNT" --resource-group "$RESOURCE_GROUP" --deployment-name gpt-5.4-mini --model-name gpt-5.4-mini --model-version 2026-03-17 --model-format OpenAI --sku-name GlobalStandard --sku-capacity 50

az cognitiveservices account deployment create --name "$FOUNDRY_ACCOUNT" --resource-group "$RESOURCE_GROUP" --deployment-name gpt-6.1-sol --model-name gpt-6.1-sol --model-version 2026-09-29 --model-format OpenAI --sku-name GlobalStandard --sku-capacity 50
```

If a deployment fails for quota, lower `--sku-capacity` or use another region. To see the models and versions in your region, run `az cognitiveservices model list --location "$LOCATION" --output table`.

## 4. Assign your roles

You need **Foundry User** to run and call agents, and **Foundry Project Manager** to create connections and toolboxes in Step 3.

```bash
export FOUNDRY_ACCOUNT_ID=$(az cognitiveservices account show --name "$FOUNDRY_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query id --output tsv)
export MY_OBJECT_ID=$(az ad signed-in-user show --query id --output tsv)

az role assignment create --assignee "$MY_OBJECT_ID" --role "Foundry User" --scope "$FOUNDRY_ACCOUNT_ID"
az role assignment create --assignee "$MY_OBJECT_ID" --role "Foundry Project Manager" --scope "$FOUNDRY_ACCOUNT_ID"
```

New role assignments can take a few minutes to apply.

## 5. Connect Application Insights

Foundry stores agent traces in Application Insights. You use them in [Step 5](05-evaluate-and-observe.md).

1. Open the [Foundry portal](https://ai.azure.com) and select your project.
2. Go to **Build** > **Agents** and select **Traces**.
3. Select **Connect**, then **Create new**, and finish the wizard.

For more information, see [Set up tracing](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-setup).

## 6. Save the values for later steps

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://$FOUNDRY_ACCOUNT.services.ai.azure.com/api/projects/$FOUNDRY_PROJECT"
export AZURE_AI_PROJECT_ID=$(az cognitiveservices account project show --name "$FOUNDRY_ACCOUNT" --resource-group "$RESOURCE_GROUP" --project-name "$FOUNDRY_PROJECT" --query id --output tsv)
echo "$FOUNDRY_PROJECT_ENDPOINT"
echo "$AZURE_AI_PROJECT_ID"
```

Later steps use these variables:

| Variable | Example |
|---|---|
| `LOCATION`, `RESOURCE_GROUP`, `FOUNDRY_ACCOUNT`, `FOUNDRY_PROJECT` | The names you chose |
| `FOUNDRY_ACCOUNT_ID` | `/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>` |
| `FOUNDRY_PROJECT_ENDPOINT` | `https://<foundry-account>.services.ai.azure.com/api/projects/<project>` |
| `AZURE_AI_PROJECT_ID` | `<FOUNDRY_ACCOUNT_ID>/projects/<project>` |

Shell variables last only as long as the terminal. Step 3 uses three terminals, so save the `export` lines in a file such as `brk240.env` at the repository root, and run `source brk240.env` in each new terminal. Files that end in `.env` are ignored by git.

## What you built

A Foundry project with the three model deployments, tracing and the roles that the sample needs.

Next: [Step 1: Build the Deal Economics agent](01-build-deal-economics.md)
