---
name: approval-routing
description: Use when submitting a decision to the Caldova Deal System, when it returns REQUIRES_HUMAN_APPROVAL, while waiting for a human approval, and after approval (term sheet, CRM, reply to seller).
---

# Approval routing

Illustrative planning record; decisions are internal to this Deal System and do not submit a customer order or external offer.

Only the **Caldova Deal System** can record an internal approval. It checks *your* identity against the authority matrix.

1. Try `submit_decision(deal_id, "approve", terms, rationale)` with the exact recommended terms.
   - Success (`auto_approved`) -> go to step 4.
   - `REQUIRES_HUMAN_APPROVAL` (403) -> read `exceeded[]` and `required_approver`; do **not** retry or
     reshape terms to sneak under a limit. Tell the seller it needs a human.
2. `request_approval(deal_id, terms, rationale, summary, alternatives)`. Rationale = 2-3 short sentences
   (ask GM -> counter GM, value retained, precedent); the approval page already shows GM, concession and approver.
   The Deal System picks the approver and puts the request in their inbox on the Deal System dashboard.
   You never see or handle the approval token.
3. Return the `approval_id`, the required approver and the `approval_page` link immediately. The approver
   opens that page on the machine running the Deal System and approves or rejects there. When asked to resume,
   poll `get_approval(approval_id)`. Never say "approved" unless `status` is `approved` and `decided_by` names
   the approver. If `rejected`, `expired` or `superseded`, report it and stop.
4. After approval: check the current deal (`get_deal`) for an already-generated term sheet and `term_sheet_sent`
   CRM activity, so a retry never duplicates completed writes. Otherwise `generate_term_sheet(deal_id)` ->
   `update_crm(deal_id, "term_sheet_sent", note)` -> reply to the seller with the approver's name, the approved
   terms, GM and the term-sheet download link. Describe this as an internal approval and a generated document.
   `term_sheet_sent` records internal CRM state; it does not send the document, submit a customer order,
   create an external offer or prove a signature.

Routine deals inside authority (e.g. Lakeshore `DEAL-RT-001`, 9% / Net-45): approve directly in step 1; no human.
Never call `record_approval`; it is for humans only and always rejects agents.
