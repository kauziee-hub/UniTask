"""End-to-end API journeys for the student workspace, including isolation between students."""

from datetime import datetime, timedelta, timezone

import pytest

from app import llm
from conftest import register

NOTES = (
    "Lexical analysis groups characters into tokens. Regular expressions describe token patterns.\n"
    "FIRST and FOLLOW sets are needed to build an LL(1) parsing table. FIRST(X) is the set of terminals that begin strings derived from X."
)
SYLLABUS = "Module 1: Lexical analysis\nTokens and lexemes, Regular expressions\nModule 2: Syntax analysis\nFIRST and FOLLOW sets, LL(1) parsing"


def subject(client, headers, name="Compiler Design"):
    response = client.post("/api/subjects", headers=headers, json={"name": name, "code": "cs301"})
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, headers, course_id, name="notes.txt", body=NOTES, kind="notes", year=None):
    data = {"course_id": str(course_id), "kind": kind}
    if year:
        data["year"] = str(year)
    return client.post("/api/materials", headers=headers, data=data, files={"file": (name, body.encode(), "text/plain")})


def test_syllabus_materials_search_and_isolation(client):
    riya = register(client, "Riya", "student")
    ravi = register(client, "Ravi", "student")
    course = subject(client, riya)
    assert course["code"] == "CS301" and course["editable"]

    extracted = client.post(f"/api/subjects/{course['id']}/syllabus/extract", headers=riya, json={"text": SYLLABUS})
    assert extracted.status_code == 200, extracted.text
    assert extracted.json()["method"] == "rules" and extracted.json()["syllabus"]["unconfirmed"] == 6
    confirmed = client.post(f"/api/subjects/{course['id']}/syllabus/confirm", headers=riya, json={"accept": True}).json()
    assert confirmed["unconfirmed"] == 0 and confirmed["topic_count"] == 4

    material = upload(client, riya, course["id"])
    assert material.status_code == 201, material.text
    assert material.json()["status"] == "ready" and material.json()["page_count"] == 1
    assert upload(client, riya, course["id"]).status_code == 409  # same file twice

    hits = client.get("/api/search", headers=riya, params={"q": "FOLLOW sets"}).json()["hits"]
    assert hits and hits[0]["page"] == 1 and hits[0]["material_id"] == material.json()["id"]
    page = client.get(f"/api/materials/{material.json()['id']}/pages/1", headers=riya).json()
    assert "LL(1)" in page["text"]
    link = client.get(f"/api/materials/{material.json()['id']}/file", headers=riya, params={"inline": True}).json()
    file = client.get(link["url"])
    assert file.content == NOTES.encode() and file.headers["content-disposition"].startswith("inline")

    syllabus = client.get(f"/api/subjects/{course['id']}/syllabus", headers=riya).json()
    first_follow = next(t for m in syllabus["modules"] for t in m["topics"] if t["title"] == "FIRST and FOLLOW sets")
    assert first_follow["material_pages"] == 1  # the notes page was linked to the topic

    # Another student sees none of it.
    mid = material.json()["id"]
    assert client.get(f"/api/materials/{mid}", headers=ravi).status_code == 404
    assert client.get(f"/api/materials/{mid}/file", headers=ravi).status_code == 404
    assert client.get(f"/api/subjects/{course['id']}/syllabus", headers=ravi).status_code == 404
    assert client.get(f"/api/topics/{first_follow['id']}", headers=ravi).status_code == 404
    assert client.patch(f"/api/topics/{first_follow['id']}", headers=ravi, json={"status": "practised"}).status_code == 404
    assert client.get("/api/search", headers=ravi, params={"q": "FOLLOW sets"}).json()["hits"] == []
    assert client.get("/api/subjects", headers=ravi).json() == []


