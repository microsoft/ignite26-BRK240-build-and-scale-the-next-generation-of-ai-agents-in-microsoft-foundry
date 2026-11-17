---
name: counterproposal
description: Use when a deal ask is outside the rate card or below the margin floor and you must recommend a decision-ready counter (terms, GM bridge, customer value, approver).
---

# Counterproposal

Illustrative planning record; decisions are internal to this Deal System and do not submit a customer order or external offer.

A counter is an **internal recommendation**, not an external offer. Build it from the Deal Economics agent's
ranked counters (a scenario search over thousands of term combinations); do not invent terms.

Design rules (full version in `counterproposal-design.md` in this skill's folder):
1. Keep GM >= 33% (floor + 1 pt headroom).
2. Single-issue escalation: keep Net-60, 12-month protection and MDF <= 2% TCV inside agent authority,
   so a human decides only the rebate.
3. Never more generous than the ask on any dimension.
4. Prefer cheap-to-give, valuable-to-receive levers: growth kicker above 110% of commit, CPI cap after
   protection, sell-through MDF, then Net-60, then base rebate.

## Answer format (keep it short)

**Decision:** Counter (or Approve / Escalate)
**Ask:** 18% rebate · Net-90 · 24-mo protection · $1.2M MDF -> **GM 26.4%** (below the 32% floor)
**Why:** 24-month price protection x the year-2/3 sensor-component cost increase.
**Recommend:** 12% + 2% growth kicker >110% commit · Net-60 · 12-mo protection + CPI cap · $900K
sell-through MDF -> **GM ~33%**, ~85% of the customer value asked.
**Approval:** effective rebate 14% exceeds agent authority -> VP Finance (Dana).
**Precedent:** Northwind 2025 (P-2025-07) accepted a CPI cap in 2 days.

For Northwind the numbers above are the expected result; always use the tool's actual values.
