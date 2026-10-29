"""Exams and the Exam Rescue engine: what to study when there isn't time for everything."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import rescue, scheduler
from ..academic import audit
from ..academic_models import Exam, Material, MaterialTopic, PlanBlock, Topic
from ..academic_schemas import ExamCreate, ExamTopics, ExamUpdate, RescueRequest
from ..database import get_db
from ..models import User
from ..security import require_student
from ..workspace import (
    aware,
    block_out,
    busy_for,
    exam_out,
    exam_topics,
    owned,
    profile_for,
    require_course,
    rescue_inputs,
    topic_out,
    utcnow,
    zone,
)

router = APIRouter(prefix="/api", tags=["exams"])


def _own_topics(db: Session, user: User, ids: list[int]) -> list[Topic]:
    topics = list(db.scalars(select(Topic).where(Topic.id.in_(ids), Topic.user_id == user.id)))
    if len(topics) != len(set(ids)):
        raise HTTPException(404, "Topic not found.")
    return topics


@router.get("/exams")
def list_exams(include_past: bool = False, user: User = Depends(require_student), db: Session = Depends(get_db)) -> list[dict]:
    now = utcnow()
    query = select(Exam).where(Exam.user_id == user.id).order_by(Exam.starts_at)
    if not include_past:
        query = query.where(Exam.starts_at > now - timedelta(hours=6))
    return [exam_out(db, exam, now) for exam in db.scalars(query)]


@router.post("/exams", status_code=201)
def create_exam(payload: ExamCreate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    profile = profile_for(db, user)
    course = require_course(db, payload.course_id, user)
    exam = Exam(
        user_id=user.id,
        course_id=course.id if course else None,
        title=payload.title.strip(),
        starts_at=aware(payload.starts_at, zone(profile)),
        duration_minutes=payload.duration_minutes,
        location=payload.location,
        notes=payload.notes,
    )
    if payload.topic_ids:
        exam.topics = _own_topics(db, user, payload.topic_ids)
    db.add(exam)
    db.commit()
    return exam_out(db, exam)


@router.get("/exams/{exam_id}")
def exam_detail(exam_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    exam = owned(db, Exam, exam_id, user, "Exam")
    topics = exam_topics(db, exam)
    blocks = db.scalars(select(PlanBlock).where(PlanBlock.exam_id == exam.id).order_by(PlanBlock.starts_at))
    return {
        **exam_out(db, exam),
        "topics": [topic_out(t) for t in topics],
        "blocks": [block_out(b) for b in blocks],
    }


@router.patch("/exams/{exam_id}")
def update_exam(exam_id: int, payload: ExamUpdate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    exam = owned(db, Exam, exam_id, user, "Exam")
    changes = payload.model_dump(exclude_unset=True)
    if "course_id" in changes:
        require_course(db, changes["course_id"], user)
    if changes.get("starts_at"):
        changes["starts_at"] = aware(changes["starts_at"], zone(profile_for(db, user)))
    for field, value in changes.items():
        if value is not None or field in {"course_id", "location", "notes"}:
            setattr(exam, field, value)
    db.commit()
    return exam_out(db, exam)


@router.put("/exams/{exam_id}/topics")
def set_exam_topics(exam_id: int, payload: ExamTopics, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    exam = owned(db, Exam, exam_id, user, "Exam")
    exam.topics = _own_topics(db, user, payload.topic_ids)
    db.commit()
    return exam_detail(exam_id, user, db)


@router.delete("/exams/{exam_id}", status_code=204)
def delete_exam(exam_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    exam = owned(db, Exam, exam_id, user, "Exam")
    db.execute(delete(PlanBlock).where(PlanBlock.exam_id == exam.id, PlanBlock.state == "planned"))
    db.delete(exam)
    db.commit()
    return Response(status_code=204)


def _rescue(db: Session, user: User, exam: Exam, payload: RescueRequest) -> dict:
    """Build the rescue plan without saving anything."""
    profile = profile_for(db, user)
    tz = zone(profile)
    now = utcnow()
    if exam.starts_at <= now:
        raise HTTPException(409, "This exam has already started.")
    inputs = rescue_inputs(db, user, exam)
    if not inputs:
        raise HTTPException(409, "Add the exam's topics first: link a subject with a syllabus, or choose topics.")

    days = max(1, (exam.starts_at - now).days + 1)
    busy = [b for b in busy_for(db, user, profile, now, days, include_rescue=False) if b.start < exam.starts_at]
    slots = [s for s in scheduler.free_slots(now, days, tz.key, profile.day_start, profile.day_end, busy) if s.start < exam.starts_at]
    for slot in slots:
        slot.end = min(slot.end, exam.starts_at - timedelta(minutes=30))
    slots = [s for s in slots if s.minutes >= scheduler.MIN_CHUNK]
    free_minutes = sum(s.minutes for s in slots)
    budget = int(payload.hours * 60) if payload.hours else min(free_minutes, days * profile.daily_study_minutes)

    chosen, excluded, needed = rescue.plan(inputs, budget, payload.mode)
    material_pages: dict[int, list[dict]] = {}
    for link, material in db.execute(
        select(MaterialTopic, Material)
        .join(Material, Material.id == MaterialTopic.material_id)
        .where(MaterialTopic.topic_id.in_([p.topic.id for p in chosen]), Material.user_id == user.id)
        .order_by(MaterialTopic.score.desc())
    ):
        pages = material_pages.setdefault(link.topic_id, [])
        if len(pages) < 3:
            pages.append({"material_id": material.id, "title": material.title, "page": link.page_no})

    # Lay the chosen topics into real free time, in study order (deadline = 30 min before the exam).
    demands = [
        scheduler.Demand(
            key=f"topic:{p.topic.id}",
            title=p.topic.title,
            minutes=p.minutes,
            deadline=exam.starts_at - timedelta(minutes=30),
            kind="rescue",
            priority=len(chosen) - index,
            topic_id=p.topic.id,
            exam_id=exam.id,
            reason=p.reason,
        )
        for index, p in enumerate(chosen)
    ]
    # Keep study order: give each demand a strictly increasing pseudo-deadline inside the window.
    for index, demand in enumerate(demands):
        demand.deadline = exam.starts_at - timedelta(minutes=30) - timedelta(seconds=len(demands) - index)
    outcome = scheduler.schedule(demands, slots, daily_cap=max(profile.daily_study_minutes, budget), tz=tz.key, now=now)

    chosen_minutes = sum(p.minutes for p in chosen)
    if not chosen:
        message = f"{budget} minutes isn't enough for even one topic. Focus on the formula sheet and past-paper answers you already know."
    elif excluded:
        message = (
            f"Covering everything needs about {needed // 60}h {needed % 60}m; you have {budget // 60}h {budget % 60}m. "
            f"This plan covers the {len(chosen)} topics with the most value per minute and leaves out {len(excluded)}."
        )
    else:
        message = f"Everything fits: {chosen_minutes} of your {budget} minutes."
    return {
        "exam": exam_out(db, exam, now),
        "mode": payload.mode,
        "mode_label": rescue.MODES[payload.mode]["label"],
        "budget_minutes": budget,
        "free_minutes": free_minutes,
        "needed_minutes": needed,
        "chosen_minutes": chosen_minutes,
        "feasible": not excluded,
        "message": message,
        "chosen": [
            {
                "order": index + 1,
                "topic_id": p.topic.id,
                "title": p.topic.title,
                "module": p.topic.module,
                "status": p.topic.status,
                "minutes": p.minutes,
                "reason": p.reason,
                "pyq_count": p.topic.pyq_count,
                "weak": p.topic.weak,
                "has_material": p.topic.has_material,
                "materials": material_pages.get(p.topic.id, []),
            }
            for index, p in enumerate(chosen)
        ],
        "excluded": [{"topic_id": t.id, "title": t.title, "minutes": m, "reason": r} for t, m, r in excluded],
        "schedule": [
            {"topic_id": b.demand.topic_id, "title": b.demand.title, "starts_at": b.start, "ends_at": b.end}
            for b in outcome.blocks
        ],
        "unscheduled": [u.demand.title for u in outcome.unfit],
    }


@router.post("/exams/{exam_id}/rescue")
def rescue_preview(exam_id: int, payload: RescueRequest, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    return _rescue(db, user, owned(db, Exam, exam_id, user, "Exam"), payload)


@router.post("/exams/{exam_id}/rescue/apply")
def rescue_apply(exam_id: int, payload: RescueRequest, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    exam = owned(db, Exam, exam_id, user, "Exam")
    plan = _rescue(db, user, exam, payload)
    db.execute(delete(PlanBlock).where(PlanBlock.user_id == user.id, PlanBlock.plan == f"rescue:{exam.id}", PlanBlock.state == "planned"))
    reasons = {c["topic_id"]: c["reason"] for c in plan["chosen"]}
    for item in plan["schedule"]:
        db.add(
            PlanBlock(
                user_id=user.id,
                starts_at=item["starts_at"],
                ends_at=item["ends_at"],
                topic_id=item["topic_id"],
                exam_id=exam.id,
                title=item["title"],
                kind="rescue",
                reason=reasons.get(item["topic_id"], "")[:300],
                plan=f"rescue:{exam.id}",
            )
        )
    audit(db, user.id, "rescue.apply", f"exam:{exam.id}", mode=payload.mode, blocks=len(plan["schedule"]))
    db.commit()
    plan["applied"] = len(plan["schedule"])
    return plan
