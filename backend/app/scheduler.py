"""Deterministic scheduling: fit work into real free time and say plainly what doesn't fit.

Pure functions, no database, so every edge case is unit-testable:
- free_slots(): the student's day window minus classes, labs and exams
- schedule(): earliest-deadline-first with pressure tie-breaks, chunked into focus blocks,
  capped per day, never placed after the item's deadline
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MAX_CHUNK = 90
MIN_CHUNK = 25
BREAK = 10


@dataclass
class Busy:
    start: datetime
    end: datetime
    title: str
    kind: str  # class | lab | exam | block


@dataclass
class Slot:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass
class Demand:
    key: str
    title: str
    minutes: int
    deadline: datetime | None
    kind: str = "work"  # work | study | revision | rescue
    priority: float = 0.0
    estimated: bool = False  # True when the effort is a default guess
    coursework_id: int | None = None
    topic_id: int | None = None
    exam_id: int | None = None
    reason: str = ""


@dataclass
class Block:
    demand: Demand
    start: datetime
    end: datetime
    reason: str


@dataclass
class Unfit:
    demand: Demand
    missing_minutes: int
    reason: str


@dataclass
class Outcome:
    blocks: list[Block] = field(default_factory=list)
    unfit: list[Unfit] = field(default_factory=list)
    risk: dict[str, str] = field(default_factory=dict)  # demand key -> ok | tight | cannot_fit
    load: dict[str, int] = field(default_factory=dict)  # local date -> scheduled minutes


def _hm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def weekly_busy(entries: list[dict], start: date, days: int, tz: str) -> list[Busy]:
    """Expand weekly timetable rows {weekday, start, end, title, kind} into concrete busy intervals."""
    zone = ZoneInfo(tz)
    out = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for entry in entries:
            if entry["weekday"] == day.weekday():
                out.append(
                    Busy(
                        datetime.combine(day, _hm(entry["start"]), zone).astimezone(timezone.utc),
                        datetime.combine(day, _hm(entry["end"]), zone).astimezone(timezone.utc),
                        entry["title"],
                        entry.get("kind", "class"),
                    )
                )
    return out


def conflicts(busy: list[Busy]) -> list[tuple[Busy, Busy]]:
    ordered = sorted(busy, key=lambda b: b.start)
    clashes = []
    for i, first in enumerate(ordered):
        for second in ordered[i + 1 :]:
            if second.start >= first.end:
                break
            clashes.append((first, second))
    return clashes


def free_slots(now: datetime, days: int, tz: str, day_start: str, day_end: str, busy: list[Busy]) -> list[Slot]:
    zone = ZoneInfo(tz)
    local_today = now.astimezone(zone).date()
    slots: list[Slot] = []
    for offset in range(days):
        day = local_today + timedelta(days=offset)
        window_start = datetime.combine(day, _hm(day_start), zone).astimezone(timezone.utc)
        window_end = datetime.combine(day, _hm(day_end), zone).astimezone(timezone.utc)
        cursor = max(window_start, now)
        for b in sorted((b for b in busy if b.end > cursor and b.start < window_end), key=lambda b: b.start):
            if b.start > cursor:
                slots.append(Slot(cursor, min(b.start, window_end)))
            cursor = max(cursor, b.end)
        if cursor < window_end:
            slots.append(Slot(cursor, window_end))
    return [s for s in slots if s.minutes >= MIN_CHUNK]


def schedule(demands: list[Demand], slots: list[Slot], *, daily_cap: int, tz: str, now: datetime) -> Outcome:
    zone = ZoneInfo(tz)
    far = now + timedelta(days=3650)
    outcome = Outcome()
    free = [Slot(s.start, s.end) for s in sorted(slots, key=lambda s: s.start)]
    used_per_day: dict[date, int] = {}

    # Earliest deadline first; when deadlines tie, the bigger/higher-pressure job goes first so it
    # isn't squeezed into whatever is left.
    ordered = sorted(demands, key=lambda d: (d.deadline or far, -d.priority, -d.minutes))
    for demand in ordered:
        remaining = demand.minutes
        last_end: datetime | None = None
        for slot in free:
            if remaining <= 0 or (demand.deadline and slot.start >= demand.deadline):
                break
            # A long free stretch takes several focus blocks, each followed by a short break.
            while remaining > 0:
                if demand.deadline and slot.start >= demand.deadline:
                    break
                day = slot.start.astimezone(zone).date()
                room_today = daily_cap - used_per_day.get(day, 0)
                limit_end = min(slot.end, demand.deadline) if demand.deadline else slot.end
                available = int((limit_end - slot.start).total_seconds() // 60)
                take = min(remaining, MAX_CHUNK, available, room_today)
                if take <= 0 or (take < MIN_CHUNK and take < remaining):
                    break
                start, end = slot.start, slot.start + timedelta(minutes=take)
                outcome.blocks.append(Block(demand, start, end, demand.reason))
                used_per_day[day] = used_per_day.get(day, 0) + take
                remaining -= take
                last_end = end
                slot.start = min(slot.end, end + timedelta(minutes=BREAK))
        if remaining > 0:
            if demand.deadline and demand.deadline <= now:
                why = "Already past its deadline"
            elif demand.deadline:
                why = f"Needs {remaining} more min of free time before the deadline than you have"
            else:
                why = f"{remaining} min didn't fit in the planning window"
            outcome.unfit.append(Unfit(demand, remaining, why))
            outcome.risk[demand.key] = "cannot_fit"
        elif demand.deadline and last_end and (demand.deadline - last_end) < timedelta(hours=12):
            outcome.risk[demand.key] = "tight"
        else:
            outcome.risk[demand.key] = "ok"
        free = [s for s in free if s.minutes >= MIN_CHUNK]

    for block in outcome.blocks:
        key = block.start.astimezone(zone).date().isoformat()
        outcome.load[key] = outcome.load.get(key, 0) + int((block.end - block.start).total_seconds() // 60)
    outcome.blocks.sort(key=lambda b: b.start)
    return outcome
