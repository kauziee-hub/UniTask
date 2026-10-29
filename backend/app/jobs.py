"""Background jobs behind one interface.

JOB_QUEUE=local (default): a small in-process thread pool. Good for development and a single server.
JOB_QUEUE=sqs: messages go to Amazon SQS (SQS_QUEUE_URL); `python -m app.worker` consumes them.
JOB_QUEUE=inline: run immediately in the caller (tests).
Handlers open their own database session and must be idempotent, because SQS delivers at least once.
"""

import json
import logging
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
_HANDLERS: dict[str, Callable[[dict], None]] = {}
_pool: ThreadPoolExecutor | None = None


def handler(kind: str):
    def register(fn: Callable[[dict], None]):
        _HANDLERS[kind] = fn
        return fn

    return register


def run(kind: str, payload: dict) -> None:
    fn = _HANDLERS.get(kind)
    if fn is None:
        logger.error("No handler for job kind %s", kind)
        return
    try:
        fn(payload)
    except Exception:  # noqa: BLE001 — a failed job must never take the server down
        logger.exception("Job %s failed: %s", kind, payload)
        raise


def enqueue(kind: str, payload: dict) -> str:
    mode = os.getenv("JOB_QUEUE", "local").lower()
    if mode == "inline":
        run(kind, payload)
        return "inline"
    if mode == "sqs":
        import boto3

        profile = os.getenv("AWS_PROFILE") or None
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        client = session.client("sqs", region_name=os.getenv("AWS_REGION", "ap-south-1"))
        response = client.send_message(QueueUrl=os.environ["SQS_QUEUE_URL"], MessageBody=json.dumps({"kind": kind, "payload": payload}))
        return response["MessageId"]
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="unitask-job")
    _pool.submit(lambda: _safe(kind, payload))
    return "local"


def _safe(kind: str, payload: dict) -> None:
    try:
        run(kind, payload)
    except Exception:  # noqa: BLE001
        pass


def register_all() -> None:
    """Import modules that define handlers."""
    from . import job_handlers  # noqa: F401
