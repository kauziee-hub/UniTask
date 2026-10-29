"""Queries and serialisation shared by the routers."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .models import Course, CourseMember, Coursework, Submission, User
from .priority import rank
from .schemas import ChangeRead, CourseBrief, Priority, WorkItem
from .security import secret_key
from .storage import (
    MAX_FILE_BYTES,
    LocalStorage,
    StorageError,
    UploadTooLargeError,
    UploadValidationError,
    ValidatedUpload,
    get_storage,
    validate_document,
)

logger = logging.getLogger(__name__)
RECENT_CHANGE_WINDOW = timedelta(days=3)


def course_brief(course: Course | None) -> CourseBrief | None:
    if course is None:
        return None
    return CourseBrief(id=course.id, name=course.name, code=course.code, color=course.color, source=course.source)


def membership(db: Session, course_id: int, user_id: int) -> CourseMember | None:
    return db.scalar(select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == user_id))


def get_course_for(db: Session, course_id: int, user: User) -> tuple[Course, str]:
    """Return the course and the caller's role in it, or 404 if they cannot see it."""
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "Class not found.")
    if course.owner_id == user.id:
        return course, "teacher" if course.source == "unitask" else "owner"
    member = membership(db, course_id, user.id)
    if member is None:
        raise HTTPException(404, "Class not found.")
    return course, member.role


def student_coursework_query(user: User):
    member_courses = select(CourseMember.course_id).where(
        CourseMember.user_id == user.id, CourseMember.role == "student"
    )
    return (
        select(Coursework)
        .where(
            or_(
                Coursework.owner_id == user.id,
                (Coursework.source == "unitask") & Coursework.course_id.in_(member_courses),
            )
        )
        .options(selectinload(Coursework.course), selectinload(Coursework.changes))
    )


def get_student_work(db: Session, work_id: int, user: User) -> Coursework:
    work = db.scalar(student_coursework_query(user).where(Coursework.id == work_id))
    if work is None:
        raise HTTPException(404, "Assignment not found.")
    return work


def get_submission(db: Session, work: Coursework, user: User, create: bool = False) -> Submission | None:
    submission = db.scalar(
        select(Submission).where(Submission.coursework_id == work.id, Submission.student_id == user.id)
    )
    if submission is None and create:
        submission = Submission(coursework_id=work.id, student_id=user.id, status="assigned")
        db.add(submission)
        db.flush()
    return submission


def to_work_item(
    work: Coursework, submission: Submission | None, now: datetime | None = None, providers: list[str] | None = None
) -> WorkItem:
    now = now or datetime.now(timezone.utc)
    status = submission.status if submission else "assigned"
    moved_earlier = any(
        change.kind == "due_changed"
        and change.old_value
        and change.new_value
        and change.new_value < change.old_value
        and now - change.detected_at < RECENT_CHANGE_WINDOW
        for change in work.changes
    )
    ranked = rank(
        due_at=work.due_at,
        effort_minutes=submission.effort_minutes if submission else None,
        points=work.points,
        status=status,
        allow_late=work.allow_late,
        due_recently_moved_earlier=moved_earlier,
        now=now,
    )
    return WorkItem(
        id=work.id,
        title=work.title,
        instructions=work.instructions,
        course=course_brief(work.course),
        source=work.source,
        external_url=work.external_url,
        due_at=work.due_at,
        points=work.points,
        allow_late=work.allow_late,
        attachment_name=work.attachment_name,
        removed_at_source=work.removed_at_source,
        status=status,
        effort_minutes=submission.effort_minutes if submission else None,
        text=submission.text if submission else None,
        file_name=submission.file_name if submission else None,
        submitted_at=submission.submitted_at if submission else None,
        grade=submission.grade if submission else None,
        feedback=submission.feedback if submission else None,
        submission_id=submission.id if submission else None,
        changes=[ChangeRead.model_validate(change) for change in work.changes if change.kind != "created"][:5],
        priority=Priority(**ranked.__dict__),
        kind=work.kind or "assignment",
        due_confidence=work.due_confidence or "manual",
        last_verified_at=work.last_synced_at,
        source_status=submission.source_status if submission else None,
        local_done_at=submission.local_done_at if submission else None,
        snoozed_until=submission.snoozed_until if submission else None,
        snooze_reason=submission.snooze_reason if submission else None,
        notes=submission.notes if submission else None,
        providers=providers or ([work.source] if work.source != "personal" else []),
    )