def test_tutor_cites_only_real_sources_and_learns_from_mistakes(client, monkeypatch):
    riya = register(client, "Riya", "student")
    course = subject(client, riya)
    client.post(f"/api/subjects/{course['id']}/syllabus/extract", headers=riya, json={"text": SYLLABUS})
    upload(client, riya, course["id"])
    topic = next(t for m in client.get(f"/api/subjects/{course['id']}/syllabus", headers=riya).json()["modules"] for t in m["topics"] if "FIRST" in t["title"])
    client.patch("/api/profile", headers=riya, json={"pace": "slow", "explain_style": "analogies", "background": "I struggle with formal definitions."})

    seen = {}

    def fake_generate(system, turns, *, json_mode=False, fast=False, image=None):
        if "Grade a university student's short answer" in system:
            return {"correct": False, "feedback": "FOLLOW is about what comes after A, not before.", "misconception": "Thinks FOLLOW(A) lists symbols before A"}
        seen["system"] = system
        seen["prompt"] = turns[-1].text
        return {
            "reply": "FIRST collects starting terminals [S1]. See also page 99 [S7].",
            "used_sources": ["S1", "S7"],
            "check": {"question": "What does FOLLOW(A) contain?", "expected": "Terminals that can appear right after A."},
            "memory": [{"kind": "struggle", "text": "Finds formal set definitions hard"}],
        }

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(llm, "generate", fake_generate)

    conversation = client.post("/api/tutor/conversations", headers=riya, json={"mode": "tutor", "topic_id": topic["id"]}).json()
    sent = client.post(f"/api/tutor/conversations/{conversation['id']}/messages", headers=riya, json={"text": "Explain FIRST sets"})
    assert sent.status_code == 200, sent.text
    reply = sent.json()["reply"]
    assert "[S7]" not in reply["content"] and "[S1]" in reply["content"]
    assert [c["label"] for c in reply["citations"]] == ["S1"] and reply["citations"][0]["page"] == 1
    assert reply["check"] == {"question": "What does FOLLOW(A) contain?"}  # the expected answer stays server-side
    # The tutor was told how this student learns, and given their own notes.
    assert "everyday analogy" in seen["system"] and "slow pace" in seen["system"] and "formal definitions" in seen["system"]
    assert "SOURCES:" in seen["prompt"] and "LL(1)" in seen["prompt"]

    checked = client.post(f"/api/tutor/messages/{reply['id']}/check", headers=riya, json={"answer": "Symbols before A", "confidence": 2})
    assert checked.status_code == 200 and checked.json()["correct"] is False and checked.json()["card_created"]
    assert client.post(f"/api/tutor/messages/{reply['id']}/check", headers=riya, json={"answer": "again"}).status_code == 409
    memory = client.get("/api/tutor/memory", headers=riya).json()["memories"]
    assert {m["kind"] for m in memory} == {"struggle", "misconception"}
    revision = client.get("/api/revision", headers=riya).json()
    assert revision["due_count"] == 1 and revision["due"][0]["origin"] == "mistake"
    # Forgetting works.
    assert client.delete(f"/api/tutor/memory/{memory[0]['id']}", headers=riya).status_code == 204
    assert len(client.get("/api/tutor/memory", headers=riya).json()["memories"]) == 1

    other = register(client, "Ravi", "student")
    assert client.get(f"/api/tutor/conversations/{conversation['id']}", headers=other).status_code == 404
    assert client.post(f"/api/tutor/messages/{reply['id']}/check", headers=other, json={"answer": "x"}).status_code == 404


def test_ask_without_a_model_falls_back_to_the_students_pages(client):
    riya = register(client, "Riya", "student")
    course = subject(client, riya)
    upload(client, riya, course["id"])
    answer = client.post("/api/ask", headers=riya, json={"question": "What are FOLLOW sets?"}).json()
    assert "unavailable" in answer["answer"] and answer["citations"][0]["page"] == 1


def test_exam_rescue_plans_inside_the_time_left(client):
    riya = register(client, "Riya", "student")
    course = subject(client, riya)
    client.post(f"/api/subjects/{course['id']}/syllabus/extract", headers=riya, json={"text": SYLLABUS})
    upload(client, riya, course["id"], "paper.txt", "Q1. Explain FIRST and FOLLOW sets with an example. [10]\nQ2. Explain LL(1) parsing. [10]", "pyq", 2024)
    upload(client, riya, course["id"], "paper2.txt", "Q1. Explain the FIRST and FOLLOW sets of a grammar. [10]", "pyq", 2025)
    starts = datetime.now(timezone.utc) + timedelta(days=2)
    exam = client.post("/api/exams", headers=riya, json={"title": "Mid-term", "course_id": course["id"], "starts_at": starts.isoformat()}).json()
    assert exam["topic_count"] == 4 and not exam["explicit_topics"]

    pyq = client.get(f"/api/subjects/{course['id']}/pyq", headers=riya).json()
    assert pyq["groups"][0]["count"] == 2 and pyq["groups"][0]["years"] == [2024, 2025]
    assert "not what will be asked" in pyq["note"]

    plan = client.post(f"/api/exams/{exam['id']}/rescue", headers=riya, json={"mode": "tomorrow", "hours": 1}).json()
    assert plan["budget_minutes"] == 60 and plan["chosen_minutes"] <= 54
    assert plan["chosen"][0]["title"] == "FIRST and FOLLOW sets"  # asked twice in past papers
    assert plan["excluded"] and not plan["feasible"]
    applied = client.post(f"/api/exams/{exam['id']}/rescue/apply", headers=riya, json={"mode": "tomorrow", "hours": 1}).json()
    assert applied["applied"] == len(applied["schedule"]) > 0
    detail = client.get(f"/api/exams/{exam['id']}", headers=riya).json()
    assert all(b["kind"] == "rescue" and b["starts_at"] < detail["starts_at"] for b in detail["blocks"])

    other = register(client, "Ravi", "student")
    assert client.post(f"/api/exams/{exam['id']}/rescue", headers=other, json={"mode": "week"}).status_code == 404


