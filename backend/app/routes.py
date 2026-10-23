import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .assistant import answer_assignment_question
from .database import get_db
from .models import Assignment, Subject, TimetableUpload
from .schemas import (
    AssistantRequest,
    AssistantResponse,
    AssignmentCreate,
    AssignmentRead,
    AssignmentUpdate,
    SubjectCreate,
    SubjectRead,
    SubjectUpdate,
    TimetableUploadRead,
)
from .storage import (
    MAX_UPLOAD_BYTES,
    LocalStorage,
    StorageError,
    UploadTooLargeError,
    UploadValidationError,
    get_storage,
    validate_image,
)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/subjects", response_model=list[SubjectRead])
def list_subjects(db: Session = Depends(get_db)) -> list[Subject]:
    return list(db.scalars(select(Subject).order_by(Subject.name)).all())


@router.post("/subjects", response_model=SubjectRead, status_code=status.HTTP_201_CREATED)
def create_subject(payload: SubjectCreate, db: Session = Depends(get_db)) -> Subject:
    subject = Subject(name=payload.name.strip(), code=payload.code.strip().upper(), color=payload.color)
    db.add(subject)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A subject with this course code already exists.") from exc
    db.refresh(subject)
    return subject


@router.patch("/subjects/{subject_id}", response_model=SubjectRead)
def update_subject(subject_id: int, payload: SubjectUpdate, db: Session = Depends(get_db)) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(subject, field, value.strip().upper() if field == "code" else value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A subject with this course code already exists.") from exc
    db.refresh(subject)
    return subject


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: int, db: Session = Depends(get_db)) -> Response:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    db.delete(subject)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/assignments", response_model=list[AssignmentRead])
def list_assignments(
    subject_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[Assignment]:
    statement = select(Assignment).order_by(Assignment.due_date.asc(), Assignment.id.asc())
    if subject_id is not None:
        statement = statement.where(Assignment.subject_id == subject_id)
    if status_filter is not None:
        statement = statement.where(Assignment.status == status_filter)
    return list(db.scalars(statement).all())


@router.post("/assignments", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
def create_assignment(payload: AssignmentCreate, db: Session = Depends(get_db)) -> Assignment:
    if db.get(Subject, payload.subject_id) is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    values = payload.model_dump()
    values["title"] = payload.title.strip()
    assignment = Assignment(**values)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("/assignments/{assignment_id}", response_model=AssignmentRead)
def get_assignment(assignment_id: int, db: Session = Depends(get_db)) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    return assignment


@router.patch("/assignments/{assignment_id}", response_model=AssignmentRead)
def update_assignment(
    assignment_id: int,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    changes = payload.model_dump(exclude_unset=True)
    subject_id = changes.get("subject_id")
    if subject_id is not None and db.get(Subject, subject_id) is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    for field, value in changes.items():
        if value is not None:
            setattr(assignment, field, value.strip() if field in {"title", "platform"} else value)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.patch("/assignments/{assignment_id}/complete", response_model=AssignmentRead)
def complete_assignment(assignment_id: int, db: Session = Depends(get_db)) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    assignment.status = "Completed"
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(assignment_id: int, db: Session = Depends(get_db)) -> Response:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    db.delete(assignment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/assistant", response_model=AssistantResponse)
def assistant(
    payload: AssistantRequest,
    db: Session = Depends(get_db),
) -> AssistantResponse:
    return answer_assignment_question(payload.prompt, db)


def timetable_response(upload: TimetableUpload, storage) -> TimetableUploadRead:
    try:
        file_url = storage.retrieval_url(upload.object_key)
    except StorageError as exc:
        logger.exception("Could not create timetable retrieval URL.")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TimetableUploadRead(
        id=upload.id,
        original_filename=upload.original_filename,
        content_type=upload.content_type,
        size_bytes=upload.size_bytes,
        storage_provider=upload.storage_provider,
        uploaded_at=upload.uploaded_at,
        file_url=file_url,
    )


@router.post("/timetables", response_model=TimetableUploadRead, status_code=status.HTTP_201_CREATED)
async def upload_timetable(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> TimetableUploadRead:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        validated = validate_image(file.filename, file.content_type, content)
        storage = get_storage()
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UploadValidationError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except StorageError as exc:
        logger.exception("Timetable storage configuration is invalid.")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await file.close()

    upload_id = str(uuid.uuid4())
    extension = ".jpg" if validated.content_type == "image/jpeg" else f".{validated.content_type.split('/')[-1]}"
    object_key = f"timetables/{upload_id}{extension}"
    try:
        storage.put(object_key, validated.content, validated.content_type)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    record = TimetableUpload(
        id=upload_id,
        original_filename=validated.filename[:255],
        object_key=object_key,
        storage_provider=storage.provider,
        content_type=validated.content_type,
        size_bytes=len(validated.content),
    )
    db.add(record)
    try:
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            storage.delete(object_key)
        except StorageError:
            logger.exception("Stored timetable could not be cleaned up after database failure.")
        raise HTTPException(status_code=500, detail="Could not save timetable metadata.") from exc
    return timetable_response(record, storage)


@router.get("/timetables", response_model=list[TimetableUploadRead])
def list_timetables(db: Session = Depends(get_db)) -> list[TimetableUploadRead]:
    try:
        storage = get_storage()
    except StorageError as exc:
        logger.exception("Timetable storage configuration is invalid.")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    uploads = db.scalars(select(TimetableUpload).order_by(TimetableUpload.uploaded_at.desc())).all()
    return [timetable_response(upload, storage) for upload in uploads]


@router.get("/timetables/{upload_id}/file")
def retrieve_timetable(upload_id: str, db: Session = Depends(get_db)):
    upload = db.get(TimetableUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Timetable image not found.")
    try:
        storage = get_storage()
    except StorageError as exc:
        logger.exception("Timetable storage configuration is invalid.")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if upload.storage_provider == "s3":
        if not hasattr(storage, "retrieval_url") or storage.provider != "s3":
            raise HTTPException(status_code=503, detail="Configure the original S3 storage provider to retrieve this image.")
        try:
            return RedirectResponse(url=storage.retrieval_url(upload.object_key), status_code=307)
        except StorageError as exc:
            logger.exception("Could not create timetable retrieval URL.")
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not isinstance(storage, LocalStorage):
        raise HTTPException(status_code=503, detail="Configure local storage to retrieve this image.")
    path = storage.get_local_path(upload.object_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored timetable image is missing.")
    return FileResponse(
        path,
        media_type=upload.content_type,
        filename=upload.original_filename,
        content_disposition_type="inline",
    )
