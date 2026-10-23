import os
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

from app.storage import (
    MAX_UPLOAD_BYTES,
    LocalStorage,
    S3Storage,
    StorageError,
    UploadTooLargeError,
    UploadValidationError,
    validate_image,
)


def one_pixel_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">II5B", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


class StorageTests(unittest.TestCase):
    def test_validates_actual_png_and_declared_type(self) -> None:
        upload = validate_image("timetable.png", "image/png", one_pixel_png())
        self.assertEqual(upload.content_type, "image/png")

    def test_rejects_wrong_signature_and_mime(self) -> None:
        with self.assertRaises(UploadValidationError):
            validate_image("timetable.png", "image/png", b"not an image")
        with self.assertRaises(UploadValidationError):
            validate_image("timetable.png", "image/jpeg", one_pixel_png())

    def test_rejects_oversized_upload(self) -> None:
        with self.assertRaises(UploadTooLargeError):
            validate_image("timetable.png", "image/png", b"x" * (MAX_UPLOAD_BYTES + 1))

    def test_local_storage_round_trip_and_path_traversal_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalStorage(Path(directory))
            storage.put("timetables/example.png", one_pixel_png(), "image/png")
            self.assertEqual(storage.get_local_path("timetables/example.png").read_bytes(), one_pixel_png())
            self.assertEqual(
                storage.retrieval_url("timetables/example.png"),
                "/api/timetables/example/file",
            )
            with self.assertRaises(StorageError):
                storage.get_local_path("../outside.png")

    def test_s3_put_uses_private_default_without_public_acl_or_network(self) -> None:
        try:
            from botocore.stub import Stubber
        except ImportError as exc:
            self.skipTest(f"Boto3 test dependency is not installed: {exc}")

        with patch.dict(
            os.environ,
            {"AWS_ACCESS_KEY_ID": "test-only", "AWS_SECRET_ACCESS_KEY": "test-only"},
        ):
            storage = S3Storage("private-test-bucket", "ap-south-1")
            stubber = Stubber(storage.client)
            stubber.add_response(
                "put_object",
                {},
                {
                    "Bucket": "private-test-bucket",
                    "Key": "timetables/test.png",
                    "Body": one_pixel_png(),
                    "ContentType": "image/png",
                },
            )
            with stubber:
                storage.put("timetables/test.png", one_pixel_png(), "image/png")
            retrieval_url = storage.retrieval_url("timetables/test.png")
            self.assertIn("X-Amz-Signature", retrieval_url)
            self.assertEqual(
                urlparse(retrieval_url).hostname,
                "private-test-bucket.s3.ap-south-1.amazonaws.com",
            )


if __name__ == "__main__":
    unittest.main()
