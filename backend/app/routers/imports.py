"""Getting coursework in: file imports, Moodle calendar feeds, quick capture, the VTOP extension,
data from the original UniTask, and a clearly labelled demo workspace."""

import csv
import hashlib
import io
import json
import os
import re
import secrets
from datetime import date, datetime, time, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from .. import ics, llm
from ..academic import audit, link_material_topics, save_questions, save_syllabus, sha256
from ..academic_models import Exam, Material, MaterialPage, PlanBlock, Profile, TimetableEntry
from ..academic_schemas import CaptureRequest, ExtensionIngest, FeedConnect, LegacyImport
from ..database import get_db
from ..ingest import SourceEvent, ingest, match_course
from ..job_handlers import sync_feed
from ..models import Connection, Course, Coursework, TimetableUpload, User
from ..netguard import UnsafeURL, check_url
from ..security import encrypt, require_student
from ..services import get_submission, read_upload, to_work_item
from ..storage import ValidatedUpload, get_storage
from ..workspace import profile_for, utcnow, zone

router = APIRouter(prefix="/api", tags=["imports"])
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
FIELDS = {
    "title": ("title", "name", "assignment", "task"),
    "due": ("due", "due_at", "due date", "duedate", "deadline", "date"),
    "subject": ("subject", "course", "code", "course code", "subject code", "module"),
    "kind": ("kind", "type", "category"),
    "description": ("description", "notes", "instructions", "details"),
    "url": ("url", "link"),
    "id": ("id", "external_id", "uid"),
}


# ---------------------------------------------------------------- dates


def parse_when(value, tz) -> datetime | None:
    """ISO datetimes, ISO dates, DD/MM/YYYY and '12 Nov [2026] [5pm]'. Date-only means end of that day."""
    if value in (None, ""):
        return None
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if len(raw) <= 10:
            return datetime.combine(parsed.date(), time(23, 59), tz)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)
    except ValueError:
        pass
    found = find_date(raw, tz, today=datetime.now(tz).date())
    return found


def find_date(text_value: str, tz, today: date) -> datetime | None:
    lowered = text_value.lower()
    day = None
    if m := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", lowered):
        day = date(int(m[1]), int(m[2]), int(m[3]))
    elif m := re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", lowered):
        year = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        try:
            day = date(year, int(m[2]), int(m[1]))  # day-first, as written in India and the UK
        except ValueError:
            return None
    elif m := re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:,?\s+(\d{4}))?", lowered):
        year = int(m[3]) if m[3] else today.year
        day = date(year, MONTHS[m[2]], int(m[1]))
        if not m[3] and day < today - timedelta(days=30):
            day = day.replace(year=year + 1)
    elif m := re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", lowered):
        year = int(m[3]) if m[3] else today.year
        day = date(year, MONTHS[m[1]], int(m[2]))
        if not m[3] and day < today - timedelta(days=30):
            day = day.replace(year=year + 1)
    elif "tomorrow" in lowered:
        day = today + timedelta(days=1)
    elif "today" in lowered or "tonight" in lowered:
        day = today
    if day is None:
        return None
    clock = time(23, 59)
    if t := re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lowered):
        hour = int(t[1]) % 12 + (12 if t[3] == "pm" else 0)
        clock = time(hour, int(t[2] or 0))
    elif t := re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", lowered):
        clock = time(int(t[1]), int(t[2]))
    return datetime.combine(day, clock, tz)


def _pick(row: dict, field: str):
    lowered = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
    for name in FIELDS[field]:
        if lowered.get(name) not in (None, ""):
            return lowered[name]
    return None


def _kind(value) -> str:
    v = str(value or "").lower()
    for kind in ("quiz", "lab", "assessment", "task"):
        if kind in v:
            return kind
    return "assessment" if re.search(r"\b(exam|test|cat|fat)\b", v) else "assignment"


