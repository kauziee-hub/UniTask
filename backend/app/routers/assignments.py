"""The Assignment Execution Workspace: subtasks, breakdown, notes, snooze and the student's own 'done' mark."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import llm, retrieval
from ..academic import audit, topic_match_score
from ..academic_models import StudySession, Subtask, Topic
from ..academic_schemas import ConfirmDue, LocalDone, NotesUpdate, Snooze, SubtaskCreate, SubtaskUpdate
from ..database import get_db
from ..models import CourseworkSource, User
from ..security import require_student
from ..services import get_student_work, get_submission, to_work_item
from ..workspace import aware, owned, profile_for, session_out, utcnow, zone

router = APIRouter(prefix="/api", tags=["assignments"])

TEMPLATES = {
    "lab": [("Read the lab sheet and expected output", 0.1), ("Set up the environment and starter code", 0.15), ("Implement the core task", 0.4),
            ("Test with your own inputs", 0.15), ("Write up observations and results", 0.15), ("Submit and keep a copy", 0.05)],
    "quiz": [("List the topics the quiz covers", 0.15), ("Revise those topics from your notes", 0.45), ("Practise a few questions", 0.3), ("Take the quiz", 0.1)],
    "assessment": [("List the topics the assessment covers", 0.1), ("Revise weakest topics first", 0.45), ("Practise past questions", 0.35), ("Final review", 0.1)],
    "assignment": [("Read the brief and marking criteria", 0.1), ("Collect notes and sources", 0.15), ("Outline your answer", 0.15),
                   ("Write the first draft", 0.4), ("Check against the brief", 0.1), ("Submit and save evidence", 0.1)],
}


def _subtask_out(s: Subtask) -> dict:
    return {"id": s.id, "title": s.title, "done": s.done, "position": s.position, "minutes": s.minutes, "origin": s.origin}


def _subtasks(db: Session, user: User, work_id: int) -> list[Subtask]:
    return list(db.scalars(select(Subtask).where(Subtask.user_id == user.id, Subtask.coursework_id == work_id).order_by(Subtask.position, Subtask.id)))


@router.get("/work/{work_id}/workspace")
def workspace(work_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Everything needed to actually do an assignment, in one call."""
    work = get_student_work(db, work_id, user)
    item = to_work_item(work, get_submission(db, work, user))
    hits = retrieval.search(db, user.id, f"{work.title} {(work.instructions or '')[:300]}", course_id=work.course_id, limit=6)
    topics = []
    if work.course_id:
        text = f"{work.title} {work.instructions or ''}"
        for topic in db.scalars(select(Topic).where(Topic.user_id == user.id, Topic.course_id == work.course_id, Topic.parent_id.is_not(None))):
            score = topic_match_score(topic.title, text)
            if score >= 0.5:
                topics.append({"id": topic.id, "title": topic.title, "status": topic.status, "score": score})
        topics.sort(key=lambda t: -t["score"])
    sessions = list(db.scalars(select(StudySession).where(StudySession.user_id == user.id, StudySession.coursework_id == work.id).order_by(StudySession.started_at.desc())))
    spent = sum(s.active_seconds for s in sessions) // 60
    sources = [
        {"provider": s.provider, "url": s.url, "last_seen_at": s.last_seen_at}
        for s in db.scalars(select(CourseworkSource).where(CourseworkSource.owner_id == user.id, CourseworkSource.coursework_id == work.id))
    ]
    subtasks = _subtasks(db, user, work.id)
    return {
        "item": item.model_dump(),
        "subtasks": [_subtask_out(s) for s in subtasks],
        "materials": [h.cite() for h in hits],
        "topics": topics[:6],
        "sessions": [session_out(s) for s in sessions[:10]],
        "spent_minutes": spent,
        "remaining_minutes": max(0, item.priority.effort_minutes - spent),
        "sources": sources,
        "has_attachment": bool(work.attachment_key),
        "checklist_done": sum(1 for s in subtasks if s.done),
    }


