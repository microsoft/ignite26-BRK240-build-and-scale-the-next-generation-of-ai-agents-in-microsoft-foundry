# Step 6: Clean up

Remove what you created so it stops costing money.

1. Stop the local processes: the Deal System (`Ctrl+C`), the dev tunnel (`Ctrl+C`) and any `azd ai agent run` sessions.

2. Delete the routine so it no longer runs every weekday:

   ```bash
   cd src/deal-desk
   azd ai routine delete deal-desk-8am-sweep
   ```

3. Delete the resource group. This removes the Foundry resource, its project, model deployments, agents, toolboxes, skills, connections, guardrail and cost control:

   ```bash
   az group delete --name "$RESOURCE_GROUP" --yes
   ```

   If you created the Application Insights resource from Step 0 in a different resource group, delete it as well.

4. Purge the Foundry resource. A deleted Foundry resource stays soft-deleted for 48 hours and keeps its name reserved. To reuse the name or release its quota right away, purge it:

   ```bash
   az cognitiveservices account purge --location "$LOCATION" --resource-group "$RESOURCE_GROUP" --name "$FOUNDRY_ACCOUNT"
   ```

5. Delete the dev tunnel if you created a persistent one (`devtunnel list`, then `devtunnel delete <tunnel-id>`). Temporary tunnels created with `devtunnel host -p 8080` go away when you stop them.

6. Optionally remove local state: `src/deal-system/.state/`, the `.azure/` folders in `src/deal-economics` and `src/deal-desk`, the `*.local.json` guardrail copies, `.env` files and virtual environments. Git ignores all of them.