def test_planner_sessions_and_revision_journey(client):
    riya = register(client, "Riya", "student")
    due = datetime.now(timezone.utc) + timedelta(days=2)
    work = client.post("/api/work", headers=riya, json={"title": "Essay draft", "due_at": due.isoformat(), "effort_minutes": 120}).json()
    planned = client.post("/api/planner/replan", headers=riya, json={"days": 3})
    assert planned.status_code == 200, planned.text
    blocks = [b for b in planned.json()["blocks"] if b["coursework_id"] == work["id"]]
    assert blocks and sum(b["minutes"] for b in blocks) == 120
    assert all(b["ends_at"] <= due.isoformat().replace("+00:00", "Z") or b["ends_at"] <= due.isoformat() for b in blocks)

    space = client.get(f"/api/work/{work['id']}/workspace", headers=riya).json()
    assert space["remaining_minutes"] == 120 and space["subtasks"] == []
    steps = client.post(f"/api/work/{work['id']}/breakdown", headers=riya).json()
    assert steps["method"] == "template" and len(steps["subtasks"]) == 6
    client.patch(f"/api/subtasks/{steps['subtasks'][0]['id']}", headers=riya, json={"done": True})

    session = client.post("/api/sessions", headers=riya, json={"kind": "assignment", "coursework_id": work["id"], "planned_minutes": 25}).json()
    assert session["state"] == "active" and session["work"]["status"] == "working"
    again = client.post("/api/sessions", headers=riya, json={"kind": "assignment", "coursework_id": work["id"]}).json()
    assert again["id"] == session["id"]  # resumes instead of duplicating
    client.patch(f"/api/sessions/{session['id']}", headers=riya, json={"scratch": "Thesis: ...", "checklist": [{"text": "Intro", "done": True}]})
    assert client.post(f"/api/sessions/{session['id']}/pause", headers=riya).json()["state"] == "paused"
    assert client.post(f"/api/sessions/{session['id']}/resume", headers=riya).json()["state"] == "active"
    done = client.post(f"/api/sessions/{session['id']}/complete", headers=riya, json={"outcome": "Outline finished"}).json()
    assert done["state"] == "completed" and done["scratch"] == "Thesis: ..." and done["checklist"][0]["done"]
    assert client.post(f"/api/sessions/{session['id']}/pause", headers=riya).status_code == 409

    card = client.post("/api/cards", headers=riya, json={"front": "Define a lexeme", "back": "The matched character sequence"}).json()
    reviewed = client.post(f"/api/cards/{card['id']}/review", headers=riya, json={"grade": "good"}).json()
    assert reviewed["reps"] == 1 and reviewed["due_at"] > card["due_at"]
    assert client.get("/api/revision", headers=riya).json()["due_count"] == 0

    local = client.post(f"/api/work/{work['id']}/local-done", headers=riya, json={"done": True}).json()
    assert local["local_done_at"]
    home = client.get("/api/home", headers=riya)
    assert home.status_code == 200, home.text
    assert home.json()["progress"]["items_done"] == 1
    insights = client.get("/api/insights", headers=riya)
    assert insights.status_code == 200 and len(insights.json()["study_minutes"]) == 14

    other = register(client, "Ravi", "student")
    assert client.get(f"/api/sessions/{session['id']}", headers=other).status_code == 404
    assert client.post(f"/api/cards/{card['id']}/review", headers=other, json={"grade": "good"}).status_code == 404
    assert client.get(f"/api/work/{work['id']}/workspace", headers=other).status_code == 404


