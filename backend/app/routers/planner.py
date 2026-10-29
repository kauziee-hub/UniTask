"""Week planning around real classes and exams, the unified calendar, the timetable and attendance."""

import logging
import math
import re
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import ics, llm, scheduler
from ..academic import audit
from ..academic_models import AttendanceMark, Exam, PlanBlock, TimetableEntry
from ..academic_schemas import AttendanceIn, BlockUpdate, ReplanRequest, TimetableEntryIn, TimetableEntryUpdate
from ..database import get_db
from ..models import TimetableUpload, User
from ..security import require_student
from ..services import course_brief, student_work_items
from ..storage import MAX_UPLOAD_BYTES, StorageError, UploadTooLargeError, UploadValidationError, get_storage, validate_image
from ..workspace import (
    DONE_STATUSES,
    aware,
    block_out,
    busy_for,
    conflict_list,
    entry_out,
    forecast,
    local_day_bounds,
    outcome_out,
    owned,
    profile_for,
    require_course,
    utcnow,
    visible_courses,
    zone,
)

router = APIRouter(prefix="/api", tags=["planner"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- planner


def _plan_window(db: Session, user: User, days: int) -> tuple[datetime, datetime]:
    profile = profile_for(db, user)
    tz = zone(profile)
    start, _ = local_day_bounds(utcnow().astimezone(tz).date(), tz)
    return start, start + timedelta(days=days)


@router.get("/planner")
def get_planner(days: int = Query(default=7, ge=1, le=14), user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    profile = profile_for(db, user)
    now = utcnow()
    start, end = _plan_window(db, user, days)
    blocks = list(
        db.scalars(
            select(PlanBlock).where(PlanBlock.user_id == user.id, PlanBlock.starts_at < end, PlanBlock.ends_at > start).order_by(PlanBlock.starts_at)
        )
    )
    outcome, demands = forecast(db, user, profile, now, days)
    busy = busy_for(db, user, profile, start, days, include_rescue=False)
    db.commit()
    return {
        "window": {"start": start, "end": end, "timezone": zone(profile).key},
        "blocks": [block_out(b) for b in blocks],
        "busy": [{"title": b.title, "kind": b.kind, "starts_at": b.start, "ends_at": b.end} for b in busy if b.end > start and b.start < end],
        "forecast": outcome_out(outcome),
        "demands": [
            {"key": d.key, "title": d.title, "minutes": d.minutes, "deadline": d.deadline, "kind": d.kind, "estimated": d.estimated, "reason": d.reason}
            for d in demands
        ],
        "daily_cap": profile.daily_study_minutes,
        "day_start": profile.day_start,
        "day_end": profile.day_end,
        "missed": sum(1 for b in blocks if b.state == "missed"),
        "conflicts": conflict_list(busy),
        "has_timetable": db.scalar(select(TimetableEntry.id).where(TimetableEntry.user_id == user.id).limit(1)) is not None,
    }


@router.post("/planner/replan")
def replan(payload: ReplanRequest, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Mark missed blocks, then rebuild the week's plan from what is actually left to do."""
    profile = profile_for(db, user)
    now = utcnow()
    missed = 0
    for block in db.scalars(select(PlanBlock).where(PlanBlock.user_id == user.id, PlanBlock.state == "planned", PlanBlock.ends_at <= now)):
        block.state = "missed"
        missed += 1
    db.execute(
        delete(PlanBlock).where(
            PlanBlock.user_id == user.id, PlanBlock.state == "planned", PlanBlock.plan == "week", PlanBlock.starts_at >= now
        )
    )
    db.flush()
    outcome, _ = forecast(db, user, profile, now, payload.days)
    for block in outcome.blocks:
        d = block.demand
        db.add(
            PlanBlock(
                user_id=user.id,
                starts_at=block.start,
                ends_at=block.end,
                coursework_id=d.coursework_id,
                topic_id=d.topic_id,
                exam_id=d.exam_id,
                title=d.title[:200],
                kind=d.kind,
                reason=(d.reason or "")[:300],
                plan="week",
            )
        )
    audit(db, user.id, "planner.replan", None, blocks=len(outcome.blocks), unfit=len(outcome.unfit), missed=missed)
    db.commit()
    result = get_planner(payload.days, user, db)
    result["marked_missed"] = missed
    result["created"] = len(outcome.blocks)
    return result


@router.patch("/planner/blocks/{block_id}")
def update_block(block_id: int, payload: BlockUpdate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    block = owned(db, PlanBlock, block_id, user, "Block")
    tz = zone(profile_for(db, user))
    if payload.state:
        block.state = payload.state
    if payload.starts_at or payload.ends_at:
        starts = aware(payload.starts_at, tz) or block.starts_at
        ends = aware(payload.ends_at, tz) or block.ends_at
        if ends <= starts:
            raise HTTPException(422, "A block must end after it starts.")
        block.starts_at, block.ends_at = starts, ends
    db.commit()
    return block_out(block)


@router.delete("/planner/blocks/{block_id}", status_code=204)
def delete_block(block_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    db.delete(owned(db, PlanBlock, block_id, user, "Block"))
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- calendar


def _calendar_events(db: Session, user: User, start: datetime, end: datetime) -> tuple[list[dict], list]:
    profile = profile_for(db, user)
    events: list[dict] = []
    for item in student_work_items(db, user):
        if item.due_at and start <= item.due_at < end and not item.removed_at_source:
            events.append(
                {
                    "id": f"work-{item.id}",
                    "kind": "deadline",
                    "title": item.title,
                    "start": item.due_at,
                    "end": None,
                    "color": item.course.color if item.course else None,
                    "course": item.course.name if item.course else None,
                    "link": f"/work/{item.id}",
                    "done": item.status in DONE_STATUSES or bool(item.local_done_at),
                    "confidence": item.due_confidence,
                }
            )
    for exam in db.scalars(select(Exam).where(Exam.user_id == user.id, Exam.starts_at >= start, Exam.starts_at < end)):
        events.append(
            {
                "id": f"exam-{exam.id}",
                "kind": "exam",
                "title": exam.title,
                "start": exam.starts_at,
                "end": exam.starts_at + timedelta(minutes=exam.duration_minutes),
                "color": exam.course.color if exam.course else None,
                "course": exam.course.name if exam.course else None,
                "link": f"/exams/{exam.id}",
                "location": exam.location,
            }
        )
    days = max(1, math.ceil((end - start).total_seconds() / 86400))
    busy = busy_for(db, user, profile, start, days, include_rescue=False)
    for b in busy:
        if b.kind in {"class", "lab", "tutorial"} and b.start < end and b.end > start:
            events.append({"id": f"class-{b.start.isoformat()}-{b.title}", "kind": "class", "title": b.title, "start": b.start, "end": b.end, "class_kind": b.kind})
    for block in db.scalars(select(PlanBlock).where(PlanBlock.user_id == user.id, PlanBlock.starts_at < end, PlanBlock.ends_at > start)):
        events.append(
            {
                "id": f"block-{block.id}",
                "kind": "study",
                "title": block.title,
                "start": block.starts_at,
                "end": block.ends_at,
                "state": block.state,
                "block_kind": block.kind,
                "block_id": block.id,
            }
        )
    events.sort(key=lambda e: e["start"])
    return events, busy


@router.get("/calendar")
def calendar(
    start: datetime,
    end: datetime,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> dict:
    tz = zone(profile_for(db, user))
    start, end = aware(start, tz), aware(end, tz)
    if end <= start or end - start > timedelta(days=62):
        raise HTTPException(422, "Choose a range of up to 62 days.")
    events, busy = _calendar_events(db, user, start, end)
    return {"events": events, "conflicts": conflict_list(busy), "timezone": tz.key}


@router.get("/calendar/export.ics", response_class=PlainTextResponse)
def export_calendar(user: User = Depends(require_student), db: Session = Depends(get_db)) -> PlainTextResponse:
    start = utcnow() - timedelta(days=1)
    events, _ = _calendar_events(db, user, start, start + timedelta(days=61))
    items = [
        {
            "uid": e["id"],
            "title": {"deadline": "Due: ", "exam": "Exam: ", "study": "Study: "}.get(e["kind"], "") + e["title"],
            "start": e["start"],
            "end": e["end"],
        }
        for e in events
        if e["kind"] in {"deadline", "exam", "study"} and not e.get("done") and e.get("state") not in {"missed", "skipped"}
    ]
    return PlainTextResponse(
        ics.export(items),
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="unitask.ics"'},
    )


# ---------------------------------------------------------------- timetable


def _course_map(db: Session, user: User) -> dict:
    return {c.id: c for c in visible_courses(db, user)}


@router.get("/timetable")
def list_timetable(user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    courses = _course_map(db, user)
    entries = list(db.scalars(select(TimetableEntry).where(TimetableEntry.user_id == user.id).order_by(TimetableEntry.weekday, TimetableEntry.start)))
    tz = zone(profile_for(db, user))
    today = utcnow().astimezone(tz).date()
    week_start = today - timedelta(days=today.weekday())
    busy = scheduler.weekly_busy(
        [{"weekday": e.weekday, "start": e.start, "end": e.end, "title": e.title, "kind": e.kind} for e in entries if e.confirmed],
        week_start,
        7,
        tz.key,
    )
    db.commit()
    return {
        "entries": [entry_out(e, courses) for e in entries],
        "unconfirmed": sum(1 for e in entries if not e.confirmed),
        "conflicts": conflict_list(busy),
    }


def _check_times(start: str, end: str) -> None:
    if end <= start:
        raise HTTPException(422, "A class must end after it starts.")


@router.post("/timetable", status_code=201)
def add_entry(payload: TimetableEntryIn, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    _check_times(payload.start, payload.end)
    require_course(db, payload.course_id, user)
    entry = TimetableEntry(user_id=user.id, source="manual", confirmed=True, **payload.model_dump())
    db.add(entry)
    db.commit()
    return entry_out(entry, _course_map(db, user))


@router.patch("/timetable/{entry_id}")
def update_entry(entry_id: int, payload: TimetableEntryUpdate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    entry = owned(db, TimetableEntry, entry_id, user, "Class")
    changes = payload.model_dump(exclude_unset=True)
    if "course_id" in changes:
        require_course(db, changes["course_id"], user)
    for field, value in changes.items():
        if value is not None or field in {"course_id", "location"}:
            setattr(entry, field, value)
    _check_times(entry.start, entry.end)
    db.commit()
    return entry_out(entry, _course_map(db, user))


@router.delete("/timetable/{entry_id}", status_code=204)
def delete_entry(entry_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    db.delete(owned(db, TimetableEntry, entry_id, user, "Class"))
    db.commit()
    return Response(status_code=204)


@router.post("/timetable/confirm-all")
def confirm_all(discard: bool = False, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    for entry in db.scalars(select(TimetableEntry).where(TimetableEntry.user_id == user.id, TimetableEntry.confirmed.is_(False))):
        if discard:
            db.delete(entry)
        else:
            entry.confirmed = True
    db.commit()
    return list_timetable(user, db)


HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _hhmm(value) -> str | None:
    match = HHMM.match(str(value or "").strip())
    return f"{int(match.group(1)):02d}:{match.group(2)}" if match else None


@router.post("/timetable/extract")
async def extract_timetable(file: UploadFile = File(...), user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Read a timetable photo or screenshot into classes the student reviews before they count."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        validated = validate_image(file.filename, file.content_type, content)
        storage = get_storage()
    except UploadTooLargeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except UploadValidationError as exc:
        raise HTTPException(415, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(503, str(exc)) from exc
    finally:
        await file.close()
    upload_id = str(uuid.uuid4())
    extension = ".jpg" if validated.content_type == "image/jpeg" else f".{validated.content_type.split('/')[-1]}"
    key = f"timetables/{upload_id}{extension}"
    try:
        storage.put(key, validated.content, validated.content_type)
    except StorageError as exc:
        raise HTTPException(502, str(exc)) from exc
    db.add(
        TimetableUpload(
            id=upload_id,
            owner_id=user.id,
            original_filename=validated.filename[:255],
            object_key=key,
            storage_provider=storage.provider,
            content_type=validated.content_type,
            size_bytes=len(validated.content),
        )
    )
    db.commit()

    if not llm.available():
        return {"upload_id": upload_id, "created": 0, "message": "Image saved. No AI model is configured to read it, so add your classes by hand."}
    try:
        data = llm.generate(
            "You read university class timetables from images. Extract each weekly class exactly as shown. "
            'Return JSON {"entries":[{"weekday":0-6 (Monday=0),"start":"HH:MM" 24h,"end":"HH:MM" 24h,'
            '"title":str (course name or code as written),"kind":"class"|"lab"|"tutorial","location":str|null}]}. '
            "Do not guess anything you cannot read; skip unreadable cells.",
            "Extract the weekly timetable.",
            json_mode=True,
            image=(validated.content, validated.content_type),
        )
    except llm.LLMError as exc:
        return {"upload_id": upload_id, "created": 0, "message": f"Image saved, but it couldn't be read automatically ({exc}). Add classes by hand."}

    created = 0
    for row in (data.get("entries") or [])[:80] if isinstance(data, dict) else []:
        if not isinstance(row, dict):
            continue
        start, end = _hhmm(row.get("start")), _hhmm(row.get("end"))
        try:
            weekday = int(row.get("weekday"))
        except (TypeError, ValueError):
            continue
        title = str(row.get("title") or "").strip()[:160]
        if not (start and end and title and 0 <= weekday <= 6 and end > start):
            continue
        kind = row.get("kind") if row.get("kind") in {"class", "lab", "tutorial"} else "class"
        db.add(
            TimetableEntry(
                user_id=user.id,
                title=title,
                weekday=weekday,
                start=start,
                end=end,
                kind=kind,
                location=(str(row.get("location"))[:80] if row.get("location") else None),
                source="image",
                confirmed=False,
            )
        )
        created += 1
    audit(db, user.id, "timetable.extract", f"upload:{upload_id}", created=created)
    db.commit()
    message = (
        f"Found {created} classes. Check them against your timetable, then confirm." if created else "No classes could be read from that image. Add them by hand."
    )
    return {"upload_id": upload_id, "created": created, "message": message}


# ---------------------------------------------------------------- attendance


def _attendance_row(course, marks: list[AttendanceMark], threshold: int | None) -> dict:
    total = len(marks)
    present = sum(1 for m in marks if m.present)
    row = {
        "course": course_brief(course),
        "present": present,
        "total": total,
        "percent": round(100 * present / total, 1) if total else None,
        "can_miss": None,
        "must_attend": None,
        "marks": [{"id": m.id, "date": m.date, "present": m.present} for m in sorted(marks, key=lambda m: m.date, reverse=True)[:30]],
    }
    if threshold and total:
        t = threshold / 100
        if present / total >= t:
            row["can_miss"] = max(0, math.floor(present / t - total + 1e-9))
        else:
            row["must_attend"] = math.ceil((t * total - present) / (1 - t) - 1e-9) if t < 1 else None
    return row


@router.get("/attendance")
def attendance(user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    profile = profile_for(db, user)
    marks = list(db.scalars(select(AttendanceMark).where(AttendanceMark.user_id == user.id)))
    courses = _course_map(db, user)
    by_course: dict[int, list[AttendanceMark]] = {}
    for mark in marks:
        by_course.setdefault(mark.course_id, []).append(mark)
    db.commit()
    return {
        "threshold": profile.attendance_threshold,
        "note": "Calculated only from the classes you've marked here, against the attendance rule you set.",
        "subjects": [_attendance_row(courses[cid], rows, profile.attendance_threshold) for cid, rows in by_course.items() if cid in courses],
    }


@router.post("/attendance")
def mark_attendance(payload: AttendanceIn, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    require_course(db, payload.course_id, user)
    mark = db.scalar(
        select(AttendanceMark).where(AttendanceMark.user_id == user.id, AttendanceMark.course_id == payload.course_id, AttendanceMark.date == payload.date)
    )
    if mark is None:
        mark = AttendanceMark(user_id=user.id, course_id=payload.course_id, date=payload.date, present=payload.present)
        db.add(mark)
    else:
        mark.present = payload.present
    db.commit()
    return attendance(user, db)


@router.delete("/attendance/{mark_id}", status_code=204)
def delete_mark(mark_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    db.delete(owned(db, AttendanceMark, mark_id, user, "Attendance record"))
    db.commit()
    return Response(status_code=204)
