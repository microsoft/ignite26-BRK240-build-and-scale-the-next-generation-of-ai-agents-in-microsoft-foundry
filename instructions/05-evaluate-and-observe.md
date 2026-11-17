# Step 5: Evaluate and observe

In this step you score the Deal Economics agent against a golden set of questions, then use traces and Insights to see what both agents did.

You need the Deal Economics agent from [Step 2](02-deploy-deal-economics.md) and the `gpt-5.4-mini` deployment from [Step 0](00-setup.md), which the evaluators use as their judge.

## 1. Run the evaluation

[`src/deal-economics/eval.yaml`](../src/deal-economics/eval.yaml) defines the eval `deal-economics-golden`. Its dataset, [`datasets/deal-economics-eval.jsonl`](../src/deal-economics/datasets/deal-economics-eval.jsonl), has 16 questions with answers computed by the pricing engine:

- Northwind's ask and counters
- The cost of price protection
- A routine renewal
- Historical deals, including multi-year price protection and co-marketing traps
- A prompt-injection refusal

Two built-in evaluators score each answer: task completion and task adherence.

From `src/deal-economics`:

```bash
azd deploy deal-economics-evals
azd ai eval run start --eval deal-economics-golden
```

The run takes about four minutes. Check on it and read the results:

```bash
azd ai eval run show --eval deal-economics-golden
azd ai eval run output list --eval deal-economics-golden
```

Don't expect every row to pass. The judge is strict about wording and completeness, and in our test run about half the rows passed. Treat the first run as your baseline: open the failed rows, decide whether the agent or the ground truth is wrong, and rerun after each change.

You can also open the run in the [Foundry portal](https://ai.azure.com) under **Evaluations**. To find patterns in the results, select the run and start a [cluster analysis](https://learn.microsoft.com/azure/foundry/observability/how-to/cluster-analysis).

## 2. Read the traces

Each agent run produces a trace. In the Foundry portal, open your project, then open an agent and select **Traces**.

- **`caldova-deal-desk`.** Open the Northwind conversation from Step 4. The trace shows each skill the agent loaded, every Deal System tool call, the `deal_economics` calls and the `REQUIRES_HUMAN_APPROVAL` result that led to the approval request.
- **`deal-economics`.** Open the run where you asked about the benchmark link in Step 2. The `fetch_url` span shows the 403 from the egress policy.

To stream the hosted agent's logs in your terminal, run `azd ai agent monitor --follow` from `src/deal-economics`.

## 3. Find patterns with Insights

Insights (preview) reviews your agents' traces and groups recurring behavior into findings. Each finding includes a description, a severity, example traces and a suggested next step. Use it to find problems that your evaluation doesn't cover yet, then add those cases to the golden set.

Insights needs traces to work with. Run a few more conversations through both agents before you open it. For more information, see [Insights in Microsoft Foundry](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/insights-in-foundry-turns-agent-traces-into-action/4559634).

## What you built

A repeatable quality check for the code-first agent, plus the traces you need to debug both agents.

Next: [Step 6: Clean up](06-clean-up.md)
