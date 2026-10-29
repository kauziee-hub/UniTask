"""Syllabus structure, previous-year questions, topic linking, inbox events and material processing."""

import hashlib
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import llm
from .extraction import extract
from .models import (
    AuditEvent,
    InboxEvent,
    Material,
    MaterialPage,
    MaterialTopic,
    Question,
    Topic,
)
from .retrieval import tokens
from .storage import StorageError, get_storage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- inbox + audit


def notify(db: Session, user_id: int, kind: str, title: str, dedupe_key: str, *, body=None, link=None, source="unitask") -> bool:
    """Add an inbox event once. Re-sending the same dedupe_key is a no-op, so jobs can retry safely."""
    exists = db.scalar(select(InboxEvent.id).where(InboxEvent.user_id == user_id, InboxEvent.dedupe_key == dedupe_key))
    if exists:
        return False
    with db.begin_nested():
        db.add(InboxEvent(user_id=user_id, kind=kind, title=title[:255], body=body, link=link, source=source, dedupe_key=dedupe_key[:160]))
        try:
            db.flush()
        except IntegrityError:
            return False
    return True


def audit(db: Session, user_id: int | None, action: str, target: str | None = None, **detail) -> None:
    db.add(AuditEvent(user_id=user_id, action=action, target=target, detail=detail or None))


# ---------------------------------------------------------------- syllabus

MODULE_RE = re.compile(r"^\s*(?:module|unit|chapter)\s*[-:]?\s*([0-9ivx]+)\b\s*[:.\-–]*\s*(.*)$", re.I)


def parse_syllabus(text: str) -> list[dict]:
    """Rule-based parse of the common 'Module 1: Title / topic, topic, topic' layout."""
    modules: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip(" \t•-–*")
        if not line:
            continue
        match = MODULE_RE.match(line)
        if match:
            title = match.group(2).strip(" :-–") or f"Module {match.group(1)}"
            title = re.sub(r"\s*\d+\s*(?:hours?|hrs?|h)\s*$", "", title, flags=re.I)
            current = {"title": title[:300], "topics": []}
            modules.append(current)
            continue
        if current is None or re.match(r"^(total|text ?books?|references?|reference books|course outcomes?)\b", line, re.I):
            if current is not None and re.match(r"^(total|text ?books?|references?)", line, re.I):
                current = None
            continue
        for part in re.split(r"[;,]|\s–\s|\.\s", line):
            part = part.strip(" .:-–")
            if 3 <= len(part) <= 160 and not re.fullmatch(r"[\d\s.]+(hours?|hrs?)?", part, re.I):
                current["topics"].append(part)
    return [m for m in modules if m["topics"] or m["title"]]


def structure_syllabus(text: str) -> tuple[list[dict], str]:
    parsed = parse_syllabus(text)
    if parsed and sum(len(m["topics"]) for m in parsed) >= 3:
        return parsed, "rules"
    if not llm.available():
        return parsed, "rules"
    try:
        data = llm.generate(
            "You read university syllabi. Extract the module/unit structure exactly as written. "
            'Return JSON: {"modules":[{"title":str,"topics":[str]}]}. Use only topics present in the text; '
            "never add topics. Keep each topic short (under 12 words).",
            text[:12000],
            json_mode=True,
            fast=True,
        )
        modules = [
            {"title": str(m.get("title", ""))[:300], "topics": [str(t)[:300] for t in m.get("topics", []) if str(t).strip()]}
            for m in data.get("modules", [])
            if isinstance(m, dict)
        ]
        return modules, "ai"
    except (llm.LLMError, AttributeError):
        return parsed, "rules"


def save_syllabus(db: Session, user_id: int, course_id: int, modules: list[dict], *, confirmed: bool, origin: str) -> int:
    """Append modules/topics. Extracted structure stays unconfirmed until the student reviews it."""
    start = db.scalar(select(Topic.position).where(Topic.course_id == course_id, Topic.user_id == user_id, Topic.parent_id.is_(None)).order_by(Topic.position.desc())) or 0
    created = 0
    for m_index, module in enumerate(modules, start=1):
        parent = Topic(user_id=user_id, course_id=course_id, title=module["title"], position=start + m_index, confirmed=confirmed, origin=origin)
        db.add(parent)
        db.flush()
        created += 1
        for t_index, title in enumerate(module.get("topics", []), start=1):
            db.add(Topic(user_id=user_id, course_id=course_id, parent_id=parent.id, title=title, position=t_index, confirmed=confirmed, origin=origin))
            created += 1
    return created


def topic_match_score(topic_title: str, text: str) -> float:
    terms = [t for t in tokens(topic_title) if len(t) > 2]
    if not terms:
        return 0.0
    lowered = text.lower()
    if topic_title.lower() in lowered:
        return 1.0
    present = sum(1 for t in terms if t in lowered)
    return present / len(terms) if present >= min(2, len(terms)) else 0.0


def link_material_topics(db: Session, material: Material) -> int:
    """Record which pages of a material discuss which syllabus topics (keyword evidence, not guesses)."""
    if material.course_id is None:
        return 0
    topics = db.scalars(
        select(Topic).where(Topic.user_id == material.user_id, Topic.course_id == material.course_id, Topic.parent_id.is_not(None))
    ).all()
    db.execute(delete(MaterialTopic).where(MaterialTopic.material_id == material.id))
    links = 0
    for page in material.pages:
        for topic in topics:
            score = topic_match_score(topic.title, page.text)
            if score >= 0.67:
                db.add(MaterialTopic(material_id=material.id, topic_id=topic.id, page_no=page.page_no, score=score))
                links += 1
    return links


