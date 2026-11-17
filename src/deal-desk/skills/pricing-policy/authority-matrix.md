# Authority matrix and triage

> Illustrative planning record; decisions are internal to this Deal System and do not submit a customer order or external offer.

**The Caldova Deal System enforces authority by caller identity, not the model.**
`submit_decision(approve)` above the caller's authority returns `403 REQUIRES_HUMAN_APPROVAL`.

## Authority matrix

| Approver | May approve a package when **all** hold |
|---|---|
| **Caldova Deal Desk agent** | effective rebate (base + growth kicker) **<= 10 %** · payment terms **<= Net-60** · price protection **<= 12 months** (a CPI cap after the protection period is allowed) · MDF **<= 2 % of TCV** · deal-life GM **>= 32 %** |
| **VP Finance (Dana)** | anything beyond agent authority, as long as total concession **<= $5M** and deal-life GM **>= 28 %** |
| **CFO (Morgan)** | anything. Required when total concession **> $5M** or deal-life GM **< 28 %** |
| Sellers, read-only agents | cannot approve |

The effective rebate counts the growth kicker as earned. For example, 12 % base + 2 % kicker = **14 %**,
which is above agent authority.

## Approvals

- `request_approval` binds the request to the **exact deal and terms hash**, expires after 4 hours, and can be used once.
- The Deal System chooses the approver role from this matrix. The agent does not choose it.
- The approver's identity and timestamp are written to the deal record.
- If the terms change after approval, the approval no longer applies. A new request is required.

## Triage (8am pipeline sweep and new requests)

| Outcome | Rule | Agent action |
|---|---|---|
| **Auto-approve** | ask is within agent authority (including GM >= 32 %) | `submit_decision(approve)` and reply to the seller |
| **Counter** | ask exceeds authority, but a counter **within agent authority** keeps **>= 80 %** of the customer value asked | `submit_decision(counter, terms)` and `update_crm(counter_sent)` |
| **Escalate** | no within-authority counter reaches 80 % of asked value | build the recommended counter (counterproposal skill), `request_approval`, wait for the human decision |

`evaluate_deal(deal_id)` returns this classification. The 40-deal open queue (`DEAL-Q-001` to `DEAL-Q-040`)
triages to **29 auto-approve / 8 counter / 3 escalate**.
