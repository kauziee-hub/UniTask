from datetime import datetime, timedelta, timezone

from app.priority import Candidate, plan_session, rank

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)


def test_effort_relative_to_time_left_drives_urgency():
    big_lab = rank(due_at=NOW + timedelta(hours=10), effort_minutes=180, points=None, status="assigned", allow_late=True, now=NOW)
    quick_quiz = rank(due_at=NOW + timedelta(hours=6), effort_minutes=20, points=None, status="assigned", allow_late=True, now=NOW)
    assert big_lab.score > quick_quiz.score
    assert big_lab.reason == "Due in 10h · about 3h of work · start within 1h"
    cramped = rank(due_at=NOW + timedelta(hours=4), effort_minutes=180, points=None, status="assigned", allow_late=True, now=NOW)
    assert cramped.reason.endswith("start now to finish comfortably")


def test_tiers():
    def tier(hours, allow_late=True):
        return rank(due_at=NOW + timedelta(hours=hours), effort_minutes=30, points=None, status="assigned", allow_late=allow_late, now=NOW).tier

    assert tier(-3) == "overdue"
    assert tier(-3, allow_late=False) == "missed"
    assert tier(5) == "now"
    assert tier(60) == "soon"
    assert tier(24 * 10) == "later"
    assert rank(due_at=None, effort_minutes=None, points=None, status="assigned", allow_late=True, now=NOW).tier == "someday"


def test_plan_session_fills_time_by_priority():
    candidates = [
        Candidate(1, "low", 60, 10),
        Candidate(2, "high", 45, 90),
        Candidate(3, "mid", 200, 50),
    ]
    blocks, left = plan_session(candidates, 150)
    assert [(c.item_id, minutes, done) for c, minutes, done in blocks] == [(2, 45, True), (3, 95, False)]
    assert left == 0
