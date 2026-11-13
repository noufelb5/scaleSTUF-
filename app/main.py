"""Ledgerwise's single-operator sales workspace."""
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from hashlib import sha256
from pathlib import Path
from secrets import compare_digest
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from uuid import uuid4

import json
import os
import re

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy import Column, Integer, JSON, MetaData, String, Table, create_engine, select, update
from svix.webhooks import Webhook, WebhookVerificationError

from app import discovery, providers

load_dotenv()
STATIC = Path(__file__).parent / "static"
DEMO = os.getenv("LEDGERWISE_DEMO") == "1"
engine = create_engine(
    os.getenv("DEMO_DATABASE_URL", "sqlite:///ledgerwise-demo.sqlite3") if DEMO
    else os.getenv("DATABASE_URL", "sqlite:///ledgerwise.sqlite3")
)
schema = MetaData()
profiles = Table("profiles", schema, Column("id", String, primary_key=True),
                 Column("contact", String, unique=True), Column("record", JSON, nullable=False))
control = Table("workspace_control", schema, Column("id", Integer, primary_key=True),
                Column("sequence", Integer, nullable=False))
suppressions = Table("suppressions", schema, Column("address", String, primary_key=True))
inbound = Table("inbound_receipts", schema, Column("id", String, primary_key=True))

SEED = {
    "name": "Allbirds",
    "domain": "allbirds.com",
    "evidence": [{
        "id": "allbirds-online",
        "criterion": "US e-commerce",
        "fact": "Allbirds has sold footwear online and has operated in San Francisco.",
        "excerpt": "Based in San Francisco",
        "url": "https://ir.allbirds.com/node/8646/pdf",
        "source_date": "2024-08-13",
    }],
    "timing": None,
    "fit_score": 40,
    "drafts": [],
    "replies": [],
    "status": "research",
    "takeover": False,
    "booking": None,
}


def seed_prospects():
    yield "allbirds", SEED
    catalog = json.loads((STATIC.parent / "prospects.json").read_text(encoding="utf-8"))
    for brand in catalog:
        company_id = brand["domain"].split(".")[0]
        yield company_id, {
            **SEED,
            "name": brand["name"],
            "domain": brand["domain"],
            "evidence": [{
                "id": f"{company_id}-online",
                "criterion": "US e-commerce",
                "fact": f"{brand['name']} sells {brand['category']} online.",
                "excerpt": "The directory lists the brand under United States in its digital-native and DTC segment.",
                "url": brand["url"],
                "checked_on": "2026-11-13",
            }],
        }


@asynccontextmanager
async def lifespan(_app):
    schema.create_all(engine)
    with engine.begin() as db:
        if db.scalar(select(control.c.id)) is None:
            db.execute(control.insert().values(id=1, sequence=0))
        existing = set(db.scalars(select(profiles.c.id)))
        for company_id, profile in seed_prospects():
            if company_id not in existing:
                db.execute(profiles.insert().values(id=company_id, record=profile))
    yield


app = FastAPI(title="Ledgerwise SDR", lifespan=lifespan)
basic = HTTPBasic(auto_error=False)
login_lock = Lock()
login_failures = 0
login_window = 0.0
MAX_WEBHOOK_BYTES = 1024 * 1024


def operator(request: Request, credentials: Annotated[HTTPBasicCredentials | None, Depends(basic)]):
    global login_failures, login_window
    origin = request.headers.get("origin")
    if request.method in {"POST", "PUT", "PATCH"} and origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Cross-origin workspace request.")
    password = os.getenv("WORKSPACE_PASSWORD")
    loopback = {"localhost", "127.0.0.1", "::1"}
    if (not password and DEMO and os.getenv("LEDGERWISE_LOCAL_DEMO") == "1"
            and request.client and request.client.host in loopback
            and request.url.hostname in loopback
            and not any(key in request.headers for key in (
                "forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto"
            ))
            and not os.getenv("OPENAI_API_KEY")):
        return
    if password and credentials:
        if (credentials.username == "ledgerwise"
                and compare_digest(credentials.password.encode(), password.encode())):
            return
        with login_lock:
            now = monotonic()
            if now >= login_window:
                login_window = now + 60
                login_failures = 0
            if login_failures >= 10:
                raise HTTPException(429, "Too many failed sign-in attempts.",
                                    headers={"Retry-After": str(int(login_window - now) + 1)})
            login_failures += 1
    raise HTTPException(401, "Workspace authentication required.",
                        headers={"WWW-Authenticate": "Basic"})


