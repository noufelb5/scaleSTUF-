# Ledgerwise SDR

[Open the hosted demo on Render](https://scalestuf.onrender.com/)

> **Simulated case-study demo.** This project uses a seeded Allbirds example and public source material. It is not connected to Ledgerwise's real systems, email, or calendar. Keep provider credentials unset for the demo.

## Run locally

Run these commands in PowerShell from the repository directory:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. The workspace username is `ledgerwise`. Set a local `WORKSPACE_PASSWORD` in an untracked `.env` file if you want authentication during local use. SQLite is the local default. For a persistent PostgreSQL database, set `DATABASE_URL` to a `postgresql+psycopg://` URL.

## Explore the simulated workflow

1. Open the seeded Allbirds prospect and review its evidence.
2. Generate and inspect the sourced draft.
3. Review how the app tracks prospect status and human review.

Do not send email or book a real meeting from this demo. With provider credentials unset, email sending, inbound email processing, and calendar availability or booking are unavailable.

## Run live prospect research

Set `WORKSPACE_PASSWORD` and `OPENAI_API_KEY` in your local `.env` or private deployment. Run with `LEDGERWISE_DEMO` unset. The research action uses the OpenAI Responses API and its web search tool. `OPENAI_RESEARCH_MODEL` defaults to `gpt-5-mini`. Search calls and model tokens use the configured API account.

Open **Prospects**, enter a goal, and select **Find prospects**. Each run requests up to three candidates from the dashboard, with a budget of up to 12 web tool calls. The results show fit, linked excerpts, and unknowns. A core fit requires sourced US operations and online sales. A bookkeeping need requires its own evidence. Review the excerpts against their sources before relying on them.

Review a match and select **Save to Prospects**. Each domain has one saved profile. The profile retains the evidence, publication dates, and unknowns. Select **Generate sourced draft** on the saved profile to open the pending draft in Inbox for review. The outgoing email requires approval of that version and a configured controlled mailbox.

## Deploy the demo on Render

Use a Python web service connected to the `main` branch:

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'`
- Health check path: `/healthz`
- Set `LEDGERWISE_DEMO=1` and a strong `WORKSPACE_PASSWORD` in Render's Environment settings.

Keep all provider settings empty in the demo deployment. Do not add Resend, Google Calendar, Langflow, or OpenAI credentials. The app reads those settings to access external services; leaving them unset keeps those integrations unavailable. Enter passwords and other secrets only in the local `.env` file or the hosting provider's secret settings. Never commit `.env` or share secret values in screenshots, chat, or source files. The repository's `.gitignore` excludes `.env`.

## Health check

Render and other hosts can check `/healthz`. A healthy response is JSON with `status` set to `ok`.

## Project notes

See [the PRD](PRD.md), [roadmap](ROADMAP.md), and [implementation notes](HOW_I_WORKED.md).
