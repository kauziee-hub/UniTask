from app.database import SessionLocal
from app.demo_seed import seed


def test_demo_entry_disabled_by_default_and_for_cognito(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    assert client.get("/api/auth/config").json()["demo_enabled"] is False
    assert client.post("/api/auth/demo").status_code == 404
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AUTH_PROVIDER", "cognito")
    assert client.post("/api/auth/demo").status_code == 404


def test_demo_sessions_use_seeded_accounts_and_enforce_roles(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    with SessionLocal() as db:
        assert seed(db)
        assert not seed(db)
    for role in ("student", "teacher"):
        session = client.post(f"/api/auth/demo?role={role}")
        assert session.status_code == 200, session.text
        headers = {"Authorization": f"Bearer {session.json()['token']}"}
        assert client.get("/api/auth/me", headers=headers).json()["role"] == role
        if role == "student":
            assert client.get("/api/subjects", headers=headers).json()
            assert client.post("/api/courses", headers=headers, json={"name": "Forbidden"}).status_code == 403
    assert client.post("/api/auth/demo?role=admin").status_code == 422


def test_missing_demo_data_has_actionable_error(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    assert client.post("/api/auth/demo").status_code == 503
