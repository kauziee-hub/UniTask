"""Job handlers. Each opens its own session and is safe to run twice."""

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from . import ics, teams
from .academic import notify, process_material
from .academic_models import InboxEvent, Profile
from .database import SessionLocal
from .ingest import ingest
from .netguard import safe_get
from .jobs import handler
from .models import Connection, Coursework, Submission, User
from .security import decrypt
from .services import student_coursework_query

logger = logging.getLogger(__name__)


@handler("process_material")
def _process_material(payload: dict) -> None:
    with SessionLocal() as db:
        process_material(db, int(payload["material_id"]))


def send_email(to: str, subject: str, body: str) -> bool:
    """EMAIL_PROVIDER=ses sends through Amazon SES; anything else only logs (local development)."""
    if os.getenv("EMAIL_PROVIDER", "log").lower() != "ses":
        logger.info("EMAIL (not sent, EMAIL_PROVIDER=log) to=%s subject=%s", to, subject)
        return False
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    profile = os.getenv("AWS_PROFILE") or None
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    client = session.client("ses", region_name=os.getenv("SES_REGION") or os.getenv("AWS_REGION", "ap-south-1"))
    try:
        client.send_email(
            Source=os.environ["SES_FROM_ADDRESS"],
            Destination={"ToAddresses": [to]},
            Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}},
        )
        return True
    except (BotoCoreError, ClientError, KeyError) as exc:
        logger.warning("SES send failed: %s", exc)
        return False


@handler("reminders")
def _reminders(payload: dict) -> None:
    """Deadline reminders 24h ahead: one inbox event per item (idempotent), optional email digest."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for user in db.scalars(select(User).where(User.role == "student")):
            due_soon = []
            for work in db.scalars(student_coursework_query(user).where(Coursework.due_at > now, Coursework.due_at <= now + timedelta(hours=24))):
                submission = db.scalar(select(Submission).where(Submission.coursework_id == work.id, Submission.student_id == user.id))
                if submission and (submission.status in {"turned_in", "returned"} or submission.local_done_at):
                    continue
                if notify(db, user.id, "reminder", f"Due within 24h: {work.title}", f"remind24:{work.id}:{work.due_at.isoformat()}",
                          link=f"/work/{work.id}", body=f"Due {work.due_at:%a %d %b %H:%M} UTC"):
                    due_soon.append(work.title)
            if due_soon and send_email(user.email, f"UniTask: {len(due_soon)} due in the next 24 hours", "\n".join(f"• {t}" for t in due_soon)):
                for event in db.scalars(select(InboxEvent).where(InboxEvent.user_id == user.id, InboxEvent.kind == "reminder", InboxEvent.emailed_at.is_(None))):
                    event.emailed_at = now
        db.commit()


def sync_feed(db, connection: Connection) -> dict:
    """Fetch a student's Moodle/iCalendar feed URL and ingest it as a full snapshot."""
    url = decrypt(connection.config) if connection.config else None
    if not url:
        raise ValueError("No feed URL saved.")
    profile = db.get(Profile, connection.user_id)
    response = safe_get(url)
    response.raise_for_status()
    if "BEGIN:VCALENDAR" not in response.text[:500]:
        raise ValueError("That link didn't return an iCalendar file.")
    events = ics.parse(response.text, provider=connection.provider, default_tz=profile.timezone if profile else "Asia/Kolkata")
    result = ingest(db, connection.user_id, connection.provider, events, full_snapshot=True)
    connection.status, connection.last_error = "connected", None
    connection.last_synced_at = datetime.now(timezone.utc)
    return result.as_dict()


@handler("sync_all")
def _sync_all(payload: dict) -> None:
    with SessionLocal() as db:
        connections = list(db.scalars(select(Connection).where(Connection.status.in_(["connected", "error"]))))
        for connection in connections:
            try:
                if connection.provider == teams.PROVIDER and connection.token_cache and teams.settings():
                    teams.sync_connection(db, connection)
                elif connection.provider == "moodle_ics":
                    sync_feed(db, connection)
                db.commit()
            except Exception as exc:  # noqa: BLE001 — one broken connection must not stop the others
                db.rollback()
                connection = db.get(Connection, connection.id)
                connection.status, connection.last_error = "error", str(exc)[:500]
                notify(db, connection.user_id, "sync_error", f"{connection.provider} sync failed", f"syncerr:{connection.id}:{datetime.now(timezone.utc):%Y%m%d%H}",
                       body=str(exc)[:300], link="/connections", source=connection.provider)
                db.commit()