def rows_to_events(rows: list[dict], provider: str, tz) -> tuple[list[SourceEvent], list[str]]:
    events, skipped = [], []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            skipped.append(f"Row {index}: not a record")
            continue
        title = str(_pick(row, "title") or "").strip()
        if not title:
            skipped.append(f"Row {index}: no title")
            continue
        due_raw = _pick(row, "due")
        due = parse_when(due_raw, tz)
        if due_raw and due is None:
            skipped.append(f"Row {index} ({title}): couldn't read the date “{due_raw}”")
            continue
        subject = _pick(row, "subject")
        given_id = _pick(row, "id")
        external = str(given_id) if given_id else hashlib.sha1(f"{title}|{due_raw}|{subject}".encode()).hexdigest()[:20]
        events.append(
            SourceEvent(
                provider=provider,
                external_id=external[:255],
                title=title[:200],
                due_at=due,
                description=str(_pick(row, "description") or "") or None,
                url=str(_pick(row, "url") or "") or None,
                subject=str(subject).strip() if subject else None,
                kind=_kind(_pick(row, "kind") or title),
                confidence="manual",
            )
        )
    return events, skipped


def _legacy_rows(data: dict) -> list[dict]:
    """The original UniTask export: {subjects:[{id,name,code}], assignments:[{title,subjectId,dueDate,status,platform}]}"""
    subjects = {s.get("id"): s for s in data.get("subjects", []) if isinstance(s, dict)}
    rows = []
    for a in data.get("assignments", []):
        if not isinstance(a, dict):
            continue
        subject = subjects.get(a.get("subjectId"), {})
        rows.append(
            {
                "id": f"legacy:{a.get('id')}" if a.get("id") else None,
                "title": a.get("title"),
                "due": a.get("dueDate"),
                "subject": subject.get("code") or subject.get("name"),
                "description": a.get("description") or (f"Imported from {a['platform']}" if a.get("platform") else None),
                "_status": a.get("status"),
            }
        )
    return rows


# ---------------------------------------------------------------- file import


@router.post("/import/file")
async def import_file(file: UploadFile = File(...), user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    name = (file.filename or "").lower()
    if not name.endswith((".csv", ".json", ".ics")):
        raise HTTPException(415, "Import a .csv, .json or .ics (calendar) file.")
    validated: ValidatedUpload = await read_upload(file, 2 * 1024 * 1024)
    text_value = validated.content.decode("utf-8-sig")
    tz = zone(profile_for(db, user))
    skipped: list[str] = []
    statuses: dict[str, str] = {}
    if name.endswith(".ics"):
        if "BEGIN:VCALENDAR" not in text_value:
            raise HTTPException(422, "That isn't an iCalendar file.")
        provider, events = "ics", ics.parse(text_value, provider="ics", default_tz=tz.key)
        for event in events:
            event.confidence = "manual"
    elif name.endswith(".json"):
        try:
            data = json.loads(text_value)
        except json.JSONDecodeError as exc:
            raise HTTPException(422, f"That JSON file couldn't be read: {exc.msg}.") from exc
        if isinstance(data, dict) and "assignments" in data:
            _ensure_legacy_subjects(db, user, data.get("subjects", []))
            rows = _legacy_rows(data)
            statuses = {r["id"]: r["_status"] for r in rows if r.get("id") and r.get("_status")}
        elif isinstance(data, list):
            rows = data
        else:
            raise HTTPException(422, "Use a list of assignments, or a UniTask export with an \"assignments\" list.")
        provider = "json"
        events, skipped = rows_to_events(rows, provider, tz)
    else:
        rows = list(csv.DictReader(io.StringIO(text_value)))
        if not rows:
            raise HTTPException(422, "That CSV has no rows. The first line should be headers such as title,due,subject.")
        provider = "csv"
        events, skipped = rows_to_events(rows, provider, tz)
    if not events:
        raise HTTPException(422, "Nothing to import. " + ("; ".join(skipped[:5]) if skipped else "No rows had a title."))
    result = ingest(db, user.id, provider, events)
    _apply_legacy_status(db, user, provider, statuses)
    audit(db, user.id, "import.file", provider, **result.as_dict())
    db.commit()
    return {**result.as_dict(), "skipped": skipped[:20], "provider": provider}


def _ensure_legacy_subjects(db: Session, user: User, subjects: list) -> None:
    for s in subjects:
        if not isinstance(s, dict) or not (s.get("name") or s.get("code")):
            continue
        course = match_course(db, user.id, s.get("code") or s.get("name"), create=False)
        if course is None:
            color = s.get("color") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(s.get("color", ""))) else "#2f5d50"
            db.add(Course(name=str(s.get("name") or s.get("code"))[:160], code=str(s.get("code") or "")[:30].upper(), color=color, owner_id=user.id, source="personal"))
            db.flush()


