"""Spaced repetition and weak-topic detection from real evidence only.

Scheduling is a simplified SM-2: each review is graded again / hard / good / easy, and the interval grows
by the card's ease. Weak topics come from recorded attempts and self-reported confidence — there is
no invented "mastery percentage".
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

GRADES = {"again": 0, "hard": 1, "good": 2, "easy": 3}


def review(interval_days: float, ease: float, reps: int, lapses: int, grade: str, now: datetime | None = None):
    """Return (interval_days, ease, reps, lapses, due_at)."""
    now = now or datetime.now(timezone.utc)
    g = GRADES[grade]
    if g == 0:
        ease, reps, lapses = max(1.3, ease - 0.2), 0, lapses + 1
        return 0.0, ease, reps, lapses, now + timedelta(minutes=10)
    if reps == 0:
        interval = 1.0
    elif reps == 1:
        interval = 3.0
    else:
        interval = interval_days * ease
    if g == 1:
        interval = max(1.0, interval_days * 1.2 if reps else 1.0)
        ease = max(1.3, ease - 0.15)
    elif g == 3:
        interval *= 1.3
        ease += 0.15
    interval = round(min(interval, 180.0), 2)
    return interval, round(ease, 2), reps + 1, lapses, now + timedelta(days=interval)


@dataclass
class Evidence:
    attempts: int
    correct: int
    avg_confidence: float | None
    last_at: datetime | None


def weakness(evidence: Evidence) -> str | None:
    """A plain-language reason this topic is weak, or None."""
    if evidence.attempts >= 2:
        accuracy = evidence.correct / evidence.attempts
        if accuracy < 0.6:
            return f"{evidence.correct} of your last {evidence.attempts} answers were correct"
    if evidence.avg_confidence is not None and evidence.avg_confidence <= 2:
        return f"you rated your confidence {evidence.avg_confidence:.1f}/5"
    return None


def evidence_status(current: str, evidence: Evidence, completed_sessions: int) -> str:
    """Promote a topic's coverage only on evidence; never demote what the student set themselves."""
    order = ["not_started", "in_progress", "revised", "practised"]
    target = current
    if completed_sessions and order.index(target) < 1:
        target = "in_progress"
    if evidence.correct >= 2 and (evidence.correct / max(evidence.attempts, 1)) >= 0.7:
        target = "practised"
    return target if order.index(target) > order.index(current) else current
