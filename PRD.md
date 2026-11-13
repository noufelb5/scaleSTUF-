# Ledgerwise SDR MVP

Ledgerwise helps a salesperson decide which e-commerce brands to contact, see the evidence behind an outreach draft, and turn an interested reply into a booked introduction.

## User journey

| Screen | What the salesperson can do |
| --- | --- |
| Prospects | Review target fit, dated sources, timing signals, and missing facts. Generate a draft from the company’s evidence. |
| Inbox | Review the draft alongside its sources, edit it, approve the exact version, send it, and read incoming replies. Take over a conversation when needed. |
| Meetings | Check real calendar availability, confirm a slot, and open the calendar event and brief. |

## Acceptance criteria

- Research at least 30 real US e-commerce prospects. Record the source URL, date, and relevant evidence behind qualification claims. Show unknown size, revenue, and timing explicitly when evidence is missing. Present target fit and timing separately.
- Retrieve company evidence by company ID. Draft from that evidence and Ledgerwise’s service description. Reject references to evidence belonging to other companies. The salesperson verifies claim support before approval.
- Each edit creates a new pending version. Sending requires explicit approval of that version. Pause automated actions during human takeover and check persistent suppression immediately before every send.
- Authenticate and deduplicate incoming email events. Treat clear refusals and opt-outs as a durable suppression. Route ambiguous replies and sensitive questions for human review.
- When a prospect expresses meeting interest, show free slots from a dedicated calendar. Recheck the slot at confirmation. Retrying a confirmation returns the same event. The brief cites company evidence and captures the prospect’s expressed interest and suggested discovery questions.
- Verify the first journey using a real company’s public research, an authorized test mailbox, and a real dedicated calendar. Expand to 30 dossiers after this verification.
- Record provider checks, measured tests, costs, and unresolved issues in HOW_I_WORKED.md. Prepare the public repository, protected demo, session exports, and Loom walkthrough for submission.

## Implementation scope

Use FastAPI with a single-operator dashboard and SQL persistence. Use SQLite for local development and PostgreSQL for deployment. Keep approvals, contact restrictions, and bookings in application code. Evaluate one optional Langflow draft-generation flow using the same sourced input and draft contract as the direct workflow.

