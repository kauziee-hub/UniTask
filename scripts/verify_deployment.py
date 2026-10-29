"""Verify a deployed synthetic demo. Never logs bearer tokens or presigned URLs.

An optional DNS address bypasses a stale local resolver; HTTPS hostname and
certificate verification remain enabled. Obtain that address from public DNS.
"""
import argparse
import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("url")
parser.add_argument("--resolve-address")
parser.add_argument("--report", default="deployment-verification.json")
args = parser.parse_args()
base = args.url.rstrip("/")
host = urlparse(base).hostname
if args.resolve_address:
    original_resolver = socket.getaddrinfo

    def resolve(name, port, *rest, **kwargs):
        return original_resolver(args.resolve_address if name in (host, host.encode()) else name, port, *rest, **kwargs)

    socket.getaddrinfo = resolve

report = {"url": base, "checked_at": datetime.now(timezone.utc).isoformat(), "dns_override": args.resolve_address,
          "tls_verification": True, "checks": []}


def passed(name, detail=""):
    report["checks"].append({"name": name, "passed": True, "detail": detail})
    print(f"PASS: {name} {detail}", flush=True)


with httpx.Client(timeout=75, trust_env=False, follow_redirects=True) as client:
    def call(method, path, token=None, **kwargs):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        result = client.request(method, base + path, headers=headers, **kwargs)
        if result.is_error:
            raise RuntimeError(f"{method} {path}: HTTP {result.status_code}: {result.text[:250]}")
        return result.json() if "application/json" in result.headers.get("content-type", "") else result.text

    try:
        health = call("GET", "/health")
        assert health["status"] == "ok"
        passed("Public HTTPS health", health["version"])
        config = call("GET", "/api/auth/config")
        assert config["demo_enabled"]
        passed("Signup-free demo enabled")
        for page in ("/", "/subjects", "/tutor"):
            assert '<div id="root"' in call("GET", page)
        passed("Website and SPA deep links")
        student = call("POST", "/api/auth/demo?role=student")["token"]
        teacher = call("POST", "/api/auth/demo?role=teacher")["token"]
        for role, token in (("student", student), ("teacher", teacher)):
            assert call("GET", "/api/auth/me", token)["role"] == role
            assert call("GET", "/api/courses", token)
            passed(f"{role.title()} demo entry and courses")
        for path in ("/api/home", "/api/subjects", "/api/materials", "/api/exams", "/api/insights"):
            assert call("GET", path, student)
        passed("Student dashboard, subjects, materials, exams and insights")
        courses = call("GET", "/api/subjects", student)
        course_id = next(c["id"] for c in courses if "Compiler" in c["name"])
        stamp = uuid4().hex[:10]
        content = f"AWS verification {stamp}. FIRST(X) contains terminals that begin strings derived from X. FOLLOW(A) contains terminals following A.\n"
        material = call("POST", "/api/materials", student,
                        data={"course_id": str(course_id), "title": f"AWS verification {stamp}", "kind": "notes"},
                        files={"file": (f"aws-verification-{stamp}.txt", content.encode(), "text/plain")})
        assert material["status"] == "ready", material
        file_link = call("GET", f"/api/materials/{material['id']}/file", student)["url"]
        downloaded = client.get(file_link)
        downloaded.raise_for_status()
        assert downloaded.content == content.encode()
        passed("Private S3 upload, processing and signed download")
        call("DELETE", f"/api/materials/{material['id']}", student)
        passed("Verification upload cleaned up")
        session = call("POST", "/api/sessions", student,
                       json={"kind": "revision", "title": f"AWS verification {stamp}", "planned_minutes": 5})
        session_id = session["id"]
        scratch = "Deployment verification: notes and checklist persist in RDS."
        call("PATCH", f"/api/sessions/{session_id}", student,
             json={"scratch": scratch, "checklist": [{"text": "Verify persistence", "done": True}]})
        # A fresh HTTP client proves this is server persistence rather than client state.
        with httpx.Client(timeout=30, trust_env=False) as fresh:
            saved = fresh.get(base + f"/api/sessions/{session_id}", headers={"Authorization": f"Bearer {student}"})
            saved.raise_for_status()
            assert saved.json()["scratch"] == scratch
            assert saved.json()["checklist"][0]["done"]
        call("POST", f"/api/sessions/{session_id}/complete", student, json={"outcome": "AWS persistence verification passed"})
        passed("Study Desk notes/checklist persist across fresh requests")
        conversation = call("POST", "/api/tutor/conversations", student, json={"course_id": course_id, "mode": "tutor"})
        reply = call("POST", f"/api/tutor/conversations/{conversation['id']}/messages", student,
                     json={"text": "Using my Compiler Design notes, briefly explain FIRST and FOLLOW sets with an example. Ask me one check question."})
        text = reply["reply"]["content"]
        ai = reply["ai"]
        assert text and "AI tutor is unavailable" not in text, text[:300]
        assert ai.get("last_used") == "gemini", ai
        report["tutor_reply_excerpt"] = text[:500]
        report["ai"] = ai
        passed("Real Gemini tutor inference", f"model={ai['model']}; citations={len(reply['reply']['citations'])}")
        assert call("GET", f"/api/tutor/conversations/{conversation['id']}", student)["messages"]
        passed("Tutor conversation persists in RDS")
        report["success"] = True
    except Exception as exc:
        report["success"] = False
        report["error"] = str(exc)
        print(f"FAIL: {exc}", flush=True)
    finally:
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report: {args.report}", flush=True)
raise SystemExit(0 if report["success"] else 1)
