"""The Academic Command Centre, insights that lead to an action, the inbox and the student's profile."""

import os
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import llm
from ..academic_models import (
    Attempt,
    Exam,
    InboxEvent,
    Material,
    MaterialTopic,
    PlanBlock,
    RevisionCard,
    StudySession,
    TimetableEntry,
    Topic,
)
from ..academic_schemas import ProfileUpdate
from ..database import get_db
from ..models import Connection, User
from ..schemas import UserRead
from ..security import get_current_user, require_student
from ..services import course_brief, student_work_items
from ..workspace import (
    DONE_STATUSES,
    block_out,
    exam_out,
    exam_topics,
    inbox_out,
    local_day_bounds,
    owned,
    profile_for,
    session_out,
    utcnow,
    visible_courses,
    weak_topics,
    zone,
)

router = APIRouter(prefix="/api", tags=["home"])


def _pending(items):
    now = utcnow()
    return [
        i
        for i in items
        if i.status not in DONE_STATUSES
        and not i.local_done_at
        and not i.removed_at_source
        and i.priority.tier != "missed"
        and not (i.snoozed_until and i.snoozed_until > now)
    ]


def _action(kind: str, title: str, reason: str, label: str, to: str, session: dict | None = None) -> dict:
    return {"kind": kind, "title": title, "reason": reason, "label": label, "to": to, "session": session}