def test_imports_capture_inbox_and_extension(client):
    riya = register(client, "Riya", "student")
    csv_body = "title,due,subject\nLab 5,2030-03-01,CS301\nReading log,,\n"
    imported = client.post("/api/import/file", headers=riya, files={"file": ("tasks.csv", csv_body.encode(), "text/csv")}).json()
    assert imported["created"] == 2
    again = client.post("/api/import/file", headers=riya, files={"file": ("tasks.csv", csv_body.encode(), "text/csv")}).json()
    assert again["created"] == 0 and again["unchanged"] == 2  # idempotent

    ics_body = "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:x1\nSUMMARY:Lab 5 is due\nDTSTART:20300301T120000Z\nEND:VEVENT\nEND:VCALENDAR\n"
    merged = client.post("/api/import/file", headers=riya, files={"file": ("cal.ics", ics_body.encode(), "text/calendar")}).json()
    assert merged["merged"] == 1 and merged["created"] == 0  # same assignment seen from a second source

    captured = client.post("/api/capture", headers=riya, json={"text": "Quiz 3 on hashing, due 12 Nov 2030 at 5pm"}).json()
    item = captured["items"][0]
    assert item["due_confidence"] == "inferred" and item["due_at"].startswith("2030-11-12T11:30")
    confirmed = client.post(f"/api/work/{item['id']}/confirm-due", headers=riya, json={}).json()
    assert confirmed["due_confidence"] == "manual"

    token = client.post("/api/extension/token", headers=riya).json()["token"]
    payload = {"items": [{"external_id": "v1", "title": "Digital assignment 1", "due_at": "2030-04-01T18:00:00+05:30", "subject": "CS301"}], "snapshot": True}
    assert client.post("/api/extension/ingest", json=payload, headers={"Authorization": "Bearer ut_wrong"}).status_code == 401
    ingested = client.post("/api/extension/ingest", json=payload, headers={"Authorization": f"Bearer {token}"}).json()
    assert ingested["created"] == 1
    moved = {"items": [{**payload["items"][0], "due_at": "2030-04-03T18:00:00+05:30"}], "snapshot": True}
    assert client.post("/api/extension/ingest", json=moved, headers={"Authorization": f"Bearer {token}"}).json()["due_changed"] == 1
    inbox = client.get("/api/inbox", headers=riya).json()
    assert any(i["kind"] == "due_changed" for i in inbox["items"])
    first = inbox["items"][0]
    assert client.post(f"/api/inbox/{first['id']}/dismiss", headers=riya).json()["dismissed"]
    client.post("/api/inbox/read-all", headers=riya)
    assert client.get("/api/inbox", headers=riya).json()["unread"] == 0
    other = register(client, "Ravi", "student")
    assert client.post(f"/api/inbox/{first['id']}/read", headers=other).status_code == 404

    legacy = {"subjects": [{"id": "cs305", "name": "Database Systems", "code": "CS305", "color": "#0d9488"}],
              "assignments": [{"id": "a1", "title": "ER Diagram", "subjectId": "cs305", "dueDate": "2030-05-01", "status": "Completed", "platform": "Moodle"}]}
    assert client.post("/api/import/legacy", headers=riya, json=legacy).json()["created"] == 1
    er = next(w for w in client.get("/api/work", headers=riya).json() if w["title"] == "ER Diagram")
    assert er["local_done_at"] and er["course"]["name"] == "Database Systems"


