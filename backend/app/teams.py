"""Microsoft Teams (Education) connector.

Uses Microsoft Graph with delegated permissions on behalf of the signed-in student:
  EduAssignments.ReadBasic  -> /education/me/assignments (+ their submission status)
  EduRoster.ReadBasic       -> /education/me/classes (class names)
  User.Read                 -> who connected
None of these require tenant admin consent by default, but a school can still block user
consent for third-party apps. That case is detected and reported, never worked around.

Tokens are held in an MSAL token cache that is encrypted before it is stored, so the
backend can keep syncing in the background without the student reopening the app.
"""

import html
import json
import logging
import os
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
import msal
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Connection, Course, Coursework, CourseworkChange, OAuthState, Submission, User
from .academic import notify
from .security import decrypt, encrypt

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["EduAssignments.ReadBasic", "EduRoster.ReadBasic", "User.Read"]
PROVIDER = "teams"
TEAMS_COLORS = ["#5b5fc7", "#2f5d50", "#b5562b", "#7a4f9a", "#2d6a8e", "#8a6d1f", "#a23b5a"]
CONSENT_ERRORS = ("AADSTS65001", "AADSTS90094", "AADSTS90008", "AADSTS65004", "consent_required", "admin")
MAX_DETAIL_FETCHES = 25


class TeamsError(RuntimeError):
    def __init__(self, message: str, status: str = "error") -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Settings:
    client_id: str
    client_secret: str
    tenant: str
    redirect_uri: str
    frontend_url: str

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant}"


def settings() -> Settings | None:
    client_id = os.getenv("MS_CLIENT_ID", "").strip()
    client_secret = os.getenv("MS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    frontend = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    return Settings(
        client_id=client_id,
        client_secret=client_secret,
        tenant=os.getenv("MS_TENANT", "organizations").strip() or "organizations",
        redirect_uri=os.getenv("MS_REDIRECT_URI", f"{frontend}/api/integrations/teams/callback"),
        frontend_url=frontend,
    )


def auto_sync_minutes() -> int:
    try:
        return max(0, int(os.getenv("TEAMS_AUTO_SYNC_MINUTES", "30")))
    except ValueError:
        return 30


def _app(config: Settings, cache: msal.SerializableTokenCache | None = None) -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        config.client_id,
        authority=config.authority,
        client_credential=config.client_secret,
        token_cache=cache,
    )


def is_consent_error(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in CONSENT_ERRORS)


def consent_message() -> str:
    return (
        "Your school's Microsoft 365 settings require an administrator to approve UniTask before it can "
        "read your Teams assignments. Ask your IT admin to grant consent for this app "
        "(EduAssignments.ReadBasic, EduRoster.ReadBasic, User.Read)."
    )


# ---------- OAuth: connect + callback ----------


def begin_connect(db: Session, user: User) -> str:
    config = settings()
    if config is None:
        raise TeamsError("Teams is not configured on this server (MS_CLIENT_ID / MS_CLIENT_SECRET).", "error")
    flow = _app(config).initiate_auth_code_flow(
        SCOPES,
        redirect_uri=config.redirect_uri,
        state=secrets.token_urlsafe(24),
        prompt="select_account",
        response_mode="form_post",  # keeps the auth code out of URLs and logs
    )
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    for stale in db.scalars(select(OAuthState).where(OAuthState.created_at < cutoff)):
        db.delete(stale)
    db.add(OAuthState(state=flow["state"], user_id=user.id, flow=encrypt(json.dumps(flow))))
    db.commit()
    return flow["auth_uri"]


def _connection(db: Session, user_id: int) -> Connection:
    connection = db.scalar(select(Connection).where(Connection.user_id == user_id, Connection.provider == PROVIDER))
    if connection is None:
        connection = Connection(user_id=user_id, provider=PROVIDER, status="not_connected")
        db.add(connection)
    return connection


def complete_connect(db: Session, params: dict[str, str]) -> tuple[User | None, str]:
    """Handle the redirect back from Microsoft. Returns the user and an outcome keyword."""
    config = settings()
    state = params.get("state", "")
    pending = db.get(OAuthState, state) if state else None
    if config is None or pending is None:
        return None, "expired"
    user = db.get(User, pending.user_id)
    flow_json = decrypt(pending.flow)
    db.delete(pending)
    connection = _connection(db, pending.user_id)

    if "error" in params or flow_json is None:
        description = params.get("error_description") or params.get("error") or "Sign-in was cancelled."
        connection.status = "needs_consent" if is_consent_error(description) else "error"
        connection.last_error = consent_message() if connection.status == "needs_consent" else description[:500]
        db.commit()
        return user, connection.status

    cache = msal.SerializableTokenCache()
    result = _app(config, cache).acquire_token_by_auth_code_flow(json.loads(flow_json), params)
    if "error" in result:
        description = f"{result.get('error')}: {result.get('error_description', '')}"
        connection.status = "needs_consent" if is_consent_error(description) else "error"
        connection.last_error = consent_message() if connection.status == "needs_consent" else description[:500]
        db.commit()
        return user, connection.status

    claims = result.get("id_token_claims", {})
    connection.status = "connected"
    connection.account_label = claims.get("preferred_username") or claims.get("email") or claims.get("name")
    connection.token_cache = encrypt(cache.serialize())
    connection.last_error = None
    db.commit()
    return user, "connected"


