# Ledgerwise SDR

Run the workspace from this directory.

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:WORKSPACE_PASSWORD = "choose-a-local-password"
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open [the workspace](http://127.0.0.1:8000) to explore 30 sourced prospect profiles and review drafts. The fit score awards 40 points for evidence of US e-commerce activity. Size, revenue, and recent timing need further research.

## Run the local demo

After installing dependencies, start the server in PowerShell with:

```powershell
$env:LEDGERWISE_DEMO = "1"
$env:LEDGERWISE_LOCAL_DEMO = "1"
.venv\Scripts\python.exe -m uvicorn app.main:app
```

Demo mode uses a separate default SQLite database. It simulates delivery, incoming replies, and bookings. Use it to walk through the workflow without provider accounts.

1. Open Prospects, pick a brand, and show its fit score, source, and unknown criteria.
2. Generate a sourced draft. In Inbox, edit and save a new version, approve it, then send it in the simulation.
3. Enter a simulated reply such as “I’m available next Tuesday for a call.” Show the reply in Inbox, then open Meetings, check availability, book a slot, and show the brief.
4. Demonstrate human review or opt-out on another conversation. For a Loom recording, keep the walkthrough under 10 minutes and identify the simulated steps.

## Share a hosted demo

1. Push this workspace to a GitHub repository, including `app/discovery.py` and `app/prospects.json`. Keep `.env` out of Git.
2. In [Render](https://dashboard.render.com/), create a **Web Service** from the repository. Choose Python and use the settings below.

   | Setting | Value |
   | --- | --- |
   | Build command | `pip install -r requirements.txt` |
   | Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'` |
   | Health check path | `/healthz` |
   | `LEDGERWISE_DEMO` | `1` |
   | `WORKSPACE_PASSWORD` | A strong password you share privately with reviewers |

3. Open the assigned HTTPS URL in a private browser window. Sign in as `ledgerwise` and complete the simulated workflow above, including a booking. Share the HTTPS URL and username with reviewers and provide the password privately.

For demo history that survives redeploys, configure `DEMO_DATABASE_URL` with a dedicated PostgreSQL `postgresql+psycopg://` connection string. To use real providers, set `LEDGERWISE_DEMO=0`, configure a separate persistent `DATABASE_URL`, and follow the live workflow below.

## Verify the live workflow

To discover prospects, set `OPENAI_API_KEY` and `WORKSPACE_PASSWORD` in `.env`, restart the app, then click **Prospects → Find new prospects**. Each run searches for up to five new brands. The app keeps source links and excerpts, skips known domains, and queues a draft when the research supports both target size ranges. Review the cited evidence in Prospects before approving the draft. Live email still uses the configured controlled mailbox.

Stop the demo server and run `Remove-Item Env:LEDGERWISE_DEMO` in the same PowerShell session before starting the live server. SQLite is the local default. For persistent PostgreSQL hosting, set `DATABASE_URL` to a `postgresql+psycopg://` URL.

1. Copy `.env.example` to `.env` and set a workspace password. The username is `ledgerwise`. Run a single app worker and use HTTPS for the provider callback.
2. Add a Resend API key with send and receive access, a verified sender, and a Resend inbound address as `MAIL_REPLY_TO`. Set `CONTROLLED_RECIPIENT` to a mailbox you own. Register the public `/webhooks/email/inbound` endpoint for `email.received` and put its signing secret in `.env`.
3. Enable the Google Calendar API. Provide an OAuth client ID, client secret, refresh token, and the exact ID of a dedicated calendar. Grant the Calendar OAuth scope `https://www.googleapis.com/auth/calendar` to the calendar owner.
4. In Prospects, save the controlled mailbox and generate a draft. In Inbox, inspect the evidence, approve the exact version, and send it. Reply from the controlled mailbox with a message such as “I’m available next Tuesday for a call.” Reopen Inbox, confirm the sender and outbound thread independently, then select **Verify reply** to apply its intent.
5. In Meetings, check live availability, choose a slot agreed with the test recipient, and open the event and its brief. The event is created on the dedicated calendar without sending a guest invitation.

Check Resend delivery logs before investigating a send with an unknown outcome. A retry uses the same idempotency key within the provider's safe window.

For submission, publish the authenticated workspace on a public HTTPS host, verify delivery and booking with the controlled accounts, and verify the URL from a private browser session. Include the GitHub link, session exports, implementation notes, and Loom. Keep the hosted app available for at least two weeks.

## Optional Langflow evaluation

Create a Chat Input → model → Chat Output flow. Its model should return a single plain JSON object with `subject`, `body`, and `evidence_ids`. Set `LANGFLOW_RUN_URL` to the full `/api/v1/run/<flow-id>` endpoint and set `LANGFLOW_API_KEY`. Generate a draft in a fresh workspace and compare its claims and source references against the built-in evidence template.

See [the PRD](PRD.md), [roadmap](ROADMAP.md), and [implementation notes](HOW_I_WORKED.md).


Public deployments require HTTPS and WORKSPACE_PASSWORD. For a passwordless local simulation, set LEDGERWISE_DEMO=1 and LEDGERWISE_LOCAL_DEMO=1 and bind Uvicorn to 127.0.0.1 without proxy headers. Keep the local demo flag disabled on hosted instances. Apply ingress login throttling for multi-worker deployments and cap webhook uploads at 1 MiB.