def test_timetable_attendance_calendar_and_demo(client):
    riya = register(client, "Riya", "student")
    course = subject(client, riya)
    client.post("/api/timetable", headers=riya, json={"title": "Compilers", "course_id": course["id"], "weekday": 0, "start": "09:00", "end": "10:00"})
    client.post("/api/timetable", headers=riya, json={"title": "Lab", "weekday": 0, "start": "09:30", "end": "11:00", "kind": "lab"})
    assert client.post("/api/timetable", headers=riya, json={"title": "Bad", "weekday": 0, "start": "11:00", "end": "10:00"}).status_code == 422
    assert len(client.get("/api/timetable", headers=riya).json()["conflicts"]) == 1

    client.patch("/api/profile", headers=riya, json={"attendance_threshold": 75})
    for day, present in [("2026-10-01", True), ("2026-10-02", True), ("2026-10-03", True), ("2026-10-04", False)]:
        client.post("/api/attendance", headers=riya, json={"course_id": course["id"], "date": day, "present": present})
    row = client.get("/api/attendance", headers=riya).json()["subjects"][0]
    assert (row["present"], row["total"], row["percent"], row["can_miss"]) == (3, 4, 75.0, 0)

    start = datetime.now(timezone.utc)
    events = client.get("/api/calendar", headers=riya, params={"start": start.isoformat(), "end": (start + timedelta(days=7)).isoformat()}).json()
    assert any(e["kind"] == "class" for e in events["events"])
    exported = client.get("/api/calendar/export.ics", headers=riya)
    assert exported.status_code == 200 and exported.text.startswith("BEGIN:VCALENDAR")

    assert client.post("/api/demo", headers=riya).status_code == 201
    assert client.post("/api/demo", headers=riya).status_code == 409
    demo = next(s for s in client.get("/api/subjects", headers=riya).json() if s["code"] == "DEMO")
    assert demo["materials"] == 3 and demo["pyq_count"] == 6 and demo["next_exam"]
    pyq = client.get(f"/api/subjects/{demo['id']}/pyq", headers=riya).json()
    assert pyq["groups"][0]["count"] == 2  # the reworded AVL/array questions are recognised as repeats
    assert client.delete("/api/demo", headers=riya).status_code == 204
    assert all(s["code"] != "DEMO" for s in client.get("/api/subjects", headers=riya).json())
    assert client.get("/api/materials", headers=riya).json() == []


def test_teachers_cannot_use_student_workspace_and_cron_needs_secret(client, monkeypatch):
    teacher = register(client, "Dr Mehta", "teacher")
    assert client.get("/api/home", headers=teacher).status_code == 403
    assert client.get("/api/profile", headers=teacher).status_code == 200
    assert client.post("/internal/cron/reminders").status_code == 404  # disabled without CRON_SECRET
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert client.post("/internal/cron/reminders", headers={"X-Cron-Secret": "wrong"}).status_code == 403
    assert client.post("/internal/cron/reminders", headers={"X-Cron-Secret": "s3cret"}).json() == {"job": "reminders", "queued": "inline"}
    assert client.post("/internal/cron/rm-rf", headers={"X-Cron-Secret": "s3cret"}).status_code == 404


def test_reminders_are_idempotent(client):
    from app import jobs

    riya = register(client, "Riya", "student")
    client.post("/api/work", headers=riya, json={"title": "Due soon", "due_at": (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()})
    jobs.register_all()
    jobs.run("reminders", {})
    jobs.run("reminders", {})
    reminders = [i for i in client.get("/api/inbox", headers=riya).json()["items"] if i["kind"] == "reminder"]
    assert len(reminders) == 1


def test_material_upload_uses_s3_when_configured(client, monkeypatch):
    stored = {}

    class FakeS3:
        provider = "s3"

        def put(self, key, content, content_type):
            stored[key] = content

        def read(self, key):
            return stored[key]

        def delete(self, key):
            stored.pop(key, None)

        def retrieval_url(self, key, download_name=None, inline=False):
            return f"https://bucket.s3.amazonaws.com/{key}?X-Amz-Signature=x&inline={inline}"

    fake = FakeS3()
    for module in ("app.services", "app.academic", "app.routers.library"):
        monkeypatch.setattr(f"{module}.get_storage", lambda: fake)
    riya = register(client, "Riya", "student")
    course = subject(client, riya)
    material = upload(client, riya, course["id"]).json()
    assert material["status"] == "ready" and list(stored) and list(stored)[0].startswith("materials/")
    link = client.get(f"/api/materials/{material['id']}/file", headers=riya, params={"inline": True}).json()
    assert link["url"].startswith("https://bucket.s3.amazonaws.com/materials/") and "inline=True" in link["url"]
    assert client.delete(f"/api/materials/{material['id']}", headers=riya).status_code == 204
    assert stored == {}


@pytest.mark.parametrize("path", ["/api/home", "/api/planner", "/api/revision", "/api/insights", "/api/exams", "/api/inbox", "/api/timetable", "/api/connections"])
def test_empty_workspace_pages_load(client, path):
    riya = register(client, "Riya", "student")
    response = client.get(path, headers=riya)
    assert response.status_code == 200, response.text
