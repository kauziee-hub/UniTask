import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="unitask-test-")
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["LOCAL_UPLOAD_DIR"] = str(Path(_tmp, "uploads"))
os.environ["UNITASK_SECRET_KEY"] = "test-secret-key-for-unit-tests-only"
os.environ["AUTH_PROVIDER"] = "local"
os.environ["MS_CLIENT_ID"] = ""
os.environ["MS_CLIENT_SECRET"] = ""
# Never call a real model from tests; individual tests monkeypatch llm.generate when they need one.
os.environ["LLM_PROVIDER"] = "none"
os.environ["GEMINI_API_KEY"] = ""
os.environ["OCR_PROVIDER"] = "none"
os.environ["JOB_QUEUE"] = "inline"
os.environ["SCHEDULER"] = "external"
os.environ["EMAIL_PROVIDER"] = "log"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.database import Base, engine  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(main.app) as test_client:
        yield test_client


def register(client: TestClient, name: str, role: str) -> dict[str, str]:
    email = f"{name.lower().replace(' ', '.')}@example.edu"
    response = client.post(
        "/api/auth/register", json={"name": name, "email": email, "password": "correct-horse", "role": role}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}
