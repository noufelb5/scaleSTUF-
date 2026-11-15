"""Run the controlled Ledgerwise journey with local provider fixtures."""
import base64
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from httpx import Request, Response
from sqlalchemy import create_engine
from svix.webhooks import Webhook

from app import main

MAILBOX = "operator@example.com"
INBOUND = "inbound@example.com"
SITE = "https://shop.example.com/"
SIGNING_SECRET = "whsec_" + base64.b64encode(b"test-webhook-signing-material").decode()
SETTINGS = {
    "WORKSPACE_PASSWORD": "local-test-password",
    "OPENAI_API_KEY": "fixture-openai",
    "OPENAI_RESEARCH_MODEL": "fixture-model",
    "RESEND_API_KEY": "fixture-resend",
    "RESEND_WEBHOOK_SECRET": SIGNING_SECRET,
    "CONTROLLED_RECIPIENT": MAILBOX,
    "MAIL_FROM": "ledgerwise@example.com",
    "MAIL_REPLY_TO": INBOUND,
    "GOOGLE_CALENDAR_ID": "fixture-calendar",
    "GOOGLE_CLIENT_ID": "fixture-client",
    "GOOGLE_CLIENT_SECRET": "fixture-secret",
    "GOOGLE_REFRESH_TOKEN": "fixture-token",
}


