"""Deterministic prioritisation: what to work on next, and how to spend a block of free time.

The idea is simple and explainable: an item is urgent when the work it still needs takes up a
large share of the time left before it is due. A 3-hour lab due in 10 hours outranks a
20-minute quiz due in 6 hours. No machine learning, so every ranking comes with a reason.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

DEFAULT_EFFORT_MINUTES = 60
# Realistically you get maybe a third of the remaining wall-clock time to actually work.
USABLE_FRACTION = 1 / 3


@dataclass(frozen=True)
class Ranked:
    score: float
    tier: str
    reason: str
    start_by: datetime | None
    hours_left: float | None
    effort_minutes: int


def _humanize_hours(hours: float) -> str:
    hours = abs(hours)
    if hours < 1:
        return f"{max(1, round(hours * 60))} min"
    if hours < 48:
        return f"{round(hours)}h"
    return f"{round(hours / 24)} days"


def _humanize_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours}h {rest}m" if rest else f"{hours}h"


def rank(
    *,
    due_at: datetime | None,
    effort_minutes: int | None,
    points: int | None,
    status: str,
    allow_late: bool,
    due_recently_moved_earlier: bool = False,
    now: datetime | None = None,
) -> Ranked:
    now = now or datetime.now(timezone.utc)
    effort = effort_minutes or DEFAULT_EFFORT_MINUTES
    effort_hours = effort / 60
    effort_text = _humanize_minutes(effort)
    momentum = 4.0 if status == "working" else 0.0
    weight = min((points or 0) / 10, 10.0)

    if due_at is None:
        return Ranked(5 + momentum, "someday", f"No deadline · about {effort_text} of work", None, None, effort)

    hours_left = (due_at - now).total_seconds() / 3600
    start_by = due_at - timedelta(hours=effort_hours / USABLE_FRACTION)

    if hours_left < 0:
        if not allow_late:
            return Ranked(0, "missed", f"Closed {_humanize_hours(hours_left)} ago", None, hours_left, effort)
        return Ranked(
            900 + weight + momentum - min(-hours_left, 100) * 0.1,
            "overdue",
            f"Overdue by {_humanize_hours(hours_left)} · late turn-in still allowed",
            None,
            hours_left,
            effort,
        )

    pressure = effort_hours / max(hours_left * USABLE_FRACTION, 0.25)
    score = pressure * 100 + weight + momentum
    if due_recently_moved_earlier:
        score += 25

    if start_by <= now or hours_left <= 24:
        tier = "now"
    elif hours_left <= 24 * 4:
        tier = "soon"
    else:
        tier = "later"

    reason = f"Due in {_humanize_hours(hours_left)} · about {effort_text} of work"
    if start_by <= now:
        reason += " — start now to finish comfortably"
    elif tier == "now":
        reason += f" · start within {_humanize_hours((start_by - now).total_seconds() / 3600)}"
    elif start_by - now < timedelta(days=6):
        reason += f" · start by {start_by.strftime('%a')}"
    else:
        reason += f" · start by {start_by.day} {start_by.strftime('%b')}"
    if due_recently_moved_earlier:
        reason = "Deadline moved earlier · " + reason
    return Ranked(round(score, 2), tier, reason, start_by, round(hours_left, 2), effort)


@dataclass(frozen=True)
class Candidate:
    item_id: int
    title: str
    remaining_minutes: int
    score: float


def plan_session(candidates: list[Candidate], minutes: int) -> tuple[list[tuple[Candidate, int, bool]], int]:
    """Fill ``minutes`` of free time with the highest-priority work.

    Each item gets at most its remaining effort. Blocks shorter than 15 minutes are not
    worth starting, so leftover slivers are returned as unused time.
    """
    blocks: list[tuple[Candidate, int, bool]] = []
    left = minutes
    for candidate in sorted(candidates, key=lambda c: c.score, reverse=True):
        if left < 15:
            break
        take = min(candidate.remaining_minutes, left)
        if take < 15 and take < candidate.remaining_minutes:
            continue
        blocks.append((candidate, take, take >= candidate.remaining_minutes))
        left -= take
        # A short break between different pieces of work.
        if left >= 25 and len(blocks) < len(candidates):
            left -= 10
    return blocks, left
