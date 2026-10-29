"""Pure logic: scheduler, exam rescue, spaced revision, iCalendar, syllabus and past-paper parsing, date reading."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app import ics, rescue, revision, scheduler
from app.academic import cluster_questions, parse_questions, parse_syllabus, pattern_key
from app.routers.imports import find_date

UTC = timezone.utc
NOW = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)  # a Monday


def slots_for(days=1, start="09:00", end="17:00", busy=()):
    return scheduler.free_slots(NOW, days, "UTC", start, end, list(busy))


# ---------------------------------------------------------------- scheduler


def test_free_slots_skip_classes_and_exams():
    busy = [
        scheduler.Busy(NOW.replace(hour=10), NOW.replace(hour=11), "Maths", "class"),
        scheduler.Busy(NOW.replace(hour=14), NOW.replace(hour=16), "Physics exam", "exam"),
    ]
    slots = slots_for(busy=busy)
    assert [(s.start.hour, s.end.hour) for s in slots] == [(9, 10), (11, 14), (16, 17)]


def test_never_scheduled_after_the_deadline_and_reports_what_does_not_fit():
    deadline = NOW.replace(hour=11)
    demand = scheduler.Demand("work:1", "Lab report", 180, deadline, estimated=True)
    outcome = scheduler.schedule([demand], slots_for(), daily_cap=600, tz="UTC", now=NOW)
    assert all(b.end <= deadline for b in outcome.blocks)
    assert sum((b.end - b.start).seconds // 60 for b in outcome.blocks) == 90  # 09:00-10:30, then only a 20 min sliver
    assert outcome.risk["work:1"] == "cannot_fit"
    assert outcome.unfit[0].missing_minutes == 90 and outcome.unfit[0].demand.estimated


def test_shared_deadline_puts_the_bigger_job_first():
    deadline = NOW + timedelta(days=2)
    small = scheduler.Demand("small", "Quiz prep", 30, deadline)
    big = scheduler.Demand("big", "Project", 120, deadline)
    outcome = scheduler.schedule([small, big], slots_for(days=2), daily_cap=600, tz="UTC", now=NOW)
    assert outcome.blocks[0].demand.key == "big"
    assert outcome.risk == {"big": "ok", "small": "ok"}


def test_exam_overlapping_a_deadline_blocks_that_time():
    exam = scheduler.Busy(NOW.replace(hour=9), NOW.replace(hour=12), "Exam", "exam")
    demand = scheduler.Demand("w", "Essay", 60, NOW.replace(hour=13))
    outcome = scheduler.schedule([demand], slots_for(busy=[exam]), daily_cap=600, tz="UTC", now=NOW)
    assert outcome.blocks[0].start >= exam.end
    assert outcome.risk["w"] == "tight"


def test_exam_tomorrow_with_too_little_time():
    deadline = NOW + timedelta(days=1)
    demand = scheduler.Demand("exam:1", "Prepare", 600, deadline, kind="study")
    outcome = scheduler.schedule([demand], slots_for(days=2), daily_cap=240, tz="UTC", now=NOW)
    assert sum((b.end - b.start).seconds // 60 for b in outcome.blocks) == 240  # the daily cap holds
    assert outcome.unfit[0].missing_minutes == 360


def test_past_deadline_is_called_out():
    demand = scheduler.Demand("late", "Late lab", 60, NOW - timedelta(hours=1))
    outcome = scheduler.schedule([demand], slots_for(), daily_cap=600, tz="UTC", now=NOW)
    assert outcome.unfit[0].reason == "Already past its deadline"


def test_timetable_conflicts_are_detected():
    rows = [
        {"weekday": 0, "start": "09:00", "end": "10:00", "title": "Maths"},
        {"weekday": 0, "start": "09:30", "end": "11:00", "title": "Physics lab", "kind": "lab"},
        {"weekday": 1, "start": "09:00", "end": "10:00", "title": "Chemistry"},
    ]
    busy = scheduler.weekly_busy(rows, date(2026, 11, 2), 7, "Asia/Kolkata")
    clashes = scheduler.conflicts(busy)
    assert len(clashes) == 1 and {clashes[0][0].title, clashes[0][1].title} == {"Maths", "Physics lab"}
    assert busy[0].start == datetime(2026, 11, 2, 3, 30, tzinfo=UTC)  # 09:00 IST


# ---------------------------------------------------------------- exam rescue


def topic(id, status="not_started", pyq=0, deps=0, pre=(), weak=False):
    return rescue.TopicInput(id=id, title=f"T{id}", module="M", status=status, pyq_count=pyq, dependants=deps, prerequisites=pre, weak=weak)


def test_rescue_respects_budget_and_explains_exclusions():
    topics = [topic(i) for i in range(1, 7)]
    chosen, excluded, needed = rescue.plan(topics, 120, "week")
    assert needed == 360
    assert sum(p.minutes for p in chosen) <= 108  # 90% of the budget
    assert excluded and all("Didn't fit" in reason for _, _, reason in excluded)


def test_rescue_prefers_frequently_asked_topics():
    topics = [topic(1), topic(2, pyq=3)]
    chosen, _, _ = rescue.plan(topics, 60, "tomorrow")
    assert [p.topic.id for p in chosen] == [2]
    assert "asked 3× in your past papers" in chosen[0].reason


def test_rescue_keeps_prerequisites_first():
    topics = [topic(1), topic(2, pyq=4, pre=(1,))]
    chosen, _, _ = rescue.plan(topics, 200, "week")
    assert [p.topic.id for p in chosen] == [1, 2]


def test_weak_mode_drops_finished_topics():
    topics = [topic(1, status="practised"), topic(2, status="practised", weak=True), topic(3)]
    chosen, _, _ = rescue.plan(topics, 300, "weak")
    assert {p.topic.id for p in chosen} == {2, 3}


# ---------------------------------------------------------------- revision


def test_spaced_review_intervals():
    interval, ease, reps, lapses, due = revision.review(0, 2.5, 0, 0, "good", NOW)
    assert (interval, reps) == (1.0, 1) and due == NOW + timedelta(days=1)
    interval, ease, reps, lapses, due = revision.review(interval, ease, reps, lapses, "good", NOW)
    assert interval == 3.0
    interval, ease2, reps, lapses, due = revision.review(interval, ease, reps, lapses, "easy", NOW)
    assert interval > 3.0 * ease and ease2 > ease
    interval, _, reps, lapses, due = revision.review(interval, ease2, reps, lapses, "again", NOW)
    assert (interval, reps, lapses) == (0.0, 0, 1) and due == NOW + timedelta(minutes=10)


def test_weakness_comes_from_evidence_only():
    assert revision.weakness(revision.Evidence(3, 1, None, None)) == "1 of your last 3 answers were correct"
    assert "confidence" in revision.weakness(revision.Evidence(0, 0, 1.5, None))
    assert revision.weakness(revision.Evidence(4, 4, 4.0, None)) is None
    assert revision.weakness(revision.Evidence(1, 0, None, None)) is None  # one answer isn't a pattern
    assert revision.evidence_status("revised", revision.Evidence(1, 0, None, None), 3) == "revised"  # never demotes


# ---------------------------------------------------------------- calendars


MOODLE = """BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:1234@moodle.example.edu\r
SUMMARY:Parser lab is due\r
DESCRIPTION:Build an LL(1) parser\\, then test it.\r
CATEGORIES:BCSE307L\r
DTSTART;TZID=Asia/Kolkata:20261105T235900\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:quiz@moodle\r
SUMMARY:Quiz 2 closes\r
DTSTART;VALUE=DATE:20261110\r
DESCRIPTION:A very long description that the server folded across\r
  two lines\r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_ics_parse_moodle_feed():
    events = ics.parse(MOODLE, provider="moodle_ics", default_tz="Asia/Kolkata")
    assert [e.title for e in events] == ["Parser lab", "Quiz 2"]
    assert events[0].due_at == datetime(2026, 11, 5, 18, 29, tzinfo=UTC)
    assert events[0].description == "Build an LL(1) parser, then test it."
    assert events[0].subject == "BCSE307L" and events[0].kind == "lab"
    assert events[1].kind == "quiz" and events[1].due_at.astimezone(ZoneInfo("Asia/Kolkata")).hour == 23
    assert "folded across two lines" in events[1].description