def _apply_legacy_status(db: Session, user: User, provider: str, statuses: dict[str, str]) -> None:
    from ..models import CourseworkSource

    for external_id, status in statuses.items():
        link = db.scalar(select(CourseworkSource).where(CourseworkSource.owner_id == user.id, CourseworkSource.provider == provider, CourseworkSource.external_id == external_id))
        if link is None:
            continue
        work = db.get(Coursework, link.coursework_id)
        submission = get_submission(db, work, user, create=True)
        if status == "Completed" and not submission.local_done_at:
            submission.local_done_at = utcnow()
        elif status == "In progress" and submission.status == "assigned":
            submission.status = "working"


@router.post("/import/legacy")
def import_legacy(payload: LegacyImport, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Bring across data the first version of UniTask kept in this browser's localStorage."""
    tz = zone(profile_for(db, user))
    data = {"subjects": payload.subjects, "assignments": payload.assignments}
    _ensure_legacy_subjects(db, user, payload.subjects)
    rows = _legacy_rows(data)
    events, skipped = rows_to_events(rows, "legacy", tz)
    if not events:
        raise HTTPException(422, "No assignments found in the saved data.")
    result = ingest(db, user.id, "legacy", events)
    _apply_legacy_status(db, user, "legacy", {r["id"]: r["_status"] for r in rows if r.get("id") and r.get("_status")})
    audit(db, user.id, "import.legacy", None, **result.as_dict())
    db.commit()
    return {**result.as_dict(), "skipped": skipped[:20]}


@router.post("/import/legacy-db")
def claim_legacy_database(user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """On a single-user local install, adopt the original UniTask database's subjects, assignments and timetable images."""
    if os.getenv("ALLOW_LEGACY_CLAIM", "false").lower() != "true":
        raise HTTPException(404, "Not available on this server.")
    tables = set(inspect(db.get_bind()).get_table_names())
    rows: list[dict] = []
    if {"subjects", "assignments"} <= tables:
        subjects = {r.id: r for r in db.execute(text("SELECT id, name, code, color FROM subjects"))}
        _ensure_legacy_subjects(db, user, [{"name": s.name, "code": s.code, "color": s.color} for s in subjects.values()])
        for a in db.execute(text("SELECT id, title, subject_id, due_date, status, platform, description FROM assignments")):
            subject = subjects.get(a.subject_id)
            rows.append({"id": f"legacydb:{a.id}", "title": a.title, "due": str(a.due_date), "subject": subject.code if subject else None,
                         "description": a.description or f"Imported from {a.platform}", "_status": a.status})
    tz = zone(profile_for(db, user))
    events, _ = rows_to_events(rows, "legacy", tz)
    result = ingest(db, user.id, "legacy", events) if events else None
    if rows:
        _apply_legacy_status(db, user, "legacy", {r["id"]: r["_status"] for r in rows})
    claimed = 0
    for upload in db.scalars(select(TimetableUpload).where(TimetableUpload.owner_id.is_(None))):
        upload.owner_id = user.id
        claimed += 1
    audit(db, user.id, "import.legacy_db", None, assignments=len(rows), timetables=claimed)
    db.commit()
    return {"assignments": result.as_dict() if result else None, "timetable_images": claimed}


# ---------------------------------------------------------------- quick capture


@router.post("/capture")
def capture(payload: CaptureRequest, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Paste an announcement or message; deadlines read from it are added but flagged until confirmed."""
    tz = zone(profile_for(db, user))
    now_local = datetime.now(tz)
    found: list[dict] = []
    method = "rules"
    if llm.available():
        try:
            data = llm.generate(
                "Extract coursework deadlines from a message a university student received. Only include items that are "
                "clearly tasks with a deadline or a test date. Never invent a date: use null if none is stated. "
                f"Today is {now_local:%A %d %B %Y}, timezone {tz.key}. "
                'Return JSON {"items":[{"title": str (short), "due": "YYYY-MM-DDTHH:MM" local or null, "subject": str|null, '
                '"kind": "assignment"|"quiz"|"lab"|"assessment"}]}.',
                payload.text,
                json_mode=True,
                fast=True,
            )
            found = [i for i in (data.get("items") or []) if isinstance(i, dict) and i.get("title")] if isinstance(data, dict) else []
            method = "ai"
        except llm.LLMError:
            found = []
    if method == "rules" or not found:
        first = next((line.strip() for line in payload.text.splitlines() if line.strip()), payload.text)[:120]
        when = find_date(payload.text, tz, now_local.date())
        found = [{"title": first, "due": when.isoformat() if when else None, "subject": None, "kind": _kind(payload.text)}]
        method = "rules"
    events = []
    for item in found[:10]:
        due = parse_when(item.get("due"), tz)
        events.append(
            SourceEvent(
                provider="capture",
                external_id=hashlib.sha1(f"{item['title']}|{item.get('due')}".encode()).hexdigest()[:20],
                title=str(item["title"])[:200],
                due_at=due,
                description=payload.text[:4000],
                subject=item.get("subject"),
                kind=item.get("kind") if item.get("kind") in {"assignment", "quiz", "lab", "assessment"} else "assignment",
                confidence="inferred",
            )
        )
    result = ingest(db, user.id, "capture", events)
    db.commit()
    works = [db.get(Coursework, wid) for wid in result.item_ids]
    return {
        "method": method,
        "items": [to_work_item(w, get_submission(db, w, user)).model_dump() for w in works if w],
        "message": "Check the dates below. They were read from your text and are marked as unconfirmed until you confirm them.",
    }


# ---------------------------------------------------------------- connections


def _connection_out(connection: Connection) -> dict:
    return {
        "provider": connection.provider,
        "status": connection.status,
        "account": connection.account_label,
        "last_synced_at": connection.last_synced_at,
        "last_error": connection.last_error,
        "last_result": json.loads(connection.last_result) if connection.last_result else None,
    }


@router.get("/connections")
def list_connections(user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    connections = {c.provider: _connection_out(c) for c in db.scalars(select(Connection).where(Connection.user_id == user.id))}
    profile = profile_for(db, user)
    db.commit()
    return {"connections": connections, "extension_token": bool(profile.ingest_token_hash)}


@router.post("/connections/moodle")
def connect_moodle(payload: FeedConnect, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    try:
        url = check_url(payload.url)
    except UnsafeURL as exc:
        raise HTTPException(422, str(exc)) from exc
    connection = db.scalar(select(Connection).where(Connection.user_id == user.id, Connection.provider == "moodle_ics"))
    if connection is None:
        connection = Connection(user_id=user.id, provider="moodle_ics")
        db.add(connection)
    connection.config = encrypt(url)
    connection.account_label = urlparse(url).hostname
    db.flush()
    try:
        counts = sync_feed(db, connection)
    except Exception as exc:  # noqa: BLE001 — report any fetch/parse failure to the student
        db.rollback()
        raise HTTPException(422, f"Couldn't read that calendar: {exc}") from None
    connection.last_result = json.dumps(counts)
    audit(db, user.id, "connect.moodle", connection.account_label, **counts)
    db.commit()
    return _connection_out(connection)


@router.post("/connections/moodle/sync")
def sync_moodle(user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    connection = db.scalar(select(Connection).where(Connection.user_id == user.id, Connection.provider == "moodle_ics"))
    if connection is None:
        raise HTTPException(409, "Connect a Moodle calendar first.")
    try:
        counts = sync_feed(db, connection)
        connection.last_result = json.dumps(counts)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        connection = db.scalar(select(Connection).where(Connection.user_id == user.id, Connection.provider == "moodle_ics"))
        connection.status, connection.last_error = "error", str(exc)[:500]
    db.commit()
    return _connection_out(connection)


@router.delete("/connections/moodle", status_code=204)
def disconnect_moodle(user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    connection = db.scalar(select(Connection).where(Connection.user_id == user.id, Connection.provider == "moodle_ics"))
    if connection:
        db.delete(connection)
        db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- VTOP browser extension


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/extension/token")
def create_extension_token(user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """A token for the browser extension. Shown once; only its hash is stored. Creating a new one revokes the old."""
    profile = profile_for(db, user)
    token = "ut_" + secrets.token_urlsafe(32)
    profile.ingest_token_hash = _token_hash(token)
    audit(db, user.id, "extension.token", None)
    db.commit()
    return {"token": token}


@router.delete("/extension/token", status_code=204)
def revoke_extension_token(user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    profile_for(db, user).ingest_token_hash = None
    db.commit()
    return Response(status_code=204)


@router.post("/extension/ingest")
def extension_ingest(payload: ExtensionIngest, authorization: str = Header(default=""), db: Session = Depends(get_db)) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith("ut_"):
        raise HTTPException(401, "Missing extension token.")
    profile = db.scalar(select(Profile).where(Profile.ingest_token_hash == _token_hash(token)))
    if profile is None:
        raise HTTPException(401, "This extension token was revoked. Create a new one in UniTask → Connections.")
    user = db.get(User, profile.user_id)
    tz = zone(profile)
    events = [
        SourceEvent(
            provider=payload.source,
            external_id=item.external_id,
            title=item.title,
            due_at=(item.due_at if item.due_at is None or item.due_at.tzinfo else item.due_at.replace(tzinfo=tz)),
            description=item.description,
            url=item.url,
            subject=item.subject,
            kind=item.kind,
            confidence="verified",
        )
        for item in payload.items
    ]
    result = ingest(db, user.id, payload.source, events, full_snapshot=payload.snapshot)
    connection = db.scalar(select(Connection).where(Connection.user_id == user.id, Connection.provider == payload.source))
    if connection is None:
        connection = Connection(user_id=user.id, provider=payload.source, account_label="Browser extension")
        db.add(connection)
    connection.status, connection.last_synced_at, connection.last_error = "connected", utcnow(), None
    connection.last_result = json.dumps(result.as_dict())
    db.commit()
    return result.as_dict()


# ---------------------------------------------------------------- demo workspace

DEMO_CODE = "DEMO"
DEMO_NOTES = [
    "Arrays and linked lists. An array stores elements contiguously, so indexing is O(1) but inserting in the middle is O(n). "
    "A singly linked list stores a pointer to the next node; insertion after a known node is O(1) but finding the k-th element is O(n). "
    "Doubly linked lists keep a previous pointer too, which makes deletion of a known node O(1).",
    "Stacks and queues. A stack is last-in first-out: push and pop happen at the top. Function calls use a call stack, and "
    "balanced-parentheses checking is the classic stack application. A queue is first-in first-out; a circular queue reuses "
    "freed slots by wrapping the rear index with modulo arithmetic.",
    "Binary search trees. In a BST every key in the left subtree is smaller than the node and every key in the right subtree is larger. "
    "Search, insert and delete take O(h) time where h is the height. An unbalanced BST degrades to O(n); AVL trees keep the balance "
    "factor of every node in {-1, 0, 1} using rotations, so height stays O(log n).",
    "Hashing. A hash function maps keys to table indices. Collisions are resolved by chaining (a list per bucket) or open addressing "
    "(linear probing, quadratic probing, double hashing). The load factor is n/m; keep it below about 0.75 for open addressing.",
    "Graph traversal. Breadth-first search visits vertices level by level using a queue and finds shortest paths in unweighted graphs. "
    "Depth-first search uses a stack (or recursion) and is used for cycle detection and topological sorting of a DAG.",
]
DEMO_PAPER = [
    "Previous year question paper 2024\nQ1. Explain the difference between an array and a linked list with time complexities. [10]\n"
    "Q2. Write an algorithm to check balanced parentheses using a stack. [10]\nQ3. Explain AVL tree rotations with an example. [15]",
    "Previous year question paper 2025\nQ1. Explain the difference between arrays and linked lists with time complexity. [10]\n"
    "Q2. Explain collision resolution in hashing: chaining and open addressing. [10]\nQ3. Explain the rotations used in AVL trees with a suitable example. [15]",
]
DEMO_SYLLABUS = [
    {"title": "Linear structures", "topics": ["Arrays and linked lists", "Stacks and queues"]},
    {"title": "Trees", "topics": ["Binary search trees", "AVL trees"]},
    {"title": "Hashing and graphs", "topics": ["Hashing", "Graph traversal"]},
]


def _demo_course(db: Session, user: User) -> Course | None:
    return db.scalar(select(Course).where(Course.owner_id == user.id, Course.source == "personal", Course.code == DEMO_CODE))


def _demo_material(db: Session, user: User, course: Course, title: str, kind: str, pages: list[str], year: int | None = None) -> None:
    """Store a demo text file and index it one page per paragraph, as a real upload would be indexed."""
    body = "\n\n".join(pages).encode()
    key = f"materials/{user.id}/demo-{kind}-{year or 0}.txt"
    get_storage().put(key, body, "text/plain")
    material = Material(user_id=user.id, course_id=course.id, kind=kind, title=title, filename=f"{title}.txt", storage_key=key,
                        content_type="text/plain", size_bytes=len(body), sha256=sha256(body + str(user.id).encode()), year=year,
                        status="ready", extractor="text", page_count=len(pages))
    db.add(material)
    db.flush()
    for number, page in enumerate(pages, start=1):
        db.add(MaterialPage(material_id=material.id, page_no=number, text=page))
    db.flush()
    db.refresh(material)
    if kind == "pyq":
        save_questions(db, material, pages)
    link_material_topics(db, material)
    db.commit()


@router.post("/demo", status_code=201)
def create_demo(user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """A small, clearly labelled sample subject so a new student can see every feature work. Removable in one click."""
    if _demo_course(db, user):
        raise HTTPException(409, "The demo subject already exists.")
    profile = profile_for(db, user)
    tz = zone(profile)
    course = Course(name="Demo · Data Structures", code=DEMO_CODE, color="#7c5cbf", owner_id=user.id, source="personal",
                    description="Sample data so you can try UniTask. Delete it from Settings whenever you like.")
    db.add(course)
    db.flush()
    save_syllabus(db, user.id, course.id, DEMO_SYLLABUS, confirmed=True, origin="manual")
    db.commit()
    _demo_material(db, user, course, "Demo lecture notes", "notes", DEMO_NOTES)
    _demo_material(db, user, course, "Demo past paper 2024", "pyq", DEMO_PAPER[:1], 2024)
    _demo_material(db, user, course, "Demo past paper 2025", "pyq", DEMO_PAPER[1:], 2025)
    now = datetime.now(tz)
    events = [
        SourceEvent("demo", "demo-1", "Demo · Linked list lab", datetime.combine(now.date() + timedelta(days=1), time(23, 59), tz), subject=DEMO_CODE, kind="lab", confidence="manual",
                    description="Implement insert, delete and reverse for a singly linked list. Submit code and a short write-up."),
        SourceEvent("demo", "demo-2", "Demo · Hashing problem set", datetime.combine(now.date() + timedelta(days=5), time(17, 0), tz), subject=DEMO_CODE, confidence="manual",
                    description="Five questions on collision resolution and load factor."),
    ]
    ingest(db, user.id, "demo", events)
    db.add(Exam(user_id=user.id, course_id=course.id, title="Demo · Data Structures mid-term",
                starts_at=datetime.combine(now.date() + timedelta(days=3), time(10, 0), tz), duration_minutes=90, location="Demo hall"))
    audit(db, user.id, "demo.create", f"course:{course.id}")
    db.commit()
    return {"course_id": course.id}


@router.delete("/demo", status_code=204)
def delete_demo(user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    course = _demo_course(db, user)
    if course is None:
        return Response(status_code=204)
    keys = [m.storage_key for m in db.scalars(select(Material).where(Material.course_id == course.id))]
    for exam in db.scalars(select(Exam).where(Exam.course_id == course.id)):
        db.query(PlanBlock).filter(PlanBlock.exam_id == exam.id).delete()
        db.delete(exam)
    for work in db.scalars(select(Coursework).where(Coursework.course_id == course.id)):
        db.query(PlanBlock).filter(PlanBlock.coursework_id == work.id).delete()
    db.query(TimetableEntry).filter(TimetableEntry.course_id == course.id).delete()
    db.delete(course)
    db.commit()
    storage = get_storage()
    for key in keys:
        try:
            storage.delete(key)
        except Exception:  # noqa: BLE001 — best effort
            pass
    return Response(status_code=204)
