"""Queries and serialisers shared by the student workspace routers.

Every lookup here is scoped to the signed-in student: rows are fetched with ``user_id == user.id``
(or, for classes, through ``services.get_course_for``), so another student's id is simply a 404.
"""

import math
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import rescue, scheduler
from .academic_models import (
    Attempt,
    Exam,
    InboxEvent,
    Material,
    MaterialTopic,
    PlanBlock,
    Profile,
    Question,
    RevisionCard,
    StudySession,
    TimetableEntry,
    Topic,
    TopicLink,
)
from .models import Course, CourseMember, User
from .revision import Evidence, weakness
from .services import course_brief, get_course_for, student_work_items

DONE_STATUSES = {"turned_in", "returned"}


# ---------------------------------------------------------------- ownership


def profile_for(db: Session, user: User) -> Profile:
    profile = db.get(Profile, user.id)
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)
        db.flush()
    return profile


def owned(db: Session, model, row_id: int, user: User, label: str = "Item"):
    row = db.get(model, row_id)
    if row is None or getattr(row, "user_id", None) != user.id:
        raise HTTPException(404, f"{label} not found.")
    return row


def require_course(db: Session, course_id: int | None, user: User) -> Course | None:
    if course_id is None:
        return None
    course, _ = get_course_for(db, course_id, user)
    return course


def visible_courses(db: Session, user: User) -> list[Course]:
    owned_courses = list(db.scalars(select(Course).where(Course.owner_id == user.id)))
    joined = list(
        db.scalars(
            select(Course)
            .join(CourseMember, CourseMember.course_id == Course.id)
            .where(CourseMember.user_id == user.id, Course.owner_id != user.id)
        )
    )
    return owned_courses + joined


def owned_topic(db: Session, topic_id: int, user: User) -> Topic:
    return owned(db, Topic, topic_id, user, "Topic")


# ---------------------------------------------------------------- time


def zone(profile: Profile) -> ZoneInfo:
    try:
        return ZoneInfo(profile.timezone or "Asia/Kolkata")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Kolkata")


