"""The student's academic library: upload notes, slides and past papers; search them; ask about them."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import jobs, tutor
from ..academic import audit, sha256
from ..academic_models import Conversation, Material, MaterialPage, MaterialTopic, Question, Topic
from ..academic_schemas import AskRequest, MaterialUpdate
from ..database import get_db
from ..models import User
from ..retrieval import search
from ..security import require_student
from ..services import download_link, put_upload, read_upload
from ..storage import StorageError, get_storage
from ..workspace import material_out, owned, require_course

router = APIRouter(prefix="/api", tags=["library"])
MATERIAL_MAX_BYTES = 30 * 1024 * 1024
KINDS = {"notes", "slides", "syllabus", "pyq", "lab_manual", "textbook", "other"}
READABLE = (".pdf", ".docx", ".pptx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp")


@router.post("/materials", status_code=201)
async def upload_material(
    file: UploadFile = File(...),
    course_id: int | None = Form(default=None),
    kind: str = Form(default="notes"),
    title: str | None = Form(default=None, max_length=255),
    year: int | None = Form(default=None, ge=1990, le=2100),
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> dict:
    if kind not in KINDS:
        raise HTTPException(422, f"Kind must be one of: {', '.join(sorted(KINDS))}.")
    if not (file.filename or "").lower().endswith(READABLE):
        raise HTTPException(415, "Upload a PDF, Word (.docx), PowerPoint (.pptx), text file or a photo.")
    course = require_course(db, course_id, user)
    validated = await read_upload(file, MATERIAL_MAX_BYTES)
    digest = sha256(validated.content)
    existing = db.scalar(select(Material).where(Material.user_id == user.id, Material.sha256 == digest))
    if existing:
        raise HTTPException(409, f"You already uploaded this file as “{existing.title}”.")
    key = put_upload(validated, f"materials/{user.id}")
    material = Material(
        user_id=user.id,
        course_id=course.id if course else None,
        kind=kind,
        title=(title or "").strip() or validated.filename.rsplit(".", 1)[0][:255],
        filename=validated.filename,
        storage_key=key,
        content_type=validated.content_type,
        size_bytes=len(validated.content),
        sha256=digest,
        year=year,
        status="queued",
    )
    db.add(material)
    audit(db, user.id, "material.upload", f"material:{material.title}", kind=kind)
    db.commit()
    db.refresh(material)
    jobs.enqueue("process_material", {"material_id": material.id})
    db.refresh(material)
    return material_out(material)


@router.get("/materials")
def list_materials(
    course_id: int | None = None,
    kind: str | None = None,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Material).where(Material.user_id == user.id).order_by(Material.created_at.desc())
    if course_id is not None:
        query = query.where(Material.course_id == course_id)
    if kind:
        query = query.where(Material.kind == kind)
    return [material_out(m) for m in db.scalars(query)]


@router.get("/materials/{material_id}")
def material_detail(material_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    material = owned(db, Material, material_id, user, "Material")
    topics = [
        {"topic_id": topic.id, "title": topic.title, "pages": sorted(pages)}
        for topic, pages in _topic_pages(db, material).items()
    ]
    return {
        **material_out(material),
        "topics": topics,
        "questions": db.scalar(select(func.count()).select_from(Question).where(Question.material_id == material.id)) or 0,
        "empty_pages": [p.page_no for p in material.pages if len(p.text.strip()) < 25],
    }


def _topic_pages(db: Session, material: Material) -> dict[Topic, set[int]]:
    out: dict[Topic, set[int]] = {}
    for link, topic in db.execute(
        select(MaterialTopic, Topic).join(Topic, Topic.id == MaterialTopic.topic_id).where(MaterialTopic.material_id == material.id)
    ):
        out.setdefault(topic, set()).add(link.page_no)
    return out


@router.patch("/materials/{material_id}")
def update_material(material_id: int, payload: MaterialUpdate, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    material = owned(db, Material, material_id, user, "Material")
    changes = payload.model_dump(exclude_unset=True)
    if "course_id" in changes:
        require_course(db, changes["course_id"], user)
    reprocess = any(changes.get(f) != getattr(material, f) for f in ("kind", "course_id", "year") if f in changes)
    for field, value in changes.items():
        if field == "title" and value:
            value = value.strip()
        setattr(material, field, value)
    db.commit()
    if reprocess:
        material.status = "queued"
        db.commit()
        jobs.enqueue("process_material", {"material_id": material.id})
        db.refresh(material)
    return material_out(material)


@router.post("/materials/{material_id}/reprocess")
def reprocess_material(material_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    material = owned(db, Material, material_id, user, "Material")
    material.status = "queued"
    db.commit()
    jobs.enqueue("process_material", {"material_id": material.id})
    db.refresh(material)
    return material_out(material)


@router.delete("/materials/{material_id}", status_code=204)
def delete_material(material_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> Response:
    material = owned(db, Material, material_id, user, "Material")
    key = material.storage_key
    audit(db, user.id, "material.delete", f"material:{material.id}", title=material.title)
    db.delete(material)
    db.commit()
    try:
        get_storage().delete(key)
    except StorageError:
        pass  # The record is gone; an orphaned object is harmless and can be swept later.
    return Response(status_code=204)


@router.get("/materials/{material_id}/file")
def material_file(material_id: int, inline: bool = False, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    material = owned(db, Material, material_id, user, "Material")
    return download_link(material.storage_key, material.filename, material.content_type, inline=inline)


@router.get("/materials/{material_id}/pages/{page_no}")
def material_page(material_id: int, page_no: int, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    material = owned(db, Material, material_id, user, "Material")
    page = db.scalar(select(MaterialPage).where(MaterialPage.material_id == material.id, MaterialPage.page_no == page_no))
    if page is None:
        raise HTTPException(404, "Page not found.")
    return {"material_id": material.id, "title": material.title, "page": page.page_no, "page_count": material.page_count, "text": page.text}


@router.get("/search")
def search_library(
    q: str = Query(min_length=2, max_length=300),
    course_id: int | None = None,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> dict:
    hits = search(db, user.id, q, course_id=course_id, limit=20)
    return {"query": q, "hits": [{**h.cite(), "course_id": h.course_id, "score": h.score} for h in hits]}


@router.post("/ask")
def ask(payload: AskRequest, user: User = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """Answer strictly from the student's own materials, with page citations."""
    require_course(db, payload.course_id, user)
    if payload.topic_id is not None:
        owned(db, Topic, payload.topic_id, user, "Topic")
    conversation = Conversation(user_id=user.id, course_id=payload.course_id, topic_id=payload.topic_id, mode="ask", title=payload.question[:80])
    db.add(conversation)
    db.flush()
    message = tutor.respond(db, conversation, payload.question)
    db.commit()
    return {
        "conversation_id": conversation.id,
        "answer": message.content,
        "citations": message.citations or [],
        "message_id": message.id,
    }