operator_only = [Depends(operator)]


@contextmanager
def transaction():
    with engine.begin() as db:
        # One writer at a time for the single-operator MVP, including provider actions.
        db.execute(update(control).where(control.c.id == 1).values(sequence=control.c.sequence + 1))
        yield db


def load(db, company_id):
    row = db.execute(select(profiles).where(profiles.c.id == company_id)).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "Company not found.")
    return {"id": row["id"], "contact": row["contact"], **row["record"]}


def save(db, profile):
    record = {key: value for key, value in profile.items() if key not in {"id", "contact"}}
    db.execute(update(profiles).where(profiles.c.id == profile["id"])
               .values(contact=profile["contact"], record=record))
    return profile


def active(profile):
    if profile["takeover"] or profile["status"] == "opt_out":
        raise HTTPException(409, "This conversation is paused or suppressed.")


def current_draft(profile, draft_id):
    if not profile["drafts"] or profile["drafts"][-1]["id"] != draft_id:
        raise HTTPException(409, "Reload and review the current draft version.")
    return profile["drafts"][-1]


class DraftContent(BaseModel):
    subject: str = Field(min_length=1, max_length=180)
    body: str = Field(min_length=1, max_length=6000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class Review(BaseModel):
    decision: Literal["approve", "reject"]
    sources_verified: bool = False


class Contact(BaseModel):
    address: EmailStr


class Slot(BaseModel):
    start: datetime


class DemoReply(BaseModel):
    body: str = Field(min_length=1, max_length=6000)


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False, dependencies=operator_only)
def dashboard():
    return FileResponse(STATIC / "index.html")


@app.get("/workspace.js", include_in_schema=False)
def workspace_script():
    return FileResponse(STATIC / "workspace.js", media_type="text/javascript")


@app.get("/api/companies", dependencies=operator_only)
def companies():
    with engine.connect() as db:
        return [{"id": row.id, "contact": row.contact, "fit_score": 40, **row.record}
                for row in db.execute(select(profiles).order_by(profiles.c.id))]


@app.get("/api/settings", dependencies=operator_only)
def settings():
    return {"demo": DEMO, "controlled_recipient": os.getenv("CONTROLLED_RECIPIENT") or None}


@app.post("/api/discovery", dependencies=operator_only)
def find_prospects():
    with engine.connect() as db:
        domains = {row["domain"] for row in db.scalars(select(profiles.c.record))}
    candidates = list(discovery.discover(domains))
    added = []
    with transaction() as db:
        domains = {row["domain"] for row in db.scalars(select(profiles.c.record))}
        for name, domain, evidence in candidates:
            if domain in domains:
                continue
            company_id = uuid4().hex
            criteria = {item["criterion"] for item in evidence}
            timing = next((item["fact"] for item in evidence if item["criterion"] == "Timing"), None)
            profile = {
                **SEED, "id": company_id, "contact": None, "name": name, "domain": domain,
                "evidence": evidence, "timing": timing,
                "fit_score": 40 + 30 * ("Revenue" in criteria) + 30 * ("Employees" in criteria),
                "discovered": True, "drafts": [], "replies": [],
            }
            record = {key: value for key, value in profile.items() if key not in {"id", "contact"}}
            db.execute(profiles.insert().values(id=company_id, record=record))
            if {"Revenue", "Employees"} <= criteria:
                draft = DraftContent.model_validate(providers.sourced_draft(name, evidence, local_only=True))
                append_draft(db, profile, draft)
            domains.add(domain)
            added.append(company_id)
    return {"added": added}


@app.put("/api/companies/{company_id}/contact", dependencies=operator_only)
def contact(company_id: str, data: Contact):
    if DEMO:
        raise HTTPException(409, "Demo sends use a simulated mailbox.")
    address = data.address.lower()
    if address != providers.setting("CONTROLLED_RECIPIENT").strip().lower():
        raise HTTPException(422, "Use the configured controlled mailbox.")
    with transaction() as db:
        profile = load(db, company_id)
        if profile["contact"] and profile["contact"] != address:
            raise HTTPException(409, "This company already has a controlled mailbox.")
        other = db.scalar(select(profiles.c.id).where(profiles.c.contact == address))
        if other and other != company_id:
            raise HTTPException(409, "This mailbox already belongs to another prospect.")
        profile["contact"] = address
        return save(db, profile)