def student_work_items(db: Session, user: User) -> list[WorkItem]:
    works = list(db.scalars(student_coursework_query(user)).unique())
    submissions = {
        s.coursework_id: s
        for s in db.scalars(
            select(Submission).where(Submission.student_id == user.id, Submission.coursework_id.in_([w.id for w in works]))
        )
    }
    from .academic_models import CourseworkSource

    providers: dict[int, list[str]] = {}
    for link in db.scalars(select(CourseworkSource).where(CourseworkSource.owner_id == user.id)):
        providers.setdefault(link.coursework_id, []).append(link.provider)
    now = datetime.now(timezone.utc)
    return [to_work_item(work, submissions.get(work.id), now, providers.get(work.id)) for work in works]


async def read_upload(upload: UploadFile, max_bytes: int = MAX_FILE_BYTES) -> ValidatedUpload:
    """Read and validate an upload without storing it (extension, signature and size)."""
    content = await upload.read(max_bytes + 1)
    await upload.close()
    try:
        return validate_document(upload.filename, content, max_bytes=max_bytes)
    except UploadTooLargeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except UploadValidationError as exc:
        raise HTTPException(415, str(exc)) from exc


def put_upload(validated: ValidatedUpload, prefix: str) -> str:
    try:
        storage = get_storage()
        key = f"{prefix}/{uuid.uuid4().hex}-{validated.filename}"
        storage.put(key, validated.content, validated.content_type)
    except StorageError as exc:
        raise HTTPException(502, str(exc)) from exc
    return key


async def store_upload(upload: UploadFile, prefix: str, max_bytes: int = MAX_FILE_BYTES):
    """Validate and store an uploaded file; returns (key, filename, content_type)."""
    validated = await read_upload(upload, max_bytes)
    return put_upload(validated, prefix), validated.filename, validated.content_type


def download_link(key: str, filename: str, content_type: str | None, *, inline: bool = False) -> dict[str, str]:
    """A short-lived link the browser can open directly (no Authorization header needed).

    S3 gets a five-minute presigned URL. Local storage gets a five-minute signed token
    for /api/files/{token}. ``inline`` asks the browser to display the file (PDF preview)
    instead of downloading it.
    """
    try:
        storage = get_storage()
    except StorageError as exc:
        raise HTTPException(503, str(exc)) from exc
    if isinstance(storage, LocalStorage):
        token = jwt.encode(
            {
                "key": key,
                "name": filename,
                "type": content_type or "application/octet-stream",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                "use": "file",
                "inline": inline,
            },
            secret_key(),
            algorithm="HS256",
        )
        return {"url": f"/api/files/{token}", "name": filename}
    try:
        return {"url": storage.retrieval_url(key, download_name=filename, inline=inline), "name": filename}
    except StorageError as exc:
        raise HTTPException(502, str(exc)) from exc


def serve_local_file(token: str) -> FileResponse:
    try:
        claims = jwt.decode(token, secret_key(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(410, "This download link has expired. Open the file again from UniTask.") from None
    if claims.get("use") != "file":
        raise HTTPException(404, "File not found.")
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise HTTPException(404, "File not found.")
    path = storage.get_local_path(claims["key"])
    if not path.is_file():
        raise HTTPException(404, "The stored file is missing.")
    return FileResponse(
        path,
        media_type=claims["type"],
        filename=claims["name"],
        content_disposition_type="inline" if claims.get("inline") else "attachment",
    )
