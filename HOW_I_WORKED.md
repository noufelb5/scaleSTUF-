# Implementation notes

## Scope and decisions

Started from the FastAPI shell and the revised product direction in the handoff. Built the controlled Allbirds journey across Prospects, Inbox, and Meetings. The Allbirds record uses the company's August 13, 2024 release for historical US and online-sales evidence. Company size, revenue, and recent timing remain unverified in this workspace.

Chose SQL retrieval by company ID and a deterministic sourced draft template for credential-free development. The optional Langflow adapter uses the same evidence and validates its output before saving a draft. No live Langflow instance or model credentials were available for comparison. Reply triage uses explicit rules for clear signals and routes other replies to a human. Application code owns version approval, sending, suppression, takeover, and booking.

Selected Resend for email and Google Calendar for availability and event creation. Sending is restricted to the configured controlled recipient. The calendar adapter writes a meeting to the dedicated calendar. The salesperson arranges the time with the controlled recipient before confirming it.

## Checks run

| Check | Observed result |
| --- | --- |
| Python compilation and JavaScript syntax check | Both passed |
| Local FastAPI and SQLite workflow with simulated provider responses | Four scenario groups passed |
| Draft revision and send | Stale approval and unapproved sends were rejected. Repeating a successful send called the simulated mail provider once. |
| Inbound webhook | A malformed signature initially raised an error. After the fix it returned 401. A valid signed fixture was processed once across duplicate deliveries. |
| Calendar conflict and retry | A busy slot returned 409. Confirming a free slot twice created one simulated event and returned the same booking. The brief contained the interested reply. |
| Reply triage | An opt-out with meeting language still created a durable suppression. An unclear reply was classified for human review. |

## Pending

Live Resend delivery and inbound callback, real Google Calendar booking, PostgreSQL deployment, and the optional live Langflow comparison remain unverified. No paid provider calls were made or measured. The 30-company research pass and deployment follow the live controlled journey. Complete the session exports and Loom after verification.