@router.post("/work/{work_id}/breakdown")
def breakdown(work_id: int, replace: bool = False, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Split the work into concrete steps with time estimates. Uses the model when available, else a template."""
    work = get_student_work(db, work_id, user)
    submission = get_submission(db, work, user)
    existing = _subtasks(db, user, work.id)
    if existing and not replace:
        raise HTTPException(409, "This already has steps. Replace them to generate new ones.")
    effort = (submission.effort_minutes if submission and submission.effort_minutes else None) or 120
    steps: list[tuple[str, int]] = []
    method = "template"
    if llm.available():
        try:
            data = llm.generate(
                "Break a university assignment into 3-7 concrete, checkable steps a student can work through in order. "
                "Each step starts with a verb. Estimate minutes for each; the total should be close to the given effort. "
                'Return JSON {"steps":[{"title": str (max 12 words), "minutes": int}]}.',
                f"TITLE: {work.title}\nTYPE: {work.kind}\nEFFORT: about {effort} minutes\nINSTRUCTIONS:\n{(work.instructions or '(none given)')[:5000]}",
                json_mode=True,
                fast=True,
            )
            for row in (data.get("steps") or [])[:7] if isinstance(data, dict) else []:
                title = str(row.get("title", "")).strip()[:200]
                try:
                    minutes = max(5, min(600, int(row.get("minutes") or 0)))
                except (TypeError, ValueError):
                    minutes = None
                if title:
                    steps.append((title, minutes))
            method = "ai" if steps else "template"
        except llm.LLMError:
            steps = []
    if not steps:
        template = TEMPLATES.get(work.kind, TEMPLATES["assignment"])
        steps = [(title, max(5, int(round(effort * share / 5) * 5))) for title, share in template]
    for s in existing:
        db.delete(s)
    for position, (title, minutes) in enumerate(steps, start=1):
        db.add(Subtask(coursework_id=work.id, user_id=user.id, title=title, minutes=minutes, position=position, origin="ai" if method == "ai" else "manual"))
    db.commit()
    return {"method": method, "subtasks": [_subtask_out(s) for s in _subtasks(db, user, work.id)]}


@router.post("/work/{work_id}/subtasks", status_code=201)
def add_subtask(work_id: int, payload: SubtaskCreate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    work = get_student_work(db, work_id, user)
    position = (db.scalar(select(func.max(Subtask.position)).where(Subtask.user_id == user.id, Subtask.coursework_id == work.id)) or 0) + 1
    subtask = Subtask(coursework_id=work.id, user_id=user.id, title=payload.title.strip(), minutes=payload.minutes, position=position)
    db.add(subtask)
    db.commit()
    return _subtask_out(subtask)


@router.patch("/subtasks/{subtask_id}")
def update_subtask(subtask_id: int, payload: SubtaskUpdate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    subtask = owned(db, Subtask, subtask_id, user, "Step")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None or field == "minutes":
            setattr(subtask, field, value.strip() if field == "title" else value)
    db.commit()
    return _subtask_out(subtask)


@router.delete("/subtasks/{subtask_id}", status_code=204)
def delete_subtask(subtask_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    db.delete(owned(db, Subtask, subtask_id, user, "Step"))
    db.commit()
    return Response(status_code=204)


@router.put("/work/{work_id}/notes")
def save_notes(work_id: int, payload: NotesUpdate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    work = get_student_work(db, work_id, user)
    submission = get_submission(db, work, user, create=True)
    submission.notes = payload.notes
    db.commit()
    return {"notes": submission.notes}


@router.post("/work/{work_id}/local-done")
def local_done(work_id: int, payload: LocalDone, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """The student's own 'I've finished this' mark, kept separate from what Teams or a teacher reports."""
    work = get_student_work(db, work_id, user)
    submission = get_submission(db, work, user, create=True)
    submission.local_done_at = utcnow() if payload.done else None
    audit(db, user.id, "work.local_done", f"work:{work.id}", done=payload.done)
    db.commit()
    return to_work_item(work, submission).model_dump()


@router.post("/work/{work_id}/snooze")
def snooze(work_id: int, payload: Snooze, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    work = get_student_work(db, work_id, user)
    until = aware(payload.until, zone(profile_for(db, user)))
    if until <= utcnow():
        raise HTTPException(422, "Snooze until a time in the future.")
    if work.due_at and until >= work.due_at:
        raise HTTPException(422, "You can't snooze past the deadline.")
    submission = get_submission(db, work, user, create=True)
    submission.snoozed_until, submission.snooze_reason = until, (payload.reason or "").strip() or None
    db.commit()
    return to_work_item(work, submission).model_dump()


@router.delete("/work/{work_id}/snooze")
def unsnooze(work_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    work = get_student_work(db, work_id, user)
    submission = get_submission(db, work, user, create=True)
    submission.snoozed_until, submission.snooze_reason = None, None
    db.commit()
    return to_work_item(work, submission).model_dump()


@router.post("/work/{work_id}/confirm-due")
def confirm_due(work_id: int, payload: ConfirmDue, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Confirm (or correct) a deadline that was read from text, so it stops being flagged as a guess."""
    work = get_student_work(db, work_id, user)
    if work.owner_id != user.id:
        raise HTTPException(409, "Your teacher sets this deadline.")
    if payload.due_at is not None:
        work.due_at = aware(payload.due_at, zone(profile_for(db, user)))
    work.due_confidence = "manual"
    db.commit()
    return to_work_item(work, get_submission(db, work, user)).model_dump()
