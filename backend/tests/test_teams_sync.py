from datetime import datetime, timedelta, timezone

from conftest import register
from sqlalchemy import select

from app import teams
from app.database import SessionLocal
from app.models import Connection, User


class FakeGraph:
    """Stands in for Microsoft Graph; returns canned /education responses."""

    def __init__(self, classes, assignments, details=None):
        self.classes = classes
        self.assignments = assignments
        self.details = details or {}
        self.calls: list[str] = []

    def get_all(self, path, limit=2000):
        self.calls.append(path)
        if path.startswith("/education/me/classes"):
            return self.classes
        if path.startswith("/education/me/assignments"):
            return self.assignments
        raise AssertionError(path)

    def get(self, path):
        self.calls.append(path)
        for key, value in self.details.items():
            if key in path:
                return value
        return {}

    def close(self):
        pass


def graph_assignment(id_, title, due, class_id="class-1", submitted=False, status="assigned"):
    return {
        "id": id_,
        "classId": class_id,
        "displayName": title,
        "dueDateTime": due,
        "status": status,
        "allowLateSubmissions": True,
        "lastModifiedDateTime": "2026-10-28T10:00:00Z",
        "grading": {"maxPoints": 10},
        "submissions": [{"status": "submitted" if submitted else "working"}],
    }


def test_sync_imports_detects_changes_and_removals(client):
    headers = register(client, "Asha Rao", "student")
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)
    sooner = soon - timedelta(days=1)
    classes = [{"id": "class-1", "displayName": "BCSE302L Database Systems", "classCode": "DB302"}]

    first = FakeGraph(
        classes,
        [
            graph_assignment("a1", "ER diagram", soon.isoformat().replace("+00:00", "Z")),
            graph_assignment("a2", "SQL lab", "9999-12-31T23:59:59Z", submitted=True),
            graph_assignment("draft", "Not yet published", None, status="draft"),
        ],
        details={"/assignments/a1": {"instructions": {"content": "<p>Draw the <b>ER</b> model.</p><ul><li>Entities</li></ul>"},
                                      "webUrl": "https://teams.microsoft.com/l/entity/x"}},
    )
    with SessionLocal() as db:
        user = db.scalar(select(User))
        result = teams.sync_user(db, user, first)
        db.commit()
    assert result.classes == 1 and result.assignments == 2 and result.new == 2 and result.turned_in == 1

    work = {w["title"]: w for w in client.get("/api/work", headers=headers).json()}
    assert set(work) == {"ER diagram", "SQL lab"}
    er = work["ER diagram"]
    assert er["source"] == "teams" and er["course"]["name"] == "BCSE302L Database Systems"
    assert er["instructions"].startswith("Draw the ER model.") and "• Entities" in er["instructions"]
    assert er["external_url"] == "https://teams.microsoft.com/l/entity/x"
    assert er["points"] == 10
    assert work["SQL lab"]["due_at"] is None and work["SQL lab"]["status"] == "turned_in"
    # First sync is imported quietly — no "new" notifications flood.
    assert client.get("/api/today", headers=headers).json()["changes"] == []

    # Students can't fake-complete Teams work.
    assert client.patch(f"/api/work/{er['id']}", headers=headers, json={"status": "done"}).status_code == 409

    second = FakeGraph(
        classes,
        [
            graph_assignment("a1", "ER diagram", sooner.isoformat().replace("+00:00", "Z")),
            graph_assignment("a3", "Normalization quiz", soon.isoformat().replace("+00:00", "Z")),
        ],
    )
    with SessionLocal() as db:
        user = db.scalar(select(User))
        result = teams.sync_user(db, user, second)
        db.commit()
    assert (result.new, result.due_changed, result.removed) == (1, 1, 1)

    changes = client.get("/api/today", headers=headers).json()["changes"]
    kinds = sorted(c["kind"] for c in changes)
    assert kinds == ["created", "due_changed", "removed"]
    moved = next(c for c in changes if c["kind"] == "due_changed")
    assert moved["title"] == "ER diagram"
    er_now = client.get(f"/api/work/{er['id']}", headers=headers).json()
    assert er_now["priority"]["reason"].startswith("Deadline moved earlier")

    client.post("/api/changes/seen", headers=headers)
    assert client.get("/api/today", headers=headers).json()["changes"] == []

    # Unchanged assignments don't trigger another details call.
    third = FakeGraph(classes, second.assignments)
    with SessionLocal() as db:
        user = db.scalar(select(User))
        teams.sync_user(db, user, third)
        db.commit()
    assert not any("/education/classes/" in call for call in third.calls)


def test_sync_connection_records_consent_failure(client, monkeypatch):
    register(client, "Asha Rao", "student")
    with SessionLocal() as db:
        user = db.scalar(select(User))
        connection = Connection(user_id=user.id, provider="teams", status="connected", token_cache="x")
        db.add(connection)
        db.commit()

        def refuse(db, connection):
            raise teams.TeamsError(teams.consent_message(), "needs_consent")

        monkeypatch.setattr(teams, "access_token", refuse)
        try:
            teams.sync_connection(db, connection)
        except teams.TeamsError:
            pass
        db.refresh(connection)
        assert connection.status == "needs_consent"
        assert "administrator" in connection.last_error


def test_consent_error_detection():
    assert teams.is_consent_error("AADSTS90094: The grant requires admin permission.")
    assert teams.is_consent_error("AADSTS65001: The user or administrator has not consented")
    assert not teams.is_consent_error("AADSTS50126: Invalid username or password")


def test_teams_status_when_not_configured(client):
    headers = register(client, "Asha Rao", "student")
    status = client.get("/api/integrations/teams", headers=headers).json()
    assert status["configured"] is False and status["status"] == "not_connected"
    assert client.post("/api/integrations/teams/connect", headers=headers).status_code == 503


def test_callback_handles_unknown_state_and_admin_block(client, monkeypatch):
    import json as _json

    from app.models import OAuthState
    from app.security import encrypt

    headers = register(client, "Asha Rao", "student")
    monkeypatch.setenv("MS_CLIENT_ID", "00000000-0000-0000-0000-000000000000")
    monkeypatch.setenv("MS_CLIENT_SECRET", "placeholder")

    unknown = client.post("/api/integrations/teams/callback", data={"state": "nope", "code": "x"}, follow_redirects=False)
    assert unknown.status_code == 303 and unknown.headers["location"].endswith("/connections?teams=expired")

    with SessionLocal() as db:
        user = db.scalar(select(User))
        db.add(OAuthState(state="s1", user_id=user.id, flow=encrypt(_json.dumps({"state": "s1"}))))
        db.commit()
    blocked = client.post(
        "/api/integrations/teams/callback",
        data={
            "state": "s1",
            "error": "access_denied",
            "error_description": "AADSTS90094: The grant requires admin permission.",
        },
        follow_redirects=False,
    )
    assert blocked.headers["location"].endswith("/connections?teams=needs_consent")
    status = client.get("/api/integrations/teams", headers=headers).json()
    assert status["status"] == "needs_consent" and "administrator" in status["last_error"]
    # The one-time state is consumed.
    replay = client.post("/api/integrations/teams/callback", data={"state": "s1", "code": "x"}, follow_redirects=False)
    assert replay.headers["location"].endswith("teams=expired")
