"""Minimal iCalendar (RFC 5545) reading and writing — enough for Moodle feeds and calendar export."""

import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .ingest import SourceEvent


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _parse_dt(value: str, params: dict[str, str], default_tz: str) -> datetime | None:
    value = value.strip()
    try:
        if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
            day = datetime.strptime(value[:8], "%Y%m%d").date()
            # An all-day deadline means "by the end of that day" in the student's timezone.
            return datetime.combine(day, time(23, 59), ZoneInfo(default_tz)).astimezone(timezone.utc)
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        naive = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        try:
            zone = ZoneInfo(params.get("TZID", default_tz))
        except ZoneInfoNotFoundError:
            zone = ZoneInfo(default_tz)
        return naive.replace(tzinfo=zone).astimezone(timezone.utc)
    except ValueError:
        return None


def parse(text: str, *, provider: str = "ics", default_tz: str = "Asia/Kolkata") -> list[SourceEvent]:
    events: list[SourceEvent] = []
    current: dict | None = None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT" or line == "BEGIN:VTODO":
            current = {}
            continue
        if line in ("END:VEVENT", "END:VTODO") and current is not None:
            uid = current.get("UID") or f"{current.get('SUMMARY')}|{current.get('DTSTART')}"
            due = current.get("DUE") or current.get("DTEND") or current.get("DTSTART")
            summary = current.get("SUMMARY") or "Untitled"
            lowered = (summary + " " + current.get("CATEGORIES", "")).lower()
            kind = "quiz" if "quiz" in lowered else "lab" if "lab" in lowered else "assessment" if re.search(r"\b(exam|test|cat|fat)\b", lowered) else "assignment"
            events.append(
                SourceEvent(
                    provider=provider,
                    external_id=uid[:255],
                    title=re.sub(r"\s+(is due|opens|closes)$", "", summary, flags=re.I)[:200],
                    due_at=due,
                    description=current.get("DESCRIPTION"),
                    url=current.get("URL"),
                    subject=current.get("CATEGORIES"),
                    kind=kind,
                    confidence="verified",
                )
            )
            current = None
            continue
        if current is None or ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, *raw_params = head.split(";")
        params = dict(p.split("=", 1) for p in raw_params if "=" in p)
        name = name.upper()
        if name in {"DTSTART", "DTEND", "DUE"}:
            current[name] = _parse_dt(value, params, default_tz)
        elif name in {"SUMMARY", "DESCRIPTION", "URL", "UID", "CATEGORIES"}:
            current[name] = _unescape(value).strip()
    return events


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def export(items: list[dict]) -> str:
    """items: {uid, title, start (datetime), end (datetime|None), description, url}"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//UniTask//Academic calendar//EN", "CALSCALE:GREGORIAN"]
    for item in items:
        start: datetime = item["start"]
        end: datetime = item.get("end") or start + timedelta(minutes=30)
        out += [
            "BEGIN:VEVENT",
            f"UID:{item['uid']}@unitask",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}",
            f"DTEND:{end.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}",
            f"SUMMARY:{_esc(item['title'])}",
        ]
        if item.get("description"):
            out.append(f"DESCRIPTION:{_esc(item['description'])}")
        if item.get("url"):
            out.append(f"URL:{item['url']}")
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"