class LedgerwiseJourney(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        engine = create_engine("sqlite:///" + str(Path(directory) / "test.sqlite3"))
        self.addCleanup(engine.dispose)
        self.enterContext(patch.object(main, "engine", engine))
        self.enterContext(patch.dict("os.environ", SETTINGS, clear=True))
        self.client = self.enterContext(TestClient(main.app))
        self.client.auth = ("ledgerwise", SETTINGS["WORKSPACE_PASSWORD"])
        self.sent = []
        self.received = {}
        self.events = {}
        self.provider = self.enterContext(patch("app.providers.httpx.request", side_effect=self.provider_request))

    def provider_request(self, method, url, **kwargs):
        # Return HTTP-shaped fixtures while leaving the provider adapters under test.
        if url == "https://api.openai.com/v1/responses":
            evidence = [
                {"criterion": "US presence", "url": SITE, "finding": "Example Shop operates in Austin.",
                 "excerpt": "Based in Austin, Texas", "source_date": None},
                {"criterion": "Online sales", "url": SITE, "finding": "Example Shop sells cookware online.",
                 "excerpt": "Shop cookware online", "source_date": None},
            ]
            candidate = {"name": "Example Shop", "website": SITE, "fit": "match", "evidence": evidence}
            data = {"status": "completed", "output": [
                {"type": "web_search_call", "status": "completed", "action": {
                    "type": "search", "sources": [{"url": SITE}]}},
                {"type": "message", "content": [{"type": "output_text",
                    "text": json.dumps({"candidates": [candidate]})}]},
            ]}
        elif url == "https://api.resend.com/emails":
            self.sent.append(kwargs["json"])
            data = {"id": str(len(self.sent))}
        elif "/emails/receiving/" in url:
            data = self.received[url.rsplit("/", 1)[1]]
        elif url == "https://oauth2.googleapis.com/token":
            data = {"access_token": "fixture-access-token"}
        elif url.endswith("/freeBusy"):
            data = {"calendars": {"fixture-calendar": {"busy": []}}}
        elif method == "POST" and url.endswith("/events"):
            data = kwargs["json"]
            self.events[data["id"]] = data
        elif method == "GET" and "/events/" in url:
            data = self.events.get(url.rsplit("/", 1)[1])
        else:
            self.fail(f"Unexpected provider request {method} {url}")
        return Response(200 if data is not None else 404, json=data, request=Request(method, url))

    def ok(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def receive(self, number, text):
        receipt = f"fixture-email-{number}"
        self.received[receipt] = {"text": text, "subject": "Re: Ledgerwise",
                                  "message_id": f"<{receipt}@example.com>"}
        payload = json.dumps({"type": "email.received", "data": {
            "email_id": receipt, "from": MAILBOX, "to": [INBOUND],
        }})
        time = datetime.now(UTC).replace(microsecond=0)
        return self.ok("POST", "/webhooks/email/inbound", content=payload, headers={
            "svix-id": receipt, "svix-timestamp": str(int(time.timestamp())),
            "svix-signature": Webhook(SIGNING_SECRET).sign(receipt, time, payload),
        })

    def test_research_to_approved_outreach_and_booking(self):
        run = self.ok("POST", "/api/research", json={"goal": "Find US online cookware shops"})
        candidate = f"/api/research/{run['id']}/prospects/shop.example.com"
        profile = self.ok("POST", candidate)
        self.assertEqual(self.ok("POST", candidate)["id"], profile["id"])
        self.assertIn("Bookkeeping need", profile["unknown"])
        path = f"/api/companies/{profile['id']}"
        self.assertEqual(self.client.put(path + "/contact", json={"address": "third-party@example.com"}).status_code, 422)
        self.ok("PUT", path + "/contact", json={"address": MAILBOX})
        initial = self.ok("POST", path + "/drafts")["drafts"][-1]
        self.assertIn(initial["evidence_ids"][0], {item["id"] for item in profile["evidence"]})
        first = f"{path}/drafts/{initial['id']}"
        self.assertEqual(self.client.post(first + "/send").status_code, 409)
        self.ok("POST", first + "/review", json={"decision": "approve"})
        self.ok("POST", first + "/send")

        self.assertEqual(self.client.post("/webhooks/email/inbound", json={}).status_code, 401)
        self.assertEqual(self.receive(1, "Let's schedule a call.")["status"], "processed")
        self.assertEqual(self.receive(1, "Let's schedule a call.")["status"], "duplicate")
        followup = self.ok("POST", path + "/followups")["drafts"][-1]
        self.assertIn("UTC", followup["body"])
        follow = f"{path}/drafts/{followup['id']}"
        self.assertEqual(self.client.post(follow + "/send").status_code, 409)
        self.ok("POST", follow + "/review", json={"decision": "approve"})
        next_version = self.ok("PATCH", follow, json={
            "subject": followup["subject"], "body": followup["body"] + "\nThank you.",
            "evidence_ids": [],
        })["drafts"][-1]
        self.assertEqual(self.client.post(follow + "/send").status_code, 409)
        edited = f"{path}/drafts/{next_version['id']}"
        self.assertEqual(self.client.post(edited + "/send").status_code, 409)
        self.ok("POST", edited + "/review", json={"decision": "approve"})
        self.ok("POST", edited + "/send")
        self.ok("POST", edited + "/send")
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[-1]["headers"]["In-Reply-To"], "<fixture-email-1@example.com>")

        self.assertEqual(self.receive(2, "The first option works.")["status"], "processed")
        slot = self.ok("GET", path + "/slots")[0]
        booking = self.ok("POST", path + "/bookings", json={"start": slot})["booking"]
        self.assertIn("The first option works.", booking["brief"])
        self.assertEqual(self.ok("POST", path + "/bookings", json={"start": slot})["booking"], booking)
        self.assertEqual(len(self.events), 1)
        self.receive(3, "No thanks, unsubscribe.")
        self.assertEqual(self.client.post(path + "/followups").status_code, 409)

    def test_demo_uses_local_drafts_and_blocks_providers(self):
        with patch.dict("os.environ", {"LEDGERWISE_DEMO": "1", "LANGFLOW_RUN_URL": "https://flow.example.com"}):
            self.assertEqual(self.ok("GET", "/healthz"), {"status": "ok"})
            dashboard = self.client.get("/")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn("Ledgerwise", dashboard.text)
            path = "/api/companies/allbirds"
            draft = self.ok("POST", path + "/drafts")["drafts"][-1]
            self.assertIn("Allbirds", draft["body"])
            send = f"{path}/drafts/{draft['id']}/send"
            self.assertEqual(self.client.post(send).status_code, 503)
            self.assertEqual(self.client.post("/api/research", json={"goal": "Find companies"}).status_code, 503)
            self.assertEqual(self.client.post("/webhooks/email/inbound", json={}).status_code, 503)
            self.provider.assert_not_called()
