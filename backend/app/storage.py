import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
PRESIGNED_URL_TTL_SECONDS = 300
IMAGE_SIGNATURES: dict[str, tuple[str, bytes]] = {
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}


class UploadValidationError(ValueError):
    pass


class UploadTooLargeError(UploadValidationError):
    pass


class StorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    content_type: str
    content: bytes


class StorageAdapter(Protocol):
    provider: str

    def put(self, key: str, content: bytes, content_type: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def get_local_path(self, key: str) -> Path | None: ...

    def retrieval_url(self, key: str) -> str: ...


def validate_image(filename: str | None, declared_content_type: str | None, content: bytes) -> ValidatedUpload:
    if not content:
        raise UploadValidationError("The selected image is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadTooLargeError("Image exceeds the 5 MB upload limit.")

    safe_name = Path(filename or "").name
    extension = Path(safe_name).suffix.lower()
    image_spec = IMAGE_SIGNATURES.get(extension)
    if extension == ".webp":
        if len(content) < 12 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
            raise UploadValidationError("The file contents do not match a supported image format.")
        actual_content_type = "image/webp"
    elif image_spec:
        actual_content_type, signature = image_spec
        if not content.startswith(signature):
            raise UploadValidationError("The file contents do not match a supported image format.")
    else:
        raise UploadValidationError("Use a JPEG, PNG, or WebP image.")

    declared = (declared_content_type or "").lower().split(";", maxsplit=1)[0].strip()
    if declared and declared not in {actual_content_type, "application/octet-stream"}:
        raise UploadValidationError("The image content type does not match its file contents.")
    return ValidatedUpload(
        filename=safe_name or f"timetable{extension}",
        content_type=actual_content_type,
        content=content,
    )


class LocalStorage:
    provider = "local"

    def __init__(self, root: Path | None = None) -> None:
        configured_root = os.getenv("LOCAL_UPLOAD_DIR")
        default_root = Path(__file__).resolve().parents[1] / "uploads"
        if root is not None:
            self.root = root.resolve()
        elif configured_root:
            self.root = Path(configured_root).resolve()
        else:
            self.root = default_root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise StorageError("Invalid local storage key.") from exc
        if path == self.root:
            raise StorageError("Invalid local storage key.")
        return path

    def put(self, key: str, content: bytes, content_type: str) -> None:
        del content_type
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def get_local_path(self, key: str) -> Path:
        return self._path(key)

    def retrieval_url(self, key: str) -> str:
        return f"/api/timetables/{Path(key).stem}/file"


class S3Storage:
    provider = "s3"

    def __init__(self, bucket: str, region: str, profile: str | None = None) -> None:
        if not bucket:
            raise StorageError("S3 storage requires S3_BUCKET to be configured.")
        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError as exc:
            raise StorageError("Install backend/requirements-aws.txt to enable S3 storage.") from exc
        self.bucket = bucket
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        self.client = session.client(
            "s3",
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual", "us_east_1_regional_endpoint": "regional"},
            ),
        )
        self._boto_errors = (BotoCoreError, ClientError)

    def put(self, key: str, content: bytes, content_type: str) -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type)
        except self._boto_errors as exc:
            logger.exception("S3 timetable upload failed.")
            raise StorageError("Could not store the timetable in S3.") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except self._boto_errors as exc:
            logger.exception("Could not clean up uploaded S3 object.")
            raise StorageError("Could not remove the uploaded S3 object.") from exc

    def get_local_path(self, key: str) -> None:
        del key
        return None

    def retrieval_url(self, key: str) -> str:
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=PRESIGNED_URL_TTL_SECONDS,
            )
        except self._boto_errors as exc:
            logger.exception("Could not create a temporary S3 retrieval URL.")
            raise StorageError("Could not create a temporary retrieval link.") from exc


def get_storage() -> StorageAdapter:
    provider = os.getenv("STORAGE_PROVIDER", "local").strip().lower()
    if provider == "local":
        return LocalStorage()
    if provider == "s3":
        return S3Storage(
            bucket=os.getenv("S3_BUCKET", ""),
            region=os.getenv("AWS_REGION", "ap-south-1"),
            profile=os.getenv("AWS_PROFILE") or None,
        )
    raise StorageError("STORAGE_PROVIDER must be either 'local' or 's3'.")
