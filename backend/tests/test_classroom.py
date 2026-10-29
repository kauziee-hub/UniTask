from datetime import datetime, timedelta, timezone

from conftest import register


def iso(dt: datetime) -> str:
    return dt.isoformat()


def test_login_and_me(client):
    headers = register(client, "Asha Rao", "student")
    assert client.get("/api/auth/me", headers=headers).json()["role"] == "student"
    bad = client.post("/api/auth/login", json={"email": "asha.rao@example.edu", "password": "wrong-pass"})
    assert bad.status_code == 401
    good = client.post("/api/auth/login", json={"email": "ASHA.RAO@example.edu", "password": "correct-horse"})
    assert good.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_teacher_posts_student_turns_in_teacher_grades(client):
    teacher = register(client, "Dr Mehta", "teacher")
    student = register(client, "Asha Rao", "student")
    outsider = register(client, "Ravi Kumar", "student")

    course = client.post("/api/courses", headers=teacher, json={"name": "Compiler Design", "code": "bcse307l"}).json()
    assert course["code"] == "BCSE307L" and len(course["join_code"]) == 6

    # Students cannot create classes; teachers cannot join them.
    assert client.post("/api/courses", headers=student, json={"name": "X"}).status_code == 403
    assert client.post("/api/courses/join", headers=student, json={"code": "ZZZZZZ"}).status_code == 404
    joined = client.post("/api/courses/join", headers=student, json={"code": course["join_code"].lower()})
    assert joined.status_code == 200 and joined.json()["my_role"] == "student"
    assert joined.json()["join_code"] is None  # students never see the code

    due = datetime.now(timezone.utc) + timedelta(hours=20)
    posted = client.post(
        f"/api/courses/{course['id']}/coursework",
        headers=teacher,
        data={"title": "Parser lab", "instructions": "Build an LL(1) parser.", "due_at": iso(due), "points": "20"},
        files={"attachment": ("spec.txt", b"grammar: E -> T E'", "text/plain")},
    )
    assert posted.status_code == 201, posted.text
    work_id = posted.json()["id"]
    assert posted.json()["total"] == 1 and posted.json()["turned_in"] == 0

    # The student sees it, ranked; the outsider does not.
    work = client.get("/api/work", headers=student).json()
    assert [w["title"] for w in work] == ["Parser lab"]
    assert work[0]["priority"]["tier"] == "now"
    assert client.get("/api/work", headers=outsider).json() == []
    assert client.get(f"/api/work/{work_id}", headers=outsider).status_code == 404

    attachment = client.get(f"/api/coursework/{work_id}/attachment", headers=student).json()
    assert client.get(attachment["url"]).content == b"grammar: E -> T E'"

    # Turning in needs content; can't mark class work "done" without turning in.
    assert client.post(f"/api/work/{work_id}/turn-in", headers=student).status_code == 422
    assert client.patch(f"/api/work/{work_id}", headers=student, json={"status": "done"}).status_code == 409
    turned = client.post(
        f"/api/work/{work_id}/turn-in",
        headers=student,
        data={"text": "Attached my parser."},
        files={"file": ("parser.py", b"def parse(): pass\n", "text/x-python")},
    )
    assert turned.status_code == 200, turned.text
    assert turned.json()["status"] == "turned_in"

    # Wrong file type is rejected.
    bad_file = client.post(
        f"/api/work/{work_id}/turn-in", headers=student, files={"file": ("x.exe", b"MZ...", "application/octet-stream")}
    )
    assert bad_file.status_code == 415

    subs = client.get(f"/api/coursework/{work_id}/submissions", headers=teacher).json()
    assert subs[0]["status"] == "turned_in" and subs[0]["file_name"] == "parser.py" and subs[0]["late"] is False
    link = client.get(f"/api/submissions/{subs[0]['id']}/file", headers=teacher).json()
    assert client.get(link["url"]).content == b"def parse(): pass\n"
    assert client.get(f"/api/submissions/{subs[0]['id']}/file", headers=outsider).status_code in (403, 404)
    assert client.get(f"/api/coursework/{work_id}/submissions", headers=student).status_code == 403

    assert client.patch(f"/api/submissions/{subs[0]['id']}/grade", headers=teacher, json={"grade": 25}).status_code == 422
    graded = client.patch(
        f"/api/submissions/{subs[0]['id']}/grade", headers=teacher, json={"grade": 18, "feedback": "Good FIRST sets."}
    )
    assert graded.json()["status"] == "returned"

    mine = client.get(f"/api/work/{work_id}", headers=student).json()
    assert mine["status"] == "returned" and mine["grade"] == 18 and mine["feedback"] == "Good FIRST sets."
    summary = client.get(f"/api/coursework/{work_id}", headers=teacher).json()
    assert summary["turned_in"] == 1 and summary["returned"] == 1


def test_closed_assignment_rejects_late_work(client):
    teacher = register(client, "Dr Mehta", "teacher")
    student = register(client, "Asha Rao", "student")
    course = client.post("/api/courses", headers=teacher, json={"name": "DBMS"}).json()
    client.post("/api/courses/join", headers=student, json={"code": course["join_code"]})
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    work = client.post(
        f"/api/courses/{course['id']}/coursework",
        headers=teacher,
        data={"title": "Quiz 1", "due_at": iso(past), "allow_late": "false"},
    ).json()
    item = client.get(f"/api/work/{work['id']}", headers=student).json()
    assert item["priority"]["tier"] == "missed"
    response = client.post(f"/api/work/{work['id']}/turn-in", headers=student, data={"text": "late"})
    assert response.status_code == 409


def test_personal_tasks_today_and_plan(client):
    student = register(client, "Asha Rao", "student")
    now = datetime.now(timezone.utc)
    big = client.post(
        "/api/work",
        headers=student,
        json={"title": "Revise unit 3", "due_at": iso(now + timedelta(hours=10)), "effort_minutes": 180},
    ).json()
    small = client.post(
        "/api/work",
        headers=student,
        json={"title": "Read paper", "due_at": iso(now + timedelta(hours=6)), "effort_minutes": 20},
    ).json()
    client.post("/api/work", headers=student, json={"title": "Project report", "due_at": iso(now + timedelta(days=9))})

    today = client.get("/api/today", headers=student).json()
    # 3h of work due in 10h is under more pressure than 20 min due in 6h.
    assert today["next"]["id"] == big["id"]
    assert [i["id"] for i in today["focus"]] == [small["id"]]
    assert [i["title"] for i in today["upcoming"]] == ["Project report"]

    plan = client.get("/api/plan?minutes=120", headers=student).json()
    assert plan["blocks"][0]["item_id"] == big["id"] and plan["blocks"][0]["minutes"] == 120
    assert plan["blocks"][0]["finishes_item"] is False

    done = client.patch(f"/api/work/{small['id']}", headers=student, json={"status": "done"})
    assert done.json()["status"] == "turned_in"
    assert client.delete(f"/api/work/{small['id']}", headers=student).status_code == 204


def test_teacher_cannot_use_student_endpoints(client):
    teacher = register(client, "Dr Mehta", "teacher")
    assert client.get("/api/today", headers=teacher).status_code == 403
    assert client.get("/api/integrations/teams", headers=teacher).status_code == 403
