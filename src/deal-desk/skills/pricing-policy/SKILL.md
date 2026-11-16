---
name: pricing-policy
description: Use whenever you need deal economics, the margin floor, the rate card or the authority matrix. Calls the Deal Economics agent for all math and explains results against Caldova policy.
---

# Pricing policy

Illustrative planning record; decisions are internal to this Deal System and do not submit a customer order or external offer.

**Never do margin math yourself.** Get every number from the hosted **Deal Economics agent** (tool
`deal_economics`). Call it asynchronously so a slow specialist cannot time out the handoff:

1. `askDealEconomics` with `background: true` and **one** terse request per deal, e.g. "DEAL-NW-001: ask GM, then
   top 3 counters (terms, deal-life GM, P10 GM, % of asked value, required approver) plus the
   price-protection cost of ask vs counter. <=150 words, no tables." It returns an `id` with status `in_progress`.
2. While it runs, read the policy files in this skill's folder, then poll `getDealEconomicsResult(response_id)`
   until `status` is `completed` (1-2 seconds between polls). Read the answer from `output[].content[].text`.
   Don't start a second request for the same deal.
3. Stop polling on a failed, cancelled, incomplete or expired status, or after 45 seconds, and report the failed
   hosted handoff. Only then use the Deal System tool `evaluate_deal` (same deterministic engine), labelled
   **Deal System fallback**, never as a successful hosted-specialist call.
4. On success, evaluate the specialist's recommended terms once with `evaluate_deal(deal_id, terms)` for
   authority validation. Do not launch another search.

The economics agent returns the ask's deal-life P&L, GM vs the floor, the GM bridge and ranked counters with
the required approver.

## Policy files in this skill

- `rate-card.md`: standard terms, concession levers and the component cost forecast.
- `authority-matrix.md`: who may approve what, approval rules and triage.
- `margin-floor.md`: the 32% floor, the P&L waterfall and the classic mistakes.

Key rules:

- Rate card: 8% rebate, Net-45, 12-month price protection, MDF 1% of TCV.
- **Margin floor: deal-life GM >= 32% (hard).** Counters keep >= 33% (1 pt negotiation headroom).
- MDF is **contra-revenue**, never opex.
- Multi-year price protection must be priced against the sensor-component **cost forecast**
  (years 2-3). This is what drags Northwind's ask to about 26% GM.
- Effective rebate for authority = base rebate + growth kicker (assumed earned).

## Authority (enforced by the Deal System, not you)

| Approver | Limits |
|---|---|
| Deal Desk agent (you) | effective rebate <= 10%, <= Net-60, <= 12-mo protection (CPI cap OK), MDF <= 2% TCV, GM >= 32% |
| Dana, VP Finance | beyond agent authority, concession <= $5M and GM >= 28% |
| Morgan, CFO | anything else |

Report numbers with one decimal (GM 26.4% -> 33.1%) and the % of customer value retained.
