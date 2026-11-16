# Step 1: Build the Deal Economics agent

In this step you run the pricing engine, then run the Deal Economics agent on your machine and test it in Agent Inspector.

**Why a hosted agent?** Deal math must be exact and repeatable, so it lives in ordinary, unit-tested Python. The model chooses which tool to call and explains the result, but every number comes from code. You build and debug the agent locally with Microsoft Agent Framework, then deploy the same code to Foundry in [Step 2](02-deploy-deal-economics.md).

You need the Foundry project and the `gpt-5.5` deployment from [Step 0](00-setup.md).

## 1. Set up the agent

From the repository root:

```bash
cd src/deal-economics
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

PowerShell: activate with `.venv\Scripts\Activate.ps1` and use `Copy-Item .env.example .env` instead of `cp`.

In `.env`, set `FOUNDRY_PROJECT_ENDPOINT` to your project endpoint and `AZURE_AI_MODEL_DEPLOYMENT_NAME` to `gpt-5.5`. Then create an azd environment with the same values. azd uses it now for `azd ai agent run` and later for the deploy.

```bash
azd env new deal-economics
azd env set FOUNDRY_PROJECT_ENDPOINT "$FOUNDRY_PROJECT_ENDPOINT"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-5.5
azd ai project add --project-id "$AZURE_AI_PROJECT_ID"
```

PowerShell: use `"$env:FOUNDRY_PROJECT_ENDPOINT"` and `"$env:AZURE_AI_PROJECT_ID"`.

`azd ai project add` links the environment to your existing project. It sets the project ID, subscription, resource group and location that the deploy in Step 2 needs.

Run the tests. They call the tools directly and make no model calls:

```bash
python -m pytest tests -q
```

## 2. Run the pricing engine

The `caldova_pricing` package is the deterministic engine behind every number in the demo. Its source is in [`src/pricing`](../src/pricing/README.md), and the agent folder ships a copy so that a deploy includes it. From `src/deal-economics`:

```bash
python -m caldova_pricing northwind
```

The output compares Northwind's ask with the recommended counter:

| Package | Deal-life gross margin | Value kept for Northwind | Approver |
|---|---|---|---|
| Northwind ask: 18% rebate, Net-90, 24 months of price protection, $1.2M co-marketing | 26.4% | 100% | CFO |
| Counter: 12% rebate plus 2% growth kicker, Net-60, 12 months of protection with a CPI cap, $900K co-marketing tied to sell-through | 33.1% | 85.1% | VP Finance |

The ask falls below the 32% floor mainly because of the 24-month price freeze: Caldova can't pass on a forecast increase in sensor-component costs. Run `python -m caldova_pricing search` to see the top three counters that the scenario search finds.

## 3. Look at the code

Open [`agent.py`](../src/deal-economics/agent.py). The parts to notice:

- **Tools are plain functions.** Each function decorated with `@tool` wraps the pricing engine: `deal_pnl_waterfall`, `check_margin_floor`, `search_counter_scenarios` and `price_protection_cost`. `model_deal` runs the first three at the same time.
- **`fetch_url`** fetches a link from a customer document. Locally it can reach any host. In Step 2 the egress policy blocks it.
- **`build_agent()`** creates an Agent Framework `Agent` with a `FoundryChatClient`, so the model runs in your Foundry project.
- **`main()`** serves the agent with `ResponsesHostServer`. The same host runs on your machine and in Foundry, and it speaks the OpenAI Responses protocol.
- **Instructions and tool descriptions** live in [`.agent_configs/baseline/`](../src/deal-economics/.agent_configs/baseline), separate from the code.

## 4. Run it in Agent Inspector

From `src/deal-economics`:

```bash
azd ai agent run
```

azd starts the agent on `http://localhost:8088` and opens Agent Inspector. Send this message:

```text
Model Northwind's ask.
```

The answer should show:

- The ask at 26.4% gross margin, below the 32% floor, which needs the CFO.
- The P&L waterfall and the gross margin bridge.
- Three counters at about 33% gross margin that the VP Finance can approve.

Open the **Traces** tab. You'll see `model_deal` and the three tools it runs in parallel. Then try a follow-up:

```text
What does 24 months of price protection cost on Northwind?
```

To call the agent without Agent Inspector, run `azd ai agent run --no-client` in one terminal and `azd ai agent invoke --local "Model Northwind's ask."` in another. If port 8088 is in use, pass `-p <port>` to `run` and `--port <port>` to `invoke`.

## What you built

A code-first agent with deterministic tools, tested locally with traces. Next, deploy it to Foundry and put it behind a network egress policy.

Next: [Step 2: Deploy Deal Economics and control egress](02-deploy-deal-economics.md)
