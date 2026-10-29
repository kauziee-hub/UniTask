"""Study Desk sessions, spaced revision, practice questions and the personalised tutor."""

from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import llm, retrieval, revision, tutor
from ..academic_models import (
    Attempt,
    Conversation,
    Exam,
    Message,
    PlanBlock,
    Question,
    RevisionCard,
    StudySession,
    Topic,
    TutorMemory,
)
from ..academic_schemas import (
    CardCreate,
    CardReview,
    CardUpdate,
    CheckAnswer,
    ConversationCreate,
    MessageCreate,
    PracticeAnswer,
    SessionEnd,
    SessionStart,
    SessionUpdate,
)
from ..database import get_db
from ..models import User
from ..security import require_student
from ..services import course_brief, get_student_work, get_submission, to_work_item
from ..workspace import (
    card_out,
    owned,
    owned_topic,
    profile_for,
    require_course,
    session_out,
    topic_evidence,
    utcnow,
    weak_topics,
    zone,
)

router = APIRouter(prefix="/api", tags=["study"])


# ---------------------------------------------------------------- sessions


def _accumulate(session: StudySession, now) -> None:
    if session.state == "active":
        session.active_seconds += max(0, int((now - (session.resumed_at or session.started_at)).total_seconds()))


def _session_target_title(db: Session, user: User, payload: SessionStart) -> str:
    if payload.title:
        return payload.title.strip()
    if payload.coursework_id:
        return get_student_work(db, payload.coursework_id, user).title
    if payload.topic_id:
        return owned_topic(db, payload.topic_id, user).title
    if payload.exam_id:
        return f"Revise for {owned(db, Exam, payload.exam_id, user, 'Exam').title}"
    return "Revision" if payload.kind == "revision" else "Focus session"


