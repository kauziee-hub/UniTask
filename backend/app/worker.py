"""SQS consumer: `python -m app.worker`. Long-polls SQS_QUEUE_URL and runs job handlers.

A message is deleted only after its handler succeeds; failures become visible again after the
visibility timeout and, after the queue's maxReceiveCount, move to its dead-letter queue.
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from . import jobs  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("unitask.worker")


def main() -> None:
    import boto3

    jobs.register_all()
    profile = os.getenv("AWS_PROFILE") or None
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    sqs = session.client("sqs", region_name=os.getenv("AWS_REGION", "ap-south-1"))
    queue = os.environ["SQS_QUEUE_URL"]
    logger.info("Worker listening on %s", queue)
    while True:
        response = sqs.receive_message(QueueUrl=queue, MaxNumberOfMessages=5, WaitTimeSeconds=20)
        for message in response.get("Messages", []):
            try:
                body = json.loads(message["Body"])
                jobs.run(body["kind"], body.get("payload", {}))
            except Exception:  # noqa: BLE001
                logger.exception("Job failed; leaving it on the queue for retry")
                continue
            sqs.delete_message(QueueUrl=queue, ReceiptHandle=message["ReceiptHandle"])


if __name__ == "__main__":
    main()
