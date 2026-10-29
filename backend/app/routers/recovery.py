"""Recovery plan: for a student who is behind, what to finish, what to ask more time for and what to push.

Deterministic triage over the same priority scores the rest of the app uses. The time budget is real
(the student's own daily study minutes, or the hours they say they have) and every decision comes with a
concrete reason. The model is only used to word an extension email, which is drafted and never sent.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import llm
from ..database import get_db
from ..models import User
from ..priority import _humanize_hours, _humanize_minutes
from ..schemas import WorkItem
from ..security import require_student
from ..services import get_student_work, get_submission, student_work_items
from ..workspace import profile_for, utcnow, zone

router = APIRouter(prefix="/api", tags=["recovery"])
PENDING = {"assigned", "working"}
HORIZON = timedelta(days=7)
DEFAULT_DAYS = 3
CAN_EXTEND = {"unitask", "teams"}  # someone else set the deadline, so ask them


def _hours(minutes: int) -> str:
    """Round to the nearest half hour for a headline: 545 -> '9h', 570 -> '9.5h'."""
    if minutes < 60:
        return f"{minutes} min"
    halves = round(minutes / 30) / 2
    return f"{halves:g}h"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _reason(item: WorkItem, minutes: int, bucket: str, now: datetime, budget: int) -> str:
    parts = []
    hours_left = (item.due_at - now).total_seconds() / 3600 if item.due_at else None
    if hours_left is not None and hours_left < 0:
        parts.append(f"Overdue by {_humanize_hours(hours_left)}" if item.allow_late else f"Closed {_humanize_hours(hours_left)} ago")
    elif hours_left is not None:
        parts.append(f"Due in {_humanize_hours(hours_left)}")
    parts.append(f"{_humanize_minutes(minutes)} of work")
    if item.points:
        parts.append(f"worth {item.points} points")
    if item.status == "working" and bucket != "missed":
        parts.append("already started")
    if bucket == "keep" and hours_left is not None and hours_left < 0:
        parts.append("late turn-in still allowed")
    elif bucket == "ask_extension":
        parts.append(f"won't fit in your {_hours(budget)} after the items above")
    elif bucket == "defer":
        parts.append("personal task, so you can move the date")
    elif bucket == "missed":
        parts.append("late turn-in not allowed")
    return " · ".join(parts)


def _item(item: WorkItem, minutes: int, bucket: str, now: datetime, budget: int) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "course": item.course.name if item.course else None,
        "source": item.source,
        "due_at": item.due_at,
        "minutes": minutes,
        "reason": _reason(item, minutes, bucket, now, budget),
    }


def _headline(budget: int, needed: int, keep: int, extend: int, defer: int, missed: int, default_budget: bool) -> str:
    window = f" over the next {DEFAULT_DAYS} days" if default_budget else ""
    closed = f" {_plural(missed, 'item')} already closed without late turn-in." if missed else ""
    if needed == 0:
        return f"Nothing open is due in the next 7 days.{closed}".strip()
    if extend == 0 and defer == 0:
        return f"You need about {_hours(needed)} and have {_hours(budget)}{window}. All {keep} fit, in this order.{closed}"
    steps = []
    if keep:
        steps.append(f"Do these {keep}" if keep > 1 else "Do this 1")
    else:
        steps.append("Nothing fits as it stands")
    if extend:
        steps.append(f"ask for more time on {extend}")
    if defer:
        steps.append(f"push {_plural(defer, 'personal task')}")
    return f"You need about {_hours(needed)} but have {_hours(budget)}{window}. {', '.join(steps)}.{closed}"


@router.get("/recovery")
def recovery_plan(
    hours: float | None = Query(default=None, gt=0, le=24 * 7),
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> dict:
    """Triage open work into keep / ask for an extension / defer / missed inside a real time budget."""
    profile = profile_for(db, user)
    default_budget = hours is None
    budget = int(round(hours * 60)) if hours is not None else profile.daily_study_minutes * DEFAULT_DAYS
    now = utcnow()

    candidates, missed = [], []
    for item in student_work_items(db, user):
        if item.status not in PENDING or item.removed_at_source or item.local_done_at or item.due_at is None:
            continue
        if item.due_at < now:
            (candidates if item.allow_late else missed).append(item)
        elif item.due_at <= now + HORIZON:
            candidates.append(item)
    candidates.sort(key=lambda i: (-i.priority.score, i.due_at, i.id))

    keep, extend, defer = [], [], []
    used = 0
    for item in candidates:
        minutes = item.priority.effort_minutes
        if used + minutes <= budget:
            used += minutes
            keep.append(_item(item, minutes, "keep", now, budget))
        elif item.source in CAN_EXTEND:
            extend.append(_item(item, minutes, "ask_extension", now, budget))
        else:
            defer.append(_item(item, minutes, "defer", now, budget))
    missed.sort(key=lambda i: (i.due_at, i.id), reverse=True)
    needed = sum(i.priority.effort_minutes for i in candidates)
    db.commit()
    return {
        "budget_minutes": budget,
        "needed_minutes": needed,
        "keep": keep,
        "ask_extension": extend,
        "defer": defer,
        "missed": [_item(i, i.priority.effort_minutes, "missed", now, budget) for i in missed],
        "headline": _headline(budget, needed, len(keep), len(extend), len(defer), len(missed), default_budget),
    }


# ---------------------------------------------------------------- extension email


def _template(*, teacher: str | None, title: str, course: str | None, due: str | None, started: bool, proposed: str | None, student: str) -> str:
    where = f" for {course}" if course else ""
    when = f", due {due}" if due else ""
    progress = "I have started on it but won't be able to finish it properly by then." if started else "I haven't been able to start it properly yet and won't be able to finish it by then."
    ask = f"Would it be possible to submit it by {proposed}?" if proposed else "Would it be possible to have a short extension?"
    return (
        f"Dear {teacher or 'Professor'},\n\n"
        f"I'm writing about {title}{where}{when}. {progress}\n\n"
        "[reason]\n\n"
        f"{ask} If an extension isn't possible, I'll submit what I have by the original deadline.\n\n"
        "Thank you for considering this.\n\n"
        f"Regards,\n{student}"
    )


@router.post("/work/{work_id}/extension-draft")
def extension_draft(work_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Draft (never send) a short, honest extension request. The student fills in the [reason] themselves."""
    work = get_student_work(db, work_id, user)
    submission = get_submission(db, work, user)
    tz = zone(profile_for(db, user))
    now = utcnow()
    teacher = work.course.owner.name if work.source == "unitask" and work.course and work.course.owner else None
    course = work.course.name if work.course else None
    due = work.due_at.astimezone(tz).strftime("%a %d %b, %H:%M") if work.due_at else None
    proposed = (max(work.due_at, now) + timedelta(days=2)).astimezone(tz).strftime("%a %d %b") if work.due_at else None
    started = bool(submission and submission.status == "working")
    code = f" ({work.course.code})" if work.course and work.course.code else ""
    subject = f"Extension request: {work.title}{code}"
    db.commit()

    facts = "\n".join(
        line
        for line in (
            f"Student: {user.name}",
            f"Teacher: {teacher or 'unknown (use a neutral greeting)'}",
            f"Assignment: {work.title}",
            f"Course: {course}" if course else None,
            f"Due: {due}" if due else "Due: no date given",
            f"Progress: {'started, not finished' if started else 'not started yet'}",
            f"Suggested new date: {proposed}" if proposed else None,
        )
        if line
    )
    try:
        data = llm.generate(
            "You draft short, polite, honest emails from a university student asking a teacher for a deadline extension. "
            "Use only the facts given. Never invent a reason, illness, emergency or progress. Where the reason belongs, "
            "write the placeholder [reason] on its own line for the student to fill in. Offer to submit what they have "
            "if an extension isn't possible. Under 130 words, plain text, no markdown. "
            'Return JSON: {"subject": str, "body": str}.',
            facts,
            json_mode=True,
            fast=True,
        )
        body = data.get("body") if isinstance(data, dict) else None
        if not isinstance(body, str) or "[reason]" not in body:
            raise llm.LLMError("The draft did not leave a [reason] placeholder.")
        ai_subject = data.get("subject")
        return {
            "to": teacher,
            "subject": ai_subject.strip()[:200] if isinstance(ai_subject, str) and ai_subject.strip() else subject,
            "body": body.strip(),
            "generated_by": "ai",
        }
    except llm.LLMError:
        return {
            "to": teacher,
            "subject": subject,
            "body": _template(teacher=teacher, title=work.title, course=course, due=due, started=started, proposed=proposed, student=user.name),
            "generated_by": "template",
        }
