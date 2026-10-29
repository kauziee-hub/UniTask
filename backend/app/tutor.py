"""A tutor that knows this particular student.

Each reply is built from:
- the learner profile (pace, preferred style, background in their own words)
- evidence about the topic: coverage status, recent answers and their accuracy, confidence
- the tutor's memory of this student: misconceptions, what clicked, what they struggle with
- excerpts from the student's own materials, labelled [S1]..[Sn]

The model must cite only the excerpts it was given; citations are validated against that list before
anything is stored, so a fabricated page reference can never reach the student. After teaching, the
tutor asks one check question. The answer is graded, recorded as evidence, and a wrong answer
becomes a revision card and a misconception the tutor remembers next time.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import llm, retrieval
from .academic_models import Attempt, Conversation, Message, Profile, RevisionCard, Topic, TutorMemory
from .revision import Evidence, weakness

logger = logging.getLogger(__name__)

STYLE = {
    "examples": "Lead with a concrete worked example, then the general idea.",
    "concise": "Be brief and precise. Bullet points over paragraphs.",
    "step_by_step": "Go one small step at a time and number the steps.",
    "analogies": "Use an everyday analogy first, then connect it to the formal definition.",
}
PACE = {
    "slow": "The student prefers a slow pace: one idea per reply, check understanding before moving on.",
    "steady": "Normal pace: one or two ideas per reply.",
    "fast": "The student moves fast: cover more ground, skip basics they have shown they know.",
}


def topic_evidence(db: Session, user_id: int, topic_id: int | None) -> Evidence:
    if topic_id is None:
        return Evidence(0, 0, None, None)
    since = datetime.now(timezone.utc) - timedelta(days=45)
    attempts = list(db.scalars(select(Attempt).where(Attempt.user_id == user_id, Attempt.topic_id == topic_id, Attempt.created_at >= since)))
    graded = [a for a in attempts if a.correct is not None]
    confidences = [a.confidence for a in attempts if a.confidence]
    return Evidence(
        attempts=len(graded),
        correct=sum(1 for a in graded if a.correct),
        avg_confidence=sum(confidences) / len(confidences) if confidences else None,
        last_at=max((a.created_at for a in attempts), default=None),
    )


def learner_brief(db: Session, user_id: int, topic: Topic | None) -> str:
    profile = db.get(Profile, user_id) or Profile(user_id=user_id)
    lines = [STYLE.get(profile.explain_style, STYLE["examples"]), PACE.get(profile.pace, PACE["steady"])]
    if profile.background:
        lines.append(f"In the student's own words: {profile.background[:500]}")
    if topic:
        evidence = topic_evidence(db, user_id, topic.id)
        lines.append(f"Topic: {topic.title}. Coverage the student has recorded: {topic.status.replace('_', ' ')}.")
        if evidence.attempts:
            lines.append(f"Recent answers on this topic: {evidence.correct}/{evidence.attempts} correct.")
        reason = weakness(evidence)
        if reason:
            lines.append(f"This is a weak area: {reason}. Rebuild from the foundations.")
    memories = list(
        db.scalars(
            select(TutorMemory)
            .where(TutorMemory.user_id == user_id, (TutorMemory.topic_id == (topic.id if topic else None)) | TutorMemory.topic_id.is_(None))
            .order_by(TutorMemory.created_at.desc())
            .limit(12)
        )
    )
    if memories:
        lines.append("What you've learned about this student so far:")
        lines += [f"- ({m.kind}) {m.text}" for m in memories]
    return "\n".join(lines)


SYSTEM = """You are UniTask's tutor for one university student. Teach them the way they learn best.

How this student learns:
{brief}

Rules:
- Ground explanations in the SOURCES from the student's own materials when they are relevant, and cite them inline as [S1], [S2].
- Cite only source labels that appear in SOURCES. Never invent page numbers, books or references.
- If the sources don't cover the question, say "Your materials don't cover this" and give a short general explanation, clearly labelled as general.
- Keep replies under 220 words unless the student asks for more. No filler, no praise padding.
- Mode "{mode}". tutor: teach, then set one short check question that tests understanding rather than recall.
  ask: answer strictly from SOURCES; if they don't contain the answer, say so. explain_back: the student is explaining
  the concept to you; point out exactly what is missing or wrong, kindly, and what to fix.
- In "memory", record only what this exchange showed about the student (e.g. a misconception they revealed, or that
  they now explain something correctly). Empty list if nothing new.

