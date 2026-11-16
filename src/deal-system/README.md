# Caldova Deal System

The Deal System is the system of record for the Caldova Deal Desk sample. It is a small FastAPI app that runs on your machine and serves three things:

- An MCP server at `/mcp` (streamable HTTP). The `caldova-deal-desk` agent in Foundry calls it through a dev tunnel.
- A REST API under `/api`, with the same operations.
- A local dashboard and approval page at `http://localhost:8080/`, where a human approver signs off on deals the agent is not allowed to approve.

The Deal System enforces approval authority itself and does not rely on the model to do it. It recomputes the economics of every proposal with the deterministic `caldova_pricing` engine in [`../pricing`](../pricing). If the terms exceed the agent's authority, it rejects the proposal with `REQUIRES_HUMAN_APPROVAL`. Only Dana (VP Finance) or Morgan (CFO) can then approve the deal on the local approval page.

All companies, people and numbers are fictional. State is kept in a local JSON file, and nothing is sent to a customer.

## Install

You need Python 3.11 or later. From this folder (`src/deal-system`):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ../pricing -e ".[dev]"
```

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ../pricing -e ".[dev]"
```

Install in editable mode (`-e`). The Deal System finds its seed file, `data/generated/deal_system_seed.json`, relative to the repository root. If you install it any other way, set `DEAL_SYSTEM_SEED_PATH`.

## Run

```bash
python -m caldova_deal_system              # http://localhost:8080
python -m caldova_deal_system --port 8081  # another port
python -m caldova_deal_system --reset      # reset state to the seed and exit
```

These commands are the same in PowerShell. The server binds to `127.0.0.1`. On first start it copies the 42 seeded deals into `.state/deal_state.json`, which is ignored by git. To start the demo over, stop the server and run `--reset`.

Check that it is up:

```bash
curl http://localhost:8080/health
```

```powershell
Invoke-RestMethod http://localhost:8080/health
```

## Settings

| Variable | Default | Purpose |
|---|---|---|
| `DEAL_SYSTEM_API_KEY` | unset | When set, `/mcp` and `/api/*` require the header `x-api-key: <key>`. |
| `DEAL_SYSTEM_PORT` | `8080` | Port to listen on. |
| `DEAL_SYSTEM_STATE_DIR` | `src/deal-system/.state` | Where the state file and generated term sheets are written. |
| `DEAL_SYSTEM_SEED_PATH` | `data/generated/deal_system_seed.json` | Seed deals, loaded on first start and by `--reset`. |

## Security

Set an API key before you expose the server:

```bash
export DEAL_SYSTEM_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

```powershell
$env:DEAL_SYSTEM_API_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"
```

- **With a key:** `/mcp` and `/api/*` return 401 unless the request carries a matching `x-api-key` header. The key is compared in constant time.
- **Without a key:** the server prints a warning at startup, and `/mcp` and `/api/*` answer only direct local requests.
- **`/health`** is always open.
- **The dashboard, approval pages and term-sheet downloads** are served only to direct local requests. A direct local request comes from a loopback client, carries a `localhost` Host header, and has no `X-Forwarded-For`, `X-Forwarded-Host` or `Forwarded` header. Every other request gets a 404. This is why the dev tunnel exposes only the key-protected API: approving a deal stays on the operator's machine.

## Expose it to Foundry with a dev tunnel

Install the [dev tunnels CLI](https://learn.microsoft.com/azure/developer/dev-tunnels/get-started), start the Deal System with `DEAL_SYSTEM_API_KEY` set, then in a second terminal run:

```bash
devtunnel user login
devtunnel host -p 8080 --allow-anonymous
```

Copy the `https://...devtunnels.ms` URL that the command prints and set it as `DEAL_SYSTEM_PUBLIC_URL` (`export` in bash, `$env:` in PowerShell). The Deal Desk agent setup in [`../deal-desk`](../deal-desk) registers it as the `deal-system` connection:

```bash
azd ai connection create deal-system --kind remote-tool --target "$DEAL_SYSTEM_PUBLIC_URL/mcp" --auth-type custom-keys --custom-key "x-api-key=$DEAL_SYSTEM_API_KEY"
```

`--allow-anonymous` lets the Foundry agent reach the tunnel without signing in to dev tunnels. The API key is what protects the API, so don't start the tunnel without one.

## Approval flow

1. The agent proposes terms with `submit_decision`. If they exceed its authority, for example Northwind's ask on `DEAL-NW-001`, the Deal System returns the error `REQUIRES_HUMAN_APPROVAL` along with the required approver role.
2. The agent calls `request_approval` with the terms, a short rationale and its alternatives. The deal moves to `awaiting_approval`, and the result includes the `approval_id` and the local `approval_page` URL.
3. Open `http://localhost:8080/`. The dashboard refreshes every few seconds and lists the pending approval. Open it to see the terms, the deal-life GM against the 32% floor, the concession and the authority breach.
4. Choose the approver and select **Approve** or **Reject**:
   - VP Finance-level requests can be approved by Dana (VP Finance) or Morgan (CFO).
   - CFO-level requests can be approved only by Morgan (CFO).
5. The deal record updates to `approved` with `approved_by`. When the agent calls `get_approval` or `get_deal`, it sees the decision and can continue with `update_crm` and `generate_term_sheet`.

The page posts a one-time approval token and the hash of the terms. The decision is refused if the token or terms hash doesn't match, if a newer request superseded this one, or if the request expired (after 4 hours). The token is never returned over MCP or REST, and `record_approval` called by the agent always returns `APPROVER_NOT_AUTHORIZED`.

## MCP tools

Every MCP and REST caller acts as the agent, `agent-deal-desk`.

| Tool | What it does |
|---|---|
| `get_deal` | Deal record: customer, ask terms, system-computed ask economics, status, decisions, approvals, CRM log |
| `list_queue` | Deal queue with status counts (`status`, `limit`) |
| `evaluate_deal` | Deal-life P&L, margin-floor check, triage and recommended counter, or the economics of given terms |
| `submit_decision` | `approve`, `counter` or `reject` within the agent's authority; otherwise `REQUIRES_HUMAN_APPROVAL` |
| `request_approval` | Ask a human approver to sign off on terms (`rationale`, optional `summary` and `alternatives`) |
| `get_approval` | Approval status: `pending`, `approved`, `rejected`, `expired` or `superseded` |
| `record_approval` | Human-only; the agent always gets `APPROVER_NOT_AUTHORIZED` |
| `update_crm` | Append a CRM activity (`counter_sent`, `approval_requested`, `term_sheet_sent`, `signed`, `closed_lost`) |
| `generate_term_sheet` | Illustrative .docx term sheet for an approved deal (local download link) |

## Endpoints

| Path | Access |
|---|---|
| `GET /health` | Open |
| `/mcp` | API key, when set |
| `GET /api/deals?status=&limit=`, `GET /api/deals/{id}` | API key, when set |
| `POST /api/deals/{id}/decision`, `POST /api/deals/{id}/approval-requests`, `POST /api/deals/{id}/crm` | API key, when set |
| `GET /api/approvals/{id}`, `POST` and `GET /api/deals/{id}/term-sheet` | API key, when set |
| `GET /`, `GET` and `POST /approvals/{id}`, `GET /term-sheets/{id}` | Direct local requests only |

## Tests

```bash
python -m pytest -q
```

The tests run the service, the REST and HTML routes, and a real MCP client against a server on a random local port.
