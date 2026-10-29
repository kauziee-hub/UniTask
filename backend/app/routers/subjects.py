"""Subjects, their syllabus map, topic prerequisites and previous-year question history."""

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import llm
from ..academic import audit, cluster_questions, save_syllabus, structure_syllabus
from ..academic_models import (
    Attempt,
    Exam,
    Material,
    MaterialPage,
    MaterialTopic,
    Question,
    RevisionCard,
    StudySession,
    Topic,
    TopicLink,
    TutorMemory,
    exam_topics,
)
from ..academic_schemas import LinkCreate, SubjectCreate, SubjectUpdate, SyllabusConfirm, SyllabusExtract, TopicCreate, TopicUpdate
from ..database import get_db
from ..models import Course, Coursework, Submission, User
from ..retrieval import excerpt, tokens
from ..revision import weakness
from ..security import require_student
from ..services import course_brief, get_course_for
from ..workspace import owned, owned_topic, topic_evidence, topic_out, utcnow, visible_courses

router = APIRouter(prefix="/api", tags=["subjects"])
STATUS_ORDER = ["not_started", "in_progress", "revised", "practised"]


def _subject_summary(db: Session, user: User, course: Course, role: str) -> dict:
    rows = db.execute(
        select(Topic.status, func.count())
        .where(Topic.user_id == user.id, Topic.course_id == course.id, Topic.parent_id.is_not(None))
        .group_by(Topic.status)
    ).all()
    coverage = {status: 0 for status in STATUS_ORDER}
    coverage.update(dict(rows))
    total = sum(coverage.values())
    next_exam = db.scalar(
        select(Exam).where(Exam.user_id == user.id, Exam.course_id == course.id, Exam.starts_at > utcnow()).order_by(Exam.starts_at)
    )
    materials = db.scalar(select(func.count()).select_from(Material).where(Material.user_id == user.id, Material.course_id == course.id))
    pyqs = db.scalar(select(func.count()).select_from(Question).where(Question.user_id == user.id, Question.course_id == course.id))
    work_ids = select(Coursework.id).where(
        Coursework.course_id == course.id,
        Coursework.removed_at_source.is_(False),
        (Coursework.owner_id == user.id) | (Coursework.source == "unitask"),
    )
    done = db.scalar(
        select(func.count()).select_from(Submission).where(
            Submission.student_id == user.id,
            Submission.coursework_id.in_(work_ids),
            Submission.status.in_(["turned_in", "returned"]) | Submission.local_done_at.is_not(None),
        )
    )
    open_work = (db.scalar(select(func.count()).select_from(work_ids.subquery())) or 0) - (done or 0)
    unconfirmed = db.scalar(
        select(func.count()).select_from(Topic).where(Topic.user_id == user.id, Topic.course_id == course.id, Topic.confirmed.is_(False))
    )
    return {
        **course_brief(course).model_dump(),
        "my_role": role,
        "editable": course.owner_id == user.id,
        "topic_count": total,
        "coverage": coverage,
        "covered_pct": round(100 * (coverage["revised"] + coverage["practised"]) / total) if total else None,
        "materials": materials or 0,
        "pyq_count": pyqs or 0,
        "open_work": max(0, open_work),
        "unconfirmed": unconfirmed or 0,
        "next_exam": {"id": next_exam.id, "title": next_exam.title, "starts_at": next_exam.starts_at} if next_exam else None,
    }