# ---------------------------------------------------------------- previous-year questions

Q_START = re.compile(r"^\s*(?:Q\.?\s*|Question\s+)?(\d{1,2})\s*[.)\]:]\s*(.*)", re.I)
MARKS = re.compile(r"[\[(]\s*(\d{1,2})\s*(?:m|marks?)?\s*[\])]\s*$", re.I)


BOILERPLATE = set(
    "explain describe discuss compare contrast illustrate define state write short brief briefly detail detailed suitable "
    "example examples neat diagram diagrams using give what how why mark marks following answer question questions any two "
    "three four five also help used use its their them they these those can will would should must".split()
)


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def salient_terms(text: str) -> frozenset[str]:
    """What a question is about, ignoring exam boilerplate ("explain with a neat diagram") and plurals."""
    return frozenset(_stem(t) for t in tokens(text) if len(t) >= 3 and not t.isdigit() and t not in BOILERPLATE)


def pattern_key(text: str) -> str:
    """Questions with the same salient terms share a key; near-repeats are grouped by `cluster_questions`."""
    salient = sorted(salient_terms(text))[:10]
    return hashlib.sha1(" ".join(salient).encode()).hexdigest()[:16]


def cluster_questions(texts: list[str], threshold: float = 0.6) -> list[int]:
    """Greedy grouping by word overlap (Jaccard). Returns a cluster index per question."""
    clusters: list[set[str]] = []
    out = []
    for text in texts:
        terms = set(salient_terms(text))
        best, best_score = None, 0.0
        for index, rep in enumerate(clusters):
            union = len(terms | rep)
            score = len(terms & rep) / union if union else 0.0
            if score > best_score:
                best, best_score = index, score
        if best is not None and best_score >= threshold:
            out.append(best)
        else:
            clusters.append(terms)
            out.append(len(clusters) - 1)
    return out


def parse_questions(pages: list[str]) -> list[dict]:
    questions: list[dict] = []
    current: dict | None = None
    for page_no, text in enumerate(pages, start=1):
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            match = Q_START.match(line)
            if match and len(match.group(2)) > 8:
                if current:
                    questions.append(current)
                current = {"label": f"Q{match.group(1)}", "text": match.group(2), "page_no": page_no}
            elif current and not re.match(r"^(part|section)\s+[a-c]\b", line, re.I):
                current["text"] += " " + line
    if current:
        questions.append(current)
    for q in questions:
        marks = MARKS.search(q["text"])
        q["marks"] = int(marks.group(1)) if marks else None
        q["text"] = MARKS.sub("", q["text"]).strip()[:4000]
    return [q for q in questions if len(q["text"]) > 12]


def map_question_topic(question_text: str, topics: list[Topic]) -> Topic | None:
    best, best_score = None, 0.0
    for topic in topics:
        score = topic_match_score(topic.title, question_text)
        if score > best_score:
            best, best_score = topic, score
    return best if best_score >= 0.5 else None


def save_questions(db: Session, material: Material, pages: list[str]) -> int:
    db.execute(delete(Question).where(Question.material_id == material.id))
    topics = []
    if material.course_id:
        topics = list(db.scalars(select(Topic).where(Topic.user_id == material.user_id, Topic.course_id == material.course_id, Topic.parent_id.is_not(None))))
    count = 0
    for q in parse_questions(pages):
        topic = map_question_topic(q["text"], topics)
        db.add(
            Question(
                user_id=material.user_id,
                material_id=material.id,
                course_id=material.course_id,
                topic_id=topic.id if topic else None,
                year=material.year,
                label=q["label"],
                text=q["text"],
                marks=q["marks"],
                page_no=q["page_no"],
                pattern_key=pattern_key(q["text"]),
            )
        )
        count += 1
    return count


# ---------------------------------------------------------------- processing pipeline


def process_material(db: Session, material_id: int) -> Material | None:
    """Extract pages, link topics, parse questions/syllabus. Safe to re-run (idempotent)."""
    material = db.get(Material, material_id)
    if material is None:
        return None
    material.status = "processing"
    db.commit()
    try:
        content = get_storage().read(material.storage_key)
    except StorageError as exc:
        material.status, material.error = "failed", f"Could not read the stored file: {exc}"[:500]
        db.commit()
        return material

    result = extract(content, material.content_type, material.filename)
    db.execute(delete(MaterialPage).where(MaterialPage.material_id == material.id))
    db.flush()
    for number, text in enumerate(result.pages, start=1):
        db.add(MaterialPage(material_id=material.id, page_no=number, text=text))
    material.page_count = len(result.pages) or None
    material.extractor = result.extractor
    material.error = result.error
    if result.error and not result.pages:
        material.status = "failed"
    elif result.needs_ocr:
        material.status = "needs_ocr"
    else:
        material.status = "ready"
    db.flush()
    db.refresh(material)

    extra = ""
    if material.status == "ready":
        if material.kind == "pyq":
            extra = f" · {save_questions(db, material, result.pages)} questions found"
        link_material_topics(db, material)
    notify(
        db,
        material.user_id,
        "material_ready" if material.status == "ready" else "sync_error",
        f"{material.title}: " + ("ready to search" if material.status == "ready" else "needs attention"),
        f"material:{material.id}:{material.status}:{material.page_count}",
        body=(f"{material.page_count or 0} pages read with {material.extractor}{extra}." if material.status == "ready" else material.error or "Some pages had no readable text. Scanned pages need OCR."),
        link=f"/library?material={material.id}",
    )
    db.commit()
    return material


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