@app.post("/api/companies/{company_id}/drafts", dependencies=operator_only)
def create_draft(company_id: str):
    with transaction() as db:
        profile = load(db, company_id)
        active(profile)
        if profile["drafts"]:
            raise HTTPException(409, "Open the existing draft to make changes.")
        try:
            draft = DraftContent.model_validate(providers.sourced_draft(
                profile["name"], profile["evidence"], local_only=DEMO
            ))
        except ValidationError as exc:
            raise HTTPException(502, "Draft provider returned invalid fields.") from exc
        return append_draft(db, profile, draft)


def append_draft(db, profile, draft):
    if not set(draft.evidence_ids) <= {item["id"] for item in profile["evidence"]}:
        raise HTTPException(422, "Draft cites evidence outside this company.")
    profile["drafts"].append({
        **draft.model_dump(), "id": uuid4().hex, "state": "pending",
        "version": len(profile["drafts"]) + 1,
    })
    return save(db, profile)


@app.patch("/api/companies/{company_id}/drafts/{draft_id}", dependencies=operator_only)
def edit_draft(company_id: str, draft_id: str, draft: DraftContent):
    with transaction() as db:
        profile = load(db, company_id)
        active(profile)
        old = current_draft(profile, draft_id)
        if old["state"] in {"sending", "sent"}:
            raise HTTPException(409, "A dispatched version cannot be edited.")
        old["state"] = "superseded"
        return append_draft(db, profile, draft)


@app.post("/api/companies/{company_id}/drafts/{draft_id}/review", dependencies=operator_only)
def review_draft(company_id: str, draft_id: str, data: Review):
    with transaction() as db:
        profile = load(db, company_id)
        active(profile)
        draft = current_draft(profile, draft_id)
        if draft["state"] != "pending":
            raise HTTPException(409, "Only a pending draft can be reviewed.")
        if data.decision == "approve" and profile.get("discovered"):
            if not data.sources_verified:
                raise HTTPException(422, "Verify the cited sources before approving.")
            draft["sources_verified"] = True
        draft["state"] = {"approve": "approved", "reject": "rejected"}[data.decision]
        return save(db, profile)


@app.post("/api/companies/{company_id}/drafts/{draft_id}/send", dependencies=operator_only)
def send_draft(company_id: str, draft_id: str):
    with transaction() as db:
        profile = load(db, company_id)
        draft = current_draft(profile, draft_id)
        if draft["state"] == "sent":
            return profile
        active(profile)
        if draft["state"] not in {"approved", "sending"}:
            raise HTTPException(409, "Approve this exact version before sending.")
        if profile.get("discovered") and not draft.get("sources_verified"):
            raise HTTPException(409, "Verify the cited sources on a new draft version.")
        if DEMO:
            return mark_sent(db, profile, draft, f"demo-{draft_id}")
        address = profile["contact"]
        if not address or address != providers.setting("CONTROLLED_RECIPIENT").strip().lower():
            raise HTTPException(409, "Set the controlled mailbox before sending.")
        if db.scalar(select(suppressions.c.address).where(suppressions.c.address == address)):
            raise HTTPException(409, "This mailbox is suppressed.")
        for name in ("RESEND_API_KEY", "MAIL_FROM", "MAIL_REPLY_TO"):
            providers.setting(name)
        if draft["state"] == "approved":
            draft["send_started"] = datetime.now(UTC).isoformat()
            draft["state"] = "sending"
            save(db, profile)

    with transaction() as db:
        profile = load(db, company_id)
        draft = current_draft(profile, draft_id)
        if draft["state"] == "sent":
            return profile
        active(profile)
        if db.scalar(select(suppressions.c.address).where(suppressions.c.address == address)):
            raise HTTPException(409, "This mailbox is suppressed.")
        if datetime.now(UTC) - datetime.fromisoformat(draft["send_started"]) >= timedelta(hours=23):
            raise HTTPException(409, "Check Resend for delivery. The safe retry window has expired.")
        provider_id = providers.send_email(address, draft, f"ledgerwise/{draft_id}")
        return mark_sent(db, profile, draft, provider_id)


def mark_sent(db, profile, draft, provider_id):
    draft["provider_id"] = provider_id
    draft["state"] = "sent"
    if profile["status"] == "research":
        profile["status"] = "sent"
    return save(db, profile)


