"""The student's side: everything due, from every source, ranked and actionable."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Connection, Coursework, CourseworkChange, User
from ..priority import Candidate, plan_session
from ..schemas import PersonalTaskCreate, PlanBlock, PlanResponse, TodayResponse, WorkItem, WorkUpdate
from ..security import require_student
from ..services import (
    get_course_for,
    get_student_work,
    get_submission,
    student_coursework_query,
    student_work_items,
    store_upload,
    to_work_item,
)
from ..teams import settings as teams_settings

router = APIRouter(prefix="/api", tags=["student"])
PENDING = {"assigned", "working"}


def _pending(items: list[WorkItem]) -> list[WorkItem]:
    now = datetime.now(timezone.utc)
    return [
        item
        for item in items
        if item.status in PENDING
        and not item.local_done_at
        and not item.removed_at_source
        and item.priority.tier != "missed"
        and not (item.snoozed_until and item.snoozed_until > now)
    ]


@router.get("/work", response_model=list[WorkItem])
def list_work(user: User = Depends(require_student), db: Session = Depends(get_db)) -> list[WorkItem]:
    items = student_work_items(db, user)
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(items, key=lambda i: (i.due_at or far_future, i.id))


@router.get("/today", response_model=TodayResponse)
def today(user: User = Depends(require_student), db: Session = Depends(get_db)) -> TodayResponse:
    items = student_work_items(db, user)
    pending = sorted(_pending(items), key=lambda i: i.priority.score, reverse=True)
    overdue = [i for i in pending if i.priority.tier == "overdue"]
    active = [i for i in pending if i.priority.tier in {"now", "soon"}]
    upcoming = sorted(
        [i for i in pending if i.priority.tier in {"later", "someday"}],
        key=lambda i: (i.due_at is None, i.due_at or datetime.max.replace(tzinfo=timezone.utc)),
    )
    ranked_now = overdue + active
    work_ids = select(Coursework.id).where(student_coursework_query(user).whereclause)
    changes = list(
        db.scalars(
            select(CourseworkChange)
            .where(CourseworkChange.coursework_id.in_(work_ids), CourseworkChange.seen.is_(False))
            .order_by(CourseworkChange.detected_at.desc())
            .limit(10)
        )
    )
    connection = db.scalar(select(Connection).where(Connection.user_id == user.id, Connection.provider == "teams"))
    return TodayResponse(
        next=ranked_now[0] if ranked_now else (upcoming[0] if upcoming else None),
        focus=ranked_now[1:6] if ranked_now else [],
        upcoming=upcoming[:8],
        overdue=overdue,
        changes=[
            {
                "id": c.id,
                "work_id": c.coursework_id,
                "title": c.coursework.title,
                "kind": c.kind,
                "old_value": c.old_value,
                "new_value": c.new_value,
                "detected_at": c.detected_at,
                "source": c.coursework.source,
            }
            for c in changes
        ],
        teams={
            "configured": teams_settings() is not None,
            "status": connection.status if connection else "not_connected",
            "last_synced_at": connection.last_synced_at if connection else None,
            "account": connection.account_label if connection else None,
        },
    )


@router.post("/changes/seen", status_code=204)
def mark_changes_seen(user: User = Depends(require_student), db: Session = Depends(get_db)):
    work_ids = select(Coursework.id).where(student_coursework_query(user).whereclause)
    for change in db.scalars(
        select(CourseworkChange).where(CourseworkChange.coursework_id.in_(work_ids), CourseworkChange.seen.is_(False))
    ):
        change.seen = True
    db.commit()
    return Response(status_code=204)


@router.get("/plan", response_model=PlanResponse)
def plan(
    minutes: int = Query(ge=15, le=12 * 60),
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> PlanResponse:
    """'I have N minutes free — what should I do with them?'"""
    items = {i.id: i for i in _pending(student_work_items(db, user))}
    candidates = [
        Candidate(item_id=i.id, title=i.title, remaining_minutes=i.priority.effort_minutes, score=i.priority.score)
        for i in items.values()
    ]
    blocks, left = plan_session(candidates, minutes)
    chosen = {c.item_id for c, _, _ in blocks}
    return PlanResponse(
        minutes=minutes,
        blocks=[
            PlanBlock(
                item_id=c.item_id,
                title=c.title,
                course=items[c.item_id].course,
                minutes=m,
                finishes_item=done,
                note=items[c.item_id].priority.reason
                if done
                else f"Gets you {m} of the ~{c.remaining_minutes} min this needs",
            )
            for c, m, done in blocks
        ],
        left_over=left,
        skipped=[i.title for i in sorted(items.values(), key=lambda i: -i.priority.score) if i.id not in chosen][:5],
    )


@router.get("/work/{work_id}", response_model=WorkItem)
def get_work(work_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> WorkItem:
    work = get_student_work(db, work_id, user)
    return to_work_item(work, get_submission(db, work, user))


@router.patch("/work/{work_id}", response_model=WorkItem)
def update_work(
    work_id: int, payload: WorkUpdate, user: User = Depends(require_student), db: Session = Depends(get_db)
) -> WorkItem:
    work = get_student_work(db, work_id, user)
    submission = get_submission(db, work, user, create=True)
    changes = payload.model_dump(exclude_unset=True)
    if "effort_minutes" in changes:
        submission.effort_minutes = changes["effort_minutes"]
    status = changes.get("status")
    if status == "done":
        if work.source == "teams":
            raise HTTPException(409, "Turn this in on Teams. UniTask picks up the new status on the next sync.")
        if work.source == "unitask":
            raise HTTPException(409, "Use Turn in so your teacher receives your work.")
        submission.status = "turned_in"
        submission.submitted_at = datetime.now(timezone.utc)
    elif status:
        if submission.status in {"turned_in", "returned"} and work.source != "personal":
            raise HTTPException(409, "This is already turned in.")
        submission.status = status
        submission.submitted_at = None
    db.commit()
    db.refresh(work)
    return to_work_item(work, submission)


@router.post("/work/{work_id}/turn-in", response_model=WorkItem)
async def turn_in(
    work_id: int,
    text: str | None = Form(default=None, max_length=20000),
    file: UploadFile | None = File(default=None),
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> WorkItem:
    work = get_student_work(db, work_id, user)
    if work.source != "unitask":
        raise HTTPException(409, "Only UniTask class assignments are turned in here.")
    now = datetime.now(timezone.utc)
    if work.due_at and now > work.due_at and not work.allow_late:
        raise HTTPException(409, "This assignment is closed and does not accept late work.")
    submission = get_submission(db, work, user, create=True)
    if submission.status == "returned":
        raise HTTPException(409, "Your teacher has already returned this assignment.")
    has_file = file is not None and bool(file.filename)
    if not has_file and not (text or "").strip() and not submission.file_key:
        raise HTTPException(422, "Add a file or write a response before turning in.")
    if has_file:
        submission.file_key, submission.file_name, submission.file_type = await store_upload(
            file, f"submissions/{work.id}/{user.id}"
        )
    submission.text = (text or "").strip() or submission.text
    submission.status = "turned_in"
    submission.submitted_at = now
    db.commit()
    return to_work_item(work, submission)


@router.post("/work/{work_id}/undo-turn-in", response_model=WorkItem)
def undo_turn_in(work_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> WorkItem:
    work = get_student_work(db, work_id, user)
    submission = get_submission(db, work, user)
    if work.source == "teams":
        raise HTTPException(409, "Teams assignments are managed in Teams.")
    if submission is None or submission.status != "turned_in":
        raise HTTPException(409, "There is nothing to undo.")
    submission.status = "working"
    submission.submitted_at = None
    db.commit()
    return to_work_item(work, submission)


@router.post("/work", response_model=WorkItem, status_code=201)
def create_personal_task(
    payload: PersonalTaskCreate, user: User = Depends(require_student), db: Session = Depends(get_db)
) -> WorkItem:
    if payload.course_id is not None:
        get_course_for(db, payload.course_id, user)
    due_at = payload.due_at
    if due_at is not None and due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    work = Coursework(
        owner_id=user.id,
        created_by_id=user.id,
        course_id=payload.course_id,
        source="personal",
        title=payload.title.strip(),
        instructions=(payload.notes or "").strip() or None,
        due_at=due_at,
    )
    db.add(work)
    db.flush()
    submission = get_submission(db, work, user, create=True)
    submission.effort_minutes = payload.effort_minutes
    db.commit()
    db.refresh(work)
    return to_work_item(work, submission)


@router.delete("/work/{work_id}", status_code=204)
def delete_personal_task(work_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)):
    work = get_student_work(db, work_id, user)
    if work.source != "personal":
        raise HTTPException(409, "Only your own tasks can be deleted here.")
    db.delete(work)
    db.commit()
    return Response(status_code=204)


