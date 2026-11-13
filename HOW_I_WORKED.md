# Implementation notes

## Scope and decisions

Started from the FastAPI shell and built the controlled journey across Prospects, Inbox, and Meetings. Added 29 brand profiles from individual AI in Fashion Daily directory records. The existing Allbirds profile uses the company's August 13, 2024 release for historical US and online-sales evidence. US e-commerce activity accounts for 40 fit points. Company size, revenue, and recent timing remain unknown in the profiles. The directory provides prospect discovery evidence and leaves commercial qualification for further research.

Chose SQL retrieval by company ID and a deterministic sourced draft template for credential-free development. The optional Langflow adapter uses the same evidence and validates its output before saving a draft. No live Langflow instance or model credentials were available for comparison. Reply triage uses explicit rules for clear signals and routes other replies to a human. Application code owns version approval, sending, suppression, takeover, and booking.

Selected Resend for email and Google Calendar for availability and event creation. Sending is restricted to the configured controlled recipient. The calendar adapter writes a meeting to the dedicated calendar. The salesperson arranges the time with the controlled recipient before confirming it.

Added a local demo mode with its own default SQLite database and simulated sending, replies, and bookings. This lets a reviewer exercise the workflow before connecting a controlled mailbox and dedicated calendar.

## Checks run

The demo smoke check exercised the FastAPI route handlers and SQLite directly. All 30 records produced a draft citing their own evidence. The check also passed for editing, approval before send, simulated send retries, pricing and automation disclosure replies, negative availability routing, booking retries and conflicts, opt-out precedence, and persistence across app startup. JavaScript passed `node --check`. The current environment denied loopback socket access, so this pass did not verify a browser session.

| Check | Observed result |
| --- | --- |
| Python compilation and JavaScript syntax check | Both passed |
| Local FastAPI and SQLite workflow with simulated provider responses | Four scenario groups passed |
| Draft revision and send | Stale approval and unapproved sends were rejected. Repeating a successful send called the simulated mail provider once. |
| Inbound webhook | A malformed signature initially raised an error. After the fix it returned 401. A valid signed fixture was processed once across duplicate deliveries. |
| Calendar conflict and retry | A busy slot returned 409. Confirming a free slot twice created one simulated event and returned the same booking. The brief contained the interested reply. |
| Reply triage | An opt-out with meeting language still created a durable suppression. An unclear reply was classified for human review. |

## Pending

Live Resend delivery and inbound callback, real Google Calendar booking, and public HTTPS deployment with persistent storage remain unverified. Live verification requires a controlled recipient, Resend configuration, a dedicated Google Calendar with OAuth credentials, and a public callback URL. No paid provider calls were made or measured. Complete the session exports and Loom for submission.

