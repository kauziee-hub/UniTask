"""Smoke-test a running demo image using only the Python standard library."""

import json
import sys
import time
from urllib.request import Request, urlopen

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")


def request(path, token=None, post=False):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with urlopen(Request(base + path, data=b"{}" if post else None, headers=headers), timeout=10) as response:
        body = response.read()
        return json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else body


for attempt in range(60):
    try:
        assert request("/health")["status"] == "ok"
        break
    except Exception:
        if attempt == 59:
            raise
        time.sleep(2)

assert request("/api/auth/config")["demo_enabled"]
for role in ("student", "teacher"):
    session = request(f"/api/auth/demo?role={role}", post=True)
    token = session["token"]
    assert request("/api/auth/me", token)["role"] == role
    assert request("/api/courses", token)
    if role == "student":
        assert request("/api/subjects", token)
        assert request("/api/materials", token)
        assert request("/api/exams", token)
assert b'<div id="root"' in request("/")
assert b'<div id="root"' in request("/subjects")
assert isinstance(request("/api/ai/status"), dict)
print("PASS: health, student/teacher demo sessions, seeded courses/materials/exams, SPA deep links, AI status")