def classify_reply(body):
    # Stop at the first quoted message or signature delimiter.
    lines = []
    for line in body.splitlines():
        if line.startswith((">", "-- ")) or re.match(r"^On .+wrote:$", line.strip()):
            break
        lines.append(line)
    text = " ".join(lines).lower().replace("’", "'")
    if re.search(r"\bunsubscribe\b|\bopt[ -]out\b|\bnot interested\b|\bno thanks\b|\b(?:stop|do not|don't|no more)\s+(?:email|contact|send|message)", text):
        return "opt_out"
    if re.search(r"\b(?:bot|automated)\b", text):
        return "bot_question"
    if re.search(r"\b(?:pricing|price|cost|rates)\b", text):
        return "pricing_question"
    if re.search(r"\b(?:not|never)\s+available\b|\bunavailable\b|\bcan't\s+(?:meet|talk|schedule)\b", text):
        return "human_review"
    if re.search(r"\b(?:let's (?:meet|talk|schedule)|available (?:on|next|for)|book a call|schedule a call)\b", text):
        return "meeting_interest"
    return "human_review"


@app.post("/webhooks/email/inbound")
async def receive_email(request: Request):
    if DEMO:
        raise HTTPException(404, "Live email webhook is disabled in demo mode.")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_WEBHOOK_BYTES:
            raise HTTPException(413, "Webhook payload too large.")
        raw.extend(chunk)
    try:
        event = Webhook(providers.setting("RESEND_WEBHOOK_SECRET")).verify(bytes(raw), dict(request.headers))
    except (WebhookVerificationError, ValueError) as exc:
        raise HTTPException(401, "Invalid webhook signature.") from exc
    if event.get("type") != "email.received":
        return {"status": "ignored"}
    return await run_in_threadpool(process_inbound, event["data"])


def process_inbound(data):
    receipt = data["email_id"]
    address = parseaddr(data["from"])[1].lower()
    recipient = parseaddr(providers.setting("MAIL_REPLY_TO"))[1].lower()
    if recipient not in [parseaddr(item)[1].lower() for item in data["to"]]:
        return {"status": "ignored"}
    with transaction() as db:
        if db.scalar(select(inbound.c.id).where(inbound.c.id == receipt)):
            return {"status": "duplicate"}
        company_id = db.scalar(select(profiles.c.id).where(profiles.c.contact == address))
        if not company_id:
            return {"status": "ignored"}
        email = providers.resend("GET", "/emails/receiving/" + receipt)
        body = email.get("text") or ""
        profile = load(db, company_id)
        profile["replies"].append({
            "id": receipt, "body": body, "intent": "human_review",
            "received_at": data.get("created_at"), "verification_pending": True,
        })
        save(db, profile)
        db.execute(inbound.insert().values(id=receipt))
    return {"status": "processed"}


@app.post("/api/companies/{company_id}/replies/{receipt}/verify", dependencies=operator_only)
def verify_reply(company_id: str, receipt: str):
    with transaction() as db:
        profile = load(db, company_id)
        reply = next((item for item in profile["replies"] if item.get("id") == receipt), None)
        if reply is None:
            raise HTTPException(404, "Reply not found.")
        if not reply.get("verification_pending"):
            return profile
        if not any(draft["state"] == "sent" for draft in profile["drafts"]):
            raise HTTPException(409, "Verification requires an outbound email.")
        reply["verification_pending"] = False
        return record_reply(db, profile, reply["body"], reply["received_at"], reply=reply)


def record_reply(db, profile, body, received_at, *, reply=None):
    intent = classify_reply(body)
    if reply is None:
        profile["replies"].append({"body": body, "intent": intent, "received_at": received_at})
    else:
        reply["intent"] = intent
    if intent == "opt_out":
        profile["status"] = intent
        address = profile["contact"]
        if address and not db.scalar(select(suppressions.c.address).where(suppressions.c.address == address)):
            db.execute(suppressions.insert().values(address=address))
    elif profile["status"] != "opt_out" and not profile["booking"]:
        reply_templates = {
            "pricing_question": "Thanks for asking. We can discuss your bookkeeping needs and pricing on a short introductory call. Would that help?",
            "bot_question": "Yes, Ledgerwise uses automation to help draft emails. A person at Ledgerwise reviews messages before sending them.",
        }
        profile["status"] = "human_review" if intent in reply_templates else intent
        if (intent in reply_templates and not profile["takeover"]
                and profile["drafts"] and profile["drafts"][-1]["state"] == "sent"):
            previous = profile["drafts"][-1]
            subject = previous["subject"]
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"
            return append_draft(db, profile, DraftContent(
                subject=subject[:180], body=reply_templates[intent],
                evidence_ids=previous["evidence_ids"],
            ))
    return save(db, profile)


