"""The Academic Sync Engine's common contract.

Every adapter (Moodle/ICS feed, CSV/JSON import, VTOP extension, quick capture) turns what it read
into SourceEvents and hands them to `ingest()`, which owns the hard parts:
- idempotent upsert keyed by (student, provider, external id)
- cross-platform de-duplication (same title, same due time ±12h, same subject)
- deadline change history and inbox events
- cancellation/removal when a full snapshot no longer contains an item
- provenance: every provider that has seen an item is recorded in coursework_sources
Microsoft Teams uses the same tables through teams.py, with its richer submission data.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .academic import notify
from .models import Course, Coursework, CourseworkChange, CourseworkSource, SyncRun

DEDUPE_WINDOW = timedelta(hours=12)
KINDS = {"assignment", "quiz", "lab", "assessment", "task"}


@dataclass
class SourceEvent:
    provider: str  # moodle_ics | ics | csv | json | vtop | capture | email
    external_id: str
    title: str
    due_at: datetime | None
    description: str | None = None
    url: str | None = None
    subject: str | None = None  # course name or code as the source spells it
    kind: str = "assignment"
    confidence: str = "verified"  # verified | inferred | manual
    published_at: datetime | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class IngestResult:
    created: int = 0
    updated: int = 0
    merged: int = 0
    due_changed: int = 0
    removed: int = 0
    unchanged: int = 0
    item_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "item_ids"}


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _fmt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def match_course(db: Session, user_id: int, subject: str | None, *, create: bool = True) -> Course | None:
    """Find the student's subject by code or name; create a personal subject if none matches."""
    if not subject:
        return None
    from .models import CourseMember

    wanted = normalize_title(subject)
    visible = list(db.scalars(select(Course).where(Course.owner_id == user_id))) + list(
        db.scalars(select(Course).join(CourseMember, CourseMember.course_id == Course.id).where(CourseMember.user_id == user_id))
    )
    for course in visible:
        if wanted in {normalize_title(course.code or ""), normalize_title(course.name)} or (
            course.code and normalize_title(course.code) and normalize_title(course.code) in wanted
        ):
            return course
    if not create:
        return None
    course = Course(name=subject.strip()[:160], code="", owner_id=user_id, source="personal")
    db.add(course)
    db.flush()
    return course


def ingest(db: Session, user_id: int, provider: str, events: list[SourceEvent], *, full_snapshot: bool = False) -> IngestResult:
    result = IngestResult()
    now = datetime.now(timezone.utc)
    run = SyncRun(user_id=user_id, provider=provider)
    db.add(run)
    first_time = db.scalar(select(CourseworkSource.id).where(CourseworkSource.owner_id == user_id, CourseworkSource.provider == provider)) is None
    seen: set[str] = set()

    for event in events:
        seen.add(event.external_id)
        due = event.due_at.astimezone(timezone.utc) if event.due_at and event.due_at.tzinfo else (event.due_at.replace(tzinfo=timezone.utc) if event.due_at else None)
        link = db.scalar(
            select(CourseworkSource).where(
                CourseworkSource.owner_id == user_id, CourseworkSource.provider == provider, CourseworkSource.external_id == event.external_id
            )
        )
        work = db.get(Coursework, link.coursework_id) if link else None
        course = match_course(db, user_id, event.subject)

        if work is None:
            # Same assignment already known from another platform?
            candidates = db.scalars(select(Coursework).where(Coursework.owner_id == user_id, Coursework.removed_at_source.is_(False)))
            for candidate in candidates:
                same_title = normalize_title(candidate.title) == normalize_title(event.title)
                same_due = (candidate.due_at is None and due is None) or (
                    candidate.due_at is not None and due is not None and abs(candidate.due_at - due) <= DEDUPE_WINDOW
                )
                same_course = course is None or candidate.course_id in (None, course.id)
                if same_title and same_due and same_course:
                    work = candidate
                    result.merged += 1
                    break
            if work is None:
                work = Coursework(
                    owner_id=user_id,
                    created_by_id=user_id,
                    source="personal",
                    external_id=None,
                    title=event.title[:200],
                    instructions=event.description,
                    due_at=due,
                    course_id=course.id if course else None,
                    kind=event.kind if event.kind in KINDS else "assignment",
                    due_confidence=event.confidence,
                    external_url=event.url,
                    last_synced_at=now,
                )
                db.add(work)
                db.flush()
                db.add(CourseworkChange(coursework_id=work.id, kind="created", new_value=_fmt(due), seen=first_time))
                if not first_time:
                    notify(db, user_id, "new_work", f"New: {work.title}", f"new:{provider}:{event.external_id}",
                           body=f"Due {due:%a %d %b, %H:%M} UTC" if due else "No due date given", link=f"/work/{work.id}", source=provider)
                result.created += 1
            db.add(CourseworkSource(coursework_id=work.id, owner_id=user_id, provider=provider, external_id=event.external_id, url=event.url))
        else:
            changed = False
            if work.due_at != due and event.confidence == "verified":
                db.add(CourseworkChange(coursework_id=work.id, kind="due_changed", old_value=_fmt(work.due_at), new_value=_fmt(due)))
                notify(db, user_id, "due_changed", f"Deadline moved: {work.title}", f"due:{work.id}:{_fmt(due)}",
                       body=f"{_fmt(work.due_at) or 'no date'} → {_fmt(due) or 'no date'}", link=f"/work/{work.id}", source=provider)
                work.due_at = due
                result.due_changed += 1
                changed = True
            if normalize_title(work.title) != normalize_title(event.title):
                db.add(CourseworkChange(coursework_id=work.id, kind="title_changed", old_value=work.title, new_value=event.title[:200]))
                work.title = event.title[:200]
                changed = True
            if event.description and event.description != work.instructions:
                work.instructions = event.description
                changed = True
            if work.removed_at_source:
                work.removed_at_source = False
                changed = True
            result.updated += int(changed)
            result.unchanged += int(not changed)
            link.last_seen_at = now
        if event.confidence == "verified" and work.due_confidence != "verified" and work.source == "personal":
            work.due_confidence = "verified"
        work.last_synced_at = now
        result.item_ids.append(work.id)

    if full_snapshot:
        for link in db.scalars(select(CourseworkSource).where(CourseworkSource.owner_id == user_id, CourseworkSource.provider == provider)):
            if link.external_id not in seen:
                work = db.get(Coursework, link.coursework_id)
                if work and not work.removed_at_source:
                    other_sources = db.scalar(
                        select(CourseworkSource.id).where(CourseworkSource.coursework_id == work.id, CourseworkSource.provider != provider)
                    )
                    if other_sources is None:
                        work.removed_at_source = True
                        db.add(CourseworkChange(coursework_id=work.id, kind="removed", old_value=work.title))
                        notify(db, user_id, "removed", f"Removed at source: {work.title}", f"removed:{provider}:{link.external_id}",
                               link=f"/work/{work.id}", source=provider)
                        result.removed += 1

    run.status, run.finished_at, run.counts = "ok", datetime.now(timezone.utc), result.as_dict()
    db.flush()
    return result