def access_token(db: Session, connection: Connection) -> str:
    config = settings()
    if config is None:
        raise TeamsError("Teams is not configured on this server.")
    raw = decrypt(connection.token_cache) if connection.token_cache else None
    if not raw:
        raise TeamsError("Reconnect Microsoft Teams to continue syncing.", "expired")
    cache = msal.SerializableTokenCache()
    cache.deserialize(raw)
    app = _app(config, cache)
    accounts = app.get_accounts()
    result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
    if not result or "access_token" not in result:
        detail = (result or {}).get("error_description", "")
        if detail and is_consent_error(detail):
            raise TeamsError(consent_message(), "needs_consent")
        raise TeamsError("Your Microsoft sign-in has expired. Reconnect Teams.", "expired")
    if cache.has_state_changed:
        connection.token_cache = encrypt(cache.serialize())
    return result["access_token"]


# ---------- Graph ----------


class GraphClient:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            base_url=GRAPH,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
            transport=transport,
        )

    def get(self, path: str) -> dict:
        response = self._client.get(path)
        if response.status_code == 403 or (response.status_code == 401 and is_consent_error(response.text)):
            raise TeamsError(
                "Microsoft refused access to Teams assignments for this account. Either the school has not "
                "approved this app, or the account is not part of a Teams for Education class.",
                "needs_consent",
            )
        if response.status_code == 401:
            raise TeamsError("Your Microsoft sign-in has expired. Reconnect Teams.", "expired")
        response.raise_for_status()
        return response.json()

    def get_all(self, path: str, limit: int = 2000) -> list[dict]:
        items: list[dict] = []
        page = self.get(path)
        items.extend(page.get("value", []))
        while page.get("@odata.nextLink") and len(items) < limit:
            page = self.get(page["@odata.nextLink"].replace(GRAPH, ""))
            items.extend(page.get("value", []))
        return items

    def close(self) -> None:
        self._client.close()


# ---------- Sync ----------


@dataclass
class SyncResult:
    classes: int = 0
    assignments: int = 0
    new: int = 0
    updated: int = 0
    due_changed: int = 0
    removed: int = 0
    turned_in: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Teams uses year 9999 for "no due date".
    if parsed.year >= 9000:
        return None
    return parsed.astimezone(timezone.utc)


