# caldova_pricing

`caldova_pricing` is the deterministic pricing engine behind the Caldova Deal Desk sample. It computes a deal's P&L waterfall, checks the 32% gross-margin floor, prices the cost of price protection and searches thousands of counter-offer packages. It is pure Python with no dependencies, no I/O and no randomness, except the seeded Monte-Carlo pass in `slow` mode.

All companies, people and numbers are fictional.

The Deal Economics hosted agent ships a copy of this package (see [`../deal-economics/sync_vendor.py`](../deal-economics/sync_vendor.py)), and the Deal System and the data generator import it directly.

## Run it

From the repository root (the commands are the same in bash and PowerShell):

```bash
python -m pip install -e "src/pricing[dev]"
python -m caldova_pricing northwind          # Northwind's ask vs. the recommended counter
python -m caldova_pricing routine            # routine regional renewal (auto-approve)
python -m caldova_pricing search             # scenario search, top 3 counters
python -m caldova_pricing search --slow      # adds a Monte-Carlo stress test (about 30 s)
python -m pytest src/pricing/tests -q
```

Add `--json` to any command for machine-readable output.

## Model

| Line | Definition |
|---|---|
| List revenue | TCV at contract-start list prices, by contract year |
| Rebates | `base % × revenue` plus `kicker % × revenue` in each year where Caldova's forecast volume ≥ threshold × commit (contra-revenue) |
| MDF | face value, or `face × claim rate (80 %)` when tied to sell-through (contra-revenue, **not opex**) |
| Pass-through recovery | price adjustments that recover the forecast sensor-component increase. Not allowed during protection months. With a CPI cap, limited to cumulative CPI (3 %/yr) |
| COGS | `cogs_ratio × TCV` + forecast sensor-component increase (5.0 % of list in year 2, 5.5 % in year 3) |
| Price-protection cost | increase − recovery (`price_protection_cost(months, forecast, revenue, cpi_cap=)`) |
| Financing | `TCV × 7 % WACC × days / 365` |
| GM % | `(net revenue − COGS − financing) / net revenue` |

**Customer value** (from Northwind's point of view): rebates at Northwind's own volume plan
(111/115/120 % of commit, so the kicker is valued in all years) + MDF (sell-through MDF valued at
95 %) + payment float at Northwind's 12 % working-capital cost + avoided price increases against
Northwind's expectation of 6.7 %/yr market increases. The CPI cap covers all three years, so it is
worth more to Northwind than it costs Caldova. That is the asymmetry the search exploits.

**Concession** = deal margin at the standard rate card − deal margin at the package.

## Scenario search

The search covers base rebate 8–18 % × kicker 0–3 % × Net-45/60/75/90 × protection 12/18/24 ×
CPI cap y/n × MDF {1, 1.25, 1.5625, 1.875, 2.5} % of TCV × sell-through y/n, for **10,560 combos**.
Constraints (`SearchConstraints` defaults, from the pricing policy):

- GM ≥ 32 % floor + 1 pt negotiation headroom
- no dimension more generous than the ask
- kicker ≤ 2 %, and every non-rebate term within agent authority (Net-60, 12 mo, MDF ≤ 2 % TCV), so the approver decides one issue

The search ranks by customer value, then by GM. `slow=True` adds a seeded Monte-Carlo stress test
(sensor shock σ = 25 %, volume σ = 6 %, 2,000 draws) over the whole feasible frontier. It reports
progress and a P10 GM for the top 3. It takes about 30 s on a laptop.

## Calibrated results

The tests assert these figures to within 0.5 points.

| Package | GM | Customer value | Approver |
|---|---|---|---|
| Northwind ask (18 %, Net-90, 24 mo, $1.2M MDF) | 26.4 % | 100 % | CFO (concession $6.7M, GM < 28 %) |
| Recommended counter (12 % + 2 % kicker, Net-60, 12 mo + CPI cap, $900K sell-through MDF) | 33.1 % | 85.1 % | VP Finance (effective rebate 14 % > 10 %) |
| Lakeshore Pharmacy Group (9 %, Net-45) | 41.8 % | — | agent (auto-approve) |