def next_best_action(db: Session, user: User, pending, now: datetime, tz) -> dict:
    """One clear thing to do now, chosen by explicit rules so the reason can always be shown."""
    active = db.scalar(select(StudySession).where(StudySession.user_id == user.id, StudySession.state == "active"))
    if active:
        return _action("resume", active.title, "Your focus session is still running.", "Back to the desk", f"/study/{active.id}")
    block = db.scalar(
        select(PlanBlock).where(PlanBlock.user_id == user.id, PlanBlock.state == "planned", PlanBlock.starts_at <= now, PlanBlock.ends_at > now)
    )
    if block:
        session = {"kind": "rescue" if block.kind == "rescue" else "assignment" if block.coursework_id else "topic", "coursework_id": block.coursework_id,
                   "topic_id": block.topic_id, "exam_id": block.exam_id, "plan_block_id": block.id,
                   "planned_minutes": max(5, int((block.ends_at - block.starts_at).total_seconds() // 60)), "title": block.title}
        return _action("block", block.title, f"Planned for now until {block.ends_at.astimezone(tz):%H:%M}. {block.reason or ''}".strip(), "Start this block", "", session)
    overdue = [i for i in pending if i.priority.tier == "overdue"]
    if overdue:
        item = overdue[0]
        return _action("work", item.title, item.priority.reason, "Open workspace", f"/work/{item.id}",
                       {"kind": "assignment", "coursework_id": item.id, "planned_minutes": min(90, item.priority.effort_minutes)})
    for exam in db.scalars(select(Exam).where(Exam.user_id == user.id, Exam.starts_at > now, Exam.starts_at <= now + timedelta(hours=48)).order_by(Exam.starts_at)):
        topics = exam_topics(db, exam)
        left = [t for t in topics if t.status not in {"revised", "practised"}]
        if left or not topics:
            hours = int((exam.starts_at - now).total_seconds() // 3600)
            reason = f"Exam in {hours}h with {len(left)} of {len(topics)} topics not yet revised." if topics else f"Exam in {hours}h and no topics are listed yet."
            return _action("rescue", exam.title, reason, "Open Exam Rescue", f"/exams/{exam.id}")
    now_items = [i for i in pending if i.priority.tier == "now"]
    if now_items:
        item = now_items[0]
        return _action("work", item.title, item.priority.reason, "Open workspace", f"/work/{item.id}",
                       {"kind": "assignment", "coursework_id": item.id, "planned_minutes": min(90, item.priority.effort_minutes)})
    paused = db.scalar(select(StudySession).where(StudySession.user_id == user.id, StudySession.state == "paused").order_by(StudySession.started_at.desc()))
    if paused:
        return _action("resume", paused.title, "You paused this session. Pick up where you left off.", "Resume", f"/study/{paused.id}")
    due_cards = db.scalar(select(func.count()).select_from(RevisionCard).where(RevisionCard.user_id == user.id, RevisionCard.due_at <= now)) or 0
    if due_cards >= 5:
        return _action("revision", f"Review {due_cards} flashcards", "Spaced revision is due. A few minutes now keeps them from piling up.", "Start revision", "/revision")
    soon = [i for i in pending if i.priority.tier == "soon"]
    if soon:
        item = soon[0]
        return _action("work", item.title, item.priority.reason, "Open workspace", f"/work/{item.id}",
                       {"kind": "assignment", "coursework_id": item.id, "planned_minutes": min(60, item.priority.effort_minutes)})
    weak = weak_topics(db, user, limit=1)
    if weak:
        return _action("practise", weak[0]["title"], f"Weak spot: {weak[0]['reason']}.", "Practise with the tutor", f"/tutor?topic={weak[0]['topic_id']}")
    if due_cards:
        return _action("revision", f"Review {due_cards} flashcard{'s' if due_cards > 1 else ''}", "Revision is due today.", "Start revision", "/revision")
    if pending:
        item = pending[0]
        return _action("work", item.title, item.priority.reason, "Open workspace", f"/work/{item.id}")
    return _action("plan", "Nothing urgent", "No deadlines are pressing. Plan the week or get ahead on a subject.", "Open planner", "/planner")


def _today(db: Session, user: User, items, tz, now: datetime) -> list[dict]:
    local = now.astimezone(tz).date()
    start, end = local_day_bounds(local, tz)
    courses = {c.id: c for c in visible_courses(db, user)}
    out = []
    for entry in db.scalars(select(TimetableEntry).where(TimetableEntry.user_id == user.id, TimetableEntry.weekday == local.weekday(), TimetableEntry.confirmed.is_(True))):
        h1, m1 = map(int, entry.start.split(":"))
        h2, m2 = map(int, entry.end.split(":"))
        s = datetime(local.year, local.month, local.day, h1, m1, tzinfo=tz)
        e = datetime(local.year, local.month, local.day, h2, m2, tzinfo=tz)
        course = courses.get(entry.course_id) if entry.course_id else None
        out.append({"kind": entry.kind, "title": entry.title, "start": s, "end": e, "location": entry.location, "color": course.color if course else None, "link": None})
    for block in db.scalars(select(PlanBlock).where(PlanBlock.user_id == user.id, PlanBlock.starts_at < end, PlanBlock.ends_at > start)):
        out.append({"kind": "study", "title": block.title, "start": block.starts_at, "end": block.ends_at, "state": block.state, "block": block_out(block), "link": None})
    for exam in db.scalars(select(Exam).where(Exam.user_id == user.id, Exam.starts_at >= start, Exam.starts_at < end)):
        out.append({"kind": "exam", "title": exam.title, "start": exam.starts_at, "end": exam.starts_at + timedelta(minutes=exam.duration_minutes),
                    "location": exam.location, "link": f"/exams/{exam.id}"})
    for item in items:
        if item.due_at and start <= item.due_at < end:
            out.append({"kind": "deadline", "title": item.title, "start": item.due_at, "end": None, "color": item.course.color if item.course else None,
                        "link": f"/work/{item.id}", "done": item.status in DONE_STATUSES or bool(item.local_done_at)})
    out.sort(key=lambda row: row["start"])
    return out


def _warnings(db: Session, user: User, pending, now: datetime) -> list[dict]:
    out = []
    inferred = [i for i in pending if i.due_confidence == "inferred"]
    if inferred:
        out.append({"kind": "confirm_due", "text": f"{len(inferred)} deadline{'s were' if len(inferred) > 1 else ' was'} read from text and need{'' if len(inferred) > 1 else 's'} confirming.",
                    "label": "Check", "to": f"/work/{inferred[0].id}"})
    for exam in db.scalars(select(Exam).where(Exam.user_id == user.id, Exam.starts_at > now, Exam.starts_at <= now + timedelta(days=14)).order_by(Exam.starts_at)):
        topics = exam_topics(db, exam)
        if not topics:
            out.append({"kind": "exam_topics", "text": f"{exam.title} has no topics yet, so UniTask can't plan revision for it.", "label": "Add topics", "to": f"/exams/{exam.id}"})
            continue
        covered = {tid for (tid,) in db.execute(select(MaterialTopic.topic_id).where(MaterialTopic.topic_id.in_([t.id for t in topics])).distinct())}
        missing = [t for t in topics if t.id not in covered]
        if missing:
            out.append({"kind": "missing_material", "text": f"{len(missing)} of {len(topics)} topics for {exam.title} have no notes or slides in your library.",
                        "label": "Upload material", "to": "/library"})
    stuck = db.scalar(select(func.count()).select_from(Material).where(Material.user_id == user.id, Material.status.in_(["needs_ocr", "failed"]))) or 0
    if stuck:
        out.append({"kind": "materials", "text": f"{stuck} uploaded file{'s' if stuck > 1 else ''} couldn't be read fully.", "label": "Review", "to": "/library"})
    missed = db.scalar(select(func.count()).select_from(PlanBlock).where(PlanBlock.user_id == user.id, PlanBlock.state == "planned", PlanBlock.ends_at < now, PlanBlock.ends_at > now - timedelta(days=3))) or 0
    if missed:
        out.append({"kind": "missed", "text": f"{missed} planned block{'s' if missed > 1 else ''} passed without being done.", "label": "Replan", "to": "/planner"})
    unconfirmed = db.scalar(select(func.count()).select_from(TimetableEntry).where(TimetableEntry.user_id == user.id, TimetableEntry.confirmed.is_(False))) or 0
    if unconfirmed:
        out.append({"kind": "timetable", "text": f"{unconfirmed} class{'es' if unconfirmed > 1 else ''} read from your timetable image need checking.", "label": "Review", "to": "/planner?tab=timetable"})
    return out


@router.get("/home")
def home(user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    profile = profile_for(db, user)
    tz = zone(profile)
    now = utcnow()
    items = student_work_items(db, user)
    pending = sorted(_pending(items), key=lambda i: i.priority.score, reverse=True)
    week_start_local = now.astimezone(tz).date() - timedelta(days=now.astimezone(tz).weekday())
    week_start, _ = local_day_bounds(week_start_local, tz)

    radar = sorted([i for i in pending if i.due_at and i.due_at <= now + timedelta(days=14)], key=lambda i: i.due_at)
    exams = [exam_out(db, e, now) for e in db.scalars(select(Exam).where(Exam.user_id == user.id, Exam.starts_at > now, Exam.starts_at <= now + timedelta(days=21)).order_by(Exam.starts_at))]
    inbox = list(db.scalars(select(InboxEvent).where(InboxEvent.user_id == user.id, InboxEvent.dismissed_at.is_(None)).order_by(InboxEvent.created_at.desc()).limit(5)))
    unread = db.scalar(select(func.count()).select_from(InboxEvent).where(InboxEvent.user_id == user.id, InboxEvent.read_at.is_(None), InboxEvent.dismissed_at.is_(None))) or 0
    open_sessions = list(db.scalars(select(StudySession).where(StudySession.user_id == user.id, StudySession.state.in_(["active", "paused"])).order_by(StudySession.started_at.desc()).limit(3)))
    due_cards = db.scalar(select(func.count()).select_from(RevisionCard).where(RevisionCard.user_id == user.id, RevisionCard.due_at <= now)) or 0

    week_sessions = list(db.scalars(select(StudySession).where(StudySession.user_id == user.id, StudySession.started_at >= week_start)))
    week_attempts = list(db.scalars(select(Attempt).where(Attempt.user_id == user.id, Attempt.created_at >= week_start, Attempt.correct.is_not(None))))
    done_this_week = [i for i in items if (i.local_done_at and i.local_done_at >= week_start) or (i.submitted_at and i.submitted_at >= week_start)]
    coverage = []
    for course in visible_courses(db, user):
        rows = dict(db.execute(select(Topic.status, func.count()).where(Topic.user_id == user.id, Topic.course_id == course.id, Topic.parent_id.is_not(None)).group_by(Topic.status)).all())
        total = sum(rows.values())
        if total:
            coverage.append({"course": course_brief(course), "total": total, "covered": rows.get("revised", 0) + rows.get("practised", 0), "started": rows.get("in_progress", 0)})

    teams = db.scalar(select(Connection).where(Connection.user_id == user.id, Connection.provider == "teams"))
    setup = {
        "onboarded": profile.onboarded,
        "has_subjects": bool(visible_courses(db, user)),
        "has_work": bool(items),
        "has_timetable": db.scalar(select(TimetableEntry.id).where(TimetableEntry.user_id == user.id).limit(1)) is not None,
        "has_materials": db.scalar(select(Material.id).where(Material.user_id == user.id).limit(1)) is not None,
        "has_exams": db.scalar(select(Exam.id).where(Exam.user_id == user.id).limit(1)) is not None,
        "connections": [c.provider for c in db.scalars(select(Connection).where(Connection.user_id == user.id))],
    }
    db.commit()
    return {
        "now": now,
        "timezone": tz.key,
        "next": next_best_action(db, user, pending, now, tz),
        "today": _today(db, user, items, tz, now),
        "radar": [i.model_dump() for i in radar[:12]],
        "overdue": [i.model_dump() for i in pending if i.priority.tier == "overdue"][:6],
        "exams": exams,
        "inbox": {"unread": unread, "items": [inbox_out(e) for e in inbox]},
        "study": {
            "sessions": [session_out(s, now) for s in open_sessions],
            "due_cards": due_cards,
            "weak_topics": weak_topics(db, user, limit=3),
        },
        "progress": {
            "minutes_this_week": sum(s.active_seconds for s in week_sessions) // 60
            + sum(int((now - (s.resumed_at or s.started_at)).total_seconds()) for s in week_sessions if s.state == "active") // 60,
            "sessions_completed": sum(1 for s in week_sessions if s.state == "completed"),
            "items_done": len(done_this_week),
            "answers": len(week_attempts),
            "correct": sum(1 for a in week_attempts if a.correct),
            "coverage": coverage,
        },
        "warnings": _warnings(db, user, pending, now),
        "setup": setup,
        "teams": {"status": teams.status if teams else "not_connected", "last_synced_at": teams.last_synced_at if teams else None},
    }


# ---------------------------------------------------------------- insights


@router.get("/insights")
def insights(user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Charts built only from recorded activity. Each one ends in something to do about it."""
    profile = profile_for(db, user)
    tz = zone(profile)
    now = utcnow()
    today = now.astimezone(tz).date()
    since, _ = local_day_bounds(today - timedelta(days=13), tz)

    minutes = {(today - timedelta(days=d)).isoformat(): 0 for d in range(13, -1, -1)}
    for s in db.scalars(select(StudySession).where(StudySession.user_id == user.id, StudySession.started_at >= since)):
        seconds = s.active_seconds + (int((now - (s.resumed_at or s.started_at)).total_seconds()) if s.state == "active" else 0)
        key = s.started_at.astimezone(tz).date().isoformat()
        if key in minutes:
            minutes[key] += seconds // 60

    items = student_work_items(db, user)
    done = []
    for i in items:
        finished = i.local_done_at or (i.submitted_at if i.status in DONE_STATUSES else None)
        if finished:
            done.append((i, finished))
    recent_done = [(i, f) for i, f in done if f >= now - timedelta(days=30)]
    with_due = [(i, f) for i, f in recent_done if i.due_at]
    on_time = sum(1 for i, f in with_due if f <= i.due_at)
    completions = defaultdict(int)
    for _, finished in recent_done:
        completions[finished.astimezone(tz).date().isoformat()] += 1

    pending = _pending(items)
    workload = {(today + timedelta(days=d)).isoformat(): {"minutes": 0, "items": 0, "exams": 0} for d in range(14)}
    for i in pending:
        if i.due_at:
            key = i.due_at.astimezone(tz).date().isoformat()
            if key in workload:
                workload[key]["minutes"] += i.priority.effort_minutes
                workload[key]["items"] += 1
    for exam in db.scalars(select(Exam).where(Exam.user_id == user.id, Exam.starts_at > now, Exam.starts_at <= now + timedelta(days=14))):
        key = exam.starts_at.astimezone(tz).date().isoformat()
        if key in workload:
            workload[key]["exams"] += 1

    coverage = []
    for course in visible_courses(db, user):
        rows = dict(db.execute(select(Topic.status, func.count()).where(Topic.user_id == user.id, Topic.course_id == course.id, Topic.parent_id.is_not(None)).group_by(Topic.status)).all())
        if rows:
            coverage.append({"course": course_brief(course), **{k: rows.get(k, 0) for k in ("not_started", "in_progress", "revised", "practised")}, "total": sum(rows.values())})

    accuracy = defaultdict(lambda: {"attempts": 0, "correct": 0})
    for a in db.scalars(select(Attempt).where(Attempt.user_id == user.id, Attempt.created_at >= now - timedelta(days=30), Attempt.correct.is_not(None), Attempt.topic_id.is_not(None))):
        accuracy[a.topic_id]["attempts"] += 1
        accuracy[a.topic_id]["correct"] += int(a.correct)
    titles = {t.id: t for t in db.scalars(select(Topic).where(Topic.id.in_(list(accuracy))))}
    topic_accuracy = sorted(
        [{"topic_id": tid, "title": titles[tid].title, "course": course_brief(titles[tid].course), **row, "rate": round(row["correct"] / row["attempts"], 2)}
         for tid, row in accuracy.items() if tid in titles],
        key=lambda r: (r["rate"], -r["attempts"]),
    )

    actions = []
    heaviest = max(workload.items(), key=lambda kv: kv[1]["minutes"], default=None)
    if heaviest and heaviest[1]["minutes"] >= max(240, profile.daily_study_minutes):
        actions.append({"text": f"{heaviest[0]} has about {heaviest[1]['minutes'] // 60}h of work due. Spread it out now.", "label": "Replan the week", "to": "/planner"})
    lowest = min(coverage, key=lambda c: (c["revised"] + c["practised"]) / c["total"], default=None)
    if lowest and (lowest["revised"] + lowest["practised"]) / lowest["total"] < 0.5:
        actions.append({"text": f"{lowest['course'].name}: only {lowest['revised'] + lowest['practised']} of {lowest['total']} topics revised.", "label": "Open syllabus", "to": f"/subjects/{lowest['course'].id}"})
    if topic_accuracy and topic_accuracy[0]["rate"] < 0.6 and topic_accuracy[0]["attempts"] >= 2:
        weakest = topic_accuracy[0]
        actions.append({"text": f"{weakest['title']}: {weakest['correct']} of {weakest['attempts']} answers correct this month.", "label": "Practise with the tutor", "to": f"/tutor?topic={weakest['topic_id']}"})
    if sum(minutes.values()) == 0:
        actions.append({"text": "No focus sessions recorded in two weeks, so there's nothing to chart yet.", "label": "Start a session", "to": "/"})
    db.commit()
    return {
        "study_minutes": [{"date": d, "minutes": m} for d, m in minutes.items()],
        "completions": [{"date": d, "count": c} for d, c in sorted(completions.items())],
        "on_time": {"done": len(with_due), "on_time": on_time, "rate": round(on_time / len(with_due), 2) if with_due else None},
        "workload": [{"date": d, **row} for d, row in workload.items()],
        "coverage": coverage,
        "topic_accuracy": topic_accuracy[:12],
        "actions": actions,
    }


# ---------------------------------------------------------------- inbox


@router.get("/inbox")
def list_inbox(include_dismissed: bool = False, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    query = select(InboxEvent).where(InboxEvent.user_id == user.id).order_by(InboxEvent.created_at.desc()).limit(200)
    if not include_dismissed:
        query = query.where(InboxEvent.dismissed_at.is_(None))
    events = list(db.scalars(query))
    unread = db.scalar(select(func.count()).select_from(InboxEvent).where(InboxEvent.user_id == user.id, InboxEvent.read_at.is_(None), InboxEvent.dismissed_at.is_(None))) or 0
    return {"unread": unread, "items": [inbox_out(e) for e in events]}


@router.post("/inbox/{event_id}/read")
def read_event(event_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    event = owned(db, InboxEvent, event_id, user, "Notification")
    event.read_at = event.read_at or utcnow()
    db.commit()
    return inbox_out(event)


@router.post("/inbox/{event_id}/dismiss")
def dismiss_event(event_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    event = owned(db, InboxEvent, event_id, user, "Notification")
    now = utcnow()
    event.read_at = event.read_at or now
    event.dismissed_at = now
    db.commit()
    return inbox_out(event)


@router.post("/inbox/read-all", status_code=204)
def read_all(user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    now = utcnow()
    for event in db.scalars(select(InboxEvent).where(InboxEvent.user_id == user.id, InboxEvent.read_at.is_(None))):
        event.read_at = now
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- profile


def _profile_out(db: Session, user: User) -> dict:
    profile = profile_for(db, user)
    return {
        "user": UserRead.model_validate(user).model_dump(),
        "university": profile.university,
        "semester": profile.semester,
        "timezone": profile.timezone,
        "day_start": profile.day_start,
        "day_end": profile.day_end,
        "daily_study_minutes": profile.daily_study_minutes,
        "pace": profile.pace,
        "explain_style": profile.explain_style,
        "background": profile.background,
        "attendance_threshold": profile.attendance_threshold,
        "onboarded": profile.onboarded,
        "extension_token": bool(profile.ingest_token_hash),
        "ai": ai_status(),
    }


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    out = _profile_out(db, user)
    db.commit()
    return out


@router.patch("/profile")
def update_profile(payload: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    profile = profile_for(db, user)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("timezone"):
        try:
            ZoneInfo(changes["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, "Unknown timezone.") from None
    name = changes.pop("name", None)
    if name:
        user.name = name.strip()
    for field, value in changes.items():
        if value is not None or field in {"university", "semester", "background", "attendance_threshold"}:
            setattr(profile, field, value)
    if profile.day_end <= profile.day_start:
        raise HTTPException(422, "Your day must end after it starts.")
    db.commit()
    return _profile_out(db, user)


@router.get("/ai/status")
def ai_status() -> dict:
    described = llm.describe()
    return {
        **described,
        "available": llm.available(),
        "ocr": os.getenv("OCR_PROVIDER", "llm" if llm.available() else "none").lower(),
        "email": os.getenv("EMAIL_PROVIDER", "log").lower(),
    }
