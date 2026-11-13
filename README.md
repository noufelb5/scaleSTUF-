# Ledgerwise SDR

Run the workspace from this directory.

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open [the workspace](http://127.0.0.1:8000) to explore the sourced Allbirds example and review a draft. SQLite is the local default. The SQLAlchemy PostgreSQL connection uses a `postgresql+psycopg://` URL.

## Verify the live workflow

1. Copy `.env.example` to `.env` and set a workspace password. The username is `ledgerwise`. Run a single app worker and use HTTPS for the provider callback.
2. Add a Resend API key with send and receive access, a verified sender, and a Resend inbound address as `MAIL_REPLY_TO`. Set `CONTROLLED_RECIPIENT` to a mailbox you own. Register the public `/webhooks/email/inbound` endpoint for `email.received` and put its signing secret in `.env`.
3. Enable the Google Calendar API. Provide an OAuth client ID, client secret, refresh token, and the exact ID of a dedicated calendar. Grant the Calendar OAuth scope `https://www.googleapis.com/auth/calendar` to the calendar owner.
4. In Prospects, save the controlled mailbox and generate a draft. In Inbox, inspect the evidence, approve the exact version, and send it. Reply from the controlled mailbox with a message such as “I’m available next Tuesday for a call.” Reopen Inbox and confirm the reply appeared.
5. In Meetings, check live availability, choose a slot agreed with the test recipient, and open the event and its brief. The event is created on the dedicated calendar without sending a guest invitation.

Check Resend delivery logs before investigating a send with an unknown outcome. A retry uses the same idempotency key within the provider's safe window.

## Optional Langflow evaluation

Create a Chat Input → model → Chat Output flow. Its model should return a single plain JSON object with `subject`, `body`, and `evidence_ids`. Set `LANGFLOW_RUN_URL` to the full `/api/v1/run/<flow-id>` endpoint and set `LANGFLOW_API_KEY`. Generate a draft in a fresh workspace and compare its claims and source references against the built-in evidence template.

See [the PRD](PRD.md), [roadmap](ROADMAP.md), and [implementation notes](HOW_I_WORKED.md).