def test_ics_export_escapes_text():
    out = ics.export([{"uid": "x", "title": "Due: Lab, part 1; draft", "start": NOW}])
    assert "SUMMARY:Due: Lab\\, part 1\\; draft" in out and out.count("BEGIN:VEVENT") == 1


def test_find_date_reads_common_formats():
    tz = ZoneInfo("Asia/Kolkata")
    today = date(2026, 10, 29)
    assert find_date("Submit by 12 Nov, 5pm", tz, today) == datetime(2026, 11, 12, 17, 0, tzinfo=tz)
    assert find_date("due 03/11/2026", tz, today).date() == date(2026, 11, 3)
    assert find_date("Quiz on Jan 4", tz, today).date() == date(2027, 1, 4)  # next occurrence, not last January
    assert find_date("submit tomorrow 23:00", tz, today) == datetime(2026, 10, 30, 23, 0, tzinfo=tz)
    assert find_date("no date here", tz, today) is None


# ---------------------------------------------------------------- syllabus and past papers


def test_parse_syllabus_modules_and_topics():
    text = """Module 1: Lexical Analysis  6 hours
    Tokens, lexemes, patterns; Regular expressions, finite automata
    Module 2: Syntax Analysis
    Context free grammars, LL(1) parsing, LR parsing
    Text Books
    Aho, Compilers"""
    modules = parse_syllabus(text)
    assert [m["title"] for m in modules] == ["Lexical Analysis", "Syntax Analysis"]
    assert "Regular expressions" in modules[0]["topics"] and "LL(1) parsing" in modules[1]["topics"]
    assert all("Aho" not in t for m in modules for t in m["topics"])


def test_parse_questions_with_marks_and_pages():
    pages = ["Q1. Explain AVL tree rotations with an example. [10]\nQ2) Define hashing and its uses (5 marks)", "3. Explain BFS and DFS with applications [15]"]
    questions = parse_questions(pages)
    assert [(q["label"], q["marks"], q["page_no"]) for q in questions] == [("Q1", 10, 1), ("Q2", 5, 1), ("Q3", 15, 2)]


def test_repeated_questions_cluster_despite_rewording():
    texts = [
        "Explain AVL tree rotations with an example.",
        "Explain the rotations used in AVL trees with a suitable example.",
        "Explain collision resolution in hashing.",
    ]
    assert cluster_questions(texts) == [0, 0, 1]
    assert pattern_key("Explain AVL tree rotations.") == pattern_key("Describe the AVL tree rotation.")