@router.post("/sessions", status_code=201)
def start_session(payload: SessionStart, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Start a focus session, or resume the open one for the same assignment/topic."""
    now = utcnow()
    title = _session_target_title(db, user, payload)
    if payload.plan_block_id:
        owned(db, PlanBlock, payload.plan_block_id, user, "Block")
    query = select(StudySession).where(
        StudySession.user_id == user.id,
        StudySession.state.in_(["active", "paused"]),
        StudySession.coursework_id == payload.coursework_id if payload.coursework_id else StudySession.coursework_id.is_(None),
        StudySession.topic_id == payload.topic_id if payload.topic_id else StudySession.topic_id.is_(None),
        StudySession.exam_id == payload.exam_id if payload.exam_id else StudySession.exam_id.is_(None),
        StudySession.kind == payload.kind,
    )
    session = db.scalar(query.order_by(StudySession.started_at.desc()))
    # Only one session runs at a time; others pause, keeping their time.
    for other in db.scalars(select(StudySession).where(StudySession.user_id == user.id, StudySession.state == "active")):
        if session is None or other.id != session.id:
            _accumulate(other, now)
            other.state = "paused"
    if session is None:
        session = StudySession(
            user_id=user.id,
            kind=payload.kind,
            title=title[:200],
            coursework_id=payload.coursework_id,
            topic_id=payload.topic_id,
            exam_id=payload.exam_id,
            plan_block_id=payload.plan_block_id,
            planned_minutes=payload.planned_minutes,
            started_at=now,
            resumed_at=now,
            checklist=[],
        )
        db.add(session)
    elif session.state == "paused":
        session.state, session.resumed_at = "active", now
    if payload.coursework_id:
        work = get_student_work(db, payload.coursework_id, user)
        submission = get_submission(db, work, user, create=True)
        if submission.status == "assigned" and work.source != "teams":
            submission.status = "working"
    db.commit()
    return session_detail(session.id, user, db)


@router.get("/sessions")
def list_sessions(state: str | None = None, limit: int = 30, user: User = Depends(require_student), db: Session = Depends(get_db)) -> list[dict]:
    query = select(StudySession).where(StudySession.user_id == user.id).order_by(StudySession.started_at.desc()).limit(min(limit, 100))
    if state:
        query = query.where(StudySession.state.in_(state.split(",")))
    now = utcnow()
    return [session_out(s, now) for s in db.scalars(query)]


@router.get("/sessions/{session_id}")
def session_detail(session_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Everything the Study Desk needs in one call: the session, its target, related pages and due cards."""
    session = owned(db, StudySession, session_id, user, "Session")
    context: dict = {"work": None, "topic": None, "exam": None}
    query_text = session.title
    course_id = None
    if session.coursework_id:
        work = get_student_work(db, session.coursework_id, user)
        context["work"] = to_work_item(work, get_submission(db, work, user)).model_dump()
        query_text = f"{work.title} {work.instructions or ''}"[:400]
        course_id = work.course_id
    topic = db.get(Topic, session.topic_id) if session.topic_id else None
    if topic and topic.user_id == user.id:
        evidence = topic_evidence(db, user.id, topic.id)
        context["topic"] = {
            "id": topic.id,
            "title": topic.title,
            "status": topic.status,
            "course": course_brief(topic.course),
            "weak_reason": revision.weakness(evidence),
        }
        query_text, course_id = topic.title, topic.course_id
    if session.exam_id:
        exam = db.get(Exam, session.exam_id)
        if exam and exam.user_id == user.id:
            context["exam"] = {"id": exam.id, "title": exam.title, "starts_at": exam.starts_at}
            course_id = course_id or exam.course_id
    hits = retrieval.search(db, user.id, query_text, course_id=course_id, limit=6) if query_text else []
    cards_query = select(RevisionCard).where(RevisionCard.user_id == user.id, RevisionCard.due_at <= utcnow())
    if session.topic_id:
        cards_query = cards_query.where(RevisionCard.topic_id == session.topic_id)
    elif course_id:
        cards_query = cards_query.where(RevisionCard.course_id == course_id)
    cards = list(db.scalars(cards_query.order_by(RevisionCard.due_at).limit(10)))
    total_seconds = db.scalar(
        select(func.coalesce(func.sum(StudySession.active_seconds), 0)).where(
            StudySession.user_id == user.id,
            StudySession.id != session.id,
            (StudySession.coursework_id == session.coursework_id) if session.coursework_id else (StudySession.topic_id == session.topic_id) if session.topic_id else StudySession.id == -1,
        )
    )
    return {
        **session_out(session),
        **context,
        "course_id": course_id,
        "materials": [h.cite() for h in hits],
        "due_cards": [card_out(c) for c in cards],
        "previous_minutes": int((total_seconds or 0) // 60),
    }


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, payload: SessionUpdate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    session = owned(db, StudySession, session_id, user, "Session")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "checklist" and value is not None:
            value = [{"text": str(i.get("text", ""))[:300], "done": bool(i.get("done"))} for i in value[:50] if isinstance(i, dict)]
        setattr(session, field, value)
    db.commit()
    return session_out(session)


def _transition(db: Session, user: User, session_id: int, to: str, payload: SessionEnd | None = None) -> dict:
    session = owned(db, StudySession, session_id, user, "Session")
    now = utcnow()
    if session.state in {"completed", "abandoned"}:
        raise HTTPException(409, "This session has already ended.")
    if to == "paused":
        _accumulate(session, now)
        session.state = "paused"
    elif to == "active":
        for other in db.scalars(select(StudySession).where(StudySession.user_id == user.id, StudySession.state == "active", StudySession.id != session.id)):
            _accumulate(other, now)
            other.state = "paused"
        session.state, session.resumed_at = "active", now
    else:
        _accumulate(session, now)
        session.state, session.ended_at = to, now
        if payload and payload.outcome:
            session.outcome = payload.outcome
        if to == "completed":
            if session.plan_block_id:
                block = db.get(PlanBlock, session.plan_block_id)
                if block and block.user_id == user.id:
                    block.state = "done"
            if session.topic_id:
                topic = db.get(Topic, session.topic_id)
                if topic and topic.user_id == user.id:
                    topic.last_studied_at = now
                    order = ["not_started", "in_progress", "revised", "practised"]
                    wanted = payload.topic_status if payload and payload.topic_status else "in_progress"
                    if order.index(wanted) > order.index(topic.status):
                        topic.status = wanted
    db.commit()
    return session_out(session)


@router.post("/sessions/{session_id}/pause")
def pause_session(session_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    return _transition(db, user, session_id, "paused")


@router.post("/sessions/{session_id}/resume")
def resume_session(session_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    return _transition(db, user, session_id, "active")


@router.post("/sessions/{session_id}/complete")
def complete_session(session_id: int, payload: SessionEnd | None = None, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    return _transition(db, user, session_id, "completed", payload)


@router.post("/sessions/{session_id}/abandon")
def abandon_session(session_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    return _transition(db, user, session_id, "abandoned")


# ---------------------------------------------------------------- revision


def _topic_titles(db: Session, user: User) -> dict[int, str]:
    return {t.id: t.title for t in db.scalars(select(Topic).where(Topic.user_id == user.id))}


@router.get("/revision")
def revision_home(user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    now = utcnow()
    tz = zone(profile_for(db, user))
    titles = _topic_titles(db, user)
    due = list(db.scalars(select(RevisionCard).where(RevisionCard.user_id == user.id, RevisionCard.due_at <= now).order_by(RevisionCard.due_at).limit(60)))
    due_count = db.scalar(select(func.count()).select_from(RevisionCard).where(RevisionCard.user_id == user.id, RevisionCard.due_at <= now)) or 0
    total = db.scalar(select(func.count()).select_from(RevisionCard).where(RevisionCard.user_id == user.id)) or 0
    upcoming: dict[str, int] = defaultdict(int)
    for (due_at,) in db.execute(
        select(RevisionCard.due_at).where(RevisionCard.user_id == user.id, RevisionCard.due_at > now, RevisionCard.due_at <= now + timedelta(days=7))
    ):
        upcoming[due_at.astimezone(tz).date().isoformat()] += 1
    history: dict[str, dict] = {}
    for attempt in db.scalars(select(Attempt).where(Attempt.user_id == user.id, Attempt.created_at >= now - timedelta(days=14))):
        day = attempt.created_at.astimezone(tz).date().isoformat()
        row = history.setdefault(day, {"date": day, "attempts": 0, "correct": 0})
        if attempt.correct is not None:
            row["attempts"] += 1
            row["correct"] += int(attempt.correct)
    db.commit()
    return {
        "due": [card_out(c, titles) for c in due],
        "due_count": due_count,
        "total_cards": total,
        "upcoming": [{"date": d, "count": c} for d, c in sorted(upcoming.items())],
        "weak_topics": weak_topics(db, user),
        "history": sorted(history.values(), key=lambda r: r["date"]),
    }


@router.get("/cards")
def list_cards(topic_id: int | None = None, course_id: int | None = None, user: User = Depends(require_student), db: Session = Depends(get_db)) -> list[dict]:
    query = select(RevisionCard).where(RevisionCard.user_id == user.id).order_by(RevisionCard.created_at.desc()).limit(500)
    if topic_id is not None:
        query = query.where(RevisionCard.topic_id == topic_id)
    if course_id is not None:
        query = query.where(RevisionCard.course_id == course_id)
    titles = _topic_titles(db, user)
    return [card_out(c, titles) for c in db.scalars(query)]


@router.post("/cards", status_code=201)
def create_card(payload: CardCreate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    course_id = payload.course_id
    if payload.topic_id is not None:
        course_id = owned_topic(db, payload.topic_id, user).course_id
    require_course(db, course_id, user)
    card = RevisionCard(user_id=user.id, topic_id=payload.topic_id, course_id=course_id, front=payload.front.strip(), back=payload.back.strip(), origin="manual")
    db.add(card)
    db.commit()
    return card_out(card, _topic_titles(db, user))


@router.patch("/cards/{card_id}")
def update_card(card_id: int, payload: CardUpdate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    card = owned(db, RevisionCard, card_id, user, "Card")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value:
            setattr(card, field, value.strip())
    db.commit()
    return card_out(card, _topic_titles(db, user))


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    db.delete(owned(db, RevisionCard, card_id, user, "Card"))
    db.commit()
    return Response(status_code=204)


@router.post("/cards/{card_id}/review")
def review_card(card_id: int, payload: CardReview, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    card = owned(db, RevisionCard, card_id, user, "Card")
    card.interval_days, card.ease, card.reps, card.lapses, card.due_at = revision.review(card.interval_days, card.ease, card.reps, card.lapses, payload.grade)
    db.add(
        Attempt(
            user_id=user.id,
            topic_id=card.topic_id,
            card_id=card.id,
            kind="card",
            correct=payload.grade != "again",
            confidence=payload.confidence,
            prompt=card.front[:2000],
        )
    )
    db.flush()
    if card.topic_id:
        topic = db.get(Topic, card.topic_id)
        if topic:
            topic.status = revision.evidence_status(topic.status, topic_evidence(db, user.id, topic.id), 0)
            topic.last_studied_at = utcnow()
    db.commit()
    return card_out(card, _topic_titles(db, user))


@router.post("/topics/{topic_id}/cards/generate", status_code=201)
def generate_cards(topic_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Flashcards written only from the student's own pages on this topic, each pointing back to its page."""
    topic = owned_topic(db, topic_id, user)
    hits = retrieval.search(db, user.id, topic.title, course_id=topic.course_id, limit=4)
    if not hits:
        raise HTTPException(409, "None of your materials mention this topic yet. Upload notes for it first.")
    if not llm.available():
        raise HTTPException(503, "No AI model is configured. Write cards by hand from the pages shown on the topic.")
    labelled = {f"S{i}": hit for i, hit in enumerate(hits, start=1)}
    sources = "\n\n".join(f"[{label}] {hit.material_title}, page {hit.page_no}:\n{hit.text[:2000]}" for label, hit in labelled.items())
    profile = profile_for(db, user)
    try:
        data = llm.generate(
            "Write revision flashcards for a university student using ONLY the given sources. Test understanding, not trivia. "
            f"The student prefers: {tutor.STYLE.get(profile.explain_style, '')} "
            'Return JSON {"cards":[{"front": str, "back": str (max 60 words), "source": "S1"}]} with at most 6 cards. '
            "Every card must name the source label it came from.",
            f"TOPIC: {topic.title}\n\nSOURCES:\n{sources}",
            json_mode=True,
            fast=True,
        )
    except llm.LLMError as exc:
        raise HTTPException(503, str(exc)) from exc
    created = []
    for item in (data.get("cards") or [])[:6] if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        hit = labelled.get(str(item.get("source", "")).strip("[] "))
        front, back = str(item.get("front", "")).strip(), str(item.get("back", "")).strip()
        if not (hit and front and back):
            continue  # an uncited card is dropped rather than shown without a source
        card = RevisionCard(
            user_id=user.id,
            topic_id=topic.id,
            course_id=topic.course_id,
            front=front[:2000],
            back=back[:4000],
            material_id=hit.material_id,
            page_no=hit.page_no,
            origin="ai",
        )
        db.add(card)
        created.append(card)
    db.commit()
    titles = _topic_titles(db, user)
    return {"created": len(created), "cards": [card_out(c, titles) for c in created]}


@router.post("/questions/{question_id}/practice")
def practise_question(question_id: int, payload: PracticeAnswer, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Answer a past-paper question. Graded against the student's own pages when a model is available."""
    question = owned(db, Question, question_id, user, "Question")
    correct, feedback, citations = payload.self_correct, None, []
    if llm.available():
        hits = retrieval.search(db, user.id, question.text, course_id=question.course_id, limit=3)
        sources = "\n\n".join(f"[S{i}] {h.material_title}, page {h.page_no}:\n{h.text[:1500]}" for i, h in enumerate(hits, start=1))
        try:
            verdict = llm.generate(
                "Grade a university student's exam answer fairly. Use the SOURCES (the student's own notes) as the reference when "
                'they are relevant. Return JSON {"correct": bool, "feedback": str (max 120 words: what was right, what was missing), '
                '"used_sources": [str]}.',
                f"QUESTION ({question.marks or '?'} marks): {question.text}\n\nSOURCES:\n{sources or '(none)'}\n\nSTUDENT ANSWER: {payload.answer}",
                json_mode=True,
                fast=True,
            )
            correct = bool(verdict.get("correct"))
            feedback = str(verdict.get("feedback", ""))[:1200]
            labels = {f"S{i}": h for i, h in enumerate(hits, start=1)}
            citations = [labels[label].cite() for label in verdict.get("used_sources", []) if label in labels]
        except llm.LLMError:
            feedback = None
    if correct is None:
        return {"graded": False, "message": "Automatic grading isn't available. Mark your own answer as right or wrong to record it."}
    db.add(
        Attempt(
            user_id=user.id,
            topic_id=question.topic_id,
            question_id=question.id,
            kind="question",
            correct=correct,
            confidence=payload.confidence,
            prompt=question.text[:2000],
            answer=payload.answer,
            feedback=feedback,
        )
    )
    if correct is False:
        db.add(
            RevisionCard(
                user_id=user.id,
                topic_id=question.topic_id,
                course_id=question.course_id,
                front=question.text[:2000],
                back=(feedback or "Review this question against your notes.")[:4000],
                material_id=question.material_id,
                page_no=question.page_no,
                origin="mistake",
            )
        )
    db.commit()
    return {"graded": True, "correct": correct, "feedback": feedback, "citations": citations, "card_created": correct is False}


# ---------------------------------------------------------------- tutor


def _conversation_out(conversation: Conversation, titles: dict[int, str] | None = None) -> dict:
    return {
        "id": conversation.id,
        "mode": conversation.mode,
        "title": conversation.title,
        "course_id": conversation.course_id,
        "topic_id": conversation.topic_id,
        "topic": (titles or {}).get(conversation.topic_id) if conversation.topic_id else None,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def _message_out(message: Message) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "citations": message.citations or [],
        "check": {"question": message.check["question"]} if message.check else None,
        "created_at": message.created_at,
    }


@router.get("/tutor/conversations")
def list_conversations(user: User = Depends(require_student), db: Session = Depends(get_db)) -> list[dict]:
    titles = _topic_titles(db, user)
    return [
        _conversation_out(c, titles)
        for c in db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).limit(50))
    ]


@router.post("/tutor/conversations", status_code=201)
def create_conversation(payload: ConversationCreate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    course_id = payload.course_id
    if payload.topic_id is not None:
        course_id = owned_topic(db, payload.topic_id, user).course_id
    require_course(db, course_id, user)
    conversation = Conversation(user_id=user.id, mode=payload.mode, course_id=course_id, topic_id=payload.topic_id)
    db.add(conversation)
    db.commit()
    return {**_conversation_out(conversation, _topic_titles(db, user)), "messages": []}


@router.get("/tutor/conversations/{conversation_id}")
def get_conversation(conversation_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    conversation = owned(db, Conversation, conversation_id, user, "Conversation")
    return {**_conversation_out(conversation, _topic_titles(db, user)), "messages": [_message_out(m) for m in conversation.messages]}


@router.delete("/tutor/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    db.delete(owned(db, Conversation, conversation_id, user, "Conversation"))
    db.commit()
    return Response(status_code=204)


@router.post("/tutor/conversations/{conversation_id}/messages")
def send_message(conversation_id: int, payload: MessageCreate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    conversation = owned(db, Conversation, conversation_id, user, "Conversation")
    reply = tutor.respond(db, conversation, payload.text.strip())
    db.commit()
    return {"reply": _message_out(reply), "conversation": _conversation_out(conversation, _topic_titles(db, user)), "ai": llm.describe()}


@router.post("/tutor/messages/{message_id}/check")
def answer_check(message_id: int, payload: CheckAnswer, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    message = db.get(Message, message_id)
    conversation = db.get(Conversation, message.conversation_id) if message else None
    if message is None or conversation is None or conversation.user_id != user.id:
        raise HTTPException(404, "Message not found.")
    if not message.check:
        raise HTTPException(409, "That message has no check question.")
    if db.scalar(select(Attempt.id).where(Attempt.user_id == user.id, Attempt.kind == "check", Attempt.prompt == message.check["question"])):
        raise HTTPException(409, "You've already answered this check question.")
    result = tutor.grade_check(db, conversation, message, payload.answer.strip(), payload.confidence)
    db.commit()
    return {**result, "expected": message.check.get("expected"), "messages": [_message_out(m) for m in conversation.messages[-2:]]}


@router.get("/tutor/memory")
def tutor_memory(user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """What the tutor has learned about the student. Everything here can be deleted."""
    profile = profile_for(db, user)
    titles = _topic_titles(db, user)
    db.commit()
    return {
        "profile": {"pace": profile.pace, "explain_style": profile.explain_style, "background": profile.background},
        "memories": [
            {"id": m.id, "kind": m.kind, "text": m.text, "topic_id": m.topic_id, "topic": titles.get(m.topic_id) if m.topic_id else None, "created_at": m.created_at}
            for m in db.scalars(select(TutorMemory).where(TutorMemory.user_id == user.id).order_by(TutorMemory.created_at.desc()))
        ],
    }


@router.delete("/tutor/memory/{memory_id}", status_code=204)
def forget(memory_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    db.delete(owned(db, TutorMemory, memory_id, user, "Memory"))
    db.commit()
    return Response(status_code=204)


@router.delete("/tutor/memory", status_code=204)
def forget_all(user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    db.execute(delete(TutorMemory).where(TutorMemory.user_id == user.id))
    db.commit()
    return Response(status_code=204)