def html_to_text(content: str | None) -> str | None:
    if not content:
        return None
    text = re.sub(r"<\s*(br|/p|/div|/li)\s*/?>", "\n", content, flags=re.I)
    text = re.sub(r"<li[^>]*>", "• ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None


def _submission_status(assignment: dict) -> str | None:
    submissions = assignment.get("submissions") or []
    if not submissions:
        return None
    status = submissions[0].get("status")
    return {"submitted": "turned_in", "returned": "returned", "working": "assigned", "reassigned": "assigned"}.get(
        status
    )


def _fmt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def sync_user(db: Session, user: User, graph: GraphClient, now: datetime | None = None) -> SyncResult:
    now = now or datetime.now(timezone.utc)
    result = SyncResult()

    existing_courses = {
        course.external_id: course
        for course in db.scalars(select(Course).where(Course.owner_id == user.id, Course.source == PROVIDER))
    }
    first_sync = not existing_courses

    classes = graph.get_all("/education/me/classes?$select=id,displayName,description,classCode")
    for index, cls in enumerate(classes):
        course = existing_courses.get(cls["id"])
        if course is None:
            course = Course(
                owner_id=user.id,
                source=PROVIDER,
                external_id=cls["id"],
                color=TEAMS_COLORS[(len(existing_courses) + index) % len(TEAMS_COLORS)],
                name=cls.get("displayName") or "Teams class",
            )
            db.add(course)
            existing_courses[cls["id"]] = course
        course.name = (cls.get("displayName") or course.name)[:160]
        course.code = (cls.get("classCode") or "")[:30]
        course.description = cls.get("description")
    db.flush()
    result.classes = len(classes)

    assignments = graph.get_all("/education/me/assignments?$expand=submissions")
    existing_work = {
        work.external_id: work
        for work in db.scalars(select(Coursework).where(Coursework.owner_id == user.id, Coursework.source == PROVIDER))
    }
    seen_ids: set[str] = set()
    detail_budget = MAX_DETAIL_FETCHES

    for item in assignments:
        if item.get("status") not in {"assigned", "published"}:
            continue
        external_id = item["id"]
        seen_ids.add(external_id)
        result.assignments += 1
        due_at = _parse_dt(item.get("dueDateTime"))
        title = (item.get("displayName") or "Untitled assignment")[:200]
        course = existing_courses.get(item.get("classId"))
        modified = _parse_dt(item.get("lastModifiedDateTime"))
        points = (item.get("grading") or {}).get("maxPoints")

        work = existing_work.get(external_id)
        if work is None:
            work = Coursework(
                owner_id=user.id,
                source=PROVIDER,
                external_id=external_id,
                title=title,
                due_at=due_at,
                course_id=course.id if course else None,
                due_confidence="verified",
            )
            db.add(work)
            db.flush()
            db.add(CourseworkChange(coursework_id=work.id, kind="created", new_value=_fmt(due_at), seen=first_sync))
            if not first_sync:
                notify(db, user.id, "new_work", f"New in Teams: {title}", f"new:teams:{external_id}",
                       body=f"{course.name if course else 'Teams'} · due {_fmt(due_at) or 'no date'}", link=f"/work/{work.id}", source=PROVIDER)
            result.new += 1
            needs_detail = True
        else:
            needs_detail = work.last_synced_at is None or (modified is not None and modified > work.last_synced_at)
            if work.due_at != due_at:
                db.add(
                    CourseworkChange(
                        coursework_id=work.id, kind="due_changed", old_value=_fmt(work.due_at), new_value=_fmt(due_at)
                    )
                )
                notify(db, user.id, "due_changed", f"Teams moved a deadline: {title}", f"due:{work.id}:{_fmt(due_at)}",
                       body=f"{_fmt(work.due_at) or 'no date'} → {_fmt(due_at) or 'no date'}", link=f"/work/{work.id}", source=PROVIDER)
                result.due_changed += 1
            if work.title != title:
                db.add(CourseworkChange(coursework_id=work.id, kind="title_changed", old_value=work.title, new_value=title))
            if work.removed_at_source:
                work.removed_at_source = False
            if needs_detail or work.due_at != due_at or work.title != title:
                result.updated += 1

        work.title = title
        work.due_at = due_at
        work.course_id = course.id if course else work.course_id
        work.points = int(points) if isinstance(points, (int, float)) else None
        work.allow_late = bool(item.get("allowLateSubmissions", True))
        work.external_url = item.get("webUrl") or work.external_url

        upcoming = due_at is None or due_at > now - timedelta(days=2)
        if needs_detail and upcoming and detail_budget > 0 and item.get("classId"):
            detail_budget -= 1
            try:
                detail = graph.get(
                    f"/education/classes/{item['classId']}/assignments/{external_id}?$select=instructions,webUrl"
                )
                work.instructions = html_to_text((detail.get("instructions") or {}).get("content"))
                work.external_url = detail.get("webUrl") or work.external_url
            except (TeamsError, httpx.HTTPError) as exc:
                logger.info("Could not fetch Teams assignment details for %s: %s", external_id, exc)
        work.last_synced_at = now

        status = _submission_status(item)
        if status is not None:
            submission = db.scalar(
                select(Submission).where(Submission.coursework_id == work.id, Submission.student_id == user.id)
            )
            if submission is None:
                submission = Submission(coursework_id=work.id, student_id=user.id, status="assigned")
                db.add(submission)
            submission.source_status = {"turned_in": "submitted", "returned": "returned"}.get(status, "working")
            if status in {"turned_in", "returned"}:
                if submission.status not in {"turned_in", "returned"}:
                    submission.submitted_at = submission.submitted_at or now
                submission.status = status
                result.turned_in += 1
            elif submission.status in {"turned_in", "returned"}:
                # Unsubmitted or reassigned in Teams; Teams is the authority for Teams work.
                submission.status = "assigned"

    for external_id, work in existing_work.items():
        if external_id not in seen_ids and not work.removed_at_source:
            work.removed_at_source = True
            db.add(CourseworkChange(coursework_id=work.id, kind="removed", old_value=work.title))
            notify(db, user.id, "removed", f"Removed from Teams: {work.title}", f"removed:teams:{external_id}", link=f"/work/{work.id}", source=PROVIDER)
            result.removed += 1

    if first_sync and result.assignments:
        result.notes.append("First sync: existing assignments were imported quietly.")
    return result


def sync_connection(
    db: Session,
    connection: Connection,
    graph_factory: Callable[[str], GraphClient] = GraphClient,
) -> SyncResult:
    user = db.get(User, connection.user_id)
    try:
        token = access_token(db, connection)
        graph = graph_factory(token)
        try:
            result = sync_user(db, user, graph)
        finally:
            graph.close()
    except TeamsError as exc:
        db.rollback()
        connection = db.get(Connection, connection.id)
        connection.status = exc.status
        connection.last_error = str(exc)
        db.commit()
        raise
    except httpx.HTTPError as exc:
        db.rollback()
        connection = db.get(Connection, connection.id)
        connection.status = "error"
        connection.last_error = f"Microsoft Graph request failed: {exc}"[:500]
        db.commit()
        raise TeamsError(connection.last_error) from exc

    connection.status = "connected"
    connection.last_error = None
    connection.last_synced_at = datetime.now(timezone.utc)
    connection.last_result = json.dumps(result.as_dict())
    db.commit()
    logger.info("Teams sync for user %s: %s", user.id, result.as_dict())
    return result