Return JSON:
{{"reply": str, "used_sources": [str], "check": {{"question": str, "expected": str}} | null,
  "memory": [{{"kind": "misconception"|"understood"|"struggle"|"preference", "text": str}}]}}"""


def _sources(db: Session, user_id: int, query: str, course_id: int | None) -> tuple[str, dict[str, retrieval.Hit]]:
    hits = retrieval.search(db, user_id, query, course_id=course_id, limit=5)
    if not hits and course_id is not None:
        hits = retrieval.search(db, user_id, query, limit=5)
    labelled = {f"S{i}": hit for i, hit in enumerate(hits, start=1)}
    if not labelled:
        return "SOURCES: (none found in the student's materials)", labelled
    blocks = [f"[{label}] {hit.material_title}, page {hit.page_no}:\n{hit.text[:1800]}" for label, hit in labelled.items()]
    return "SOURCES:\n" + "\n\n".join(blocks), labelled


def respond(db: Session, conversation: Conversation, user_text: str) -> Message:
    topic = db.get(Topic, conversation.topic_id) if conversation.topic_id else None
    query = f"{user_text} {topic.title if topic else ''}".strip()
    sources_text, labelled = _sources(db, conversation.user_id, query, conversation.course_id)
    history = [llm.Turn("model" if m.role == "tutor" else "user", m.content) for m in conversation.messages[-10:]]
    history.append(llm.Turn("user", f"{sources_text}\n\nSTUDENT: {user_text}"))
    db.add(Message(conversation_id=conversation.id, role="user", content=user_text))
    db.flush()
    system = SYSTEM.format(brief=learner_brief(db, conversation.user_id, topic), mode=conversation.mode)

    try:
        data = llm.generate(system, history, json_mode=True)
        reply = str(data.get("reply", "")).strip() or "I couldn't produce an answer this time."
        used = [label for label in data.get("used_sources", []) if label in labelled]
        check = data.get("check") if conversation.mode == "tutor" and isinstance(data.get("check"), dict) else None
        for memo in data.get("memory", [])[:3]:
            if isinstance(memo, dict) and memo.get("kind") in {"misconception", "understood", "struggle", "preference"} and memo.get("text"):
                db.add(TutorMemory(user_id=conversation.user_id, topic_id=conversation.topic_id, kind=memo["kind"], text=str(memo["text"])[:400]))
        # Strip any citation label the model invented.
        for label in [f"S{i}" for i in range(1, 10)]:
            if label not in labelled:
                reply = reply.replace(f"[{label}]", "")
    except llm.LLMError as exc:
        logger.info("Tutor fallback: %s", exc)
        used = list(labelled)[:3]
        check = None
        if labelled:
            reply = "The AI tutor is unavailable right now. Here is what your own materials say:\n\n" + "\n\n".join(
                f"[{label}] {labelled[label].excerpt}" for label in used
            )
        else:
            reply = "The AI tutor is unavailable right now, and nothing in your materials matched this question."

    message = Message(
        conversation_id=conversation.id,
        role="tutor",
        content=reply,
        citations=[{"label": label, **labelled[label].cite()} for label in used],
        check={"question": str(check.get("question", ""))[:600], "expected": str(check.get("expected", ""))[:1200]} if check and check.get("question") else None,
    )
    db.add(message)
    if conversation.title == "New conversation":
        conversation.title = user_text[:80]
    conversation.updated_at = datetime.now(timezone.utc)
    if topic and topic.status == "not_started":
        topic.status = "in_progress"
    db.flush()
    return message


def grade_check(db: Session, conversation: Conversation, message: Message, answer: str, confidence: int | None) -> dict:
    """Grade the student's answer to a tutor check question and record it as evidence."""
    question, expected = message.check["question"], message.check["expected"]
    try:
        verdict = llm.generate(
            "Grade a university student's short answer against the expected answer. Be fair: accept correct answers in "
            'different words. Return JSON {"correct": bool, "feedback": str (max 80 words, say what was right and what was missing), '
            '"misconception": str | null (the specific wrong belief, if the answer revealed one)}.',
            f"QUESTION: {question}\nEXPECTED: {expected}\nSTUDENT ANSWER: {answer}",
            json_mode=True,
            fast=True,
        )
        correct = bool(verdict.get("correct"))
        feedback = str(verdict.get("feedback", ""))[:800]
        misconception = verdict.get("misconception")
    except llm.LLMError:
        correct, feedback, misconception = None, f"Couldn't grade automatically. Compare with the expected answer: {expected}", None

    db.add(Attempt(user_id=conversation.user_id, topic_id=conversation.topic_id, kind="check", correct=correct,
                   confidence=confidence, prompt=question, answer=answer, feedback=feedback))
    if misconception:
        db.add(TutorMemory(user_id=conversation.user_id, topic_id=conversation.topic_id, kind="misconception", text=str(misconception)[:400]))
    if correct is False:
        db.add(RevisionCard(user_id=conversation.user_id, topic_id=conversation.topic_id, course_id=conversation.course_id,
                            front=question, back=expected, origin="mistake"))
    db.add(Message(conversation_id=conversation.id, role="tutor",
                   content=("Correct. " if correct else "Not quite. " if correct is False else "") + feedback))
    db.flush()
    return {"correct": correct, "feedback": feedback, "card_created": correct is False}
