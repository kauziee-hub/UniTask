import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import get_db
from .models import TimetableUpload, User
from .schemas import TimetableUploadRead
from .security import get_current_user
from .services import download_link
from .storage import (
    MAX_UPLOAD_BYTES,
    LocalStorage,
    StorageError,
    UploadTooLargeError,
    UploadValidationError,
    get_storage,
    validate_image,
)

# Timetable-image upload from the first S3 demo. Kept working, now behind sign-in and scoped to the uploader.
router = APIRouter(prefix="/api", tags=["timetables"])
logger = logging.getLogger(__name__)


def timetable_response(upload: TimetableUpload, storage) -> TimetableUploadRead:
    del storage  # links are signed per request so an <img> tag can load them without a bearer token
    file_url = download_link(upload.object_key, upload.original_filename, upload.content_type, inline=True)["url"]
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
    user: User = Depends(get_current_user),
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
        owner_id=user.id,
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
def list_timetables(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[TimetableUploadRead]:
    try:
        storage = get_storage()
    except StorageError as exc:
        logger.exception("Timetable storage configuration is invalid.")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    uploads = db.scalars(
        select(TimetableUpload).where(TimetableUpload.owner_id == user.id).order_by(TimetableUpload.uploaded_at.desc())
    ).all()
    return [timetable_response(upload, storage) for upload in uploads]


@router.get("/timetables/{upload_id}/file")
def retrieve_timetable(upload_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    upload = db.get(TimetableUpload, upload_id)
    if upload is None or upload.owner_id != user.id:
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