@app.post("/api/companies/{company_id}/demo-replies", dependencies=operator_only)
def demo_reply(company_id: str, data: DemoReply):
    if not DEMO:
        raise HTTPException(404, "Simulated replies require demo mode.")
    with transaction() as db:
        profile = load(db, company_id)
        if not any(draft["state"] == "sent" for draft in profile["drafts"]):
            raise HTTPException(409, "Send a demo email before simulating a reply.")
        return record_reply(db, profile, data.body, datetime.now(UTC).isoformat())


@app.post("/api/companies/{company_id}/takeover", dependencies=operator_only)
def takeover(company_id: str):
    with transaction() as db:
        profile = load(db, company_id)
        profile["takeover"] = True
        return save(db, profile)


def candidate_slots(now):
    for day in range(1, 8):
        date = now + timedelta(days=day)
        if date.weekday() < 5:
            for hour in (15, 16, 17):
                yield date.replace(hour=hour, minute=0, second=0, microsecond=0)


def overlaps(start, end, busy):
    return any(start < datetime.fromisoformat(item["end"])
               and end > datetime.fromisoformat(item["start"]) for item in busy)


def ready_to_book(profile):
    active(profile)
    if profile["status"] != "meeting_interest":
        raise HTTPException(409, "Booking requires an interested reply.")
    if not DEMO and not any(
        reply.get("verification_pending") is False and reply["intent"] == "meeting_interest"
        for reply in profile["replies"]
    ):
        raise HTTPException(409, "Booking requires a verified interested reply.")


def demo_busy(db):
    return [record["booking"] for record in db.scalars(select(profiles.c.record)) if record["booking"]]


@app.get("/api/companies/{company_id}/slots", dependencies=operator_only)
def slots(company_id: str):
    with engine.connect() as db:
        ready_to_book(load(db, company_id))
    candidates = list(candidate_slots(datetime.now(UTC)))
    duration = timedelta(minutes=30)
    if DEMO:
        with engine.connect() as db:
            busy = demo_busy(db)
    else:
        busy = providers.Calendar().busy(candidates[0], candidates[-1] + duration)
    return [start for start in candidates if not overlaps(start, start + duration, busy)]


@app.post("/api/companies/{company_id}/bookings", dependencies=operator_only)
def book(company_id: str, slot: Slot):
    if slot.start.utcoffset() is None:
        raise HTTPException(422, "Supply a timezone with the selected slot.")
    start = slot.start.astimezone(UTC)
    end = start + timedelta(minutes=30)
    with transaction() as db:
        profile = load(db, company_id)
        if profile["booking"]:
            if profile["booking"]["start"] == start.isoformat():
                return profile
            raise HTTPException(409, "A meeting is already booked for this company.")
        ready_to_book(profile)
        event_id = sha256(f"ledgerwise/{company_id}/{start.isoformat()}".encode()).hexdigest()
        calendar = None if DEMO else providers.Calendar()
        event = None if DEMO else calendar.event(event_id)
        evidence = "\n".join(f"{item['fact']} ({item['url']})" for item in profile["evidence"])
        replies = "\n\n".join(item["body"] for item in profile["replies"]
                               if item["intent"] == "meeting_interest")
        brief = (
            f"Company research\n{evidence}\n\nWhy we reached out\nIntroductory outreach about "
            f"e-commerce bookkeeping. Recent timing signal: {profile['timing'] or 'unknown'}.\n\n"
            f"Interested replies\n{replies[:3000]}\n\nQuestions for the call\n"
            "How do you handle bookkeeping today? Where does your current process take the most time?"
        )
        if event is None:
            if start not in set(candidate_slots(datetime.now(UTC))):
                raise HTTPException(422, "Choose a slot from the current availability list.")
            busy = overlaps(start, end, demo_busy(db)) if DEMO else calendar.busy(start, end)
            if busy:
                raise HTTPException(409, "This slot is no longer available. Refresh availability.")
            event = {"id": f"demo-{event_id}"} if DEMO else calendar.book(
                event_id, profile["name"], start, end, brief
            )
        profile["booking"] = {
            "event_id": event["id"], "url": event.get("htmlLink"), "start": start.isoformat(),
            "end": end.isoformat(), "brief": brief,
        }
        profile["status"] = "booked"
        return save(db, profile)