def aware(value: datetime | None, tz: ZoneInfo) -> datetime | None:
    """Naive datetimes from forms are in the student's own timezone."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    return value.astimezone(timezone.utc)


def local_day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0, 0), tz).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- serialisers


def topic_out(topic: Topic, **extra) -> dict:
    return {
        "id": topic.id,
        "course_id": topic.course_id,
        "parent_id": topic.parent_id,
        "title": topic.title,
        "position": topic.position,
        "status": topic.status,
        "confirmed": topic.confirmed,
        "origin": topic.origin,
        "est_minutes": topic.est_minutes,
        "last_studied_at": topic.last_studied_at,
        **extra,
    }


def material_out(material: Material) -> dict:
    return {
        "id": material.id,
        "title": material.title,
        "filename": material.filename,
        "kind": material.kind,
        "course": course_brief(material.course),
        "content_type": material.content_type,
        "size_bytes": material.size_bytes,
        "page_count": material.page_count,
        "status": material.status,
        "extractor": material.extractor,
        "error": material.error,
        "year": material.year,
        "created_at": material.created_at,
    }


def exam_out(db: Session, exam: Exam, now: datetime | None = None) -> dict:
    now = now or utcnow()
    topics = exam_topics(db, exam)
    covered = sum(1 for t in topics if t.status in {"revised", "practised"})
    blocks = db.scalar(
        select(func.count()).select_from(PlanBlock).where(PlanBlock.exam_id == exam.id, PlanBlock.state == "planned")
    )
    return {
        "id": exam.id,
        "title": exam.title,
        "course": course_brief(exam.course),
        "starts_at": exam.starts_at,
        "duration_minutes": exam.duration_minutes,
        "location": exam.location,
        "notes": exam.notes,
        "hours_left": round((exam.starts_at - now).total_seconds() / 3600, 1),
        "topic_count": len(topics),
        "covered_count": covered,
        "explicit_topics": bool(exam.topics),
        "planned_blocks": blocks or 0,
    }


def block_out(block: PlanBlock) -> dict:
    return {
        "id": block.id,
        "title": block.title,
        "kind": block.kind,
        "state": block.state,
        "starts_at": block.starts_at,
        "ends_at": block.ends_at,
        "minutes": int((block.ends_at - block.starts_at).total_seconds() // 60),
        "coursework_id": block.coursework_id,
        "topic_id": block.topic_id,
        "exam_id": block.exam_id,
        "reason": block.reason,
        "plan": block.plan,
    }


def session_out(session: StudySession, now: datetime | None = None) -> dict:
    now = now or utcnow()
    seconds = session.active_seconds
    if session.state == "active":
        seconds += int((now - (session.resumed_at or session.started_at)).total_seconds())
    return {
        "id": session.id,
        "kind": session.kind,
        "title": session.title,
        "state": session.state,
        "planned_minutes": session.planned_minutes,
        "elapsed_seconds": max(0, seconds),
        "started_at": session.started_at,
        "resumed_at": session.resumed_at,
        "ended_at": session.ended_at,
        "coursework_id": session.coursework_id,
        "topic_id": session.topic_id,
        "exam_id": session.exam_id,
        "plan_block_id": session.plan_block_id,
        "scratch": session.scratch,
        "checklist": session.checklist or [],
        "resume": session.resume,
        "outcome": session.outcome,
    }


def card_out(card: RevisionCard, topic_titles: dict[int, str] | None = None) -> dict:
    return {
        "id": card.id,
        "front": card.front,
        "back": card.back,
        "topic_id": card.topic_id,
        "topic": (topic_titles or {}).get(card.topic_id) if card.topic_id else None,
        "course_id": card.course_id,
        "material_id": card.material_id,
        "page_no": card.page_no,
        "origin": card.origin,
        "due_at": card.due_at,
        "interval_days": card.interval_days,
        "reps": card.reps,
        "lapses": card.lapses,
    }


def inbox_out(event: InboxEvent) -> dict:
    return {
        "id": event.id,
        "kind": event.kind,
        "title": event.title,
        "body": event.body,
        "link": event.link,
        "source": event.source,
        "created_at": event.created_at,
        "read": event.read_at is not None,
        "dismissed": event.dismissed_at is not None,
    }


def entry_out(entry: TimetableEntry, courses: dict[int, Course] | None = None) -> dict:
    course = (courses or {}).get(entry.course_id) if entry.course_id else None
    return {
        "id": entry.id,
        "title": entry.title,
        "course": course_brief(course),
        "course_id": entry.course_id,
        "weekday": entry.weekday,
        "start": entry.start,
        "end": entry.end,
        "kind": entry.kind,
        "location": entry.location,
        "source": entry.source,
        "confirmed": entry.confirmed,
    }


# ---------------------------------------------------------------- evidence


def topic_evidence(db: Session, user_id: int, topic_id: int, days: int = 45) -> Evidence:
    since = utcnow() - timedelta(days=days)
    attempts = list(
        db.scalars(select(Attempt).where(Attempt.user_id == user_id, Attempt.topic_id == topic_id, Attempt.created_at >= since))
    )
    graded = [a for a in attempts if a.correct is not None]
    confidences = [a.confidence for a in attempts if a.confidence]
    return Evidence(
        attempts=len(graded),
        correct=sum(1 for a in graded if a.correct),
        avg_confidence=sum(confidences) / len(confidences) if confidences else None,
        last_at=max((a.created_at for a in attempts), default=None),
    )


def weak_topics(db: Session, user: User, limit: int = 8) -> list[dict]:
    since = utcnow() - timedelta(days=45)
    topic_ids = [
        tid
        for (tid,) in db.execute(
            select(Attempt.topic_id).where(Attempt.user_id == user.id, Attempt.topic_id.is_not(None), Attempt.created_at >= since).distinct()
        )
    ]
    out = []
    for topic in db.scalars(select(Topic).where(Topic.id.in_(topic_ids), Topic.user_id == user.id)):
        evidence = topic_evidence(db, user.id, topic.id)
        reason = weakness(evidence)
        if reason:
            out.append(
                {
                    "topic_id": topic.id,
                    "title": topic.title,
                    "course": course_brief(topic.course),
                    "reason": reason,
                    "accuracy": round(evidence.correct / evidence.attempts, 2) if evidence.attempts else None,
                    "attempts": evidence.attempts,
                }
            )
    out.sort(key=lambda row: (row["accuracy"] if row["accuracy"] is not None else 1.0))
    return out[:limit]


def leaf_topics(db: Session, user_id: int, course_id: int) -> list[Topic]:
    """Topics to study: children, plus modules that have no children of their own."""
    rows = list(db.scalars(select(Topic).where(Topic.user_id == user_id, Topic.course_id == course_id).order_by(Topic.position)))
    parents = {t.parent_id for t in rows if t.parent_id}
    return [t for t in rows if t.parent_id is not None or t.id not in parents]


def exam_topics(db: Session, exam: Exam) -> list[Topic]:
    if exam.topics:
        return list(exam.topics)
    if exam.course_id is None:
        return []
    return leaf_topics(db, exam.user_id, exam.course_id)


def rescue_inputs(db: Session, user: User, exam: Exam) -> list[rescue.TopicInput]:
    topics = exam_topics(db, exam)
    if not topics:
        return []
    ids = [t.id for t in topics]
    titles = {t.id: t.title for t in db.scalars(select(Topic).where(Topic.user_id == user.id, Topic.parent_id.is_(None)))}
    pyq = dict(
        db.execute(
            select(Question.topic_id, func.count()).where(Question.user_id == user.id, Question.topic_id.in_(ids)).group_by(Question.topic_id)
        ).all()
    )
    links = list(db.scalars(select(TopicLink).where(TopicLink.user_id == user.id, TopicLink.suggested.is_(False))))
    with_material = {
        tid for (tid,) in db.execute(select(MaterialTopic.topic_id).where(MaterialTopic.topic_id.in_(ids)).distinct())
    }
    inputs = []
    for topic in topics:
        evidence = topic_evidence(db, user.id, topic.id)
        inputs.append(
            rescue.TopicInput(
                id=topic.id,
                title=topic.title,
                module=titles.get(topic.parent_id, "") if topic.parent_id else topic.title,
                status=topic.status,
                pyq_count=pyq.get(topic.id, 0),
                dependants=sum(1 for link in links if link.from_topic_id == topic.id),
                prerequisites=tuple(link.from_topic_id for link in links if link.to_topic_id == topic.id),
                has_material=topic.id in with_material,
                weak=weakness(evidence) is not None,
                est_minutes=topic.est_minutes,
            )
        )
    return inputs


# ---------------------------------------------------------------- planning


def timetable_rows(db: Session, user: User) -> list[dict]:
    return [
        {"weekday": e.weekday, "start": e.start, "end": e.end, "title": e.title, "kind": e.kind}
        for e in db.scalars(select(TimetableEntry).where(TimetableEntry.user_id == user.id, TimetableEntry.confirmed.is_(True)))
    ]


def busy_for(db: Session, user: User, profile: Profile, start: datetime, days: int, *, include_rescue: bool = True) -> list[scheduler.Busy]:
    tz = zone(profile)
    local_start = start.astimezone(tz).date()
    busy = scheduler.weekly_busy(timetable_rows(db, user), local_start, days + 1, tz.key)
    window_end = start + timedelta(days=days + 1)
    for exam in db.scalars(select(Exam).where(Exam.user_id == user.id, Exam.starts_at < window_end)):
        end = exam.starts_at + timedelta(minutes=exam.duration_minutes)
        if end > start:
            busy.append(scheduler.Busy(exam.starts_at, end, exam.title, "exam"))
    if include_rescue:
        for block in db.scalars(
            select(PlanBlock).where(
                PlanBlock.user_id == user.id,
                PlanBlock.state == "planned",
                PlanBlock.plan.like("rescue:%"),
                PlanBlock.ends_at > start,
                PlanBlock.starts_at < window_end,
            )
        ):
            busy.append(scheduler.Busy(block.starts_at, block.ends_at, block.title, "block"))
    return busy


def spent_minutes(db: Session, user: User, *, coursework_id: int | None = None, exam_id: int | None = None) -> int:
    query = select(func.coalesce(func.sum(StudySession.active_seconds), 0)).where(StudySession.user_id == user.id)
    if coursework_id is not None:
        query = query.where(StudySession.coursework_id == coursework_id)
    if exam_id is not None:
        query = query.where(StudySession.exam_id == exam_id)
    return int((db.scalar(query) or 0) // 60)


def build_demands(db: Session, user: User, profile: Profile, now: datetime, horizon_days: int) -> list[scheduler.Demand]:
    """Everything that needs time: pending coursework, exam preparation and due revision cards."""
    demands: list[scheduler.Demand] = []
    horizon = now + timedelta(days=horizon_days)
    for item in student_work_items(db, user):
        if item.status in DONE_STATUSES or item.local_done_at or item.removed_at_source:
            continue
        if item.priority.tier == "missed" or (item.snoozed_until and item.snoozed_until > now):
            continue
        if item.due_at and item.due_at > horizon + timedelta(days=7):
            continue
        remaining = max(0, item.priority.effort_minutes - spent_minutes(db, user, coursework_id=item.id))
        if remaining < 10:
            continue
        demands.append(
            scheduler.Demand(
                key=f"work:{item.id}",
                title=item.title,
                minutes=remaining,
                deadline=item.due_at,
                kind="work",
                priority=item.priority.score,
                estimated=item.effort_minutes is None,
                coursework_id=item.id,
                reason=item.priority.reason,
            )
        )
    for exam in db.scalars(select(Exam).where(Exam.user_id == user.id, Exam.starts_at > now, Exam.starts_at <= horizon + timedelta(days=7))):
        topics = [t for t in exam_topics(db, exam) if t.status != "practised"]
        if not topics:
            continue
        minutes = sum(t.est_minutes or rescue.STATUS_MINUTES.get(t.status, 60) for t in topics)
        minutes = max(0, minutes - spent_minutes(db, user, exam_id=exam.id))
        if minutes < 10:
            continue
        demands.append(
            scheduler.Demand(
                key=f"exam:{exam.id}",
                title=f"Prepare: {exam.title}",
                minutes=minutes,
                deadline=exam.starts_at,
                kind="study",
                priority=50,
                estimated=True,
                exam_id=exam.id,
                reason=f"{len(topics)} topic{'s' if len(topics) != 1 else ''} not yet practised before the exam",
            )
        )
    due_cards = db.scalar(select(func.count()).select_from(RevisionCard).where(RevisionCard.user_id == user.id, RevisionCard.due_at <= now))
    if due_cards:
        tz = zone(profile)
        _, end_of_day = local_day_bounds(now.astimezone(tz).date(), tz)
        demands.append(
            scheduler.Demand(
                key="cards",
                title=f"Review {due_cards} flashcard{'s' if due_cards != 1 else ''}",
                minutes=min(45, max(scheduler.MIN_CHUNK, math.ceil(due_cards * 1.5))),
                deadline=end_of_day,
                kind="revision",
                priority=20,
                reason="Spaced revision is due today",
            )
        )
    return demands


def forecast(db: Session, user: User, profile: Profile, now: datetime, days: int) -> tuple[scheduler.Outcome, list[scheduler.Demand]]:
    busy = busy_for(db, user, profile, now, days)
    slots = scheduler.free_slots(now, days, zone(profile).key, profile.day_start, profile.day_end, busy)
    demands = build_demands(db, user, profile, now, days)
    return scheduler.schedule(demands, slots, daily_cap=profile.daily_study_minutes, tz=zone(profile).key, now=now), demands


def outcome_out(outcome: scheduler.Outcome) -> dict:
    return {
        "unfit": [
            {
                "key": u.demand.key,
                "title": u.demand.title,
                "missing_minutes": u.missing_minutes,
                "reason": u.reason,
                "deadline": u.demand.deadline,
                "coursework_id": u.demand.coursework_id,
                "exam_id": u.demand.exam_id,
                "estimated": u.demand.estimated,
            }
            for u in outcome.unfit
        ],
        "risk": outcome.risk,
        "load": outcome.load,
    }


def conflict_list(busy: list[scheduler.Busy]) -> list[dict]:
    return [
        {"a": a.title, "a_kind": a.kind, "b": b.title, "b_kind": b.kind, "start": max(a.start, b.start), "end": min(a.end, b.end)}
        for a, b in scheduler.conflicts(busy)
    ]