@router.get("/subjects")
def list_subjects(user: User = Depends(require_student), db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for course in visible_courses(db, user):
        role = "student" if course.owner_id != user.id else "owner"
        out.append(_subject_summary(db, user, course, role))
    return sorted(out, key=lambda s: s["name"].lower())


@router.post("/subjects", status_code=201)
def create_subject(payload: SubjectCreate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    course = Course(name=payload.name.strip(), code=payload.code.strip().upper(), color=payload.color, owner_id=user.id, source="personal")
    db.add(course)
    db.commit()
    db.refresh(course)
    return _subject_summary(db, user, course, "owner")


def _own_course(db: Session, course_id: int, user: User) -> Course:
    course, _ = get_course_for(db, course_id, user)
    if course.owner_id != user.id:
        raise HTTPException(403, "This subject belongs to a class. Ask the teacher to change it.")
    return course


@router.patch("/subjects/{course_id}")
def update_subject(course_id: int, payload: SubjectUpdate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    course = _own_course(db, course_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(course, field, value.strip().upper() if field == "code" else value)
    db.commit()
    return _subject_summary(db, user, course, "owner")


@router.delete("/subjects/{course_id}", status_code=204)
def delete_subject(course_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    course = _own_course(db, course_id, user)
    if course.source != "personal":
        raise HTTPException(409, "Synced subjects are removed by disconnecting their source.")
    db.delete(course)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- syllabus


def _syllabus(db: Session, user: User, course: Course) -> dict:
    topics = list(db.scalars(select(Topic).where(Topic.user_id == user.id, Topic.course_id == course.id).order_by(Topic.position, Topic.id)))
    ids = [t.id for t in topics]
    pages = defaultdict(int)
    for tid, count in db.execute(select(MaterialTopic.topic_id, func.count()).where(MaterialTopic.topic_id.in_(ids)).group_by(MaterialTopic.topic_id)):
        pages[tid] = count
    pyq = dict(db.execute(select(Question.topic_id, func.count()).where(Question.topic_id.in_(ids)).group_by(Question.topic_id)).all())
    links = list(db.scalars(select(TopicLink).where(TopicLink.user_id == user.id, TopicLink.to_topic_id.in_(ids))))
    titles = {t.id: t.title for t in topics}
    children = defaultdict(list)
    for topic in topics:
        if topic.parent_id:
            children[topic.parent_id].append(topic)

    def node(topic: Topic) -> dict:
        evidence = topic_evidence(db, user.id, topic.id)
        return topic_out(
            topic,
            material_pages=pages.get(topic.id, 0),
            pyq_count=pyq.get(topic.id, 0),
            weak_reason=weakness(evidence),
            prerequisites=[
                {"link_id": link.id, "topic_id": link.from_topic_id, "title": titles.get(link.from_topic_id, "(another subject)"), "suggested": link.suggested}
                for link in links
                if link.to_topic_id == topic.id
            ],
        )

    modules = [
        {**node(m), "topics": [node(t) for t in children.get(m.id, [])]}
        for m in topics
        if m.parent_id is None
    ]
    leaves = [t for t in topics if t.parent_id is not None or not children.get(t.id)]
    coverage = {s: sum(1 for t in leaves if t.status == s) for s in STATUS_ORDER}
    return {
        "course": course_brief(course),
        "modules": modules,
        "coverage": coverage,
        "topic_count": len(leaves),
        "unconfirmed": sum(1 for t in topics if not t.confirmed),
        "without_material": [t.title for t in leaves if not pages.get(t.id)][:12],
    }


@router.get("/subjects/{course_id}/syllabus")
def get_syllabus(course_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    course, _ = get_course_for(db, course_id, user)
    return _syllabus(db, user, course)


@router.post("/subjects/{course_id}/topics", status_code=201)
def create_topic(course_id: int, payload: TopicCreate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    course, _ = get_course_for(db, course_id, user)
    if payload.parent_id is not None:
        parent = owned_topic(db, payload.parent_id, user)
        if parent.course_id != course.id or parent.parent_id is not None:
            raise HTTPException(422, "Topics can only be added under a module of this subject.")
    position = (
        db.scalar(
            select(func.max(Topic.position)).where(Topic.user_id == user.id, Topic.course_id == course.id, Topic.parent_id == payload.parent_id)
        )
        or 0
    )
    topic = Topic(
        user_id=user.id,
        course_id=course.id,
        parent_id=payload.parent_id,
        title=payload.title.strip(),
        est_minutes=payload.est_minutes,
        position=position + 1,
    )
    db.add(topic)
    db.commit()
    return topic_out(topic)


@router.patch("/topics/{topic_id}")
def update_topic(topic_id: int, payload: TopicUpdate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    topic = owned_topic(db, topic_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(topic, field, value.strip() if isinstance(value, str) and field == "title" else value)
    if payload.status in {"revised", "practised", "in_progress"}:
        topic.last_studied_at = utcnow()
    db.commit()
    return topic_out(topic)


@router.delete("/topics/{topic_id}", status_code=204)
def delete_topic(topic_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    topic = owned_topic(db, topic_id, user)
    for child in db.scalars(select(Topic).where(Topic.parent_id == topic.id)):
        db.delete(child)
    db.delete(topic)
    db.commit()
    return Response(status_code=204)


@router.post("/subjects/{course_id}/syllabus/extract")
def extract_syllabus(course_id: int, payload: SyllabusExtract, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    course, _ = get_course_for(db, course_id, user)
    text = (payload.text or "").strip()
    if payload.material_id is not None:
        material = owned(db, Material, payload.material_id, user, "Material")
        if material.status != "ready":
            raise HTTPException(409, "That file hasn't finished processing yet.")
        text = "\n".join(p.text for p in db.scalars(select(MaterialPage).where(MaterialPage.material_id == material.id).order_by(MaterialPage.page_no)))
    if len(text) < 20:
        raise HTTPException(422, "Paste the syllabus text or choose a processed syllabus file.")
    modules, method = structure_syllabus(text)
    if not modules:
        raise HTTPException(422, "No module structure found. Try pasting just the syllabus section, one module per line.")
    created = save_syllabus(db, user.id, course.id, modules, confirmed=False, origin="extracted")
    audit(db, user.id, "syllabus.extract", f"course:{course.id}", method=method, created=created)
    db.commit()
    return {"method": method, "modules": len(modules), "created": created, "syllabus": _syllabus(db, user, course)}


@router.post("/subjects/{course_id}/syllabus/confirm")
def confirm_syllabus(course_id: int, payload: SyllabusConfirm, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    course, _ = get_course_for(db, course_id, user)
    pending = list(db.scalars(select(Topic).where(Topic.user_id == user.id, Topic.course_id == course.id, Topic.confirmed.is_(False))))
    if payload.accept:
        for topic in pending:
            topic.confirmed = True
    else:
        for topic in sorted(pending, key=lambda t: t.parent_id is None):  # children before their modules
            db.delete(topic)
    db.commit()
    return _syllabus(db, user, course)


# ---------------------------------------------------------------- prerequisites


@router.post("/topics/{topic_id}/links", status_code=201)
def add_prerequisite(topic_id: int, payload: LinkCreate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    topic = owned_topic(db, topic_id, user)
    prerequisite = owned_topic(db, payload.prerequisite_id, user)
    if prerequisite.id == topic.id:
        raise HTTPException(422, "A topic can't be its own prerequisite.")
    existing = db.scalar(select(TopicLink).where(TopicLink.from_topic_id == prerequisite.id, TopicLink.to_topic_id == topic.id))
    if existing:
        existing.suggested = False
        link = existing
    else:
        link = TopicLink(user_id=user.id, from_topic_id=prerequisite.id, to_topic_id=topic.id, suggested=False)
        db.add(link)
    db.commit()
    return {"id": link.id, "from_topic_id": link.from_topic_id, "to_topic_id": link.to_topic_id, "suggested": link.suggested}


@router.post("/topic-links/{link_id}/accept")
def accept_link(link_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    link = owned(db, TopicLink, link_id, user, "Link")
    link.suggested = False
    db.commit()
    return {"id": link.id, "suggested": False}


@router.delete("/topic-links/{link_id}", status_code=204)
def delete_link(link_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    db.delete(owned(db, TopicLink, link_id, user, "Link"))
    db.commit()
    return Response(status_code=204)


@router.post("/subjects/{course_id}/suggest-links")
def suggest_links(course_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Ask the model which topics depend on which. Suggestions stay flagged until the student accepts them."""
    course, _ = get_course_for(db, course_id, user)
    topics = [t for t in db.scalars(select(Topic).where(Topic.user_id == user.id, Topic.course_id == course.id, Topic.parent_id.is_not(None)))]
    if len(topics) < 2:
        raise HTTPException(409, "Add at least two topics first.")
    if not llm.available():
        raise HTTPException(503, "The AI model isn't configured, so links can't be suggested. Add them by hand.")
    listing = "\n".join(f"{t.id}: {t.title}" for t in topics[:120])
    try:
        data = llm.generate(
            "You map prerequisite relationships between topics of one university subject. Only link topics where "
            "understanding the first is genuinely needed for the second. At most 15 links. "
            'Return JSON {"links":[{"from": id, "to": id}]} using only the ids given.',
            f"SUBJECT: {course.name}\nTOPICS:\n{listing}",
            json_mode=True,
            fast=True,
        )
    except llm.LLMError as exc:
        raise HTTPException(503, str(exc)) from exc
    valid = {t.id for t in topics}
    created = 0
    for item in (data.get("links") or [])[:15] if isinstance(data, dict) else []:
        try:
            a, b = int(item["from"]), int(item["to"])
        except (KeyError, TypeError, ValueError):
            continue
        if a == b or a not in valid or b not in valid:
            continue
        if db.scalar(select(TopicLink.id).where(TopicLink.from_topic_id == a, TopicLink.to_topic_id == b)):
            continue
        db.add(TopicLink(user_id=user.id, from_topic_id=a, to_topic_id=b, suggested=True))
        created += 1
    db.commit()
    return {"suggested": created, "syllabus": _syllabus(db, user, course)}


# ---------------------------------------------------------------- topic detail


@router.get("/topics/{topic_id}")
def topic_detail(topic_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    topic = owned_topic(db, topic_id, user)
    module = db.get(Topic, topic.parent_id) if topic.parent_id else None
    evidence = topic_evidence(db, user.id, topic.id)
    pages = []
    for link, material in db.execute(
        select(MaterialTopic, Material)
        .join(Material, Material.id == MaterialTopic.material_id)
        .where(MaterialTopic.topic_id == topic.id, Material.user_id == user.id)
        .order_by(MaterialTopic.score.desc())
        .limit(12)
    ):
        page = db.scalar(select(MaterialPage).where(MaterialPage.material_id == material.id, MaterialPage.page_no == link.page_no))
        pages.append(
            {
                "material_id": material.id,
                "title": material.title,
                "kind": material.kind,
                "page": link.page_no,
                "excerpt": excerpt(page.text, tokens(topic.title)) if page else "",
            }
        )
    questions = [
        {"id": q.id, "text": q.text, "year": q.year, "label": q.label, "marks": q.marks, "material_id": q.material_id, "page": q.page_no}
        for q in db.scalars(select(Question).where(Question.topic_id == topic.id, Question.user_id == user.id).order_by(Question.year.desc()))
    ]
    links = list(db.scalars(select(TopicLink).where(TopicLink.user_id == user.id, (TopicLink.to_topic_id == topic.id) | (TopicLink.from_topic_id == topic.id))))
    related_ids = {link.from_topic_id for link in links} | {link.to_topic_id for link in links}
    titles = {t.id: t for t in db.scalars(select(Topic).where(Topic.id.in_(related_ids)))}
    minutes = db.scalar(select(func.coalesce(func.sum(StudySession.active_seconds), 0)).where(StudySession.user_id == user.id, StudySession.topic_id == topic.id)) or 0
    exams = [
        {"id": e.id, "title": e.title, "starts_at": e.starts_at}
        for e in db.scalars(
            select(Exam).where(Exam.user_id == user.id, Exam.starts_at > utcnow())
            .where((Exam.id.in_(select(exam_topics.c.exam_id).where(exam_topics.c.topic_id == topic.id))) | (Exam.course_id == topic.course_id))
            .order_by(Exam.starts_at)
        )
    ]
    return {
        **topic_out(topic),
        "course": course_brief(topic.course),
        "module": module.title if module else None,
        "evidence": {
            "attempts": evidence.attempts,
            "correct": evidence.correct,
            "avg_confidence": evidence.avg_confidence,
            "last_at": evidence.last_at,
            "weak_reason": weakness(evidence),
        },
        "pages": pages,
        "questions": questions,
        "prerequisites": [
            {"link_id": l.id, "topic_id": l.from_topic_id, "title": titles[l.from_topic_id].title, "status": titles[l.from_topic_id].status, "suggested": l.suggested}
            for l in links
            if l.to_topic_id == topic.id and l.from_topic_id in titles
        ],
        "dependants": [
            {"link_id": l.id, "topic_id": l.to_topic_id, "title": titles[l.to_topic_id].title, "suggested": l.suggested}
            for l in links
            if l.from_topic_id == topic.id and l.to_topic_id in titles
        ],
        "cards": db.scalar(select(func.count()).select_from(RevisionCard).where(RevisionCard.user_id == user.id, RevisionCard.topic_id == topic.id)) or 0,
        "memory": [
            {"id": m.id, "kind": m.kind, "text": m.text, "created_at": m.created_at}
            for m in db.scalars(select(TutorMemory).where(TutorMemory.user_id == user.id, TutorMemory.topic_id == topic.id).order_by(TutorMemory.created_at.desc()).limit(10))
        ],
        "recent_attempts": [
            {"kind": a.kind, "correct": a.correct, "prompt": a.prompt, "created_at": a.created_at}
            for a in db.scalars(select(Attempt).where(Attempt.user_id == user.id, Attempt.topic_id == topic.id).order_by(Attempt.created_at.desc()).limit(8))
        ],
        "studied_minutes": int(minutes // 60),
        "exams": exams,
    }


# ---------------------------------------------------------------- previous-year questions


@router.get("/subjects/{course_id}/pyq")
def pyq_analysis(course_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Group the student's own past-paper questions by what they ask. History, not prediction."""
    course, _ = get_course_for(db, course_id, user)
    questions = list(db.scalars(select(Question).where(Question.user_id == user.id, Question.course_id == course.id)))
    topics = {t.id: t.title for t in db.scalars(select(Topic).where(Topic.user_id == user.id, Topic.course_id == course.id))}
    papers = {m.id: m for m in db.scalars(select(Material).where(Material.user_id == user.id, Material.course_id == course.id, Material.kind == "pyq"))}
    groups: dict[str, list[Question]] = defaultdict(list)
    ordered = sorted(questions, key=lambda q: (q.year or 0, q.id))
    for q, cluster in zip(ordered, cluster_questions([q.text for q in ordered])):
        groups[f"c{cluster}"].append(q)
    repeated = []
    for key, items in groups.items():
        years = sorted({q.year for q in items if q.year})
        topic_id = next((q.topic_id for q in items if q.topic_id), None)
        repeated.append(
            {
                "pattern_key": key,
                "count": len(items),
                "years": years,
                "topic_id": topic_id,
                "topic": topics.get(topic_id) if topic_id else None,
                "marks": max((q.marks or 0 for q in items), default=0) or None,
                "questions": [
                    {"id": q.id, "text": q.text, "year": q.year, "label": q.label, "marks": q.marks, "material_id": q.material_id, "page": q.page_no}
                    for q in sorted(items, key=lambda q: q.year or 0, reverse=True)
                ],
            }
        )
    repeated.sort(key=lambda g: (-g["count"], -(g["marks"] or 0)))
    by_topic: dict[int | None, int] = defaultdict(int)
    for q in questions:
        by_topic[q.topic_id] += 1
    return {
        "note": "Counts come from the past papers you uploaded. They show what was asked before, not what will be asked.",
        "papers": [{"id": m.id, "title": m.title, "year": m.year, "status": m.status} for m in papers.values()],
        "total_questions": len(questions),
        "groups": repeated,
        "by_topic": sorted(
            [{"topic_id": tid, "topic": topics.get(tid) if tid else "Not matched to a topic", "count": count} for tid, count in by_topic.items()],
            key=lambda row: -row["count"],
        ),
    }
