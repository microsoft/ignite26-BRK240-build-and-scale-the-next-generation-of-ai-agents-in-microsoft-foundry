# Counterproposal design

> Illustrative planning record; decisions are internal to this Deal System and do not submit a customer order or external offer.

A counter is a **decision-ready package**, not a list of objections. The Deal Economics agent builds it
with a scenario search that applies these rules:

1. **Negotiation headroom.** Counters must keep deal-life GM >= **floor + 1 pt (33 %)**, because procurement always claws something back.
2. **Single-issue escalation.** Keep every non-rebate term within agent authority (Net-60, 12-month protection, MDF <= 2 % TCV), so the human approver decides one thing: the rebate.
3. **Never more generous than the ask** on any dimension.
4. **Use cheap-to-give, valuable-to-receive levers first:** growth kicker (<= 2 %, above 110 % of commit), CPI cap after protection, sell-through-tied MDF, then Net-60, then base rebate.
5. **Rank by customer value.** Present the top 3 with GM, % of asked value and the required approver.

## What to send the approver

- One line: what the customer asked, what we recommend, and why.
- GM bridge: ask GM -> counter GM, showing the price-protection x cost-forecast effect.
- Customer value retained (% of ask) and the approver required by the authority matrix.
- Precedent where relevant (see the deal-intake skill). For Northwind, the 2025 price-protection negotiation (P-2025-07).
