from datetime import datetime, timedelta, timezone

from conftest import register

from app import llm


def _setup(client):
    teacher = register(client, "Dr Mehta", "teacher")
    student = register(client, "Asha Rao", "student")
    course = client.post("/api/courses", headers=teacher, json={"name": "Compiler Design", "code": "CS301"}).json()
    assert client.post("/api/courses/join", headers=student, json={"code": course["join_code"]}).status_code == 200
    now = datetime.now(timezone.utc)

    def post(title: str, hours: float, points: int, allow_late: bool = True) -> int:
        response = client.post(
            f"/api/courses/{course['id']}/coursework",
            headers=teacher,
            data={"title": title, "due_at": (now + timedelta(hours=hours)).isoformat(), "points": str(points), "allow_late": str(allow_late).lower()},
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def personal(title: str, hours: float) -> int:
        response = client.post("/api/work", headers=student, json={"title": title, "due_at": (now + timedelta(hours=hours)).isoformat(), "effort_minutes": 60})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    ids = {
        "overdue": post("ER diagram", -5, 15),
        "lab": post("Parser lab", 10, 20),
        "report": post("Optimisation report", 30, 25),
        "missed": post("Socket server", -48, 30, allow_late=False),
        "far": post("Term project", 24 * 10, 50),
        "revise": personal("Revise module 2", 40),
        "slides": personal("Make revision slides", 50),
    }
    assert client.patch(f"/api/work/{ids['lab']}", headers=student, json={"effort_minutes": 120, "status": "working"}).status_code == 200
    assert client.patch(f"/api/work/{ids['report']}", headers=student, json={"effort_minutes": 180}).status_code == 200
    return teacher, student, ids


def test_recovery_splits_work_inside_the_budget(client):
    _, student, ids = _setup(client)
    plan = client.get("/api/recovery?hours=4", headers=student)
    assert plan.status_code == 200, plan.text
    plan = plan.json()
    assert set(plan) == {"budget_minutes", "needed_minutes", "keep", "ask_extension", "defer", "missed", "headline"}
    assert plan["budget_minutes"] == 240
    # Overdue (60) + lab (120) + report (180) + two personal tasks (60 each); the far-off project is outside 7 days.
    assert plan["needed_minutes"] == 480

    def ids_of(bucket):
        return [i["id"] for i in plan[bucket]]

    # Highest priority first while it fits: overdue, lab; the 3h report doesn't fit so ask; the first personal
    # task still fits in the last hour; the second personal task is pushed.
    assert ids_of("keep") == [ids["overdue"], ids["lab"], ids["revise"]]
    assert ids_of("ask_extension") == [ids["report"]]
    assert ids_of("defer") == [ids["slides"]]
    assert ids_of("missed") == [ids["missed"]]
    assert ids["far"] not in ids_of("keep") + ids_of("ask_extension") + ids_of("defer")

    lab = plan["keep"][1]
    assert set(lab) == {"id", "title", "course", "source", "due_at", "minutes", "reason"}
    assert lab["course"] == "Compiler Design" and lab["source"] == "unitask" and lab["minutes"] == 120
    assert lab["reason"].startswith("Due in ") and "2h of work" in lab["reason"] and "worth 20 points" in lab["reason"]
    assert "late turn-in not allowed" in plan["missed"][0]["reason"]
    assert plan["defer"][0]["course"] is None and plan["defer"][0]["source"] == "personal"
    assert plan["headline"].startswith("You need about 8h but have 4h.")
    assert "Do these 3, ask for more time on 1, push 1 personal task." in plan["headline"]

    # Without hours, the budget is three days of the student's daily study time (240 by default).
    default = client.get("/api/recovery", headers=student).json()
    assert default["budget_minutes"] == 720
    assert len(default["keep"]) == 5 and default["ask_extension"] == [] and default["defer"] == []
    assert "over the next 3 days" in default["headline"]

    assert client.get("/api/recovery?hours=0", headers=student).status_code == 422


def test_recovery_ignores_finished_work(client):
    _, student, ids = _setup(client)
    assert client.post(f"/api/work/{ids['revise']}/local-done", headers=student, json={"done": True}).status_code == 200
    plan = client.get("/api/recovery?hours=4", headers=student).json()
    every = [i["id"] for bucket in ("keep", "ask_extension", "defer") for i in plan[bucket]]
    assert ids["revise"] not in every
    assert plan["needed_minutes"] == 420


def test_extension_draft_template_fallback(client):
    teacher, student, ids = _setup(client)
    draft = client.post(f"/api/work/{ids['report']}/extension-draft", headers=student)
    assert draft.status_code == 200, draft.text
    draft = draft.json()
    assert set(draft) == {"to", "subject", "body", "generated_by"}
    assert draft["generated_by"] == "template"
    assert draft["to"] == "Dr Mehta"
    assert "Optimisation report" in draft["subject"] and "CS301" in draft["subject"]
    assert "[reason]" in draft["body"] and draft["body"].startswith("Dear Dr Mehta,")
    assert draft["body"].rstrip().endswith("Asha Rao")
    assert "haven't been able to start" in draft["body"]
    # Started work is described as started, never with an invented excuse.
    lab = client.post(f"/api/work/{ids['lab']}/extension-draft", headers=student).json()
    assert "I have started on it" in lab["body"]
    # Personal tasks have no teacher to address.
    assert client.post(f"/api/work/{ids['revise']}/extension-draft", headers=student).json()["to"] is None
    # Teachers can't use the student endpoint.
    assert client.post(f"/api/work/{ids['report']}/extension-draft", headers=teacher).status_code == 403


def test_extension_draft_uses_the_model_when_it_keeps_the_placeholder(client, monkeypatch):
    _, student, ids = _setup(client)
    monkeypatch.setattr(llm, "generate", lambda *a, **k: {"subject": "Extension: Optimisation report", "body": "Dear Dr Mehta,\n\n[reason]\n\nThanks,\nAsha"})
    draft = client.post(f"/api/work/{ids['report']}/extension-draft", headers=student).json()
    assert draft["generated_by"] == "ai" and draft["subject"] == "Extension: Optimisation report"
    # A draft that drops the placeholder (and could invent a reason) is replaced by the template.
    monkeypatch.setattr(llm, "generate", lambda *a, **k: {"subject": "x", "body": "I was ill all week."})
    draft = client.post(f"/api/work/{ids['report']}/extension-draft", headers=student).json()
    assert draft["generated_by"] == "template" and "[reason]" in draft["body"]


def test_extension_draft_is_private_to_the_student(client):
    _, student, ids = _setup(client)
    other = register(client, "Ravi Kumar", "student")
    # Not in the class: can't see the class work, and never someone else's personal task.
    assert client.post(f"/api/work/{ids['report']}/extension-draft", headers=other).status_code == 404
    assert client.post(f"/api/work/{ids['revise']}/extension-draft", headers=other).status_code == 404
    assert client.post("/api/work/99999/extension-draft", headers=student).status_code == 404
    assert all(not client.get("/api/recovery", headers=other).json()[bucket] for bucket in ("keep", "ask_extension", "defer", "missed"))



def test_search_matches_word_prefixes(client):
    headers = register(client, "Prefix Searcher", "student")
    text = b"Normalization removes redundancy. Second normal form needs full functional dependency."
    upload = client.post(
        "/api/materials", headers=headers, data={"kind": "notes", "title": "DBMS notes"},
        files={"file": ("dbms.txt", text, "text/plain")},
    )
    assert upload.status_code in (200, 201), upload.text
    hits = client.get("/api/search?q=normaliz", headers=headers).json()["hits"]
    assert hits and hits[0]["title"] == "DBMS notes" and hits[0]["page"] == 1
